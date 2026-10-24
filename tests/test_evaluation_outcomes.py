"""Attempt facts stay distinct from retained configuration facts; no GPU or provider calls."""

import builtins
import io
import json
import os
import socket
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_orchestrator import search_run

from headroom.api.evaluations import register_evaluations
from headroom.evaluation import (
    Scenario,
    evaluation_outcomes,
    public_outcomes,
    render_campaign,
    result_row,
    summarize,
)
from headroom.patch import apply_proposal

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("External network, real credentials and GPU execution are forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr("headroom.runtime.read_live_profile", denied)
    monkeypatch.setattr("headroom.runtime.read_nebius_key", denied)

    def guard(original):
        def checked(path, *args, **kwargs):
            if (
                isinstance(path, (str, bytes, os.PathLike))
                and Path(os.fsdecode(path)).absolute() == ROOT / ".env"
            ):
                denied()
            return original(path, *args, **kwargs)

        return checked

    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    monkeypatch.setattr(os, "open", guard(os.open))


def case():
    return Scenario(
        id="fixture",
        group="synthetic",
        script="train.py",
        source_root=".",
        target="fit:22GB",
        expected_baseline="completed",
        ground_truth="activations",
    )


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def artifact_result(tmp_path, outcomes, *, selected="missing"):
    rounds = []
    for number, (applied, completed, decision) in enumerate(outcomes, 1):
        row = {"number": number, "decision": decision}
        if applied is not None:
            write(
                tmp_path / f"rounds/{number:02d}/patch-result.json",
                {"status": "applied" if applied else "failed"},
            )
        if completed is not None:
            verification = {"completed": completed, "after": {"run_id": f"candidate-{number}"}}
            write(tmp_path / f"rounds/{number:02d}/verification.json", verification)
            row["verification"] = verification
        rounds.append(row)
    report = {"rounds": rounds, "run": {}, "summary": {"target_met": True}}
    if selected != "missing":
        report["run"]["kept"] = {"round": selected} if selected is not None else None
        if selected is not None:
            report["selected_configuration"] = {"round": selected}
            report["verification"] = rounds[selected - 1].get("verification", {})
    return {"run_dir": str(tmp_path), "report": report, "status": "completed", "target_met": True}


def test_keep_then_revert_does_not_swap_selected_completion(tmp_path):
    result = artifact_result(tmp_path, [(True, True, "keep"), (True, False, "revert")], selected=1)
    row = result_row(
        case(), "full_ultra", result, {"total_cost_usd": "0"}, provenance="offline_fixture"
    )
    assert row["patch_applied"] is True and row["patch_applied_rounds"] == [1, 2]
    assert row["selected_round"] == 1 and row["selected_patch_applied"] is True
    assert row["selected_completed"] is True
    assert row["round_outcomes"][1]["candidate_completed"] is False


def test_all_reverted_still_has_applied_attempt_and_no_selected_completion(tmp_path):
    result = artifact_result(
        tmp_path, [(True, True, "revert"), (True, False, "revert")], selected=None
    )
    facts = evaluation_outcomes(result)
    assert facts["patch_applied"] is True
    assert facts["selected_round"] is None and facts["selected_patch_applied"] is False
    assert facts["selected_completed"] is None
    assert [r["candidate_completed"] for r in facts["round_outcomes"]] == [True, False]


@pytest.mark.parametrize("missing", [False, True])
def test_negative_application_needs_complete_recorded_round_facts(tmp_path, missing):
    outcomes = [(False, None, "revert"), (None if missing else False, None, "revert")]
    facts = evaluation_outcomes(artifact_result(tmp_path, outcomes, selected=None))
    assert facts["patch_applied"] is (None if missing else False)
    assert facts["patch_applied_rounds"] == []


def test_historical_status_target_and_empty_diff_are_not_facts(tmp_path):
    result = artifact_result(tmp_path, [(None, None, "keep")])
    result["report"]["rounds"][0].update(diff="", patch="patch.diff", keep=True)
    result["report"]["verification"] = {"completed": True}
    facts = evaluation_outcomes(result)
    assert (
        facts["patch_applied"]
        is facts["selected_patch_applied"]
        is facts["selected_completed"]
        is None
    )
    assert facts["selected_round"] is None and facts["outcome_basis"] is None


@pytest.mark.parametrize("bad", [True, 0, -1, 7, "1", [1], {"value": 1}])
def test_invalid_round_identity_remains_unknown(tmp_path, bad):
    result = artifact_result(tmp_path, [(True, True, "keep")], selected=1)
    result["report"]["rounds"][0]["number"] = bad
    assert evaluation_outcomes(result)["outcome_basis"] is None


@pytest.mark.parametrize("field", ["status", "decision"])
@pytest.mark.parametrize("value", [[], {}, ["applied"]])
def test_invalid_json_enum_values_do_not_crash(tmp_path, field, value):
    result = artifact_result(tmp_path, [(True, True, "keep")], selected=1)
    if field == "status":
        write(tmp_path / "rounds/01/patch-result.json", {"status": value})
        assert evaluation_outcomes(result)["patch_applied"] is None
    else:
        result["report"]["rounds"][0]["decision"] = value
        facts = evaluation_outcomes(result)
        assert facts["round_outcomes"][0]["decision"] is None
        projected = public_outcomes(
            {**facts, "round_outcomes": [{**facts["round_outcomes"][0], "decision": value}]}
        )
        assert projected["round_outcomes"][0]["decision"] is None


@pytest.mark.parametrize("kind", ["malformed", "oversized", "symlink", "fifo"])
def test_rejected_verification_artifact_cannot_fall_back_to_inline_success(tmp_path, kind):
    result = artifact_result(tmp_path, [(True, True, "keep")], selected=1)
    path = tmp_path / "rounds/01/verification.json"
    path.unlink()
    if kind == "malformed":
        path.write_text("not json")
    elif kind == "oversized":
        path.write_bytes(b" " * (1024 * 1024 + 1))
    elif kind == "symlink":
        target = tmp_path / "outside.json"
        write(target, {"completed": True})
        path.symlink_to(target)
    else:
        os.mkfifo(path)
    facts = evaluation_outcomes(result)
    assert facts["round_outcomes"][0]["candidate_completed"] is None
    assert facts["selected_completed"] is None


def test_missing_file_can_use_actual_saved_inline_verification(tmp_path):
    result = artifact_result(tmp_path, [(True, True, "keep")], selected=1)
    (tmp_path / "rounds/01/verification.json").unlink()
    assert evaluation_outcomes(result)["selected_completed"] is True


def test_explicit_failed_patch_conflicts_with_selected_success(tmp_path):
    result = artifact_result(tmp_path, [(False, True, "keep")], selected=1)
    facts = evaluation_outcomes(result)
    assert facts["patch_applied"] is False and facts["selected_patch_applied"] is False
    assert facts["selected_completed"] is None
    assert public_outcomes({**facts, "selected_completed": True})["selected_completed"] is None


@pytest.mark.parametrize("conflict", ["identity", "completed", "after_run_id", "revert"])
def test_conflicting_selected_evidence_cannot_be_presented_as_completed(tmp_path, conflict):
    result = artifact_result(tmp_path, [(True, True, "keep"), (True, False, "revert")], selected=1)
    if conflict == "identity":
        result["kept"] = {"round": 2}
    elif conflict == "completed":
        result["report"]["verification"] = {"completed": False}
    elif conflict == "after_run_id":
        result["report"]["verification"] = {"completed": True, "after": {"run_id": "candidate-2"}}
    else:
        result["report"]["rounds"][0]["decision"] = "revert"
    assert evaluation_outcomes(result)["selected_completed"] is None


def test_cli_only_empty_diff_uses_real_apply_result_not_diff_size(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    patch = apply_proposal(
        source,
        {"diff": "", "env_changes": {}, "cli_changes": ["--batch_size", "4"]},
        work_root=tmp_path / "patch-work",
        base_cli=["--batch_size", "32"],
    )
    assert patch.applied and Path(patch.patch_path).read_text() == ""
    result = artifact_result(tmp_path / "run", [(None, True, "keep")], selected=1)
    write(tmp_path / "run/rounds/01/patch-result.json", asdict(patch))
    facts = evaluation_outcomes(result)
    assert (
        facts["patch_applied"] and facts["selected_patch_applied"] and facts["selected_completed"]
    )


def _publish(tmp_path, rows):
    write(
        tmp_path / "public-evaluations.json",
        {"version": 1, "campaigns": [{"id": "fixture", "title": "Offline outcomes"}]},
    )
    write(
        tmp_path / "published-evaluations/fixture.json",
        {"mode": "campaign", "provenance": "offline_fixture", "status": "finished", "rows": rows},
    )
    app = FastAPI()
    register_evaluations(app, tmp_path)
    return TestClient(app)


@pytest.mark.parametrize(
    "mode", ["keep_revert", "all_revert", "budget_after_keep", "error_after_keep"]
)
def test_real_run_fix_artifacts_flow_into_campaign_markdown_and_public_api(tmp_path, mode):
    first = {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25}
    second = {
        "before": "VALUE = 2\n",
        "after": "VALUE = 3\n",
        "peak": 20,
        "loss": "changed",
        "checks": {"loss_tolerance": False},
        "verification_extra": {"completed": False},
        "candidate_extra": {"status": "oom"},
    }
    options = {"max_rounds": 2}
    if mode == "all_revert":
        first.update(loss="changed", checks={"loss_tolerance": False})
        plans = [first]
        options["max_rounds"] = 1
    elif mode == "budget_after_keep":
        plans = [first]
        options["budget_after"] = 1
    elif mode == "error_after_keep":
        plans = [first, second]
        options["verify_error_at"] = 2
    else:
        plans = [first, second]
    (tmp_path / "execution").mkdir()
    result, store, requests, _, _ = search_run(tmp_path / "execution", plans, **options)
    try:
        before = {str(path): path.read_bytes() for path in Path(result["run_dir"]).rglob("*.json")}
        row = result_row(
            case(),
            "full_ultra",
            result,
            store.usage(result["run_id"]),
            provenance="offline_fixture",
        )
        row["policy_name"] = "default"
        assert requests and row["patch_applied"] is True
        if mode == "all_revert":
            assert row["selected_round"] is None and row["selected_patch_applied"] is False
            assert row["selected_completed"] is None
        else:
            assert row["selected_round"] == 1 and row["selected_completed"] is True
            assert row["peak_after_bytes"] == 25_000_000_000
        document = {
            "mode": "campaign",
            "status": "finished",
            "provenance": "offline_fixture",
            "rows": [row],
        }
        markdown = render_campaign(document)
        assert "Any patch/config applied" in markdown and "Selected completed" in markdown
        assert "Attempted versus selected outcomes" in markdown
        with _publish(tmp_path / "published", [row]) as api:
            payload = api.get("/api/evaluations/fixture").json()
        published = payload["rows"][0]
        assert published["patch_applied"] is True
        assert published["selected_completed"] is row["selected_completed"]
        assert published["round_outcomes"] == row["round_outcomes"]
        assert payload["summary"]["outcomes"]["patch_applied"]["known_count"] == 0
        assert before == {
            str(path): path.read_bytes() for path in Path(result["run_dir"]).rglob("*.json")
        }
    finally:
        store.close()


def test_summary_excludes_fixtures_and_preserves_unknown_denominators(tmp_path):
    facts = evaluation_outcomes(artifact_result(tmp_path, [(True, True, "keep")], selected=1))
    live = {"status": "completed", "provenance": "live", "cost_usd": "0", **facts}
    historical = {"status": "completed", "provenance": "live", "target_met": True, "cost_usd": "0"}
    fixture = {**live, "provenance": "offline_fixture"}
    counts = summarize([live, historical, fixture])["outcomes"]
    assert counts["patch_applied"] == {
        "true_count": 1,
        "false_count": 0,
        "unknown_count": 1,
        "known_count": 1,
    }
    assert counts["selected_completed"] == counts["patch_applied"]


@pytest.mark.parametrize(
    "change",
    [
        {"round_outcomes": [{"round": True, "patch_applied": True}]},
        {"round_outcomes": [{"round": 1}] * 2},
        {"round_outcomes": [{"round": n} for n in range(1, 8)]},
        {"outcome_basis": "inferred_from_status"},
    ],
)
def test_public_projection_rejects_invalid_or_unversioned_outcomes(tmp_path, change):
    facts = evaluation_outcomes(artifact_result(tmp_path, [(True, True, "keep")], selected=1))
    projected = public_outcomes({**facts, **change})
    assert projected["outcome_basis"] is None
    assert projected["patch_applied"] is projected["selected_completed"] is None


def test_public_projection_never_exposes_artifact_paths_and_never_coerces_booleans(tmp_path):
    facts = evaluation_outcomes(artifact_result(tmp_path, [(True, True, "keep")], selected=1))
    facts["round_outcomes"][0].update(
        patch_applied="true", candidate_completed=1, path="/private/.env"
    )
    facts["path"] = "/private/.env"
    projected = public_outcomes(facts)
    assert "/private" not in json.dumps(projected)
    assert projected["patch_applied"] is None and projected["selected_completed"] is None


@pytest.mark.parametrize("raw_present", [False, True])
def test_selected_identity_uses_the_actual_verification_source(tmp_path, raw_present):
    result = artifact_result(tmp_path, [(True, True, "keep")], selected=1)
    result["report"]["rounds"][0]["verification"] = {
        "completed": True,
        "after": {"run_id": "a-different-candidate"},
    }
    if not raw_present:
        (tmp_path / "rounds/01/verification.json").unlink()
    facts = evaluation_outcomes(result)
    if raw_present:
        assert facts["round_outcomes"][0]["candidate_completed"] is None
    else:
        # The candidate completion itself is known; its identity cannot be
        # substituted for the different selected after-run in the final report.
        assert facts["round_outcomes"][0]["candidate_completed"] is True
    assert facts["selected_completed"] is None
    assert public_outcomes(facts)["selected_completed"] is None
