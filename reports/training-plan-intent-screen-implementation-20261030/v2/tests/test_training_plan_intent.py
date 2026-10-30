"""Bounded original-update intent feedback; offline provider-shaped tests only."""

import copy
import json
from pathlib import Path

import pytest
from test_diagnosis_bounded_repair import payload, provider_client
from test_scoped_observation_feedback import observed_source

from headroom.diagnose import (
    _MODEL_SHRINK_NEGATION,
    diagnose_with_router,
    validate_diagnosis,
)
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.llm.router import LLMRouter
from headroom.training_plan_intent import training_update_rejection_trigger

FORBIDDEN = (
    "Set backbone.requires_grad_(False) before constructing optimizer; "
    "pass only head.parameters() to AdamW so optimizer state and grads store only head tensors."
)
SECOND = (
    "Add model.backbone.requires_grad_(False) after the selected source line to exclude "
    "backbone parameters from optimizer state and computation graph, matching the intended contract."
)


def evidence():
    value, markdown = observed_source()
    value["execution_context"]["required_optimizer_updates"] = 20
    return value, markdown


def trigger(text=FORBIDDEN, *, observed=None, policy=None):
    value = evidence()[0] if observed is None else observed
    return training_update_rejection_trigger(
        text,
        value,
        {"allow_model_change": False} if policy is None else policy,
        negation_pattern=_MODEL_SHRINK_NEGATION,
    )


@pytest.mark.parametrize(
    "text",
    [
        FORBIDDEN,
        SECOND,
        "Freeze backbone parameters; exclude backbone parameters from optimizer.",
        "Stop updating previously trainable model parameters.",
    ],
)
def test_explicit_parameter_update_reduction_contradicts_complete_original_updates(text):
    value = trigger(text)
    assert value["required_optimizer_updates"] == value["all_catalog_updated_records"] == 20
    assert value["catalog_numel"] == value["registered_parameter_numel"] == 1234
    assert value["updated_numel_per_complete_record_range"] == [1234, 1234]
    assert len(json.dumps(value, ensure_ascii=True).encode()) < 1400


@pytest.mark.parametrize(
    "text",
    [
        "Do not set backbone.requires_grad_(False); pass only head.parameters() to AdamW.",
        "Never freeze backbone parameters; exclude backbone parameters from optimizer.",
        "Avoid freezing backbone parameters; exclude backbone parameters from optimizer.",
        "Set backbone.requires_grad_(False) without excluding backbone parameters from optimizer.",
        "Rejected example: set backbone.requires_grad_(False) and pass only head.parameters() to AdamW.",
        'Do not choose "set backbone.requires_grad_(False) and pass only head.parameters() to AdamW".',
        'Never "set backbone.requires_grad_(False) and pass only head.parameters() to AdamW".',
        "Consider setting backbone.requires_grad_(False); pass only head.parameters() to AdamW.",
        "If already frozen, set backbone.requires_grad_(False); exclude backbone parameters from optimizer.",
        "Preserve all parameter updates; do not freeze or exclude them. Drop detached temporary buffers.",
        "Use optimizer-in-backward, update every parameter, and release gradients after the last consumer.",
        "Set requires_grad_(False) after the last consumer and restore True before the next update.",
        "Freeze activation buffers; remove duplicate optimizer parameter references after each update.",
        "Stop updating parameter gradients after their last consumer.",
        "Stop updating optimizer state metadata.",
        "The existing code uses requires_grad_(False); keep every update.",
        "Remove an unused eval-only teacher and keep all training parameter updates.",
        "Remove parameters that never updated from optimizer while preserving actual update unions.",
        "Set backbone.requires_grad_(False) only after the final optimizer update; exclude backbone parameters from optimizer.",
        "Set backbone.requires_grad_(False) after training is complete; pass only head.parameters() to AdamW.",
    ],
)
def test_negation_examples_unknown_and_lifetime_changes_do_not_create_new_rejections(text):
    assert trigger(text) is None


