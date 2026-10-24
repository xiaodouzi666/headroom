"""Read-only command classification; no subprocess, network or GPU execution."""

import pytest

from headroom.repository import parse_python_command, parse_watch_command


@pytest.mark.parametrize("flags", [[], ["-u"], ["-B", "-s"], ["-uBs"]])
def test_script_flags_equivalent_to_fixed_lab_environment(flags):
    argv = ["python", *flags, "nested/train.py", "--batch=4", "literal;argument"]
    parsed = parse_watch_command(argv)
    assert parsed.argv == tuple(argv)
    assert parsed.script == "nested/train.py" and parsed.script_args == tuple(argv[-2:])
    assert parsed.repair_supported and parsed.capture_expected


@pytest.mark.parametrize("flags", [["-OO"], ["-W", "error"], ["-X", "dev"], ["-x"], ["-i"]])
def test_flags_that_change_execution_are_not_dropped_for_repair(flags):
    argv = ["python", *flags, "train.py", "--batch=4"]
    parsed = parse_watch_command(argv)
    assert parsed.argv == tuple(argv) and parsed.capture_expected
    assert (
        not parsed.repair_supported and parsed.repair_reason == "INTERPRETER_FLAGS_REQUIRE_REPLAY"
    )


@pytest.mark.parametrize("flag", ["-E", "-I", "-S", "-uS"])
def test_capture_disabling_flags_are_observed_as_the_original_argv(flag):
    parsed = parse_watch_command(["python", flag, "train.py"])
    assert not parsed.capture_expected and not parsed.repair_supported


def test_module_inline_and_generic_argv_are_classified_without_host_shell():
    module = parse_watch_command(["python3", "-u", "-m", "package.train", "--help"])
    assert module.kind == "python_module" and module.python_flags == ("-u",)
    inline = parse_watch_command(["python", "-c", "print('x')\nraise SystemExit(0)"])
    assert inline.kind == "python_inline" and not inline.repair_supported
    command = ["/bin/sh", "-c", "printf '%s' '$NOT_A_HOST_VARIABLE'"]
    parsed = parse_watch_command(command)
    assert parsed.kind == "command" and parsed.argv == tuple(command)
    assert not parsed.repair_supported


def test_repository_parser_remains_strict_for_existing_fix_contract():
    for command in ("python -m trainer", "python -O train.py", "sh train.sh"):
        with pytest.raises(ValueError):
            parse_python_command(command)
    assert parse_python_command("python train.py --batch=4") == ("train.py", ("--batch=4",))


def test_run_argv_preserves_flags_arguments_and_uses_only_docker_core(tmp_path, monkeypatch):
    from headroom.lab import runner

    observed = []

    def isolated(**kwargs):
        observed.append(kwargs)
        return {"status": "fixture"}

    monkeypatch.setattr(runner, "_run", isolated)
    command = ["python3", "-O", "-m", "package.train", "literal;$(no-host-shell)"]
    runner.run_argv(tmp_path, command, device="cpu")
    assert observed[0]["command"] == ["/opt/venv/bin/python", *command[1:]]
    assert observed[0]["script_relative"] is None
    assert observed[0]["source_root"] == tmp_path
    runner.run_argv(tmp_path, ["/bin/sh", "-c", "exit 7"], device="cpu")
    assert observed[1]["command"] == ["/bin/sh", "-c", "exit 7"]
    assert command[0] == "python3"
