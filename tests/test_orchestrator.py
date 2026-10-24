"""Explicit offline integration fixtures; these do not certify model/GPU acceptance."""

import json
import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from headroom.config import RuntimeConfig, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.cost import Pricing
from headroom.llm.router import LLMRouter
from headroom.orchestrator import FixRequest, Services, run_fix
from headroom.search import HARD_CHECKS
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in offline orchestrator tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "train.py").write_text("VALUE = 1\n")
    return root


def test_missing_nebius_produces_durable_partial_report_without_running_lab(tmp_path):
    root = source(tmp_path)
    store = Store(tmp_path / "store.db")

    def forbidden(*args, **kwargs):
        pytest.fail("Lab must not run when runtime prerequisites are missing")

    result = run_fix(
        FixRequest(script=str(root / "train.py"), runtime_profile=str(tmp_path / "absent.json")),
        store=store,
        run_root=tmp_path / "jobs",
        services=Services(baseline=forbidden),
    )
    assert result["status"] == "needs_human"
    assert not result["target_met"]
    assert store.usage(result["run_id"])["calls"] == 0
    assert Path(result["report_md"]).read_text().count("\n## ") >= 7
    assert "needs_human" in [event["kind"] for event in store.events(result["run_id"])]
    store.close()


def test_source_network_code_rejected_before_runtime_or_model(tmp_path):
    root = source(tmp_path)
    (root / "train.py").write_text("import socket\n")

    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted input must be rejected before runtime setup")

    store = Store(tmp_path / "store.db")
    result = run_fix(
        FixRequest(script=str(root / "train.py")),
        store=store,
        run_root=tmp_path / "jobs",
        services=Services(runtime_factory=forbidden, provenance="offline_fixture"),
    )
    assert result["status"] == "needs_human"
    assert store.usage(result["run_id"])["calls"] == 0
    store.close()


