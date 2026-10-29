"""Search selection survives every public adapter; no workloads or provider calls."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from headroom.api.app import ApiSettings, _public_run, create_app
from headroom.api.evaluations import _public_row
from headroom.cli import app
from headroom.evaluation import (
    campaign_plan,
    load_manifest,
    render_campaign,
    result_row,
    run_campaign,
    run_fixture_campaign,
)

cli = CliRunner()


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Search interface tests forbid network, keys and workload execution")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr("headroom.runtime.read_nebius_key", denied)
    monkeypatch.setattr("headroom.lab.runner.run_script", denied)


@pytest.fixture
def captured_fix(tmp_path, monkeypatch):
    captured = []
    monkeypatch.chdir(tmp_path)

    def fake(request, **kwargs):
        captured.append(request)
        return {"status": "completed"}

    monkeypatch.setattr("headroom.orchestrator.run_fix", fake)
    return captured


@pytest.mark.parametrize("target", ["fix-oom", "reclaim"])
@pytest.mark.parametrize(
    "configured, explicit, expected",
    [
        (None, None, "until_target"),
        ("bounded_pareto", None, "bounded_pareto"),
        ("bounded_pareto", "until_target", "until_target"),
        ("until_target", "bounded_pareto", "bounded_pareto"),
    ],
)
def test_fix_and_reclaim_mode_precedence(
    tmp_path, captured_fix, target, configured, explicit, expected
):
    if configured:
        (tmp_path / "headroom.yaml").write_text(f"search_mode: {configured}\n")
    args = ["fix", "train.py", "--target", target]
    if explicit:
        args += ["--search-mode", explicit]
    result = cli.invoke(app, args)
    assert result.exit_code == 0, result.output
    request = captured_fix[0]
    assert request.search_mode == expected and request.target == target
    assert request.max_rounds == 6 and request.budget_usd == "0.6"
    assert request.policy.allow_numerics_change is False
    assert request.runtime_profile is None


@pytest.mark.parametrize("explicit", [None, "until_target"])
def test_watch_mode_yaml_and_cli_preserve_original_argv(tmp_path, monkeypatch, explicit):
    (tmp_path / "headroom.yaml").write_text(
        "search_mode: bounded_pareto\nmax_steps: 9\npolicy: {allow_numerics_change: true}\n"
    )
    captured = []

    def fake(argv, **kwargs):
        captured.append((argv, kwargs))
        return {"exit_code": 0, "status": "completed"}

    monkeypatch.setattr("headroom.watch.watch_command", fake)
    args = ["watch", "--source-root", str(tmp_path)]
    if explicit:
        args += ["--search-mode", explicit]
    result = cli.invoke(app, [*args, "--", "python", "-u", "-m", "package.train"])
    assert result.exit_code == 0, result.output
    argv, options = captured[0]
    assert argv == ["python", "-u", "-m", "package.train"]
    assert options["fix_options"]["search_mode"] == (explicit or "bounded_pareto")
    # Watch only opts into the new search setting; unrelated YAML is not activated.
    assert options["max_steps"] == 20
    assert options["fix_options"]["policy"].allow_numerics_change is False


def test_watch_explicit_configuration_path(tmp_path, monkeypatch):
    config = tmp_path / "search.yaml"
    config.write_text("search_mode: bounded_pareto\n")
    captured = []
    monkeypatch.setattr(
        "headroom.watch.watch_command",
        lambda *args, **kwargs: captured.append(kwargs) or {"exit_code": 0},
    )
    assert (
        cli.invoke(app, ["watch", "--config", str(config), "--", "python", "a.py"]).exit_code == 0
    )
    assert captured[0]["fix_options"]["search_mode"] == "bounded_pareto"


@pytest.mark.parametrize("command", ["fix", "watch", "eval"])
def test_invalid_cli_mode_rejected_before_dispatch(monkeypatch, command):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid mode must not dispatch or prepare repository")

    monkeypatch.setattr("headroom.orchestrator.run_fix", forbidden)
    monkeypatch.setattr("headroom.repository.prepare_repository", forbidden)
    monkeypatch.setattr("headroom.watch.watch_command", forbidden)
    monkeypatch.setattr("headroom.evaluation.campaign_plan", forbidden)
    result = cli.invoke(app, [command, "--search-mode", "unbounded"])
    assert result.exit_code == 2


@pytest.mark.parametrize("value", ["unbounded", "false", "null", "0", "[]"])
@pytest.mark.parametrize("command", ["fix", "watch"])
def test_invalid_project_mode_rejected_before_dispatch(tmp_path, monkeypatch, value, command):
    (tmp_path / "headroom.yaml").write_text(f"search_mode: {value}\n")
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid project mode must not dispatch")

    monkeypatch.setattr("headroom.orchestrator.run_fix", forbidden)
    monkeypatch.setattr("headroom.watch.watch_command", forbidden)
    tail = ["train.py"] if command == "fix" else ["--", "python", "train.py"]
    assert cli.invoke(app, [command, *tail]).exit_code != 0


@pytest.mark.parametrize("mode", [None, "until_target", "bounded_pareto"])
def test_api_submission_persists_actual_mode_and_forwards_request(tmp_path, mode):
    captured = []

    def worker(request, **kwargs):
        captured.append(request)
        return {"status": "needs_human", "target_met": False}

    settings = ApiSettings(
        project_root=tmp_path,
        data_root=tmp_path / "api",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "jobs",
        web_dist=tmp_path / "dist",
    )
    api = create_app(settings, worker=worker)
    with TestClient(api) as client:
        payload = {"script_text": "print('offline fixture')"}
        if mode is not None:
            payload["search_mode"] = mode
        response = client.post("/api/runs", json=payload)
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            row = client.get(f"/api/runs/{run_id}").json()
            if row.get("api_worker_finished"):
                break
            time.sleep(0.01)
        assert row.get("api_worker_finished")
        assert row["search_mode"] == (mode or "until_target")
        assert captured[0].search_mode == (mode or "until_target")
        saved = api.state.store.get_run(run_id)
        assert saved["api_source"]["search_mode"] == row["search_mode"]
        assert captured[0].policy.allow_numerics_change is False


@pytest.mark.parametrize("mode", ["unbounded", False, None, [], {}])
def test_api_rejects_invalid_mode_without_admission(tmp_path, mode):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid submission must never reach a worker")

    settings = ApiSettings(
        project_root=tmp_path,
        data_root=tmp_path / "api",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "jobs",
    )
    with TestClient(create_app(settings, worker=forbidden)) as client:
        result = client.post("/api/runs", json={"script_text": "print(1)", "search_mode": mode})
        assert result.status_code == 400
        assert client.get("/api/runs").json()["runs"] == []


def make_manifest(tmp_path, mode=None):
    source = tmp_path / "scenario"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    document = {
        "version": 1,
        "scenarios": [
            {
                "id": "scenario",
                "group": "synthetic",
                "script": "scenario/train.py",
                "source_root": "scenario",
                "target": "reclaim",
                "expected_baseline": "completed",
            }
        ],
    }
    if mode is not None:
        document["search_mode"] = mode
    path = tmp_path / "scenarios.yaml"
    path.write_text(json.dumps(document))
    return path


@pytest.mark.parametrize(
    "configured, explicit, expected",
    [
        (None, None, "until_target"),
        ("bounded_pareto", None, "bounded_pareto"),
        ("bounded_pareto", "until_target", "until_target"),
    ],
)
def test_campaign_records_effective_mode_and_preserves_terminal_failure(
    tmp_path, configured, explicit, expected
):
    path = make_manifest(tmp_path, configured)
    captured = []

    def runner(request, *, store, run_id, **kwargs):
        captured.append(request)
        store.create_run(run_id, {"status": "budget_exceeded", "provenance": "offline_fixture"})
        store.add_llm_call(run_id, {"model": "offline", "role": "diagnose", "cost_usd": "0.1"})
        return {
            "run_id": run_id,
            "status": "budget_exceeded",
            "reason": "fixture_budget_stop",
            "report": {
                "summary": {"target_met": True},
                "search": {
                    "mode": request.search_mode,
                    "stop_reason": "budget_exceeded",
                    "rounds_executed": 2,
                    "first_target_met_round": 1,
                    "baseline_target_met": False,
                },
            },
        }

    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=runner,
        services_factory=lambda *args: None,
        search_mode=explicit,
    )
    assert result["search_mode"] == result["plan"]["search_mode"] == expected
    assert captured[0].search_mode == expected
    row = result["rows"][0]
    assert row["search_mode"] == expected and row["search_stop_reason"] == "budget_exceeded"
    assert row["status"] == "budget_exceeded" and row["target_met"] is True
    assert row["reason"] == "fixture_budget_stop" and row["first_target_met_round"] == 1
    assert row["baseline_target_met"] is False and row["search_rounds_executed"] == 2
    assert result["summary"]["status"] == "pending"  # fixtures cannot become live scores
    persisted = json.loads(Path(result["report_path"]).read_text())
    assert persisted["rows"][0]["search_mode"] == expected
    projected = _public_row(row, "offline_fixture")
    assert projected["search_mode"] == expected
    assert projected["search_stop_reason"] == "budget_exceeded"
    markdown = render_campaign(result)
    assert "Search mode" in markdown and "Search stop reason" in markdown
    assert expected in markdown.replace("\\_", "_")
    assert "budget_exceeded" in markdown.replace("\\_", "_")

    from fastapi import FastAPI

    from headroom.api.evaluations import register_evaluations

    publication = tmp_path / "publication"
    (publication / "published-evaluations").mkdir(parents=True)
    (publication / "public-evaluations.json").write_text(
        json.dumps({"version": 1, "campaigns": [{"id": "fixture", "title": "Offline fixture"}]})
    )
    (publication / "published-evaluations/fixture.json").write_text(json.dumps(result))
    application = FastAPI()
    register_evaluations(application, publication)
    with TestClient(application) as client:
        public = client.get("/api/evaluations/fixture").json()
    assert public["search_mode"] == expected
    assert public["rows"][0]["search_stop_reason"] == "budget_exceeded"
    assert public["summary"]["status"] == "pending"


@pytest.mark.parametrize("value", ["unbounded", False, 0, []])
def test_invalid_campaign_mode_fails_before_profile_access(tmp_path, monkeypatch, value):
    path = make_manifest(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid campaign mode must fail before live profile access")

    monkeypatch.setattr("headroom.runtime.read_live_profile", forbidden)
    with pytest.raises(ValueError):
        run_campaign(
            path,
            project_root=tmp_path,
            execute=True,
            live_authorized=True,
            runtime_profile="not-read.json",
            search_mode=value,
        )
    data = json.loads(path.read_text())
    data["search_mode"] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        campaign_plan(path, project_root=tmp_path)
    assert not (tmp_path / "runs").exists()


def test_historical_reports_do_not_gain_an_inferred_search_mode(tmp_path):
    path = make_manifest(tmp_path)
    case = load_manifest(path, project_root=tmp_path).scenarios[0]
    row = result_row(
        case, "full_ultra", {"status": "completed", "report": {}}, None, provenance="live"
    )
    assert row["search_mode"] is None and row["search_stop_reason"] is None
    assert _public_row(row, "live")["search_mode"] is None
    assert "search_mode" not in _public_run({"status": "completed"})


@pytest.mark.parametrize("command", ["--plan-only", "--live"])
def test_eval_cli_passes_explicit_mode_only_to_campaign_adapters(monkeypatch, command):
    seen = []
    name = "campaign_plan" if command == "--plan-only" else "run_campaign"
    monkeypatch.setattr(
        "headroom.evaluation." + name,
        lambda *args, **kwargs: seen.append(kwargs) or {"status": "finished", "rows": []},
    )
    assert cli.invoke(app, ["eval", command, "--search-mode", "bounded_pareto"]).exit_code == 0
    assert seen[0]["search_mode"] == "bounded_pareto"


@pytest.mark.parametrize("mode", ["--validate-only", "--dry-run"])
def test_baseline_and_validation_do_not_silently_accept_search_override(mode):
    assert cli.invoke(app, ["eval", mode, "--search-mode", "bounded_pareto"]).exit_code == 2


@pytest.mark.parametrize("mode", [None, "bounded_pareto"])
def test_cli_to_real_watch_preflight_and_saved_manifest(tmp_path, monkeypatch, mode):
    import headroom.watch as watch_module

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("print(1)\n")
    original = watch_module.watch_command
    seen = []

    def lab(*args, **kwargs):
        seen.append(kwargs)
        return {
            "status": "completed",
            "cleanup_verified": True,
            "capture_complete": True,
            "execution": {"state": {"ExitCode": 0}},
        }

    def adapter(argv, **kwargs):
        return original(argv, run_root=tmp_path / "watch", lab_runner=lab, **kwargs)

    monkeypatch.setattr(watch_module, "watch_command", adapter)
    args = ["watch", "--source-root", str(source)]
    if mode:
        args += ["--search-mode", mode]
    result = cli.invoke(app, [*args, "--", "python", "train.py"])
    assert result.exit_code == 0, result.output
    assert len(seen) == 1
    output = json.loads(result.stdout)
    assert output["search_mode"] == (mode or "until_target")
    saved = json.loads(Path(output["watch_report_path"]).with_name("watch.json").read_text())
    assert saved["search_mode"] == (mode or "until_target")


def test_real_watch_rejects_invalid_mode_before_lab(tmp_path):
    from headroom.watch import watch_command

    (tmp_path / "train.py").write_text("print(1)\n")

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid direct Watch mode must fail before Lab")

    with pytest.raises(ValueError):
        watch_command(
            ["python", "train.py"],
            source_root=tmp_path,
            fix_options={"search_mode": "unbounded"},
            lab_runner=forbidden,
        )


@pytest.mark.parametrize(
    "modes, comparable",
    [
        (["bounded_pareto"] * 3, True),
        ([None] * 3, True),
        (["until_target", "bounded_pareto", "until_target"], False),
        (["until_target", None, "until_target"], False),
    ],
)
def test_ablation_search_mode_comparability_without_rewriting_legacy(modes, comparable):
    from headroom.evaluation import CONDITIONS, ablation_summary

    rows = [
        {
            "scenario_id": "s1",
            "condition": condition,
            "policy_name": "default",
            "group": "synthetic",
            "provenance": "live",
            "source_sha256": "a" * 64,
            "truth_status": "authored",
            "first_cause_matches": True,
            "run_id": str(index) * 32,
            "search_mode": modes[index],
        }
        for index, condition in enumerate(CONDITIONS)
    ]
    result = ablation_summary(rows)
    assert result["paired_scored_count"] == int(comparable)
    if comparable:
        assert result["pairs"][0]["search_mode"] == modes[0]
        assert result["excluded"] == []
    else:
        assert result["excluded"][0]["reason"] == "search_mode_not_comparable"


def test_campaign_retains_actual_search_when_report_missing(tmp_path):
    path = make_manifest(tmp_path)
    case = load_manifest(path, project_root=tmp_path).scenarios[0]
    row = result_row(
        case,
        "full_ultra",
        {
            "status": "failed",
            "reason": "report_generation_failed",
            "search": {
                "mode": "bounded_pareto",
                "stop_reason": "runtime_error",
                "rounds_executed": 1,
                "first_target_met_round": None,
                "baseline_target_met": False,
            },
        },
        None,
        provenance="offline_fixture",
    )
    assert row["status"] == "failed" and row["target_met"] is None
    assert row["search_mode"] == "bounded_pareto"
    assert row["search_stop_reason"] == "runtime_error"
    assert row["search_rounds_executed"] == 1
