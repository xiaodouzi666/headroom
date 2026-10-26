"""Independent review regressions for archived applicability records."""

import copy
import hashlib
import json

import pytest
from test_repair_scope import BASE_ID, CAND_ID, alter, build, make_job, write
from typer.testing import CliRunner

from headroom.cli import app
from headroom.verify import applicability


@pytest.mark.parametrize("status", ["oom", "error", "timeout"])
def test_terminal_candidate_failure_is_not_hidden_by_complete_step_count(tmp_path, status):
    selection = make_job(tmp_path)
    alter(tmp_path / "job/lab" / CAND_ID / "result.json", lambda r: r.update(status=status))
    scope, query = build(tmp_path, selection)
    assert scope["observations"][0]["status"] == "tested_fail"
    assert "candidate ended with " + status in scope["observations"][0]["reasons"]
    assert applicability.check_scope(tmp_path, scope, query)["status"] == "tested_fail"


def test_observed_throughput_limit_failure_is_a_counterexample(tmp_path):
    selection = make_job(tmp_path)
    alter(
        tmp_path / "job/lab" / CAND_ID / "result.json",
        lambda r: r.update(step_ms_median=200.0),
    )
    scope, query = build(tmp_path, selection)
    assert scope["observations"][0]["status"] == "tested_fail"
    assert "throughput_limit failed" in scope["observations"][0]["reasons"]
    assert applicability.check_scope(tmp_path, scope, query)["status"] == "tested_fail"


@pytest.mark.parametrize("missing", ["timing", "clear_gpu", "same_gpu"])
def test_unreliable_throughput_is_unknown_not_an_observed_failure(tmp_path, missing):
    selection = make_job(tmp_path)
    candidate = tmp_path / "job/lab" / CAND_ID / "result.json"
    alter(candidate, lambda r: r.update(step_ms_median=200.0))
    if missing == "timing":
        alter(tmp_path / "job/lab" / BASE_ID / "result.json", lambda r: r.pop("step_ms_median"))
    elif missing == "clear_gpu":
        alter(candidate, lambda r: r.update(gpu_observation_complete=False))
    else:
        alter(candidate, lambda r: r["env"].update(gpu_name="another observed GPU"))
    scope = applicability.build_scope(tmp_path, [selection])
    assert scope["observations"][0]["status"] == "unknown"


@pytest.mark.parametrize("key", ["PYTORCH_CUDA_ALLOC_CONF", "CUBLAS_WORKSPACE_CONFIG"])
def test_absent_runtime_environment_observation_is_not_an_explicit_null(tmp_path, key):
    selection = make_job(tmp_path)
    for run_id in (BASE_ID, CAND_ID):
        alter(tmp_path / "job/lab" / run_id / "result.json", lambda r: r["env"].pop(key))
    scope = applicability.build_scope(tmp_path, [selection])
    assert scope["observations"][0]["status"] == "unknown"
    assert "environment." + key in scope["observations"][0]["reasons"][0]


@pytest.mark.parametrize("key", ["PYTORCH_CUDA_ALLOC_CONF", "CUBLAS_WORKSPACE_CONFIG"])
def test_malformed_runtime_environment_value_is_rejected(tmp_path, key):
    selection = make_job(tmp_path)
    alter(
        tmp_path / "job/lab" / CAND_ID / "result.json",
        lambda r: r["env"].update({key: True}),
    )
    with pytest.raises(ValueError, match="runtime environment"):
        applicability.build_scope(tmp_path, [selection])


@pytest.mark.parametrize(
    "changes",
    [{"max_seconds": 999}, {"max_seconds": True}, {"max_seconds": 0}, {"device": "cpu"}],
)
def test_request_execution_controls_cannot_disagree_with_recorded_lab_invocation(tmp_path, changes):
    selection = make_job(tmp_path)
    alter(tmp_path / "job/report.json", lambda r: r["run"]["request"].update(changes))
    with pytest.raises(ValueError):
        applicability.build_scope(tmp_path, [selection])


