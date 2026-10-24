"""Real SDK/router/shared-ledger acceptance path under independent network/secret guards."""

import builtins
import hashlib
import io
import json
import os
import shutil
import socket
from pathlib import Path

import httpx
import pytest

from headroom.acceptance.client import (
    execute_client_acceptance,
    prepare_client_acceptance,
)
from headroom.acceptance.common import acceptance_run, file_record, read_bytes, read_json
from headroom.acceptance.long_evidence import (
    MIN_EVIDENCE_TOKENS,
    canonical,
    prepare_long_evidence,
)
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.config import SUPER_MODEL, ULTRA_MODEL, candidate_models
from headroom.runtime import PROJECT_ROOT


@pytest.fixture(autouse=True)
def independent_guards(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("External network is forbidden in acceptance tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    real_path = PROJECT_ROOT / ".env"
    monkeypatch.delenv("HEADROOM_RUN_BUDGET_USD", raising=False)
    monkeypatch.delenv("HEADROOM_DAILY_BUDGET_USD", raising=False)

    def guard(original):
        def guarded(file, *args, **kwargs):
            if (
                isinstance(file, (str, bytes, os.PathLike))
                and Path(os.fsdecode(file)).absolute() == real_path
            ):
                pytest.fail("Real project .env read is forbidden")
            return original(file, *args, **kwargs)

        return guarded

    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    monkeypatch.setattr(os, "open", guard(os.open))


def runtime_fixture(root, *, prompt_ceiling=300000, authorized="2", enabled=True, super_model=None):
    root.mkdir(parents=True, exist_ok=True)
    env = root / "fixture-key.txt"
    env.write_text("NEBIUS_API_KEY=offline-placeholder\n")
    env.chmod(0o600)
    profile = {
        "live_enabled": enabled,
        "credit_confirmed": True,
        "available_credit_usd": "2",
        "authorized_total_usd": authorized,
        "verified_at": "offline-fixture",
        "evidence": "offline-fixture",
        "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
        "evidence_token_budget": 1000,
        "models": {
            role: {
                "model_id": model.model_id,
                "input_usd_per_million": "1",
                "output_usd_per_million": "2",
                "evidence": "offline fixture, never provider pricing",
                "billing": {
                    "prompt_token_ceiling": prompt_ceiling,
                    "max_prompt_utf8_bytes": 16000000,
                    "max_completion_tokens": 512,
                    "output_cap_field": "max_tokens",
                    "output_cap_includes_reasoning": True,
                    "verified": True,
                    "evidence": "offline fixture, never provider bound",
                },
            }
            for role, model in candidate_models().items()
        },
    }
    if super_model is not None:
        profile["models"]["super"]["model_id"] = super_model
    path = root / "fixture-profile.json"
    path.write_text(json.dumps(profile))
    return path, env


def response(model, text, prompt_tokens=100, *, usage=True):
    payload = {
        "id": "fixture",
        "created": 0,
        "object": "chat.completion",
        "model": model,
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
        ],
    }
    if usage:
        payload["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 20,
            "total_tokens": prompt_tokens + 20,
        }
    return httpx.Response(200, json=payload)


def execute(package, root, handler, case="super_schema", **options):
    profile, env = runtime_fixture(root, **options.pop("profile_options", {}))
    return execute_client_acceptance(
        package / "prepared.json",
        case=case,
        profile_path=profile,
        run_limit_usd=options.pop("run_limit_usd", "0.5"),
        daily_limit_usd="2",
        execute=True,
        live_authorized=True,
        project_root=root,
        env_file=env,
        transport=httpx.MockTransport(handler),
        **options,
    )


def capture_fixture(root, records=4000):
    (root / "source").mkdir(parents=True)
    (root / "artifacts").mkdir()
    source = "value = 1\n"
    (root / "source/train.py").write_text(source)
    result = {
        "run_id": "fixture",
        "status": "oom",
        "capture_complete": True,
        "cleanup_verified": True,
        "env": {"device": "cuda", "torch": "2.5.1"},
        "step_records": [],
        "peak_allocated_bytes": 512,
        "peak_reserved_bytes": 2048,
        "oom_requested_bytes": 4096,
    }
    manifest = {
        "device": "cuda",
        "command": ["python", "-m", "headroom.lab.run_target", "--script", "/source/train.py"],
        "source": {"files": {"train.py": {"sha256": hashlib.sha256(source.encode()).hexdigest()}}},
    }
    events = [{"action": "segment_alloc", "addr": 0, "size": 2048}]
    for index in range(records):
        events.extend(
            [
                {
                    "action": "alloc",
                    "addr": 0,
                    "size": 512,
                    "time_us": index * 3,
                    "frames": [
                        {"filename": "/source/train.py", "line": 1, "name": "forward"},
                        {
                            "filename": "/opt/venv/torch/nn/functional.py",
                            "line": 100,
                            "name": "linear",
                        },
                    ],
                },
                {"action": "free_requested", "addr": 0, "time_us": index * 3 + 1},
                {"action": "free_completed", "addr": 0, "time_us": index * 3 + 2},
            ]
        )
    events.append({"action": "oom", "size": 4096, "device_free": 0})
    snapshot = {
        "device_traces": [events],
        "segments": [
            {
                "device": 0,
                "address": 0,
                "total_size": 2048,
                "blocks": [{"address": 0, "size": 2048, "state": "inactive", "frames": []}],
            }
        ],
    }
    for name, data in (
        ("result.json", result),
        ("manifest.json", manifest),
        ("artifacts/result.json", result),
        ("artifacts/snapshot.json", snapshot),
    ):
        (root / name).write_text(json.dumps(data))
    return root


@pytest.fixture(scope="module")
def long_package(tmp_path_factory):
    root = tmp_path_factory.mktemp("long-client")
    capture = capture_fixture(root / "capture")
    result = prepare_client_acceptance(root / "prepared", capture=capture)
    assert result["cases"]["ultra_200k"]["status"] == "ready"
    return root / "prepared"


def test_prepare_without_capture_reads_no_profile_or_key(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation constructed a runtime")

    monkeypatch.setattr("headroom.acceptance.common.read_live_profile", forbidden)
    monkeypatch.setattr("headroom.acceptance.common.BudgetLedger", forbidden)
    result = prepare_client_acceptance(tmp_path / "prepared")
    assert result["cases"]["super_schema"]["status"] == "ready"
    assert result["cases"]["ultra_200k"]["reason"] == "CAPTURE_REQUIRED"
    assert not result["accepted"] and not result["live_executed"]


def test_super_strict_schema_real_router_and_shared_ledger(tmp_path):
    package = tmp_path / "prepared"
    prepared = prepare_client_acceptance(package)
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == SUPER_MODEL and body["max_tokens"] == 512
        assert "additionalProperties" in body["messages"][0]["content"]
        return response(
            SUPER_MODEL,
            json.dumps({"probe_id": prepared["probe_id"], "status": "ok", "observed": [2, 3, 5]}),
        )

    result = execute(package, tmp_path / "runtime", handler)
    assert result["checks_passed"] and not result["accepted"]
    assert result["provenance"] == "offline_fixture"
    assert len(requests) == len(result["runtime"]["calls"]) == 1
    assert result["runtime"]["usage"]["total_cost_usd"] == "0.00014"
    assert result["runtime"]["budget"]["status"] == "closed"
    assert (tmp_path / "runtime/runs/acceptance/headroom.db").exists()
    assert not (tmp_path / "runtime/runs/headroom.db").exists()
    assert (tmp_path / "runtime/.cache/budget.db").exists()
    with pytest.raises(FileExistsError):
        execute(package, tmp_path / "runtime", handler)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "text",
    [
        '{"status":"ok","observed":[2,3,5]}',
        '{"probe_id":"wrong","status":"ok","observed":[2,3,5]}',
        '{"probe_id":"wrong","status":"ok","observed":["2",3,5]}',
    ],
)
def test_invalid_schema_or_case_values_never_pass_and_charge_remains(tmp_path, text):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    result = execute(package, tmp_path / "runtime", lambda _: response(SUPER_MODEL, text))
    assert not result["checks_passed"] and not result["accepted"]
    assert result["runtime"]["usage"]["total_cost_usd"] == "0.00014"
    assert len(result["runtime"]["calls"]) == 1


@pytest.mark.parametrize("kind", ["429", "missing_usage", "wrong_model"])
def test_unknown_or_invalid_identity_halts_across_new_case_and_restart(tmp_path, kind):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    requests = []

    def handler(request):
        requests.append(request)
        if kind == "429":
            return httpx.Response(429, json={"error": {"message": "fixture"}})
        return response(
            "nvidia/wrong" if kind == "wrong_model" else SUPER_MODEL,
            "{}",
            usage=kind != "missing_usage",
        )

    root = tmp_path / "runtime"
    result = execute(package, root, handler)
    assert not result["accepted"] and len(requests) == 1
    assert result["runtime"]["usage"]["total_cost_usd"] is None
    assert result["runtime"]["budget"]["dispatch_blocked"]
    ledger = BudgetLedger(root / ".cache/budget.db", daily_limit="2", total_limit="2")
    with pytest.raises(BudgetExceeded):
        ledger.open_run("unrelated-after-restart", "0.1")
    next_package = tmp_path / "next"
    prepare_client_acceptance(next_package)
    blocked = execute(next_package, root, handler)
    assert blocked["status"] == "blocked_or_failed" and len(requests) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"run_limit_usd": "0.01"},
        {"profile_options": {"authorized": "0.1"}},
        {"profile_options": {"enabled": False}},
    ],
)
def test_original_admission_authorization_and_enablement_gates(tmp_path, options):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    requests = []
    result = execute(package, tmp_path / "runtime", lambda r: requests.append(r), **options)
    assert not requests and not result["accepted"]
    assert result["status"] == "blocked_or_failed"


