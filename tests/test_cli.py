"""CLI contract tests with no workloads, provider requests, or network access."""

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from headroom.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in CLI unit tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize("flags", [[], ["--validate-only", "--dry-run"], ["--dry-run", "--live"]])
def test_eval_requires_exactly_one_mode(flags):
    assert runner.invoke(app, ["eval", *flags]).exit_code == 2


@pytest.mark.parametrize("status,expected", [("valid", 0), ("incomplete", 78)])
def test_validate_only_exit_code_reflects_missing_inputs(monkeypatch, status, expected):
    import headroom.evaluation

    called = []
    monkeypatch.setattr(
        headroom.evaluation,
        "validate_manifest",
        lambda path: called.append(path) or {"status": status, "executed": False},
    )
    result = runner.invoke(app, ["eval", "--validate-only"])
    assert result.exit_code == expected
    assert len(called) == 1
    assert json.loads(result.stdout)["executed"] is False


@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"accepted": True}, 0),
        ({"accepted": False, "selected_baselines_passed": True}, 0),
        ({"accepted": False, "selected_baselines_passed": False}, 1),
    ],
)
def test_dry_run_exit_code_and_actual_execution_arguments(monkeypatch, fields, expected):
    import headroom.evaluation

    captured = {}

    def fake(path, **kwargs):
        captured.update(kwargs)
        return {"status": "not_accepted", **fields}

    monkeypatch.setattr(headroom.evaluation, "execute_baselines", fake)
    result = runner.invoke(app, ["eval", "--dry-run", "--scenario", "s1_batch_too_big"])
    assert result.exit_code == expected
    assert captured["execute"] is True
    assert captured["scenario_ids"] == ["s1_batch_too_big"]


@pytest.mark.parametrize(
    "extra",
    [
        ["--device", "cpu"],
        ["--max-seconds", "30"],
    ],
)
def test_live_never_silently_ignores_execution_constraints(monkeypatch, extra):
    import headroom.evaluation

    monkeypatch.setattr(
        headroom.evaluation,
        "run_campaign",
        lambda *args, **kwargs: pytest.fail("Invalid live constraints must not dispatch"),
    )
    assert runner.invoke(app, ["eval", "--live", *extra]).exit_code == 2


@pytest.mark.parametrize(
    "status,rows,expected",
    [
        ("finished", [{"status": "completed"}], 0),
        ("finished", [{"status": "error"}], 1),
        ("partial", [{"status": "pending"}], 1),
    ],
)
def test_live_adapter_keeps_string_budgets_and_failure_status(monkeypatch, status, rows, expected):
    import headroom.evaluation

    captured = {}

    def fake(path, **kwargs):
        captured.update(kwargs)
        return {"status": status, "rows": rows}

    monkeypatch.setattr(headroom.evaluation, "run_campaign", fake)
    result = runner.invoke(
        app,
        [
            "eval",
            "--live",
            "--runtime-profile",
            "offline-fixture.json",
            "--conditions",
            "full_ultra, full_super",
            "--budget",
            "0.50",
            "--campaign-budget",
            "1",
        ],
    )
    assert result.exit_code == expected
    assert captured["execute"] is True and captured["live_authorized"] is True
    assert captured["conditions"] == ("full_ultra", "full_super")
    assert captured["per_run_budget_usd"] == "0.50"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", 0),
        ("needs_human", 78),
        ("budget_exceeded", 78),
        ("failed", 1),
        ("timeout", 124),
        ("unexpected_state", 1),
    ],
)
def test_fix_exit_status_is_not_false_success(monkeypatch, status, expected):
    import headroom.orchestrator

    monkeypatch.setattr(
        headroom.orchestrator,
        "run_fix",
        lambda *args, **kwargs: {"status": status, "run_id": "a" * 32, "report": {}},
    )
    result = runner.invoke(app, ["fix", "offline.py", "--runtime-profile", "missing.json"])
    assert result.exit_code == expected


