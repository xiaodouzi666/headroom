"""Temporary allocation + normal snapshot runtime; SDK transport is always mocked."""

import hashlib
import json
import pickle
import shutil
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414
from test_snapshot_diagnosis import diagnosis, native_snapshot

import headroom.snapshot_diagnosis as core
from headroom.acceptance import allocation
from headroom.acceptance import feature_allocation as feature
from headroom.acceptance.snapshot_binding import (
    SnapshotWebAllocation,
    load_snapshot_feature_binding,
    snapshot_budget_factory,
    snapshot_cleanup_verified,
    snapshot_feature_context,
    snapshot_intent,
)
from headroom.budget import BudgetLedger
from headroom.runtime import read_live_profile


@pytest.fixture
def pool(tmp_path):
    def create(*, with_source=False):
        root = tmp_path / "project"
        root.mkdir()
        old = BudgetLedger(root / ".cache/budget.db", total_limit="5", daily_limit="5")
        old.open_run("offline-old", "0.1")
        old.close_run("offline-old")
        profile_path, env = profile(root)
        profile_doc = json.loads(profile_path.read_text())
        snapshot = root / "capture.pickle"
        snapshot.write_bytes(pickle.dumps(native_snapshot(), protocol=pickle.HIGHEST_PROTOCOL))
        source = None
        if with_source:
            source = root / "source.py"
            source.write_text("raise AssertionError('uploaded source must not run')\n")
        bound_profile = root / ".cache/final48-allocation/runtime-profile.json"
        request = core.SnapshotDiagnosisRequest(
            snapshot=snapshot, source=source, runtime_profile=bound_profile
        )
        intent = snapshot_intent(request, daily_budget_usd="5")
        intents = {
            slot: feature.intent_sha256(intent)
            for slot in ("snapshot-s2", "snapshot-nanogpt", "snapshot-web")
        }
        intents["watch-s1"] = feature.intent_sha256(
            {**intent, "kind": "watch", "payload": {"fixture": "not-executed"}}
        )
        plan = allocation.prepare_allocation_plan()
        plan["amounts"] = {
            "approved_net_usd": "5",
            "available_gift_usd": "5",
            "review_reserve_usd": "0",
            "tax_reserve_usd": "0",
            "daily_limit_usd": "5",
        }
        plan["balance_evidence_sha256"] = "1" * 64
        plan["task_run_caps_usd"].update(F1="1.5", F3b_snapshot="0.30", F3b_watch="0.30")
        plan["task_pins"]["F1"] = {
            "preparation_sha256": "2" * 64,
            "scoring_policy_sha256": "3" * 64,
        }
        plan["feature_scope_caps_usd"]["F3b"] = "1"
        plan["task_pins"]["F3b"] = {
            "preparation_sha256": "4" * 64,
            "slot_intents_sha256": allocation.digest(intents),
        }
        authorization = {
            "state": "authorized",
            "scope": "FINAL48",
            "approved_net_usd": "5",
            "approval_message_ref": "offline-test-only-not-user-approval",
            "statement_sha256": "5" * 64,
        }
        allocation.activate_allocation(plan, authorization, profile_doc, project_root=root)
        parent = feature.claim_feature_parent(
            root / ".cache/final48-allocation/receipt.json",
            project_root=root,
            scope="F3b",
            preparation_sha256="4" * 64,
            slot_intents=intents,
        )
        return root, request, parent, env

    return create


def claim(pool, *, source=False, slot="snapshot-s2"):
    root, request, parent, env = pool(with_source=source)
    run_id = "a" * 32
    child = feature.claim_feature_child(
        parent, slot_id=slot, intent=snapshot_intent(request, daily_budget_usd="5"), run_id=run_id
    )
    return root, request, parent, env, child


