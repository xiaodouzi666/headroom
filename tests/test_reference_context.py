"""Protocol capabilities reach both mock HTTP requests; no GPU/provider calls."""

import copy
import hashlib
import json

import pytest
from test_orchestrator import search_run
from test_verify_checkpoint_reference import SCRIPT, measured

from headroom.solver_context import (
    MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES,
    MAX_SOLVER_CONTEXT_BYTES,
    solver_prompt_context,
)
from headroom.verify.reference_config import NumericalReference
from headroom.verify.reference_context import numerical_reference_context


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in numerical reference context tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def bound_baseline(tmp_path, args=()):
    original = measured("oom")
    original["run_dir"] = str(tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "command": [
                    "python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                    "--",
                    *args,
                ],
            }
        )
    )
    return original


def context(baseline, **changes):
    options = changes.pop(
        "options", NumericalReference(strategy="original_workload_checkpoint", max_seconds=480)
    )
    values = {
        "baseline": baseline,
        "original_script": SCRIPT,
        "original_args": [],
        "retained_script": SCRIPT,
    }
    values.update(changes)
    return numerical_reference_context(options, **values)


def test_source_preconditions_are_not_execution_or_candidate_success(tmp_path):
    baseline = bound_baseline(tmp_path)
    before = copy.deepcopy(baseline)
    value = context(baseline)
    assert value["capability_status"] == "preconditions_observed_execution_unverified"
    assert all(value["explicit_reference_preconditions"].values())
    assert value["reference_execution_verified"] is None
    assert value["candidate_equivalence_verified"] is None
    assert (
        value["retained_source"]["source_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    )
    assert value["fallback_to_legacy"] is False
    assert value["repository_no_reference_exception_enabled"] is False
    assert (
        value["source_contract_boundary"]["microbatch_or_gradient_accumulation_rewrites_supported"]
        is False
    )
    assert value["scalar_comparison"]["automatic_loss_rescaling"] is False
    assert value["scalar_comparison"]["automatic_microbatch_aggregation"] is False
    assert "never from candidate" in value["reference_construction"]
    assert baseline == before
    assert {p.name for p in tmp_path.iterdir()} == {"artifacts", "manifest.json"}
    wire = json.dumps(value)
    for forbidden in (
        str(SCRIPT),
        "s1_batch",
        "s1_non_reentrant",
        "manual",
        "14,297",
        "22.60",
        "hidden = block",
    ):
        assert forbidden not in wire
    assert len(wire.encode()) < MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_precision",
        "missing_initialization",
        "changed_argv",
        "runtime",
        "command",
        "steps",
        "changed_source",
    ],
)
def test_insufficient_preconditions_do_not_claim_availability(tmp_path, failure):
    baseline = bound_baseline(tmp_path)
    changes = {}
    if failure == "unknown_precision":
        baseline["precision_observation"]["complete"] = False
    elif failure == "missing_initialization":
        baseline["pairing_capture"]["initial_parameters"] = []
    elif failure == "changed_argv":
        changes["original_args"] = ["--batch=1"]
    elif failure == "runtime":
        baseline["env"]["torch"] = "2.6.0"
    elif failure == "command":
        changes["command_mode"] = True
    elif failure == "steps":
        changes["required_steps"] = 19
    else:
        altered = tmp_path / "changed.py"
        altered.write_text(SCRIPT.read_text() + "\nCHANGED = True\n")
        changes["retained_script"] = altered
    value = context(baseline, **changes)
    assert value["capability_status"] == "unavailable_under_current_preconditions"
    assert not all(value["explicit_reference_preconditions"].values())
    assert value["reference_execution_verified"] is None


@pytest.mark.parametrize("shape", ["missing", "symlink", "oversized", "directory"])
def test_unreadable_source_is_unknown_without_path_or_content_leak(tmp_path, shape):
    baseline = measured("oom")
    source = tmp_path / "source.py"
    if shape == "symlink":
        source.symlink_to(SCRIPT)
    elif shape == "oversized":
        source.write_text("SECRET_SOURCE_MARKER" * 10000)
    elif shape == "directory":
        source.mkdir()
    value = context(baseline, original_script=source, retained_script=source)
    assert value["original_source"]["status"] == "unknown"
    assert value["retained_source"]["status"] == "unknown"
    assert "SECRET_SOURCE_MARKER" not in json.dumps(value)
    assert str(source) not in json.dumps(value)


