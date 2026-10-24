"""Offline evaluation plumbing. Fixture outputs are never benchmark results."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from headroom.evaluation import (
    _SuperDiagnosisRouter,
    condition_services,
    execute_baselines,
    load_manifest,
    restricted_evidence,
    run_campaign,
    run_fixture_campaign,
    summarize,
    validate_manifest,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in offline evaluation tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def manifest(tmp_path, count=1):
    cases = []
    for i in range(count):
        root = tmp_path / ("case_" + str(i))
        root.mkdir()
        (root / "train.py").write_text("VALUE=1\n")
        cases.append(
            {
                "id": "case_" + str(i),
                "group": "synthetic",
                "script": root.name + "/train.py",
                "source_root": root.name,
                "target": "reclaim",
                "expected_baseline": "completed",
                "ground_truth": "activations",
                "truth_status": "authored",
            }
        )
    path = tmp_path / "manifest.yaml"
    path.write_text(json.dumps({"version": 1, "scenarios": cases}))
    return path


def test_validate_only_does_not_execute_or_claim_baselines(tmp_path):
    path = manifest(tmp_path)
    result = validate_manifest(path, project_root=tmp_path)
    assert result["status"] == "valid"
    assert result["executed"] is False
    assert result["baseline_acceptance"] == "pending"
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("malicious", ["../outside.py", "/etc/passwd", ".env"])
def test_manifest_paths_reject_escape_and_private_files(tmp_path, malicious):
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"][0]["script"] = malicious
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_manifest(path, project_root=tmp_path)


def test_symlink_source_rejected(tmp_path):
    path = manifest(tmp_path)
    script = tmp_path / "case_0/train.py"
    script.unlink()
    script.symlink_to(tmp_path / "manifest.yaml")
    with pytest.raises(ValueError):
        load_manifest(path, project_root=tmp_path)


def test_missing_script_remains_incomplete_not_validated_baseline(tmp_path):
    path = manifest(tmp_path)
    (tmp_path / "case_0/train.py").unlink()
    assert validate_manifest(path, project_root=tmp_path)["status"] == "incomplete"


def test_duplicate_ids_rejected(tmp_path):
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"].append(data["scenarios"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate"):
        load_manifest(path, project_root=tmp_path)


def test_baseline_requires_explicit_execution(tmp_path):
    path = manifest(tmp_path)
    with pytest.raises(ValueError, match="execute=True"):
        execute_baselines(path, project_root=tmp_path)
    assert not (tmp_path / "runs").exists()


def test_baseline_fake_completed_is_not_gpu_acceptance(tmp_path):
    path = manifest(tmp_path)
    calls = []

    def fake(script, **kwargs):
        calls.append((script, kwargs))
        return {
            "status": "completed",
            "steps": 20,
            "capture_complete": True,
            "cleanup_verified": True,
            "run_id": "fixture",
            "peak_allocated_bytes": 50,
        }

    result = execute_baselines(path, project_root=tmp_path, execute=True, runner=fake)
    assert len(calls) == 1
    assert result["rows"][0]["behavior_matches"] is True
    assert result["provenance"] == "offline_fixture"
    assert result["accepted"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"status": "error"},
        {"steps": 19},
        {"capture_complete": False},
        {"cleanup_verified": False},
        {"status": "oom"},
    ],
)
def test_incomplete_or_wrong_baseline_behavior_fails(tmp_path, change):
    path = manifest(tmp_path)

    def fake(*args, **kwargs):
        return {
            "status": "completed",
            "steps": 20,
            "capture_complete": True,
            "cleanup_verified": True,
            **change,
        }

    result = execute_baselines(path, project_root=tmp_path, execute=True, runner=fake)
    assert result["rows"][0]["behavior_matches"] is False


def test_baseline_history_is_never_overwritten(tmp_path):
    path = manifest(tmp_path)

    def fake(*args, **kwargs):
        return {"status": "error"}

    first = execute_baselines(path, project_root=tmp_path, execute=True, runner=fake)
    old = Path(first["report_path"]).read_bytes()
    second = execute_baselines(path, project_root=tmp_path, execute=True, runner=fake)
    assert first["report_path"] != second["report_path"]
    assert Path(first["report_path"]).read_bytes() == old


@pytest.mark.parametrize("options", [{}, {"execute": True}, {"live_authorized": True}])
def test_live_gate_does_not_read_credentials_or_execute(tmp_path, options):
    path = manifest(tmp_path)
    with pytest.raises(ValueError, match="Live campaigns"):
        run_campaign(path, project_root=tmp_path, **options)
    assert not (tmp_path / "runs").exists()


def fake_runner(cost="0.5", fail=False):
    def run(request, *, store, run_root, run_id, services):
        store.create_run(run_id, {"status": "running", "provenance": "offline_fixture"})
        store.add_llm_call(
            run_id,
            {
                "model": "offline-test-model",
                "role": "diagnose",
                "cost_usd": cost,
                "input_tokens": 10,
                "output_tokens": 10,
            },
        )
        if fail:
            raise RuntimeError("Deliberate offline fixture failure")
        directory = Path(run_root) / run_id
        (directory / "rounds/01").mkdir(parents=True)
        (directory / "rounds/01/diagnosis.json").write_text(
            json.dumps(
                {
                    "diagnosis": {"root_causes": [{"category": "activations"}]},
                }
            )
        )
        return {
            "run_id": run_id,
            "status": "completed",
            "run_dir": str(directory),
            "report": {
                "summary": {"target_met": True, "peak_reduction_pct": "20"},
                "measurements": {
                    "before": {"peak_allocated_bytes": 100},
                    "after": {"peak_allocated_bytes": 80},
                },
                "run": {"elapsed_seconds": 1.0},
                "rounds": [{}],
            },
        }

    return run


def test_fixture_campaign_excluded_from_actual_scores(tmp_path):
    path = manifest(tmp_path)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(),
        services_factory=lambda *args: None,
    )
    assert result["rows"][0]["first_cause_matches"] is True
    assert result["summary"]["status"] == "pending"
    assert result["summary"]["attempted_live_runs"] == 0
    assert result["summary"]["offline_fixture_rows_excluded"] == 1
    assert "offline-fixtures" in result["report_path"]


def test_campaign_reserves_whole_next_run_not_just_last_actual_cost(tmp_path):
    path = manifest(tmp_path, 3)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(),
        services_factory=lambda *args: None,
        per_run_budget_usd="0.6",
        campaign_budget_usd="1.0",
    )
    assert [r["status"] for r in result["rows"]] == ["completed", "pending", "pending"]
    assert result["halt_reason"] == "campaign_budget_cannot_reserve_next_run"


def test_unknown_cost_stops_remaining_dispatch_and_stays_unknown(tmp_path):
    path = manifest(tmp_path, 2)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(cost=None),
        services_factory=lambda *args: None,
    )
    assert result["halt_reason"] == "unresolved_cost_requires_review"
    assert result["rows"][0]["cost_usd"] is None
    assert result["rows"][1]["status"] == "pending"


def test_exception_after_billing_retains_failed_cost(tmp_path):
    path = manifest(tmp_path)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(fail=True),
        services_factory=lambda *args: None,
    )
    assert result["rows"][0]["status"] == "error"
    assert Decimal(result["rows"][0]["cost_usd"]) == Decimal("0.5")


def test_summary_keeps_unknown_failures_in_denominator_and_cost(tmp_path):
    rows = [
        {
            "provenance": "live",
            "status": "completed",
            "target_met": True,
            "condition": "full_ultra",
            "cost_usd": "0.2",
            "first_cause_matches": True,
        },
        {
            "provenance": "live",
            "status": "error",
            "target_met": None,
            "condition": "full_ultra",
            "cost_usd": None,
            "first_cause_matches": None,
        },
        {
            "provenance": "offline_fixture",
            "status": "completed",
            "target_met": True,
            "cost_usd": "0",
        },
    ]
    result = summarize(rows)
    assert result["target_met_rate"] is None
    assert result["target_success_lower_bound"] == 0.5
    assert result["target_unknown_runs"] == 1
    assert result["total_cost_usd"] is None
    assert Decimal(result["known_cost_usd"]) == Decimal("0.2")
    assert result["first_cause_scored_denominator"] == 1


def test_traceback_condition_has_no_snapshot_or_source_leakage():
    markdown, evidence = restricted_evidence(
        {
            "evaluation_inputs": {"traceback": "OOM traceback", "memory_summary": "summary"},
            "analysis": {"stack_catalog": {"stk_secret": [{"text": "snapshot-secret"}]}},
            "sources": [{"text": "source-secret"}],
        }
    )
    assert "snapshot-secret" not in markdown and "source-secret" not in markdown
    assert set(evidence["analysis"]["stack_catalog"]) == {"traceback", "memory_summary"}


def test_missing_restricted_capture_not_filled_with_fake_context():
    with pytest.raises(ValueError, match="lacks captured"):
        restricted_evidence({"analysis": {"header": {}}})


def test_super_diagnosis_keeps_underlying_router_and_billing_path():
    called = []

    class Router:
        def chat(self, role, *args, **kwargs):
            called.append((role, args, kwargs))
            return "offline-response"

    wrapped = _SuperDiagnosisRouter(Router())
    assert wrapped.chat("diagnose", ["message"], max_tokens=4000) == "offline-response"
    assert called[0][0] == "patcher"
    assert called[0][2]["max_tokens"] == 4000


def test_conditions_remain_internal_services_hooks(tmp_path):
    from headroom.orchestrator import FixRequest

    services = condition_services("full_ultra", tmp_path / "audit")
    assert services.evaluation_condition == "full_ultra"
    assert "evaluation_condition" not in FixRequest.model_fields


def test_source_pin_mismatch_blocks_baseline_before_runner(tmp_path):
    import hashlib

    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    script = tmp_path / "case_0/train.py"
    data["scenarios"][0]["source_sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    path.write_text(json.dumps(data))
    script.write_text("CHANGED=2\n")
    assert validate_manifest(path, project_root=tmp_path)["status"] == "incomplete"

    def forbidden(*args, **kwargs):
        pytest.fail("Changed source must not execute")

    result = execute_baselines(path, project_root=tmp_path, execute=True, runner=forbidden)
    assert result["rows"][0]["status"] == "error"


def test_ablation_only_scores_matching_sources_with_all_three_conditions():
    from headroom.evaluation import CONDITIONS, ablation_summary

    rows = [
        {
            "scenario_id": "s1",
            "group": "synthetic",
            "condition": condition,
            "status": "completed",
            "provenance": "live",
            "run_id": condition,
            "source_sha256": "a" * 64,
            "truth_status": "authored",
            "first_cause_matches": condition != "traceback_ultra",
        }
        for condition in CONDITIONS
    ]
    summary = ablation_summary(rows)
    assert summary["paired_scored_count"] == 1
    assert summary["ultra_full_minus_traceback"] == 1.0
    rows[-1]["source_sha256"] = "b" * 64
    summary = ablation_summary(rows)
    assert summary["paired_scored_count"] == 0
    assert summary["ultra_full_minus_traceback"] is None
    assert summary["excluded"][0]["reason"] == "source_hash_not_comparable"


def test_unverified_truth_and_offline_fixtures_cannot_be_ablation_wins():
    from headroom.evaluation import CONDITIONS, ablation_summary

    rows = [
        {
            "scenario_id": "s5",
            "group": "synthetic",
            "condition": condition,
            "status": "completed",
            "provenance": "live",
            "run_id": condition,
            "source_sha256": "a" * 64,
            "truth_status": "unverified",
            "first_cause_matches": True,
        }
        for condition in CONDITIONS
    ]
    assert ablation_summary(rows)["paired_scored_count"] == 0
    for row in rows:
        row["provenance"] = "offline_fixture"
    assert ablation_summary(rows)["status"] == "pending"


def test_ablation_default_selects_only_eight_synthetic_group_candidates(tmp_path):
    path = manifest(tmp_path, 2)
    data = json.loads(path.read_text())
    data["scenarios"][1]["group"] = "library"
    path.write_text(json.dumps(data))
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(cost="0.01"),
        services_factory=lambda *args: None,
        conditions=("full_ultra", "traceback_ultra", "full_super"),
    )
    assert len(result["rows"]) == 3
    assert {row["scenario_id"] for row in result["rows"]} == {"case_0"}


def test_restricted_context_keeps_search_decisions_but_not_snapshot_metrics():
    markdown, _ = restricted_evidence(
        {
            "evaluation_inputs": {"memory_summary": "real-summary"},
            "search_state": {
                "round": 2,
                "previous_rounds": [
                    {
                        "number": 1,
                        "fix_id": "f1",
                        "decision": "keep",
                        "reason": "measured_improvement",
                        "memory_improvement_pct": "SECRET-PEAK",
                    }
                ],
                "current_kept": {"round": 1, "numerics_impact": "none", "bytes": "SECRET-BYTES"},
                "policy_flags": {"allow_model_change": False, "not_allowed": True},
            },
        }
    )
    assert "measured_improvement" in markdown and '"round": 2' in markdown
    assert "SECRET-PEAK" not in markdown and "SECRET-BYTES" not in markdown
    assert "not_allowed" not in markdown


def test_condition_audit_hash_names_do_not_claim_wire_requests(tmp_path, monkeypatch):
    import hashlib

    import headroom.diagnose

    marker = object()
    monkeypatch.setattr(headroom.diagnose, "diagnose_with_router", lambda *args, **kwargs: marker)
    services = condition_services("full_ultra", tmp_path / "audit")
    result = services.diagnose(
        object(),
        "literal evidence",
        evidence={"analysis": {"stack_catalog": {"stk_1": []}}},
        goal="reclaim",
        policy={"allow_model_change": False},
    )
    assert result is marker
    audit = json.loads((tmp_path / "audit/01-provenance.json").read_text())
    assert "prompt_sha256" not in audit
    assert audit["evidence_markdown_sha256"] == hashlib.sha256(b"literal evidence").hexdigest()
    assert "before router" in audit["message_scope"]
    messages = json.loads((tmp_path / "audit/01-initial-messages.json").read_text())
    canonical = json.dumps(messages, ensure_ascii=False, allow_nan=False)
    assert (
        audit["initial_messages_before_router_sha256"]
        == hashlib.sha256(canonical.encode()).hexdigest()
    )


def test_explicit_policy_plan_defaults_safe_and_exposes_equivalence(tmp_path):
    from headroom.evaluation import campaign_plan

    path = manifest(tmp_path)
    default = campaign_plan(path, project_root=tmp_path)
    assert default["planned_pipeline_runs"] == 1
    assert default["policies"][0]["policy"]["allow_numerics_change"] is False
    matrix = campaign_plan(
        path, project_root=tmp_path, policy_names=("default", "strict", "allow_precision")
    )
    assert matrix["planned_pipeline_runs"] == 3
    assert matrix["campaign_cap_usd"] == "0.6"
    assert matrix["sum_of_configured_run_caps_usd"] == "1.8"
    assert matrix["can_reserve_all_run_caps"] is False
    assert matrix["provider_api_attempts"] is None
    assert matrix["authorization_expanded"] is False
    assert matrix["policies"][0]["same_effective_policy_as"] == ["strict"]
    assert matrix["policies"][2]["policy"]["allow_numerics_change"] is True
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("names", [(), ("unknown",), ("default", "default")])
def test_invalid_policy_selection_rejected_without_dispatch(tmp_path, names):
    from headroom.evaluation import campaign_plan

    path = manifest(tmp_path)
    with pytest.raises(ValueError):
        campaign_plan(path, project_root=tmp_path, policy_names=names)
    assert not (tmp_path / "runs").exists()


def test_policy_matrix_is_forwarded_and_every_row_records_actual_policy(tmp_path):
    path = manifest(tmp_path)
    observed = []
    original = fake_runner(cost="0.01")

    def wrapper(request, **kwargs):
        observed.append(request.policy.model_dump())
        return original(request, **kwargs)

    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=wrapper,
        services_factory=lambda *args: None,
        policy_names=("default", "allow_precision"),
    )
    assert [policy["allow_numerics_change"] for policy in observed] == [False, True]
    assert [r["policy_name"] for r in result["rows"]] == ["default", "allow_precision"]
    assert [r["policy"] for r in result["rows"]] == observed
    assert result["summary"]["attempted_live_runs"] == 0


def test_policy_matrix_budget_applies_to_combined_runs_not_each_policy(tmp_path):
    path = manifest(tmp_path)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(cost="0.1"),
        services_factory=lambda *args: None,
        policy_names=("default", "allow_precision"),
        campaign_budget_usd="0.6",
    )
    assert [r["status"] for r in result["rows"]] == ["completed", "pending"]
    assert result["rows"][1]["policy"]["allow_numerics_change"] is True
    assert result["halt_reason"] == "campaign_budget_cannot_reserve_next_run"
    assert result["limits"]["campaign_usd"] == "0.6"


def test_unknown_fee_stops_other_policies(tmp_path):
    path = manifest(tmp_path)
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(cost=None),
        services_factory=lambda *args: None,
        policy_names=("default", "allow_precision"),
    )
    assert result["halt_reason"] == "unresolved_cost_requires_review"
    assert result["rows"][1]["status"] == "pending"


def test_policy_matrix_default_uses_original_workloads_without_library_additions(tmp_path):
    from headroom.evaluation import campaign_plan

    path = manifest(tmp_path, 3)
    data = json.loads(path.read_text())
    data["scenarios"][1]["group"] = "repository"
    data["scenarios"][2]["group"] = "library"
    path.write_text(json.dumps(data))
    plan = campaign_plan(path, project_root=tmp_path, policy_names=("default", "strict"))
    assert plan["scenarios"] == ["case_0", "case_1"]
    assert plan["planned_pipeline_runs"] == 4


def test_statistics_keep_missing_denominators_and_do_not_infer_throughput():
    rows = [
        {
            "provenance": "live",
            "status": "completed",
            "target_met": True,
            "cost_usd": "0.2",
            "peak_reduction_pct": "20",
            "step_time_change_pct": "10",
            "rounds": 2,
            "loss_equivalence": "within_tol",
            "policy_name": "default",
        },
        {
            "provenance": "live",
            "status": "failed",
            "reason": "verification_failed",
            "cost_usd": None,
            "peak_reduction_pct": None,
            "rounds": None,
            "loss_equivalence": "n/a",
            "policy_name": "allow_precision",
        },
    ]
    summary = summarize(rows)
    metrics = summary["measured_metrics"]
    assert metrics["peak_reduction_pct"]["mean"] == "20"
    assert metrics["peak_reduction_pct"]["unknown_count"] == 1
    assert metrics["throughput_change_pct"]["mean"] is None
    assert metrics["numerical_equivalence"]["rate_among_comparable"] == 1.0
    assert metrics["numerical_equivalence"]["not_comparable_or_unknown"] == 1
    assert metrics["failure_modes"] == {"verification_failed": 1}
    assert summary["total_cost_usd"] is None
    assert set(summary["by_policy"]) == {"default", "allow_precision"}


def test_ablation_pairs_do_not_mix_different_policies():
    from headroom.evaluation import CONDITIONS, ablation_summary

    rows = [
        {
            "scenario_id": "s1",
            "group": "synthetic",
            "condition": condition,
            "provenance": "live",
            "status": "completed",
            "run_id": name + condition,
            "source_sha256": "a" * 64,
            "truth_status": "authored",
            "first_cause_matches": True,
            "policy_name": name,
            "policy": {"allow_numerics_change": name == "allow_precision"},
        }
        for name in ("default", "allow_precision")
        for condition in CONDITIONS
    ]
    summary = ablation_summary(rows)
    assert summary["paired_scored_count"] == 2
    assert {pair["policy_name"] for pair in summary["pairs"]} == {"default", "allow_precision"}
    rows[0]["policy"]["allow_numerics_change"] = True
    assert ablation_summary(rows)["paired_scored_count"] == 1


def test_partial_cause_scores_never_become_a_complete_accuracy():
    rows = [
        {
            "provenance": "live",
            "status": "completed",
            "target_met": True,
            "first_cause_matches": score,
            "policy_name": "default",
            "cost_usd": "0.1",
        }
        for score in (True, None)
    ]
    result = summarize(rows)
    assert result["first_cause_accuracy"] is None
    assert result["first_cause_accuracy_among_scored"] == 1.0
    assert result["first_cause_success_lower_bound"] == 0.5
    assert result["first_cause_unknown_runs"] == 1
    policy = result["by_policy"]["default"]
    assert policy["first_cause_accuracy"] is None
    assert policy["first_cause_accuracy_among_scored"] == 1.0
    assert policy["first_cause_unknown"] == 1


def test_plan_high_precision_run_caps_never_round_down_to_fit(tmp_path):
    from headroom.evaluation import campaign_plan

    path = manifest(tmp_path)
    plan = campaign_plan(
        path,
        project_root=tmp_path,
        policy_names=("default", "strict"),
        per_run_budget_usd="0.10000000000000000000000000001",
        campaign_budget_usd="0.2",
    )
    assert plan["sum_of_configured_run_caps_usd"] == "0.20000000000000000000000000002"
    assert plan["can_reserve_all_run_caps"] is False


@pytest.mark.parametrize(
    "count,cap,expected_completed",
    [(2, "0.2", 1), (3, "0.30000000000000000000000000002", 2)],
)
def test_high_precision_campaign_reservation_and_accumulation_do_not_exceed_cap(
    tmp_path, count, cap, expected_completed
):
    value = "0.10000000000000000000000000001"
    result = run_fixture_campaign(
        manifest(tmp_path, count),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=fake_runner(cost=value),
        services_factory=lambda *args: None,
        per_run_budget_usd=value,
        campaign_budget_usd=cap,
    )
    assert sum(row["status"] == "completed" for row in result["rows"]) == expected_completed
    assert result["rows"][-1]["status"] == "pending"
    assert result["halt_reason"] == "campaign_budget_cannot_reserve_next_run"


def test_summary_costs_preserve_high_precision_and_full_money_magnitude_span():
    from decimal import localcontext

    values = ["0.10000000000000000000000000001"] * 2
    rows = [
        {"provenance": "live", "status": "completed", "cost_usd": value, "policy_name": "default"}
        for value in values
    ]
    result = summarize(rows)
    expected = "0.20000000000000000000000000002"
    assert result["known_cost_usd"] == expected
    assert result["total_cost_usd"] == expected
    assert result["by_policy"]["default"]["total_cost_usd"] == expected
    assert result["measured_metrics"]["cost_usd"]["mean"] == values[0]

    values = ["9" * 80 + "E+80", "1E-80"]
    for row, value in zip(rows, values, strict=True):
        row["cost_usd"] = value
    with localcontext() as context:
        context.prec = 256
        expected = str(sum(map(Decimal, values), Decimal(0)))
    result = summarize(rows)
    assert result["known_cost_usd"] == expected
    assert result["by_policy"]["default"]["known_cost_usd"] == expected


def test_explicit_reclaim_target_reaches_request_and_campaign_evidence(tmp_path):
    from headroom.evaluation import campaign_plan

    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"][0]["reclaim_reduction_pct"] = 20
    path.write_text(json.dumps(data))
    requests = []

    def observed(request, **kwargs):
        requests.append(request)
        return fake_runner()(request, **kwargs)

    plan = campaign_plan(path, project_root=tmp_path)
    assert plan["targets"][0]["reclaim_reduction_pct"] == 20
    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=observed,
        services_factory=lambda *args: None,
    )
    assert len(requests) == 1
    assert requests[0].reclaim_reduction_pct == 20
    assert requests[0].repository_mode is False
    assert requests[0].execution_argv is None
    assert result["rows"][0]["reclaim_reduction_pct"] == 20


@pytest.mark.parametrize("target", [-1, 0, 101, float("inf"), float("nan"), True, "20"])
def test_invalid_reclaim_target_is_rejected_before_execution(tmp_path, target):
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"][0]["reclaim_reduction_pct"] = target
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_manifest(path, project_root=tmp_path)


def test_mvp_manifest_uses_twenty_only_in_its_original_nine_case_scope():
    root = Path(__file__).resolve().parents[1]
    general = load_manifest(root / "eval/scenario_set.yaml", project_root=root)
    mvp = load_manifest(root / "eval/mvp_phase1.yaml", project_root=root)
    assert len(general.scenarios) == 12
    assert all(case.reclaim_reduction_pct == 30 for case in general.scenarios)
    assert len(mvp.scenarios) == 9
    assert {case.id for case in mvp.scenarios} == {
        case.id for case in general.scenarios if case.group == "synthetic" or case.id == "nanogpt"
    }
    assert all(
        case.reclaim_reduction_pct == (20 if case.target == "reclaim" else 30)
        for case in mvp.scenarios
    )


def repository_case(tmp_path):
    path = manifest(tmp_path)
    source = tmp_path / "case_0"
    (source / "pkg").mkdir()
    (source / "pkg/__init__.py").write_text("")
    (source / "pkg/train.py").write_text("raise RuntimeError('must never execute')\n")
    data = json.loads(path.read_text())
    data["scenarios"][0].update(
        group="repository",
        script="case_0/pkg/train.py",
        script_args=["--batch=4"],
        repository_manifest="repository.yaml",
    )
    path.write_text(json.dumps(data))
    (tmp_path / "repository.yaml").write_text(
        json.dumps(
            {
                "command": "python -u -m pkg.train --batch=4",
            }
        )
    )
    return path


def test_repository_command_survives_baseline_and_repair_request(tmp_path):
    path = repository_case(tmp_path)
    baseline_calls = []

    def baseline(script, **kwargs):
        baseline_calls.append((script, kwargs))
        return {
            "status": "completed",
            "steps": 20,
            "capture_complete": True,
            "cleanup_verified": True,
        }

    baselines = execute_baselines(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "baseline",
        execute=True,
        runner=baseline,
    )
    command = ["python", "-u", "-m", "pkg.train", "--batch=4"]
    assert baseline_calls[0][1]["execution_argv"] == command
    assert baselines["rows"][0]["execution"]["requested_argv"] == command
    assert baselines["rows"][0]["execution"]["execution_argv"] == command
    requests = []

    def observed(request, **kwargs):
        requests.append(request)
        return fake_runner()(request, **kwargs)

    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "campaign",
        runner=observed,
        services_factory=lambda *args: None,
    )
    assert requests[0].repository_mode is True
    assert requests[0].execution_argv == command
    assert requests[0].script_args == ["--batch=4"]
    recorded = result["rows"][0]["execution"]
    assert recorded["command_source"] == "repository.yaml"
    assert len(recorded["repository_manifest_sha256"]) == 64
    assert recorded["execution_argv"] == command


@pytest.mark.parametrize(
    "command",
    [
        "python train.py --batch=4",
        "python -u -m pkg.train --batch=8",
    ],
)
def test_repository_command_mismatch_blocks_dispatch(tmp_path, command):
    path = repository_case(tmp_path)
    (tmp_path / "repository.yaml").write_text(json.dumps({"command": command}))

    def forbidden(*args, **kwargs):
        pytest.fail("Mismatched repository command must not execute")

    result = execute_baselines(
        path,
        project_root=tmp_path,
        execute=True,
        runner=forbidden,
    )
    assert result["rows"][0]["status"] == "error"
    assert result["rows"][0]["error_type"] == "ValueError"


def test_nanogpt_dataset_rewrite_preserves_requested_and_executed_commands(tmp_path):
    from headroom.evaluation import _prepare

    root = Path(__file__).resolve().parents[1]
    manifest_data = load_manifest(root / "eval/mvp_phase1.yaml", project_root=root)
    case = next(case for case in manifest_data.scenarios if case.id == "nanogpt")
    if not (root / case.script).is_file():
        pytest.skip("Reviewed local nanoGPT cache is unavailable; never fetch it")
    script, source, arguments, execution = _prepare(case, root, tmp_path)
    assert script == source / "train.py"
    assert "--dataset=/input" in execution["requested_argv"]
    assert "--dataset=/input" not in execution["execution_argv"]
    assert "--dataset=headroom_synthetic" in arguments
    assert execution["execution_argv"] == ["python", "train.py", *arguments]
    assert (source / "data/headroom_synthetic/train.bin").is_file()
    saved = json.loads((tmp_path / "execution-nanogpt.json").read_text())
    assert saved == execution


def test_repository_without_upstream_command_labels_derived_provenance(tmp_path):
    from headroom.evaluation import _prepare

    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    data["scenarios"][0]["group"] = "repository"
    path.write_text(json.dumps(data))
    case = load_manifest(path, project_root=tmp_path).scenarios[0]
    _, _, _, execution = _prepare(case, tmp_path, tmp_path)
    assert execution["execution_argv"] == ["python", "train.py"]
    assert execution["command_source"] == "scenario entrypoint and script_args"
    assert "repository_manifest_sha256" not in execution


def test_nonregular_repository_manifest_cannot_block_preparation(tmp_path):
    import os

    path = repository_case(tmp_path)
    metadata = tmp_path / "repository.yaml"
    metadata.unlink()
    os.mkfifo(metadata)

    def forbidden(*args, **kwargs):
        pytest.fail("Nonregular manifest must not reach execution")

    result = execute_baselines(path, project_root=tmp_path, execute=True, runner=forbidden)
    assert result["rows"][0]["status"] == "error"
    assert result["rows"][0]["error_type"] == "ValueError"


def test_campaign_keeps_numerical_basis_and_repository_exception_scope(tmp_path):
    path = manifest(tmp_path)

    def observed(request, **kwargs):
        result = fake_runner()(request, **kwargs)
        result["report"]["summary"]["loss_equivalence"] = "n/a"
        result["report"]["verification"] = {
            "numerical_basis": "repository_no_reference_exception",
            "acceptance_scope": "repository",
        }
        return result

    result = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        runner=observed,
        services_factory=lambda *args: None,
    )
    assert result["rows"][0]["numerical_basis"] == "repository_no_reference_exception"
    assert result["rows"][0]["acceptance_scope"] == "repository"
    assert result["rows"][0]["loss_equivalence"] == "n/a"
