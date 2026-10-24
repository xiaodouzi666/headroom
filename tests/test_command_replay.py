"""CPU/fixture checks for exact Python command replay; no API or GPU."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.execution import parse_command, prepare_local_command, replay_argv
from headroom.lab.runner import run_script


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("No network permitted in command-replay tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize(
    "prefix",
    [
        ["python", "-O", "-W", "ignore", "train.py"],
        ["python3", "-OO", "-Xdev", "-m", "pkg.entry"],
        ["python", "-u", "-mpkg"],
        ["python", "--", "/source/train.py"],
    ],
)
def test_only_target_argv_changes(prefix):
    original = [*prefix, "--batch", "8", "literal spaced;$(text)"]
    assert replay_argv(original, ["--batch", "1"]) == [*prefix, "--batch", "1"]
    assert parse_command(original).script_args == ("--batch", "8", "literal spaced;$(text)")


def test_module_and_package_sources_are_located_without_imports(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("raise AssertionError('never host import')\n")
    (package / "entry.py").write_text("from . import value\n")
    (package / "__main__.py").write_text("raise AssertionError('never host execute')\n")
    entry = prepare_local_command(tmp_path, "python -O -m pkg.entry 'two words'")
    assert entry.script == package / "entry.py"
    assert entry.script_args == ("two words",)
    assert entry.execution_argv == ("python", "-O", "-m", "pkg.entry", "two words")
    assert prepare_local_command(tmp_path, ["python", "-mpkg"]).script == package / "__main__.py"
    assert (
        prepare_local_command(tmp_path, ["python", "/source/pkg/entry.py"]).script == entry.script
    )


@pytest.mark.parametrize(
    "argv,reason",
    [
        (["python", "-I", "train.py"], "SITECUSTOMIZE_DISABLED"),
        (["python", "-S", "-m", "pkg"], "SITECUSTOMIZE_DISABLED"),
        (["python", "-c", "print(1)"], "PYTHON_INLINE_REPAIR_UNSUPPORTED"),
        (["/bin/sh", "-c", "python train.py"], "COMMAND_REPAIR_UNSUPPORTED"),
        (["python", "-m", "absent"], "REPAIR_SOURCE_UNAVAILABLE_OR_LINKED"),
    ],
)
def test_unreplayable_or_missing_source_has_explicit_reason(tmp_path, argv, reason):
    with pytest.raises(ValueError, match=reason):
        prepare_local_command(tmp_path, argv)


def test_lab_replay_uses_command_mode_and_refuses_wrong_edit_target(tmp_path, monkeypatch):
    import headroom.lab.runner as lab

    (tmp_path / "train.py").write_text("pass\n")
    (tmp_path / "other.py").write_text("pass\n")
    observed = []
    monkeypatch.setattr(lab, "_run", lambda **kw: observed.append(kw) or {"status": "fixture"})
    command = ["python3", "-O", "-W", "error", "-m", "train", "--batch=8"]
    run_script(
        tmp_path / "train.py",
        source_root=tmp_path,
        execution_argv=command,
        script_args=["--batch=1"],
        device="cpu",
    )
    assert observed[0]["command"] == ["/opt/venv/bin/python", *command[1:-1], "--batch=1"]
    assert observed[0]["script_relative"] is None
    with pytest.raises(ValueError, match="supplied script"):
        run_script(
            tmp_path / "other.py", source_root=tmp_path, execution_argv=command, device="cpu"
        )
    assert len(observed) == 1


def test_candidate_and_small_batch_reference_keep_original_interpreter_prefix(
    tmp_path, monkeypatch
):
    import headroom.verify.runner as verify

    script = tmp_path / "train.py"
    script.write_text(
        "import argparse\np = argparse.ArgumentParser()\np.add_argument('--batch', type=int, default=8)\n"
    )
    command = ["python", "-O", "-W", "ignore", "-m", "train", "--batch", "8"]
    calls = []

    def execute(script, **options):
        calls.append(options)
        return {"status": "completed", "steps": 20, "env": {"seed": 1337}, "loss_series": []}

    report = SimpleNamespace(notes=[], model_dump=dict)
    monkeypatch.setattr(verify, "run_script", execute)
    monkeypatch.setattr(verify, "compare_runs", lambda *a, **k: report)
    monkeypatch.setattr(
        verify,
        "derive_pairing",
        lambda *a: {"checks": {}, "source": "offline_fixture", "reasons": []},
    )
    result = verify.verify_script(
        {"status": "oom", "env": {"seed": 1337}},
        script,
        baseline_script=script,
        execution_argv=command,
        script_args=["--batch", "4"],
        baseline_args=["--batch", "8"],
        device="cpu",
    )
    assert result["reference"] is not None
    assert len(calls) == 2
    assert all(call["execution_argv"] == command for call in calls)
    assert calls[0]["script_args"] == ["--batch", "4"]
    assert calls[1]["script_args"] == ["--batch", "1"]


@pytest.mark.parametrize("module", [False, True])
def test_real_cpu_repair_backend_preserves_flags_imports_argv_and_source_context(tmp_path, module):
    from headroom.evidence import collect_sources

    source = tmp_path / "source"
    package = source / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "helper.py").write_text("VALUE = 17\n")
    script = package / "entry.py"
    script.write_text(
        ("from .helper import VALUE\n" if module else "from helper import VALUE\n")
        + "import json, sys\n"
        + "print('REPLAY:' + json.dumps([VALUE, sys.flags.optimize, sys._xoptions, __package__, sys.argv[1:]]))\n"
    )
    target = ["-m", "pkg.entry"] if module else ["pkg/entry.py"]
    command = ["python", "-O", "-X", "dev", *target, "--batch", "8"]
    prepared = prepare_local_command(source, command)
    runs = []
    for arguments in (prepared.script_args, ("--batch", "1")):
        result = run_script(
            prepared.script,
            source_root=source,
            execution_argv=command,
            script_args=arguments,
            run_root=tmp_path / "runs",
            device="cpu",
            max_seconds=30,
        )
        assert result["status"] == "completed" and result["capture_complete"]
        assert result["cleanup_verified"]
        run = Path(result["run_dir"])
        manifest = json.loads((run / "manifest.json").read_text())
        assert manifest["command"] == ["/opt/venv/bin/python", *command[1:-2], *arguments]
        line = next(
            line
            for line in (run / "stdout.log").read_text().splitlines()
            if line.startswith("REPLAY:")
        )
        value = json.loads(line.removeprefix("REPLAY:"))
        assert value[:3] == [17, 1, {"dev": True}]
        assert value[3] == ("pkg" if module else None)
        assert value[4] == list(arguments)
        files, warnings = collect_sources(run, manifest, {})
        assert {"pkg/entry.py", "pkg/helper.py"} <= {item["path"] for item in files}, warnings
        runs.append(result)
    assert len(runs) == 2


def test_repository_preparation_retains_module_command_without_running_source(
    tmp_path, monkeypatch
):
    import io
    import tarfile

    from headroom import repository

    commit = "a" * 40
    contents = {
        "pkg/__init__.py": "raise AssertionError('must not execute on host')\n",
        "pkg/entry.py": "from . import value\n",
    }

    def git(directory, *args, **kwargs):
        if args[0] == "rev-parse":
            return commit
        if args[0] == "archive":
            archive = Path(
                next(arg.removeprefix("--output=") for arg in args if arg.startswith("--output="))
            )
            with tarfile.open(archive, "w") as output:
                for name, content in contents.items():
                    data = content.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    output.addfile(info, io.BytesIO(data))
        return ""

    monkeypatch.setattr(repository, "_git", git)
    command = ["python3", "-O", "-W", "ignore", "-m", "pkg.entry", "--batch=8"]
    prepared = repository.prepare_repository(
        "https://github.com/fixture/project", commit, command, destination=tmp_path / "prepared"
    )
    assert prepared.script.relative_to(prepared.source_root).as_posix() == "pkg/entry.py"
    assert prepared.script_args == ("--batch=8",)
    assert prepared.execution_argv == tuple(command)
    assert prepared.metadata["requested_argv"] == command
    assert prepared.metadata["execution_argv"] == command
    assert prepared.metadata["code_executed"] is False