@pytest.mark.parametrize(
    "execution_argv",
    [
        None,
        ["python", "-O", "-W", "ignore", "train.py", "--batch=4"],
        ["python3", "-X", "dev", "-m", "train", "--batch=4"],
    ],
)
def test_sdk_patch_and_report_pipeline_keeps_fixture_provenance(tmp_path, execution_argv):
    root = source(tmp_path)
    store = Store(tmp_path / "store.db")
    diagnosis = {
        "root_causes": [
            {
                "id": "c1",
                "title": "Fixture allocation",
                "category": "activations",
                "bytes_gb": 2.0,
                "evidence_refs": ["stk_fixture"],
                "confidence": 0.9,
            }
        ],
        "plan": [
            {
                "fix_id": "f1",
                "type": "code",
                "title": "Fixture edit",
                "description": "Change a fixture constant.",
                "expected_saving_gb": 1.0,
                "numerics_impact": "none",
                "throughput_impact": "none",
                "risk": "This is an offline fixture only.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Synthetic integration, not actual diagnosis."],
    }
    proposal = {
        "diff": "diff --git a/train.py b/train.py\n--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
        "env_changes": {},
        "cli_changes": [],
        "notes": ["Synthetic test only."],
    }
    calls = []

    def runtime(run_id, store, directory):
        models = candidate_models()
        for name, spec in models.items():
            models[name] = replace(
                spec,
                pricing=Pricing(Decimal(1), Decimal(2), verified=True, source="offline fixture"),
            )

        def respond(request):
            body = json.loads(request.content)
            calls.append(body["model"])
            payload = diagnosis if len(calls) == 1 else proposal
            return httpx.Response(
                200,
                json={
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps(payload)},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            )

        def recorded(record):
            store.add_llm_call(
                run_id,
                {
                    "role": record.role,
                    "model": record.model,
                    "usage": vars(record.usage),
                    "cost": record.cost.as_dict(),
                    "outcome": record.outcome,
                    "provenance": "offline_fixture",
                },
            )

        client = TokenFactoryClient(
            config=RuntimeConfig(models=models),
            transport=httpx.MockTransport(respond),
            after_record=recorded,
        )
        return SimpleNamespace(
            router=LLMRouter(client), client=client, evidence_token_budget=1000, close=client.close
        )

    def baseline(script, **kwargs):
        assert kwargs.get("execution_argv") == execution_argv
        run = Path(kwargs["run_root"]) / "fixture-baseline"
        run.mkdir(parents=True)
        shutil.copytree(kwargs["source_root"], run / "source")
        return {
            "run_id": "fixture-baseline",
            "run_dir": str(run),
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
        (output_dir / "evidence.md").write_text("Synthetic fixture stack stk_fixture.\n")
        return {
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
            "token_count": 10,
            "analysis": data["analysis"],
        }

    def verify(before, script, **kwargs):
        assert kwargs.get("execution_argv") == execution_argv
        assert kwargs.get("acceptance_scope", "standard") == (
            "repository" if execution_argv else "standard"
        )
        assert Path(script).read_text() == "VALUE = 2\n"
        assert (root / "train.py").read_text() == "VALUE = 1\n"
        after = {
            **before,
            "status": "completed",
            "steps": 20,
            "peak_alloc_gb": 1.0,
            "peak_reserved_gb": 1.1,
        }
        return {
            "report": {
                "completed": True,
                "target_met": True,
                "loss_equivalence": "identical",
                "peak_before": 2.0,
                "peak_after": 1.0,
                "reduction_pct": 50.0,
                "notes": ["All measurements synthetic"],
                "checks": {
                    **dict.fromkeys(HARD_CHECKS, True),
                    "parameter_count_unchanged": True,
                    "numerical_acceptance": True,
                    "loss_tolerance": True,
                    "loss_decreases": True,
                    "throughput_limit": None,
                    "offline_fixture_only": True,
                },
            },
            "candidate": after,
            "reference": None,
        }

    result = run_fix(
        FixRequest(
            script=str(root / "train.py"),
            execution_argv=execution_argv,
            script_args=["--batch=4"] if execution_argv else [],
            repository_mode=execution_argv is not None,
        ),
        store=store,
        run_root=tmp_path / "jobs",
        services=Services(
            baseline=baseline,
            evidence=evidence,
            verify=verify,
            runtime_factory=runtime,
            provenance="offline_fixture",
        ),
    )
    assert result["status"] == "completed", result["reason"]
    assert len(calls) == 2
    assert store.usage(result["run_id"])["calls"] == 2
    assert len(store.events(result["run_id"])) >= 15
    assert store.get_run(result["run_id"])["provenance"] == "offline_fixture"
    assert (root / "train.py").read_text() == "VALUE = 1\n"
    assert (Path(result["run_dir"]) / "patch.diff").exists()
    assert "offline_fixture" in Path(result["report_json"]).read_text()
    store.close()


def search_run(
    tmp_path,
    plans,
    *,
    max_rounds=6,
    budget_after=None,
    cancel_after=None,
    research_factory=None,
    research_enabled=False,
    target="fit:22GB",
    reclaim_reduction_pct=30.0,
    search_mode="until_target",
    evidence_fail_at=None,
    verify_error_at=None,
    policy=None,
):
    import difflib

    from headroom.budget import BudgetExceeded
    from headroom.config import ULTRA_MODEL
    from headroom.search import HARD_CHECKS

    root = source(tmp_path)
    store = Store(tmp_path / "search-store.db")
    requests, verifies = [], []
    counters = {"diagnose": 0, "patch": 0}
    env = {
        "seed": 1337,
        "torch": "2.5.1",
        "device": "cuda",
        "gpu_name": "SYNTHETIC FIXTURE",
        "gpu_total_memory_bytes": 40_000_000_000,
    }

    def observed(path, peak=30, ms=100):
        return {
            "run_id": path.name,
            "run_dir": str(path),
            "status": "completed",
            "protocol": "headroom.lab.v1",
            "capture_complete": True,
            "cleanup_verified": True,
            "peak_allocated_bytes": int(peak * 1e9),
            "peak_alloc_gb": peak,
            "step_ms_median": ms,
            "shared_gpu": False,
            "gpu_observation_complete": True,
            "steps": 20,
            "loss_series": [1.0] * 20,
            "env": env,
            "provenance": "offline_fixture",
        }

    def runtime(run_id, store, directory):
        models = {
            name: replace(
                spec,
                pricing=Pricing(Decimal(1), Decimal(2), verified=True, source="offline fixture"),
            )
            for name, spec in candidate_models().items()
        }

        def before(role, spec, attempt, body):
            if (
                role == "diagnose"
                and cancel_after is not None
                and counters["diagnose"] >= cancel_after
            ):
                from headroom.orchestrator import RunCancelled

                raise RunCancelled("Synthetic deadline")
            if (
                role == "diagnose"
                and budget_after is not None
                and counters["diagnose"] >= budget_after
            ):
                raise BudgetExceeded("Synthetic request reservation denied")

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if body["model"] == ULTRA_MODEL:
                index = counters["diagnose"]
                counters["diagnose"] += 1
                plan = plans[min(index, len(plans) - 1)]
                payload = {
                    "root_causes": [
                        {
                            "id": "c1",
                            "title": "Synthetic memory",
                            "category": "activations",
                            "bytes_gb": 30.0,
                            "evidence_refs": ["stk_fixture"],
                            "confidence": 0.9,
                        }
                    ],
                    "plan": [
                        {
                            "fix_id": f"f{index + 1}",
                            "type": "code",
                            "title": plan.get("title", "Fixture change"),
                            "description": plan.get("description", "Change a fixture constant."),
                            "expected_saving_gb": plan.get("saving", 50.0),
                            "numerics_impact": plan.get("numerics", "none"),
                            "throughput_impact": "none",
                            "risk": "Offline fixture only.",
                            "requires_policy": [],
                        }
                    ],
                    "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
                    "needs_more_info": plan.get("needs_more_info", False),
                    "notes": ["Synthetic request: provide the missing input shape."],
                }
                if plan.get("empty_plan"):
                    payload.update(root_causes=[], plan=[])
            else:
                plan = plans[min(counters["patch"], len(plans) - 1)]
                counters["patch"] += 1
                before_text, after_text = plan["before"], plan["after"]
                diff = "".join(
                    difflib.unified_diff(
                        before_text.splitlines(True),
                        after_text.splitlines(True),
                        fromfile="a/train.py",
                        tofile="b/train.py",
                    )
                )
                payload = {
                    "diff": diff,
                    "env_changes": {},
                    "cli_changes": [],
                    "notes": ["Offline synthetic fixture."],
                }
            return httpx.Response(
                200,
                json={
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": json.dumps(payload)},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            )

        def recorded(record):
            store.add_llm_call(
                run_id,
                {
                    "role": record.role,
                    "model": record.model,
                    "usage": vars(record.usage),
                    "cost": record.cost.as_dict(),
                    "outcome": record.outcome,
                    "provenance": "offline_fixture",
                },
            )

        client = TokenFactoryClient(
            config=RuntimeConfig(models=models),
            transport=httpx.MockTransport(respond),
            before_attempt=before,
            after_record=recorded,
        )
        return SimpleNamespace(
            router=LLMRouter(client), client=client, evidence_token_budget=1000, close=client.close
        )

    def baseline(script, **kwargs):
        path = Path(kwargs["run_root"]) / "original"
        path.mkdir(parents=True)
        shutil.copytree(root, path / "source")
        return observed(path)

    def evidence(run, *, output_dir, **kwargs):
        if evidence_fail_at is not None and run.name == f"candidate-{evidence_fail_at}":
            raise ValueError("Synthetic fresh evidence unavailable")
        output_dir.mkdir(parents=True)
        data = {
            "sources": [{"path": "train.py"}],
            "analysis": {"stack_catalog": {"stk_fixture": []}},
        }
        (output_dir / "evidence.json").write_text(json.dumps(data))
        (output_dir / "evidence.md").write_text(
            "Synthetic captured source: " + (run / "source/train.py").read_text()
        )
        return {
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
            "token_count": 10,
            "analysis": data["analysis"],
        }

    def verify(original, script, **kwargs):
        index = len(verifies)
        if verify_error_at is not None and index + 1 == verify_error_at:
            raise ValueError("Synthetic verification failure")
        plan = plans[index]
        assert Path(kwargs["baseline_script"]).read_text() == "VALUE = 1\n"
        assert original["peak_allocated_bytes"] == 30_000_000_000
        assert Path(script).read_text() == plan["after"]
        path = Path(kwargs["run_root"]) / f"candidate-{index + 1}"
        path.mkdir(parents=True)
        shutil.copytree(kwargs["candidate_source_root"], path / "source")
        candidate = observed(path, plan.get("peak", 25), plan.get("ms", 110))
        candidate.update(plan.get("candidate_extra", {}))
        checks = {
            **dict.fromkeys(HARD_CHECKS, True),
            "parameter_count_unchanged": True,
            "numerical_acceptance": True,
            "loss_tolerance": True,
            "loss_decreases": True,
            "throughput_limit": True,
            "memory_target": plan.get("target", False),
        }
        checks.update(plan.get("checks", {}))
        result = {
            "completed": True,
            "target_met": plan.get("target", False),
            "loss_equivalence": plan.get("loss", "identical"),
            "numerics_changed": plan.get("numerics", "none") != "none",
            "checks": checks,
            "notes": ["All metrics are synthetic."],
        }
        result.update(plan.get("verification_extra", {}))
        verifies.append({"original": original, "candidate": candidate, "kwargs": kwargs})
        return {
            "report": result,
            "candidate": candidate,
            "reference": None,
            "pairing_evidence": {"provenance": "offline_fixture", "reason": "test transport only"},
        }

    result = run_fix(
        FixRequest(
            script=str(root / "train.py"),
            target=target,
            reclaim_reduction_pct=reclaim_reduction_pct,
            max_rounds=max_rounds,
            search_mode=search_mode,
            research_enabled=research_enabled,
            **({"policy": policy} if policy is not None else {}),
        ),
        store=store,
        run_root=tmp_path / "jobs",
        services=Services(
            baseline=baseline,
            evidence=evidence,
            verify=verify,
            runtime_factory=runtime,
            research_factory=research_factory,
            provenance="offline_fixture",
        ),
    )
    return result, store, requests, verifies, root


def test_keep_revert_keep_uses_original_verification_and_current_source(tmp_path):
    plans = [
        {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25, "ms": 110},
        {
            "before": "VALUE = 2\n",
            "after": "VALUE = 3\n",
            "peak": 20,
            "ms": 115,
            "loss": "changed",
            "checks": {"loss_tolerance": False},
        },
        {"before": "VALUE = 2\n", "after": "VALUE = 4\n", "peak": 20, "ms": 120, "target": True},
    ]
    result, store, requests, verifies, root = search_run(tmp_path, plans)
    assert result["status"] == "completed" and result["target_met"]
    assert [row["decision"] for row in store.rounds(result["run_id"])] == ["keep", "revert", "keep"]
    assert len(verifies) == 3 and len(requests) == 6
    assert all(item["original"] is verifies[0]["original"] for item in verifies)
    assert (root / "train.py").read_text() == "VALUE = 1\n"
    finaldiff = (Path(result["run_dir"]) / "patch.diff").read_text()
    assert "-VALUE = 1" in finaldiff and "+VALUE = 4" in finaldiff
    assert "-VALUE = 2" not in finaldiff
    assert len(result["pareto"]["points"]) == 2
    assert Path(result["run_dir"], result["pareto"]["points"][0]["artifacts"]["patch"]).exists()
    # Third diagnosis sees earlier keep/revert decisions and the current kept source.
    assert (
        '"decision": "revert"'
        in json.loads(requests[4]["messages"][-1]["content"])["evidence_markdown"]
    )
    assert "VALUE = 2" in requests[4]["messages"][-1]["content"]
    assert all(
        Path(result["run_dir"], row["candidate_dir"]).exists()
        for row in store.rounds(result["run_id"])
    )
    store.close()


def test_budget_stop_preserves_last_kept_patch_and_durable_partial_report(tmp_path):
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25}]
    result, store, requests, verifies, _ = search_run(tmp_path, plans, budget_after=1)
    assert result["status"] == "budget_exceeded" and not result["target_met"]
    assert result["kept"]["round"] == 1 and len(verifies) == 1 and len(requests) == 2
    assert "+VALUE = 2" in Path(result["run_dir"], "patch.diff").read_text()
    assert len(store.rounds(result["run_id"])) == 2
    assert store.rounds(result["run_id"])[1]["reason"] == "budget_exceeded"
    assert json.loads(Path(result["report_json"]).read_text())["run"]["kept"]["round"] == 1
    store.close()


def test_single_round_remains_bounded_when_target_not_reached(tmp_path):
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25}]
    result, store, requests, verifies, _ = search_run(tmp_path, plans, max_rounds=1)
    assert result["status"] == "completed" and result["reason"] == "max_rounds_reached"
    assert len(verifies) == 1 and len(requests) == 2 and result["kept"]["round"] == 1
    store.close()


