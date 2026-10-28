"""Receipt-bound fixed Watch acceptance; preparation never executes source."""

import hashlib
import json
import os
import stat
from pathlib import Path

from headroom.acceptance.feature_allocation import intent_sha256, verify_feature_child_binding
from headroom.budget import BudgetLedger, money
from headroom.execution import PYTHON_COMMANDS
from headroom.lab.runner import MAX_SOURCE_BYTES, MAX_SOURCE_FILES, _excluded, read_artifact_json
from headroom.orchestrator import FixRequest, Services, run_fix
from headroom.watch import FIX_OPTIONS, _command, _cuda_oom, watch_command


def _source_files(root):
    root = Path(root).resolve(strict=True)
    files, total = {}, 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        current = Path(directory)
        dirs[:] = sorted(n for n in dirs if not _excluded(n) and not (current / n).is_symlink())
        for name in sorted(names):
            path = current / name
            if _excluded(name) or path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                continue
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("Watch source escapes its root")
            digest, size = hashlib.sha256(), 0
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError("Watch source changed to a nonregular file")
                while chunk := handle.read(1024 * 1024):
                    size += len(chunk)
                    if total + size > MAX_SOURCE_BYTES:
                        raise ValueError("Watch source exceeds the Lab copy bound")
                    digest.update(chunk)
            if len(files) >= MAX_SOURCE_FILES:
                raise ValueError("Watch source exceeds the Lab file bound")
            files[str(path.relative_to(root))] = {"sha256": digest.hexdigest(), "bytes": size}
            total += size
    return files


def prepare_watch_intent(
    command,
    *,
    source_root,
    device="cuda",
    max_steps=20,
    max_seconds=120,
    seed=1337,
    fix_options=None,
):
    """Freeze mapped Python argv, complete request and the same files Lab copies."""
    source, parsed = _command(command, source_root)
    if not parsed.repair_supported or parsed.kind not in {"python_script", "python_module"}:
        raise ValueError("Fixed Watch acceptance needs one directly mapped Python entrypoint")
    options = dict(fix_options or {})
    if set(options) - FIX_OPTIONS:
        raise ValueError("Unsupported Watch fix option")
    request = FixRequest(
        script=str(source / parsed.script),
        source_root=str(source),
        script_args=list(parsed.script_args),
        execution_argv=list(parsed.argv),
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        **options,
    )
    return {
        "kind": "watch",
        "runtime_profile": request.runtime_profile,
        "budget_usd": request.budget_usd,
        "daily_budget_usd": request.daily_budget_usd,
        "payload": {
            "command": list(command),
            "queued_request": request.model_dump(mode="json"),
            "source_files": _source_files(source),
        },
    }


