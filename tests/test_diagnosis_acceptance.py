"""Offline T1.4 acceptance chain: real analyzer/router/runtime with SDK MockTransport."""

import builtins
import hashlib
import io
import json
import os
import socket
from pathlib import Path

import httpx
import pytest

from headroom.acceptance.diagnosis import (
    SCENARIO_IDS,
    DiagnosisAcceptanceRefused,
    prepare_diagnosis_acceptance,
)
from headroom.acceptance.diagnosis import (
    execute_diagnosis_acceptance as _execute_diagnosis_acceptance,
)
from headroom.config import candidate_models
from headroom.store.db import Store


def execute_diagnosis_acceptance(*args, **kwargs):
    # Every test explicitly supplies admission limits to the production entry point.
    limits = {"run_limit_usd": "0.35", "campaign_limit_usd": "2.8", "daily_limit_usd": "12"}
    return _execute_diagnosis_acceptance(*args, **(limits | kwargs))


CATEGORIES = (
    "activations",
    "optimizer_state",
    "activations",
    "retained_graph",
    "fragmentation_candidate",
    "temporaries",
    "optimizer_state",
    "params",
)


@pytest.fixture(autouse=True)
def guard_network_and_real_credentials(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real DNS/INET is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    original_os_open = os.open

    def guarded_os_open(path, *args, **kwargs):
        if isinstance(path, (str, Path)) and Path(path).name.startswith(".env"):
            raise AssertionError("No .env descriptor access in acceptance tests")
        return original_os_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_os_open)
    for module in (builtins, io):
        original = module.open

        def guarded(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, Path)) and Path(path).name.startswith(".env"):
                raise AssertionError("No .env access in acceptance tests")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def project(tmp_path, monkeypatch):
    import headroom.timeline_plot

    monkeypatch.setattr(
        headroom.timeline_plot,
        "render_timeline",
        lambda _, path, **kwargs: Path(path).write_bytes(b"fixture-not-a-GPU-image"),
    )
    root = tmp_path / "project"
    rows, index, captures = [], [], {}
    for position, case_id in enumerate(SCENARIO_IDS):
        source = "VALUE = 1\nVALUE += 1\n"
        sha = hashlib.sha256(source.encode()).hexdigest()
        script = root / "scenarios" / case_id / "train.py"
        script.parent.mkdir(parents=True)
        script.write_text(source)
        (script.parent / "README.md").write_text(
            "OFFLINE FIXTURE truth: " + CATEGORIES[position] + "\nUnconfirmed for s5.\n"
        )
        expected = "oom" if position in {0, 3, 5} else "completed"
        rows.append(
            {
                "id": case_id,
                "script": f"scenarios/{case_id}/train.py",
                "source_root": f"scenarios/{case_id}",
                "source_sha256": sha,
                "ground_truth": CATEGORIES[position],
                "truth_status": "unverified" if position == 4 else "authored",
                "target": "fix-oom" if expected == "oom" else "reclaim",
                "expected_baseline": expected,
            }
        )
        index.append(
            {
                "id": case_id,
                "script": rows[-1]["script"],
                "root_cause": CATEGORIES[position],
                "gpu_source_sha256": sha,
            }
        )
        capture = root / "captures" / case_id
        (capture / "source").mkdir(parents=True)
        (capture / "source/train.py").write_text(source)
        result = {
            "protocol": "headroom.lab.v1",
            "run_id": "fixture-" + case_id,
            "status": expected,
            "execution_status": expected,
            "termination_reason": "oom" if expected == "oom" else "step_limit",
            "steps": 0 if expected == "oom" else 20,
            "loss_series": [],
            "capture_complete": True,
            "env": {
                "device": "cuda",
                "max_steps": 20,
                "torch": "2.5.1",
                "gpu_name": "OFFLINE FIXTURE",
            },
            "peak_allocated_bytes": 512,
            "peak_reserved_bytes": 1024,
            "step_records": [],
            "shared_gpu": False,
        }
        write(capture / "artifacts/result.json", result)
        write(
            capture / "result.json", {**result, "cleanup_verified": True, "run_dir": str(capture)}
        )
        write(capture / "artifacts/env.json", result["env"])
        write(
            capture / "manifest.json",
            {
                "device": "cuda",
                "max_steps": 20,
                "command": [
                    "python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                ],
                "source": {"files": {"train.py": {"sha256": sha}}},
            },
        )
        frames = [{"filename": "/source/train.py", "line": 2, "name": "forward"}]
        write(
            capture / "artifacts/snapshot.json",
            {
                "segments": [
                    {
                        "device": 0,
                        "address": 0,
                        "total_size": 1024,
                        "blocks": [
                            {
                                "address": 0,
                                "size": 512,
                                "state": "active_allocated",
                                "frames": frames,
                            },
                            {"address": 512, "size": 512, "state": "inactive", "frames": []},
                        ],
                    }
                ],
                "device_traces": [
                    [
                        {"action": "segment_alloc", "addr": 0, "size": 1024},
                        {"action": "alloc", "addr": 0, "size": 512, "frames": frames},
                    ]
                ],
            },
        )
        captures[case_id] = capture
    write(root / "eval/mvp_phase1.yaml", {"version": 1, "scenarios": rows})
    write(root / "scenarios/INDEX.yaml", {"version": 1, "scenarios": index})
    return root, captures


def prepare(project, output=None):
    root, captures = project
    output = output or root / "prepared"
    report = prepare_diagnosis_acceptance(captures, output, project_root=root)
    return report, output / "preparation.json"


def profile(root, *, ceiling=30000, enabled=True):
    path = root / "profile.fixture.json"
    write(
        path,
        {
            "live_enabled": enabled,
            "credit_confirmed": True,
            "available_credit_usd": "5",
            "authorized_total_usd": "5",
            "verified_at": "offline-fixture",
            "evidence": "Not provider evidence",
            "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
            "evidence_token_budget": 150000,
            "models": {
                role: {
                    "model_id": model.model_id,
                    "input_usd_per_million": "1",
                    "output_usd_per_million": "2",
                    "evidence": "offline fixture",
                    "billing": {
                        "prompt_token_ceiling": ceiling,
                        "max_prompt_utf8_bytes": 1000000,
                        "max_completion_tokens": 4000,
                        "output_cap_field": "max_completion_tokens",
                        "output_cap_includes_reasoning": True,
                        "verified": True,
                        "evidence": "offline fixture only",
                    },
                }
                for role, model in candidate_models().items()
            },
        },
    )
    env = root / "credential.fixture"
    env.write_text("NEBIUS_API_KEY=offline-acceptance-fixture\n")
    env.chmod(0o600)
    return path, env


def payload(category, ref):
    return {
        "root_causes": [
            {
                "id": "rc1",
                "title": "Observed fixture mechanism",
                "category": category,
                "bytes_gb": 0.000000512,
                "evidence_refs": [ref],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "f1",
                "type": "code",
                "title": "Preserve training",
                "description": "Release unneeded tensors while preserving the objective.",
                "expected_saving_gb": 0.000001,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Measure before keeping.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": [],
    }


def transport_for(prepared, *, mode=None):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        index = len(calls)
        calls.append(body)
        row = prepared["rows"][index]
        answer = payload(CATEGORIES[index], row["stack_ids"][0])
        if mode == "bad_reference" and index == 0:
            answer["root_causes"][0]["evidence_refs"] = ["stk_invented"]
        if mode == "wrong" and index < 2:
            answer["root_causes"][0]["category"] = "unknown"
        if mode == "needs_more":
            answer.update(root_causes=[], plan=[], needs_more_info=True)
        if mode == "supplement":
            answer["plan"][0]["expected_saving_gb"] = 0.0
        response = {
            "id": "offline",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": json.dumps(answer)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 200, "completion_tokens": 120, "total_tokens": 320},
        }
        if mode == "unknown":
            response.pop("usage")
        if mode == "expensive":
            response["usage"] = {
                "prompt_tokens": 400000,
                "completion_tokens": 120,
                "total_tokens": 400120,
            }
        if mode == "identity":
            response["model"] = "unapproved-model"
        if mode == "truncated":
            response["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=response)

    return httpx.MockTransport(handler), calls


def execute(project, prepared, path, *, mode=None, **kwargs):
    root, _ = project
    price, env = profile(root, ceiling=500000 if mode == "expensive" else 30000)
    transport, calls = transport_for(prepared, mode=mode)
    result = execute_diagnosis_acceptance(
        path,
        profile_path=price,
        env_file=env,
        transport=transport,
        execute=True,
        live_authorized=True,
        **kwargs,
    )
    return result, calls


def test_prepare_preserves_eight_inputs_and_truth_without_reading_profile(project):
    report, path = prepare(project)
    assert report["ready_count"] == 8 and report["ready_for_execution"]
    assert report["accepted"] is False and report["live_executed"] is False
    assert report["thresholds"] == {
        "required_matches": 6,
        "denominator": 8,
        "actual_call_limit_usd": "0.35",
    }
    s5 = report["rows"][4]
    assert s5["truth"]["declared_category"] == "fragmentation_candidate"
    assert s5["truth"]["scoreable_category"] is None
    assert "cache" in s5["truth"]["limitations"][0]
    for row in report["rows"]:
        assert row["capture_inputs"]["source/train.py"]["sha256"]
        assert row["evidence_tokens"] <= 150000
        messages = json.loads(
            (path.parent / "cases" / row["scenario_id"] / "messages.json").read_text()
        )
        assert "OFFLINE FIXTURE truth" not in json.dumps(messages)
        assert "root_cause" not in json.loads(messages[-1]["content"])


def test_real_router_runtime_chain_scores_seven_without_fake_live_acceptance(project):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path)
    assert len(calls) == 8
    assert result["first_cause_matches"] == 7 and result["denominator"] == 8
    assert result["fixture_gates_passed"] and not result["accepted"]
    assert result["rows"][4]["first_cause_match"] is None
    assert all(row["references_valid"] and row["response_identity_valid"] for row in result["rows"])
    assert all(row["runtime"]["usage"]["unknown_cost_calls"] == 0 for row in result["rows"])
    assert all(body["max_completion_tokens"] == 4000 for body in calls)
    assert all(
        "root_causes" in body["messages"][0]["content"] for body in calls
    )  # Actual router-added schema.
    store = Store(project[0] / "runs/acceptance/headroom.db")
    try:
        assert store.usage()["calls"] == 8
        assert store.usage()["total_cost_usd"] == result["total_cost_usd"]
    finally:
        store.close()


@pytest.mark.parametrize(
    "mode,stop",
    [
        ("unknown", "UNKNOWN_BILLING"),
        ("identity", "UNKNOWN_BILLING"),
        ("truncated", "ResponseValidationError"),
    ],
)
def test_uncertain_billing_identity_or_truncation_stops_before_next_case(project, mode, stop):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, mode=mode)
    assert len(calls) == 1 and not result["accepted"]
    assert result["stop_reason"] == stop
    assert len(result["rows"]) == 8 and all(
        row["status"] == "not_executed" for row in result["rows"][1:]
    )
    if mode != "truncated":
        assert result["total_cost_usd"] is None
        assert result["rows"][0]["runtime"]["usage"]["unknown_cost_calls"] == 1


def test_actual_cost_gate_is_not_replaced_by_the_larger_admission_cap(project):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, mode="expensive", run_limit_usd="1")
    assert len(calls) == 1
    assert result["admission_cap_per_case_usd"] == "1"
    assert result["actual_acceptance_limit_per_call_usd"] == "0.35"
    assert result["stop_reason"] == "ACTUAL_CALL_COST_EXCEEDS_035"
    assert result["rows"][0]["actual_cost_within_035"] is False


@pytest.mark.parametrize("mode", ["bad_reference", "wrong", "needs_more"])
def test_wrong_invalid_or_incomplete_diagnosis_never_passes(project, mode):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, mode=mode)
    assert len(calls) == 8
    assert not result["fixture_gates_passed"] and not result["accepted"]
    if mode == "bad_reference":
        assert result["rows"][0]["actual_stack_references"][0]["invalid_references"] == [
            "stk_invented"
        ]
    if mode == "wrong":
        assert result["first_cause_matches"] == 5
    if mode == "needs_more":
        assert all(not row["complete_diagnosis"] for row in result["rows"])