def test_max_rounds_contract():
    assert FixRequest(script="train.py").max_rounds == 6
    for count in (0, 7, True):
        with pytest.raises(ValueError):
            FixRequest(script="train.py", max_rounds=count)


def test_research_uses_actual_version_once_and_injects_context_sources(tmp_path, monkeypatch):
    import dotenv

    from headroom.research.tavily_tool import ResearchSession

    def forbidden(*args, **kwargs):
        pytest.fail("Tests must not read the real .env")

    monkeypatch.setattr(dotenv, "dotenv_values", forbidden)
    calls = []

    class FakeResearch:
        def search(self, **kwargs):
            calls.append(("search", kwargs))
            return {
                "results": [
                    {
                        "url": "https://docs.pytorch.org/docs/2.5/checkpoint.html",
                        "title": "Checkpoint",
                        "content": "Choose use_reentrant=False.",
                    }
                ],
                "usage": {"credits": 1},
            }

        def extract(self, **kwargs):
            calls.append(("extract", kwargs))
            return {
                "results": [
                    {"url": url, "raw_content": "Versioned checkpoint documentation."}
                    for url in kwargs["urls"]
                ],
                "usage": {"credits": 1},
                "failed_results": [],
            }

    def factory(run_id, **kwargs):
        assert (
            kwargs["torch_version"] == "2.5.1"
            and kwargs["live"] is False
            and kwargs["api_key"] is None
        )
        return ResearchSession.for_run(
            run_id,
            torch_version=kwargs["torch_version"],
            store=kwargs["store"],
            cache_dir=tmp_path / "research-cache",
            api_key="offline-placeholder",
            live=True,
            client_factory=lambda key: FakeResearch(),
            max_calls=kwargs["max_calls"],
        )

    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "peak": 25,
            "description": "Use torch.utils.checkpoint use_reentrant=False",
        },
        {
            "before": "VALUE = 2\n",
            "after": "VALUE = 3\n",
            "peak": 20,
            "target": True,
            "description": "Adjust checkpoint granularity",
        },
    ]
    result, store, requests, _, _ = search_run(
        tmp_path, plans, research_factory=factory, research_enabled=True
    )
    assert result["target_met"] and len(calls) == 2
    assert calls[0][1]["query"].startswith("PyTorch 2.5.1")
    assert len(store.research(result["run_id"])) == 2
    assert "Versioned checkpoint documentation" in requests[1]["messages"][-1]["content"]
    report = json.loads(Path(result["report_json"]).read_text())
    assert report["sources"][0]["url"] == "https://docs.pytorch.org/docs/2.5/checkpoint.html"
    assert report["run"]["research"]["api_calls"] == 2
    store.close()


