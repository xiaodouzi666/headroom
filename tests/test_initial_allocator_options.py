"""Initial allocator declarations survive every entrypoint without general env access."""

import json
import shutil
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from headroom.api.app import ApiSettings, Submission, _prepare_submission, create_app
from headroom.cli import app
from headroom.cli_execution import cli_arguments
from headroom.evaluation import Scenario, campaign_plan, run_fixture_campaign
from headroom.lab.envs import container_environment
from headroom.orchestrator import FixRequest
from headroom.project_config import ProjectConfig, ProjectConfigError, load_project_config
from headroom.verify.reference_config import NumericalReference

ALLOCATOR = "expandable_segments:True"
OFFLOAD = {"strategy": "original_saved_tensor_offload", "disk_saved_tensor_limit_bytes": 1024}
SCENARIO = {
    "id": "case",
    "group": "synthetic",
    "script": "train.py",
    "source_root": ".",
    "target": "reclaim",
    "expected_baseline": "completed",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("No real network permitted in allocator option tests")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.mark.parametrize(
    "model,base",
    [
        (FixRequest, {"script": "train.py"}),
        (ProjectConfig, {}),
        (Submission, {"script_text": "VALUE=1"}),
        (Scenario, SCENARIO),
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        "",
        "LD_PRELOAD:/tmp/anything",
        "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
        "expandable_segments:True;echo unsafe",
        "expandable_segments:True,expandable_segments:False",
        "backend:unknown",
        "expandable_segments:yes",
        "x" * 513,
        True,
        {"backend": "native"},
    ],
)
def test_every_declaration_rejects_non_allowlisted_allocator_before_execution(model, base, value):
    with pytest.raises(ValidationError):
        model.model_validate({**base, "allocator_conf": value})


@pytest.mark.parametrize(
    "model,base",
    [
        (FixRequest, {"script": "train.py"}),
        (ProjectConfig, {}),
        (Submission, {"script_text": "VALUE=1"}),
        (Scenario, SCENARIO),
    ],
)
def test_defaults_do_not_enable_allocator_or_offload_and_arbitrary_env_is_rejected(model, base):
    original = model.model_validate(base)
    assert original.allocator_conf is None
    assert original.numerical_reference.strategy == "legacy_small_batch"
    assert model.model_validate({**base, "allocator_conf": ALLOCATOR}).allocator_conf == ALLOCATOR
    assert model.model_validate({**base, "allocator_conf": None}).allocator_conf is None
    for field in ("env", "environment", "LD_PRELOAD"):
        with pytest.raises(ValidationError):
            model.model_validate({**base, field: {"ANY": "value"}})


def test_yaml_empty_is_not_cli_reset_and_error_does_not_echo_value(tmp_path):
    path = tmp_path / "headroom.yaml"
    for value in ("", "private-invalid-option:canary-secret"):
        path.write_text(json.dumps({"allocator_conf": value}))
        with pytest.raises(ProjectConfigError) as failure:
            load_project_config(path)
        assert "canary" not in str(failure.value)


@pytest.mark.parametrize("value", [None, ALLOCATOR, "max_split_size_mb:64"])
def test_installed_cli_explicit_value_including_none_overrides_project_yaml(
    tmp_path, monkeypatch, value
):
    from headroom import orchestrator

    script = tmp_path / "train.py"
    script.write_text("VALUE=1\n")
    (tmp_path / "headroom.yaml").write_text(
        json.dumps({"allocator_conf": "backend:cudaMallocAsync"})
    )
    captured = []
    monkeypatch.setattr(
        orchestrator,
        "run_fix",
        lambda request, **kwargs: captured.append(request) or {"status": "completed", "report": {}},
    )
    declared = FixRequest(
        script=str(script),
        source_root=str(tmp_path),
        allocator_conf=value,
        script_args=["--literal=3"],
    )
    argv = cli_arguments(declared)
    assert argv[argv.index("--allocator-conf") + 1] == (value or "")
    result = CliRunner().invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert captured[-1].allocator_conf == value
    assert captured[-1].script_args == ["--literal=3"]
    assert captured[-1].numerical_reference == NumericalReference()


def test_plain_cli_honors_yaml_or_explicit_reset_and_refuses_invalid_value(tmp_path, monkeypatch):
    from headroom import orchestrator

    script = tmp_path / "train.py"
    script.write_text("VALUE=1\n")
    (tmp_path / "headroom.yaml").write_text(json.dumps({"allocator_conf": ALLOCATOR}))
    calls = []
    monkeypatch.setattr(
        orchestrator,
        "run_fix",
        lambda request, **kwargs: calls.append(request) or {"status": "completed", "report": {}},
    )
    assert CliRunner().invoke(app, ["fix", str(script)]).exit_code == 0
    assert calls[-1].allocator_conf == ALLOCATOR
    assert CliRunner().invoke(app, ["fix", str(script), "--allocator-conf", ""]).exit_code == 0
    assert calls[-1].allocator_conf is None
    count = len(calls)
    result = CliRunner().invoke(app, ["fix", str(script), "--allocator-conf", "LD_PRELOAD:canary"])
    assert result.exit_code == 1 and len(calls) == count
    assert "canary" not in result.output


def test_manifest_plan_execution_and_result_record_initial_allocator(tmp_path):
    from test_evaluation import fake_runner, manifest

    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"][0]["allocator_conf"] = ALLOCATOR
    path.write_text(json.dumps(data))
    calls = []

    def observed(request, **kwargs):
        calls.append(request)
        return fake_runner()(request, **kwargs)

    plan = campaign_plan(path, project_root=tmp_path)
    assert plan["targets"][0]["allocator_conf"] == ALLOCATOR
    assert plan["run_wall_limit_seconds"] == 480
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "output",
        runner=observed,
        services_factory=lambda *args: None,
    )
    assert calls[0].allocator_conf == ALLOCATOR
    assert result["rows"][0]["allocator_conf"] == ALLOCATOR
    assert calls[0].numerical_reference.strategy == "legacy_small_batch"


