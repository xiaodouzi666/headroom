"""Private, single-use bridge from the evaluation supervisor to the real CLI.

No runtime is built here. The CLI parses its own argv, then dispatches run_fix
once using the existing case identity, Store and normal evaluation Services.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import sys
import time
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from headroom.diagnosis_protocol import StudyProtocol

ENVIRONMENT_KEY = "HEADROOM_EVALUATION_CONTEXT"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MAX_CONTEXT_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _read(path, limit, *, private=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("CLI control input must be a bounded regular file")
        if private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("CLI control input must be private to the current user")
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("CLI control input grew beyond its bound")
    return raw


def digest(path, limit=MAX_SOURCE_BYTES):
    return hashlib.sha256(_read(Path(path), limit)).hexdigest()


def _write(path, value, *, replace=False):
    raw = (_json(value) + "\n").encode()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("CLI result exceeds its artifact bound")
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid4().hex) if replace else path
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
        if replace:
            temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class RepositoryInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: str
    ref: str
    command: list[str]
    destination: str


class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(default=1, ge=1, le=1)
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    request: dict
    queued_request: dict
    store_path: str
    run_root: str
    audit_dir: str
    result_path: str
    deadline: float = Field(allow_inf_nan=False)
    condition: str
    study_protocol: StudyProtocol | None = None
    argv: list[str]
    package_root: str
    console_path: str
    console_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository: RepositoryInvocation | None = None


def cli_arguments(request, repository=None):
    """Explicit manifest arguments: ambient YAML cannot silently change this run."""
    args = ["fix"]
    if repository is not None:
        args += [
            "--repo",
            repository.repository,
            "--ref",
            repository.ref,
            "--cmd",
            shlex.join(repository.command),
        ]
    elif request.repository_mode:
        args += ["--source-root", request.source_root, "--cmd", shlex.join(request.execution_argv)]
    else:
        args += [
            request.script,
            "--source-root",
            request.source_root or str(Path(request.script).parent),
        ]
    for name, value in (
        ("target", request.target),
        ("reclaim-reduction-pct", request.reclaim_reduction_pct),
        ("max-throughput-regression-pct", request.policy.max_throughput_regression_pct),
        ("max-steps", request.max_steps),
        ("max-seconds", request.max_seconds),
        ("budget", request.budget_usd),
        ("daily-budget", request.daily_budget_usd),
        ("device", request.device),
        ("seed", request.seed),
        ("max-rounds", request.max_rounds),
        ("search-mode", request.search_mode),
        ("allocator-conf", request.allocator_conf or ""),
        ("reference-strategy", request.numerical_reference.strategy),
        ("reference-cpu-bytes", request.numerical_reference.cpu_saved_tensor_limit_bytes),
        ("reference-disk-bytes", request.numerical_reference.disk_saved_tensor_limit_bytes),
        ("reference-max-seconds", request.numerical_reference.max_seconds or 0),
    ):
        args += ["--" + name, str(value)]
    for name, value in (
        ("allow-numerics-change", request.policy.allow_numerics_change),
        ("allow-batch-grad-accum", request.policy.allow_batch_grad_accum),
        ("research", request.research_enabled),
    ):
        args.append("--" + ("" if value else "no-") + name)
    if request.runtime_profile is not None:
        args += ["--runtime-profile", request.runtime_profile]
    if repository is None and not request.repository_mode:
        args += ["--", *request.script_args] if request.script_args else []
    return args


def launch(invocation):
    """Replace this owned worker with the installed console script, never a second run."""
    invocation = Invocation.model_validate(invocation)
    directory = Path(invocation.run_root).parent
    path = directory / ("cli-context-" + invocation.run_id + ".json")
    _write(path, invocation.model_dump())
    environment = dict(os.environ)
    environment[ENVIRONMENT_KEY] = str(path)
    # The installed stub may live in a shared venv; bind its imports to this checkout.
    environment["PYTHONPATH"] = str(PACKAGE_ROOT) + os.pathsep + environment.get("PYTHONPATH", "")
    output = []
    try:
        for fd, suffix in ((1, "stdout"), (2, "stderr")):
            target = directory / ("cli-" + invocation.run_id + "." + suffix + ".log")
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            output.append((fd, os.dup(fd)))
            os.dup2(descriptor, fd)
            os.close(descriptor)
        os.execve(invocation.console_path, [invocation.console_path, *invocation.argv], environment)
    finally:
        # Only reached when exec fails (or an offline test intercepts it).
        for fd, saved in output:
            os.dup2(saved, fd)
            os.close(saved)


def console_script():
    path = Path(sys.executable).parent / "headroom"
    raw = _read(path, 65536)
    if not os.access(path, os.X_OK) or b"from headroom.cli import main" not in raw:
        raise ValueError("Installed headroom console entrypoint is unavailable")
    return str(path), hashlib.sha256(raw).hexdigest()


class CLIExecution:
    def __init__(self, invocation):
        from headroom.orchestrator import FixRequest
        from headroom.store.db import Store

        self.spec = invocation
        self.expected = FixRequest.model_validate(invocation.request)
        self.directory = Path(invocation.run_root).parent
        self.receipt_path = self.directory / ("cli-invocation-" + invocation.run_id + ".json")
        self.dispatched = False
        self.result_saved = False
        self.prepared = None
        self.store = Store(invocation.store_path)
        try:
            state = self.store.get_run(invocation.run_id)
            if (
                not state
                or state.get("status") != "queued"
                or Path(state.get("run_dir", "")).resolve()
                != (Path(invocation.run_root) / invocation.run_id).resolve()
                or _json(state.get("request")) != _json(invocation.queued_request)
                or state.get("study_protocol") != invocation.study_protocol
            ):
                raise ValueError("CLI invocation does not match its queued evaluation intent")
            _write(
                self.directory / ("cli-claimed-" + invocation.run_id + ".json"),
                {"pid": os.getpid()},
            )
            self.receipt = {
                "invocation_kind": "installed_console_script",
                "run_id": invocation.run_id,
                "pid": os.getpid(),
                "console_path": invocation.console_path,
                "console_sha256": invocation.console_sha256,
                "package_root": str(PACKAGE_ROOT),
                "cli_sha256": digest(PACKAGE_ROOT / "headroom/cli.py"),
                "bridge_sha256": digest(Path(__file__)),
                "argv": invocation.argv,
                "invoked": True,
                "returned": False,
                "observed_exit_code": None,
                "started_monotonic": time.monotonic(),
                "run_dispatched": False,
                "result_saved": False,
            }
            if invocation.study_protocol is not None:
                self.receipt["study_protocol"] = invocation.study_protocol
            _write(self.receipt_path, self.receipt)
        except BaseException:
            self.store.close()
            raise

    def close(self):
        self.store.close()

    def _deadline(self):
        if time.monotonic() >= self.spec.deadline:
            raise TimeoutError("Evaluation deadline expired before CLI dispatch")

    def repository_options(self, repository, ref, command):
        from headroom.execution import command_argv
        from headroom.repository import validate_repository

        self._deadline()
        declared = self.spec.repository
        if declared is None or (
            validate_repository(repository, ref)
            != validate_repository(declared.repository, declared.ref)
            or ref != declared.ref
            or list(command_argv(command)) != declared.command
        ):
            raise ValueError("CLI repository arguments differ from the evaluation intent")
        return {"destination": Path(declared.destination), "deadline": self.spec.deadline}

    def repository_prepared(self, prepared):
        from headroom.execution import replay_argv
        from headroom.repository import NANOGPT_REF, NANOGPT_URL
        from headroom.verify.policy import NANOGPT_HASHES

        declared = self.spec.repository
        if declared is None:
            raise ValueError("Unexpected repository preparation")
        args = list(self.expected.script_args)
        if self.expected.source_profile == "pinned_nanogpt":
            if declared.repository != NANOGPT_URL or declared.ref != NANOGPT_REF:
                raise ValueError("Pinned policy requires the original reviewed repository")
            args = ["--dataset=headroom_synthetic" if a == "--dataset=/input" else a for a in args]
            if not any(a.startswith("--dataset=") for a in args):
                args.append("--dataset=headroom_synthetic")
            for name, expected_hash in NANOGPT_HASHES.items():
                if digest(prepared.source_root / name) != expected_hash:
                    raise ValueError("CLI prepared repository differs from its reviewed source")
            dataset = prepared.metadata.get("dataset", {})
            if dataset.get("kind") != "synthetic_uint16" or dataset.get("seed") != 1337:
                raise ValueError("CLI dataset differs from its reviewed preparation")
            for split in ("train", "val"):
                data_path = prepared.source_root / "data/headroom_synthetic" / (split + ".bin")
                if digest(data_path) != dataset.get("sha256", {}).get(split):
                    raise ValueError("CLI prepared dataset hash changed")
        expected_argv = list(replay_argv(declared.command, args))
        if (
            prepared.source_profile != self.expected.source_profile
            or list(prepared.script_args) != args
            or list(prepared.execution_argv) != expected_argv
            or not prepared.source_root.resolve().is_relative_to(
                Path(declared.destination).resolve()
            )
        ):
            raise ValueError("CLI preparation changed execution or policy identity")
        self.expected = self.expected.model_copy(
            update={
                "script": str(prepared.script),
                "source_root": str(prepared.source_root),
                "script_args": args,
                "execution_argv": expected_argv,
                "repository_mode": True,
            }
        )
        self.prepared = {
            "source_sha256": digest(prepared.script),
            "execution": {
                "repository_mode": True,
                "requested_argv": declared.command,
                "execution_argv": expected_argv,
                "command_source": "literal_cli_repository",
            },
            "repository": prepared.metadata,
        }

    def before_run(self, request):
        from headroom.evaluation import condition_services

        self._deadline()
        if self.dispatched:
            raise ValueError("A CLI evaluation invocation may dispatch only once")
        if _json(request.model_dump()) != _json(self.expected.model_dump()):
            raise ValueError("Parsed CLI request differs from the approved evaluation request")
        if digest(request.script) != self.spec.source_sha256:
            raise ValueError("CLI source changed after the evaluation source pin")
        if self.prepared is not None:
            _write(self.directory / ("preparation-" + self.spec.run_id + ".json"), self.prepared)
        services = condition_services(
            self.spec.condition,
            Path(self.spec.audit_dir),
            **(
                {"study_protocol": self.spec.study_protocol}
                if self.spec.study_protocol is not None
                else {}
            ),
        )
        self.dispatched = True
        self.receipt["run_dispatched"] = True
        self.receipt["request_sha256"] = hashlib.sha256(
            _json(request.model_dump()).encode()
        ).hexdigest()
        _write(self.receipt_path, self.receipt, replace=True)
        return {
            "store": self.store,
            "run_root": Path(self.spec.run_root),
            "run_id": self.spec.run_id,
            "services": services,
        }

    def save_result(self, result):
        if result.get("run_id") != self.spec.run_id or not self.dispatched:
            raise ValueError("CLI result is not from the assigned evaluation run")
        _write(Path(self.spec.result_path), result)
        self.result_saved = True
        self.receipt["result_saved"] = True
        self.receipt["result_sha256"] = digest(self.spec.result_path, 64 * 1024 * 1024)

    def finish(self, code, *, returned):
        self.receipt.update(
            returned=returned,
            observed_exit_code=code,
            finished_monotonic=time.monotonic(),
            result_saved=self.result_saved,
        )
        _write(self.receipt_path, self.receipt, replace=True)


def load_context():
    """Consume only a private supervisor bridge; regular CLI invocation is unchanged."""
    path = os.environ.pop(ENVIRONMENT_KEY, None)
    if path is None:
        return None
    invocation = Invocation.model_validate_json(_read(Path(path), MAX_CONTEXT_BYTES, private=True))
    directory = Path(invocation.run_root).parent.resolve()
    if (
        Path(path).resolve() != directory / ("cli-context-" + invocation.run_id + ".json")
        or Path(invocation.package_root).resolve() != PACKAGE_ROOT
        or Path(invocation.result_path).resolve()
        != directory / ("worker-result-" + invocation.run_id + ".json")
        or Path(sys.argv[0]).resolve() != Path(invocation.console_path).resolve()
        or invocation.argv != sys.argv[1:]
        or digest(invocation.console_path, 65536) != invocation.console_sha256
    ):
        raise ValueError("CLI control manifest does not match the executing entrypoint")
    return CLIExecution(invocation)