def test_missing_research_credential_is_explicitly_skipped_without_blocking_patch(tmp_path):
    from headroom.research.tavily_tool import ResearchSession

    def factory(run_id, **kwargs):
        def forbidden(key):
            pytest.fail("Missing research credential must not construct a client")

        return ResearchSession.for_run(
            run_id,
            torch_version=kwargs["torch_version"],
            store=kwargs["store"],
            cache_dir=tmp_path / "no-key-cache",
            api_key=None,
            live=True,
            client_factory=forbidden,
        )

    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "peak": 20,
            "target": True,
            "description": "Use checkpoint",
        }
    ]
    result, store, _, _, _ = search_run(
        tmp_path, plans, research_factory=factory, research_enabled=True
    )
    assert result["target_met"]
    research = store.get_run(result["run_id"])["research"]
    assert research["status"] == "skipped" and research["api_calls"] == 0
    assert research["operations"][0]["reason"] == "missing_credential"
    store.close()


def test_six_round_limit_keeps_every_rejected_candidate_history(tmp_path):
    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "peak": 20,
            "loss": "changed",
            "checks": {"loss_tolerance": False},
        }
        for _ in range(6)
    ]
    result, store, requests, verifies, root = search_run(tmp_path, plans)
    assert result["status"] == "completed" and not result["target_met"]
    assert len(verifies) == 6 and len(requests) == 12
    assert len(store.rounds(result["run_id"])) == 6
    assert all(row["decision"] == "revert" for row in store.rounds(result["run_id"]))
    assert result["kept"] is None and result["pareto"]["points"] == []
    assert (root / "train.py").read_text() == "VALUE = 1\n"
    store.close()


