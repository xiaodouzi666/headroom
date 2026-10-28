"""Offline F3 numerical-policy and receipt binding through the installed CLI."""

import json
import socket

import pytest
from typer.testing import CliRunner

from headroom.cli import app
from headroom.cli_execution import cli_arguments
from headroom.orchestrator import FixRequest, Policy


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in F3 CLI bridge tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize(
    "mode,allow",
    [
        ("legacy", False),
        ("exact-loss20-v1", False),
        ("observed-bf16-v1", True),
    ],
)
def test_numerical_requirement_cli_roundtrip_retains_legacy_shape(monkeypatch, mode, allow):
    from headroom import orchestrator

    seen = []
    monkeypatch.setattr(
        orchestrator,
        "run_fix",
        lambda request, **kwargs: seen.append(request) or {"status": "completed"},
    )
    request = FixRequest(
        script="offline.py", policy=Policy(numerical_requirement=mode, allow_numerics_change=allow)
    )
    args = cli_arguments(request)
    assert ("--numerical-requirement" in args) is (mode != "legacy")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert len(seen) == 1 and seen[0].policy == request.policy
    assert ("numerical_requirement" in seen[0].policy.model_dump()) is (mode != "legacy")
    assert len(Policy().model_dump()) == 4


@pytest.mark.parametrize(
    "args",
    [
        ["--numerical-requirement", "unknown"],
        ["--numerical-requirement", "exact-loss20-v1", "--allow-numerics-change"],
        ["--numerical-requirement", "observed-bf16-v1", "--no-allow-numerics-change"],
        ["--numerical-requirement", "exact-loss20-v1", "--max-steps", "5"],
    ],
)
def test_invalid_cli_tier_never_dispatches(monkeypatch, args):
    from headroom import orchestrator

    monkeypatch.setattr(
        orchestrator,
        "run_fix",
        lambda *args, **kwargs: pytest.fail("Invalid tier must stop before run_fix"),
    )
    result = CliRunner().invoke(app, ["fix", "offline.py", *args])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "mode,allow",
    [
        ("exact-loss20-v1", False),
        ("observed-bf16-v1", True),
    ],
)
def test_actual_installed_console_preserves_explicit_numerical_requirement(tmp_path, mode, allow):
    from test_cli_execution import execute_case, setup_case

    request, run_id, values = setup_case(
        tmp_path, policy=Policy(numerical_requirement=mode, allow_numerics_change=allow)
    )
    result, receipt = execute_case(tmp_path, values)
    assert result.returncode == 0, result.stderr
    assert receipt["run_dispatched"] and receipt["result_saved"]
    dispatch = json.loads((tmp_path / "dispatch.json").read_text())
    assert dispatch["run_id"] == run_id
    assert dispatch["request"] == request.model_dump()


@pytest.fixture
def bound_case(tmp_path):
    from test_cli_execution import setup_case
    from test_diagnosis_acceptance import profile

    from headroom.acceptance import allocation as alloc
    from headroom.budget import BudgetLedger
    from headroom.store.db import Store

    request, run_id, values = setup_case(tmp_path, budget_usd="0.6", daily_budget_usd="5")
    request = request.model_copy(
        update={"runtime_profile": str(tmp_path / ".cache/final48-allocation/runtime-profile.json")}
    )
    values[0] = request.model_dump()
    BudgetLedger(tmp_path / ".cache/budget.db", total_limit="5", daily_limit="5")
    path, _ = profile(tmp_path)
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "5",
        "available_gift_usd": "5",
        "review_reserve_usd": "0",
        "tax_reserve_usd": "0",
        "daily_limit_usd": "5",
    }
    plan["task_run_caps_usd"]["F1"] = "1.5"
    plan["task_run_caps_usd"]["F3"] = "1.2"
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    cells = {f"cell{i}": alloc.request_sha256(request) for i in range(12)}
    plan["task_pins"]["F3"] = {
        "preparation_sha256": "4" * 64,
        "cell_requests_sha256": alloc.digest(cells),
    }
    auth = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "5",
        "approval_message_ref": "offline-fixture-only",
        "statement_sha256": "5" * 64,
    }
    receipt = alloc.activate_allocation(
        plan, auth, json.loads(path.read_text()), project_root=tmp_path
    )
    parent = alloc.claim_f3_parent(
        tmp_path / ".cache/final48-allocation/receipt.json",
        project_root=tmp_path,
        preparation_sha256="4" * 64,
        cell_requests=cells,
        scope_limit_usd="1.2",
    )
    binding = alloc.claim_f3_child(parent, cell_id="cell0", request=request, run_id=run_id)
    store = Store(tmp_path / "store.db")
    store.update_run(run_id, request=request.model_dump(), allocation_child_binding=binding)
    store.close()
    values.append(binding)
    return request, run_id, values, binding, receipt