def test_explicit_authorization_precedes_any_profile_read(tmp_path):
    with pytest.raises(ValueError, match="Explicit"):
        execute_client_acceptance(
            tmp_path / "missing",
            case="super_schema",
            profile_path=PROJECT_ROOT / ".env",
            run_limit_usd="1",
            daily_limit_usd="1",
            execute=True,
        )
    with (
        pytest.raises(ValueError, match="explicit"),
        acceptance_run(
            case_id="fixture",
            artifact_dir=tmp_path / "unused",
            profile_path=PROJECT_ROOT / ".env",
            run_limit_usd="1",
            daily_limit_usd="1",
        ),
    ):
        pytest.fail("unauthorized context entered")


def test_unique_real_record_locations_and_counts(long_package):
    document = read_json(long_package / "prepared.json")["cases"]["ultra_200k"]
    rows = read_json(long_package / "ultra_200k/records.json")
    assert document["evidence_content_tokens_local_estimate"] >= MIN_EVIDENCE_TOKENS
    assert document["provider_prompt_tokens"] is None and document["provider_token_bound"] is None
    assert (
        len(rows) == len({row["pointer"] for row in rows}) == len({row["sha256"] for row in rows})
    )
    snapshot = read_json(
        Path(document["capture_root"]) / document["selected_snapshot"], 16 * 1024 * 1024
    )
    for row in rows[::137]:
        value = snapshot
        for part in row["pointer"].strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert hashlib.sha256(canonical(value).encode()).hexdigest() == row["sha256"]


