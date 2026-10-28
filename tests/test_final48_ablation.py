"""No-network F1 study tests; all captures/responses are explicitly offline fixtures."""

import builtins
import hashlib
import importlib.util
import io
import json
import os
import socket
from pathlib import Path

import httpx
import pytest
from test_diagnosis_acceptance import payload, profile, write

from headroom.acceptance import final48_ablation as f1
from headroom.config import SUPER_MODEL, ULTRA_MODEL

CATEGORIES = (
    "activations",
    "optimizer_state",
    "activations",
    "retained_graph",
    "fragmentation_candidate",
    "temporaries",
    "optimizer_state",
    "params",
    None,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real network and GPU/research execution forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module in (builtins, io, os):
        name = "open"
        original = getattr(module, name)

        def guard(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, Path)) and Path(path).name.startswith(".env"):
                raise AssertionError("Credential access forbidden")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(module, name, guard)
    import headroom.timeline_plot

    monkeypatch.setattr(
        headroom.timeline_plot,
        "render_timeline",
        lambda _, path, **kwargs: Path(path).write_bytes(b"offline fixture"),
    )


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    scenarios, rows, captures = [], [], {}
    for position, scenario in enumerate(f1.SCENARIOS):
        source = "SOURCE_CONTENT_CANARY = 1\nSOURCE_CONTENT_CANARY += 1\n"
        sha = hashlib.sha256(source.encode()).hexdigest()
        truth = root / (
            f"scenarios/{scenario}/README.md" if scenario != "nanogpt" else "repos/nanogpt.yaml"
        )
        truth.parent.mkdir(parents=True, exist_ok=True)
        truth.write_text("ANSWER_KEY_CANARY: " + str(CATEGORIES[position]))
        expected = "oom" if position in {0, 3, 5, 8} else "completed"
        case = {
            "id": scenario,
            "source_sha256": sha,
            "ground_truth": CATEGORIES[position],
            "truth_status": "unverified" if position in {4, 8} else "authored",
            "expected_baseline": expected,
        }
        scenarios.append(case)
        job = root / "runs/history" / scenario
        baseline_id = f"{position:032x}"
        capture = job / "lab" / baseline_id
        (capture / "source").mkdir(parents=True)
        (capture / "source/train.py").write_text(source)
        result = {
            "protocol": "headroom.lab.v1",
            "run_id": baseline_id,
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
        write(capture / "result.json", result | {"cleanup_verified": True, "run_dir": str(capture)})
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
        (capture / "artifacts/traceback.txt").write_text("CAPTURED_TRACEBACK: allocation failed")
        (capture / "artifacts/memory_summary.txt").write_text(
            "CAPTURED_SUMMARY: allocated 512 bytes"
        )
        write(
            job / "evidence/before/evidence.json",
            {"run_id": baseline_id, "annotation_delivery": {"private": "OLD_MODEL_ANSWER_CANARY"}},
        )
        captures[scenario] = capture
        rows.append({"scenario_id": scenario, "condition": "full_ultra", "run_dir": str(job)})
    write(root / "eval/mvp_phase1_v2.yaml", {"scenarios": scenarios})
    campaign = root / "runs/history/campaign.json"
    write(campaign, {"provenance": "offline_fixture", "rows": rows})
    return root, campaign, captures


def prepare(project):
    root, campaign, _ = project
    directory = root / "runs/prepared"
    result = f1.prepare_f1(campaign, directory, project_root=root)
    return result, directory / "preparation.json"


def transport_for(prepared, path, mode=None):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        index = len(calls)
        calls.append(body)
        if mode == "transient":
            return httpx.Response(429, json={"error": {"message": "offline fixture"}})
        row = prepared["rows"][index]
        request_payload = json.loads((path.parent / row["request_path"]).read_text())
        ref = next(iter(request_payload["evidence"]["analysis"]["stack_catalog"]))
        answer = payload(CATEGORIES[index // 3] or "unknown", ref)
        if mode == "invalid" and index == 0:
            answer["root_causes"][0]["evidence_refs"] = ["unseen_stack"]
        if mode == "extra_field" and index == 0:
            answer["extra_schema_field"] = "invalid contract but same category"
        if mode == "bad_category" and index == 0:
            answer["root_causes"][0]["category"] = "invented_category"
        content = json.dumps(answer)
        if mode == "duplicate_keys" and index == 0:
            content = content[:-1] + ', "root_causes": ' + json.dumps(answer["root_causes"]) + "}"
        if mode == "non_json" and index == 0:
            content = "Here is the diagnosis: " + content
        response = {
            "id": "fixture",
            "object": "chat.completion",
            "created": 1,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 200, "completion_tokens": 120, "total_tokens": 320},
        }
        if mode == "unknown":
            response.pop("usage")
        return httpx.Response(200, json=response)

    return httpx.MockTransport(handle), calls


def execute(project, prepared, path, mode=None, campaign_limit_usd="1.50"):
    root, _, _ = project
    profile_path, credentials = profile(root)
    profile_data = json.loads(profile_path.read_text())
    profile_data["models"]["super"]["capabilities"] = {
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline fixture",
    }
    profile_path.write_text(json.dumps(profile_data))
    transport, calls = transport_for(prepared, path, mode)
    result = f1.execute_f1(
        path,
        profile_path=profile_path,
        env_file=credentials,
        daily_limit_usd="5",
        execute=True,
        live_authorized=True,
        transport=transport,
        campaign_limit_usd=campaign_limit_usd,
    )
    return result, calls


def test_prepare_frozen_grid_without_runtime_credentials_or_previous_answers(project, monkeypatch):
    monkeypatch.setattr(
        f1, "acceptance_run", lambda **kwargs: pytest.fail("preparation opened runtime")
    )
    result, path = prepare(project)
    assert result["inputs_ready"], result["rows"]
    assert result["ready_requests"] == result["planned_requests"] == 27
    assert result["executed_requests"] == 0
    frozen = f1.verify_preparation(path)
    assert len(frozen["rows"]) == 27
    for index in range(0, 27, 3):
        full, restricted, small = frozen["rows"][index : index + 3]
        assert full["messages_sha256"] == small["messages_sha256"]
        assert (
            full["_payload"]["schema"]["$defs"]["RootCause"]["properties"]["category"]
            == restricted["_payload"]["schema"]["$defs"]["RootCause"]["properties"]["category"]
        )
        all_text = json.dumps(full["_payload"]["messages"])
        assert "SOURCE_CONTENT_CANARY" in all_text
        assert "ANSWER_KEY_CANARY" not in all_text and "OLD_MODEL_ANSWER_CANARY" not in all_text
        restricted_text = json.dumps(restricted["_payload"])
        assert "CAPTURED_TRACEBACK" in restricted_text and "CAPTURED_SUMMARY" in restricted_text
        assert "SOURCE_CONTENT_CANARY" not in restricted_text
    assert frozen["truths"][f1.SCENARIOS[4]]["category"] is None
    assert frozen["truths"]["nanogpt"]["category"] is None
    assert all((p.stat().st_mode & 0o077) == 0 for p in path.parent.rglob("*"))


def test_missing_captured_text_keeps_nine_case_grid_and_refuses(project):
    _, _, captures = project
    (captures["nanogpt"] / "artifacts/traceback.txt").unlink()
    result, path = prepare(project)
    assert not result["inputs_ready"] and result["ready_requests"] == 24
    assert len(result["rows"]) == 27
    assert all(row["status"] == "not_ready" for row in result["rows"][-3:])
    with pytest.raises(f1.F1Refused, match="INPUTS_NOT_READY"):
        f1.verify_preparation(path)


@pytest.mark.parametrize("mutation", ["source", "request", "preparation"])
def test_file_tampering_refused_before_any_runtime(project, monkeypatch, mutation):
    result, path = prepare(project)
    _, _, captures = project
    target = {
        "source": captures[f1.SCENARIOS[0]] / "source/train.py",
        "request": path.parent / result["rows"][0]["request_path"],
        "preparation": path,
    }[mutation]
    if mutation == "preparation":
        changed = json.loads(target.read_text())
        changed["request_policy"]["reasoning"] = True
        target.write_text(json.dumps(changed))
    else:
        target.write_text(target.read_text() + " ")
    monkeypatch.setattr(f1, "acceptance_run", lambda **kwargs: pytest.fail("runtime started"))
    with pytest.raises(f1.F1Refused):
        f1.verify_preparation(path)


def test_live_requires_both_flags_and_at_most_150_before_reading_inputs():
    with pytest.raises(f1.F1Refused, match="EXPLICIT_LIVE"):
        f1.execute_f1("/no-file", profile_path="/no-profile", daily_limit_usd="5")
    with pytest.raises(f1.F1Refused, match="INVALID_F1_BUDGET"):
        f1.execute_f1(
            "/no-file",
            profile_path="/no-profile",
            daily_limit_usd="5",
            campaign_limit_usd="1.51",
            execute=True,
            live_authorized=True,
        )


def test_real_audited_runtime_exactly_27_fixture_requests_no_retries_or_supplements(project):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path)
    assert len(calls) == 27, result
    assert result["completed_all_requests"] is True and result["provenance"] == "offline_fixture"
    assert [body["model"] for body in calls].count(ULTRA_MODEL) == 18
    assert [body["model"] for body in calls].count(SUPER_MODEL) == 9
    assert all(body["max_completion_tokens"] == 2000 for body in calls)
    assert all(body["chat_template_kwargs"] == {"enable_thinking": False} for body in calls)
    assert all(not body.get("tools") for body in calls)
    assert all(row["call_count"] == 1 for row in result["rows"])
    assert all(
        row["valid_correct_first_causes"] == 7 and row["denominator"] == 9
        for row in result["conditions"]
    )
    assert all(row["mean_provider_input_tokens"] == 200 for row in result["conditions"])
    assert result["total_cost_usd"] is not None and float(result["total_cost_usd"]) < 1.5
    assert result["within_budget"] is True and result["study_complete_within_budget"] is True
    assert all(row["usage"][0]["request_evidence"] for row in result["rows"])


@pytest.mark.parametrize("mode", ["transient", "unknown"])
def test_first_error_stops_without_hidden_retry_and_cost_unknown_preserved(project, mode):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, mode)
    assert len(calls) == 1, result
    assert not result["completed_all_requests"] and result["stop_reason"]
    assert all(row["status"] == "not_executed" for row in result["rows"][1:])
    assert result["total_cost_usd"] is None
    assert result["within_budget"] is None and result["study_complete_within_budget"] is False
    assert all(row["mean_provider_input_tokens"] is None for row in result["conditions"])