def test_missing_capture_keeps_denominator_and_blocks_execution_before_credentials(project):
    root, captures = project
    del captures[SCENARIO_IDS[0]]
    prepared, path = prepare(project)
    assert prepared["ready_count"] == 7 and prepared["rows"][0]["status"] == "missing"
    with pytest.raises(DiagnosisAcceptanceRefused, match="EIGHT_READY"):
        execute_diagnosis_acceptance(
            path, profile_path=root / ".env", execute=True, live_authorized=True
        )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("partial", "INCOMPLETE_CAPTURE"),
        ("source", "CAPTURE_SOURCE_HASH_MISMATCH"),
        ("tiny", "ORIGINAL_SCENARIO_ARGUMENTS_REQUIRED"),
        ("snapshot", "CUDA_SNAPSHOT_HISTORY_REQUIRED"),
    ],
)
def test_invalid_capture_stays_explicit_without_rewriting_original(project, mutation, reason):
    _, captures = project
    capture = captures[SCENARIO_IDS[0]]
    if mutation == "source":
        (capture / "source/train.py").write_text("DIFFERENT = True\n")
    elif mutation == "snapshot":
        write(capture / "artifacts/snapshot.json", {"segments": [], "device_traces": [[]]})
    else:
        leaf = capture / ("result.json" if mutation == "partial" else "manifest.json")
        data = json.loads(leaf.read_text())
        if mutation == "partial":
            data["capture_complete"] = False
        else:
            data["command"] += ["--", "--tiny"]
        write(leaf, data)
    before = (capture / "result.json").read_bytes()
    prepared, _ = prepare(project)
    assert prepared["rows"][0]["status"] == "invalid"
    assert prepared["rows"][0]["reason"] == reason
    assert (capture / "result.json").read_bytes() == before


