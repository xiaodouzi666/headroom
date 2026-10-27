"""HTTP 529 retention uses offline fixtures only; it never calls a provider."""

import hashlib
import json
import sqlite3

import httpx
import pytest
from test_bounded_billing import profile_data, response, runtime

from headroom.billing_http_review import execute_retention, prepare_retention
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.llm.request_audit import capture_request
from headroom.runtime import RuntimeNotReady


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("HTTP billing review tests cannot access DNS/INET")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def history(tmp_path):
    data = profile_data()
    for item in data["models"].values():
        item["billing"]["output_cap_field"] = "max_completion_tokens"
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(data))
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps(
            {
                "verified": True,
                "output_caps_include_reasoning": True,
                "models": {
                    item["model_id"]: {
                        "input_usd_per_million": item["input_usd_per_million"],
                        "output_usd_per_million": item["output_usd_per_million"],
                        "cached_input_usd_per_million": item["cached_input_usd_per_million"],
                        "prompt_token_ceiling": item["billing"]["prompt_token_ceiling"],
                        "output_cap_field": "max_completion_tokens",
                        "fee_components_per_request": {
                            "image": "0",
                            "price_per_video_second": "0",
                            "request": "0",
                            "price_per_minute": "0",
                        },
                    }
                    for item in data["models"].values()
                },
            }
        )
    )
    dispatched = []

    def handler(request):
        dispatched.append(request)
        if len(dispatched) == 3:
            return httpx.Response(529, json={"error": {"message": "offline unavailable"}})
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if len(dispatched) == 1:
            usage["prompt_tokens_details"] = {"cached_tokens": 0}
        return response(request, usage=usage)

    bundle, budget, store = runtime(tmp_path, handler, data=data)
    try:
        for text in ("exact", "bounded"):
            bundle.router.chat("patch", [{"role": "user", "content": text}], max_tokens=20)
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("patch", [{"role": "user", "content": "529"}], max_tokens=20)
        # SDK retries are disabled. The custom retry is refused before dispatch.
        assert len(dispatched) == 3
        calls = store.llm_calls("r")
        assert len(calls) == 3
        assert all(call["attempt"] == 1 for call in calls)
        budget.close_run("r")
        target = calls[-1]
        kwargs = {
            "ledger_path": tmp_path / "budget.db",
            "store_path": tmp_path / "store.db",
            "profile_path": profile,
            "pricing_path": pricing,
            "run_id": "r",
            "attempt_id": target["budget_attempt_id"],
        }
    finally:
        bundle.close()
        store.close()
    return budget, kwargs, target["id"]


def receipt(tmp_path, kwargs):
    value = prepare_retention(**kwargs)
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), value


def edit_call(kwargs, call_id, edit):
    with sqlite3.connect(kwargs["store_path"]) as conn:
        raw = conn.execute("SELECT data_json FROM llm_calls WHERE id=?", (call_id,)).fetchone()[0]
        data = json.loads(raw)
        edit(data)
        conn.execute("UPDATE llm_calls SET data_json=? WHERE id=?", (json.dumps(data), call_id))


def rewrite_request(data, edit):
    evidence = data["request_evidence"]
    payload = evidence["payload"]
    edit(payload)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    data["request_evidence"] = {
        **capture_request(body),
        **{key: evidence[key] for key in ("role", "model", "attempt")},
    }


def review_rows(kwargs):
    with sqlite3.connect(kwargs["ledger_path"]) as conn:
        return conn.execute("SELECT COUNT(*) FROM budget_retention_reviews").fetchone()[0]


