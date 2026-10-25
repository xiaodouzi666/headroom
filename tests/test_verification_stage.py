"""Plan assessments cannot become fabricated prior measurements."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_evidence_blockers import payload, ready_source, request, source

from headroom.diagnose import (
    build_diagnosis_messages,
    diagnose_with_router,
    validate_diagnosis,
)
from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.solver_context import invocation_observation, prompt_arguments
from headroom.verify.policy import check_source_changes

CODE = "PLAN_ASSESSMENT_IS_NOT_OBSERVED_INPUT"


def future(field="plan[0].numerics_impact"):
    value = payload()
    value["evidence_requests"] = [
        request(
            field=field,
            reason="ambiguous",
            detail="The future candidate has not been measured.",
            evidence_ref=None,
            source_line_start=None,
            source_line_end=None,
        )
    ]
    return value


@pytest.mark.parametrize(
    "field",
    [
        "plan[0].numerics_impact",
        "plan[0].throughput_impact",
        "/plan/0/numerics_impact",
        "/plan/0/throughput_impact",
    ],
)
def test_future_plan_measurement_receives_feedback_without_becoming_ready(field):
    value = future(field)
    before = copy.deepcopy(value)
    checked = validate_diagnosis(value, evidence=ready_source(), policy={})
    assert CODE in {i.code for i in checked.issues}
    assert checked.requires_supplement and not checked.ready_for_patch
    assert checked.diagnosis.needs_more_info is True
    assert value == before


@pytest.mark.parametrize(
    "field",
    [
        "source.loss_weight",
        "source.rng_replay",
        "numerical_reference_context.supported",
        "policy.allow_numerics_change",
        "runtime_input_observations.actual_batch",
    ],
)
def test_genuine_prerequisites_stay_blockers_and_are_not_reinterpreted(field):
    value = future(field)
    value["evidence_requests"][0]["detail"] = (
        "Need actual candidate throughput and loss to understand this genuine missing prerequisite."
    )
    checked = validate_diagnosis(value, evidence=ready_source(), policy={})
    assert CODE not in {i.code for i in checked.issues}
    assert not checked.requires_supplement
    assert checked.diagnosis.needs_more_info and not checked.ready_for_patch


def test_unbound_or_unrecognized_plan_field_is_not_semantically_guessed():
    for field in [
        "plan[99].numerics_impact",
        "plan[0].numerics_impact.extra",
        "throughput measurement",
    ]:
        checked = validate_diagnosis(future(field), evidence=ready_source(), policy={})
        assert CODE not in {i.code for i in checked.issues}
        assert not checked.ready_for_patch


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_repeated_future_request_uses_only_existing_supplement_limit(limit):
    calls = []

    class Router:
        def chat(self, *args, **kwargs):
            calls.append(copy.deepcopy(args))
            return SimpleNamespace(parsed=future())

    evidence, markdown = source()
    checked = diagnose_with_router(
        Router(), markdown, evidence=evidence, goal="reclaim", policy={}, max_supplements=limit
    )
    assert len(calls) == limit + 1
    assert not checked.ready_for_patch and checked.diagnosis.needs_more_info
    if limit:
        assert CODE in calls[1][1][-1]["content"]


def test_model_can_clarify_stage_but_readiness_does_not_claim_measured_pass():
    answers = [future(), payload()]
    answers[1]["needs_more_info"] = False
    calls = []

    class Router:
        def chat(self, *args, **kwargs):
            calls.append(args)
            return SimpleNamespace(parsed=answers.pop(0))

    evidence, markdown = source()
    checked = diagnose_with_router(
        Router(),
        markdown,
        evidence=evidence,
        goal="reclaim",
        policy={},
        required_saving_gb=1,
        max_supplements=1,
    )
    assert len(calls) == 2 and checked.ready_for_patch
    assert checked.diagnosis.verification.compare_loss is True
    assert checked.diagnosis.verification.tolerance == 0.001
    assert "verified_pass" not in checked.diagnosis.model_dump()


@pytest.mark.parametrize("invalid", ["precision", "savings", "source", "genuine_missing"])
def test_stage_feedback_never_bypasses_other_validation(invalid):
    second = payload()
    second["needs_more_info"] = False
    required = 1
    if invalid == "precision":
        second["plan"][0]["numerics_impact"] = "minor"
    elif invalid == "savings":
        required = 2
    elif invalid == "source":
        second["root_causes"][0]["evidence_refs"] = ["invented"]
    else:
        second = future("source.loss_weight")
    answers = [future(), second]

    class Router:
        def chat(self, *args, **kwargs):
            return SimpleNamespace(parsed=answers.pop(0))

    evidence, markdown = source()
    checked = diagnose_with_router(
        Router(),
        markdown,
        evidence=evidence,
        goal="reclaim",
        policy={},
        required_saving_gb=required,
        max_supplements=1,
    )
    assert not answers and not checked.ready_for_patch
    if invalid == "genuine_missing":
        assert checked.diagnosis.needs_more_info


def invocation_evidence(arguments, *, lines=("value = 7", "consume(value)")):
    evidence, markdown = source(lines=lines)
    evidence["execution_context"]["script_args"] = prompt_arguments(arguments)
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    return evidence, markdown


def missing_invocation(evidence, field):
    reply = payload()
    reply["evidence_requests"] = [
        request(
            field=field,
            evidence_ref=field,
            source_line_start=None,
            source_line_end=None,
        )
    ]
    return validate_diagnosis(reply, evidence=evidence, policy={})


def test_complete_empty_target_args_and_missing_launcher_keep_distinct_scopes():
    evidence, markdown = invocation_evidence([])
    context = evidence["execution_context"]
    messages = build_diagnosis_messages(
        markdown, goal="reclaim", policy={}, execution_context=context
    )
    delivered = json.loads(messages[-1]["content"])
    assert delivered["execution_context"] == context
    aid = delivered["invocation_reading_aid"]
    assert aid["script_args_complete"] and aid["assignments"] == []
    assert aid["target_effective_configuration"] == "unverified"
    assert invocation_observation(context, "script_args", 0) == ("absent", None)
    assert invocation_observation(context, "execution_argv", 0) == ("unsupported", None)
    assert context["runtime_input_observations"]["status"] == "unsupported"

    target = missing_invocation(evidence, "execution_context.script_args")
    assert "EVIDENCE_AVAILABILITY_CONTRADICTED" in {i.code for i in target.issues}
    assert target.diagnosis.needs_more_info and not target.ready_for_patch
    launcher = missing_invocation(evidence, "execution_context.execution_argv")
    assert not launcher.requires_supplement
    assert launcher.diagnosis.needs_more_info and not launcher.ready_for_patch


@pytest.mark.parametrize("arguments", [None, ["--api-key=canary"], ["x" * 5000]])
def test_unknown_or_redacted_target_args_never_become_complete_empty_args(arguments):
    evidence, markdown = invocation_evidence(arguments)
    context = evidence["execution_context"]
    messages = build_diagnosis_messages(
        markdown, goal="reclaim", policy={}, execution_context=context
    )
    delivered = json.loads(messages[-1]["content"])
    assert not delivered["invocation_reading_aid"]["script_args_complete"]
    assert invocation_observation(context, "script_args", 0)[0] in {
        "unsupported",
        "unverified",
    }
    checked = missing_invocation(evidence, "execution_context.script_args")
    assert "EVIDENCE_AVAILABILITY_CONTRADICTED" not in {i.code for i in checked.issues}
    assert not checked.ready_for_patch and checked.diagnosis.needs_more_info
    assert "canary" not in json.dumps(messages)


@pytest.mark.parametrize(
    "statement,field",
    [
        ("value = os.environ['SETTING']", "source.environment_precedence"),
        ("value = config['setting']", "source.configuration_precedence"),
        ("exec(config_text)", "source.dynamic_execution"),
        ("sys.argv.extend(extra)", "source.argument_mutation"),
        ("value = parser.parse_args()", "source.parser_semantics"),
    ],
)
def test_complete_host_args_do_not_resolve_real_source_interpretation(statement, field):
    evidence, _ = invocation_evidence([], lines=(statement, "consume(value)"))
    reply = payload()
    reply["evidence_requests"] = [
        request("ambiguous", field=field, source_line_start=1, source_line_end=1)
    ]
    checked = validate_diagnosis(reply, evidence=evidence, policy={})
    assert not checked.requires_supplement
    assert checked.diagnosis.needs_more_info and not checked.ready_for_patch
    assert evidence["execution_context"]["runtime_input_observations"]["status"] == "unsupported"


def test_unconditional_visible_source_is_text_not_measured_runtime_proof():
    evidence, _ = invocation_evidence([])
    reply = payload()
    reply["evidence_requests"] = [
        request(
            "ambiguous",
            field="execution_context.runtime_input_observations.effective_value",
            evidence_ref="execution_context.runtime_input_observations",
            source_line_start=None,
            source_line_end=None,
        )
    ]
    checked = validate_diagnosis(reply, evidence=evidence, policy={})
    assert not checked.requires_supplement
    assert checked.diagnosis.needs_more_info and not checked.ready_for_patch
    entry = next(
        e
        for e in evidence["evidence_availability_catalog"]["entries"]
        if e["evidence_ref"] == "source[0]"
    )
    assert entry["availability"] == "visible" and not entry["runtime_values_verified"]


_BASE_SOURCE = """import torch
from torch import nn
width = 6
model = nn.Linear(width, width)
model.to('cuda')
loss = model(inputs).sum()
loss.backward()
optimizer.step()
"""


def test_device_placement_is_not_itself_a_model_shape_change_or_verified_pass():
    after = _BASE_SOURCE.replace("model.to('cuda')", "model.to('cpu')")
    report = check_source_changes(
        {"model.py": _BASE_SOURCE}, {"model.py": after}, policy={"allow_model_change": False}
    )
    assert report.allowed
    # Static permission says nothing about input-device compatibility, loss, or speed.
    assert report.issues == () and report.requires_runtime_verification


@pytest.mark.parametrize(
    "old,new,code",
    [
        ("width = 6", "width = 3", "MODEL_SHRUNK"),
        ("model.to('cuda')", "model.to('cuda', dtype=torch.float16)", "NUMERICS_CHANGE_FORBIDDEN"),
        ("loss.backward()", "pass", "TRAINING_TRUNCATED"),
        ("optimizer.step()", "pass", "TRAINING_TRUNCATED"),
    ],
)
def test_resource_lifetime_explanation_does_not_waive_existing_source_policies(old, new, code):
    report = check_source_changes(
        {"model.py": _BASE_SOURCE},
        {"model.py": _BASE_SOURCE.replace(old, new)},
        policy={"allow_model_change": False, "allow_numerics_change": False},
    )
    assert not report.allowed and code in {i.code for i in report.issues}


def test_explicit_forbidden_policy_dependency_is_not_cleared_by_placement_language():
    reply = payload()
    reply["needs_more_info"] = False
    reply["plan"][0]["description"] = "Change device placement after checking dependencies."
    reply["plan"][0]["requires_policy"] = ["allow_model_change"]
    checked = validate_diagnosis(
        reply, evidence=ready_source(), policy={"allow_model_change": False}
    )
    assert "POLICY_PERMISSION_DENIED" in {i.code for i in checked.issues}
    assert not checked.ready_for_patch


def test_real_message_carries_stage_and_invocation_limits_without_scenario_answers():
    _, markdown = source()
    messages = build_diagnosis_messages(markdown, goal="reclaim", policy={})
    prompt = messages[0]["content"]
    for contract in (
        "Pending candidate loss/throughput measurements belong in risk",
        "not a claim of already measured bitwise",
        "missing optional execution_argv",
        "not proof of the target's parsed values",
        "incomplete or redacted source",
        "not automatically compliant either",
        "alternative_plan and overall_feasibility use an empty ID list",
    ):
        assert contract in prompt
    for fixture_name in ("s8_two_models_resident", "unused teacher", "--tiny"):
        assert fixture_name not in prompt
