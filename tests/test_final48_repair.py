"""Offline F3 pack/sequence checks. Workload source is never imported or executed."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_final48_ablation import offline as offline  # noqa: PLC0414

from headroom.acceptance import final48_repair as repair


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    cases = []
    for index, identifier in enumerate(repair.SCENARIOS):
        repository = identifier == "nanogpt"
        directory = (
            Path(".cache/upstream/nanoGPT") if repository else Path("scenarios") / identifier
        )
        source = root / directory / "train.py"
        source.parent.mkdir(parents=True)
        source.write_text("raise AssertionError('workload must not execute')\n")
        case = {
            "id": identifier,
            "group": "repository" if repository else "synthetic",
            "script": str(directory / "train.py"),
            "source_root": str(directory),
            "target": "fit:22GB"
            if identifier in {"s2_capacity_v2", "nanogpt"}
            else "reclaim"
            if index in {2, 4, 6, 7}
            else "fix-oom",
            "expected_baseline": "completed" if index in {1, 2, 4, 6, 7} else "oom",
            "truth_status": "unverified",
            "source_sha256": repair.file_record(source, 1024)["sha256"],
            "reclaim_reduction_pct": 20.0 if index in {1, 2, 4, 6, 7} else 30.0,
        }
        if repository:
            case.update(repository_manifest="repos/nanogpt.yaml", source_profile="pinned_nanogpt")
        cases.append(case)
    (root / "repos").mkdir()
    (root / "repos/nanogpt.yaml").write_text(
        json.dumps({"ref": "a" * 40, "command": "python train.py"})
    )
    hf_source = root / "repos/hf_trainer/train.py"
    hf_source.parent.mkdir()
    hf_source.write_text("raise AssertionError('HF must not execute')\n")
    hf = {
        "id": "hf_trainer",
        "group": "repository",
        "script": "repos/hf_trainer/train.py",
        "source_root": "repos/hf_trainer",
        "target": "fix-oom",
        "expected_baseline": "oom",
        "repository_manifest": "repos/hf_trainer.yaml",
        "truth_status": "unverified",
        "source_sha256": repair.file_record(hf_source, 1024)["sha256"],
    }
    (root / "repos/hf_trainer.yaml").write_text("command: python train.py\n")
    (root / "eval").mkdir()
    (root / "eval/mvp_phase1_v2.yaml").write_text(json.dumps({"version": 1, "scenarios": cases}))
    (root / "eval/scenario_set_v2.yaml").write_text(json.dumps({"version": 1, "scenarios": [hf]}))
    calibration = root / repair.CALIBRATION
    calibration.parent.mkdir(parents=True)
    plan = calibration.parent / "preregistration.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "headroom.s2-calibration.v2",
                "required_steps": 20,
                "fit_limit_bytes": 22000000000,
                "source_pins": {"capacity_baseline": {"sha256": cases[1]["source_sha256"]}},
            }
        )
    )
    calibration.write_text(
        json.dumps(
            {
                "schema": "headroom.s2-calibration-audit.v2",
                "accepted": True,
                "errors": [],
                "cases": [{"accepted": True}] * 5,
                "preregistration_sha256": repair.file_record(plan, 4096)["sha256"],
            }
        )
    )
    monkeypatch.setattr(
        repair.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="a" * 40 + "\n"),
    )
    monkeypatch.setattr(
        repair,
        "implementation_pins",
        lambda: {"fixed-implementation": {"sha256": "b" * 64, "bytes": 1}},
    )
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    pack = repair.prepare_f3(project_root=root)
    assert before == sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    path = root / "runs/prepared/preparation.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(pack))
    profile = root / ".cache/new/profile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text(json.dumps({"diagnosis_request_policy": repair.CONTROLS["request_policy"]}))
    return root, path, pack


def test_pure_plan_has_twelve_separate_cells_and_original_controls(prepared):
    root, path, pack = prepared
    assert len(pack["cells"]) == len({x["cell_id"] for x in pack["cells"]}) == 12
    assert [x["result_group"] for x in pack["cells"]] == ["fixed_nine"] * 9 + ["s2_tiers"] * 2 + [
        "hf_trainer"
    ]
    assert [x["scenario_id"] for x in pack["cells"][:9]] == list(repair.SCENARIOS)
    assert all(
        x["request"]["policy"].get("numerical_requirement", "legacy") == "legacy"
        for x in pack["cells"][:9]
    )
    assert pack["cells"][9]["request"]["policy"]["numerical_requirement"] == "exact-loss20-v1"
    assert pack["cells"][10]["request"]["policy"]["numerical_requirement"] == "observed-bf16-v1"
    assert pack["cells"][11]["request"]["policy"]["allow_numerics_change"] is True
    assert all(
        cell["request"]["reclaim_reduction_pct"] == 20
        for cell in pack["cells"][:9]
        if cell["request"]["target"] == "reclaim"
    )
    assert pack["controls"]["fixed_denominator"] == 9 and pack["controls"]["minimum_targets"] == 6
    assert repair.verify_preparation(path, expected_sha256=pack["preparation_sha256"]) == pack
    assert not (root / ".env").exists() and not (root / ".cache/budget.db").exists()


def test_source_tampering_refuses_even_with_unchanged_preparation(prepared):
    root, path, pack = prepared
    (root / pack["cells"][0]["case"]["script"]).write_text("changed\n")
    with pytest.raises(repair.F3Refused):
        repair.verify_preparation(path, expected_sha256=pack["preparation_sha256"])


def test_reviewed_digest_is_required_and_pack_mutations_refuse(prepared):
    _, path, pack = prepared
    changed = copy.deepcopy(pack)
    changed["controls"]["fixed_denominator"] = 12
    path.write_text(json.dumps(changed))
    with pytest.raises(repair.F3Refused, match="PREPARATION_CHANGED"):
        repair.verify_preparation(path, expected_sha256=pack["preparation_sha256"])
    with pytest.raises(repair.F3Refused, match="REVIEWED_PREPARATION_SHA_REQUIRED"):
        repair.verify_preparation(path, expected_sha256=None)


def test_bound_requests_preserve_controls_and_bind_runtime_profile(prepared):
    root, _, pack = prepared
    requests = repair.bound_requests(
        pack, profile_path=root / ".cache/new/profile.json", daily_limit_usd="4"
    )
    pins = repair.cell_request_pins(
        pack, profile_path=root / ".cache/new/profile.json", daily_limit_usd="4"
    )
    assert len(pins) == 12
    assert requests["s2-strict"].policy.numerical_requirement == "exact-loss20-v1"
    assert all(
        request.budget_usd == "0.6" and request.max_steps == 20 for request in requests.values()
    )
    assert pins["s2-strict"] != pins["s2-allow-precision"]
    assert pack["cells"][0]["request"]["runtime_profile"] is None


class FakeAllocation:
    def __init__(self, root, costs):
        self.root, self.costs, self.claimed, self.children, self.spent = (
            root,
            costs,
            False,
            [],
            repair.Decimal(0),
        )
        self.blocked = False
        self.finished = None

    def verify_receipt(self, receipt, *, project_root):
        assert project_root == self.root
        return {
            "profile_path": str(self.root / ".cache/new/profile.json"),
            "amounts": {"daily_limit_usd": "4"},
        }

    def claim_f3_parent(self, receipt, **kwargs):
        if self.claimed:
            raise repair.F3Refused("ALLOCATION_EXECUTION_ALREADY_CLAIMED")
        assert len(kwargs["cell_requests"]) == 12
        self.claimed = True
        return {"scope_limit_usd": kwargs["scope_limit_usd"]}

    def f3_accounting(self, parent):
        return {
            "status": "blocked" if self.blocked else "active",
            "all_costs_known": not self.blocked,
            "scope_limit_usd": parent["scope_limit_usd"],
            "scope_spent_usd": None if self.blocked else str(self.spent),
        }

    def claim_f3_child(self, parent, *, cell_id, request, run_id):
        assert not self.blocked and request.budget_usd == "0.6"
        child = {"cell_id": cell_id, "run_id": run_id, "index": len(self.children)}
        self.children.append(child)
        return child

    def finish_f3_child(self, binding, *, execution_terminal, cleanup_verified):
        value = self.costs[binding["index"]]
        self.blocked = (
            value is None
            or not execution_terminal
            or not cleanup_verified
            or repair.Decimal(value) > repair.PER_RUN
        )
        if value is not None:
            self.spent += repair.Decimal(value)
        return {
            "status": "blocked" if self.blocked else "settled",
            "actual_usd": value,
            "scope_spent_usd": None if value is None else str(self.spent),
        }

    def finish_f3_parent(self, parent, *, status):
        self.finished = status


def fake_supervisor(
    request, *, store, run_id, run_root, preparation, allocation_child_binding, **kwargs
):
    assert request.runtime_profile.endswith("profile.json")
    assert allocation_child_binding["run_id"] == run_id
    assert preparation["case"]["source_sha256"]
    directory = Path(run_root) / run_id
    directory.mkdir(parents=True)
    store.create_run(
        run_id, status="completed", provenance="offline_fixture", run_dir=str(directory)
    )
    report = {
        "run": {"run_id": run_id, "target_met": True, "provenance": "offline_fixture"},
        "summary": {"target_met": True, "loss_equivalence": "identical"},
        "rounds": [],
        "verification": {"target_met": True},
        "measurements": {},
    }
    return {
        "run_id": run_id,
        "run_dir": str(directory),
        "status": "completed",
        "report": report,
        "evaluation_timing": {
            "cleanup_verified": True,
            "within_wall_limit": True,
            "cli": {"verified": True},
        },
    }


def execute(prepared, costs, **kwargs):
    root, path, pack = prepared
    allocation = FakeAllocation(root, costs)
    result = repair.execute_f3(
        path,
        expected_sha256=pack["preparation_sha256"],
        allocation_receipt=root / "fake-receipt.json",
        profile_path=root / ".cache/new/profile.json",
        output_dir=root / "runs/execution",
        execute=True,
        live_authorized=True,
        _allocation=allocation,
        _supervisor=fake_supervisor,
        **kwargs,
    )
    return allocation, result


def test_twelve_sequential_cells_never_merge_extra_successes_into_nine(prepared):
    allocation, result = execute(prepared, ["0.1"] * 12)
    assert result["provenance"] == "offline_fixture"
    assert len(allocation.children) == 12
    assert result["fixed_nine"]["denominator"] == 9
    assert result["fixed_nine"]["target_met_count"] == 0
    assert result["fixed_nine"]["offline_fixture_target_count"] == 9
    assert result["fixed_nine"]["threshold_met"] is False
    assert len(result["s2_tiers"]) == 2 and result["hf_trainer"]["scenario_id"] == "hf_trainer"
    assert result["hf_trainer"]["configuration_check"]["status"] == "unavailable"
    assert result["status"] == "finished" and result["scope_spent_usd"] == "1.2"
    assert allocation.finished == "completed"


def test_scope_shortfall_keeps_all_twelve_rows_and_unrun_rows(prepared):
    allocation, result = execute(prepared, ["0.6"] * 12)
    assert len(allocation.children) == 6
    assert result["scope_spent_usd"] == "3.6"
    assert result["remaining_unrun_cells"] == 6
    assert result["fixed_nine"]["denominator"] == 9
    assert result["stop_reason"] == "insufficient_scope_for_next_full_run"
    assert allocation.finished == "stopped"


@pytest.mark.parametrize("cost", [None, "0.7"])
def test_unknown_or_overrun_cost_stops_and_is_never_replaced_with_zero(prepared, cost):
    allocation, result = execute(prepared, [cost] + ["0.1"] * 11)
    assert len(allocation.children) == 1
    assert result["rows"][0]["cost_usd"] == cost
    assert result["rows"][0]["target_met"] is False
    assert result["remaining_unrun_cells"] == 11
    assert allocation.finished == "blocked"


def test_authorization_guard_before_io(prepared):
    root, path, pack = prepared
    with pytest.raises(repair.F3Refused, match="EXPLICIT_LIVE_AUTHORIZATION_REQUIRED"):
        repair.execute_f3(
            path,
            expected_sha256=pack["preparation_sha256"],
            allocation_receipt="missing",
            profile_path="missing",
            output_dir=root / "runs/not-created",
        )
    assert not (root / "runs/not-created").exists()


def test_replayed_parent_cannot_reset_scope(prepared):
    root, path, pack = prepared
    allocation, _ = execute(prepared, ["0.1"] * 12)
    with pytest.raises(repair.F3Refused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        repair.execute_f3(
            path,
            expected_sha256=pack["preparation_sha256"],
            allocation_receipt=root / "fake-receipt.json",
            profile_path=root / ".cache/new/profile.json",
            output_dir=root / "runs/replayed",
            execute=True,
            live_authorized=True,
            _allocation=allocation,
            _supervisor=fake_supervisor,
        )


def test_unrun_and_running_intents_are_not_measured(prepared):
    _, _, pack = prepared
    document = {"rows": [repair._empty_row(cell, "live") for cell in pack["cells"]]}
    repair._summaries(document)
    assert document["executed_cells"] == 0
    assert document["fixed_nine"]["summary"]["attempted_live_runs"] == 0
    assert document["fixed_nine"]["summary"]["status"] == "pending"
    assert document["fixed_nine"]["denominator"] == 9
    document["rows"][0]["status"] = "running"
    repair._summaries(document)
    assert document["fixed_nine"]["summary"]["attempted_live_runs"] == 0


def test_legacy_default_profile_is_rejected_before_parent_claim(prepared):
    root, _, _ = prepared
    (root / ".cache/new/profile.json").write_text("{}")
    with pytest.raises(repair.F3Refused, match="F3_DIAGNOSIS_REQUEST_POLICY_REQUIRED"):
        execute(prepared, ["0.1"] * 12)
    assert not (root / "runs/execution").exists()


def test_real_temporary_allocation_driver_binding_and_settlement(prepared):
    from test_diagnosis_acceptance import profile

    from headroom.acceptance import allocation
    from headroom.budget import BudgetLedger

    root, path, pack = prepared
    old = BudgetLedger(root / ".cache/budget.db", total_limit="6", daily_limit="6")
    old.open_run("offline-history", "0.1")
    old.close_run("offline-history")
    profile_path, _ = profile(root)
    profile_document = json.loads(profile_path.read_text())
    profile_document.update(
        authorized_total_usd="6.43",
        available_credit_usd="8.43",
        diagnosis_request_policy=repair.CONTROLS["request_policy"],
    )
    plan = allocation.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6.43",
        "available_gift_usd": "8.43",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": "6.43",
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"].update(F1="1.5", F3="4")
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    bound_profile = root / ".cache/final48-allocation/runtime-profile.json"
    pins = repair.cell_request_pins(pack, profile_path=bound_profile, daily_limit_usd="6.43")
    plan["task_pins"]["F3"] = {
        "preparation_sha256": pack["preparation_sha256"],
        "cell_requests_sha256": allocation.digest(pins),
    }
    authorization = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "6.43",
        "approval_message_ref": "offline-fixture-not-human-authorization",
        "statement_sha256": "5" * 64,
    }
    receipt = allocation.activate_allocation(
        plan, authorization, profile_document, project_root=root
    )
    receipt_path = root / ".cache/final48-allocation/receipt.json"
    previous = allocation.verify_and_claim_allocation(
        receipt_path,
        project_root=root,
        task_scope="F1",
        execution_key="once",
        profile_path=bound_profile,
        run_limit_usd="1.5",
        daily_limit_usd="6.43",
        preparation_sha256="2" * 64,
        scoring_policy_sha256="3" * 64,
    )
    preceding = BudgetLedger(
        receipt["ledger_path"], total_limit="6.43", daily_limit="6.43", require_existing=True
    )
    preceding.open_run(previous.run_id, "1.5")
    preceding.reserve(previous.run_id, "offline-F1", "1.5")
    preceding.settle(previous.run_id, "offline-F1", "1.5")
    preceding.close_run(previous.run_id)
    allocation.finish_claim(previous, status="completed")
    dispatched = []

    def supervisor(request, **kwargs):
        assert request.daily_budget_usd == "6.43"
        binding = kwargs["allocation_child_binding"]
        verified = allocation.verify_child_binding(
            binding, request=request, run_id=kwargs["run_id"], environ={}
        )
        budget = BudgetLedger(
            verified.database.path,
            require_existing=True,
            expected_identity=verified.database.file_identity,
            total_limit=verified.total_limit_usd,
            daily_limit=verified.daily_limit_usd,
        )
        run_id = kwargs["run_id"]
        budget.open_run(run_id, binding["run_limit_usd"])
        budget.reserve(run_id, run_id + "-offline", "0.6")
        budget.settle(run_id, run_id + "-offline", "0.3")
        budget.close_run(run_id)
        dispatched.append((binding["cell_id"], request.policy.numerical_requirement))
        return fake_supervisor(request, **kwargs)

    result = repair.execute_f3(
        path,
        expected_sha256=pack["preparation_sha256"],
        allocation_receipt=root / ".cache/final48-allocation/receipt.json",
        profile_path=bound_profile,
        output_dir=root / "runs/real-accounting-fixture",
        execute=True,
        live_authorized=True,
        _allocation=allocation,
        _supervisor=supervisor,
    )
    assert len(dispatched) == 12
    assert dispatched[9:] == [
        ("s2-strict", "exact-loss20-v1"),
        ("s2-allow-precision", "observed-bf16-v1"),
        ("hf-trainer", "legacy"),
    ]
    assert result["scope_spent_usd"] == "3.6" and result["all_costs_known"] is True
    assert result["status"] == "finished" and result["provenance"] == "offline_fixture"
    assert result["fixed_nine"]["threshold_met"] is False
    assert all(row["settlement"]["actual_usd"] == "0.3" for row in result["rows"])

    assert result["accounting"]["new_pool_charged_usd"] == "5.1"
    assert result["accounting"]["total_limit_usd"] == "5.5"


def test_cleanup_uncertainty_stops_after_first_cell(prepared):
    root, path, pack = prepared
    allocation = FakeAllocation(root, ["0.1"] * 12)

    def incomplete(request, **kwargs):
        result = fake_supervisor(request, **kwargs)
        result["evaluation_timing"]["cleanup_verified"] = False
        return result

    result = repair.execute_f3(
        path,
        expected_sha256=pack["preparation_sha256"],
        allocation_receipt=root / "fake-receipt.json",
        profile_path=root / ".cache/new/profile.json",
        output_dir=root / "runs/no-cleanup",
        execute=True,
        live_authorized=True,
        _allocation=allocation,
        _supervisor=incomplete,
    )
    assert len(allocation.children) == 1 and result["remaining_unrun_cells"] == 11
    assert result["rows"][0]["execution_certified"] is False
    assert result["rows"][0]["cost_usd"] == "0.1"
    assert allocation.finished == "blocked"