@pytest.mark.parametrize("tamper", ["binding", "profile", "receipt", "child_state"])
def test_bound_factory_uses_scope_ceiling_and_rechecks_before_attempt(
    bound_case, monkeypatch, tamper
):
    from decimal import Decimal
    from types import SimpleNamespace

    from headroom.acceptance.allocation import AllocationRefused
    from headroom.cli_execution import allocation_budget_factory
    from headroom.ledger_path import BUDGET_DB_ENV
    from headroom.runtime import read_live_profile

    request, run_id, _, binding, receipt = bound_case
    monkeypatch.setenv(BUDGET_DB_ENV, receipt["ledger_path"])
    spec = SimpleNamespace(
        allocation_child_binding=binding, queued_request=request.model_dump(), run_id=run_id
    )
    budget = allocation_budget_factory(spec)(
        run_id, request, read_live_profile(request.runtime_profile)
    )
    assert budget.total_limit == Decimal("1.2")  # allocation profile has 5, F3 has 1.2
    assert budget.daily_limit == Decimal(5)
    budget.open_run(run_id, "0.6")
    budget.reserve(run_id, "offline-attempt", "0.01")
    budget.settle(run_id, "offline-attempt", "0.01")
    if tamper == "binding":
        binding["cell_id"] = "forged"
    elif tamper in {"profile", "receipt"}:
        path = request.runtime_profile if tamper == "profile" else binding["receipt_path"]
        with open(path, "a") as handle:
            handle.write(" " if tamper == "profile" else "invalid")
    else:
        import sqlite3
        from pathlib import Path

        with sqlite3.connect(
            Path(binding["project_root"]) / ".cache/final48-allocation-registry.sqlite3"
        ) as conn:
            conn.execute("UPDATE f3_children SET state='settled' WHERE run_id=?", (run_id,))
    with pytest.raises((AllocationRefused, ValueError)):
        budget.reserve(run_id, "never-dispatched", "0.01")
    assert budget.snapshot(run_id)["pending_attempts"] == 0


def test_supervisor_rejects_changed_request_before_spawn(bound_case, monkeypatch, tmp_path):
    import time

    from headroom import evaluation_worker as worker
    from headroom.acceptance.allocation import AllocationRefused
    from headroom.store.db import Store

    request, run_id, _, binding, _ = bound_case
    monkeypatch.setattr(
        worker.multiprocessing,
        "get_context",
        lambda *a: pytest.fail("No spawn after failed allocation verification"),
    )
    store = Store(tmp_path / "store.db")
    try:
        with pytest.raises(AllocationRefused):
            worker.supervise_evaluation_run(
                request.model_copy(update={"budget_usd": "0.61"}),
                store=store,
                run_root=tmp_path / "jobs",
                run_id=run_id,
                condition="full_ultra",
                audit_dir=tmp_path / "audit",
                started=time.monotonic(),
                allocation_child_binding=binding,
            )
    finally:
        store.close()


def test_child_rechecks_profile_before_preparation(bound_case, tmp_path):
    from headroom.evaluation_worker import _evaluation_entry
    from headroom.store.db import Store

    request, run_id, values, _, _ = bound_case
    with open(request.runtime_profile, "a") as f:
        f.write(" ")
    _evaluation_entry(*values)
    assert not (tmp_path / "prepared").exists()
    store = Store(tmp_path / "store.db")
    try:
        assert store.get_run(run_id)["status"] == "failed"
    finally:
        store.close()


def test_conflicting_database_is_refused_before_console_launch(bound_case, monkeypatch, tmp_path):
    from test_cli_execution import execute_case

    from headroom.ledger_path import BUDGET_DB_ENV

    _, _, values, _, _ = bound_case
    monkeypatch.setenv(BUDGET_DB_ENV, str(tmp_path / ".cache/budget.db"))
    _, receipt = execute_case(tmp_path, values)
    assert receipt is None
    assert not (tmp_path / "dispatch.json").exists()
    assert not (tmp_path / "prepared").exists()


def test_bound_installed_console_selects_new_database_and_real_runtime_settles(
    bound_case, monkeypatch, tmp_path
):
    import sqlite3

    import test_cli_execution as helper

    from headroom.acceptance.allocation import historical_snapshot

    _, run_id, values, _, receipt = bound_case
    history = historical_snapshot(tmp_path)
    original = helper.child_environment

    def environment(path):
        result = original(path)
        startup = path / "python-startup/sitecustomize.py"
        with startup.open("a") as handle:
            handle.write("""
if os.environ.get("HEADROOM_EVALUATION_CONTEXT"):
    from headroom import orchestrator
    from headroom.runtime import read_live_profile
    orchestrator.read_live_profile = read_live_profile
""")
        return result

    monkeypatch.setattr(helper, "child_environment", environment)
    result, cli_receipt = helper.execute_case(tmp_path, values, mode="pipeline")
    assert result.returncode == 78, result.stderr
    assert cli_receipt["run_dispatched"] and cli_receipt["result_saved"]
    assert (tmp_path / "mock-request.json").exists()
    with sqlite3.connect(receipt["ledger_path"]) as conn:
        state = conn.execute(
            "SELECT status,limit_usd,budget_mode FROM budget_runs WHERE id=?", (run_id,)
        ).fetchone()
        attempts = conn.execute(
            "SELECT settled,actual_usd FROM budget_attempts WHERE run_id=?", (run_id,)
        ).fetchall()
    assert state == ("closed", "0.6", "strict_reservation")
    assert len(attempts) == 1 and attempts[0][0] == 1 and attempts[0][1] is not None
    assert historical_snapshot(tmp_path) == history
    saved = json.loads((tmp_path / f"worker-result-{run_id}.json").read_text())
    assert saved["report"]["budget"]["run_budget_mode"] == "strict_reservation"
