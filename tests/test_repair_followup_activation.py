"""Temporary-ledger E2E checks for the explicitly approved development transfer."""

import hashlib
import json
import runpy
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from headroom.acceptance import allocation as alloc
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.ledger_path import existing_file_identity

SCRIPT = (
    Path(__file__).resolve().parents[1] / "reports/repair-followup-20261030/activate-pool.py.txt"
)


def history(path):
    with sqlite3.connect(path) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            for table in ("budget_runs", "budget_attempts")
        }


@pytest.fixture
def activation(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(SCRIPT))
    activate = namespace["activate"]
    globals_ = activate.__globals__
    directory = tmp_path / "allocation"
    directory.mkdir(mode=0o700)
    records = []
    donors = []
    for name, cap, charged, amount, receipt_sha in (
        ("final48", "6.43", "4.841686372", "1.288313628", "a" * 64),
        ("judge", "20.92", "0.11456028", "3.612190772", "b" * 64),
    ):
        path = tmp_path / f"{name}.db"
        ledger = BudgetLedger(path, total_limit=cap, daily_limit=cap)
        ledger.open_run("historical", cap)
        ledger.reserve("historical", "historical-attempt", charged)
        ledger.settle("historical", "historical-attempt", charged)
        ledger.close_run("historical")
        receipt = {
            "ledger_path": str(path),
            "ledger_identity": list(existing_file_identity(path)),
            "receipt_sha256": receipt_sha,
        }
        limits = {"total_limit_usd": cap, "daily_limit_usd": cap}
        records.append((name, receipt, limits))
        donors.append(
            {
                "name": name,
                **receipt,
                "limits": limits,
                "charged_before_usd": charged,
                "amount_usd": amount,
            }
        )

    def donor_states():
        return [
            (name, receipt, limits, alloc._budget_state(receipt))
            for name, receipt, limits in records
        ]

    plan = {
        "schema": "headroom.repair-followup-allocation.v1",
        "scope": "DEVELOPMENT_REPAIR_FOLLOWUP",
        "project_root": str(tmp_path),
        "transfer_id": "temporary-approved-transfer",
        "authorization": {"gift_only": True, "approved_net_usd": "5.40"},
        "target_net_usd": "4.890504400",
        "already_consumed_under_original_authority_net_usd": "0.19949560",
        "anonymous_demo_retained_net_usd": "0.30",
        "locked_precision_reserve_net_usd": "0.01",
        "target_ledger_path": str(directory / "budget.db"),
        "target_profile_path": str(directory / "runtime-profile.json"),
        "profile": {"offline_fixture_only": True, "authorized_total_usd": "4.890504400"},
        "donors": donors,
    }
    sha = alloc.digest(plan)
    plan["plan_sha256"] = sha
    (directory / "plan.json").write_text(json.dumps(plan))
    monkeypatch.setitem(globals_, "ROOT", tmp_path)
    monkeypatch.setitem(globals_, "DIRECTORY", directory)
    monkeypatch.setitem(globals_, "TRANSFER", plan["transfer_id"])
    monkeypatch.setitem(globals_, "donors", donor_states)
    return {
        "activate": activate,
        "globals": globals_,
        "directory": directory,
        "plan": plan,
        "sha": sha,
        "records": records,
    }


def donor_snapshots(case):
    return {name: history(receipt["ledger_path"]) for name, receipt, _ in case["records"]}


