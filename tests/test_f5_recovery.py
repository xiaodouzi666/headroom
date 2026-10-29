"""Offline-only F5 environment recovery: real temporary ledgers, no live credentials."""

import hashlib
import json
import socket
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_feature_bridges import activate, clean_fixture

from headroom.acceptance import allocation as alloc
from headroom.acceptance import f5_recovery as recovery
from headroom.acceptance import feature_allocation as feature
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.cli_execution import allocation_budget_factory, prepare_feature_fix_intent
from headroom.orchestrator import FixRequest
from headroom.runtime import read_live_profile
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Network/GPU forbidden in recovery tests")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    import headroom.lab.runner

    for name in ("run_script", "run_command", "run_argv"):
        monkeypatch.setattr(headroom.lab.runner, name, deny)


def failed_original(root, intent, binding, receipt):
    budget = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="6")
    budget.open_run(binding["run_id"], ".30")
    budget.close_run(binding["run_id"])
    feature.finish_feature_child(binding, execution_terminal=True, cleanup_verified=True)
    with alloc.registry(root) as conn:
        parent = json.loads(
            conn.execute(
                "SELECT payload FROM feature_parents WHERE parent_id=?", (binding["parent_id"],)
            ).fetchone()[0]
        )
    feature.finish_feature_parent(parent, status="completed")
    job = root / "runs/old/jobs" / binding["run_id"]
    job.mkdir(parents=True)
    store = Store(job.parent.parent / "results.sqlite3")
    store.create_run(binding["run_id"], {"status": "needs_human"})
    store.close()
    outcome = {
        "run_id": binding["run_id"],
        "run_dir": str(job),
        "status": "needs_human",
        "reason": recovery.ENV_REASON,
        "target_met": False,
        "search": {"stop_reason": "runtime_not_ready", "rounds_executed": 0},
        "report": {
            "run": {"feature_intent": intent},
            "evidence": {},
            "rounds": [],
            "usage": {"calls": 0},
        },
        "evaluation_timing": {
            "cleanup_verified": True,
            "deadline_exceeded": False,
            "within_wall_limit": True,
            "worker_exit_code": 78,
            "cli": {
                "run_id": binding["run_id"],
                "verified": True,
                "invoked": True,
                "observed_exit_code": 78,
            },
        },
    }
    path = root / "outcome.json"
    path.write_text(json.dumps(outcome))
    return path, budget


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "allocation"
    root.mkdir()
    clean, source = clean_fixture(tmp_path)
    request = FixRequest(
        script=str(source / "train.py"),
        source_root=str(source),
        runtime_profile=str(root / ".cache/final48-allocation/runtime-profile.json"),
        budget_usd=".30",
        daily_budget_usd="6",
        research_enabled=False,
    )
    old_intent = prepare_feature_fix_intent(request, checkout=clean)
    original, receipt, _ = activate(root, old_intent, "clean-s3")
    path, budget = failed_original(root, old_intent, original, receipt)
    # New committed implementation; the original workload/request remain identical.
    target = clean / "headroom/__init__.py"
    target.write_text(target.read_text() + "\n# reviewed offline recovery revision\n")
    subprocess.run(["git", "-C", str(clean), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(clean),
            "-c",
            "user.name=Offline",
            "-c",
            "user.email=offline@example.invalid",
            "commit",
            "-qm",
            "recovery",
        ],
        check=True,
        capture_output=True,
    )
    (clean / ".env").write_text("OFFLINE_ONLY=1\\n")
    (clean / ".env").chmod(0o600)
    new = prepare_feature_fix_intent(request, checkout=clean)
    return SimpleNamespace(
        root=root,
        clean=clean,
        source=source,
        request=request,
        original=original,
        receipt=receipt,
        path=path,
        budget=budget,
        intent=new,
    )


def prepare(case, **kwargs):
    return recovery.prepare_f5_recovery(
        case.original, case.intent, outcome_path=case.path, run_id=kwargs.get("run_id", uuid4().hex)
    )


def claim(case):
    proposal = prepare(case)
    path = case.root / "proposal.json"
    path.write_text(json.dumps(proposal))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return recovery.claim_f5_recovery(path, expected_sha256=sha), proposal, path, sha


def bound_budget(case, binding, monkeypatch):
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", case.receipt["ledger_path"])
    spec = SimpleNamespace(
        allocation_child_binding=binding,
        queued_request=case.request.model_dump(mode="json"),
        run_id=binding["run_id"],
        feature_intent=case.intent,
    )
    return allocation_budget_factory(spec)(
        binding["run_id"], case.request, read_live_profile(case.request.runtime_profile)
    )


