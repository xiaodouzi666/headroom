"""Watch dispatch safety, exit preservation, and real CPU Docker boundaries."""

import json
from pathlib import Path

import pytest

from headroom.watch import watch_command


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "train.py").write_text("print('original script')\n")
    return root


def captured(tmp_path, **changes):
    path = tmp_path / "lab" / ("1" * 32)
    path.mkdir(parents=True)
    (path / "source").mkdir()
    (path / "source/train.py").write_text("print('captured script')\n")
    return {
        "status": "oom",
        "protocol": "headroom.lab.v1",
        "termination_reason": "oom",
        "capture_complete": True,
        "cleanup_verified": True,
        "oom": {"traceback": "fixture"},
        "env": {"device": "cuda"},
        "run_dir": str(path),
        "execution": {"state": {"ExitCode": 1, "OOMKilled": False, "Running": False}},
        **changes,
    }


def fake_lab(**changes):
    def call(source, command, **options):
        return captured(Path(options["run_root"]).parent, **changes)

    return call


def fail_if_fix(*args, **kwargs):
    raise AssertionError("Non-OOM must never enter repair")


@pytest.mark.parametrize(
    "command",
    [
        "python train.py",
        [],
        [""],
        ["python", "train.py", "bad\x00value"],
        ["python", "train.py", "x" * 65536],
    ],
)
def test_invalid_argv_fails_before_execution(source, tmp_path, command):
    with pytest.raises((ValueError, TypeError)):
        watch_command(
            command,
            source_root=source,
            run_root=tmp_path / "runs",
            lab_runner=fail_if_fix,
            fix_runner=fail_if_fix,
        )