@pytest.mark.parametrize("permission", [None, True, "false", 0])
def test_only_explicit_model_change_false_enables_this_narrow_screen(permission):
    assert trigger(policy={"allow_model_change": permission}) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "no_run",
        "wrong_run",
        "wrong_source",
        "wrong_context_source",
        "wrong_round",
        "missing_round",
        "partial",
        "zero_steps",
        "missing_required",
        "wrong_required",
        "capture_incomplete",
        "reported_incomplete",
        "boundary_incomplete",
        "set_incomplete",
        "calls_inconsistent",
        "missing_registered",
        "registered_mismatch",
        "already_frozen",
        "unused_members",
        "missing_flag",
        "bool_count",
        "missing_updates",
        "short_updates",
        "not_all_updated",
    ],
)
def test_incomplete_stale_or_not_all_updated_observations_remain_unknown(mutation):
    value, _ = evidence()
    context = value["execution_context"]
    observed = context["runtime_optimizer_observations"]
    parameters, updates = observed["parameters"], observed["updates"]
    if mutation == "no_run":
        del value["run_id"]
    elif mutation == "wrong_run":
        value["run_id"] = "b" * 32
    elif mutation == "wrong_source":
        value["sources"][0]["sha256"] = "b" * 64
    elif mutation == "wrong_context_source":
        context["source_files"][0]["sha256"] = "b" * 64
    elif mutation == "wrong_round":
        observed["selected_round"] = 1
    elif mutation == "missing_round":
        del context["selected_round"]
    elif mutation == "partial":
        observed["status"] = "partial"
    elif mutation == "zero_steps":
        observed["logical_updates"] = 0
    elif mutation == "missing_required":
        del context["required_optimizer_updates"]
    elif mutation == "wrong_required":
        context["required_optimizer_updates"] = 19
    elif mutation in {
        "capture_incomplete",
        "reported_incomplete",
        "boundary_incomplete",
        "set_incomplete",
        "calls_inconsistent",
    }:
        key = {
            "capture_incomplete": "capture_complete",
            "reported_incomplete": "reported_complete",
            "boundary_incomplete": "logical_boundary_complete",
            "set_incomplete": "parameter_update_sets_complete",
            "calls_inconsistent": "optimizer_call_counts_consistent",
        }[mutation]
        observed[key] = False
    elif mutation == "missing_registered":
        del parameters["registered_parameter_numel"]
    elif mutation == "registered_mismatch":
        parameters["registered_parameter_numel"] = 1235
    elif mutation == "already_frozen":
        parameters["requires_grad_false_entries"] = 1
    elif mutation == "unused_members":
        updates["updated_numel_per_complete_record_range"] = [1233, 1233]
    elif mutation == "missing_flag":
        del parameters["catalog_numel_matches_registered_count"]
    elif mutation == "bool_count":
        parameters["catalog_entries"] = True
    elif mutation == "missing_updates":
        del observed["updates"]
    elif mutation == "short_updates":
        updates["complete_update_set_records"] = 19
    else:
        updates["all_catalog_parameters_updated_each_record"] = False
    assert trigger(observed=value) is None


def forbidden_reply(description=FORBIDDEN):
    value = payload()
    value["plan"][0]["title"] = "Preserve the original model"
    value["plan"][0]["description"] = description
    return value


def test_actual_description_not_title_controls_new_issue_and_bounded_observation_feedback():
    observed, _ = evidence()
    before = copy.deepcopy(observed)
    answer = forbidden_reply()
    original = copy.deepcopy(answer)
    result = validate_diagnosis(answer, evidence=observed, policy={"allow_model_change": False})
    issues = [issue for issue in result.issues if issue.code == "MODEL_CHANGE_FORBIDDEN"]
    assert len(issues) == 1 and issues[0].path == "/plan/0"
    assert not result.ready_for_patch and result.requires_supplement
    assert result.diagnosis.needs_more_info is False  # Host never rewrites it.
    assert "training_update_trigger" in result.supplement_request
    data = json.loads(result.supplement_request.split("Errors: ", 1)[1])
    assert len(json.dumps(data, ensure_ascii=True).encode()) <= 14000
    assert observed == before and answer == original
    answer["plan"][0]["description"] = (
        "Checkpoint activations while preserving every parameter update."
    )
    answer["plan"][0]["title"] = "Freeze backbone parameters and exclude from optimizer"
    title_only = validate_diagnosis(answer, evidence=observed, policy={"allow_model_change": False})
    assert not any(issue.code == "MODEL_CHANGE_FORBIDDEN" for issue in title_only.issues)


@pytest.mark.parametrize("corrected", [True, False])
def test_same_original_two_request_allowance_and_full_revalidation(corrected):
    observed, markdown = evidence()
    first = forbidden_reply()
    second = payload() if corrected else forbidden_reply(SECOND)
    requests = []
    with provider_client([first, second], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=observed,
            goal="reclaim",
            policy={"allow_model_change": False},
            max_supplements=1,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert len(requests) == 2
    assert [
        request.get("max_completion_tokens", request.get("max_tokens")) for request in requests
    ] == [2000, 2000]
    assert "training_update_trigger" in requests[1]["messages"][-1]["content"]
    assert result.ready_for_patch is corrected
    if not corrected:
        assert any(issue.code == "MODEL_CHANGE_FORBIDDEN" for issue in result.issues)
        assert result.diagnosis.needs_more_info is False


def test_no_supplement_still_cannot_dispatch_a_forbidden_plan():
    observed, markdown = evidence()
    requests = []
    with provider_client([forbidden_reply()], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=observed,
            goal="reclaim",
            policy={"allow_model_change": False},
            max_supplements=0,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert len(requests) == 1 and not result.ready_for_patch


def test_two_quote_notes_are_valid_json_field_fragments_and_no_origin_component_is_installed():
    for name in ("patch.md", "patch_fix.md"):
        text = (Path(__file__).parents[1] / "headroom/prompts" / name).read_text()
        line = next(
            line for line in text.splitlines() if line.startswith("JSON transports literal source:")
        )
        fragment = line.split("the field fragment ", 1)[1].split(" decodes to ", 1)[0]
        assert json.loads(fragment) == {"new_lines": ['    label = "ready"']}
    assert not (Path(__file__).parents[1] / "headroom/patch_origin_feedback.py").exists()


def test_real_needs_more_info_is_never_cleared_by_the_new_policy_issue():
    observed, _ = evidence()
    answer = forbidden_reply()
    answer["needs_more_info"] = True
    result = validate_diagnosis(answer, evidence=observed, policy={"allow_model_change": False})
    assert result.diagnosis.needs_more_info is True
    assert not result.ready_for_patch
    assert any(issue.code == "MODEL_CHANGE_FORBIDDEN" for issue in result.issues)