@pytest.mark.parametrize("target", ["capture", "evidence", "truth"])
def test_changed_inputs_refused_before_profile_or_credentials(project, target):
    _, path = prepare(project)
    if target == "capture":
        changed = project[1][SCENARIO_IDS[0]] / "source/train.py"
    elif target == "truth":
        changed = project[0] / "scenarios" / SCENARIO_IDS[0] / "README.md"
    else:
        changed = path.parent / "cases" / SCENARIO_IDS[0] / "evidence/evidence.md"
    changed.write_text(changed.read_text() + "\nchanged")
    with pytest.raises(DiagnosisAcceptanceRefused):
        execute_diagnosis_acceptance(
            path, profile_path=project[0] / ".env", execute=True, live_authorized=True
        )


@pytest.mark.parametrize("execute_flag,authorized", [(False, False), (True, False), (False, True)])
def test_explicit_execute_and_authorization_required_before_any_file_read(
    tmp_path, execute_flag, authorized
):
    with pytest.raises(DiagnosisAcceptanceRefused, match="EXPLICIT_LIVE_AUTHORIZATION"):
        execute_diagnosis_acceptance(
            tmp_path / ".env",
            profile_path=tmp_path / ".env",
            execute=execute_flag,
            live_authorized=authorized,
        )


def test_closed_profile_has_no_dispatch(project):
    prepared, path = prepare(project)
    root, _ = project
    price, env = profile(root, enabled=False)
    transport, calls = transport_for(prepared)
    result = execute_diagnosis_acceptance(
        path,
        profile_path=price,
        env_file=env,
        transport=transport,
        execute=True,
        live_authorized=True,
    )
    assert not calls and result["stop_reason"]
    assert not result["accepted"]