def run_bound_watch(
    command,
    *,
    intent,
    allocation_child_binding,
    source_root,
    run_root=None,
    device="cuda",
    max_steps=20,
    max_seconds=120,
    seed=1337,
    fix_options=None,
    lab_runner=None,
):
    """Capture once, then use normal run_fix accounting for the assigned repair run."""
    rebuilt = prepare_watch_intent(
        command,
        source_root=source_root,
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        fix_options=fix_options,
    )
    if intent_sha256(rebuilt) != intent_sha256(intent):
        raise ValueError("Watch request or source differs from its approved intent")
    binding = allocation_child_binding
    run_id = binding["run_id"]
    if binding.get("scope") != "F3b" or binding.get("slot_id") != "watch-s1":
        raise ValueError("Bound Watch requires the fixed watch-s1 slot")
    expected = FixRequest.model_validate(intent["payload"]["queued_request"])
    if (
        Path(expected.script)
        != Path(binding["project_root"]) / "scenarios/s1_batch_too_big/train.py"
    ):
        raise ValueError("Bound Watch requires the fixed s1 source")
    verify_feature_child_binding(binding, intent=intent, run_id=run_id)
    bound_root = Path(binding["project_root"]) / "runs/watch"
    if bound_root.resolve() != bound_root or (
        run_root is not None and Path(run_root).resolve() != bound_root
    ):
        raise ValueError("Bound Watch uses its assigned project run root")

    def verify_capture(request):
        capture = Path(request.source_root).parent
        manifest = read_artifact_json(capture / "manifest.json")
        result = read_artifact_json(capture / "result.json")
        normalized = list(command)
        if normalized[0] in PYTHON_COMMANDS:
            normalized[0] = "/opt/venv/bin/python"
        if (
            manifest.get("command") != normalized
            or manifest.get("source_root") != expected.source_root
            or manifest.get("source", {}).get("files") != intent["payload"]["source_files"]
            or _source_files(request.source_root) != intent["payload"]["source_files"]
            or not _cuda_oom(result, device)
            or any(
                manifest.get(k) != getattr(expected, k)
                for k in ("device", "max_steps", "max_seconds", "seed")
            )
        ):
            raise ValueError("Captured Watch command, source or cleanup differs from intent")
        rebased = request.model_dump(mode="json")
        rebased["script"] = expected.script
        rebased["source_root"] = expected.source_root
        if rebased != expected.model_dump(mode="json"):
            raise ValueError("Captured repair request changed approved controls")
        return result

    def repair(request, *, run_root):
        captured = verify_capture(request)
        verify_feature_child_binding(binding, intent=intent, run_id=run_id)

        class BoundLedger(BudgetLedger):
            def reserve(self, *args, **kwargs):
                verify_feature_child_binding(binding, intent=intent, run_id=run_id)
                verify_capture(request)
                return super().reserve(*args, **kwargs)

        def budget_factory(actual_run_id, actual_request, profile):
            verified = verify_feature_child_binding(binding, intent=intent, run_id=actual_run_id)
            if (
                actual_run_id != run_id
                or money(actual_request.budget_usd) != money(verified.run_limit_usd)
                or money(actual_request.daily_budget_usd) != money(verified.daily_limit_usd)
                or money(verified.total_limit_usd) > money(profile.authorized_total_usd)
            ):
                raise ValueError("Bound Watch limits differ from receipt")
            database = verified.database
            return BoundLedger(
                database.path,
                require_existing=True,
                expected_identity=database.file_identity,
                daily_limit=verified.daily_limit_usd,
                total_limit=verified.total_limit_usd,
            )

        directory = Path(run_root)
        directory.mkdir(parents=True, exist_ok=True)
        audit = {
            "provenance": "watch-capture-binding",
            "run_id": run_id,
            "intent_sha256": intent_sha256(intent),
            "binding_sha256": binding["binding_sha256"],
            "capture_run_id": captured.get("run_id"),
            "cleanup_verified": True,
            "actual_request_sha256": hashlib.sha256(
                json.dumps(
                    request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
        }
        (directory / "allocation-binding.json").write_text(json.dumps(audit, indent=2) + "\n")
        return run_fix(
            request,
            run_root=directory,
            run_id=run_id,
            services=Services(budget_factory=budget_factory),
        )

    return watch_command(
        command,
        source_root=source_root,
        run_root=bound_root,
        watch_id=run_id,
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        fix_options=fix_options,
        lab_runner=lab_runner,
        fix_runner=repair,
    )


def load_watch_feature_context(
    path,
    *,
    command,
    source_root,
    device="cuda",
    max_steps=20,
    max_seconds=120,
    seed=1337,
    fix_options=None,
):
    """Read only an owner-private bounded context and validate before any Lab work."""
    from headroom.cli_execution import _read

    document = json.loads(_read(Path(path), 1024 * 1024, private=True))
    if not isinstance(document, dict) or set(document) != {"binding", "intent"}:
        raise ValueError("Watch context must contain only binding and intent")
    binding, intent = document["binding"], document["intent"]
    rebuilt = prepare_watch_intent(
        command,
        source_root=source_root,
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        fix_options=fix_options,
    )
    if intent_sha256(rebuilt) != intent_sha256(intent):
        raise ValueError("Watch context differs from the requested command or source")
    if binding.get("scope") != "F3b" or binding.get("slot_id") != "watch-s1":
        raise ValueError("Watch context requires the fixed watch-s1 slot")
    expected = FixRequest.model_validate(intent["payload"]["queued_request"])
    if (
        Path(expected.script)
        != Path(binding["project_root"]) / "scenarios/s1_batch_too_big/train.py"
    ):
        raise ValueError("Watch context requires the fixed s1 source")
    verify_feature_child_binding(binding, intent=intent, run_id=binding["run_id"])
    return binding, intent