def test_phase_events_use_recorded_models_and_keep_unknown_elapsed_unknown(tmp_path):
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}]
    result, store, requests, _, _ = search_run(tmp_path, plans)
    events = [
        row
        for row in store.events(result["run_id"])
        if row["kind"] in {"diagnose.done", "patch.written"}
    ]
    assert len(events) == 2
    assert [event["model"] for event in events] == [request["model"] for request in requests]
    assert all(event["elapsed_seconds"] is None for event in events)  # Fixture recorder omitted it.
    assert all(event["cost_usd"] == "0.00003" for event in events)
    assert all(len(event["llm_calls"]) == 1 for event in events)
    store.close()


def test_deadline_stop_preserves_kept_pointer_and_restores_signal_handler(tmp_path):
    import signal

    previous = signal.getsignal(signal.SIGTERM)
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25}]
    result, store, requests, verifies, _ = search_run(tmp_path, plans, cancel_after=1)
    assert result["status"] == "timeout" and result["kept"]["round"] == 1
    assert len(verifies) == 1 and len(requests) == 2
    assert "+VALUE = 2" in Path(result["run_dir"], "patch.diff").read_text()
    assert signal.getsignal(signal.SIGTERM) == previous
    store.close()


def test_optional_research_factory_failure_is_reported_and_does_not_block_patch(tmp_path):
    def factory(*args, **kwargs):
        raise OSError("synthetic unavailable")

    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "peak": 20,
            "target": True,
            "description": "Use checkpoint",
        }
    ]
    result, store, _, _, _ = search_run(
        tmp_path, plans, research_factory=factory, research_enabled=True
    )
    assert result["target_met"]
    assert store.get_run(result["run_id"])["research"]["reason"] == "session_unavailable"
    store.close()