@pytest.mark.parametrize("key", ["max_seconds", "device"])
def test_missing_request_control_remains_unknown(tmp_path, key):
    selection = make_job(tmp_path)
    alter(tmp_path / "job/report.json", lambda r: r["run"]["request"].pop(key))
    scope = applicability.build_scope(tmp_path, [selection])
    assert scope["observations"][0]["status"] == "unknown"


@pytest.mark.parametrize("key,value", [("max_seconds", 121), ("device", "cpu")])
def test_query_execution_controls_are_bound_to_the_observed_context(tmp_path, key, value):
    scope, query = build(tmp_path, make_job(tmp_path))
    assert query["max_seconds"] == 120 and query["device"] == "cuda"
    query[key] = value
    result = applicability.check_scope(tmp_path, scope, query)
    assert result["status"] == "unknown"
    assert key in result["mismatched_fields"]


def test_float_or_tuple_query_does_not_match_integer_or_list(tmp_path):
    scope, query = build(tmp_path, make_job(tmp_path))
    query["max_seconds"] = 120.0
    assert applicability.check_scope(tmp_path, scope, query)["status"] == "unknown"
    query = copy.deepcopy(scope["observations"][0]["context"])
    query["effective_argv"] = tuple(query["effective_argv"])
    assert applicability.check_scope(tmp_path, scope, query)["status"] == "invalid_evidence"


def test_unknown_at_identical_context_prevents_unanimous_success(tmp_path):
    good = make_job(tmp_path, "good")
    unknown = make_job(tmp_path, "unknown")
    alter(
        tmp_path / "unknown/lab" / CAND_ID / "result.json",
        lambda r: r.update(parameter_count_complete=False),
    )
    scope = applicability.build_scope(tmp_path, [good, unknown])
    assert [item["status"] for item in scope["observations"]] == ["tested_pass", "unknown"]
    assert scope["observations"][0]["context"] == scope["observations"][1]["context"]
    query = scope["observations"][0]["context"]
    assert applicability.check_scope(tmp_path, scope, query)["status"] == "unknown"


def test_extra_manifested_source_change_outside_patch_is_rejected(tmp_path):
    selection = make_job(tmp_path)
    for run_id, content in ((BASE_ID, b"original\n"), (CAND_ID, b"changed\n")):
        lab = tmp_path / "job/lab" / run_id
        (lab / "source/extra.txt").write_bytes(content)

        def update(manifest, content=content):
            manifest["source"]["files"]["extra.txt"] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
            manifest["source"]["total_bytes"] += len(content)

        alter(lab / "manifest.json", update)
    with pytest.raises(ValueError, match="Source-tree changes"):
        applicability.build_scope(tmp_path, [selection])


def test_pretty_record_size_is_bounded_before_cli_creates_an_unreadable_output(
    tmp_path, monkeypatch
):
    selection = make_job(tmp_path)
    scope, _ = build(tmp_path, selection)
    encoded_size = len((json.dumps(scope, indent=2, allow_nan=False) + "\n").encode())
    # Reuse the verified implementation inventory to isolate the output-size
    # boundary, rather than lowering the unrelated source-file read limit.
    monkeypatch.setattr(
        applicability, "_implementation_hashes", lambda: scope["implementation_hashes"]
    )
    assert encoded_size > max(p.stat().st_size for p in (tmp_path / "job").rglob("*.json"))
    monkeypatch.setattr(applicability, "MAX_JSON_BYTES", encoded_size - 1)
    with pytest.raises(ValueError, match="Scope record exceeds"):
        applicability.build_scope(tmp_path, [selection])
    spec, output = tmp_path / "selection.json", tmp_path / "scope.json"
    write(spec, {"selections": [selection]})
    result = CliRunner().invoke(
        app,
        [
            "scope",
            "build",
            str(spec),
            "--evidence-root",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 78
    assert not output.exists()
    monkeypatch.setattr(applicability, "MAX_JSON_BYTES", encoded_size)
    record = applicability.build_scope(tmp_path, [selection])
    output.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    assert applicability.load_json(output) == record