@pytest.mark.parametrize("provider_tokens,passed", [(200000, True), (199999, False)])
def test_ultra_uses_actual_provider_tokens_not_local_estimate(
    tmp_path, long_package, provider_tokens, passed
):
    package = tmp_path / "prepared"
    shutil.copytree(long_package, package)
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == ULTRA_MODEL and "response_format" not in body
        assert "/device_traces/0/" in body["messages"][1]["content"]
        return response(
            ULTRA_MODEL,
            "Allocator source /device_traces/0/1 records the allocation.",
            provider_tokens,
        )

    result = execute(package, tmp_path / "runtime", handler, case="ultra_200k")
    assert result["checks_passed"] is passed and result["accepted"] is False
    assert len(requests) == 1
    assert result["response"]["usage"]["prompt_tokens"] == provider_tokens
    assert result["runtime"]["usage"]["total_cost_usd"] is not None


def test_insufficient_evidence_stays_pending_and_no_profile_read(tmp_path):
    capture = capture_fixture(tmp_path / "capture", records=1)
    package = tmp_path / "prepared"
    prepared = prepare_client_acceptance(package, capture=capture)
    assert prepared["cases"]["ultra_200k"]["status"] == "pending"
    with pytest.raises(ValueError, match="pending"):
        execute_client_acceptance(
            package / "prepared.json",
            case="ultra_200k",
            profile_path=PROJECT_ROOT / ".env",
            run_limit_usd="1",
            daily_limit_usd="1",
            execute=True,
            live_authorized=True,
        )


