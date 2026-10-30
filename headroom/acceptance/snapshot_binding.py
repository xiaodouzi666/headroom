"""Private snapshot acceptance binding; HTTP input never selects a claim or budget."""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from headroom.acceptance.common import file_record
from headroom.api.security import open_regular
from headroom.budget import BudgetLedger, money

INPUT_LIMITS = {"snapshot": 50 * 1024 * 1024, "traceback": 256 * 1024, "source": 1024 * 1024}
PROTOCOL = "headroom.snapshot-feature-intent.v1"
_CONTEXT = ContextVar("headroom_snapshot_feature_binding", default=None)


def _record(path, limit):
    path = Path(path).absolute()
    if ".." in path.parts or any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Unsafe snapshot acceptance input")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Snapshot acceptance inputs must not follow symlinks")
    return file_record(path, limit)


def snapshot_intent(request, *, daily_budget_usd):
    """Hash actual bounded input bytes, not paths; server copies retain the same intent."""
    from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest

    request = SnapshotDiagnosisRequest.model_validate(request)
    if request.runtime_profile is None or money(daily_budget_usd) <= 0:
        raise ValueError("Snapshot acceptance requires a bound profile and daily allowance")
    inputs = {
        name: _record(value, limit) if (value := getattr(request, name)) is not None else None
        for name, limit in INPUT_LIMITS.items()
    }
    return {
        "kind": "snapshot_diagnosis",
        "runtime_profile": str(request.runtime_profile.absolute()),
        "budget_usd": str(money(request.budget_usd)),
        "daily_budget_usd": str(money(daily_budget_usd)),
        "payload": {"protocol": PROTOCOL, "inputs": inputs},
    }


def snapshot_budget_factory(binding, *, project_root=None):
    """Use normal live runtime with a receipt-bound ledger and a per-reserve file recheck."""
    from headroom.acceptance.feature_allocation import verify_feature_child_binding

    def factory(run_id, request, profile):
        def verify():
            intent = snapshot_intent(request, daily_budget_usd=binding["daily_limit_usd"])
            return verify_feature_child_binding(
                binding, intent=intent, run_id=run_id, project_root=project_root
            )

        verified = verify()
        if money(request.budget_usd) != money(verified.run_limit_usd) or money(
            verified.total_limit_usd
        ) > money(profile.authorized_total_usd):
            raise ValueError("Snapshot budget differs from the approved input intent")

        class BoundSnapshotLedger(BudgetLedger):
            def open_run(self, *args, **kwargs):
                verify()
                return super().open_run(*args, **kwargs)

            def reserve(self, *args, **kwargs):
                # A replaced upload, profile, receipt or ledger stops before transport.
                verify()
                return super().reserve(*args, **kwargs)

        database = verified.database
        return BoundSnapshotLedger(
            database.path,
            require_existing=True,
            expected_identity=database.file_identity,
            daily_limit=verified.daily_limit_usd,
            total_limit=verified.total_limit_usd,
        )

    return factory


@contextmanager
def snapshot_feature_context(binding, *, project_root=None):
    """Trusted CLI/worker bridge only; does not alter runtime provenance or grant approval."""
    if _CONTEXT.get() is not None:
        raise ValueError("Nested snapshot allocation contexts are not supported")
    token = _CONTEXT.set((binding, project_root))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def current_snapshot_budget_factory():
    context = _CONTEXT.get()
    if not context:
        return None
    binding, project_root = context
    if binding.get("snapshot_protocol") == "headroom.public-snapshot.judge.v1":
        from headroom.acceptance.snapshot_public_binding import snapshot_public_budget_factory

        return snapshot_public_budget_factory(binding, project_root=project_root)
    return snapshot_budget_factory(binding, project_root=project_root)


class SnapshotWebAllocation:
    """One private server-configured slot; uploads cannot choose scope, receipt or amount."""

    def __init__(self, parent, *, project_root):
        from headroom.acceptance.feature_allocation import verify_feature_parent

        verify_feature_parent(parent)
        if Path(parent["project_root"]).resolve() != Path(project_root).resolve():
            raise ValueError("Snapshot server and allocation project differ")
        if parent["scope"] != "F3b":
            raise ValueError("The snapshot web slot requires the F3b scope")
        self.parent = dict(parent)
        self.project_root = Path(project_root).resolve()
        self.profile_path = parent["profile_path"]
        self.daily_limit_usd = parent["daily_limit_usd"]

    def claim(self, request, run_id):
        from headroom.acceptance.feature_allocation import claim_feature_child

        return claim_feature_child(
            self.parent,
            slot_id="snapshot-web",
            intent=snapshot_intent(request, daily_budget_usd=self.daily_limit_usd),
            run_id=run_id,
        )

    @staticmethod
    def finish(binding, *, execution_terminal, cleanup_verified):
        from headroom.acceptance.feature_allocation import finish_feature_child

        return finish_feature_child(
            binding, execution_terminal=execution_terminal, cleanup_verified=cleanup_verified
        )


def load_snapshot_feature_binding(path, *, request, project_root):
    """Read a private CLI control file and verify its registered claim and actual inputs."""
    from headroom.acceptance.feature_allocation import verify_feature_child_binding

    path = Path(path).absolute()
    if ".." in path.parts or any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Unsafe snapshot binding path")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Snapshot binding must not follow symlinks")
    with open_regular(path.parent, path.name, 128 * 1024) as stream:
        info = os.fstat(stream.fileno())
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Snapshot binding must be private to the current user")
        binding = json.load(stream)
    if (
        not isinstance(binding, dict)
        or binding.get("scope") != "F3b"
        or binding.get("slot_id") not in {"snapshot-s2", "snapshot-nanogpt", "snapshot-web"}
        or not re.fullmatch(r"[a-f0-9]{32}", str(binding.get("run_id", "")))
    ):
        raise ValueError("Invalid snapshot feature binding")
    verify_feature_child_binding(
        binding,
        intent=snapshot_intent(request, daily_budget_usd=binding["daily_limit_usd"]),
        run_id=binding["run_id"],
        project_root=project_root,
    )
    return binding


def snapshot_cleanup_verified(run_root, run_id):
    """Read only the trusted private completion receipt, never a public success flag."""
    if not re.fullmatch(r"[a-f0-9]{32}", str(run_id)):
        return False
    path = Path(run_root).absolute() / run_id / "private" / "cleanup.json"
    try:
        if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)):
            return False
        with open_regular(path.parent, path.name, 4096) as stream:
            document = json.load(stream)
        return (
            document.get("schema") == "headroom.snapshot-cleanup.v1"
            and document.get("run_id") == run_id
            and document.get("cleanup_verified") is True
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False