def assert_funded(case):
    plan = case["plan"]
    receipt_path = case["directory"] / "activation.json"
    receipt = json.loads(receipt_path.read_text())
    digest = receipt.pop("receipt_sha256")
    assert digest == alloc.digest(receipt)
    assert receipt["state"] == "active"
    assert receipt["scope"] == "DEVELOPMENT_REPAIR_FOLLOWUP"
    assert receipt["plan_sha256"] == case["sha"]
    assert receipt["model_calls"] == receipt["gpu_jobs"] == 0
    for intended in plan["donors"]:
        ledger = BudgetLedger(
            intended["ledger_path"],
            require_existing=True,
            expected_identity=tuple(intended["ledger_identity"]),
            total_limit=intended["limits"]["total_limit_usd"],
            daily_limit=intended["limits"]["daily_limit_usd"],
        )
        assert ledger.committed_hold_usd == Decimal(intended["amount_usd"])
        assert ledger.external_commitments()[0]["receipt_sha256"] == case["sha"]
        remaining = (
            Decimal(intended["limits"]["total_limit_usd"])
            - Decimal(intended["charged_before_usd"])
            - Decimal(intended["amount_usd"])
        )
        with pytest.raises(BudgetExceeded):
            ledger.open_run("reuse-transferred-funds", str(remaining + Decimal("0.000000001")))
    final = plan["donors"][0]
    final_ledger = BudgetLedger(
        final["ledger_path"],
        total_limit=final["limits"]["total_limit_usd"],
        daily_limit=final["limits"]["daily_limit_usd"],
    )
    final_ledger.open_run("retained-anonymous-example", "0.30")
    final_ledger.close_run("retained-anonymous-example")
    target = BudgetLedger(
        plan["target_ledger_path"],
        require_existing=True,
        expected_identity=tuple(receipt["ledger_identity"]),
        total_limit=plan["target_net_usd"],
        daily_limit=plan["target_net_usd"],
    )
    assert target.external_commitments() == []
    target.open_run("new-development", plan["target_net_usd"])
    with pytest.raises(BudgetExceeded):
        target.open_run("beyond-target-cap", "0.000000001")
    target.close_run("new-development")


def test_two_donor_activation_has_separate_cap_without_rewriting_actual_costs(activation):
    case = activation
    before = donor_snapshots(case)
    profile = Path(case["plan"]["target_profile_path"])
    assert not profile.exists()
    case["activate"](case["sha"])
    assert donor_snapshots(case) == before
    assert json.loads(profile.read_text()) == case["plan"]["profile"]
    assert profile.stat().st_mode & 0o777 == 0o600
    assert_funded(case)
    # Opening retained capacity adds a run, but never changes historical attempts/costs.
    for name, receipt, _ in case["records"]:
        assert history(receipt["ledger_path"])["budget_attempts"] == before[name]["budget_attempts"]
    with pytest.raises(AssertionError):
        case["activate"](case["sha"])


def test_resume_after_profile_written_before_activation_receipt(activation, monkeypatch):
    case = activation
    before = donor_snapshots(case)
    write = case["globals"]["write"]

    def interrupted(path, value):
        if path.name == "activation.json":
            raise RuntimeError("offline interruption before activation receipt")
        return write(path, value)

    monkeypatch.setitem(case["globals"], "write", interrupted)
    with pytest.raises(RuntimeError, match="offline interruption"):
        case["activate"](case["sha"])
    profile = Path(case["plan"]["target_profile_path"])
    digest = hashlib.sha256(profile.read_bytes()).hexdigest()
    assert not (case["directory"] / "activation.json").exists()
    assert donor_snapshots(case) == before
    monkeypatch.setitem(case["globals"], "write", write)
    case["activate"](case["sha"])
    assert hashlib.sha256(profile.read_bytes()).hexdigest() == digest
    assert donor_snapshots(case) == before
    assert_funded(case)


def test_second_donor_failure_never_credits_target_and_keeps_first_hold(activation):
    case = activation
    judge = case["plan"]["donors"][1]
    judge_ledger = BudgetLedger(
        judge["ledger_path"],
        total_limit=judge["limits"]["total_limit_usd"],
        daily_limit=judge["limits"]["daily_limit_usd"],
    )
    judge_ledger.open_run("active-donor-run", "0.1")
    before = donor_snapshots(case)
    with pytest.raises(BudgetExceeded, match="Active run"):
        case["activate"](case["sha"])
    assert donor_snapshots(case) == before
    final = case["plan"]["donors"][0]
    final_ledger = BudgetLedger(
        final["ledger_path"],
        total_limit=final["limits"]["total_limit_usd"],
        daily_limit=final["limits"]["daily_limit_usd"],
    )
    assert final_ledger.committed_hold_usd == Decimal(final["amount_usd"])
    assert judge_ledger.committed_hold_usd == 0
    assert not Path(case["plan"]["target_ledger_path"]).exists()
    assert not Path(case["plan"]["target_profile_path"]).exists()
    assert not (case["directory"] / "activation.json").exists()