def test_changed_payload_rejected_before_runtime(tmp_path):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    (package / "super_schema/messages.json").write_text("[]")
    with pytest.raises(ValueError, match="messages changed"):
        execute(package, tmp_path / "runtime", lambda _: pytest.fail("must not send"))
    assert not (tmp_path / "runtime/.cache/budget.db").exists()


def test_changed_source_rejected_before_runtime(tmp_path, long_package):
    package = tmp_path / "prepared"
    shutil.copytree(long_package, package)
    document = read_json(package / "prepared.json")
    capture = tmp_path / "capture-copy"
    shutil.copytree(document["cases"]["ultra_200k"]["capture_root"], capture)
    document["cases"]["ultra_200k"]["capture_root"] = str(capture)
    (package / "prepared.json").write_text(json.dumps(document))
    (package / "prepared.seal.json").write_text(
        json.dumps(file_record(package / "prepared.json", 1024 * 1024))
    )
    (capture / "source/train.py").write_text("changed = True\n")
    with pytest.raises(ValueError, match="capture changed"):
        execute(
            package, tmp_path / "runtime", lambda _: pytest.fail("must not send"), case="ultra_200k"
        )


def test_snapshot_bound_and_no_overwrite_of_old_capture(tmp_path):
    capture = capture_fixture(tmp_path / "capture", records=1)
    with pytest.raises(ValueError, match="must not modify"):
        prepare_long_evidence(capture, capture / "new")
    with pytest.raises(ValueError, match="bounded"):
        read_bytes(capture / "artifacts/snapshot.json", 2)


def test_common_rejects_mislabelled_live_and_production_fixture(tmp_path):
    common = {
        "case_id": "fixture",
        "artifact_dir": tmp_path / "unused",
        "profile_path": PROJECT_ROOT / ".env",
        "run_limit_usd": "1",
        "daily_limit_usd": "1",
        "execute": True,
        "live_authorized": True,
    }
    with (
        pytest.raises(ValueError, match="shared ledger"),
        acceptance_run(**common, project_root=tmp_path),
    ):
        pytest.fail("unexpected live")
    with (
        pytest.raises(ValueError, match="production ledger"),
        acceptance_run(**common, transport=httpx.MockTransport(lambda _: None)),
    ):
        pytest.fail("unexpected fixture")


def test_interruption_persists_charge_and_propagates(tmp_path):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)

    def interrupt(_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute(package, tmp_path / "runtime", interrupt)
    saved = read_json(package / "execution-super_schema/result.json")
    assert not saved["accepted"] and saved["error_type"] == "KeyboardInterrupt"
    assert saved["runtime"]["budget"]["dispatch_blocked"]
    assert saved["runtime"]["usage"]["total_cost_usd"] is None


@pytest.mark.parametrize("name", ["HEADROOM_RUN_BUDGET_USD", "HEADROOM_DAILY_BUDGET_USD"])
def test_deployment_budget_limits_can_only_lower_admission(tmp_path, monkeypatch, name):
    monkeypatch.setenv(name, "0.01")
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    requests = []
    result = execute(package, tmp_path / "runtime", lambda request: requests.append(request))
    assert not requests and not result["accepted"]
    field = "admission_run_limit_usd" if "RUN_" in name else "daily_limit_usd"
    assert result["runtime"][field] == "0.01"
    assert result["runtime"]["requested_admission_run_limit_usd"] == "0.5"


def test_bounded_read_rejects_growth_after_fstat(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "headroom.acceptance.common.open_regular", lambda *a, **k: io.BytesIO(b"123456")
    )
    with pytest.raises(ValueError, match="bounded read"):
        read_bytes(tmp_path / "fixture", 5)
    with pytest.raises(ValueError, match="bounded read"):
        file_record(tmp_path / "fixture", 5)


def test_actual_output_cap_violation_remains_halted(tmp_path):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)

    def handler(_):
        payload = json.loads(response(SUPER_MODEL, "{}").content)
        payload["usage"] = {"prompt_tokens": 100, "completion_tokens": 513, "total_tokens": 613}
        return httpx.Response(200, json=payload)

    result = execute(package, tmp_path / "runtime", handler)
    assert not result["accepted"] and result["runtime"]["budget"]["dispatch_blocked"]
    assert len(result["runtime"]["calls"]) == 1