def test_invalid_model_reference_is_counted_once_not_repaired_or_supplemented(project):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, "invalid")
    assert len(calls) == 27, result
    assert result["rows"][0]["status"] == "invalid_response"
    assert result["rows"][0]["valid_correct_first_cause"] is False
    assert result["rows"][0]["first_cause_match"] is True
    assert result["rows"][0]["references_valid"] is False
    assert result["conditions"][0]["first_cause_matches"] == 7
    assert result["conditions"][0]["valid_correct_first_causes"] == 6


def test_cli_defaults_to_prepare_only(project, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "f1_cli", Path(__file__).parents[1] / "scripts/prepare_final48_ablation.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    called = []
    monkeypatch.setattr(
        cli,
        "prepare_f1",
        lambda *a, **k: (
            called.append((a, k))
            or {
                "mode": "prepare",
                "provenance": "offline_fixture",
                "inputs_ready": True,
                "ready_requests": 27,
                "planned_requests": 27,
                "executed_requests": 0,
                "request_policy": {},
                "preparation_sha256": "fixture",
            }
        ),
    )
    monkeypatch.setattr(cli, "execute_f1", lambda *a, **k: pytest.fail("default executed live"))
    assert cli.main(["--output", str(project[0] / "runs/private")]) == 0
    assert len(called) == 1


def test_budget_rejection_is_pre_dispatch_and_never_a_model_diagnosis(project):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, campaign_limit_usd="0.001")
    assert calls == []
    assert result["stop_reason"] == "BudgetExceeded"
    assert result["rows"][0]["status"] == "not_dispatched"
    assert result["rows"][0]["dispatched"] is False
    assert result["rows"][0]["valid_correct_first_cause"] is None
    assert all(c["attempted"] == 0 for c in result["conditions"])


