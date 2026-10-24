"""Bounded multi-capture selection; CUDA classification below is synthetic unless stated."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from headroom.execution import prepare_captured_command
from headroom.lab import runner


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in multi-capture tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def capture(pid, *, primary=False, target=False, status="completed", args=None):
    arguments = list(args or (["--batch", "8"] if target else []))
    argv = ["python", "train.py", *arguments] if target else ["python", "-c", "print('helper')"]
    return {
        "protocol": "headroom.lab.v1",
        "schema_version": 1,
        "status": status,
        "termination_reason": "oom" if status == "oom" else "script_exit",
        "capture_complete": True,
        "pid": pid,
        "is_primary": primary,
        "steps": 0,
        "loss_series": [],
        "step_records": [],
        "peak_allocated_bytes": 900 if target else 11,
        "peak_reserved_bytes": 1000,
        "precision_observation": {"complete": True, "precision": "fp32" if target else "unknown"},
        "parameter_count": 4 if target else 0,
        "pairing_capture": {"complete": False},
        "oom": {"traceback": "synthetic CUDA classification"} if status == "oom" else None,
        "env": {"device": "cuda" if status == "oom" else "cpu", "seed": 1337},
        "execution_entrypoint": {
            "schema_version": 1,
            "complete": target,
            "pid": pid,
            "ppid": 1,
            "executable": "/opt/venv/bin/python",
            "startup_cwd": "/source",
            "cwd": "/source",
            "orig_argv": argv,
            "startup_argv": [argv[1], *arguments],
            "effective_startup_argv": [argv[1], *arguments],
            "argv": [argv[1], *arguments],
            "main_file": "/source/train.py" if target else None,
            "module": None,
        },
    }


def write_capture(run, relative, data, snapshot=None):
    directory = run / relative
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps(data))
    (directory / "snapshot.json").write_text(json.dumps(snapshot))
    (directory / "env.json").write_text(json.dumps(data["env"]))
    (directory / "traceback.txt").write_text(relative)
    return directory


@pytest.fixture
def captured_run(tmp_path):
    run = tmp_path / "captured"
    source = run / "source"
    source.mkdir(parents=True)
    (source / "train.py").write_text("VALUE = 1\n")
    manifest = {
        "command": ["/bin/sh", "launch.sh", "--batch", "8"],
        "source": {
            "files": {
                "train.py": {
                    "sha256": hashlib.sha256((source / "train.py").read_bytes()).hexdigest(),
                    "bytes": 10,
                }
            }
        },
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    write_capture(run, "artifacts", capture(1, primary=True), {"label": "helper"})
    write_capture(
        run, "artifacts/processes/7", capture(7, target=True, status="oom"), {"label": "train"}
    )
    return run, manifest


def publish_selection(run, manifest, *, expected=None):
    records, inventory = runner._read_capture_roster(run, manifest)
    selected, inventory = runner._select_capture(records, inventory, expected)
    assert selected is not None, inventory
    relative = selected["capture_relative"]
    result = {
        **selected["capture"],
        "execution_capture": inventory,
        "selected_capture_relative": relative,
    }
    manifest.update(
        execution_capture=inventory,
        execution_entrypoint=result["execution_entrypoint"],
        selected_capture_relative=relative,
    )
    (run / "result.json").write_text(json.dumps(result))
    (run / "manifest.json").write_text(json.dumps(manifest))
    return result


def synthesize_unique_target_oom(result):
    """Relabel only a copied test capture; preserve original CPU evidence beside it."""
    run = Path(result["run_dir"])
    manifest = json.loads((run / "manifest.json").read_text())
    records, _ = runner._read_capture_roster(run, manifest)
    target = next(
        row
        for row in records
        if (
            (row["capture"] or {}).get("execution_entrypoint", {}).get("main_file")
            == "/source/train.py"
        )
    )
    raw = target["capture"]
    assert raw["status"] == "error" and raw["capture_complete"]
    path = run / target["capture_relative"] / "result.json"
    shutil.copyfile(path, path.with_name("result.cpu.json"))
    raw.update(
        status="oom",
        termination_reason="oom",
        oom={"traceback": "Explicit synthetic CUDA OOM from a real CPU exception"},
        env={**raw["env"], "device": "cuda"},
    )
    path.write_text(json.dumps(raw))
    shutil.copyfile(run / "manifest.json", run / "manifest.cpu.json")
    shutil.copyfile(run / "result.json", run / "result.cpu.json")
    selected = publish_selection(run, manifest)
    combined = {
        **result,
        **selected,
        "provenance": "synthetic_cuda_classification",
        "target_artifact_dir": str(run / selected["selected_capture_relative"]),
    }
    combined.pop("reason", None)
    (run / "result.json").write_text(json.dumps(combined))
    return combined


def test_unique_oom_child_binds_all_evidence_and_keeps_primary(captured_run, monkeypatch):
    import headroom.evidence_analysis as analysis
    from headroom.evidence import build_evidence, collect_sources

    run, manifest = captured_run
    primary = (run / "artifacts/result.json").read_bytes()
    result = publish_selection(run, manifest)
    assert result["execution_capture"]["captured_process_count"] == 2
    assert result["execution_capture"]["single_python_entrypoint"] is False
    assert result["execution_capture"]["selection"]["status"] == "unique_oom"
    assert result["selected_capture_relative"] == "artifacts/processes/7"
    assert result["parameter_count"] == 4
    assert runner.selected_capture_directory(run, result, manifest) == run / "artifacts/processes/7"
    assert (run / "artifacts/result.json").read_bytes() == primary
    sources, _ = collect_sources(run, manifest, {})
    assert [item["path"] for item in sources] == ["train.py"]

    class CorrectChildSnapshot(Exception):
        pass

    def observe(snapshot, received, **kwargs):
        assert snapshot == {"label": "train"}
        assert received["pid"] == 7 and received["parameter_count"] == 4
        raise CorrectChildSnapshot

    monkeypatch.setattr(analysis, "analyze_snapshot", observe)
    with pytest.raises(CorrectChildSnapshot):
        build_evidence(run)


@pytest.mark.parametrize("field", ["precision_observation", "parameter_count", "pairing_capture"])
def test_target_result_cannot_mix_primary_validation_fields(captured_run, field):
    run, manifest = captured_run
    result = publish_selection(run, manifest)
    result[field] = "different owner"
    with pytest.raises(ValueError, match="RESULT_MISMATCH"):
        runner.selected_capture_directory(run, result, manifest)


@pytest.mark.parametrize(
    "kind", ["second_oom", "duplicate_identity", "helper_error", "missing_record"]
)
def test_no_guess_when_oom_or_identity_is_ambiguous(captured_run, kind):
    run, manifest = captured_run
    if kind == "second_oom":
        other = capture(8, target=True, status="oom", args=["--batch", "4"])
        write_capture(run, "artifacts/processes/8", other)
    elif kind == "duplicate_identity":
        write_capture(run, "artifacts/processes/8", capture(8, target=True))
    elif kind == "helper_error":
        write_capture(run, "artifacts", capture(1, primary=True, status="error"))
    else:
        (run / "artifacts/processes/8").mkdir()
    records, inventory = runner._read_capture_roster(run, manifest)
    selected, inventory = runner._select_capture(records, inventory)
    assert selected is None and inventory["selection"]["reason"]


def test_replay_matches_successful_target_instead_of_new_primary(captured_run):
    run, manifest = captured_run
    first = publish_selection(run, manifest)
    descriptor = prepare_captured_command(
        run / "source", manifest["command"], first, manifest
    ).execution_entrypoint
    write_capture(run, "artifacts/processes/7", capture(7, target=True))
    selected = publish_selection(run, manifest, expected=descriptor)
    assert selected["status"] == "completed"
    assert selected["execution_capture"]["selection"]["status"] == "matched_replay"
    assert selected["pid"] == 7


@pytest.mark.parametrize("case", ["ancestor_link", "leaf_link", "oversize", "invalid_path"])
def test_capture_artifact_boundaries(captured_run, tmp_path, case):
    run, manifest = captured_run
    if case == "invalid_path":
        with pytest.raises(ValueError, match="INVALID_CAPTURE"):
            runner.capture_artifact_directory(run, "artifacts/processes/7/../../outside")
        return
    if case == "ancestor_link":
        outside = tmp_path / "moved"
        (run / "artifacts/processes").rename(outside)
        (run / "artifacts/processes").symlink_to(outside, target_is_directory=True)
    elif case == "leaf_link":
        path = run / "artifacts/processes/7/result.json"
        path.unlink()
        path.symlink_to(run / "artifacts/result.json")
    else:
        with (run / "artifacts/processes/7/result.json").open("wb") as target:
            target.truncate(runner.MAX_CAPTURE_RESULT_BYTES + 1)
    records, inventory = runner._read_capture_roster(run, manifest)
    selected, inventory = runner._select_capture(records, inventory)
    assert selected is None and not inventory["complete"]


def test_legacy_multicapture_cannot_silently_read_primary_snapshot(captured_run):
    run, manifest = captured_run
    with pytest.raises(ValueError, match="REQUIRED_FOR_MULTIPLE"):
        runner.selected_capture_directory(run, {}, manifest)


@pytest.mark.parametrize(
    "exit_code,timed_out,killed,cleanup,expected",
    [
        (1, False, False, True, "oom"),
        (42, False, False, True, "oom"),
        (0, False, False, True, "error"),
        (7, False, False, True, "error"),
        (137, False, True, True, "error"),
        (124, True, False, True, "timeout"),
        (1, False, False, False, "error"),
    ],
)
def test_root_exit_timeout_and_cleanup_cannot_be_hidden(
    tmp_path,
    monkeypatch,
    exit_code,
    timed_out,
    killed,
    cleanup,
    expected,
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("pass\n")

    def execute(*, run_dir, **kwargs):
        write_capture(run_dir, "artifacts", capture(1, primary=True))
        write_capture(run_dir, "artifacts/processes/7", capture(7, target=True, status="oom"))
        return {
            "state": {"ExitCode": exit_code, "OOMKilled": killed, "Running": False},
            "timed_out": timed_out,
            "cleanup_verified": cleanup,
            "image_id": "synthetic",
        }

    monkeypatch.setattr(runner.docker, "execute", execute)
    result = runner.run_argv(source, ["sh", "launch.sh"], run_root=tmp_path / "runs", device="cpu")
    assert result["status"] == expected
    assert result["execution"]["state"]["ExitCode"] == exit_code
    assert result["selected_capture_relative"] == "artifacts/processes/7"


def test_direct_fix_cannot_accept_completed_primary_with_failed_helper(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("pass\n")

    def execute(*, run_dir, **kwargs):
        write_capture(run_dir, "artifacts", capture(1, primary=True, target=True))
        write_capture(run_dir, "artifacts/processes/7", capture(7, status="error"))
        return {
            "state": {"ExitCode": 0, "OOMKilled": False, "Running": False},
            "timed_out": False,
            "cleanup_verified": True,
            "image_id": "synthetic",
        }

    monkeypatch.setattr(runner.docker, "execute", execute)
    result = runner.run_script(
        script,
        source_root=source,
        execution_argv=["python", "train.py"],
        script_args=["--batch", "8"],
        run_root=tmp_path / "runs",
        device="cpu",
    )
    assert result["status"] == "error"
    assert result["execution_capture"]["selection"]["selected_capture_relative"] is None


@pytest.mark.parametrize("helper_first", [False, True])
def test_real_cpu_helper_and_training_replay_target_args_and_reference(tmp_path, helper_first):
    from headroom.verify.runner import verify_script

    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(
        "import argparse, torch\np=argparse.ArgumentParser()\n"
        "p.add_argument('--batch', type=int, default=8)\na=p.parse_args()\n"
        "if a.batch == 8:\n    raise RuntimeError('synthetic CPU initial failure')\n"
        "m=torch.nn.Linear(1,1)\no=torch.optim.SGD(m.parameters(),lr=0.01)\n"
        "x=torch.ones(a.batch,1)\nfor _ in range(30):\n"
        "    o.zero_grad()\n    loss=m(x).square().mean()\n    loss.backward()\n    o.step()\n"
    )
    helper = "python -c \"print('helper-complete')\"\n"
    training = 'python train.py "$@"\nresult=$?\n'
    (source / "launch.sh").write_text(
        (helper + training if helper_first else training + helper) + 'exit "$result"\n'
    )
    command = ["/bin/sh", "launch.sh", "--batch", "8"]
    raw = runner.run_argv(source, command, run_root=tmp_path / "runs", device="cpu")
    baseline = synthesize_unique_target_oom(raw)
    run = Path(baseline["run_dir"])
    manifest = json.loads((run / "manifest.json").read_text())
    prepared = prepare_captured_command(run / "source", command, baseline, manifest)
    assert baseline["execution_capture"]["captured_process_count"] == 2
    assert not baseline["execution_capture"]["single_python_entrypoint"]
    assert prepared.script.name == "train.py"
    result = verify_script(
        baseline,
        prepared.script,
        baseline_script=prepared.script,
        candidate_source_root=prepared.source_root,
        baseline_source_root=prepared.source_root,
        execution_argv=command,
        execution_entrypoint=prepared.execution_entrypoint,
        script_args=["--batch", "4"],
        baseline_args=["--batch", "8"],
        run_root=tmp_path / "runs",
        device="cpu",
    )
    for observed, batch in [(result["candidate"], "4"), (result["reference"], "1")]:
        assert observed["steps"] == 20 and observed["execution_replay"]["matched"], observed
        assert observed["execution_capture"]["captured_process_count"] == 2
        assert observed["execution_capture"]["selection"]["status"] == "matched_replay"
        assert observed["execution_entrypoint"]["effective_startup_argv"][1:] == ["--batch", batch]
        directory = Path(observed["run_dir"])
        replay_manifest = json.loads((directory / "manifest.json").read_text())
        target_dir = runner.selected_capture_directory(directory, observed, replay_manifest)
        target_capture = json.loads((target_dir / "result.json").read_text())
        assert target_capture["steps"] == 20
    assert result["report"].target_met is False  # CPU execution is not GPU acceptance.


def test_real_cpu_python_parent_watch_hands_off_child_source(tmp_path):
    from headroom.watch import watch_command

    source = tmp_path / "parent-source"
    source.mkdir()
    (source / "train.py").write_text("raise RuntimeError('synthetic CPU failure')\n")
    (source / "launcher.py").write_text(
        "import subprocess, sys\n"
        "child = subprocess.call([sys.executable, 'train.py', '--batch', '8'])\n"
        "raise SystemExit(child)\n"
    )
    command = ["python", "launcher.py"]
    requests = []

    def lab(root, argv, **options):
        options["device"] = "cpu"
        return synthesize_unique_target_oom(runner.run_argv(root, argv, **options))

    def repair(request, **kwargs):
        requests.append(request)
        return {"status": "needs_human", "target_met": False}

    result = watch_command(
        command,
        source_root=source,
        run_root=tmp_path / "watch",
        device="cuda",
        lab_runner=lab,
        fix_runner=repair,
    )
    assert result["triggered"] and len(requests) == 1, result
    assert Path(requests[0].script).name == "train.py"
    assert requests[0].execution_argv == command
    assert requests[0].script_args == ["--batch", "8"]
    assert requests[0].execution_entrypoint["source_relative"] == "train.py"
    assert requests[0].execution_entrypoint["root_argv"] == command
    assert result["lab"]["execution_capture"]["single_python_entrypoint"] is False
    assert result["original_exit_code"] == 1


def test_legacy_manifest_multicapture_without_children_is_not_primary(captured_run):
    run, manifest = captured_run
    shutil.rmtree(run / "artifacts/processes")
    manifest["execution_capture"] = {"captured_process_count": 2}
    with pytest.raises(ValueError, match="REQUIRED_FOR_MULTIPLE"):
        runner.selected_capture_directory(run, {}, manifest)