def test_unrelated_metadata_and_duplicate_records_do_not_fill_long_input(tmp_path):
    capture = capture_fixture(tmp_path / "capture", records=1)
    path = capture / "artifacts/snapshot.json"
    snapshot = read_json(path)
    first = snapshot["device_traces"][0][1]
    snapshot["device_traces"][0].extend([first] * 1000)
    snapshot["external_annotations"] = ["irrelevant synthetic text"] * 50000
    snapshot["device_traces"][0].append({"not_an_allocator_record": "ignored"})
    path.write_text(json.dumps(snapshot))
    result = prepare_long_evidence(capture, tmp_path / "long")
    assert result["status"] == "pending" and result["duplicate_records_omitted"] == 1000
    assert "irrelevant synthetic text" not in (tmp_path / "long/evidence.txt").read_text()


def test_wrong_planned_role_model_is_rejected_before_dispatch(tmp_path):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    requests = []
    result = execute(
        package,
        tmp_path / "runtime",
        lambda r: requests.append(r),
        profile_options={"super_model": "nvidia/wrong-model"},
    )
    assert not requests and result["status"] == "blocked_or_failed"
    assert result["runtime"]["calls"] == []


def test_response_validation_uses_verified_probe_even_if_manifest_changes(tmp_path):
    package = tmp_path / "prepared"
    prepared = prepare_client_acceptance(package)

    def handler(_):
        changed = dict(prepared, probe_id="changed-during-call")
        (package / "prepared.json").write_text(json.dumps(changed))
        return response(
            SUPER_MODEL,
            json.dumps({"probe_id": prepared["probe_id"], "status": "ok", "observed": [2, 3, 5]}),
        )

    result = execute(package, tmp_path / "runtime", handler)
    assert result["checks_passed"] and not result["accepted"]


@pytest.mark.parametrize("committed", [False, True])
def test_pre_sdk_failure_distinguishes_cancelled_from_uncertain_dispatch(
    tmp_path, monkeypatch, committed
):
    package = tmp_path / "prepared"
    prepare_client_acceptance(package)
    original = BudgetLedger.mark_dispatched

    def interrupted(ledger, run_id, attempt_id):
        if committed:
            original(ledger, run_id, attempt_id)
        raise RuntimeError("fixture dispatch bookkeeping interruption")

    monkeypatch.setattr(BudgetLedger, "mark_dispatched", interrupted)
    requests = []
    result = execute(package, tmp_path / "runtime", lambda r: requests.append(r))
    assert not requests and not result["accepted"] and not result["live_executed"]
    assert result["dispatch"]["attempted_calls"] == 0
    assert result["dispatch"]["confirmed_not_dispatched"] == (0 if committed else 1)
    assert result["dispatch"]["dispatch_unresolved"] is committed
    if committed:
        assert result["runtime"]["budget"]["dispatch_blocked"]
    else:
        assert result["runtime"]["usage"]["total_cost_usd"] == "0"


def test_client_prepare_rejects_output_inside_original_capture_before_writing(tmp_path):
    capture = capture_fixture(tmp_path / "capture", records=1)
    output = capture / "should-not-exist"
    with pytest.raises(ValueError, match="must not modify"):
        prepare_client_acceptance(output, capture=capture)
    assert not output.exists()


def test_mismatched_raw_capture_is_not_ready_for_execution(tmp_path):
    capture = capture_fixture(tmp_path / "capture", records=1)
    raw_path = capture / "artifacts/result.json"
    raw = read_json(raw_path)
    raw["run_id"] = "different-capture"
    raw_path.write_text(json.dumps(raw))
    result = prepare_client_acceptance(tmp_path / "prepared", capture=capture)
    assert result["cases"]["ultra_200k"]["status"] == "pending"