def test_529_dispatches_once_and_review_keeps_all_charges_and_unknown_actual(tmp_path):
    budget, kwargs, call_id = history(tmp_path)
    before = budget.snapshot("r")
    with sqlite3.connect(kwargs["store_path"]) as conn:
        original_calls = conn.execute("SELECT * FROM llm_calls ORDER BY id").fetchall()
    path, sha, proposal = receipt(tmp_path, kwargs)
    assert budget.snapshot("r") == before and review_rows(kwargs) == 0
    assert len(proposal["expected_attempts"]) == len(proposal["expected_calls"]) == 3
    assert proposal["call_id"] == call_id
    assert proposal["request"]["delivery_confirmed"] is False
    result = execute_retention(
        path, expected_sha256=sha, reviewed_by="offline reviewer", daily_limit="2"
    )
    for key in ("conservative_charge_usd", "reserved_or_actual_usd", "total_actual_usd"):
        assert result[key] == before[key]
    assert result["total_actual_usd"] is None
    assert result["reviewed_retained_attempts"] == 1
    assert result["billing_complete"] and not result["dispatch_blocked"]
    with sqlite3.connect(kwargs["store_path"]) as conn:
        assert conn.execute("SELECT * FROM llm_calls ORDER BY id").fetchall() == original_calls
    with sqlite3.connect(kwargs["ledger_path"]) as conn:
        assert conn.execute(
            "SELECT upper_usd,charged_usd,actual_usd FROM budget_attempts WHERE id=?",
            (kwargs["attempt_id"],),
        ).fetchone() == ("0.00104", "0.00104", None)
    with pytest.raises(ValueError):
        execute_retention(path, expected_sha256=sha, reviewed_by="again", daily_limit="2")
    budget.open_run("next", "0.1", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded):
        budget.reserve("next", "overspend", "2")


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "usage",
        "response_model",
        "attempt",
        "request_absent",
        "wire_hash",
        "stored_hash",
        "request_size",
        "redacted",
        "cap",
        "model",
        "n",
        "stream",
        "multimodal",
        "extra_parameter",
        "template_override",
        "duplicate_mapping",
        "missing_mapping",
        "pending",
        "other_unknown",
        "charge",
        "actual",
        "halt",
        "pricing_fee",
        "pricing_rate",
        "pricing_ceiling",
        "profile_cap",
    ],
)
def test_invalid_or_ambiguous_history_remains_blocked(tmp_path, mutation):
    budget, kwargs, call_id = history(tmp_path)
    if mutation in {"other_unknown", "charge", "actual", "halt"}:
        with sqlite3.connect(kwargs["ledger_path"]) as conn:
            if mutation == "other_unknown":
                conn.execute(
                    "UPDATE budget_attempts SET actual_usd=NULL,charge_status='unknown' "
                    "WHERE id != ?",
                    (kwargs["attempt_id"],),
                )
            elif mutation == "charge":
                conn.execute(
                    "UPDATE budget_attempts SET charged_usd='0.00001' WHERE id=?",
                    (kwargs["attempt_id"],),
                )
            elif mutation == "actual":
                conn.execute(
                    "UPDATE budget_attempts SET actual_usd='0.00001' WHERE id=?",
                    (kwargs["attempt_id"],),
                )
            else:
                conn.execute("UPDATE budget_runs SET halt_reason='provider_bound_exceeded'")
    elif mutation.startswith("pricing_") or mutation == "profile_cap":
        file = kwargs["profile_path" if mutation == "profile_cap" else "pricing_path"]
        value = json.loads(file.read_text())
        if mutation == "profile_cap":
            value["models"]["super"]["billing"]["max_completion_tokens"] = 10
        else:
            # Mutate all models so this does not depend on fixture role order.
            for item in value["models"].values():
                if mutation == "pricing_fee":
                    item["fee_components_per_request"]["request"] = "0.01"
                elif mutation == "pricing_rate":
                    item["input_usd_per_million"] = "999"
                else:
                    item["prompt_token_ceiling"] = 2000
        file.write_text(json.dumps(value))
    elif mutation in {"duplicate_mapping", "missing_mapping"}:
        with sqlite3.connect(kwargs["store_path"]) as conn:
            if mutation == "missing_mapping":
                conn.execute("DELETE FROM llm_calls WHERE id=?", (call_id - 1,))
            else:
                other = json.loads(
                    conn.execute(
                        "SELECT data_json FROM llm_calls WHERE id=?", (call_id - 1,)
                    ).fetchone()[0]
                )
                other["budget_attempt_id"] = kwargs["attempt_id"]
                conn.execute(
                    "UPDATE llm_calls SET data_json=? WHERE id=?",
                    (json.dumps(other), call_id - 1),
                )
    else:

        def edit(data):
            if mutation == "status":
                data["http_status"] = 500
            elif mutation == "usage":
                data["usage"] = {"prompt_tokens": 1}
            elif mutation == "response_model":
                data["response_model"] = data["model"]
            elif mutation == "attempt":
                data["attempt"] = 2
            elif mutation == "pending":
                data["settled"] = False
            elif mutation == "request_absent":
                del data["request_evidence"]
            elif mutation in {"wire_hash", "stored_hash", "request_size", "redacted"}:
                key, value = {
                    "wire_hash": ("wire_body_sha256", "0" * 64),
                    "stored_hash": ("stored_payload_sha256", "0" * 64),
                    "request_size": ("wire_body_utf8_bytes", 1),
                    "redacted": ("payload_status", "redacted"),
                }[mutation]
                data["request_evidence"][key] = value
            else:

                def change(payload):
                    if mutation == "cap":
                        payload["max_completion_tokens"] = 21
                    elif mutation == "model":
                        payload["model"] = "wrong"
                    elif mutation == "n":
                        payload["n"] = 2
                    elif mutation == "stream":
                        payload["stream"] = True
                    elif mutation == "multimodal":
                        payload["messages"][0]["content"] = [{"type": "image_url"}]
                    elif mutation == "template_override":
                        payload["chat_template_kwargs"] = {"max_tokens": 999}
                    else:
                        payload["extra_body"] = {"max_completion_tokens": 999}

                rewrite_request(data, change)

        edit_call(kwargs, call_id, edit)
    with pytest.raises((ValueError, TypeError, RuntimeNotReady)):
        prepare_retention(**kwargs)
    assert budget.snapshot("r")["dispatch_blocked"]
    assert review_rows(kwargs) == 0


