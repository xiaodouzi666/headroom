"""Only the explicit bounded planner prose changes on the actual SDK wire."""

import copy
import hashlib
import json

import pytest
from test_diagnosis_bounded_repair import payload, provider_client
from test_evidence_blockers import source

import headroom.diagnosis_protocol as protocol
from headroom.acceptance.final48_repair import implementation_pins
from headroom.diagnose import PROMPT_PATH, diagnose_with_router
from headroom.llm.router import LLMRouter


def rich_evidence():
    evidence, markdown = source()
    evidence["execution_context"].update(
        selected_round=None,
        runtime_optimizer_observations={
            "status": "observed",
            "scope": "cooperative_fixture_only",
            "updates": {"logical_updates": 20},
            "numerical_equivalence_proven": False,
        },
    )
    evidence["candidate_evidence"] = [
        {"round": 1, "decision": "revert", "candidate_selected": False}
    ]
    evidence["numerical_reference_context"] = {
        "protocol": "headroom.numerical_reference_context.v1",
        "selected_strategy": "legacy_small_batch",
        "candidate_equivalence_verified": None,
        "required_logical_updates": 20,
    }
    return evidence, markdown


def request_for(*, evidence, markdown, study_protocol=None, request_policy=None):
    requests = []
    with provider_client([payload()], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={"allow_numerics_change": False, "allow_model_change": False},
            required_saving_gb=0.5,
            verification_feedback=[
                {"round": 1, "decision": "revert", "verification_available": False}
            ],
            max_supplements=0,
            study_protocol=study_protocol,
            request_policy=request_policy,
        )
        assert result.ready_for_patch and len(client.ledger.entries) == 1
    assert len(requests) == 1
    return requests[0]


def test_lean_wire_changes_only_planner_system_and_preserves_schema_full_context_catalog(
    monkeypatch,
):
    evidence, markdown = rich_evidence()
    original = copy.deepcopy(evidence)
    lean = request_for(
        evidence=evidence, markdown=markdown, request_policy=protocol.FINAL48_DIAGNOSIS_ONLY
    )
    with monkeypatch.context() as patch:
        # Reconstruct the old bounded body using the untouched legacy source file.
        patch.setattr(protocol, "COMPACT_PROMPT_PATH", PROMPT_PATH)
        legacy = request_for(
            evidence=evidence, markdown=markdown, request_policy=protocol.FINAL48_DIAGNOSIS_ONLY
        )
    assert evidence == original
    assert lean["messages"][0] == legacy["messages"][0]  # Native schema system.
    assert lean["response_format"] == legacy["response_format"]
    assert lean["messages"][2:] == legacy["messages"][2:]
    user = json.loads(lean["messages"][2]["content"])
    assert user["evidence_markdown"] == markdown
    for key in (
        "execution_context",
        "candidate_evidence",
        "verification_feedback",
        "numerical_reference_context",
        "runtime_operator_catalog",
        "evidence_availability_catalog",
    ):
        assert key in user
    assert user["execution_context"]["runtime_optimizer_observations"]["status"] == "observed"
    assert user["numerical_reference_context"]["candidate_equivalence_verified"] is None
    expected = (
        protocol.PLANNER_COMPACT_INSTRUCTIONS
        + "\n"
        + protocol.COMPACT_PROMPT_PATH.read_text().replace(protocol.PROMPT_CAP_MARKER, "2000")
    )
    assert lean["messages"][1]["content"] == expected
    assert lean["messages"][1] != legacy["messages"][1]
    lean_compare = copy.deepcopy(lean)
    lean_compare["messages"][1] = legacy["messages"][1]
    assert lean_compare == legacy
    assert lean["max_tokens"] == 2000
    assert lean["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("study,cap", [(None, 16384), (protocol.COMMON_4000, 4000)])
def test_ordinary_and_study_wire_use_exact_legacy_prose_even_when_lean_file_absent(
    monkeypatch, tmp_path, study, cap
):
    monkeypatch.setattr(protocol, "COMPACT_PROMPT_PATH", tmp_path / "absent.md")
    evidence, markdown = rich_evidence()
    body = request_for(evidence=evidence, markdown=markdown, study_protocol=study)
    assert body["messages"][1]["content"] == PROMPT_PATH.read_text().replace(
        protocol.PROMPT_CAP_MARKER, str(cap)
    )
    assert body["max_tokens"] == cap
    assert body["chat_template_kwargs"] == {"enable_thinking": True}


def test_missing_or_invalid_lean_template_fails_closed_for_only_selected_mode(
    monkeypatch, tmp_path
):
    missing = tmp_path / "missing.md"
    monkeypatch.setattr(protocol, "COMPACT_PROMPT_PATH", missing)
    with pytest.raises(FileNotFoundError):
        protocol.diagnosis_prompt(
            PROMPT_PATH.read_text(), request_policy=protocol.FINAL48_DIAGNOSIS_ONLY
        )
    missing.write_text("No marker")
    with pytest.raises(ValueError, match="exactly one completion-cap marker"):
        protocol.diagnosis_prompt(
            PROMPT_PATH.read_text(), request_policy=protocol.FINAL48_DIAGNOSIS_ONLY
        )


def test_actual_implementation_pins_include_new_static_prompt_bytes():
    pins = implementation_pins()
    name = "headroom/prompts/diagnose_compact.md"
    raw = protocol.COMPACT_PROMPT_PATH.read_bytes()
    assert pins[name]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert pins[name]["bytes"] == len(raw)
    assert len(raw.splitlines()) <= 80
    assert protocol.COMPACT_PROMPT_PATH.read_text().count(protocol.PROMPT_CAP_MARKER) == 1


@pytest.mark.parametrize("kind", ["snapshot", "custom"])
def test_nonstandard_bounded_task_retains_its_exact_template_and_does_not_load_lean_file(
    monkeypatch, tmp_path, kind
):
    from headroom.snapshot_diagnosis import SNAPSHOT_PROMPT

    template = (
        SNAPSHOT_PROMPT.read_text()
        if kind == "snapshot"
        else "Custom task cap: " + protocol.PROMPT_CAP_MARKER
    )
    monkeypatch.setattr(protocol, "COMPACT_PROMPT_PATH", tmp_path / "absent.md")
    actual = protocol.diagnosis_prompt(template, request_policy=protocol.FINAL48_DIAGNOSIS_ONLY)
    assert actual == protocol.COMPACT_DIAGNOSIS_INSTRUCTIONS + "\n" + template.replace(
        protocol.PROMPT_CAP_MARKER, "2000"
    )


def test_actual_snapshot_sdk_wire_keeps_the_complete_readonly_snapshot_system(tmp_path):
    import pickle

    from test_snapshot_diagnosis import OfflineRuntimeFactory, execute, native_snapshot

    from headroom.snapshot_diagnosis import SNAPSHOT_PROMPT

    upload = tmp_path / "upload.pickle"
    upload.write_bytes(pickle.dumps(native_snapshot()))
    factory = OfflineRuntimeFactory()
    result = execute(upload, tmp_path, factory)
    assert result["status"] == "completed" and len(factory.requests) == 1
    expected = (
        protocol.COMPACT_DIAGNOSIS_INSTRUCTIONS
        + "\n"
        + SNAPSHOT_PROMPT.read_text().replace(protocol.PROMPT_CAP_MARKER, "2000")
    )
    body = factory.requests[0]
    assert (
        sum(
            message["role"] == "system" and message["content"] == expected
            for message in body["messages"]
        )
        == 1
    )
    assert body["max_tokens"] == 2000
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert result["verification"]["status"] == "not_run"