def snapshot_provider_intent(body, evidence):
    """Synthetic provider reply conforms to the actual request, never legacy quantities."""
    prefix = "Return only valid JSON matching this schema, without markdown or commentary.\n"
    messages = [
        m["content"]
        for m in body["messages"]
        if isinstance(m.get("content"), str) and m["content"].startswith(prefix)
    ]
    assert len(messages) == 1
    schema = json.loads(messages[0][len(prefix) :])
    assert schema["title"] == "SnapshotDiagnosisIntent"
    cause = schema["$defs"]["RootCause"]
    assert "bytes_gb" not in cause["properties"] and "bytes_gb" not in cause["required"]
    assert cause["additionalProperties"] is False
    native = body.get("response_format", {}).get("json_schema")
    if native is not None:
        assert native["schema"] == schema
    visible = set(evidence["presentation"]["peak_stack_ids"])
    peak_rows = {row["stack_id"]: row["bytes"] for row in evidence["analysis"]["peak_composition"]}
    refs = cause["properties"]["evidence_refs"]["items"]["enum"]
    assert refs and all(ref in visible and ref in peak_rows for ref in refs)
    reply = diagnosis(refs[0])
    for item in reply["root_causes"]:
        item.pop("bytes_gb")
    Draft202012Validator(schema).validate(reply)
    return reply