def test_reusing_preparation_cannot_silently_spend_again(project):
    prepared, path = prepare(project)
    _, calls = execute(project, prepared, path)
    with pytest.raises(FileExistsError):
        execute(project, prepared, path)
    assert len(calls) == 8


def test_existing_unknown_charge_blocks_a_new_package(project):
    first, path = prepare(project)
    result, calls = execute(project, first, path, mode="unknown")
    assert len(calls) == 1 and result["stop_reason"] == "UNKNOWN_BILLING"
    second, other = prepare(project, output=project[0] / "second")
    result, calls = execute(project, second, other)
    assert not calls and not result["accepted"]
    assert result["stop_reason"] == "BudgetExceeded"


def test_strict_full_context_reservation_does_not_fit_original_035_gate(project):
    prepared, path = prepare(project)
    price, env = profile(project[0], ceiling=1048576)
    transport, calls = transport_for(prepared)
    result = execute_diagnosis_acceptance(
        path,
        profile_path=price,
        env_file=env,
        transport=transport,
        execute=True,
        live_authorized=True,
    )
    assert not calls
    assert result["stop_reason"] == "BudgetExceeded"
    assert result["total_cost_usd"] == "0"


def test_prepare_cli_default_never_enters_live_runtime(project, monkeypatch, capsys):
    import importlib.util

    from headroom.acceptance import diagnosis

    script = Path(__file__).resolve().parents[1] / "scripts/check_diagnosis_acceptance.py"
    spec = importlib.util.spec_from_file_location("diagnosis_acceptance_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    root, captures = project
    mapping = root / "captures.json"
    write(mapping, {key: str(value) for key, value in captures.items()})
    monkeypatch.setattr(
        cli,
        "prepare_diagnosis_acceptance",
        lambda captures, output, **kw: prepare_diagnosis_acceptance(
            captures, output, project_root=root, **kw
        ),
    )
    monkeypatch.setattr(
        diagnosis, "acceptance_run", lambda **kw: pytest.fail("Preparation must not open runtime")
    )
    assert cli.main(["--captures", str(mapping), "--output", str(root / "cli-prepared")]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "prepare" and output["accepted"] is False
    assert output["ready_count"] == 8


def test_required_savings_are_fixed_from_original_reclaim_target_without_supplements(project):
    prepared, path = prepare(project)
    assert prepared["rows"][0]["required_saving_gb"] is None
    assert prepared["rows"][1]["required_saving_gb"] == pytest.approx(512 / 1e9 * 0.3)
    assert prepared["rows"][1]["reclaim_reduction_pct"] == 30
    result, calls = execute(project, prepared, path, mode="supplement")
    assert len(calls) == 8
    assert result["rows"][1]["requires_supplement"] is True
    assert result["rows"][1]["complete_diagnosis"] is False
    assert all(row["supplement_executed"] is False for row in result["rows"])
    assert not result["fixture_gates_passed"]


def test_later_case_changed_during_batch_is_refused_before_its_request(project):
    prepared, path = prepare(project)
    price, env = profile(project[0])
    transport, calls = transport_for(prepared)
    original_handler = transport.handler

    def mutate_after_first(request):
        response = original_handler(request)
        next_md = path.parent / "cases" / SCENARIO_IDS[1] / "evidence/evidence.md"
        next_md.write_text(next_md.read_text() + "\nchanged after initial validation")
        return response

    result = execute_diagnosis_acceptance(
        path,
        profile_path=price,
        env_file=env,
        transport=httpx.MockTransport(mutate_after_first),
        execute=True,
        live_authorized=True,
    )
    assert len(calls) == 1
    assert result["stop_reason"] == "PREPARED_EVIDENCE_CHANGED"
    assert result["rows"][1]["status"] == "failed"
    assert all(row["status"] == "not_executed" for row in result["rows"][2:])


def test_execute_api_has_no_implicit_admission_caps(tmp_path):
    with pytest.raises(TypeError, match="run_limit_usd"):
        _execute_diagnosis_acceptance(
            tmp_path / "preparation.json",
            profile_path=tmp_path / "profile.json",
            execute=True,
            live_authorized=True,
        )


def test_failure_to_persist_final_runtime_receipt_does_not_claim_zero_charge(project, monkeypatch):
    from headroom.acceptance import common

    prepared, path = prepare(project)
    original = common.write_json

    def fail_final(path, value):
        if Path(path).name == "runtime.json" and value.get("usage") is not None:
            raise OSError("fixture final receipt failure")
        return original(path, value)

    monkeypatch.setattr(common, "write_json", fail_final)
    result, calls = execute(project, prepared, path)
    assert len(calls) == 1
    assert result["total_cost_usd"] is None
    assert result["stop_reason"] == "ACCOUNTING_UNAVAILABLE"
    assert not result["accepted"]


def test_raw_valid_model_verdict_is_retained_before_scoring(project):
    prepared, path = prepare(project)
    result, _ = execute(project, prepared, path, mode="bad_reference")
    raw = json.loads(
        (path.parent / "execution" / SCENARIO_IDS[0] / "model-response.json").read_text()
    )
    assert "stk_invented" in raw["text"]
    assert raw["parsed"]["root_causes"][0]["evidence_refs"] == ["stk_invented"]
    assert result["rows"][0]["references_valid"] is False


def test_total_cost_preserves_high_precision_decimal_usage(project):
    from decimal import Decimal, localcontext

    prepared, path = prepare(project)
    price, env = profile(project[0])
    data = json.loads(price.read_text())
    input_price = "0.123456789123456789123456789123456789"
    output_price = "0.234567891234567891234567891234567891"
    data["models"]["ultra"]["input_usd_per_million"] = input_price
    data["models"]["ultra"]["output_usd_per_million"] = output_price
    write(price, data)
    transport, calls = transport_for(prepared)
    result = execute_diagnosis_acceptance(
        path,
        profile_path=price,
        env_file=env,
        transport=transport,
        execute=True,
        live_authorized=True,
    )
    with localcontext() as context:
        context.prec = 256
        expected = (200 * Decimal(input_price) + 120 * Decimal(output_price)) * 8 / 1000000
    assert len(calls) == 8 and Decimal(result["total_cost_usd"]) == expected


@pytest.mark.parametrize("inside", ["capture", "source"])
def test_prepare_output_cannot_modify_original_capture_or_canonical_source(project, inside):
    root, captures = project
    original = (
        captures[SCENARIO_IDS[0]] if inside == "capture" else root / "scenarios" / SCENARIO_IDS[0]
    )
    output = original / "new-preparation"
    with pytest.raises(DiagnosisAcceptanceRefused, match="OUTPUT_MUST_NOT_MODIFY"):
        prepare_diagnosis_acceptance(captures, output, project_root=root)
    assert not output.exists()
