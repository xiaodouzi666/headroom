"""Offline common-budget study contracts; no provider/GPU or real files."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from test_actual_usage_budget import reviewed_fixture
from test_cli_execution import setup_case
from test_diagnosis_bounded_repair import evidence, payload
from test_llm_client import completion
from typer.testing import CliRunner

from headroom import cli_execution as bridge
from headroom import evaluation, evaluation_worker
from headroom.acceptance.diagnosis import REQUEST_IMPLEMENTATION_PATHS
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.cli import app
from headroom.diagnose import PROMPT_PATH, build_diagnosis_messages, diagnose_with_router
from headroom.diagnosis_protocol import (
    COMMON_4000,
    DEFAULT_DIAGNOSIS_CAP,
    PROMPT_CAP_MARKER,
    STUDY_CONDITIONS,
    STUDY_SCENARIOS,
    diagnosis_cap,
    diagnosis_prompt,
)
from headroom.orchestrator import FixRequest, Policy
from headroom.runtime import LiveProfile, RuntimeNotReady, build_live_runtime
from headroom.store.db import Store

ROOT = Path(__file__).resolve().parents[1]


def study_profile(tmp_path):
    data = reviewed_fixture(tmp_path).model_dump()
    for name, item in data["models"].items():
        item["billing"].update(
            max_completion_tokens=16384 if name == "ultra" else 8192,
            prompt_token_ceiling=1048576 if name == "ultra" else 262144,
            max_prompt_utf8_bytes=500000,
            output_cap_field="max_completion_tokens",
        )
        item["input_usd_per_million"] = "1" if name == "ultra" else "0.30"
        item["output_usd_per_million"] = "3" if name == "ultra" else "0.90"
        item["capabilities"] = {
            "json_method": "json_schema",
            "reasoning_method": "chat_template_kwargs",
            "evidence": "offline fixture, not a capability certification",
        }
    return LiveProfile.model_validate(data)


def runtime_case(tmp_path, *, total="3", responses=None):
    profile = study_profile(tmp_path)
    store = Store(tmp_path / "store.db")
    store.create_run("study")
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit=total, total_limit=total)
    budget.open_run("study", "0.6", budget_mode="actual_usage")
    bodies = []
    reserved = []
    replies = responses or [payload()]

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        snapshot = budget.snapshot("study")
        reserved.append(
            str(Decimal(snapshot["reserved_or_actual_usd"]) - Decimal(snapshot["known_charge_usd"]))
        )
        response = completion(
            json.dumps(replies[min(len(bodies) - 1, len(replies) - 1)]), model=body["model"]
        )
        response["usage"]["completion_tokens_details"] = {"reasoning_tokens": 5}
        return httpx.Response(200, json=response)

    bundle = build_live_runtime(
        "study",
        profile=profile,
        budget=budget,
        store=store,
        env_file=tmp_path / ".env",
        transport=httpx.MockTransport(respond),
    )
    return bundle, budget, store, profile, bodies, reserved


def call_condition(tmp_path, condition, *, total="3", responses=None, study=COMMON_4000):
    if condition == "traceback_ultra" and responses is None:
        reply = payload()
        reply["root_causes"][0]["evidence_refs"] = ["memory_summary"]
        responses = [reply]
    bundle, budget, store, profile, bodies, reserved = runtime_case(
        tmp_path, total=total, responses=responses
    )
    data = evidence()
    data["evaluation_inputs"] = {"traceback": "Traceback fixture", "memory_summary": "Peak fixture"}
    try:
        services = evaluation.condition_services(
            condition, tmp_path / "audit", study_protocol=study
        )
        result = services.diagnose(
            bundle.router,
            "immutable snapshot evidence stk",
            evidence=data,
            goal="reclaim",
            policy=Policy().model_dump(),
            max_supplements=1,
        )
        rows = store.llm_calls("study")
        state = budget.close_run("study")
        return result, bodies, reserved, rows, state, profile
    finally:
        bundle.close()
        store.close()


def test_normal_contract_and_prepared_dependency_pin_stay_explicit():
    assert DEFAULT_DIAGNOSIS_CAP == diagnosis_cap() == 16384
    normal = build_diagnosis_messages("same", goal="reclaim", policy={})
    common = build_diagnosis_messages("same", goal="reclaim", policy={}, study_protocol=COMMON_4000)
    assert normal[0]["content"] == PROMPT_PATH.read_text().replace(PROMPT_CAP_MARKER, "16384")
    assert common[0]["content"] == normal[0]["content"].replace("16384", "4000")
    assert normal[1] == common[1]
    assert "diagnosis_protocol.py" in REQUEST_IMPLEMENTATION_PATHS
    assert REQUEST_IMPLEMENTATION_PATHS["diagnosis_protocol.py"].is_file()


@pytest.mark.parametrize("value", [True, False, 4000, "", "4000", "default", {}, []])
def test_unknown_protocol_refused_before_any_router_call(value):
    class Never:
        def chat(self, *args, **kwargs):
            pytest.fail("Bad protocol must not reach the router")

    with pytest.raises(ValueError):
        diagnose_with_router(
            Never(), "snapshot", evidence={}, goal="reclaim", policy={}, study_protocol=value
        )


@pytest.mark.parametrize("template", ["no marker", PROMPT_CAP_MARKER * 2])
def test_missing_or_duplicated_prompt_cap_is_not_silently_replaced(template):
    with pytest.raises(ValueError, match="exactly one"):
        diagnosis_prompt(template, COMMON_4000)


def test_all_three_wire_caps_provider_bounds_and_exact_full_input_equivalence(tmp_path):
    results = {}
    for condition in STUDY_CONDITIONS:
        directory = tmp_path / condition
        directory.mkdir()
        results[condition] = call_condition(directory, condition)
    for condition, (result, bodies, reserved, rows, state, profile) in results.items():
        assert len(bodies) == len(rows) == len(reserved) == 1
        body = bodies[0]
        role = "super" if condition == "full_super" else "ultra"
        assert body["model"] == profile.models[role].model_id
        assert body["max_completion_tokens"] == 4000
        assert "max_tokens" not in body
        assert body["chat_template_kwargs"] == {"enable_thinking": True}
        assert "4000" in body["messages"][1]["content"]
        assert PROMPT_CAP_MARKER not in json.dumps(body)
        assert Decimal(reserved[0]) == Decimal("0.0822432" if role == "super" else "1.060576")
        assert rows[0]["admission_kind"] == "verified_provider_bound"
        assert rows[0]["settled"] is True and rows[0]["attempt"] == 1
        assert rows[0]["request_evidence"]["payload"] == body
        assert state["billing_complete"] is True
        assert Decimal(state["conservative_total_usd"]) < Decimal(reserved[0])
        assert profile.models["super"].billing.max_completion_tokens == 8192
        saved = json.loads((tmp_path / condition / "audit/01-initial-messages.json").read_text())
        assert body["messages"][1:] == saved
        audit = json.loads((tmp_path / condition / "audit/01-provenance.json").read_text())
        assert audit["study_protocol"]["id"] == COMMON_4000
        assert audit["diagnosis_max_completion_tokens"] == 4000
    ultra, super_body = results["full_ultra"][1][0], results["full_super"][1][0]
    assert {k: v for k, v in ultra.items() if k != "model"} == {
        k: v for k, v in super_body.items() if k != "model"
    }
    traceback = results["traceback_ultra"][1][0]
    assert traceback["messages"] != ultra["messages"]
    assert "immutable snapshot evidence" not in json.dumps(traceback["messages"])
    assert "Traceback fixture" in json.dumps(traceback["messages"])


def test_supplement_keeps_same_named_budget_and_schema(tmp_path):
    invalid = payload()
    invalid["extra_outside_schema"] = True
    _, bodies, reserved, rows, _, _ = call_condition(
        tmp_path, "full_ultra", responses=[invalid, payload()]
    )
    assert len(bodies) == len(rows) == 2
    assert [b["max_completion_tokens"] for b in bodies] == [4000, 4000]
    assert bodies[0]["response_format"] == bodies[1]["response_format"]
    assert bodies[1]["messages"][: len(bodies[0]["messages"])] == bodies[0]["messages"]
    assert all(Decimal(value) == Decimal("1.060576") for value in reserved)
    assert all(row["attempt"] == 1 and row["settled"] for row in rows)


def test_common_budget_cannot_bypass_full_provider_reservation(tmp_path):
    bundle, _budget, store, _, bodies, _ = runtime_case(tmp_path, total="1.06")
    try:
        with pytest.raises(BudgetExceeded):
            evaluation.condition_services(
                "full_ultra", tmp_path / "audit", study_protocol=COMMON_4000
            ).diagnose(bundle.router, "snapshot", evidence=evidence(), goal="reclaim", policy={})
        assert not bodies and not store.llm_calls("study")
    finally:
        bundle.close()
        store.close()


def test_ordinary_full_super_still_refuses_unverified_16384_not_clamped(tmp_path):
    bundle, _budget, store, _, bodies, _ = runtime_case(tmp_path)
    try:
        with pytest.raises(RuntimeNotReady):
            evaluation.condition_services("full_super", tmp_path / "audit").diagnose(
                bundle.router, "snapshot", evidence=evidence(), goal="reclaim", policy={}
            )
        assert not bodies and not store.llm_calls("study")
    finally:
        bundle.close()
        store.close()


def plan_options():
    return {
        "project_root": ROOT,
        "scenario_ids": list(STUDY_SCENARIOS),
        "conditions": STUDY_CONDITIONS,
        "policy_names": ("strict",),
        "study_protocol": COMMON_4000,
        "campaign_budget_usd": "14.4",
        "search_mode": "until_target",
    }


def test_versioned_plan_fixed_24_no_new_funding_and_old_default_unchanged():
    plan = evaluation.campaign_plan(ROOT / "eval/scenario_set_v2.yaml", **plan_options())
    assert plan["planned_pipeline_runs"] == 24
    assert plan["study_protocol"]["seed"] == FixRequest.model_fields["seed"].default == 1337
    assert plan["study_protocol"]["design"] == "independent_end_to_end"
    assert plan["study_protocol"]["patch_max_completion_tokens"] == 4000
    assert plan["study_protocol"]["diagnosis_enable_thinking"] is True
    assert plan["study_protocol"]["patcher_enable_thinking"] is False
    assert "reasoning" not in plan["study_protocol"]
    assert plan["authorization_expanded"] is False and plan["provider_api_attempts"] is None
    normal = evaluation.campaign_plan(ROOT / "eval/scenario_set_v2.yaml")
    assert "study_protocol" not in normal


@pytest.mark.parametrize(
    "change",
    [
        {"conditions": ("full_super",)},
        {"policy_names": ("default",)},
        {"policy_names": ("strict", "allow_precision")},
        {"scenario_ids": list(STUDY_SCENARIOS[:-1])},
        {"study_protocol": "unknown"},
        {"scenario_ids": [*STUDY_SCENARIOS[:-1], "nanogpt"]},
    ],
)
def test_study_scope_not_silently_changed_or_credential_accessed(change, monkeypatch):
    import headroom.runtime

    monkeypatch.setattr(
        headroom.runtime,
        "read_live_profile",
        lambda *a, **k: pytest.fail("Invalid scope reached private profile"),
    )
    with pytest.raises(ValueError):
        evaluation.run_campaign(
            ROOT / "eval/scenario_set_v2.yaml",
            **(plan_options() | change),
            runtime_profile="unused",
            execute=True,
            live_authorized=True,
        )


def invocation(tmp_path, study):
    request, run_id, values = setup_case(tmp_path)
    spec = bridge.Invocation(
        run_id=run_id,
        request=request.model_dump(),
        queued_request=request.model_dump(),
        store_path=values[1],
        run_root=values[2],
        audit_dir=values[5],
        result_path=values[6],
        deadline=values[7],
        condition=values[4],
        argv=bridge.cli_arguments(request),
        package_root=str(ROOT),
        console_path="/offline/headroom",
        console_sha256="a" * 64,
        source_sha256=bridge.digest(request.script),
        study_protocol=study,
    )
    return request, spec, values


def test_old_invocation_schema_default_and_study_queued_intent_binding(tmp_path):
    _request, spec, _ = invocation(tmp_path, COMMON_4000)
    with pytest.raises(ValueError, match="queued"):
        bridge.CLIExecution(spec)
    state = Store(spec.store_path)
    state.update_run(spec.run_id, study_protocol=COMMON_4000)
    state.close()
    context = bridge.CLIExecution(spec)
    try:
        services = context.before_run(context.expected)["services"]
        assert services.evaluation_condition == "full_ultra"
        assert context.receipt["study_protocol"] == COMMON_4000
        with pytest.raises(ValueError, match="only once"):
            context.before_run(context.expected)
    finally:
        context.close()
    legacy = spec.model_dump()
    legacy.pop("study_protocol")
    assert bridge.Invocation.model_validate(legacy).study_protocol is None
    for wrong in [True, 4000, "unknown"]:
        with pytest.raises(ValidationError):
            bridge.Invocation.model_validate(legacy | {"study_protocol": wrong})


def test_worker_transports_protocol_without_changing_legacy_positional_contract(
    tmp_path, monkeypatch
):
    _, spec, values = invocation(tmp_path, COMMON_4000)
    values[8]["study_protocol"] = COMMON_4000
    captured = []
    monkeypatch.setattr(bridge, "console_script", lambda: ("/offline/headroom", "a" * 64))
    monkeypatch.setattr(bridge, "launch", captured.append)
    evaluation_worker._evaluation_entry(*values)
    assert len(captured) == 1
    assert captured[0].study_protocol == COMMON_4000
    assert captured[0].queued_request == spec.queued_request


def test_cli_named_study_is_explicit_and_no_arbitrary_fix_cap():
    args = [
        "eval",
        "--manifest",
        str(ROOT / "eval/scenario_set_v2.yaml"),
        "--plan-only",
        "--conditions",
        ",".join(STUDY_CONDITIONS),
        "--policies",
        "strict",
        "--study-protocol",
        COMMON_4000,
    ]
    for name in STUDY_SCENARIOS:
        args.extend(["--scenario", name])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["study_protocol"]["diagnosis_max_completion_tokens"] == 4000
    invalid = CliRunner().invoke(app, ["eval", "--validate-only", "--study-protocol", COMMON_4000])
    assert invalid.exit_code != 0


def test_named_study_reaches_one_real_console_exec_and_mock_http(tmp_path):
    from test_cli_execution import execute_case

    _, run_id, values = setup_case(tmp_path)
    values[8]["study_protocol"] = COMMON_4000
    store = Store(values[1])
    store.update_run(run_id, study_protocol=COMMON_4000)
    store.close()
    result, receipt = execute_case(tmp_path, values, mode="pipeline")
    assert result.returncode == 78, result.stderr
    assert receipt["study_protocol"] == COMMON_4000
    assert receipt["run_dispatched"] and receipt["result_saved"]
    store = Store(values[1])
    try:
        calls = store.llm_calls(run_id)
        assert len(calls) == 1 and calls[0]["attempt"] == 1 and calls[0]["settled"]
        body = calls[0]["request_evidence"]["payload"]
        # This legacy fixture explicitly verifies max_tokens; real-profile wire
        # max_completion_tokens is separately checked in all three arms above.
        assert body["max_tokens"] == 4000
        assert body["chat_template_kwargs"] == {"enable_thinking": True}
        assert "4000-token" in body["messages"][1]["content"]
        assert len([e for e in store.events(run_id) if e["kind"] == "run.started"]) == 1
    finally:
        store.close()


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "legacy",
        "cap",
        "seed",
        "args",
        "missing",
        "all_missing_budget",
        "all_wrong_seed",
        "all_bool_seed",
        "all_wrong_mode",
    ],
)
def test_report_cannot_pair_ordinary_16k_or_different_study_controls(change):
    import copy

    from headroom.diagnosis_protocol import study_metadata

    controls = {
        "seed": 1337,
        "script_args": ["--max_steps=20"],
        "target": "reclaim",
        "reclaim_reduction_pct": 30.0,
        "allocator_conf": None,
        "numerical_reference": {"strategy": "legacy"},
        "search_mode": "until_target",
        "per_run_budget_usd": "0.6",
        "campaign_budget_usd": "1",
        "daily_budget_usd": "1",
    }
    rows = [
        {
            "scenario_id": STUDY_SCENARIOS[0],
            "condition": condition,
            "run_id": str(i),
            "provenance": "live",
            "group": "synthetic",
            "policy_name": "strict",
            "policy": Policy().model_dump(),
            "source_sha256": "a" * 64,
            "search_mode": "until_target",
            "truth_status": "authored",
            "first_cause_matches": True,
            **study_metadata(COMMON_4000),
            "study_controls": copy.deepcopy(controls),
        }
        for i, condition in enumerate(STUDY_CONDITIONS)
    ]
    if change == "legacy":
        rows[0].pop("study_protocol")
    elif change == "cap":
        rows[0]["study_protocol"]["diagnosis_max_completion_tokens"] = 16384
    elif change == "seed":
        rows[0]["study_controls"]["seed"] = 42
    elif change == "args":
        rows[0]["study_controls"]["script_args"] = ["--max_steps=2"]
    elif change == "missing":
        rows[0].pop("study_controls")
    elif change == "all_missing_budget":
        for row in rows:
            row["study_controls"].pop("per_run_budget_usd")
    elif change == "all_wrong_seed":
        for row in rows:
            row["study_controls"]["seed"] = 42
    elif change == "all_bool_seed":
        for row in rows:
            row["study_controls"]["seed"] = True
    elif change == "all_wrong_mode":
        for row in rows:
            row["study_controls"]["search_mode"] = "bounded_pareto"
    report = evaluation.ablation_summary(rows)
    assert report["paired_scored_count"] == (1 if change == "none" else 0)
    if change != "none":
        assert report["excluded"][0]["reason"] == "study_protocol_or_controls_not_comparable"