def test_research_prompt_excerpts_are_bounded_and_labeled():
    from headroom.orchestrator import _research_patch_context

    result = _research_patch_context({"context": "x" * 30000, "topic": "checkpoint"})
    assert "truncated" in result["context"]
    assert len(result["context"].encode()) < 25000


def test_internal_eval_hook_is_not_a_public_request_field():
    from headroom.diagnose import diagnose_with_router

    assert Services().diagnose is diagnose_with_router
    assert (
        Services(evaluation_condition="traceback_ultra").evaluation_condition == "traceback_ultra"
    )
    with pytest.raises(ValueError):
        FixRequest(script="train.py", evaluation_condition="traceback_ultra")


def test_optional_annotations_are_live_only_and_do_not_rewrite_evidence(monkeypatch):
    from copy import deepcopy

    from headroom.orchestrator import _optional_annotations

    evidence = {"analysis": {"category_bytes": {"activations": 10}}}
    original = deepcopy(evidence)
    calls = []

    def fake(router, payload):
        calls.append(payload)
        return {"status": "failed", "reason": "offline simulated error", "acceptance": False}

    monkeypatch.setattr("headroom.orchestrator.annotate_stacks", fake)
    assert _optional_annotations(None, evidence, "offline_fixture")["status"] == "skipped"
    assert not calls
    assert _optional_annotations(None, evidence, "live")["status"] == "failed"
    assert calls == [evidence] and evidence == original


def test_interruption_during_pareto_publication_cannot_commit_unkept_point(tmp_path, monkeypatch):
    from headroom.orchestrator import RunCancelled, write_pareto

    count = 0

    def interrupted(*args, **kwargs):
        nonlocal count
        count += 1
        result = write_pareto(*args, **kwargs)
        if count == 2:
            raise RunCancelled("Synthetic publication interruption")
        return result

    monkeypatch.setattr("headroom.orchestrator.write_pareto", interrupted)
    plans = [
        {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25},
        {"before": "VALUE = 2\n", "after": "VALUE = 3\n", "peak": 20, "target": True},
    ]
    result, store, _, _, _ = search_run(tmp_path, plans)
    assert result["status"] == "timeout" and result["kept"]["round"] == 1
    assert len(result["pareto"]["points"]) == 1
    assert len(json.loads(Path(result["run_dir"], "pareto.json").read_text())["points"]) == 1
    assert "+VALUE = 2" in Path(result["run_dir"], "patch.diff").read_text()
    assert [row["decision"] for row in store.rounds(result["run_id"])] == ["keep", "revert"]
    store.close()