def test_recovery_preserves_original_rows_and_uses_same_pool(case, monkeypatch):
    before = alloc._budget_state(case.receipt)
    with alloc.registry(case.root) as conn:
        original = recovery._original(conn, case.original)
    binding, _, _, _ = claim(case)
    assert binding["scope"] == "F5" and binding["slot_id"] == "clean-s3"
    budget = bound_budget(case, binding, monkeypatch)
    assert budget.total_limit == recovery.money(".30")
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "paid", ".2")
    budget.settle(binding["run_id"], "paid", ".2")
    with pytest.raises(BudgetExceeded):
        budget.reserve(binding["run_id"], "over", ".11")
    budget.close_run(binding["run_id"])
    result = recovery.finish_f5_recovery(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["combined_f5_charged_usd"] == "0.2"
    with alloc.registry(case.root) as conn:
        assert recovery._original(conn, case.original) == original
    after = alloc._budget_state(case.receipt)
    assert after["runs"][case.original["run_id"]] == before["runs"][case.original["run_id"]]
    assert not [a for a in after["attempts"] if a["run_id"] == case.original["run_id"]]


@pytest.mark.parametrize(
    "change", ["reason", "cleanup", "baseline", "store_call", "zero_attempt", "pending"]
)
def test_only_exact_zero_dispatch_environment_failure(case, change):
    d = json.loads(case.path.read_text())
    if change == "reason":
        d["reason"] = "some other readiness failure"
    elif change == "cleanup":
        d["evaluation_timing"]["cleanup_verified"] = False
    elif change == "baseline":
        (case.root / "runs/old/jobs" / case.original["run_id"] / "lab").mkdir()
    elif change == "store_call":
        with sqlite3.connect(case.root / "runs/old/results.sqlite3") as conn:
            conn.execute(
                "INSERT INTO llm_calls(run_id,model,role,created_at,data_json) VALUES(?,?,?,?,?)",
                (case.original["run_id"], "offline", "diagnose", "now", "{}"),
            )
    else:
        with sqlite3.connect(case.receipt["ledger_path"]) as conn:
            conn.execute(
                "UPDATE budget_runs SET status='open' WHERE id=?", (case.original["run_id"],)
            )
        case.budget.reserve(case.original["run_id"], "old-attempt", ".01")
        if change == "zero_attempt":
            case.budget.settle(case.original["run_id"], "old-attempt", "0")
            case.budget.close_run(case.original["run_id"])
    case.path.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        prepare(case)


@pytest.mark.parametrize("change", ["budget", "request", "workload"])
def test_new_intent_cannot_change_workload_controls_or_caps(case, change):
    if change == "budget":
        case.intent["budget_usd"] = ".31"
    elif change == "request":
        case.intent["payload"]["queued_request"]["max_steps"] = 5
    else:
        key = "scenarios/s3_eval_no_grad_missing/train.py"
        case.intent["payload"]["checkout"]["source_files"][key] = "0" * 64
    with pytest.raises(ValueError):
        prepare(case)


def test_exact_proposal_sha_and_original_run_once(case):
    p = prepare(case)
    path = case.root / "proposal.json"
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match="PROPOSAL_CHANGED"):
        recovery.claim_f5_recovery(path, expected_sha256="0" * 64)
    binding, _, path, sha = claim(case)
    with pytest.raises(ValueError, match="ALREADY_CLAIMED|UNSETTLED"):
        recovery.claim_f5_recovery(path, expected_sha256=sha)
    with pytest.raises(ValueError, match="ALREADY_CLAIMED|UNSETTLED"):
        prepare(case)
    assert binding["run_id"] != case.original["run_id"]


@pytest.mark.parametrize(
    "change", ["source", "profile", "receipt", "child_state", "evidence", "original"]
)
def test_second_reserve_rechecks_frozen_binding(case, monkeypatch, change):
    binding, _, _, _ = claim(case)
    budget = bound_budget(case, binding, monkeypatch)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "first", ".01")
    budget.settle(binding["run_id"], "first", ".01")
    if change == "source":
        (case.source / "train.py").write_text("changed=1\n")
    elif change == "receipt":
        path = Path(binding["receipt_path"])
        data = json.loads(path.read_text())
        data["amounts"]["daily_limit_usd"] = "999"
        path.write_text(json.dumps(data))
    elif change == "profile":
        with open(case.receipt["profile_path"], "a") as f:
            f.write(" ")
    elif change == "evidence":
        case.path.write_text(case.path.read_text() + " ")
    else:
        with alloc.registry(case.root) as conn:
            if change == "child_state":
                conn.execute("UPDATE f5_zero_dispatch_recoveries SET state='blocked'")
            else:
                conn.execute("UPDATE claims SET state='blocked' WHERE task_scope='F5'")
    with pytest.raises(ValueError):
        budget.reserve(binding["run_id"], "second", ".01")
    assert (
        len(
            [
                a
                for a in alloc._budget_state(case.receipt)["attempts"]
                if a["run_id"] == binding["run_id"]
            ]
        )
        == 1
    )


