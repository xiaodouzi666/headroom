"""Independent reference scheduling tests; real containers use CPU/no network only."""

import builtins
import importlib.util
import io
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from headroom.acceptance import isolation
from headroom.lab import docker
from headroom.lab.runner import PROJECT_ROOT, run_script
from headroom.lab.subprocess_reference import require_boundary, validate_request
from tests.test_hf_cache import make_cache
from tests.test_hf_trainer import TRAINING


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No DNS/INET during subprocess-reference validation")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module in (builtins, io, os):
        original = module.open

        def guarded(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, Path)) and any(
                part.lower().startswith(".env") for part in Path(path).parts
            ):
                raise AssertionError("No credential reads")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)


def request(**changes):
    return {
        "schema": isolation.PROTOCOL,
        "script": "train.py",
        "script_args": [],
        "device": "cpu",
        "max_steps": 4,
        "max_seconds": 60,
        "seed": 1337,
        "allocator_conf": None,
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"script": "../train.py"},
        {"script": "/source/train.py"},
        {"script": ".env.py"},
        {"script_args": "--evil"},
        {"script_args": ["x\0y"]},
        {"max_steps": True},
        {"max_seconds": True},
        {"max_seconds": float("nan")},
        {"seed": True},
        {"max_steps": 0},
        {"device": "gpu"},
        {"schema": "unknown"},
        {"unexpected": 1},
    ],
)
def test_request_rejects_ambiguous_or_unbounded_control(change):
    with pytest.raises((ValueError, TypeError)):
        validate_request(request(**change))


def test_child_environment_is_allowlisted_and_controller_cannot_run_bare_host(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "offline-canary")
    monkeypatch.setenv("TAVILY_API_KEY", "offline-canary")
    monkeypatch.setenv("HF_TOKEN", "offline-canary")
    env = validate_request(request())
    assert not ({"NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN"} & set(env))
    assert env["HEADROOM_CAPTURE"] == "1" and env["HEADROOM_CONTROL_DIR"] == "/control"
    assert env["HF_HUB_OFFLINE"] == "1"
    original = Path.is_file
    monkeypatch.setattr(
        Path, "is_file", lambda self: False if str(self) == "/.dockerenv" else original(self)
    )
    with pytest.raises(ValueError, match="Docker"):
        require_boundary()


def test_reference_host_execution_uses_one_deadline_and_its_own_lifecycle(tmp_path, monkeypatch):
    calls = []
    state = {"n": 0}

    def command(argv, timeout):
        calls.append((argv, timeout))
        return subprocess.CompletedProcess(argv, 0, "", "")

    def inspect(name, timeout):
        state["n"] += 1
        return {
            "state": {"Running": state["n"] == 1, "ExitCode": 0, "OOMKilled": False},
            "image_id": "sha256:fixture",
        }

    controls = []

    def publish(control, seconds):
        controls.append((control, seconds))
        return {"hard_deadline_monotonic_ns": time.monotonic_ns() + 2_000_000_000}

    monkeypatch.setattr(isolation, "_command", command)
    monkeypatch.setattr(isolation, "_inspect", inspect)
    monkeypatch.setattr(isolation, "publish_deadline", publish)
    monkeypatch.setattr(isolation, "_cleanup", lambda name: {"cleanup_verified": True})
    monkeypatch.setattr(
        docker, "execute", lambda **kwargs: pytest.fail("production dispatcher reused")
    )
    result = isolation._execute_reference(
        ["docker", "create"], "headroom-reference-fixture", tmp_path, tmp_path, 2
    )
    assert len(controls) == 1
    assert not result["timed_out"] and result["cleanup_verified"]
    assert [a[0][1] for a in calls] == ["create", "start"]
    assert 0 < calls[1][1] <= 2
    assert (tmp_path / "execution.json").exists()