def test_api_preparation_and_queue_keep_allocator_and_reference_without_changing_caps(tmp_path):
    from test_api import wait_done

    settings = ApiSettings(
        project_root=tmp_path,
        data_root=tmp_path / "data",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "jobs",
    )
    (settings.data_root / "uploads").mkdir(parents=True)
    submission = Submission(
        script_text="VALUE=1\n", allocator_conf=ALLOCATOR, numerical_reference=OFFLOAD
    )
    request = _prepare_submission(
        settings, submission, submission.script_text, uuid4().hex, deadline=time.monotonic() + 10
    )
    assert request.allocator_conf == ALLOCATOR
    assert request.max_seconds == 180 and request.max_steps == 20 and request.budget_usd == "0.6"
    calls = []

    def worker(request, **kwargs):
        calls.append(request)
        return {"status": "needs_human", "target_met": False}

    with TestClient(create_app(settings, worker=worker)) as client:
        bad = client.post(
            "/api/runs", json={"script_text": "VALUE=1", "allocator_conf": "LD_PRELOAD:x"}
        )
        assert bad.status_code in (400, 422) and not calls
        response = client.post("/api/runs", json=submission.model_dump())
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        final = wait_done(client, run_id)
        assert calls[0].allocator_conf == ALLOCATOR
        assert calls[0].numerical_reference == submission.numerical_reference
        assert final["allocator_conf"] == ALLOCATOR
        assert final["numerical_reference"] == submission.numerical_reference.model_dump()


@pytest.mark.parametrize("configured,reset", [(False, False), (True, False), (True, True)])
def test_watch_cli_whitelist_baseline_and_repair_share_initial_settings(
    tmp_path, monkeypatch, configured, reset
):
    from headroom import watch

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE=1\n")
    if configured:
        (source / "headroom.yaml").write_text(
            json.dumps({"allocator_conf": ALLOCATOR, "numerical_reference": OFFLOAD})
        )
    baselines, repairs = [], []

    def lab(root, command, **kwargs):
        baselines.append(kwargs)
        directory = Path(kwargs["run_root"]) / ("1" * 32)
        directory.mkdir(parents=True)
        shutil.copytree(root, directory / "source")
        return {
            "status": "oom",
            "protocol": "headroom.lab.v1",
            "termination_reason": "oom",
            "capture_complete": True,
            "cleanup_verified": True,
            "oom": {"fixture": True},
            "env": {"device": "cuda"},
            "run_dir": str(directory),
            "execution": {"state": {"ExitCode": 1, "OOMKilled": False, "Running": False}},
        }

    def repair(request, **kwargs):
        repairs.append(request)
        return {"status": "completed", "target_met": True}

    monkeypatch.setattr(watch, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(watch, "run_argv", lab)
    monkeypatch.setattr(watch, "run_fix", repair)
    argv = ["watch", "--source-root", str(source)]
    if reset:
        argv += ["--allocator-conf", ""]
    result = CliRunner().invoke(app, [*argv, "--", "python", "train.py"])
    assert result.exit_code == 0, result.output
    expected = ALLOCATOR if configured and not reset else None
    assert baselines[0]["allocator_conf"] == expected
    assert repairs[0].allocator_conf == expected
    assert repairs[0].numerical_reference == (
        NumericalReference(**OFFLOAD) if configured else NumericalReference()
    )


def test_fix_initial_allocator_reaches_original_baseline_and_candidate_reference(
    tmp_path, monkeypatch
):
    import test_orchestrator as fixtures

    from headroom.orchestrator import run_fix

    baselines = []

    def configured(request, **kwargs):
        request = FixRequest.model_validate({**request.model_dump(), "allocator_conf": ALLOCATOR})
        services = kwargs["services"]

        def baseline(*args, **options):
            baselines.append(options)
            return services.baseline(*args, **options)

        return run_fix(request, **{**kwargs, "services": replace(services, baseline=baseline)})

    monkeypatch.setattr(fixtures, "run_fix", configured)
    result, store, _, verifies, _ = fixtures.search_run(
        tmp_path, [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}]
    )
    try:
        assert result["target_met"] and len(baselines) == 1 and len(verifies) == 1
        assert baselines[0]["allocator_conf"] == ALLOCATOR
        assert verifies[0]["kwargs"]["allocator_conf"] == ALLOCATOR
        assert verifies[0]["kwargs"]["baseline_allocator_conf"] == ALLOCATOR
        assert store.get_run(result["run_id"])["request"]["allocator_conf"] == ALLOCATOR
    finally:
        store.close()


def test_container_environment_keeps_single_allocator_key_and_ignores_host_env(monkeypatch):
    monkeypatch.setenv("PYTORCH_CUDA_ALLOC_CONF", "backend:cudaMallocAsync")
    monkeypatch.setenv("ARBITRARY_ENV", "canary")
    options = {"device": "cuda", "max_steps": 20, "max_seconds": 120, "seed": 3}
    absent = container_environment(**options)
    assert "PYTORCH_CUDA_ALLOC_CONF" not in absent and "ARBITRARY_ENV" not in absent
    selected = container_environment(**options, allocator_conf=ALLOCATOR)
    assert selected["PYTORCH_CUDA_ALLOC_CONF"] == ALLOCATOR and "ARBITRARY_ENV" not in selected
