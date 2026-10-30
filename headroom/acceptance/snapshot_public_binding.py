"""Snapshot-only claims in the existing server-owned judge allocation.

No training FixRequest is fabricated. Uploaded bytes are bound by size and hash;
the shared judge claims transaction excludes ordinary repair jobs. This module
never bootstraps funding, reads credentials or selects a pool from HTTP fields.
"""

import json
import re
import sqlite3
from pathlib import Path

from headroom.acceptance import judge_binding as judge
from headroom.acceptance.allocation import (
    AllocationRefused,
    _budget_state,
    _quiet_pool,
    digest,
    require,
)
from headroom.acceptance.snapshot_binding import snapshot_intent
from headroom.budget import BudgetLedger, money
from headroom.runtime import read_live_profile
from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest

PROTOCOL = "headroom.public-snapshot.judge.v1"


def _snapshot_binding(binding):
    require(
        isinstance(binding, dict)
        and binding.get("schema") == judge.PERIOD_SCHEMA
        and binding.get("kind") == "snapshot_diagnosis"
        and binding.get("snapshot_protocol") == PROTOCOL
        and isinstance(binding.get("snapshot_intent"), dict)
        and binding.get("request_sha256") == digest(binding["snapshot_intent"]),
        "SNAPSHOT_JUDGE_BINDING_CHANGED",
    )