def test_offload_limits_and_legacy_exception_are_descriptions_not_new_permission(tmp_path):
    baseline = bound_baseline(tmp_path)
    options = NumericalReference(
        strategy="original_saved_tensor_offload",
        disk_saved_tensor_limit_bytes=64 * 1024**3,
        max_seconds=480,
    )
    offload = context(baseline, options=options, repository_mode=True)
    assert offload["selected_strategy"] == options.strategy
    assert offload["reference_limits"]["disk_saved_tensor_limit_bytes"] == 64 * 1024**3
    assert offload["repository_no_reference_exception_enabled"] is False
    assert offload["fallback_to_legacy"] is False
    legacy = context(baseline, options=NumericalReference(), repository_mode=True)
    assert legacy["repository_no_reference_exception_enabled"] is True
    assert legacy["explicit_reference_preconditions"] is None
    assert "source_contract_boundary" not in legacy
    assert legacy["reference_execution_verified"] is None
    baseline["status"] = "completed"
    assert context(baseline)["capability_status"] == "not_needed_completed_baseline"


def test_context_does_not_transmit_baseline_argv_or_environment_secrets(tmp_path, monkeypatch):
    args = ["--api-key=SECRET_ARG_VALUE"]
    baseline = bound_baseline(tmp_path, args)
    baseline["env"]["API_KEY"] = "SECRET_ENV_VALUE"
    monkeypatch.setenv("NEBIUS_API_KEY", "SECRET_PROCESS_VALUE")
    value = context(baseline, original_args=args)
    assert value["explicit_reference_preconditions"]["original_source_and_argv_bound_to_capture"]
    assert "SECRET_" not in json.dumps(value)


def test_context_is_bounded_individually_and_with_solver_payload(tmp_path):
    value = context(bound_baseline(tmp_path))
    rendered = solver_prompt_context(numerical_reference_context=value)
    assert rendered["numerical_reference_context"] == value
    assert len(json.dumps(rendered).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    with pytest.raises(ValueError, match="numerical_reference_context"):
        solver_prompt_context(
            numerical_reference_context={"x": "x" * MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES}
        )
    with pytest.raises(ValueError):
        solver_prompt_context(numerical_reference_context={"x": float("nan")})


@pytest.mark.parametrize(
    "strategy",
    ["legacy_small_batch", "original_saved_tensor_offload", "original_workload_checkpoint"],
)
def test_protocol_reaches_first_diagnosis_and_patcher_http_requests(tmp_path, strategy):
    options = {"strategy": strategy}
    if strategy != "legacy_small_batch":
        options["max_seconds"] = 480
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}]
    result, store, calls, verifies, _ = search_run(tmp_path, plans, numerical_reference=options)
    try:
        assert result["target_met"] and len(calls) == 2
        diagnosis = json.loads(calls[0]["messages"][-1]["content"])
        patch = json.loads(calls[1]["messages"][-1]["content"])
        first = diagnosis["numerical_reference_context"]
        assert patch["evidence_context"]["numerical_reference_context"] == first
        assert first["selected_strategy"] == strategy
        assert first["reference_execution_verified"] is None
        assert first["candidate_equivalence_verified"] is None
        assert first["retained_source"]["status"] == "unsupported"
        # The synthetic verifier outcome is independent; no production gate changed.
        assert verifies[0]["kwargs"].get("reference_strategy", "legacy_small_batch") == strategy
    finally:
        store.close()


def test_default_request_builder_remains_compatible_without_capability_context():
    from headroom.diagnose import build_diagnosis_messages

    messages = build_diagnosis_messages("Offline evidence", goal="fix-oom", policy={})
    user = json.loads(messages[-1]["content"])
    assert "numerical_reference_context" not in user
    assert "numerical_reference_context" not in solver_prompt_context()


def test_static_source_read_race_remains_unknown(tmp_path, monkeypatch):
    import headroom.verify.reference_context as module

    baseline = bound_baseline(tmp_path)
    monkeypatch.setattr(
        module,
        "source_contract",
        lambda path: {
            "supported": True,
            "source_sha256": "0" * 64,
            "contract_sha256": "1" * 64,
        },
    )
    value = context(baseline)
    assert value["original_source"]["status"] == "unknown"
    assert value["retained_source"]["status"] == "unknown"
    assert value["capability_status"] == "unavailable_under_current_preconditions"


def test_extra_catalogue_and_capabilities_share_original_combined_bound(tmp_path):
    from headroom.solver_context import MAX_EVIDENCE_AVAILABILITY_CONTEXT_BYTES

    capability = context(bound_baseline(tmp_path))
    catalogue = {"protocol": "fixture", "visible_source": "observed"}
    rendered = solver_prompt_context(
        numerical_reference_context=capability,
        evidence_availability_catalog=catalogue,
    )
    assert rendered["numerical_reference_context"] == capability
    assert rendered["evidence_availability_catalog"] == catalogue
    assert len(json.dumps(rendered).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    with pytest.raises(ValueError, match="evidence_availability_catalog"):
        solver_prompt_context(
            evidence_availability_catalog={"x": "x" * MAX_EVIDENCE_AVAILABILITY_CONTEXT_BYTES}
        )
