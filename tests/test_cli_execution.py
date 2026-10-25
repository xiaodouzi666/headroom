"""Actual installed-console exec tests; all runtime/Lab/provider data is offline."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from headroom import cli_execution as bridge
from headroom import evaluation_worker as worker
from headroom.orchestrator import FixRequest, Policy
from headroom.store.db import Store

ROOT = Path(__file__).resolve().parents[1]


def child_environment(tmp_path):
    """Self-contained guard/fixture bootstrap for both multiprocessing spawn and exec."""
    tmp_path = Path(tmp_path).resolve(strict=True)
    startup = tmp_path / "python-startup"
    startup.mkdir(exist_ok=True)
    code = r"""
import builtins
import io
import os
import socket
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__PACKAGE_ROOT__).resolve()
MAIN = Path("/home/xiaodouzi/workspace/headroom").resolve()
CASE = Path(__CASE_ROOT__).resolve(strict=True)

def check_path(value, *, dir_fd=None):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return
    value = os.fsdecode(value)
    if value.startswith("file:"):
        value = unquote(value[5:].split("?", 1)[0])
    if value in {"", ":memory:"}:
        return
    path = Path(value)
    if not path.is_absolute() and dir_fd is not None:
        path = Path("/proc/self/fd") / str(dir_fd) / path
    path = path.resolve(strict=False)
    # Never grant real secrets or run databases, even if the caller chose an
    # inappropriate broad case root. A symlink is classified by its target.
    for workspace in {ROOT, MAIN}:
        if path.is_relative_to(workspace):
            relative = path.relative_to(workspace)
            if relative.parts and (
                relative.parts[0] == "runs" or relative.parts[0].startswith(".env")
            ):
                raise PermissionError("Test forbids production credentials/database")
            if path == workspace / ".cache/budget.db":
                raise PermissionError("Test forbids the production budget ledger")
    if path.is_relative_to(CASE):
        return
    if path.is_relative_to(ROOT):
        relative = path.relative_to(ROOT)
        if relative.parts and (relative.parts[0] in {".cache", "runs"} or relative.parts[0].startswith(".env")):
            raise PermissionError("Test forbids production credentials/profile/cache/database")
        return
    if path.is_relative_to(MAIN) and not path.is_relative_to(MAIN / ".venv"):
        raise PermissionError("Test forbids the live main worktree")

for module, name in ((builtins, "open"), (io, "open"), (os, "open")):
    original = getattr(module, name)
    def guarded(file, *args, _original=original, **kwargs):
        check_path(file, dir_fd=kwargs.get("dir_fd"))
        return _original(file, *args, **kwargs)
    setattr(module, name, guarded)

original_connect = sqlite3.connect
def guarded_connect(database, *args, **kwargs):
    check_path(database)
    return original_connect(database, *args, **kwargs)
sqlite3.connect = guarded_connect
sqlite3.dbapi2.connect = guarded_connect

def denied(*args, **kwargs):
    raise PermissionError("Offline DNS/INET forbidden")
socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
for key in tuple(os.environ):
    if key.endswith("_API_KEY") or key in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
        os.environ.pop(key, None)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["NVIDIA_VISIBLE_DEVICES"] = "none"

original_popen = subprocess.Popen
def guarded_popen(args, *a, **kw):
    command = args if isinstance(args, (list, tuple)) else [args]
    if any(Path(str(part)).name in {"docker", "nvidia-smi", "curl", "wget", "ssh"} for part in command):
        raise PermissionError("Offline process guard forbids external workloads")
    return original_popen(args, *a, **kw)
subprocess.Popen = guarded_popen

if os.environ.get("LITERAL_CLI_FIXTURE") and os.environ.get("HEADROOM_EVALUATION_CONTEXT"):
    try:
        from test_cli_execution import install_child_fixture
        install_child_fixture()
    except BaseException as error:
        os.write(2, ("Offline fixture startup failed: " + type(error).__name__ + "\n").encode())
        os._exit(96)