def assert_intent_provenance(job):
    """The saved provider intent is the private source; quantities come from evidence."""
    private = job / "private"
    source = json.loads((private / "snapshot-intent.json").read_text())
    assert source["protocol"] == "headroom.snapshot-intent.v1"
    intent = source["intent"]
    assert all("bytes_gb" not in cause for cause in intent["root_causes"])
    record = json.loads((private / "snapshot-quantity-provenance.json").read_text())
    raw_intent = json.dumps(
        intent, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    assert record["intent_sha256"] == hashlib.sha256(raw_intent).hexdigest()
    assert (
        record["evidence_json_sha256"]
        == hashlib.sha256((job / "evidence.json").read_bytes()).hexdigest()
    )
    assert record["derivations"][0]["cited_peak_bytes"] == 512
    assert record["derivations"][0]["decimal_GB"] == "0.000000512"
    assert record["causal_contribution_verified"] is False
    assert record["hardware_verification"] == "not_run"
    output = json.loads((job / "diagnosis.json").read_text())
    assert output["diagnosis"]["root_causes"][0]["bytes_gb"] == 0.000000512
    return record


def sdk_runtime(monkeypatch, root, env, *, on_wire=None):
    calls = []
    real = core.build_live_runtime

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        if on_wire:
            on_wire(body)
        evidence = json.loads((root / "runs/uploads" / ("a" * 32) / "evidence.json").read_text())
        intent = snapshot_provider_intent(body, evidence)
        return httpx.Response(
            200,
            json={
                "id": "offline-sdk-fixture",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(intent)},
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            },
        )

    def build(*args, **kwargs):
        return real(*args, **kwargs, env_file=env, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(core, "build_live_runtime", build)
    return calls


def test_normal_live_runtime_uses_bound_ledger_and_closes_actual_sdk_usage(pool, monkeypatch):
    root, request, parent, env, child = claim(pool)
    calls = sdk_runtime(monkeypatch, root, env)
    with snapshot_feature_context(child, project_root=root):
        result = core.run_snapshot_diagnosis(
            request, run_root=root / "runs/uploads", run_id=child["run_id"]
        )
    assert result["status"] == "completed" and len(calls) == 1
    assert_intent_provenance(root / "runs/uploads" / child["run_id"])
    # This checks the normal runtime branch; the test transport/cost are synthetic.
    assert result["provenance"] == "live_model"
    assert result["cost_usd"] == 0.0004
    settled = feature.finish_feature_child(child, execution_terminal=True, cleanup_verified=True)
    assert settled["status"] == "settled" and settled["actual_usd"] == "0.0004"
    assert feature.feature_accounting(parent)["scope_spent_usd"] == "0.0004"
    assert result["verification"]["status"] == "not_run"
    assert snapshot_cleanup_verified(root / "runs/uploads", child["run_id"]) is True


def test_web_copy_has_same_content_intent_and_unapproved_input_cannot_claim(pool):
    root, request, parent, _ = pool(with_source=True)
    web = SnapshotWebAllocation(parent, project_root=root)
    target = root / "runs/uploads" / ("b" * 32)
    target.mkdir(parents=True)
    shutil.copyfile(request.snapshot, target / "snapshot.pickle")
    shutil.copyfile(request.source, target / "source.py")
    moved = request.model_copy(
        update={"snapshot": target / "snapshot.pickle", "source": target / "source.py"}
    )
    assert snapshot_intent(moved, daily_budget_usd="5") == snapshot_intent(
        request, daily_budget_usd="5"
    )
    (target / "source.py").write_text("changed\n")
    with pytest.raises(allocation.AllocationRefused, match="FEATURE_CHILD_INTENT_CHANGED"):
        web.claim(moved, "b" * 32)
    assert feature.feature_accounting(parent)["children"] == []
    shutil.copyfile(request.source, target / "source.py")
    child = web.claim(moved, "b" * 32)
    assert child["slot_id"] == "snapshot-web"
    feature.finish_feature_child(child, execution_terminal=True, cleanup_verified=True)
    with pytest.raises(allocation.AllocationRefused, match="FEATURE_CHILD_ALREADY_CLAIMED"):
        web.claim(moved, "c" * 32)


@pytest.mark.parametrize("field", ["snapshot", "source"])
def test_upload_replacement_is_rechecked_before_each_reservation(pool, field):
    root, request, _, _, child = claim(pool, source=True)
    ledger = snapshot_budget_factory(child, project_root=root)(
        child["run_id"], request, read_live_profile(request.runtime_profile)
    )
    ledger.open_run(child["run_id"], "0.30")
    ledger.reserve(child["run_id"], "first-offline", "0.01")
    ledger.settle(child["run_id"], "first-offline", "0.001")
    path = getattr(request, field)
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(allocation.AllocationRefused, match="FEATURE_CHILD_INTENT_CHANGED"):
        ledger.reserve(child["run_id"], "must-not-dispatch", "0.01")
    ledger.close_run(child["run_id"])
    settled = feature.finish_feature_child(child, execution_terminal=True, cleanup_verified=True)
    assert settled["actual_usd"] == "0.001"


def test_context_rejects_offline_runtime_substitution_before_any_job(pool):
    root, request, _, _, child = claim(pool)
    with (
        snapshot_feature_context(child, project_root=root),
        pytest.raises(ValueError, match="offline runtime"),
    ):
        core.run_snapshot_diagnosis(
            request,
            run_root=root / "runs/uploads",
            run_id=child["run_id"],
            services=core.SnapshotServices(runtime_factory=lambda *a: None),
        )
    assert not (root / "runs/uploads").exists()


def test_bound_input_symlink_is_rejected(pool):
    root, request, _, _ = pool()
    alias = root / "alias.pickle"
    alias.symlink_to(request.snapshot)
    with pytest.raises(ValueError, match="symlinks"):
        snapshot_intent(request.model_copy(update={"snapshot": alias}), daily_budget_usd="5")


def bound_sdk_worker(request, *, run_root, run_id):
    """Spawn-safe test worker: normal runtime, mock SDK transport, fake credential only."""
    root = Path(run_root).parent.parent
    original = core.build_live_runtime

    def respond(http_request):
        body = json.loads(http_request.content)
        evidence = json.loads((Path(run_root) / run_id / "evidence.json").read_text())
        intent = snapshot_provider_intent(body, evidence)
        return httpx.Response(
            200,
            json={
                "id": "offline-web-sdk",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(intent)},
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            },
        )

    def build(*args, **kwargs):
        return original(
            *args,
            **kwargs,
            env_file=root / "credential.fixture",
            transport=httpx.MockTransport(respond),
        )

    core.build_live_runtime = build
    try:
        return core.run_snapshot_diagnosis(
            core.SnapshotDiagnosisRequest(**vars(request)), run_root=run_root, run_id=run_id
        )
    finally:
        core.build_live_runtime = original


