"""Transactional persistence tests; no services, keys, or GPU are used."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from headroom.store.db import Store


def test_five_tables_wal_and_restart(tmp_path):
    path = tmp_path / "store.sqlite"
    store = Store(path)
    created = store.create_run("r1", target="fix-oom", status="baseline")
    assert created["target"] == "fix-oom"
    store.update_run("r1", status="needs_human", reason="No credentials")
    store.add_round("r1", decision="revert", reason="unknown verification")
    store.add_research("r1", url="https://pytorch.org/docs", credits_used=0)
    store.close()
    reopened = Store(path)
    assert reopened.get_run("r1")["status"] == "needs_human"
    assert reopened.rounds("r1")[0]["number"] == 1
    assert reopened.research("r1")[0]["credits_used"] == 0
    assert reopened.list_runs()[0]["run_id"] == "r1"
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert tables == {"runs", "rounds", "events", "llm_calls", "research"}
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_concurrent_events_across_store_instances_are_contiguous(tmp_path):
    path = tmp_path / "events.sqlite"
    stores = [Store(path) for _ in range(4)]
    stores[0].create_run("r1")
    stores[0].create_run("r2")

    def write(index):
        return stores[index % 4].add_event("r1", "round.done", {"worker": index})

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(write, range(80)))
    assert sorted(row["sequence"] for row in rows) == list(range(1, 81))
    assert [row["sequence"] for row in stores[0].events("r1", 77)] == [78, 79, 80]
    assert stores[0].get_run("r1")["event_sequence"] == 80
    assert stores[1].add_event("r2", "run.started")["sequence"] == 1


def test_failed_event_and_round_do_not_consume_numbers(tmp_path):
    store = Store(tmp_path / "rollback.sqlite")
    store.create_run("r")
    with pytest.raises(ValueError):
        store.add_event("r", "made.up")
    with pytest.raises(ValueError):
        store.add_event("r", "run.started", {"bad": float("nan")})
    assert store.add_event("r", "run.started")["sequence"] == 1
    with pytest.raises(ValueError):
        store.add_round("r", number=7)
    assert store.add_round("r")["number"] == 1
    with pytest.raises(KeyError):
        store.add_llm_call("missing", cost_usd="0.1")
    with pytest.raises(ValueError):
        store.update_run("r", event_sequence=99)
    assert store.get_run("r")["event_sequence"] == 1


def test_decimal_exact_known_subtotal_and_unknown_total(tmp_path):
    store = Store(tmp_path / "cost.sqlite")
    store.create_run("r")
    store.add_llm_call("r", model="a", cost_usd="0.1", input_tokens=1, output_tokens=2)
    store.add_llm_call("r", model="a", cost_usd=Decimal("0.2"), input_tokens=3, output_tokens=4)
    assert store.usage("r")["total_cost_usd"] == "0.3"
    store.add_llm_call("r", model="b", cost={"usd": None, "status": "unknown"}, outcome="timeout")
    usage = store.usage("r")
    assert usage["known_cost_usd"] == "0.3"
    assert usage["total_cost_usd"] is None
    assert usage["unknown_cost_calls"] == 1 and not usage["complete"]
    assert usage["input_tokens"] is None and usage["known_input_tokens"] == 4
    assert usage["by_model"][0]["total_cost_usd"] == "0.3"
    assert usage["by_model"][1]["total_cost_usd"] is None
    assert store.llm_calls("r")[-1]["cost_status"] == "unknown"


@pytest.mark.parametrize("bad", [0.1, True, "NaN", "Infinity", "-1", "1e1000"])
def test_invalid_money_rejected_without_record(tmp_path, bad):
    store = Store(tmp_path / "cost.sqlite")
    store.create_run("r")
    with pytest.raises((ValueError, TypeError)):
        store.add_llm_call("r", cost_usd=bad)
    assert store.usage("r")["calls"] == 0


def test_zero_known_charge_distinct_from_unknown_and_nested_usage(tmp_path):
    store = Store(tmp_path / "cost.sqlite")
    store.create_run("r")
    row = store.add_llm_call(
        "r",
        cost={"usd": "0", "status": "known"},
        usage={"prompt_tokens": 3, "completion_tokens": 7},
    )
    assert row["cost_status"] == "known"
    assert store.usage()["total_cost_usd"] == "0"
    assert store.usage()["input_tokens"] == 3
    with pytest.raises(ValueError):
        store.add_llm_call("r", cost_status="unknown", cost_usd="0")


def test_empty_usage_is_zero_calls_not_unknown_attempt(tmp_path):
    store = Store(tmp_path / "empty.sqlite")
    assert store.usage()["calls"] == 0
    assert store.usage()["total_cost_usd"] == "0"


def test_concrete_lifecycle_extensions_are_persisted(tmp_path):
    store = Store(tmp_path / "lifecycle.sqlite")
    store.create_run("r")
    kinds = [
        "run.preflight",
        "run.queued",
        "evidence.started",
        "patch.started",
        "report.started",
        "report.written",
        "verify.reference",
        "budget.reserved",
    ]
    for kind in kinds:
        store.add_event("r", kind)
    assert [row["kind"] for row in store.events("r")] == kinds


def test_pending_call_durable_unknown_then_settled_exactly_once(tmp_path):
    path = tmp_path / "pending.sqlite"
    store = Store(path)
    store.create_run("r")
    row = store.add_llm_call(
        "r", model="m", role="diagnose", outcome="pending", settled=False, cost_usd=None
    )
    assert store.usage()["total_cost_usd"] is None
    store.close()
    store = Store(path)
    assert store.usage()["calls"] == 1 and store.usage()["unknown_cost_calls"] == 1
    settled = store.update_llm_call(
        row["id"],
        settled=True,
        outcome="success",
        cost={"usd": "0.125", "status": "known"},
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        response_model="m",
    )
    assert settled["id"] == row["id"] and settled["model"] == "m"
    assert settled["settled"] and settled["input_tokens"] == 100
    assert store.usage()["calls"] == 1 and store.usage()["total_cost_usd"] == "0.125"
    with pytest.raises(ValueError, match="already been settled"):
        store.update_llm_call(row["id"], settled=True, outcome="success", cost_usd="0.25")
    assert store.usage()["total_cost_usd"] == "0.125"


def test_settled_unknown_charge_remains_unknown_and_cannot_resettle(tmp_path):
    store = Store(tmp_path / "unknown.sqlite")
    store.create_run("r")
    row = store.add_llm_call("r", outcome="pending", settled=False)
    settled = store.update_llm_call(
        row["id"], outcome="timeout", settled=True, cost={"usd": None, "status": "unknown"}
    )
    assert settled["settled"] and settled["cost_usd"] is None
    assert store.usage()["total_cost_usd"] is None
    with pytest.raises(ValueError):
        store.update_llm_call(row["id"], outcome="success", settled=True, cost_usd="0")


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "different"},
        {"run_id": "other"},
        {"role": "other"},
        {"cost_usd": 0.1},
        {"input_tokens": -1},
    ],
)
def test_invalid_settlement_keeps_pending_identity_and_unknown_cost(tmp_path, changes):
    store = Store(tmp_path / "invalid.sqlite")
    store.create_run("r")
    row = store.add_llm_call("r", model="m", role="diagnose", outcome="pending", settled=False)
    with pytest.raises((ValueError, TypeError)):
        store.update_llm_call(row["id"], outcome="success", settled=True, **changes)
    saved = store.llm_calls("r")[0]
    assert saved["outcome"] == "pending" and not saved["settled"]
    assert saved["model"] == "m" and store.usage()["total_cost_usd"] is None


def test_concurrent_settlement_only_one_writer_succeeds(tmp_path):
    path = tmp_path / "settlement.sqlite"
    stores = [Store(path) for _ in range(2)]
    stores[0].create_run("r")
    row = stores[0].add_llm_call("r", outcome="pending", settled=False)

    def settle(store):
        try:
            store.update_llm_call(row["id"], outcome="success", settled=True, cost_usd="0.1")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(settle, stores)) == [False, True]
    assert stores[0].usage()["total_cost_usd"] == "0.1"
    assert stores[0].usage()["calls"] == 1
