"""Reference protocol survives real entrypoint/config boundaries; no GPU or API."""

import json
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from headroom.api.app import ApiSettings, Submission, _prepare_submission
from headroom.cli import app
from headroom.cli_execution import cli_arguments
from headroom.evaluation import campaign_plan, run_fixture_campaign
from headroom.orchestrator import FixRequest
from headroom.project_config import ProjectConfig
from headroom.verify.reference_config import NumericalReference

OFFLOAD = {
    "strategy": "original_saved_tensor_offload",
    "cpu_saved_tensor_limit_bytes": 16 * 1024**3,
    "disk_saved_tensor_limit_bytes": 64 * 1024**3,
    "max_seconds": 480,
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail("Network forbidden in reference option tests")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.mark.parametrize(
    "bad",
    [
        {"strategy": "unknown"},
        {"cpu_saved_tensor_limit_bytes": 16 * 1024**3 + 1},
        {"cpu_saved_tensor_limit_bytes": True},
        {"disk_saved_tensor_limit_bytes": -1},
        {"disk_saved_tensor_limit_bytes": 64 * 1024**3 + 1},
        {"max_seconds": 481},
        {"max_seconds": 0},
        {"max_seconds": True},
        {"max_seconds": 1.5},
        {"allow_numerics_change": True},
    ],
)
def test_invalid_resources_fail_before_dispatch(bad):
    with pytest.raises(ValidationError):
        NumericalReference.model_validate({**OFFLOAD, **bad})


def test_defaults_remain_legacy_and_offload_needs_explicit_strategy():
    for reference in (
        NumericalReference(),
        FixRequest(script="train.py").numerical_reference,
        ProjectConfig().numerical_reference,
        Submission(script_text="VALUE=1").numerical_reference,
    ):
        assert reference.strategy == "legacy_small_batch"
        assert reference.verify_kwargs() == {}
    for field, value in (
        ("disk_saved_tensor_limit_bytes", 1),
        ("max_seconds", 1),
        ("cpu_saved_tensor_limit_bytes", 1024),
    ):
        with pytest.raises(ValidationError):
            NumericalReference.model_validate({field: value})


def test_cli_transport_overrides_conflicting_yaml_and_preserves_literal_args(tmp_path, monkeypatch):
    from headroom import orchestrator

    script = tmp_path / "train.py"
    script.write_text("VALUE=1\n")
    (tmp_path / "headroom.yaml").write_text(
        json.dumps(
            {
                "numerical_reference": OFFLOAD,
            }
        )
    )
    captured = []
    monkeypatch.setattr(
        orchestrator,
        "run_fix",
        lambda request, **kw: captured.append(request) or {"status": "completed", "report": {}},
    )
    # A default manifest request must not inherit the source directory's opt-in.
    legacy = FixRequest(script=str(script), source_root=str(tmp_path), script_args=["--batch=8"])
    result = CliRunner().invoke(app, cli_arguments(legacy))
    assert result.exit_code == 0, result.output
    assert captured[-1].numerical_reference == legacy.numerical_reference
    assert captured[-1].script_args == ["--batch=8"]

    explicit = legacy.model_copy(update={"numerical_reference": NumericalReference(**OFFLOAD)})
    result = CliRunner().invoke(app, cli_arguments(explicit))
    assert result.exit_code == 0, result.output
    assert captured[-1].numerical_reference == explicit.numerical_reference

    checkpoint = legacy.model_copy(
        update={
            "numerical_reference": NumericalReference(
                strategy="original_workload_checkpoint", max_seconds=480
            )
        }
    )
    result = CliRunner().invoke(app, cli_arguments(checkpoint))
    assert result.exit_code == 0, result.output
    assert captured[-1].numerical_reference == checkpoint.numerical_reference

    # Plain CLI honors project settings; one explicit zero disk option overrides them.
    result = CliRunner().invoke(app, ["fix", str(script), "--reference-disk-bytes", "0"])
    assert result.exit_code == 0, result.output
    assert captured[-1].numerical_reference.disk_saved_tensor_limit_bytes == 0
    assert captured[-1].numerical_reference.max_seconds == 480


def test_manifest_plan_and_execution_share_explicit_reference(tmp_path):
    from test_evaluation import fake_runner, manifest

    path = manifest(tmp_path)
    document = json.loads(path.read_text())
    document["scenarios"][0]["numerical_reference"] = OFFLOAD
    path.write_text(json.dumps(document))
    captured = []

    def observed(request, **kwargs):
        captured.append(request)
        return fake_runner()(request, **kwargs)

    plan = campaign_plan(path, project_root=tmp_path)
    assert plan["targets"][0]["numerical_reference"] == OFFLOAD
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=observed,
        services_factory=lambda *args: None,
    )
    assert result["provenance"] == "offline_fixture"
    assert captured[0].numerical_reference.model_dump() == OFFLOAD


def test_api_preparation_carries_protocol_without_changing_run_caps(tmp_path):
    settings = ApiSettings(
        project_root=tmp_path,
        data_root=tmp_path / "data",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "runs",
    )
    (settings.data_root / "uploads").mkdir(parents=True)
    submission = Submission(script_text="VALUE=1\n", numerical_reference=OFFLOAD)
    request = _prepare_submission(
        settings, submission, submission.script_text, uuid4().hex, deadline=time.monotonic() + 10
    )
    assert request.numerical_reference.model_dump() == OFFLOAD
    assert request.max_seconds == 180 and request.max_steps == 20
    assert request.policy.allow_numerics_change is False
    assert request.budget_usd == "0.6"


@pytest.mark.parametrize(
    "strategy",
    ["legacy_small_batch", "original_saved_tensor_offload", "original_workload_checkpoint"],
)
def test_pipeline_does_not_inject_legacy_reference_cache_into_explicit_reference(
    tmp_path, strategy
):
    from test_orchestrator import search_run

    cached = {"fixture": "a previously returned reference"}
    plans = [
        {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25, "reference": cached},
        {"before": "VALUE = 2\n", "after": "VALUE = 3\n", "peak": 20, "target": True},
    ]
    reference_options = (
        OFFLOAD
        if strategy == "original_saved_tensor_offload"
        else {"strategy": strategy, "max_seconds": 480}
        if strategy == "original_workload_checkpoint"
        else None
    )
    result, store, _, verifies, _ = search_run(
        tmp_path, plans, numerical_reference=reference_options
    )
    try:
        assert result["target_met"]
        assert len(verifies) == 2
        first, second = (v["kwargs"] for v in verifies)
        assert first["reference"] is None
        if strategy != "legacy_small_batch":
            assert second["reference"] is None
            assert first["reference_strategy"] == strategy
            assert first["reference_max_seconds"] == 480
            if strategy == "original_saved_tensor_offload":
                assert first["reference_offload_disk_bytes"] == 64 * 1024**3
            else:
                assert "reference_offload_disk_bytes" not in first
            assert (
                store.get_run(result["run_id"])["request"]["numerical_reference"]
                == NumericalReference(**reference_options).model_dump()
            )
        else:
            assert second["reference"] == cached
            assert "reference_strategy" not in first
    finally:
        store.close()