def test_unsettled_recovery_blocks_other_feature_claims(case):
    binding, _, _, _ = claim(case)
    with alloc.registry(case.root) as conn:
        with pytest.raises(ValueError, match="F5_RECOVERY_UNSETTLED"):
            feature._quiet_registry(conn)
        feature._quiet_registry(conn, allowed_run=binding["run_id"])


@pytest.mark.parametrize("cleanup", [False, True])
def test_unknown_or_unclean_recovery_is_never_settled(case, monkeypatch, cleanup):
    binding, _, _, _ = claim(case)
    budget = bound_budget(case, binding, monkeypatch)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "unknown", ".01")
    budget.settle(binding["run_id"], "unknown", None if cleanup else ".01")
    budget.close_run(binding["run_id"])
    result = recovery.finish_f5_recovery(binding, execution_terminal=True, cleanup_verified=cleanup)
    assert result["status"] == "blocked"
    if cleanup:
        assert result["actual_usd"] is None and not result["cost_resolved"]


def test_clean_installed_console_recovery_route(tmp_path, monkeypatch):
    import test_feature_bridges as bridge

    ordinary = bridge.activate

    def replacement(root, intent, slot):
        old, receipt, credential = ordinary(root, intent, slot)
        path, _ = failed_original(root, intent, old, receipt)
        env = Path(intent["payload"]["checkout"]["path"]) / ".env"
        env.write_text("OFFLINE_ONLY=1\\n")
        env.chmod(0o600)
        proposal = recovery.prepare_f5_recovery(old, intent, outcome_path=path, run_id=uuid4().hex)
        filename = root / "recovery-proposal.json"
        filename.write_text(json.dumps(proposal))
        new = recovery.claim_f5_recovery(
            filename, expected_sha256=hashlib.sha256(filename.read_bytes()).hexdigest()
        )
        return new, receipt, credential

    monkeypatch.setattr(bridge, "activate", replacement)
    bridge.test_f5_actual_installed_console_imports_own_clean_checkout_and_removes_pythonpath(
        tmp_path
    )


def test_bound_is_resolved_without_fabricating_actual(case, monkeypatch):
    binding, _, _, _ = claim(case)
    budget = bound_budget(case, binding, monkeypatch)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "bounded", ".02")
    budget.settle_upper_bound(
        binding["run_id"], "bounded", ".01", basis="verified_tariff_missing_cache_count"
    )
    budget.close_run(binding["run_id"])
    result = recovery.finish_f5_recovery(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["cost_resolved"] is True
    assert result["actual_usd"] is None and result["combined_f5_charged_usd"] == "0.01"


def test_global_ceiling_counts_prior_shared_spend(case, monkeypatch):
    case.budget.open_run("other-task", ".20")
    case.budget.reserve("other-task", "other-paid", ".20")
    case.budget.settle("other-task", "other-paid", ".12")
    case.budget.close_run("other-task")
    binding, proposal, _, _ = claim(case)
    assert proposal["prior_charged_usd"] == "0.12"
    assert binding["total_limit_usd"] == "0.42"
    budget = bound_budget(case, binding, monkeypatch)
    assert budget.total_limit == recovery.money(".42")
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "all", ".30")
    budget.settle(binding["run_id"], "all", ".30")
    with pytest.raises(alloc.AllocationRefused, match="CAP_EXCEEDED"):
        budget.reserve(binding["run_id"], "over", ".001")


def test_shared_pool_exhaustion_refuses_recovery(case):
    case.budget.open_run("other-task", "5.80")
    case.budget.reserve("other-task", "other-paid", "5.80")
    case.budget.settle("other-task", "other-paid", "5.80")
    case.budget.close_run("other-task")
    with pytest.raises(ValueError, match="POOL_EXHAUSTED"):
        prepare(case)


def test_replaced_budget_db_identity_rejected_before_second_reserve(case, monkeypatch):
    binding, _, _, _ = claim(case)
    budget = bound_budget(case, binding, monkeypatch)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "first", ".01")
    budget.settle(binding["run_id"], "first", ".01")
    path = Path(case.receipt["ledger_path"])
    copy = path.with_name("fixture-replacement.db")
    from contextlib import closing

    with (
        closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(copy)) as dst,
    ):
        src.backup(dst)
    copy.replace(path)
    with pytest.raises(ValueError):
        budget.reserve(binding["run_id"], "second", ".01")


@pytest.mark.parametrize("kind", ["missing", "mode", "symlink"])
def test_environment_metadata_must_be_correct_before_claim(case, kind):
    env = case.clean / ".env"
    if kind == "missing":
        env.unlink()
    elif kind == "mode":
        env.chmod(0o644)
    else:
        saved = case.clean / "offline-env"
        env.rename(saved)
        env.symlink_to(saved)
    with pytest.raises(ValueError, match="ENV_NOT_READY"):
        prepare(case)