"""
    code = code.replace("__PACKAGE_ROOT__", repr(str(ROOT)))
    code = code.replace("__CASE_ROOT__", repr(str(tmp_path)))
    (startup / "sitecustomize.py").write_text(code)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([str(startup), str(ROOT / "tests"), str(ROOT)])
    return environment


def install_child_fixture():
    """Installed by the test-only sitecustomize after exec, not by production code."""
    from headroom import orchestrator

    config = json.loads(Path(os.environ["LITERAL_CLI_FIXTURE"]).read_text())
    base = Path(config["base"])
    if config.get("repository"):
        _install_repository_fixture(base)
    if config["mode"] == "pipeline":
        _install_pipeline_fixture(base)
        return

    def fake(request, **kwargs):
        # Exclusive evidence proves that dispatch was not repeated.
        with (base / "dispatch.json").open("x") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "run_id": kwargs["run_id"],
                    "store": str(kwargs["store"].path),
                    "root": str(kwargs["run_root"]),
                    "request": request.model_dump(),
                    "headroom_file": str(Path(orchestrator.__file__).resolve()),
                },
                handle,
            )
        status = config["mode"]
        if status == "wait":
            while True:
                time.sleep(0.05)
        directory = kwargs["run_root"] / kwargs["run_id"]
        directory.mkdir(parents=True)
        kwargs["store"].update_run(kwargs["run_id"], status=status, target_met=False)
        kwargs["on_event"]({"sequence": 1, "kind": "offline.fixture"})
        return {
            "status": status,
            "target_met": False,
            "run_id": kwargs["run_id"],
            "run_dir": str(directory),
            "report": {},
        }

    orchestrator.run_fix = fake


def _install_repository_fixture(base):
    """Real prepare_repository with offline Git archive and explicitly fake reviewed hashes."""
    import tarfile

    from headroom import repository
    from headroom.verify import policy

    source = base / "source"
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")}
    policy.NANOGPT_HASHES = hashes
    repository.NANOGPT_HASHES = hashes
    repository.PROJECT_ROOT = base
    cached = base / ".cache/upstream/nanoGPT"
    cached.mkdir(parents=True)

    def git(directory, *args, **kwargs):
        if args[:1] == ("rev-parse",):
            return repository.NANOGPT_REF
        if args[:1] == ("remote",):
            return repository.NANOGPT_URL
        if args[:1] == ("status",):
            return ""
        if args[:1] == ("archive",):
            target = next(a.removeprefix("--output=") for a in args if a.startswith("--output="))
            with tarfile.open(target, "w") as archive:
                for path in sorted(source.glob("*.py")):
                    archive.add(path, arcname=path.name)
            return ""
        raise AssertionError("No fetch or repository execution permitted")

    repository._git = git


def _install_pipeline_fixture(base):
    """Real run_fix -> build_live_runtime -> SDK MockTransport -> Store/ledger."""
    import shutil

    import httpx
    from test_actual_usage_budget import reviewed_fixture

    from headroom import evaluation, orchestrator
    from headroom.runtime import build_live_runtime

    profile = reviewed_fixture(base)
    orchestrator.PROJECT_ROOT = base
    orchestrator.read_live_profile = lambda *a: profile

    def respond(request):
        body = json.loads(request.content)
        with (base / "mock-request.json").open("x") as handle:
            json.dump(
                {
                    "model": body["model"],
                    "max_completion_tokens": body.get("max_completion_tokens"),
                },
                handle,
            )
        diagnosis = {
            "root_causes": [
                {
                    "id": "c1",
                    "title": "Offline allocation",
                    "category": "activations",
                    "bytes_gb": 2.0,
                    "evidence_refs": ["stk_fixture"],
                    "confidence": 0.9,
                }
            ],
            "plan": [],
            "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
            "needs_more_info": True,
            "notes": ["Offline fixture requires additional information."],
        }
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(diagnosis)},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    def runtime(run_id, **kwargs):
        return build_live_runtime(
            run_id,
            **kwargs,
            env_file=base / ".env",
            transport=httpx.MockTransport(respond),
        )

    orchestrator.build_live_runtime = runtime

    def baseline(script, **kwargs):
        path = Path(kwargs["run_root"]) / "offline-baseline"
        path.mkdir(parents=True)
        shutil.copytree(kwargs["source_root"], path / "source")
        return {
            "run_id": "offline-baseline",
            "run_dir": str(path),
            "status": "oom",
            "peak_alloc_gb": 2.0,
            "peak_reserved_gb": 2.1,
            "steps": 0,
            "loss_series": [],
            "env": {"seed": 1337},
        }

    def evidence(run, *, output_dir, **kwargs):
        output_dir.mkdir(parents=True)
        data = {
            "sources": [{"path": "train.py"}],
            "analysis": {"stack_catalog": {"stk_fixture": []}},
        }
        (output_dir / "evidence.json").write_text(json.dumps(data))
        (output_dir / "evidence.md").write_text("Offline stk_fixture.\n")
        return {
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
            "analysis": data["analysis"],
            "token_count": 10,
        }

    real_condition_services = evaluation.condition_services

    def services(condition, audit_dir):
        from dataclasses import replace

        return replace(
            real_condition_services(condition, audit_dir),
            baseline=baseline,
            evidence=evidence,
            provenance="offline_fixture",
        )

    evaluation.condition_services = services


def setup_case(tmp_path, *, repository=False, **changes):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    request = FixRequest(
        script=str(source / "train.py"),
        source_root=str(source),
        research_enabled=False,
        runtime_profile=str(tmp_path / "reviewed.json"),
        **changes,
    )
    case = {
        "id": "fixture",
        "group": "synthetic",
        "script": "source/train.py",
        "source_root": "source",
        "target": request.target,
        "expected_baseline": "oom",
        "source_sha256": bridge.digest(source / "train.py"),
    }
    if repository:
        from headroom.repository import NANOGPT_REF, NANOGPT_URL

        (source / "model.py").write_text("MODEL = 1\n")
        (source / "configurator.py").write_text("CONFIG = 1\n")
        request = request.model_copy(
            update={
                "script_args": ["--dataset=/input", "--max_iters=20", "--dtype=float32"],
                "source_profile": "pinned_nanogpt",
            }
        )
        (tmp_path / "repo.json").write_text(
            json.dumps(
                {
                    "repository": NANOGPT_URL,
                    "ref": NANOGPT_REF,
                    "command": "python -u train.py --dataset=/input --max_iters=20 --dtype=float32",
                }
            )
        )
        case.update(
            group="repository",
            script_args=request.script_args,
            source_profile="pinned_nanogpt",
            repository_manifest="repo.json",
        )
    run_id = uuid4().hex
    store = Store(tmp_path / "store.db")
    store.create_run(
        run_id,
        {
            "status": "queued",
            "target_met": False,
            "request": request.model_dump(),
            "run_dir": str(tmp_path / "jobs" / run_id),
        },
    )
    store.close()
    values = [
        request.model_dump(),
        str(tmp_path / "store.db"),
        str(tmp_path / "jobs"),
        run_id,
        "full_ultra",
        str(tmp_path / "audit"),
        str(tmp_path / ("worker-result-" + run_id + ".json")),
        time.monotonic() + 40,
        {"case": case, "project_root": str(tmp_path), "input_dir": str(tmp_path / "prepared")},
    ]
    return request, run_id, values


def execute_case(tmp_path, values, *, mode="completed", repository=False):
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps({"base": str(tmp_path), "mode": mode, "repository": repository}))
    request = tmp_path / "worker-input.json"
    request.write_text(json.dumps(values))
    environment = child_environment(tmp_path)
    environment["LITERAL_CLI_FIXTURE"] = str(config)
    program = (
        "import json,os; from pathlib import Path;"
        "from headroom.evaluation_worker import _evaluation_entry;"
        f"Path({str(tmp_path / 'original-pid')!r}).write_text(str(os.getpid()));"
        f"_evaluation_entry(*json.loads(Path({str(request)!r}).read_text()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    run_id = values[3]
    receipt_path = tmp_path / ("cli-invocation-" + run_id + ".json")
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    return result, receipt


@pytest.mark.parametrize(
    "status,code",
    [
        ("completed", 0),
        ("needs_human", 78),
        ("budget_exceeded", 78),
        ("timeout", 124),
        ("failed", 1),
    ],
)
def test_actual_console_exec_keeps_pid_uuid_one_dispatch_and_real_exit(tmp_path, status, code):
    request, run_id, values = setup_case(tmp_path)
    result, receipt = execute_case(tmp_path, values, mode=status)
    assert result.returncode == code, result.stderr
    assert receipt["invocation_kind"] == "installed_console_script"
    assert receipt["observed_exit_code"] == code and receipt["returned"]
    dispatch = json.loads((tmp_path / "dispatch.json").read_text())
    assert dispatch["pid"] == receipt["pid"] == int((tmp_path / "original-pid").read_text())
    assert dispatch["run_id"] == run_id and dispatch["store"] == str(tmp_path / "store.db")
    assert dispatch["request"] == request.model_dump()
    assert Path(dispatch["headroom_file"]).is_relative_to(ROOT)
    raw = worker._read(Path(values[6]))
    assert raw["target_met"] is False  # Completed/exit0 is not fabricated quality acceptance.
    _, verified = worker._verified_cli_receipt(
        tmp_path / ("cli-invocation-" + run_id + ".json"),
        raw,
        code,
        run_id,
        receipt["pid"],
    )
    assert verified
    assert "offline.fixture" in (tmp_path / ("cli-" + run_id + ".stderr.log")).read_text()


def test_real_run_fix_sdk_mock_and_shared_ledger_are_not_executed_twice(tmp_path):
    _, run_id, values = setup_case(tmp_path)
    result, receipt = execute_case(tmp_path, values, mode="pipeline")
    assert result.returncode == 78, result.stderr
    assert receipt["result_saved"] and receipt["run_dispatched"]
    store = Store(tmp_path / "store.db")
    try:
        calls = store.llm_calls(run_id)
        assert len(calls) == 1
        assert calls[0]["outcome"] == "response"
        assert store.get_run(run_id)["provenance"] == "offline_fixture"
        assert len([e for e in store.events(run_id) if e["kind"] == "run.started"]) == 1
        import sqlite3

        connection = sqlite3.connect(tmp_path / ".cache/budget.db")
        try:
            assert connection.execute("SELECT COUNT(*) FROM budget_runs").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        store.close()


def test_true_repository_cli_prepares_once_and_preserves_profile_and_prefix(tmp_path):
    _, run_id, values = setup_case(tmp_path, repository=True)
    result, receipt = execute_case(tmp_path, values, repository=True)
    assert result.returncode == 0, result.stderr
    dispatch = json.loads((tmp_path / "dispatch.json").read_text())["request"]
    assert dispatch["source_profile"] == "pinned_nanogpt" and dispatch["repository_mode"]
    assert dispatch["execution_argv"][:3] == ["python", "-u", "train.py"]
    assert "--dataset=headroom_synthetic" in dispatch["script_args"]
    assert "--repo" in receipt["argv"] and "--ref" in receipt["argv"] and "--cmd" in receipt["argv"]
    prepared = json.loads((tmp_path / ("preparation-" + run_id + ".json")).read_text())
    assert prepared["source_sha256"] == values[8]["case"]["source_sha256"]
    assert prepared["repository"]["ref"] == receipt["argv"][receipt["argv"].index("--ref") + 1]
    assert prepared["repository"]["dataset"]["kind"] == "synthetic_uint16"
    data = Path(dispatch["source_root"]) / "data/headroom_synthetic"
    for split, expected in prepared["repository"]["dataset"]["sha256"].items():
        assert bridge.digest(data / (split + ".bin")) == expected
    assert len(list((tmp_path / "prepared").glob("repository"))) == 1


@pytest.mark.parametrize("change", ["budget", "policy", "source", "argv", "closed"])
def test_pre_dispatch_binding_refuses_drift_without_run_fix(tmp_path, monkeypatch, change):
    request, run_id, values = setup_case(tmp_path)
    console, console_hash = bridge.console_script()
    spec = bridge.Invocation(
        run_id=run_id,
        request=request.model_dump(),
        queued_request=request.model_dump(),
        store_path=values[1],
        run_root=values[2],
        audit_dir=values[5],
        result_path=values[6],
        deadline=values[7],
        condition=values[4],
        argv=bridge.cli_arguments(request),
        package_root=str(ROOT),
        console_path=console,
        console_sha256=console_hash,
        source_sha256=bridge.digest(request.script),
    )
    if change == "closed":
        store = Store(values[1])
        store.update_run(run_id, status="completed")
        store.close()
        with pytest.raises(ValueError, match="queued"):
            bridge.CLIExecution(spec)
        return
    context = bridge.CLIExecution(spec)
    try:
        if change == "budget":
            request.budget_usd = "0.7"
        elif change == "policy":
            request.policy.allow_numerics_change = True
        elif change == "source":
            Path(request.script).write_text("VALUE = 2\n")
        else:
            request.script_args = ["--max_steps=1"]
        with pytest.raises(ValueError, match="differs|changed"):
            context.before_run(request)
        assert not context.dispatched
        assert not (tmp_path / "audit").exists()
    finally:
        context.close()


def test_explicit_false_zero_and_yaml_cannot_change_manifest_request(tmp_path):
    request, _, values = setup_case(
        tmp_path,
        policy=Policy(
            allow_numerics_change=False,
            allow_batch_grad_accum=False,
            max_throughput_regression_pct=0,
        ),
        seed=0,
        reclaim_reduction_pct=20.0,
        target="reclaim",
    )
    (tmp_path / "source/headroom.yaml").write_text(
        "policy:\n  allow_numerics_change: true\n  allow_batch_grad_accum: true\n"
        "  max_throughput_regression_pct: 100\nseed: 99\nreclaim_reduction_pct: 30\n"
    )
    result, _ = execute_case(tmp_path, values)
    assert result.returncode == 0
    assert json.loads((tmp_path / "dispatch.json").read_text())["request"] == request.model_dump()


def test_claim_prevents_relaunch_of_the_same_run(tmp_path):
    _, _, values = setup_case(tmp_path)
    result, _ = execute_case(tmp_path, values)
    assert result.returncode == 0
    context_path = tmp_path / ("cli-context-" + values[3] + ".json")
    config = json.loads(context_path.read_text())
    store = Store(values[1])
    store.update_run(values[3], status="queued")
    store.close()
    with pytest.raises(FileExistsError):
        bridge.CLIExecution(bridge.Invocation.model_validate(config))


def test_receipt_does_not_convert_status_or_missing_return_into_observed_success(tmp_path):
    _, run_id, values = setup_case(tmp_path)
    result, receipt = execute_case(tmp_path, values, mode="needs_human")
    assert result.returncode == 78
    path = tmp_path / ("cli-invocation-" + run_id + ".json")
    raw = worker._read(Path(values[6]))
    for changes in (
        {"observed_exit_code": 0},
        {"returned": False},
        {"pid": -1},
        {"result_sha256": "0" * 64},
    ):
        path.write_text(json.dumps({**receipt, **changes}))
        assert worker._verified_cli_receipt(path, raw, 78, run_id, receipt["pid"])[1] is False


def test_local_repository_command_keeps_existing_no_manifest_path(tmp_path):
    request, _, values = setup_case(tmp_path)
    values[8]["case"]["group"] = "repository"
    result, receipt = execute_case(tmp_path, values)
    assert result.returncode == 0, result.stderr
    actual = json.loads((tmp_path / "dispatch.json").read_text())["request"]
    assert actual["repository_mode"] and actual["source_profile"] is None
    assert actual["execution_argv"] == ["python", "train.py"]
    assert "--cmd" in receipt["argv"] and "--repo" not in receipt["argv"]
    assert actual["budget_usd"] == request.budget_usd


def test_supervisor_accepts_legitimate_nonzero_cli_result_without_masking_it(tmp_path, monkeypatch):
    request, run_id, values = setup_case(tmp_path)
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps({"base": str(tmp_path), "mode": "needs_human"}))
    monkeypatch.setenv("LITERAL_CLI_FIXTURE", str(config))
    monkeypatch.setenv("PYTHONPATH", child_environment(tmp_path)["PYTHONPATH"])
    store = Store(values[1])
    try:
        result = worker.supervise_evaluation_run(
            request,
            store=store,
            run_root=Path(values[2]),
            run_id=run_id,
            condition=values[4],
            audit_dir=Path(values[5]),
            started=time.monotonic(),
            preparation=values[8],
            wall_limit_seconds=15,
        )
        assert result["status"] == "needs_human" and not result["target_met"]
        timing = result["evaluation_timing"]
        assert timing["worker_exit_code"] == timing["cli"]["observed_exit_code"] == 78
        assert timing["cli"]["verified"] is True
        assert timing["cli"]["pid"] == store.get_run(run_id)["evaluation_worker_pid"]
    finally:
        store.close()


def test_deadline_kills_real_console_without_inventing_cli_return(tmp_path, monkeypatch):
    request, run_id, values = setup_case(tmp_path)
    config = tmp_path / "fixture.json"
    config.write_text(json.dumps({"base": str(tmp_path), "mode": "wait"}))
    monkeypatch.setenv("LITERAL_CLI_FIXTURE", str(config))
    monkeypatch.setenv("PYTHONPATH", child_environment(tmp_path)["PYTHONPATH"])
    store = Store(values[1])
    try:
        result = worker.supervise_evaluation_run(
            request,
            store=store,
            run_root=Path(values[2]),
            run_id=run_id,
            condition=values[4],
            audit_dir=Path(values[5]),
            started=time.monotonic(),
            preparation=values[8],
            wall_limit_seconds=4,
        )
        assert result["status"] == "timeout"
        timing = result["evaluation_timing"]
        assert timing["worker_exit_code"] < 0
        assert timing["cli"]["invoked"] is True and timing["cli"]["returned"] is False
        assert timing["cli"]["observed_exit_code"] is None
        assert timing["cli"]["verified"] is False
        assert timing["cleanup_verified"]
    finally:
        store.close()


def test_child_guard_is_self_contained_without_private_setup_files(tmp_path):
    environment = child_environment(tmp_path)
    environment.pop("LITERAL_CLI_FIXTURE", None)
    environment.pop("HEADROOM_EVALUATION_CONTEXT", None)
    program = r"""
