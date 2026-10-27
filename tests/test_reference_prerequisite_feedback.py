"""Synthetic reference prerequisite feedback, preserving existing execution gates."""

import copy
import socket
from pathlib import Path

import pytest
from test_verify_checkpoint_reference import measured, reference

from headroom.verify import runner

GOOD = {"supported": True, "profile": "s1", "checkpointed": False}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No live network in reference feedback fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def setup(tmp_path, monkeypatch, original=None, candidate=None):
    original_script = tmp_path / "original.py"
    candidate_script = tmp_path / "candidate.py"
    original_script.write_text("x = 1\n")
    candidate_script.write_text("x = 2\n")
    baseline, after = measured("oom"), measured(transformed=True)
    after["run_dir"] = str(tmp_path / "candidate-run")
    Path(after["run_dir"]).mkdir()
    calls, preparations = [], []

    def run(script, **kwargs):
        calls.append((script, kwargs))
        return copy.deepcopy(after if len(calls) == 1 else reference())

    def contract(script):
        return copy.deepcopy(
            (original or GOOD) if script == original_script else (candidate or GOOD)
        )

    def prepare(*args):
        preparations.append(args)
        raise ValueError("synthetic binding mismatch")

    monkeypatch.setattr(runner, "run_script", run)
    monkeypatch.setattr(runner, "source_contract", contract)
    monkeypatch.setattr(runner, "prepare_reference", prepare)
    monkeypatch.setattr(
        runner, "discover_batch", lambda *_: {"found": False, "reason": "synthetic"}
    )
    monkeypatch.setattr(runner, "read_artifact_json", lambda *_: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(
        runner,
        "derive_pairing",
        lambda *_: {
            "checks": dict.fromkeys(("same_inputs", "same_effective_batch", "same_objective")),
            "source": "synthetic",
            "reasons": [],
        },
    )
    kwargs = {
        "baseline_script": original_script,
        "baseline_args": ["--batch=32"],
        "script_args": ["--batch=4"],
        "reference_strategy": runner.CHECKPOINT_STRATEGY,
        "seed": 1337,
    }
    return baseline, candidate_script, kwargs, calls, preparations


def test_candidate_contract_failure_is_not_misattributed_to_original_args(tmp_path, monkeypatch):
    baseline, script, kwargs, calls, preparations = setup(
        tmp_path, monkeypatch, candidate={"supported": False}
    )
    result = runner.verify_script(baseline, script, **kwargs)
    discovery = result["reference_discovery"]
    assert discovery["prerequisites"]["original_argv_available"] is True
    assert discovery["prerequisites"]["original_source_supported"] is True
    assert discovery["unmet_prerequisites"] == [
        "candidate_source_supported",
        "candidate_profile_supported",
    ]
    assert "candidate_source_supported" in discovery["reason"]
    assert discovery["preparation_attempted"] is False
    assert preparations == [] and len(calls) == 1
    assert result["reference"] is None
    assert result["report"].loss_equivalence == "n/a"
    assert result["report"].target_met is False


@pytest.mark.parametrize(
    "side,change,key",
    [
        ("original", {"supported": False}, "original_source_supported"),
        ("original", {"supported": 1}, "original_source_supported"),
        ("original", {"profile": "foreign"}, "original_profile_supported"),
        ("original", {"checkpointed": True}, "original_uncheckpointed"),
        ("original", {"checkpointed": None}, "original_uncheckpointed"),
        ("candidate", {"supported": False}, "candidate_source_supported"),
        ("candidate", {"profile": "foreign"}, "candidate_profile_supported"),
    ],
)
def test_each_existing_source_precondition_still_blocks_without_reference_run(
    tmp_path, monkeypatch, side, change, key
):
    contract = GOOD | change
    baseline, script, kwargs, calls, preparations = setup(tmp_path, monkeypatch, **{side: contract})
    result = runner.verify_script(baseline, script, **kwargs)
    discovery = result["reference_discovery"]
    assert discovery["unmet_prerequisites"] == [key]
    assert discovery["prerequisites"][key] is False
    assert discovery["preparation_attempted"] is False
    assert preparations == [] and len(calls) == 1
    assert result["reference"] is None and not result["report"].target_met


@pytest.mark.parametrize("kind", ["missing_args", "command_mode"])
def test_original_argv_and_standalone_requirements_still_block(tmp_path, monkeypatch, kind):
    baseline, script, kwargs, calls, preparations = setup(tmp_path, monkeypatch)
    if kind == "missing_args":
        kwargs["baseline_args"] = None
        key = "original_argv_available"
    else:
        kwargs["baseline_execution_argv"] = ["python", "original.py"]
        key = "standalone_execution"
    result = runner.verify_script(baseline, script, **kwargs)
    discovery = result["reference_discovery"]
    assert discovery["unmet_prerequisites"] == [key]
    assert preparations == [] and len(calls) == 1
    assert discovery["preparation_attempted"] is False


def test_satisfied_preconditions_do_not_claim_baseline_binding_or_swallow_real_prepare_failure(
    tmp_path, monkeypatch
):
    baseline, script, kwargs, calls, preparations = setup(tmp_path, monkeypatch)
    result = runner.verify_script(baseline, script, **kwargs)
    discovery = result["reference_discovery"]
    assert discovery["unmet_prerequisites"] == []
    assert discovery["preparation_attempted"] is True
    assert (
        discovery["reason"] == "Checkpoint reference preparation failed: synthetic binding mismatch"
    )
    assert result["reference"] is None and not result["report"].target_met
    assert len(calls) == 1 and len(preparations) == 1
    assert preparations[0][1] == kwargs["baseline_script"]
    assert preparations[0][2] == ["--batch=32"]  # Never the candidate --batch=4.
    assert calls[0][1]["script_args"] == ["--batch=4"]


def test_supported_path_keeps_original_reference_argv_and_two_mocked_runs(tmp_path, monkeypatch):
    baseline, script, kwargs, calls, preparations = setup(tmp_path, monkeypatch)

    def prepare(*args):
        preparations.append(args)
        return tmp_path / "reference.py", {}

    monkeypatch.setattr(runner, "prepare_reference", prepare)
    monkeypatch.setattr(runner, "attest_reference", lambda result, *_: result)
    result = runner.verify_script(baseline, script, **kwargs)
    assert len(calls) == 2 and len(preparations) == 1
    assert calls[0][1]["script_args"] == ["--batch=4"]
    assert calls[1][1]["script_args"] == ["--batch=32"]
    assert result["reference_discovery"]["found"] is True
    assert result["reference_discovery"]["unmet_prerequisites"] == []
    assert result["reference_discovery"]["preparation_attempted"] is True


def test_bounded_round_feedback_keeps_fixed_prerequisites_when_notes_are_truncated():
    from headroom.diagnose import round_verification_feedback
    from headroom.solver_context import solver_prompt_context

    checks = {
        "original_argv_available": True,
        "standalone_execution": True,
        "original_source_supported": True,
        "original_profile_supported": True,
        "original_uncheckpointed": True,
        "candidate_source_supported": False,
        "candidate_profile_supported": False,
    }
    row = {
        "number": 1,
        "verification": {
            "target_met": False,
            "notes": ["earlier note"] * 12 + ["precise reason beyond note limit"],
            "reference_discovery": {
                "strategy": "original_workload_checkpoint",
                "prerequisites": checks,
                "preparation_attempted": False,
                "reason": "RAW_PRIVATE_TEXT",
                "original_args": ["PRIVATE_ARG"],
                "unmet_prerequisites": ["FORGED_FREE_TEXT"],
            },
        },
    }
    kwargs = {"selected_result": None, "selected_round": None, "selected_target_met": False}
    value = round_verification_feedback(row, **kwargs)
    bounded = value["verification"]["reference_prerequisites"]
    assert value["verification"]["notes_omitted"] == 5
    assert bounded["checks"] == checks
    assert bounded["unmet"] == ["candidate_source_supported", "candidate_profile_supported"]
    assert bounded["unknown"] == []
    assert bounded["preparation_attempted"] is False
    original = copy.deepcopy(row)
    original["verification"].pop("reference_discovery")
    old = round_verification_feedback(original, **kwargs)
    comparable = copy.deepcopy(value)
    comparable["verification"].pop("reference_prerequisites")
    assert comparable == old
    context = solver_prompt_context(verification_feedback=[value])
    assert context["verification_feedback"][0]["verification"]["reference_prerequisites"] == bounded
    import json

    encoded = json.dumps(context)
    assert all(
        secret not in encoded for secret in ("RAW_PRIVATE_TEXT", "PRIVATE_ARG", "FORGED_FREE_TEXT")
    )


def test_reference_feedback_does_not_convert_missing_or_nonbool_conditions_to_pass_or_failure():
    from headroom.diagnose import round_verification_feedback

    row = {
        "number": 1,
        "verification": {
            "reference_discovery": {
                "strategy": "original_workload_checkpoint",
                "prerequisites": {
                    "original_argv_available": 1,
                    "standalone_execution": "True",
                    "candidate_source_supported": False,
                    "UNTRUSTED_KEY": True,
                },
                "preparation_attempted": 1,
            }
        },
    }
    value = round_verification_feedback(
        row, selected_result=None, selected_round=None, selected_target_met=False
    )["verification"]["reference_prerequisites"]
    assert value["unmet"] == ["candidate_source_supported"]
    assert len(value["unknown"]) == 6
    assert value["preparation_attempted"] is None
    assert "UNTRUSTED_KEY" not in value["checks"]


@pytest.mark.parametrize("discovery", [None, {}, {"strategy": "foreign", "prerequisites": GOOD}])
def test_legacy_or_unbound_discovery_does_not_add_reference_claims(discovery):
    from headroom.diagnose import round_verification_feedback

    value = round_verification_feedback(
        {"number": 1, "verification": {"reference_discovery": discovery}},
        selected_result=None,
        selected_round=None,
        selected_target_met=False,
    )
    assert "reference_prerequisites" not in value["verification"]