@pytest.mark.parametrize("mutation", ["receipt", "profile", "pricing", "call", "attempt"])
def test_changed_receipt_or_inputs_refuse_execution(tmp_path, mutation):
    budget, kwargs, call_id = history(tmp_path)
    path, sha, _ = receipt(tmp_path, kwargs)
    if mutation == "receipt":
        path.write_text(path.read_text() + " ")
    elif mutation in {"profile", "pricing"}:
        file = kwargs[mutation + "_path"]
        file.write_text(file.read_text() + " ")
    elif mutation == "call":
        edit_call(kwargs, call_id, lambda data: data.update(elapsed_seconds=123))
    else:
        with sqlite3.connect(kwargs["ledger_path"]) as conn:
            conn.execute(
                "UPDATE budget_attempts SET charged_usd='0.000021' WHERE id != ?",
                (kwargs["attempt_id"],),
            )
    with pytest.raises((ValueError, TypeError, RuntimeNotReady)):
        execute_retention(path, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
    assert budget.snapshot("r")["dispatch_blocked"] and review_rows(kwargs) == 0


@pytest.mark.parametrize("mutation", ["sibling_attempt", "call"])
def test_transaction_rechecks_entire_run_after_preparation(tmp_path, monkeypatch, mutation):
    budget, kwargs, call_id = history(tmp_path)
    path, sha, _ = receipt(tmp_path, kwargs)
    original = BudgetLedger.review_retained

    def change_then_review(self, *args, **values):
        if mutation == "sibling_attempt":
            with sqlite3.connect(kwargs["ledger_path"]) as conn:
                conn.execute(
                    "UPDATE budget_attempts SET charged_usd='0.000021' WHERE id != ?",
                    (kwargs["attempt_id"],),
                )
        else:
            edit_call(kwargs, call_id - 1, lambda data: data.update(elapsed_seconds=777))
        return original(self, *args, **values)

    monkeypatch.setattr(BudgetLedger, "review_retained", change_then_review)
    with pytest.raises(ValueError):
        execute_retention(path, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
    assert budget.snapshot("r")["dispatch_blocked"] and review_rows(kwargs) == 0


def test_review_failure_rolls_back_receipt_and_keeps_halt(tmp_path):
    budget, kwargs, _ = history(tmp_path)
    path, sha, _ = receipt(tmp_path, kwargs)
    with sqlite3.connect(kwargs["ledger_path"]) as conn:
        conn.execute(
            "CREATE TRIGGER fail_review BEFORE UPDATE OF charge_status ON budget_attempts "
            "BEGIN SELECT RAISE(ABORT,'offline injected failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        execute_retention(path, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
    assert budget.snapshot("r")["dispatch_blocked"] and review_rows(kwargs) == 0


def test_other_run_halt_is_never_cleared(tmp_path):
    budget, kwargs, _ = history(tmp_path)
    path, sha, _ = receipt(tmp_path, kwargs)
    with sqlite3.connect(kwargs["ledger_path"]) as conn:
        conn.execute(
            "INSERT INTO budget_runs(id,day,limit_usd,status,halt_reason,budget_mode) "
            "SELECT 'other',day,'0.6','closed','provider_bound_exceeded',budget_mode "
            "FROM budget_runs WHERE id='r'"
        )
    result = execute_retention(path, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
    assert result["halt_reason"] is None and result["dispatch_blocked"]
    with pytest.raises(BudgetExceeded):
        budget.open_run("new", "0.1", budget_mode="actual_usage")