def test_actual_usage_stopline_mode_refused_before_runtime(project, monkeypatch):
    _, path = prepare(project)
    profile_path, _ = profile(project[0])
    data = json.loads(profile_path.read_text())
    data["run_budget_mode"] = "actual_usage"
    profile_path.write_text(json.dumps(data))
    monkeypatch.setattr(f1, "acceptance_run", lambda **kwargs: pytest.fail("runtime opened"))
    with pytest.raises(f1.F1Refused, match="STRICT_RESERVATION_REQUIRED"):
        f1.execute_f1(
            path,
            profile_path=profile_path,
            daily_limit_usd="5",
            execute=True,
            live_authorized=True,
            transport=httpx.MockTransport(lambda _: None),
        )


@pytest.mark.parametrize(
    "mode,expected,reason",
    [
        ("extra_field", True, "strict_json_category"),
        ("duplicate_keys", None, "duplicate_json_keys"),
        ("non_json", None, "invalid_json"),
        ("bad_category", None, "missing_or_invalid_first_category"),
    ],
)
def test_primary_category_scoring_uses_same_unrepaired_response(project, mode, expected, reason):
    prepared, path = prepare(project)
    result, calls = execute(project, prepared, path, mode)
    assert len(calls) == 27
    assert result["rows"][0]["first_cause_match"] is expected
    assert result["rows"][0]["first_category_extraction"] == reason
    assert result["conditions"][0]["first_cause_matches"] == (7 if expected else 6)
    assert result["conditions"][0]["denominator"] == 9
    assert result["scoring_policy_sha256"] == prepared["scoring_policy_sha256"]
    if mode == "extra_field":
        assert result["rows"][0]["references_valid"] is True
        assert result["rows"][0]["diagnosis_valid"] is False


def test_overflow_float_in_original_json_cannot_count_as_category_hit():
    text = json.dumps(payload("activations", "traceback"))[:-1] + ', "extra_value": 1e999}'
    assert f1.strict_first_category(text, {}) == (None, "nonfinite_json", None)
