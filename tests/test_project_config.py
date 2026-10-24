"""Project YAML and CLI precedence, using offline request capture only."""

import os

import pytest
from typer.testing import CliRunner

from headroom.cli import app
from headroom.project_config import (
    ProjectConfigError,
    configured_script,
    find_project_config,
    load_project_config,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in project configuration tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def capture(monkeypatch, tmp_path):
    import headroom.orchestrator

    monkeypatch.chdir(tmp_path)
    captured = []

    def fake(request, **kwargs):
        captured.append(request)
        return {"status": "completed", "report": {}}

    monkeypatch.setattr(headroom.orchestrator, "run_fix", fake)
    return captured


def write_config(tmp_path, content):
    path = tmp_path / "headroom.yaml"
    path.write_text(content)
    return path


def test_config_defaults_do_not_change_plain_script_cli(capture):
    result = runner.invoke(app, ["fix", "offline.py"])
    assert result.exit_code == 0, result.output
    request = capture[0]
    assert request.target == "fix-oom" and request.max_steps == 20 and request.seed == 1337
    assert request.reclaim_reduction_pct == 30
    assert request.policy.allow_batch_grad_accum is True
    assert request.policy.max_throughput_regression_pct == 25
    assert request.execution_argv is None and request.repository_mode is False
    assert request.script_args == [] and request.source_root is None


def test_config_script_runtime_and_all_existing_policy_fields(tmp_path, capture):
    write_config(
        tmp_path,
        """version: 1
script: train.py
script_args: [--batch, "8"]
target: fit:16GB
policy:
  allow_numerics_change: true
  allow_model_change: false
  allow_batch_grad_accum: false
  max_throughput_regression_pct: 0
max_steps: 7
max_seconds: 41
seed: 0
device: cpu
max_rounds: 2
""",
    )
    result = runner.invoke(app, ["fix"])
    assert result.exit_code == 0, result.output
    request = capture[0]
    assert request.script == str(tmp_path / "train.py")
    assert request.source_root == str(tmp_path)
    assert request.script_args == ["--batch", "8"]
    assert request.target == "fit:16GB"
    assert request.policy.model_dump() == {
        "allow_numerics_change": True,
        "allow_model_change": False,
        "allow_batch_grad_accum": False,
        "max_throughput_regression_pct": 0,
    }
    assert (
        request.max_steps,
        request.max_seconds,
        request.seed,
        request.device,
        request.max_rounds,
    ) == (7, 41, 0, "cpu", 2)
    assert request.budget_usd == "0.6" and request.daily_budget_usd == "12"
    assert request.runtime_profile is None and request.repository_mode is False


def test_explicit_cli_false_zero_and_default_values_override_yaml(tmp_path, capture):
    path = write_config(
        tmp_path,
        """script: ignored.py
script_args: [--batch, "8"]
target: fit:16GB
policy:
  allow_numerics_change: true
  allow_batch_grad_accum: false
  max_throughput_regression_pct: 30
max_steps: 7
max_seconds: 41
seed: 42
device: cpu
max_rounds: 2
""",
    )
    result = runner.invoke(
        app,
        [
            "fix",
            "chosen.py",
            "--config",
            str(path),
            "--target",
            "fix-oom",
            "--no-allow-numerics-change",
            "--allow-batch-grad-accum",
            "--max-throughput-regression-pct",
            "0",
            "--max-steps",
            "20",
            "--max-seconds",
            "120",
            "--seed",
            "0",
            "--device",
            "cuda",
            "--max-rounds",
            "6",
            "--",
            "--batch",
            "2",
            "literal space",
        ],
    )
    assert result.exit_code == 0, result.output
    request = capture[0]
    assert request.script == "chosen.py" and request.script_args == [
        "--batch",
        "2",
        "literal space",
    ]
    assert request.target == "fix-oom" and request.seed == 0
    assert (request.max_steps, request.max_seconds, request.device, request.max_rounds) == (
        20,
        120,
        "cuda",
        6,
    )
    assert request.policy.allow_numerics_change is False
    assert request.policy.allow_batch_grad_accum is True
    assert request.policy.max_throughput_regression_pct == 0


def test_negative_batch_flag_does_not_become_target_argv(capture):
    result = runner.invoke(
        app,
        [
            "fix",
            "offline.py",
            "--no-allow-batch-grad-accum",
            "--max-throughput-regression-pct",
            "12.5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert capture[0].policy.allow_batch_grad_accum is False
    assert capture[0].policy.max_throughput_regression_pct == 12.5
    assert capture[0].script_args == []


@pytest.mark.parametrize("value", ["-1", "1001", "nan", "inf"])
def test_cli_rejects_invalid_throughput_limits(capture, value):
    result = runner.invoke(app, ["fix", "offline.py", "--max-throughput-regression-pct", value])
    assert result.exit_code != 0
    assert not capture


@pytest.mark.parametrize(
    "content",
    [
        "provider: private-provider\n",
        "runtime_profile: private.json\n",
        "budget: 100\n",
        "daily_budget: 100\n",
        "research: true\n",
        "live: true\n",
        "repository_mode: true\n",
        "acceptance_scope: repository\n",
        "NEBIUS_API_KEY: secret-value-must-never-echo\n",
        "policy: {allow_numerics_change: 'false'}\n",
        "policy: {max_throughput_regression_pct: .nan}\n",
        "policy: {max_throughput_regression_pct: .inf}\n",
        "policy: {extra: true}\n",
        "max_steps: 0\n",
        "max_seconds: 3601\n",
        "seed: true\n",
        "seed: 4294967296\n",
        "device: tpu\n",
        "max_rounds: 7\n",
        "target: reclaim:10GB\n",
        "script: ../train.py\n",
        "script: /tmp/train.py\n",
        "script_args: [1]\n",
        "script_args: ['\\0']\n".replace("'\\0'", '"\\0"'),
        "version: true\n",
        "batch: {arg: --other, value: 4}\n",
        "batch: {arg: --batch, value: true}\n",
        "batch: 0\n",
        "target: fix-oom\ntarget: reclaim\n",
        "policy: {allow_numerics_change: false, allow_numerics_change: true}\n",
        "!!python/object/apply:os.system ['false']\n",
        "[]\n",
    ],
)
def test_rejects_unsupported_or_unsafe_config_without_echoing_values(tmp_path, capture, content):
    path = write_config(tmp_path, content)
    with pytest.raises(ProjectConfigError):
        load_project_config(path)
    result = runner.invoke(app, ["fix", "offline.py", "--config", str(path)])
    assert result.exit_code == 1 and not capture
    assert "secret-value-must-never-echo" not in result.output


@pytest.mark.parametrize(
    "content",
    [
        "batch: {arg: --batch_size, value: 32}\n",
        "batch_arg: --batch-size\nbatch: 16\n",
        "batch_arg: --batch\n",
    ],
)
def test_preserves_legacy_batch_discovery_config(tmp_path, capture, content):
    from headroom.verify.runner import discover_batch

    path = write_config(tmp_path, content)
    script = tmp_path / "train.py"
    script.write_text("pass\n")
    project = load_project_config(path)
    assert "batch" in project.model_fields_set or "batch_arg" in project.model_fields_set
    batch = discover_batch(script)
    assert batch["found"] and batch["reference_batch"] == 1
    result = runner.invoke(app, ["fix", str(script)])
    assert result.exit_code == 0, result.output
    assert capture[0].script_args == []


def test_only_selected_project_is_autodiscovered(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    path = write_config(project, "target: reclaim\n")
    assert find_project_config(None, script=project / "train.py", source_root=None) == path
    assert find_project_config(None, script=None, source_root=project) == path
    assert (
        find_project_config(None, script=None, source_root=project, remote_repository=True) is None
    )
    assert find_project_config(path, script=None, source_root=None, remote_repository=True) == path


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory", "oversized", "missing"])
def test_only_bounded_regular_files_are_read(tmp_path, kind):
    path = tmp_path / "headroom.yaml"
    if kind == "symlink":
        target = tmp_path / "target.yaml"
        target.write_text("{}")
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    elif kind == "oversized":
        path.write_text("#" * 16385)
    with pytest.raises(ProjectConfigError):
        load_project_config(path)


def test_config_script_cannot_escape_via_symlink(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    path = write_config(project, "script: linked.py\n")
    (project / "linked.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(ProjectConfigError):
        configured_script(load_project_config(path), path)


@pytest.mark.parametrize(
    "command,relative,args",
    [
        ('python -u -W ignore train.py --label "two words"', "train.py", ["--label", "two words"]),
        ("python3 -u -m package.train --batch 4", "package/train.py", ["--batch", "4"]),
    ],
)
def test_local_command_preserves_python_entrypoint_without_running_source(
    tmp_path, capture, command, relative, args
):
    import shlex

    project = tmp_path / "source"
    script = project / relative
    script.parent.mkdir(parents=True)
    script.write_text("raise AssertionError('User code must not execute')\n")
    write_config(project, "script: ignored.py\nscript_args: [--ignored]\nseed: 0\n")
    result = runner.invoke(app, ["fix", "--source-root", str(project), "--cmd", command])
    assert result.exit_code == 0, result.output
    request = capture[0]
    assert request.script == str(script) and request.source_root == str(project)
    assert request.execution_argv == shlex.split(command)
    assert request.script_args == args and request.seed == 0
    assert request.repository_mode is True


@pytest.mark.parametrize(
    "extra",
    [
        ["--cmd", "python train.py"],
        ["--source-root", ".", "--cmd", "python train.py", "train.py"],
        ["--source-root", ".", "--cmd", "python train.py", "--", "--extra"],
        ["--source-root", ".", "--cmd", "python train.py", "--ref", "a" * 40],
    ],
)
def test_ambiguous_local_commands_do_not_dispatch(capture, extra):
    result = runner.invoke(app, ["fix", *extra])
    assert result.exit_code == 1 and not capture


def test_remote_repository_does_not_load_cwd_configuration(tmp_path, capture, monkeypatch):
    from types import SimpleNamespace

    import headroom.repository

    write_config(tmp_path, "provider: forbidden-setting\n")
    prepared = SimpleNamespace(
        script=tmp_path / "train.py",
        source_root=tmp_path,
        script_args=("--batch", "4"),
        source_profile=None,
        execution_argv=("python", "-u", "train.py", "--batch", "4"),
    )
    monkeypatch.setattr(headroom.repository, "prepare_repository", lambda *a: prepared)
    result = runner.invoke(
        app,
        [
            "fix",
            "--repo",
            "https://github.com/a/b",
            "--ref",
            "a" * 40,
            "--cmd",
            "python -u train.py --batch 4",
        ],
    )
    assert result.exit_code == 0, result.output
    assert capture[0].execution_argv == list(prepared.execution_argv)
    assert capture[0].target == "fix-oom" and capture[0].repository_mode is True


def test_explicit_config_is_resolved_from_its_own_directory(tmp_path, capture):
    project = tmp_path / "other"
    project.mkdir()
    path = write_config(project, "script: nested/train.py\nscript_args: [--tiny]\n")
    result = runner.invoke(app, ["fix", "--config", str(path)])
    assert result.exit_code == 0, result.output
    assert capture[0].script == str(project / "nested/train.py")
    assert capture[0].source_root == str(project)
    assert capture[0].script_args == ["--tiny"]


def test_remote_explicit_config_controls_policy_but_not_launch_argv(tmp_path, capture, monkeypatch):
    from types import SimpleNamespace

    import headroom.repository

    path = write_config(
        tmp_path,
        "script: ignored.py\nscript_args: [--ignored]\n"
        "target: reclaim\npolicy: {allow_batch_grad_accum: false}\n",
    )
    prepared = SimpleNamespace(
        script=tmp_path / "train.py",
        source_root=tmp_path,
        script_args=("--batch", "4"),
        source_profile=None,
        execution_argv=("python", "-u", "train.py", "--batch", "4"),
    )
    monkeypatch.setattr(headroom.repository, "prepare_repository", lambda *a: prepared)
    result = runner.invoke(
        app,
        [
            "fix",
            "--repo",
            "https://github.com/a/b",
            "--ref",
            "a" * 40,
            "--cmd",
            "python -u train.py --batch 4",
            "--config",
            str(path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert capture[0].target == "reclaim"
    assert capture[0].policy.allow_batch_grad_accum is False
    assert capture[0].script_args == ["--batch", "4"]
    assert capture[0].execution_argv == list(prepared.execution_argv)


@pytest.mark.parametrize("cli_value,expected", [(None, 20), ("30", 30), ("12.5", 12.5)])
def test_reclaim_target_cli_overrides_yaml_without_changing_default(
    tmp_path, capture, cli_value, expected
):
    write_config(tmp_path, "script: train.py\ntarget: reclaim\nreclaim_reduction_pct: 20\n")
    extra = ["--reclaim-reduction-pct", cli_value] if cli_value is not None else []
    result = runner.invoke(app, ["fix", *extra])
    assert result.exit_code == 0, result.output
    assert capture[0].target == "reclaim"
    assert capture[0].reclaim_reduction_pct == expected


@pytest.mark.parametrize("value", ["0", "-1", "101", "nan", "inf"])
def test_reclaim_cli_invalid_target_does_not_dispatch(capture, value):
    result = runner.invoke(app, ["fix", "train.py", "--reclaim-reduction-pct", value])
    assert result.exit_code != 0 and not capture


@pytest.mark.parametrize("value", ["0", "-1", "101", ".nan", ".inf", "true", "'20'"])
def test_reclaim_yaml_rejects_invalid_target(tmp_path, capture, value):
    path = write_config(tmp_path, f"script: train.py\nreclaim_reduction_pct: {value}\n")
    with pytest.raises(ProjectConfigError):
        load_project_config(path)
    result = runner.invoke(app, ["fix"])
    assert result.exit_code == 1 and not capture