def test_reference_host_timeout_retains_unknown_capture_and_always_cleans(tmp_path, monkeypatch):
    cleaned = []

    def command(argv, timeout):
        if "start" in argv:
            raise subprocess.TimeoutExpired(argv, timeout)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(isolation, "_command", command)
    monkeypatch.setattr(
        isolation,
        "publish_deadline",
        lambda *a: {"hard_deadline_monotonic_ns": time.monotonic_ns() + 10_000_000},
    )

    def cleanup(name):
        cleaned.append(name)
        return {"cleanup_verified": True}

    monkeypatch.setattr(isolation, "_cleanup", cleanup)
    result = isolation._execute_reference(
        ["docker", "create"], "headroom-reference-fixture", tmp_path, tmp_path, 0.01
    )
    assert result["timed_out"] and cleaned == ["headroom-reference-fixture"]
    assert result["state"] is None


def comparison_fixture(tmp_path, *, device="cuda", peak=10000):
    results = []
    for name, value in (("production", 10000), ("reference", peak)):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "manifest.json").write_text(
            json.dumps({"source": {"files": {"train.py": {"sha256": "a" * 64, "bytes": 1}}}})
        )
        results.append(
            {
                "run_dir": str(directory),
                "status": "completed",
                "capture_complete": True,
                "cleanup_verified": True,
                "steps": 20,
                "loss_series": [1.0],
                "parameter_count": 9,
                "parameter_count_complete": True,
                "image_id": "sha256:fixture",
                "gpu_observation_complete": True,
                "shared_gpu": False,
                "gpu_clear_before_after": True,
                "env": {
                    "python": "fixture",
                    "torch": "fixture",
                    "cuda": "fixture",
                    "device": device,
                    "seed": 1337,
                    "max_steps": 20,
                    "max_seconds": 60,
                    "PYTORCH_CUDA_ALLOC_CONF": None,
                    "CUDA_VISIBLE_DEVICES": "",
                    "seeded": {"torch": True},
                    "deterministic_algorithms": True,
                    "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
                },
                "peak_allocated_bytes": value if device == "cuda" else None,
            }
        )
    return results


@pytest.mark.parametrize("peak,accepted", [(9900, True), (10100, True), (10101, False)])
def test_original_one_percent_cuda_gate_is_exact(tmp_path, peak, accepted):
    pair = comparison_fixture(tmp_path, peak=peak)
    result = isolation.compare_pair(
        *pair,
        expected_status="completed",
        max_steps=20,
        device="cuda",
        expected_script_sha256="a" * 64,
    )
    assert result["t2_7_case_accepted"] is accepted


@pytest.mark.parametrize(
    "change",
    [
        {"capture_complete": False},
        {"cleanup_verified": False},
        {"steps": 19},
        {"status": "timeout"},
        {"image_id": "different"},
        {"loss_series": []},
    ],
)
def test_comparison_never_turns_partial_or_mismatched_run_into_pass(tmp_path, change):
    pair = comparison_fixture(tmp_path)
    pair[1].update(change)
    result = isolation.compare_pair(
        *pair,
        expected_status="completed",
        max_steps=20,
        device="cuda",
        expected_script_sha256="a" * 64,
    )
    assert not result["t2_7_case_accepted"]


def test_cpu_parity_is_not_cuda_acceptance(tmp_path):
    pair = comparison_fixture(tmp_path, device="cpu")
    result = isolation.compare_pair(*pair, expected_status="completed", max_steps=20, device="cpu")
    assert result["component_parity_pass"]
    assert result["peak_delta_pct"] is None and not result["t2_7_case_accepted"]


def test_cli_default_only_prints_plan_without_creating_output(tmp_path, monkeypatch, capsys):
    file = PROJECT_ROOT / "scripts/check_docker_subprocess_parity.py"
    spec = importlib.util.spec_from_file_location("parity_cli", file)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(
        cli, "run_acceptance", lambda *a, **kw: pytest.fail("execute without opt-in")
    )
    assert cli.main(["--output", str(tmp_path / "unused")]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["cases"]) == 3 and plan["cost_usd"] == "0"
    assert not (tmp_path / "unused").exists()
    with pytest.raises(SystemExit):
        cli.main(["--execute"])