def test_private_web_slot_runs_normal_worker_and_remains_owner_scoped(pool):
    import test_snapshot_routes as existing
    from fastapi.testclient import TestClient
    from test_snapshot_integration import OfflineAvailability, ordinary_worker

    from headroom.api.app import COOKIE, ApiSettings, create_app

    root, request, parent, _ = pool()
    (root / "scenarios").mkdir()
    (root / "scenarios/INDEX.yaml").write_text('{"scenarios":[]}')
    config = ApiSettings(
        project_root=root,
        runtime_profile=str(request.runtime_profile),
        snapshot_submissions_enabled=True,
        run_submissions_enabled=True,
        verified_runs_enabled=False,
        deadline_seconds=20,
        event_poll_seconds=0.01,
    )
    app = create_app(
        config,
        worker=ordinary_worker,
        availability_monitor=OfflineAvailability(),
        snapshot_worker=bound_sdk_worker,
        snapshot_allocation_parent=parent,
    )
    files = {
        "snapshot": ("ignored.pickle", request.snapshot.read_bytes(), "application/octet-stream")
    }
    with TestClient(app) as owner:
        # Even a matching upload cannot select receipt, slot or an allowance through HTTP.
        rejected = owner.post(
            "/api/snapshots",
            files={**files, "receipt": ("receipt.json", b"{}", "application/json")},
        )
        assert rejected.status_code == 400
        accepted = owner.post("/api/snapshots", files=files)
        assert accepted.status_code == 202
        identifier = accepted.json()["run_id"]
        result = existing.wait_status(owner, identifier)
        assert result["status"] == "completed", result
        assert_intent_provenance(root / "runs/uploads" / identifier)
        assert result["result"]["provenance"] == "live_model"
        assert result["result"]["cost_usd"] == 0.0004
        assert result["result"]["verification"]["status"] == "not_run"
        own = owner.get(f"/api/snapshots/{identifier}/download/diagnosis_json")
        assert own.status_code == 200
        foreign = owner.get(
            f"/api/snapshots/{identifier}", headers={"cookie": COOKIE + "=" + "c" * 32}
        )
        assert foreign.status_code == 404
        foreign_download = owner.get(
            f"/api/snapshots/{identifier}/download/diagnosis_json",
            headers={"cookie": COOKIE + "=" + "c" * 32},
        )
        assert foreign_download.status_code == 404
    account = feature.feature_accounting(parent)
    assert account["scope_spent_usd"] == "0.0004"
    assert len(account["children"]) == 1 and account["children"][0]["slot_id"] == "snapshot-web"
    assert account["children"][0]["state"] == "settled"


def test_private_cli_binding_requires_permissions_and_actual_input_match(pool):
    root, request, _, _, child = claim(pool)
    path = root / "private-binding.json"
    path.write_text(json.dumps(child))
    path.chmod(0o600)
    assert load_snapshot_feature_binding(path, request=request, project_root=root) == child
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        load_snapshot_feature_binding(path, request=request, project_root=root)
    path.chmod(0o600)
    request.snapshot.write_bytes(request.snapshot.read_bytes() + b" ")
    with pytest.raises(allocation.AllocationRefused, match="FEATURE_CHILD_INTENT_CHANGED"):
        load_snapshot_feature_binding(path, request=request, project_root=root)
    assert snapshot_cleanup_verified(root / "runs/uploads", child["run_id"]) is False


def test_cli_private_context_uses_normal_runtime_and_settles_real_mock_transport(pool, monkeypatch):
    from typer.testing import CliRunner

    from headroom.cli import app as cli_app
    from headroom.lab import runner

    root, request, _, env, child = claim(pool)
    path = root / "cli-binding.json"
    path.write_text(json.dumps(child))
    path.chmod(0o600)
    monkeypatch.setattr(runner, "PROJECT_ROOT", root)
    monkeypatch.setenv("HEADROOM_SNAPSHOT_FEATURE_BINDING", str(path))
    calls = sdk_runtime(monkeypatch, root, env)
    outcome = CliRunner().invoke(
        cli_app,
        [
            "diagnose",
            "--snapshot",
            str(request.snapshot),
            "--runtime-profile",
            str(request.runtime_profile),
            "--budget",
            "0.30",
            "--run-root",
            str(root / "runs/uploads"),
        ],
    )
    assert outcome.exit_code == 0, outcome.output
    summary = json.loads(outcome.stdout)
    assert summary["run_id"] == child["run_id"] and summary["provenance"] == "live_model"
    assert summary["status"] == "completed" and len(calls) == 1
    assert_intent_provenance(root / "runs/uploads" / child["run_id"])
    clean = snapshot_cleanup_verified(root / "runs/uploads", child["run_id"])
    assert clean is True
    settled = feature.finish_feature_child(child, execution_terminal=True, cleanup_verified=clean)
    assert settled["status"] == "settled" and settled["actual_usd"] == "0.0004"