import builtins, io, json, os, socket, sqlite3, subprocess
from pathlib import Path
import headroom
root = Path(headroom.__file__).resolve().parents[1]
blocked = []
for name, action in [
    ("builtins_env", lambda: builtins.open(root / ".env")),
    ("io_env", lambda: io.open(root / ".env")),
    ("os_env", lambda: os.open(root / ".env", os.O_RDONLY)),
    ("profile", lambda: builtins.open(root / ".cache/live-profile.json")),
    ("sqlite", lambda: sqlite3.connect(root / ".cache/budget.db")),
    ("sqlite_uri", lambda: sqlite3.connect("file:" + str(root / "runs/headroom.db") + "?mode=ro", uri=True)),
    ("dns", lambda: socket.getaddrinfo("example.com", 443)),
    ("connect", lambda: socket.socket().connect(("127.0.0.1", 80))),
    ("docker", lambda: subprocess.Popen(["docker", "ps"])),
]:
    try:
        action()
    except PermissionError:
        blocked.append(name)
    else:
        raise AssertionError(name)
assert os.environ["CUDA_VISIBLE_DEVICES"] == ""
print(json.dumps({"blocked": blocked, "root": str(root)}))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert len(data["blocked"]) == 9
    assert Path(data["root"]) == ROOT
    assert ".cache/setup" not in environment["PYTHONPATH"]