@pytest.mark.parametrize("empty_plan", [False, True])
def test_diagnosis_information_request_stops_without_repeating_same_evidence(tmp_path, empty_plan):
    result, store, requests, verifies, root = search_run(
        tmp_path, [{"needs_more_info": True, "empty_plan": empty_plan}], max_rounds=6
    )
    assert result["status"] == "needs_human"
    assert result["target_met"] is False
    assert len(requests) == 1
    assert verifies == []
    assert (root / "train.py").read_text() == "VALUE = 1\n"
    report = json.loads(Path(result["report_json"]).read_text())
    assert len(report["rounds"]) == 1
    assert report["rounds"][0]["reason"] == "diagnosis_needs_more_info"
    assert "input shape" in report["rounds"][0]["requested_information"][0]
    kinds = [event["kind"] for event in store.events(result["run_id"])]
    assert "needs_human" in kinds and "patch.written" not in kinds
    store.close()


@pytest.mark.parametrize("reclaim_reduction_pct,expected", [(30.0, 9.0), (20.0, 6.0)])
def test_reclaim_requests_supplement_then_stops_with_insufficient_savings(
    tmp_path, reclaim_reduction_pct, expected
):
    result, store, requests, verifies, _ = search_run(
        tmp_path,
        [{"saving": 0.1}],
        target="reclaim",
        max_rounds=6,
        reclaim_reduction_pct=reclaim_reduction_pct,
    )
    assert result["status"] == "needs_human"
    assert verifies == []
    # One initial diagnosis plus the existing bounded supplement, not six rounds.
    assert len(requests) == 2
    prompt = json.loads(next(m["content"] for m in requests[0]["messages"] if m["role"] == "user"))
    assert prompt["required_saving_gb"] == expected
    diagnosis = json.loads((Path(result["run_dir"]) / "diagnosis.json").read_text())
    assert diagnosis["requires_supplement"] is True
    assert f"{expected:g} GB" in diagnosis["supplement_request"]
    assert any(i["code"] == "INSUFFICIENT_EXPECTED_SAVING" for i in diagnosis["issues"])
    store.close()


def test_remaining_reclaim_savings_use_original_peak_and_keep_unknown_oom_unknown():
    from headroom.orchestrator import _required_reduction

    baseline = {"status": "completed", "peak_allocated_bytes": 10_000_000_000}
    current = {"status": "completed", "peak_allocated_bytes": 8_000_000_000}
    assert _required_reduction(baseline, "reclaim") == 3.0
    assert _required_reduction(current, "reclaim", original_baseline=baseline) == 1.0
    assert (
        _required_reduction(
            current, "reclaim", original_baseline=baseline, reclaim_reduction_pct=20
        )
        == 0.0
    )
    assert _required_reduction(current, "fit:7GB") == 1.0
    assert _required_reduction(current, "fit:9GB") == 0.0
    assert _required_reduction({**baseline, "status": "oom"}, "reclaim") is None
    assert _required_reduction({"status": "completed"}, "reclaim") is None
    assert _required_reduction(current, "reclaim", original_baseline={"status": "oom"}) is None


def test_verifier_pairing_evidence_is_retained_in_round_artifact_and_report(tmp_path):
    result, store, _, _, _ = search_run(
        tmp_path, [{"before": "VALUE = 1\n", "after": "VALUE = 2\n"}], max_rounds=1
    )
    expected = {"provenance": "offline_fixture", "reason": "test transport only"}
    directory = Path(result["run_dir"])
    verification = json.loads((directory / "rounds/01/verification.json").read_text())
    report = json.loads(Path(result["report_json"]).read_text())
    assert verification["pairing_evidence"] == expected
    assert report["rounds"][0]["verification"]["pairing_evidence"] == expected
    store.close()
