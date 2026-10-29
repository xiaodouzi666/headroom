"""One explicit gift-backed extension of an existing judge ledger.

An operator reviews provider evidence and the exact plan hash. Hashes provide
integrity, not bank verification or signatures. The reviewed local input estimate
remains an admission estimate, never a mathematical provider-bill upper bound.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime
from decimal import ROUND_FLOOR
from pathlib import Path

from headroom.acceptance.allocation import _budget_state, _quiet_pool, digest, hash64, require
from headroom.budget import money

EXTENSION_SCHEMA = "headroom.judge-access.credit-extension.v1"
AUTHORIZATION_SCOPE = "JUDGE_GIFT_CREDIT_EXTENSION"
EXTENSION_FILENAME = "credit-extension.json"
MAX_SNAPSHOT_AGE_SECONDS = 3600


def _binding():
    # Avoid a module cycle; the immutable base allocation remains the trust anchor.
    from headroom.acceptance import judge_binding

    return judge_binding


def _exact_keys(value, keys, reason):
    require(isinstance(value, dict) and set(value) == set(keys.split()), reason)


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 512


def _amount(value):
    require(isinstance(value, str), "JUDGE_CREDIT_AMOUNT_INVALID")
    return money(value)


def _observed_at(value):
    require(_text(value), "JUDGE_CREDIT_SNAPSHOT_TIME_INVALID")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        require(False, "JUDGE_CREDIT_SNAPSHOT_TIME_INVALID")
    require(result.tzinfo is not None, "JUDGE_CREDIT_SNAPSHOT_TIME_INVALID")
    return result


def prepare_judge_credit(base_receipt, credit_snapshot, authorization, *, project_root):
    """Pure preparation. Provider facts require independent operator review."""
    base = _binding()
    root = str(Path(project_root).resolve())
    require(
        isinstance(base_receipt, dict)
        and base_receipt.get("schema") == base.RECEIPT_SCHEMA
        and base_receipt.get("project_root") == root
        and base_receipt.get("amounts") == base.AMOUNTS
        and base_receipt.get("receipt_sha256")
        == digest({k: v for k, v in base_receipt.items() if k != "receipt_sha256"}),
        "JUDGE_CREDIT_BASE_CHANGED",
    )
    _exact_keys(
        credit_snapshot,
        "observed_at gift_balance_gross_usd reserve_gross_usd tax_factor "
        "unreflected_charge_reserve_gross_usd unreflected_charge_review "
        "other_commitments judge_charged_usd judge_accounting_sha256 evidence gift_only",
        "JUDGE_CREDIT_SNAPSHOT_INVALID",
    )
    _observed_at(credit_snapshot["observed_at"])
    require(credit_snapshot["gift_only"] is True, "JUDGE_CREDIT_GIFT_ONLY_REQUIRED")
    require(
        _text(credit_snapshot["unreflected_charge_review"]),
        "JUDGE_CREDIT_LAG_REVIEW_REQUIRED",
    )
    require(hash64(credit_snapshot["judge_accounting_sha256"]), "JUDGE_CREDIT_STATE_REQUIRED")
    balance = _amount(credit_snapshot["gift_balance_gross_usd"])
    reserve = _amount(credit_snapshot["reserve_gross_usd"])
    tax = _amount(credit_snapshot["tax_factor"])
    lag = _amount(credit_snapshot["unreflected_charge_reserve_gross_usd"])
    charged = _amount(credit_snapshot["judge_charged_usd"])
    require(reserve >= money("8"), "JUDGE_CREDIT_RESERVE_TOO_SMALL")
    require(tax == money(base_receipt["amounts"]["tax_factor"]), "JUDGE_CREDIT_TAX_CHANGED")
    require(charged <= money(base.AMOUNTS["approved_net_usd"]), "JUDGE_CREDIT_PRIOR_OVERRUN")
    others = credit_snapshot["other_commitments"]
    require(isinstance(others, list) and 0 < len(others) <= 32, "JUDGE_CREDIT_COMMITMENTS_REQUIRED")
    ids = set()
    other_gross = money("0")
    for item in others:
        _exact_keys(
            item,
            "allocation_id receipt_sha256 accounting_sha256 authorized_net_usd charged_net_usd remaining_net_usd tax_factor",
            "JUDGE_CREDIT_COMMITMENT_INVALID",
        )
        require(
            _text(item["allocation_id"])
            and item["allocation_id"] not in ids
            and item["allocation_id"] != base_receipt["allocation_id"]
            and hash64(item["receipt_sha256"])
            and hash64(item["accounting_sha256"]),
            "JUDGE_CREDIT_COMMITMENT_INVALID",
        )
        ids.add(item["allocation_id"])
        authorized = _amount(item["authorized_net_usd"])
        spent = _amount(item["charged_net_usd"])
        remaining = _amount(item["remaining_net_usd"])
        item_tax = _amount(item["tax_factor"])
        require(
            authorized > 0
            and spent <= authorized
            and remaining == authorized - spent
            and item_tax == tax,
            "JUDGE_CREDIT_COMMITMENT_AMOUNT_CHANGED",
        )
        other_gross += remaining * item_tax
    evidence = credit_snapshot["evidence"]
    require(
        isinstance(evidence, list) and 0 < len(evidence) <= 16, "JUDGE_CREDIT_EVIDENCE_REQUIRED"
    )
    paths = set()
    for record in evidence:
        _exact_keys(record, "path sha256", "JUDGE_CREDIT_EVIDENCE_INVALID")
        path = Path(record["path"]) if _text(record["path"]) else Path("/")
        require(
            path.is_absolute()
            and path.is_relative_to(Path(root) / ".cache")
            and ".." not in path.parts
            and path.suffix == ".json"
            and not any(part.startswith(".env") for part in path.parts)
            and str(path) not in paths
            and hash64(record["sha256"]),
            "JUDGE_CREDIT_EVIDENCE_INVALID",
        )
        paths.add(str(path))
    _exact_keys(
        authorization,
        "state scope approval_message_ref statement_sha256 credit_snapshot_sha256 gift_only no_topup no_overage preserve_reserve_gross_usd",
        "JUDGE_CREDIT_AUTHORIZATION_REQUIRED",
    )
    require(
        authorization["state"] == "authorized"
        and authorization["scope"] == AUTHORIZATION_SCOPE
        and _text(authorization["approval_message_ref"])
        and hash64(authorization["statement_sha256"])
        and authorization["credit_snapshot_sha256"] == digest(credit_snapshot)
        and all(authorization[key] is True for key in ("gift_only", "no_topup", "no_overage"))
        and _amount(authorization["preserve_reserve_gross_usd"]) == reserve,
        "JUDGE_CREDIT_AUTHORIZATION_REQUIRED",
    )
    future_gross = balance - reserve - other_gross - lag
    require(future_gross > 0, "JUDGE_CREDIT_NO_AVAILABLE_GIFTS")
    future_net = (future_gross / tax).quantize(money("0.01"), rounding=ROUND_FLOOR)
    cumulative = charged + future_net
    require(
        future_net > 0 and cumulative > money(base.AMOUNTS["approved_net_usd"]),
        "JUDGE_CREDIT_NOT_AN_EXTENSION",
    )
    plan = {
        "schema": EXTENSION_SCHEMA,
        "project_root": root,
        "base_receipt_sha256": base_receipt["receipt_sha256"],
        "allocation_id": base_receipt["allocation_id"],
        "profile_sha256": base_receipt["profile_sha256"],
        "ledger_identity": base_receipt["ledger_identity"],
        "claims_identity": base_receipt["claims_identity"],
        "expires_at": base.EXPIRES_AT,
        "admission_basis": base.ADMISSION_BASIS,
        "credit_snapshot": credit_snapshot,
        "authorization": authorization,
        "amounts": {
            "future_gross_usd": str(future_gross),
            "future_net_usd": str(future_net),
            "prior_charged_usd": str(charged),
            "total_limit_usd": str(cumulative),
            "daily_limit_usd": str(cumulative),
            "run_limit_usd": base.AMOUNTS["run_limit_usd"],
        },
    }
    # Return detached plain data; later caller mutation cannot affect original inputs.
    plan = json.loads(json.dumps(plan, allow_nan=False))
    return plan | {"extension_sha256": digest(plan)}


def judge_accounting_snapshot(receipt, *, connection=None):
    """Read-only digest of the existing judge history for operator preparation."""
    base = _binding()
    if connection is None:
        with base._claims(receipt) as conn:
            return judge_accounting_snapshot(receipt, connection=conn)
    base._clear_claims(connection)
    state = _budget_state(receipt)
    _quiet_pool(state)
    claims = [dict(row) for row in connection.execute("SELECT * FROM claims ORDER BY run_id")]
    document = {
        "runs": state["runs"],
        "attempts": sorted(state["attempts"], key=lambda row: row["id"]),
        "resolved_attempt_ids": sorted(state["resolved_attempt_ids"]),
        "claims": claims,
    }
    return {"judge_charged_usd": str(state["charged"]), "judge_accounting_sha256": digest(document)}


def _row(connection):
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='judge_credit_extension'"
    ).fetchone()
    if not exists:
        return None
    rows = connection.execute("SELECT * FROM judge_credit_extension").fetchall()
    require(len(rows) == 1, "JUDGE_CREDIT_REGISTRY_CHANGED")
    return rows[0]


def _evidence(plan):
    base = _binding()
    for record in plan["credit_snapshot"]["evidence"]:
        _, sha = base._private_json(Path(plan["project_root"]), Path(record["path"]))
        require(sha == record["sha256"], "JUDGE_CREDIT_EVIDENCE_CHANGED")


def read_judge_credit(receipt, *, connection=None):
    """Resolve the immutable extension, failing closed on partial/corrupt state."""
    base = _binding()
    path = Path(receipt["project_root"]) / ".cache/judge-access" / EXTENSION_FILENAME
    if connection is None:
        with closing(
            sqlite3.connect(Path(receipt["claims_path"]).as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.row_factory = sqlite3.Row
            return read_judge_credit(receipt, connection=conn)
    row = _row(connection)
    if row is None:
        require(not path.exists() and not path.is_symlink(), "JUDGE_CREDIT_PARTIAL_ACTIVATION")
        return None
    plan, file_sha = base._private_json(Path(receipt["project_root"]), path)
    checked = prepare_judge_credit(
        receipt,
        plan.get("credit_snapshot"),
        plan.get("authorization"),
        project_root=receipt["project_root"],
    )
    require(
        plan == checked
        and row["singleton"] == 1
        and row["extension_sha256"] == plan["extension_sha256"]
        and row["document_sha256"] == file_sha,
        "JUDGE_CREDIT_CHANGED",
    )
    _evidence(plan)
    return plan


def activate_judge_credit(plan, *, project_root, expected_sha256):
    """Explicit, once-only extension. No model, key, topup or existing-row mutation.

    The caller must independently review the exact hash and provider evidence.
    Activation requires an idle deployment; a partial file is retained and blocks
    use rather than silently reverting to a different allowance.
    """
    base = _binding()
    root, directory = base._paths(project_root)
    receipt = base.verify_judge_receipt(directory / "receipt.json", project_root=root)
    require(isinstance(plan, dict) and hash64(expected_sha256), "JUDGE_CREDIT_PLAN_REQUIRED")
    checked = prepare_judge_credit(
        receipt, plan.get("credit_snapshot"), plan.get("authorization"), project_root=root
    )
    require(
        plan == checked and plan["extension_sha256"] == expected_sha256, "JUDGE_CREDIT_PLAN_CHANGED"
    )
    age = (base._now() - _observed_at(plan["credit_snapshot"]["observed_at"])).total_seconds()
    require(0 <= age <= MAX_SNAPSHOT_AGE_SECONDS, "JUDGE_CREDIT_SNAPSHOT_STALE")
    _evidence(plan)
    with base._claims(receipt) as connection:
        require(
            read_judge_credit(receipt, connection=connection) is None,
            "JUDGE_CREDIT_ALREADY_EXTENDED",
        )
        accounting = judge_accounting_snapshot(receipt, connection=connection)
        require(
            all(accounting[key] == plan["credit_snapshot"][key] for key in accounting),
            "JUDGE_CREDIT_ACCOUNTING_CHANGED",
        )
        file_sha = base._write_new(directory / EXTENSION_FILENAME, plan)
        connection.execute(
            "CREATE TABLE judge_credit_extension (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
            "extension_sha256 TEXT NOT NULL, document_sha256 TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO judge_credit_extension VALUES (1,?,?)",
            (plan["extension_sha256"], file_sha),
        )
    return plan
