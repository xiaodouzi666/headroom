"""Receipt-bound FINAL48 feature slots using the existing shared budget ledger.

F3b's snapshots and Watch share one admission ceiling; F5 has a separate fixed
slot. Actual provider charges, unknown charges and cleanup remain authoritative.
No draft, intent hash or verification initializes a profile or budget database.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from headroom.acceptance.allocation import (
    LIMIT,
    AllocationRefused,
    VerifiedChildBinding,
    _budget_state,
    _checked_document,
    _cost_summary,
    _quiet_pool,
    _signed,
    digest,
    hash64,
    registry,
    require,
    verify_receipt,
)
from headroom.budget import money

GROUPS = {
    "F3b": {
        "cap": Decimal(1),
        "slots": {
            "snapshot-s2": ("snapshot_diagnosis", "F3b_snapshot"),
            "snapshot-nanogpt": ("snapshot_diagnosis", "F3b_snapshot"),
            "snapshot-web": ("snapshot_diagnosis", "F3b_snapshot"),
            "watch-s1": ("watch", "F3b_watch"),
        },
    },
    "F5": {"cap": Decimal("0.30"), "slots": {"clean-s3": ("fix", "F5")}},
}
CHILD_CAP = Decimal("0.30")
PARENT_SCHEMA = "headroom.final48.feature-parent.v1"
CHILD_SCHEMA = "headroom.final48.feature-child.v1"
VerifiedFeatureChild = VerifiedChildBinding


def validate_feature_plan(plan, *, approved):
    """Validate explicit group caps only when enabled; old F1/F3 plans stay usable."""
    caps = plan.get("feature_scope_caps_usd", {"F3b": None, "F5": None})
    require(isinstance(caps, dict) and set(caps) == set(GROUPS), "FEATURE_SCOPE_CAPS_REQUIRED")
    for scope, rule in GROUPS.items():
        cap = caps[scope]
        if cap is None:
            continue
        require(
            isinstance(cap, str) and 0 < money(cap) <= min(rule["cap"], approved),
            "FEATURE_SCOPE_LIMIT_EXCEEDED",
        )
        pins = plan.get("task_pins", {}).get(scope, {})
        require(
            hash64(pins.get("preparation_sha256")) and hash64(pins.get("slot_intents_sha256")),
            "FEATURE_REVIEWED_INPUT_REQUIRED",
        )
        for _, task_scope in rule["slots"].values():
            child_cap = plan.get("task_run_caps_usd", {}).get(task_scope)
            require(
                isinstance(child_cap, str) and 0 < money(child_cap) <= CHILD_CAP,
                "FEATURE_CHILD_CAP_REQUIRED",
            )
    return dict(caps)


def _json_value(value):
    if value is None or type(value) in (str, int, bool):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_value(item) for key, item in value.items())
    return False


def intent_sha256(intent):
    """Hash the complete canonical intent; callers must reconstruct it from real inputs."""
    require(
        type(intent) is dict
        and set(intent) == {"kind", "runtime_profile", "budget_usd", "daily_budget_usd", "payload"},
        "FEATURE_INTENT_REQUIRED",
    )
    require(
        intent["kind"] in {"snapshot_diagnosis", "watch", "fix"}
        and isinstance(intent["runtime_profile"], str)
        and isinstance(intent["budget_usd"], str)
        and isinstance(intent["daily_budget_usd"], str)
        and type(intent["payload"]) is dict
        and bool(intent["payload"])
        and _json_value(intent),
        "FEATURE_INTENT_INVALID",
    )
    require(len(json.dumps(intent).encode()) <= LIMIT, "FEATURE_INTENT_TOO_LARGE")
    require(
        0 < money(intent["budget_usd"]) <= CHILD_CAP and money(intent["daily_budget_usd"]) > 0,
        "FEATURE_INTENT_LIMIT_INVALID",
    )
    return digest(intent)


def verify_feature_parent(parent, *, environ=None, active=True):
    _checked_document(parent, PARENT_SCHEMA)
    require(parent.get("scope") in GROUPS, "FEATURE_SCOPE_INVALID")
    receipt = verify_receipt(
        parent["receipt_path"], project_root=parent["project_root"], environ=environ
    )
    require(receipt["receipt_sha256"] == parent["receipt_sha256"], "FEATURE_RECEIPT_CHANGED")
    with registry(parent["project_root"]) as conn:
        row = conn.execute(
            "SELECT * FROM feature_parents WHERE parent_id=?", (parent["parent_id"],)
        ).fetchone()
        claim = conn.execute(
            "SELECT * FROM claims WHERE task_scope=? AND execution_key='once'",
            (parent["scope"],),
        ).fetchone()
        require(
            row is not None
            and json.loads(row["payload"]) == parent
            and row["scope"] == parent["scope"]
            and claim is not None
            and claim["run_id"] == parent["parent_id"],
            "FEATURE_PARENT_NOT_REGISTERED",
        )
        if active:
            require(
                row["state"] == "claimed" and claim["state"] == "claimed",
                "FEATURE_PARENT_NOT_ACTIVE",
            )
    return receipt


def _quiet_registry(conn, *, allowed_run=None):
    # Cleanup uncertainty must not be escaped by switching from F3b to F5.
    for table in ("feature_children", "f3_children"):
        row = conn.execute(
            f"SELECT run_id FROM {table} WHERE state!='settled' "
            "AND (? IS NULL OR run_id!=?) LIMIT 1",
            (allowed_run, allowed_run),
        ).fetchone()
        require(row is None, "FEATURE_OTHER_CHILD_UNSETTLED")


def claim_feature_parent(
    receipt_path,
    *,
    project_root,
    scope,
    preparation_sha256,
    slot_intents,
    scope_limit_usd=None,
):
    require(scope in GROUPS, "FEATURE_SCOPE_INVALID")
    rule = GROUPS[scope]
    receipt = verify_receipt(receipt_path, project_root=project_root)
    approved = receipt.get("feature_scope_caps_usd", {}).get(scope)
    require(approved is not None, "FEATURE_SCOPE_NOT_AUTHORIZED")
    cap = money(approved if scope_limit_usd is None else scope_limit_usd)
    require(0 < cap <= min(money(approved), rule["cap"]), "FEATURE_SCOPE_LIMIT_EXCEEDED")
    require(
        isinstance(slot_intents, dict)
        and set(slot_intents) == set(rule["slots"])
        and all(hash64(value) for value in slot_intents.values()),
        "FEATURE_FIXED_SLOTS_REQUIRED",
    )
    pins = receipt.get("task_pins", {}).get(scope, {})
    require(
        hash64(preparation_sha256)
        and preparation_sha256 == pins.get("preparation_sha256")
        and digest(slot_intents) == pins.get("slot_intents_sha256"),
        "FEATURE_INPUT_BINDING_CHANGED",
    )
    with registry(project_root) as conn:
        _quiet_registry(conn)
        state = _budget_state(receipt)
        _quiet_pool(state)
        ceiling = min(money(receipt["amounts"]["approved_net_usd"]), state["charged"] + cap)
        require(ceiling > state["charged"], "FEATURE_SCOPE_EXHAUSTED")
        parent_id = uuid4().hex
        parent = _signed(
            {
                "schema": PARENT_SCHEMA,
                "scope": scope,
                "parent_id": parent_id,
                "project_root": str(Path(project_root).resolve()),
                "receipt_path": str(Path(receipt_path)),
                "receipt_sha256": receipt["receipt_sha256"],
                "allocation_id": receipt["allocation_id"],
                "profile_path": receipt["profile_path"],
                "daily_limit_usd": receipt["amounts"]["daily_limit_usd"],
                "preparation_sha256": preparation_sha256,
                "slot_intents": dict(slot_intents),
                "slot_intents_sha256": digest(slot_intents),
                "scope_limit_usd": str(cap),
                "prior_charged_usd": str(state["charged"]),
                "total_limit_usd": str(ceiling),
            }
        )
        try:
            conn.execute(
                "INSERT INTO claims VALUES(?,'once',?,?,NULL,'claimed')",
                (scope, parent_id, preparation_sha256),
            )
            conn.execute(
                "INSERT INTO feature_parents VALUES(?,?,?,'claimed')",
                (parent_id, scope, json.dumps(parent, sort_keys=True)),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("ALLOCATION_EXECUTION_ALREADY_CLAIMED") from None
    return parent


def _check_intent(receipt, parent, slot_id, intent):
    spec = GROUPS[parent["scope"]]["slots"].get(slot_id)
    require(spec is not None, "FEATURE_SLOT_NOT_AUTHORIZED")
    intent_hash = intent_sha256(intent)
    require(
        parent["slot_intents"].get(slot_id) == intent_hash and intent["kind"] == spec[0],
        "FEATURE_CHILD_INTENT_CHANGED",
    )
    require(intent["runtime_profile"] == receipt["profile_path"], "FEATURE_CHILD_PROFILE_CHANGED")
    require(
        money(intent["daily_budget_usd"]) == money(receipt["amounts"]["daily_limit_usd"]),
        "FEATURE_DAILY_LIMIT_CHANGED",
    )
    task_cap = receipt["task_run_caps_usd"].get(spec[1])
    require(
        task_cap is not None and money(intent["budget_usd"]) <= money(task_cap),
        "FEATURE_CHILD_CAP_EXCEEDED",
    )
    return intent_hash


def claim_feature_child(parent, *, slot_id, intent, run_id):
    receipt = verify_feature_parent(parent)
    intent_hash = _check_intent(receipt, parent, slot_id, intent)
    require(
        isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id),
        "FEATURE_CHILD_RUN_ID_INVALID",
    )
    with registry(parent["project_root"]) as conn:
        row = conn.execute(
            "SELECT state FROM feature_parents WHERE parent_id=?", (parent["parent_id"],)
        ).fetchone()
        require(row and row["state"] == "claimed", "FEATURE_PARENT_NOT_ACTIVE")
        require(
            conn.execute(
                "SELECT 1 FROM feature_children WHERE parent_id=? AND state!='settled'",
                (parent["parent_id"],),
            ).fetchone()
            is None,
            "FEATURE_PREVIOUS_CHILD_UNSETTLED",
        )
        _quiet_registry(conn)
        state = _budget_state(receipt)
        _quiet_pool(state)
        require(run_id not in state["runs"], "FEATURE_CHILD_RUN_ALREADY_EXISTS")
        require(
            state["charged"] + money(intent["budget_usd"]) <= money(parent["total_limit_usd"]),
            "FEATURE_SCOPE_EXHAUSTED",
        )
        binding = _signed(
            {
                "schema": CHILD_SCHEMA,
                "scope": parent["scope"],
                "parent_id": parent["parent_id"],
                "parent_binding_sha256": parent["binding_sha256"],
                "preparation_sha256": parent["preparation_sha256"],
                "slot_id": slot_id,
                "run_id": run_id,
                "intent_sha256": intent_hash,
                "project_root": parent["project_root"],
                "receipt_path": parent["receipt_path"],
                "receipt_sha256": parent["receipt_sha256"],
                "run_limit_usd": str(money(intent["budget_usd"])),
                "daily_limit_usd": str(money(intent["daily_budget_usd"])),
                "total_limit_usd": parent["total_limit_usd"],
            }
        )
        try:
            conn.execute(
                "INSERT INTO feature_children VALUES(?,?,?,?,'claimed',NULL)",
                (run_id, parent["parent_id"], slot_id, json.dumps(binding, sort_keys=True)),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("FEATURE_CHILD_ALREADY_CLAIMED") from None
    return binding


def _child_record(binding, *, active=True, environ=None):
    _checked_document(binding, CHILD_SCHEMA)
    require(binding.get("scope") in GROUPS, "FEATURE_SCOPE_INVALID")
    receipt = verify_receipt(
        binding["receipt_path"], project_root=binding["project_root"], environ=environ
    )
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "FEATURE_RECEIPT_CHANGED")
    with registry(binding["project_root"]) as conn:
        child = conn.execute(
            "SELECT * FROM feature_children WHERE run_id=?", (binding["run_id"],)
        ).fetchone()
        parent = conn.execute(
            "SELECT * FROM feature_parents WHERE parent_id=?", (binding["parent_id"],)
        ).fetchone()
        require(
            child is not None and json.loads(child["payload"]) == binding and parent is not None,
            "FEATURE_CHILD_NOT_REGISTERED",
        )
        document = json.loads(parent["payload"])
        require(
            document["binding_sha256"] == binding["parent_binding_sha256"]
            and parent["scope"] == binding["scope"],
            "FEATURE_PARENT_BINDING_CHANGED",
        )
        if active:
            require(
                child["state"] == "claimed" and parent["state"] == "claimed",
                "FEATURE_CHILD_NOT_ACTIVE",
            )
            _quiet_registry(conn, allowed_run=binding["run_id"])
    return receipt, document


def verify_feature_child_binding(
    binding,
    *,
    intent,
    run_id,
    project_root=None,
    environ=None,
):
    receipt, parent = _child_record(binding, environ=environ)
    require(run_id == binding["run_id"], "FEATURE_CHILD_RUN_CHANGED")
    require(
        project_root is None or str(Path(project_root).resolve()) == binding["project_root"],
        "FEATURE_CHILD_PROJECT_CHANGED",
    )
    require(
        _check_intent(receipt, parent, binding["slot_id"], intent) == binding["intent_sha256"],
        "FEATURE_CHILD_INTENT_CHANGED",
    )
    state = _budget_state(receipt)
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    if run:
        require(
            run["status"] == "open"
            and run["budget_mode"] == "strict_reservation"
            and money(run["limit_usd"]) <= money(binding["run_limit_usd"]),
            "FEATURE_CHILD_LEDGER_LIMIT_CHANGED",
        )
    require(state["charged"] < money(binding["total_limit_usd"]), "FEATURE_SCOPE_EXHAUSTED")
    return VerifiedFeatureChild(
        receipt,
        run_id,
        binding["run_limit_usd"],
        binding["daily_limit_usd"],
        binding["total_limit_usd"],
    )


def feature_accounting(parent):
    receipt = verify_feature_parent(parent, active=False)
    state = _budget_state(receipt)
    with registry(parent["project_root"]) as conn:
        parent_state = conn.execute(
            "SELECT state FROM feature_parents WHERE parent_id=?", (parent["parent_id"],)
        ).fetchone()["state"]
        children = [
            dict(row)
            for row in conn.execute(
                "SELECT run_id,slot_id,state,settlement FROM feature_children WHERE parent_id=?",
                (parent["parent_id"],),
            )
        ]
    child_ids = {row["run_id"] for row in children}
    own = [row for row in state["attempts"] if row["run_id"] in child_ids]
    cost = _cost_summary(state, own)
    known, actual = cost["known"], cost["actual"]
    blocked = (
        not cost["resolved"]
        or not state["resolved"]
        or any(row["halt_reason"] for row in state["runs"].values())
        or any(row["state"] == "blocked" for row in children)
        or state["charged"] > money(parent["total_limit_usd"])
        or parent_state not in {"claimed", "completed"}
    )
    all_settled = len(children) == len(GROUPS[parent["scope"]]["slots"]) and all(
        row["state"] == "settled" for row in children
    )
    return {
        "status": "blocked" if blocked else "settled" if all_settled else "active",
        "parent_status": parent_state,
        "parent_id": parent["parent_id"],
        "scope": parent["scope"],
        "scope_spent_usd": str(actual) if actual is not None else None,
        "scope_charged_usd": str(cost["charged"]),
        "all_costs_resolved": cost["resolved"] and state["resolved"],
        "scope_limit_usd": parent["scope_limit_usd"],
        "total_limit_usd": parent["total_limit_usd"],
        "new_pool_charged_usd": str(state["charged"]),
        "all_costs_known": known and state["known"],
        "children": children,
    }


def finish_feature_child(binding, *, execution_terminal, cleanup_verified):
    receipt, parent = _child_record(binding)
    with registry(binding["project_root"]) as conn:
        row = conn.execute(
            "SELECT state FROM feature_children WHERE run_id=?", (binding["run_id"],)
        ).fetchone()
        require(row and row["state"] == "claimed", "FEATURE_CHILD_NOT_ACTIVE")
        state = _budget_state(receipt)
        own = [row for row in state["attempts"] if row["run_id"] == binding["run_id"]]
        cost = _cost_summary(state, own)
        known, actual = cost["known"], cost["actual"]
        settled = (
            execution_terminal is True
            and cleanup_verified is True
            and cost["resolved"]
            and state["resolved"]
            and all(
                row["status"] == "closed" and not row["halt_reason"]
                for row in state["runs"].values()
            )
            and cost["charged"] <= money(binding["run_limit_usd"])
            and state["charged"] <= money(binding["total_limit_usd"])
        )
        result = {
            "status": "settled" if settled else "blocked",
            "actual_usd": str(actual) if actual is not None else None,
            "charged_usd": str(cost["charged"]),
            "cost_resolved": cost["resolved"],
            "cost_basis": "exact"
            if known
            else "conservative_bound"
            if cost["resolved"]
            else "unresolved",
        }
        conn.execute(
            "UPDATE feature_children SET state=?,settlement=? WHERE run_id=?",
            (result["status"], json.dumps(result, sort_keys=True), binding["run_id"]),
        )
    return result | {"scope_spent_usd": feature_accounting(parent)["scope_spent_usd"]}


def finish_feature_parent(parent, *, status):
    verify_feature_parent(parent)
    require(
        status in {"completed", "failed", "blocked", "stopped"},
        "FEATURE_PARENT_STATUS_INVALID",
    )
    with registry(parent["project_root"]) as conn:
        if status == "completed":
            children = conn.execute(
                "SELECT state FROM feature_children WHERE parent_id=?", (parent["parent_id"],)
            ).fetchall()
            require(
                len(children) == len(GROUPS[parent["scope"]]["slots"])
                and all(row["state"] == "settled" for row in children),
                "FEATURE_NOT_COMPLETE",
            )
        conn.execute(
            "UPDATE feature_parents SET state=? WHERE parent_id=?",
            (status, parent["parent_id"]),
        )
        conn.execute("UPDATE claims SET state=? WHERE run_id=?", (status, parent["parent_id"]))