def test_symlink_script_parent_cannot_be_handed_to_repair(source, tmp_path):
    (source / "linked").symlink_to(source, target_is_directory=True)
    result = watch_command(
        ["python", "linked/train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(),
        fix_runner=fail_if_fix,
    )
    assert result["status"] == "needs_human" and not result["triggered"]
    assert result["repair_unavailable_reason"] == "REPAIR_SOURCE_UNAVAILABLE_OR_LINKED"


def test_fix_cannot_override_watched_script_or_device(source):
    with pytest.raises(ValueError, match="Unsupported"):
        watch_command(
            ["python", "train.py"],
            source_root=source,
            fix_options={"script": "/outside.py"},
            lab_runner=fail_if_fix,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "error"},
        {"capture_complete": False},
        {"termination_reason": "exception"},
        {"protocol": "forged"},
        {"env": {"device": "cpu"}},
        {"oom": None},
        {"execution": {"state": {"ExitCode": 137, "OOMKilled": True, "Running": False}}},
    ],
)
def test_non_cuda_or_incomplete_oom_never_triggers(source, tmp_path, changes):
    result = watch_command(
        ["python", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(**changes),
        fix_runner=fail_if_fix,
    )
    assert not result["triggered"]


def test_uncertain_cleanup_halts_before_fix(source, tmp_path):
    result = watch_command(
        ["python", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(cleanup_verified=False),
        fix_runner=fail_if_fix,
    )
    assert result["exit_code"] == 125 and result["status"] == "needs_human"


def test_oom_hands_snapshot_and_exact_argv_to_full_pipeline(source, tmp_path):
    calls = []

    def repair(request, **kwargs):
        calls.append((request, kwargs))
        assert Path(request.script).read_text() == "print('captured script')\n"
        return {"status": "completed", "target_met": True, "report_md": "fixture-report.md"}

    result = watch_command(
        ["python", "train.py", "--batch=16"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(),
        fix_runner=repair,
        fix_options={"budget_usd": "0.05"},
    )
    assert result["triggered"] and result["exit_code"] == 0
    assert result["original_exit_code"] == 1 and result["report_path"] == "fixture-report.md"
    assert calls[0][0].script_args == ["--batch=16"]
    assert calls[0][0].budget_usd == "0.05"
    assert Path(result["watch_report_path"]).exists()
    assert json.loads((Path(result["run_dir"]) / "watch.json").read_text())["triggered"]


def test_unfinished_repair_does_not_turn_oom_into_success(source, tmp_path):
    result = watch_command(
        ["python", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(),
        fix_runner=lambda *args, **kwargs: {"status": "needs_human", "target_met": False},
    )
    assert result["triggered"] and result["exit_code"] == 1


def test_fix_exception_is_recorded_without_echoing_message(source, tmp_path):
    def failed(*args, **kwargs):
        raise ValueError("fake-credential-must-not-appear")

    result = watch_command(
        ["python", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=fake_lab(),
        fix_runner=failed,
    )
    assert result["status"] == "failed" and result["error_type"] == "ValueError"
    assert "fake-credential" not in json.dumps(result)


@pytest.mark.parametrize(
    "body,exit_code",
    [
        ("print('successful')", 0),
        ("raise SystemExit(7)", 7),
        ("print('CUDA out of memory')\nraise RuntimeError('other failure')", 1),
        ("import torch\nraise torch.OutOfMemoryError('CPU out of memory')", 1),
    ],
)
def test_real_cpu_docker_preserves_exit_and_never_calls_fix(source, tmp_path, body, exit_code):
    (source / "train.py").write_text(body + "\n")
    result = watch_command(
        ["python", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        device="cpu",
        max_seconds=30,
        fix_runner=fail_if_fix,
    )
    assert result["exit_code"] == exit_code, result
    assert not result["triggered"] and result["lab"]["cleanup_verified"]
    assert result["lab"]["execution"]["state"]["ExitCode"] == exit_code
    assert Path(result["stderr_path"]).exists()


@pytest.mark.parametrize(
    "command",
    [
        ["python", "-m", "trainer.module"],
        ["python", "-c", "raise RuntimeError('fixture')"],
        ["python", "-OO", "train.py"],
        ["/bin/sh", "-c", "python train.py"],
    ],
)
def test_observation_only_cuda_oom_does_not_rewrite_invocation(source, tmp_path, command):
    observed = []

    def lab(root, argv, **options):
        observed.append(argv)
        return captured(Path(options["run_root"]).parent)

    result = watch_command(
        command,
        source_root=source,
        run_root=tmp_path / "runs",
        lab_runner=lab,
        fix_runner=fail_if_fix,
    )
    assert observed == [command]
    assert result["status"] == "needs_human" and result["original_exit_code"] == 1
    assert result["exit_code"] == 1 and not result["triggered"]
    assert not result["repair_supported"] and result["repair_unavailable_reason"]


def test_missing_injection_does_not_turn_stderr_text_into_oom_evidence(source, tmp_path):
    result = watch_command(
        ["python", "-I", "train.py"],
        source_root=source,
        run_root=tmp_path / "runs",
        fix_runner=fail_if_fix,
        lab_runner=fake_lab(
            status="error",
            capture_complete=False,
            reason="CAPTURE_RESULT_MISSING_OR_INVALID",
            oom=None,
        ),
    )
    assert result["capture_status"] == "unknown" and result["status"] == "needs_human"
    assert result["exit_code"] == 1 and not result["triggered"]


@pytest.mark.parametrize(
    "command,code",
    [
        (["python", "-c", "print('inline')\nprint('second line')"], 0),
        (["python", "-O", "-c", "assert False; raise SystemExit(9)"], 9),
        (["python", "-I", "-c", "raise SystemExit(11)"], 11),
        (["python", "-S", "-c", "raise SystemExit(12)"], 12),
        (["/bin/sh", "-c", "printf 'plain command\n'; exit 13"], 13),
        (["/usr/bin/printf", "%s", "literal;$(not-a-shell)"], 0),
    ],
)
def test_real_cpu_argv_and_interpreter_semantics(source, tmp_path, command, code):
    result = watch_command(
        command,
        source_root=source,
        run_root=tmp_path / "runs",
        device="cpu",
        max_seconds=30,
        fix_runner=fail_if_fix,
    )
    assert result["exit_code"] == code, result
    assert not result["triggered"] and result["lab"]["cleanup_verified"]
    manifest = json.loads((Path(result["lab"]["run_dir"]) / "manifest.json").read_text())
    assert manifest["command"][1:] == command[1:]
    if "-I" in command or "-S" in command or command[0] != "python":
        assert result["capture_status"] == "unknown" and result["status"] == "needs_human"


def test_real_cpu_module_keeps_package_imports_and_argv(source, tmp_path):
    package = source / "package"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "helper.py").write_text("VALUE = 17\n")
    (package / "entry.py").write_text(
        "from .helper import VALUE\nimport sys\nassert sys.argv[1:] == ['literal;arg']\n"
        "assert __package__ == 'package'\nraise SystemExit(VALUE)\n"
    )
    result = watch_command(
        ["python", "-m", "package.entry", "literal;arg"],
        source_root=source,
        run_root=tmp_path / "runs",
        device="cpu",
        max_seconds=30,
        fix_runner=fail_if_fix,
    )
    assert result["exit_code"] == 17 and result["lab"]["cleanup_verified"]
    assert result["capture_status"] == "complete" and not result["repair_supported"]


def test_real_cpu_supported_flags_match_repair_lab_environment(source, tmp_path):
    from headroom.lab.runner import run_script

    (source / "train.py").write_text(
        "import json, sys\n"
        "print('FLAGS:' + json.dumps([sys.flags.dont_write_bytecode, "
        "sys.flags.no_user_site, sys.stdout.write_through, sys.argv[1:]]))\n"
    )
    arguments = ["literal;$(not-a-shell)"]
    watched = watch_command(
        ["python", "-uBs", "train.py", *arguments],
        source_root=source,
        run_root=tmp_path / "runs",
        device="cpu",
        max_seconds=30,
        fix_runner=fail_if_fix,
    )
    replay = run_script(
        source / "train.py",
        script_args=arguments,
        source_root=source,
        run_root=tmp_path / "replay",
        device="cpu",
        max_seconds=30,
    )

    def flags(path):
        return next(
            line for line in Path(path).read_text().splitlines() if line.startswith("FLAGS:")
        )

    assert watched["exit_code"] == 0 and watched["repair_supported"]
    assert replay["status"] == "completed" and replay["cleanup_verified"]
    assert flags(watched["stdout_path"]) == flags(Path(replay["run_dir"]) / "stdout.log")
