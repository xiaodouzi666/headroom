"""Real API/spawn/runtime wiring, with synthetic Lab and SDK transport only."""

import json
import shutil
import socket
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_demo_allocation import demo_pool as demo_pool  # noqa: PLC0414
from test_final48_ablation import offline as offline  # noqa: PLC0414
from test_public_launcher import launcher as launcher  # noqa: PLC0414

from headroom.acceptance.allocation import historical_snapshot
from headroom.acceptance.demo_binding import DemoAllocation
from headroom.api.app import ApiSettings, create_app
from headroom.runtime import read_live_profile


class NoObservation:
    def snapshot(self):
        return {"gpu": {}, "token_factory": {}, "local_budget": {}}

    def close(self):
        pass


def sdk_worker(request, *, store, run_root, run_id, services):
    """Injected only by tests: real run_fix/build_live_runtime/open/close are retained."""
    from headroom import orchestrator
    from headroom.runtime import build_live_runtime

    def denied(*args, **kwargs):
        raise AssertionError("No network/GPU test execution")

    socket.getaddrinfo = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    root = Path(request.runtime_profile).parents[2]

    def respond(wire):
        body = json.loads(wire.content)
        (root / ("sdk-" + run_id + ".json")).write_text(json.dumps({"model": body["model"]}))
        diagnosis = {
            "root_causes": [
                {
                    "id": "c1",
                    "title": "Offline memory evidence",
                    "category": "activations",
                    "bytes_gb": 2.0,
                    "evidence_refs": ["stk_fixture"],
                    "confidence": 0.9,
                }
            ],
            "plan": [],
            "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
            "needs_more_info": True,
            "notes": ["Offline integration fixture; not an empirical repair."],
        }
        return httpx.Response(
            200,
            json={
                "id": "offline-api-fixture",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(diagnosis)},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    def runtime(*args, **kwargs):
        return build_live_runtime(
            *args,
            **kwargs,
            env_file=root / "credential.fixture",
            transport=httpx.MockTransport(respond),
        )

    def baseline(script, **kwargs):
        path = Path(kwargs["run_root"]) / "offline-baseline"
        path.mkdir(parents=True)
        shutil.copytree(kwargs["source_root"], path / "source")
        return {
            "run_id": "offline-baseline",
            "run_dir": str(path),
            "status": "oom",
            "peak_alloc_gb": 2.0,
            "peak_reserved_gb": 2.1,
            "steps": 0,
            "loss_series": [],
            "env": {"seed": 1337},
        }

    def evidence(run, *, output_dir, **kwargs):
        output_dir.mkdir(parents=True)
        data = {
            "sources": [{"path": "train.py"}],
            "analysis": {"stack_catalog": {"stk_fixture": []}},
        }
        (output_dir / "evidence.json").write_text(json.dumps(data))
        (output_dir / "evidence.md").write_text("Offline stk_fixture.\n")
        return {
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
            "analysis": data["analysis"],
            "token_count": 10,
        }

    orchestrator.build_live_runtime = runtime
    orchestrator.read_live_profile = read_live_profile
    # Only Lab/evidence are synthetic. No runtime_factory or alternate accounting.
    return orchestrator.run_fix(
        request,
        store=store,
        run_root=run_root,
        run_id=run_id,
        services=replace(services, baseline=baseline, evidence=evidence),
    )


def make_app(pool, **kwargs):
    root = pool["root"]
    scenarios = root / "scenarios"
    scenarios.mkdir()
    script = scenarios / "s3_eval_no_grad_missing/train.py"
    script.parent.mkdir()
    script.write_text("raise AssertionError('user script must not execute in offline tests')\n")
    (scenarios / "INDEX.yaml").write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "id": "s3_eval_no_grad_missing",
                        "script": "scenarios/s3_eval_no_grad_missing/train.py",
                        "expected_mode": "reclaim",
                    }
                ]
            }
        )
    )
    settings = ApiSettings(
        project_root=root,
        public_host="demo.example",
        run_submissions_enabled=True,
        judge_token="fixture-judge-token-for-offline-tests-only",
        data_root=root / "api",
        db_path=root / "api.db",
        run_root=root / "jobs",
        web_dist=root / "dist",
        event_poll_seconds=0.01,
        **kwargs,
    )
    controller = DemoAllocation(pool["path"], project_root=root)
    return create_app(
        settings,
        worker=sdk_worker,
        worker_mode="process",
        availability_monitor=NoObservation(),
        demo_allocation=controller,
    )


def done(client, run_id):
    until = time.monotonic() + 20
    while time.monotonic() < until:
        value = client.get("/api/runs/" + run_id).json()
        if value.get("api_worker_finished"):
            return value
        time.sleep(0.03)
    raise AssertionError("Offline spawned worker did not settle")