def test_pinned_repository_adapter_preserves_argv_and_source_profile(monkeypatch, tmp_path):
    import headroom.orchestrator
    import headroom.repository

    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("VALUE=1\n")
    prepared = SimpleNamespace(
        script=script,
        source_root=source,
        script_args=("--dataset=headroom_synthetic",),
        source_profile="pinned_nanogpt",
    )
    monkeypatch.setattr(headroom.repository, "prepare_repository", lambda *args: prepared)
    captured = []

    def fake(request, **kwargs):
        captured.append(request)
        return {"status": "needs_human", "report": {}}

    monkeypatch.setattr(headroom.orchestrator, "run_fix", fake)
    result = runner.invoke(
        app,
        [
            "fix",
            "--repo",
            "https://github.com/karpathy/nanoGPT.git",
            "--ref",
            "a" * 40,
            "--cmd",
            "python train.py --dataset=/input",
            "--target",
            "fit:22GB",
        ],
    )
    assert result.exit_code == 78
    assert captured[0].source_profile == "pinned_nanogpt"
    assert captured[0].script_args == ["--dataset=headroom_synthetic"]
    assert captured[0].source_root == str(source)


@pytest.mark.parametrize("code", [0, 7, 124, 125])
def test_watch_preserves_non_oom_exit_code_and_argv(monkeypatch, code):
    import headroom.watch

    captured = []

    def fake(command, **kwargs):
        captured.append((command, kwargs))
        return {
            "status": "passthrough",
            "triggered": False,
            "exit_code": code,
            "original_exit_code": code,
        }

    monkeypatch.setattr(headroom.watch, "watch_command", fake)
    result = runner.invoke(app, ["watch", "--device", "cpu", "--", "python", "train.py", "--tiny"])
    assert result.exit_code == code
    assert captured[0][0] == ["python", "train.py", "--tiny"]
    assert captured[0][1]["device"] == "cpu"


def test_serve_rejects_public_bind_and_preserves_loopback(monkeypatch):
    import uvicorn

    import headroom.api.app

    captured = []
    sentinel = object()
    monkeypatch.setattr(headroom.api.app, "create_app", lambda: sentinel)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.append((app, kwargs)))
    assert runner.invoke(app, ["serve", "--host", "0.0.0.0"]).exit_code == 2
    assert not captured
    assert runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "8765"]).exit_code == 0
    assert captured == [(sentinel, {"host": "127.0.0.1", "port": 8765})]


def test_eval_plan_only_displays_matrix_without_live_profile(monkeypatch):
    import headroom.evaluation

    captured = {}

    def fake(path, **kwargs):
        captured.update(kwargs)
        return {"mode": "campaign_plan", "executed": False, "planned_pipeline_runs": 20}

    monkeypatch.setattr(headroom.evaluation, "campaign_plan", fake)
    result = runner.invoke(app, ["eval", "--plan-only", "--policies", "default,allow_precision"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["executed"] is False
    assert captured["policy_names"] == ("default", "allow_precision")
    assert captured["campaign_budget_usd"] == "0.6"


def test_live_policy_expansion_requires_explicit_selection(monkeypatch):
    import headroom.evaluation

    captured = []

    def fake(path, **kwargs):
        captured.append(kwargs["policy_names"])
        return {"status": "finished", "rows": [{"status": "completed"}]}

    monkeypatch.setattr(headroom.evaluation, "run_campaign", fake)
    assert runner.invoke(app, ["eval", "--live"]).exit_code == 0
    assert captured[-1] == ("default",)
    assert (
        runner.invoke(app, ["eval", "--live", "--policies", "default,allow_precision"]).exit_code
        == 0
    )
    assert captured[-1] == ("default", "allow_precision")


def test_policy_option_cannot_be_silently_ignored_by_baseline_mode():
    result = runner.invoke(app, ["eval", "--dry-run", "--policies", "allow_precision"])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "argv", [["python", "-m", "torch.utils.collect_env"], ["python", "-c", "print(1)"], ["true"]]
)
def test_watch_exposes_capture_and_repair_mapping_without_inventing_support(monkeypatch, argv):
    import headroom.watch

    captured = []

    def fake(command, **kwargs):
        captured.append(command)
        return {
            "status": "needs_human",
            "triggered": False,
            "exit_code": 1,
            "original_exit_code": 1,
            "capture_status": "complete",
            "cuda_oom_confirmed": True,
            "repair_supported": False,
            "repair_unavailable_reason": "UNMAPPED_ENTRY",
        }

    monkeypatch.setattr(headroom.watch, "watch_command", fake)
    result = runner.invoke(app, ["watch", "--", *argv])
    assert result.exit_code == 1
    assert captured == [argv]
    payload = json.loads(result.stdout)
    assert payload["capture_status"] == "complete"
    assert payload["cuda_oom_confirmed"] is True
    assert payload["repair_supported"] is False
    assert payload["repair_unavailable_reason"] == "UNMAPPED_ENTRY"