class SnapshotPublicAllocation:
    def __init__(self, judge_allocation, *, project_root):
        require(
            isinstance(judge_allocation, judge.JudgeAllocation), "SNAPSHOT_JUDGE_OWNER_REQUIRED"
        )
        self.project_root = Path(project_root).resolve()
        require(judge_allocation.root == self.project_root, "SNAPSHOT_JUDGE_ROOT_CHANGED")
        self.owner = judge_allocation

    @property
    def profile_path(self):
        return self.owner._receipt(active=False)["profile_path"]

    @property
    def daily_limit_usd(self):
        return self.owner.effective_daily_limit_usd

    @property
    def available(self):
        return self.owner.available

    def claim(self, request, run_id):
        request = SnapshotDiagnosisRequest.model_validate(request)
        require(re.fullmatch(r"[a-f0-9]{32}", str(run_id)) is not None, "JUDGE_RUN_INVALID")
        receipt = self.owner._receipt()
        require(
            request.runtime_profile is not None
            and str(request.runtime_profile.absolute()) == receipt["profile_path"],
            "SNAPSHOT_JUDGE_PROFILE_CHANGED",
        )
        with judge._claims(receipt) as connection:
            judge._clear_claims(connection)
            limits = judge._funding_limits(receipt, connection=connection)
            require(
                0 < money(request.budget_usd) <= money(limits["run_limit_usd"]),
                "SNAPSHOT_JUDGE_LIMIT_CHANGED",
            )
            state = _budget_state(receipt)
            _quiet_pool(state)
            cap = min(
                money(request.budget_usd),
                money(limits["total_limit_usd"]) - state["charged"],
            )
            require(cap > 0, "JUDGE_EXHAUSTED")
            effective_request = request.model_copy(update={"budget_usd": str(cap)})
            intent = snapshot_intent(effective_request, daily_budget_usd=limits["daily_limit_usd"])
            binding = {
                "schema": judge.PERIOD_SCHEMA,
                "kind": "snapshot_diagnosis",
                "snapshot_protocol": PROTOCOL,
                "project_root": str(self.project_root),
                "receipt_path": str(self.owner.receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
                "run_id": run_id,
                "snapshot_intent": intent,
                "request_sha256": digest(intent),
                "run_limit_usd": str(cap),
                "daily_limit_usd": limits["daily_limit_usd"],
                "total_limit_usd": limits["total_limit_usd"],
                "expires_at": judge.EFFECTIVE_EXPIRES_AT,
                "judging_period_policy": judge.JUDGING_PERIOD_POLICY,
            }
            if limits["credit_extension_sha256"]:
                binding["credit_extension_sha256"] = limits["credit_extension_sha256"]
            binding["binding_sha256"] = digest(binding)
            try:
                connection.execute(
                    "INSERT INTO claims VALUES (?,?,'claimed',NULL)",
                    (run_id, json.dumps(binding, sort_keys=True)),
                )
            except sqlite3.IntegrityError:
                raise AllocationRefused("JUDGE_ALREADY_CLAIMED") from None
        return binding

    def finish(self, binding, *, execution_terminal, cleanup_verified):
        # Input files may have been removed by trusted cleanup. Settlement checks
        # registered binding/history and costs, not the continued presence of input.
        _snapshot_binding(binding)
        return self.owner.finish(
            binding, execution_terminal=execution_terminal, cleanup_verified=cleanup_verified
        )


def verify_snapshot_public_binding(
    binding, request, run_id, *, project_root=None, pending_attempt_id=None
):
    _snapshot_binding(binding)
    request = SnapshotDiagnosisRequest.model_validate(request)
    if project_root is not None:
        require(
            str(Path(project_root).resolve()) == binding["project_root"],
            "SNAPSHOT_JUDGE_ROOT_CHANGED",
        )
    receipt = judge.verify_judge_receipt(
        binding["receipt_path"], project_root=binding["project_root"]
    )
    judge._validate_binding(binding, receipt, run_id)
    judge._active(binding["expires_at"])
    intent = snapshot_intent(request, daily_budget_usd=binding["daily_limit_usd"])
    require(
        intent == binding["snapshot_intent"]
        and digest(intent) == binding["request_sha256"]
        and intent["runtime_profile"] == receipt["profile_path"]
        and money(request.budget_usd) == money(binding["run_limit_usd"]),
        "SNAPSHOT_JUDGE_INPUT_CHANGED",
    )
    with judge._claims(receipt) as connection:
        judge._active_claim(connection, binding)
        judge._clear_claims(connection, run_id)
    state = _budget_state(receipt)
    if pending_attempt_id is not None:
        pending = [row for row in state["attempts"] if row["id"] == pending_attempt_id]
        require(
            len(pending) == 1
            and pending[0]["run_id"] == run_id
            and pending[0]["dispatched"] == 0
            and pending[0]["settled"] == 0,
            "JUDGE_PENDING_ATTEMPT_CHANGED",
        )
        state["resolved"] = all(
            row["id"] == pending_attempt_id or row["id"] in state["resolved_attempt_ids"]
            for row in state["attempts"]
        )
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    require(
        run is None
        or (
            money(run["limit_usd"]) == money(binding["run_limit_usd"])
            and run["budget_mode"] == "strict_reservation"
        ),
        "JUDGE_RUN_LIMIT_CHANGED",
    )
    return receipt


def snapshot_public_budget_factory(binding, *, project_root=None):
    """Normal live runtime with the same cumulative judge funding and strict admitted request limit."""
    _snapshot_binding(binding)

    def factory(run_id, request, profile):
        def verify(*, pending_attempt_id=None):
            return verify_snapshot_public_binding(
                binding,
                request,
                run_id,
                project_root=project_root,
                pending_attempt_id=pending_attempt_id,
            )

        receipt = verify()
        require(
            profile.model_dump(mode="json")
            == read_live_profile(receipt["profile_path"]).model_dump(mode="json"),
            "JUDGE_PROFILE_CHANGED",
        )

        class BoundSnapshotLedger(BudgetLedger):
            def open_run(self, own_run_id, run_limit, *, budget_mode="strict_reservation"):
                require(
                    own_run_id == run_id
                    and money(run_limit) == money(binding["run_limit_usd"])
                    and budget_mode == "strict_reservation",
                    "JUDGE_RUN_LIMIT_CHANGED",
                )
                verify()
                return super().open_run(own_run_id, run_limit, budget_mode=budget_mode)

            def reserve(self, own_run_id, *args, **kwargs):
                require(own_run_id == run_id, "JUDGE_RUN_CHANGED")
                verify()
                return super().reserve(own_run_id, *args, **kwargs)

            def mark_dispatched(self, own_run_id, attempt_id):
                require(own_run_id == run_id, "JUDGE_RUN_CHANGED")
                verify(pending_attempt_id=attempt_id)
                return super().mark_dispatched(own_run_id, attempt_id)

        return judge._ledger(receipt, binding, BoundSnapshotLedger)

    return factory