@pytest.mark.parametrize("scenario", ["sgd", "adamw", "hf_trainer"])
def test_three_real_cpu_pairs_use_independent_subprocess_controller(
    tmp_path, monkeypatch, scenario
):
    if scenario == "hf_trainer":
        script = PROJECT_ROOT / "repos/hf_trainer/train.py"
        args, steps = ["--profile", "cpu-smoke", "--device", "cpu"], 20
    else:
        source = tmp_path / "source"
        source.mkdir()
        script = source / "train.py"
        script.write_text(TRAINING.format(optimizer="SGD" if scenario == "sgd" else "AdamW"))
        args, steps = [], 4
    first = run_script(
        script,
        script_args=args,
        run_root=tmp_path / "production",
        device="cpu",
        max_steps=steps,
        max_seconds=60,
        seed=1337,
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            docker, "execute", lambda **kw: pytest.fail("reference reused production dispatch")
        )
        patcher.setattr(
            isolation,
            "run_script",
            lambda *a, **kw: pytest.fail("reference reused production script"),
        )
        second = isolation.run_subprocess_reference(
            script,
            script_args=args,
            run_root=tmp_path / "reference",
            device="cpu",
            max_steps=steps,
            max_seconds=60,
            seed=1337,
        )
    assert first["status"] == second["status"] == "completed", (first, second)
    assert second["controller"]["child_pid"] == second["pid"]
    assert second["controller"]["pid"] != second["pid"]
    assert second["controller"]["group_cleanup_verified"]
    assert second["controller"]["deadline"]["clock_verified"]
    compared = isolation.compare_pair(
        first, second, expected_status="completed", max_steps=steps, device="cpu"
    )
    (tmp_path / "cpu-parity.json").write_text(json.dumps(compared, indent=2))
    assert compared["component_parity_pass"], compared
    assert not compared["t2_7_case_accepted"]


def test_real_cpu_child_has_no_network_secret_or_write_escape_and_hf_cache_is_readonly(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "headroom").symlink_to(PROJECT_ROOT / "headroom", target_is_directory=True)
    (project / "uv.lock").write_bytes((PROJECT_ROOT / "uv.lock").read_bytes())
    make_cache(project)
    source = tmp_path / "source"
    source.mkdir()
    script = source / "probe.py"
    script.write_text("""import json, os, socket
from pathlib import Path
from transformers import GPT2Config
assert not any(os.environ.get(k) for k in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN"))
assert sorted(p.name for p in Path("/sys/class/net").iterdir()) == ["lo"]
s=socket.socket()
s.settimeout(0.2)
try:
    s.connect(("192.0.2.1", 443))
except OSError:
    network_blocked=True
else:
    raise AssertionError("network escape")
finally:
    s.close()
for location in ("/source/forbidden", "/runtime/headroom/forbidden", "/control/forbidden", "/forbidden", "/hf-cache/forbidden"):
    try:
        Path(location).write_text("invalid")
    except OSError:
        pass
    else:
        raise AssertionError("write escape")
config=GPT2Config.from_pretrained("/hf-cache/random-model",local_files_only=True)
assert config.n_embd == 16
Path("/out/isolation-probe.json").write_text(json.dumps({"network_blocked":network_blocked,"cache_read":True,"writes_blocked":True}))
""")
    monkeypatch.setenv("NEBIUS_API_KEY", "synthetic-no-secret")
    result = isolation.run_subprocess_reference(
        script, run_root=tmp_path / "runs", project_root=project, device="cpu", max_seconds=60
    )
    assert result["status"] == "completed" and result["cleanup_verified"], result
    raw = json.loads((Path(result["run_dir"]) / "artifacts/isolation-probe.json").read_text())
    assert all(raw.values())
    assert not (source / "forbidden").exists()