def test_case_inside_checkout_cache_is_allowed_but_symlink_escape_is_not(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    case = checkout / ".cache/tmp/case"
    case.mkdir(parents=True)
    (checkout / ".env").write_text("fake production credential; must not be opened")
    (checkout / ".cache/profile.json").write_text("fake production profile")
    (checkout / ".cache/budget.db").write_text("fake production ledger")
    sibling = checkout / ".cache/tmp/sibling"
    sibling.mkdir()
    (sibling / "not-this-case").write_text("must not be opened")
    (case / "secret-link").symlink_to(checkout / ".env")
    (case / "profile-link").symlink_to(checkout / ".cache/profile.json")
    (case / "ledger-link").symlink_to(checkout / ".cache/budget.db")
    (case / "directory-link").symlink_to(checkout / ".cache", target_is_directory=True)
    monkeypatch.setattr(sys.modules[__name__], "ROOT", checkout)
    environment = child_environment(case)
    environment.pop("LITERAL_CLI_FIXTURE", None)
    environment.pop("HEADROOM_EVALUATION_CONTEXT", None)
    program = r"""
import io, json, os, sqlite3, sys
from pathlib import Path
case, checkout = map(Path, sys.argv[1:])
(case / "original-pid").write_text(str(os.getpid()))
(case / ".env").write_text("explicit offline fixture")
assert (case / ".env").read_text() == "explicit offline fixture"
connection = sqlite3.connect(case / "fixture.db")
connection.execute("CREATE TABLE fixture(id INTEGER)")
connection.close()
directory = os.open(checkout, os.O_RDONLY | os.O_DIRECTORY)
blocked = []
try:
    for name, action in [
        ("direct_env", lambda: open(checkout / ".env")),
        ("direct_profile", lambda: io.open(checkout / ".cache/profile.json")),
        ("direct_ledger", lambda: sqlite3.connect(checkout / ".cache/budget.db")),
        ("sibling", lambda: open(case / "../sibling/not-this-case")),
        ("env_symlink", lambda: open(case / "secret-link")),
        ("profile_symlink", lambda: io.open(case / "profile-link")),
        ("ledger_symlink", lambda: sqlite3.connect(case / "ledger-link")),
        ("directory_symlink", lambda: os.open(case / "directory-link/profile.json", os.O_RDONLY)),
        ("relative_dir_fd", lambda: os.open(".env", os.O_RDONLY, dir_fd=directory)),
    ]:
        try:
            action()
        except PermissionError:
            blocked.append(name)
        else:
            raise AssertionError(name)
finally:
    os.close(directory)
print(json.dumps(blocked))
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(case), str(checkout)],
        env=environment,
        cwd=case,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 9
    assert (case / "original-pid").is_file()