@pytest.mark.parametrize("mode", ["example", "judge"])
def test_api_spawn_normal_runtime_uses_new_pool_and_owner_sse(demo_pool, mode, monkeypatch):
    pool = demo_pool
    # No Docker containers are created by the synthetic Lab. Real cleanup is
    # covered separately; this fixture verifies that the supervisor waits for it.
    from headroom.api import queue

    cleaned = []

    def fixture_cleanup(root, run_id):
        assert (Path(root) / run_id / "lab/offline-baseline/source/train.py").is_file()
        cleaned.append(run_id)
        return True

    monkeypatch.setattr(queue, "cleanup_owned_lab", fixture_cleanup)
    app = make_app(pool)
    with TestClient(app, base_url="https://demo.example") as client:
        config = client.get("/api/config").json()
        assert config["run_submissions"]["enabled"] and config["judge_scripts_available"]
        examples = client.get("/api/examples").json()["examples"]
        assert examples[0]["recommended"]["target"] == "reclaim"
        body = {"budget": "5"}
        if mode == "example":
            body["example_id"] = "s3_eval_no_grad_missing"
            headers = {}
        else:
            body["script_text"] = "raise AssertionError('never execute custom source')\n"
            assert client.post("/api/runs", json=body).status_code == 401
            headers = {"Authorization": "Bearer fixture-judge-token-for-offline-tests-only"}
        for extra in [
            {"receipt": str(pool["path"])},
            {"runtime_profile": "other.json"},
            {"daily_budget_usd": "100"},
        ]:
            assert (
                client.post("/api/runs", json={**body, **extra}, headers=headers).status_code == 400
            )
        response = client.post("/api/runs", json=body, headers=headers)
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        final = done(client, run_id)
        assert final["status"] == "needs_human", final
        assert (pool["root"] / ("sdk-" + run_id + ".json")).exists()
        assert "stream.end" in client.get("/api/runs/" + run_id + "/events").text
        assert client.post("/api/runs", json=body, headers=headers).status_code == 429
        other = TestClient(app, base_url="https://demo.example")
        assert other.get("/api/runs/" + run_id).status_code == 404
        other.close()
        assert cleaned == [run_id]
        with sqlite3.connect(pool["receipt"]["ledger_path"]) as conn:
            run = conn.execute(
                "SELECT status,limit_usd FROM budget_runs WHERE id=?", (run_id,)
            ).fetchone()
            attempts = conn.execute(
                "SELECT settled,actual_usd FROM budget_attempts WHERE run_id=?", (run_id,)
            ).fetchall()
        assert run == ("closed", "0.30")
        assert len(attempts) == 1 and attempts[0][0] == 1 and attempts[0][1] is not None
        with sqlite3.connect(pool["root"] / ".cache/final48-allocation-registry.sqlite3") as conn:
            assert conn.execute(
                "SELECT state FROM f2_demo_runs WHERE run_id=?", (run_id,)
            ).fetchone() == ("settled",)
        assert historical_snapshot(pool["root"]) == pool["history"]


def test_changed_receipt_disables_post_before_parsing(demo_pool):
    app = make_app(demo_pool)
    with TestClient(app, base_url="https://demo.example") as client:
        assert client.get("/api/config").json()["run_submissions"]["enabled"]
        demo_pool["path"].write_text("invalid")
        assert not client.get("/api/config").json()["run_submissions"]["enabled"]
        assert client.post("/api/runs", content="not-json").status_code == 503
        assert app.state.store.list_runs() == []


def test_launcher_requires_real_receipt_for_live_mode(launcher, demo_pool, monkeypatch):
    module, _ = launcher
    root = demo_pool["root"]
    monkeypatch.setattr(module, "__file__", str(root / "scripts/serve_public.py"))
    monkeypatch.setenv("HEADROOM_PUBLIC_HOST", "demo.example")
    monkeypatch.setenv("HEADROOM_RUN_SUBMISSIONS_ENABLED", "true")
    monkeypatch.setenv("HEADROOM_PUBLIC_ALLOCATION_RECEIPT", str(demo_pool["path"]))
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", demo_pool["receipt"]["ledger_path"])
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "6.43")
    for relative in (
        "public-evaluations.json",
        "published-evaluations/r6-20261027.json",
        "published-evaluations/r5-20261027.json",
    ):
        path = root / "public-evidence" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    seen = {}

    def create(settings, *, demo_allocation):
        seen.update(settings=settings, controller=demo_allocation)
        return object()

    monkeypatch.setattr(module, "create_app", create)
    monkeypatch.setattr(module.uvicorn, "run", lambda *a, **kw: None)
    module.main()
    assert seen["settings"].run_submissions_enabled
    assert not seen["settings"].snapshot_submissions_enabled
    assert seen["controller"].receipt == demo_pool["receipt"]
    assert seen["controller"].available