def test_real_cpu_ignored_signal_is_hard_stopped_and_container_removed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "loop.py"
    script.write_text(
        "import signal,time\nsignal.signal(signal.SIGALRM,signal.SIG_IGN)\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nwhile True: time.sleep(0.1)\n"
    )
    started = time.monotonic()
    result = isolation.run_subprocess_reference(
        script, run_root=tmp_path / "runs", device="cpu", max_seconds=6
    )
    assert result["status"] == "timeout" and result["cleanup_verified"], result
    assert time.monotonic() - started < 25
    assert result.get("capture_complete") is not True


def test_real_cpu_nonzero_target_exit_is_not_rewritten_as_success(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "exit.py"
    script.write_text("raise SystemExit(7)\n")
    result = isolation.run_subprocess_reference(
        script, run_root=tmp_path / "runs", device="cpu", max_seconds=30
    )
    assert result["status"] == "error" and result["cleanup_verified"], result
    assert result["controller"]["returncode"] == 7


def test_last_inspect_cannot_extend_execution_deadline(tmp_path, monkeypatch):
    clock = {"now": 0}
    monkeypatch.setattr(isolation.time, "monotonic_ns", lambda: clock["now"])
    monkeypatch.setattr(
        isolation, "publish_deadline", lambda *a: {"hard_deadline_monotonic_ns": 100}
    )
    monkeypatch.setattr(
        isolation, "_command", lambda argv, timeout: subprocess.CompletedProcess(argv, 0, "", "")
    )

    def inspect(*args):
        clock["now"] = 101
        return {"state": {"Running": False, "ExitCode": 0, "OOMKilled": False}}

    monkeypatch.setattr(isolation, "_inspect", inspect)
    monkeypatch.setattr(isolation, "_cleanup", lambda name: {"cleanup_verified": True})
    result = isolation._execute_reference(
        ["docker", "create"], "headroom-reference-fixture", tmp_path, tmp_path, 1
    )
    assert result["timed_out"]


def test_real_cpu_normal_exit_reaps_background_process_group(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "background.py"
    script.write_text(
        "import subprocess\nsubprocess.Popen(['/bin/sleep','60'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
    )
    result = isolation.run_subprocess_reference(
        script, run_root=tmp_path / "runs", device="cpu", max_seconds=30
    )
    assert result["status"] == "completed" and result["cleanup_verified"], result
    assert result["controller"]["group_cleanup_verified"]


@pytest.mark.parametrize(
    "changes",
    [
        {"shared_gpu": True},
        {"shared_gpu": None},
        {"gpu_observation_complete": False},
        {"gpu_clear_before_after": False},
    ],
)
def test_cuda_comparison_preserves_shared_or_unknown_observations(tmp_path, changes):
    pair = comparison_fixture(tmp_path)
    pair[1].update(changes)
    compared = isolation.compare_pair(
        *pair,
        expected_status="completed",
        max_steps=20,
        device="cuda",
        expected_script_sha256="a" * 64,
    )
    assert not compared["t2_7_case_accepted"]
    assert compared["gpu_observation"]["reference_shared"] == pair[1]["shared_gpu"]


@pytest.mark.parametrize(
    "files", [None, {}, {"train.py": None}, {"train.py": {"sha256": "a", "bytes": 1}}]
)
def test_equal_incomplete_manifests_are_not_equal_source_evidence(tmp_path, files):
    pair = comparison_fixture(tmp_path)
    for result in pair:
        (Path(result["run_dir"]) / "manifest.json").write_text(
            json.dumps({"source": {"files": files}})
        )
    compared = isolation.compare_pair(
        *pair,
        expected_status="completed",
        max_steps=20,
        device="cuda",
        expected_script_sha256="a" * 64,
    )
    assert not compared["checks"]["same_source_hashes"]
    assert not compared["t2_7_case_accepted"]


def test_cuda_comparison_requires_original_script_pin(tmp_path):
    pair = comparison_fixture(tmp_path)
    compared = isolation.compare_pair(
        *pair,
        expected_status="completed",
        max_steps=20,
        device="cuda",
        expected_script_sha256="b" * 64,
    )
    assert not compared["checks"]["original_script_pin"]
    assert not compared["t2_7_case_accepted"]
