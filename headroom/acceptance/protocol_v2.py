"""Pure plans for the approved v2 benchmark; no model/GPU execution or rescoring."""

import argparse
import json
from pathlib import Path

from headroom.evaluation import campaign_plan, load_manifest, resolve_policies

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ("primary", "mvp_policy_matrix", "phase2_policy_matrix")


def protocol_plan(
    path: Path,
    *,
    scope: str = "primary",
    project_root: Path = ROOT,
    per_run_budget_usd: str,
    campaign_budget_usd: str,
    daily_budget_usd: str,
) -> dict:
    protocol = json.loads(Path(path).read_text())
    if protocol.get("schema") != "headroom.evaluation-protocol.v2" or scope not in SCOPES:
        raise ValueError("Unknown evaluation protocol/scope")
    primary = protocol["primary"]
    comparison = protocol["policy_comparison"]
    if (
        primary["scenario_count"] != 9
        or primary["minimum_target_met"] != 6
        or primary["policy_names"] != ["strict"]
        or primary["condition"] != "full_ultra"
        or comparison["policy_names"] != ["strict", "allow_precision"]
        or comparison["default_alias"] != "strict"
        or comparison["combine_policy_successes"] is not False
        or protocol["s2"]["classification_in_primary_denominator"] is not False
        or protocol["s2"]["calibration_controls_count_as_model_repairs"] is not False
        or protocol["s2"]["classification_minimum_fraction"] != "0.40"
        or protocol["s2"]["fit_limit_bytes"] != 22_000_000_000
        or protocol["s2"]["required_updates"] != 20
        or protocol["s2"]["minimum_successful_repair_rounds"] != 2
        or protocol["s2"]["maximum_search_rounds"] != 6
    ):
        raise ValueError("Protocol changes an approved score/policy boundary")
    policies = dict(resolve_policies(("default", "strict", "allow_precision")))
    if policies["default"] != policies["strict"] or policies["strict"].allow_numerics_change:
        raise ValueError("Default/strict policy semantics changed")
    if not policies["allow_precision"].allow_numerics_change:
        raise ValueError("Explicit precision permission is unavailable")
    settings = primary if scope == "primary" else protocol["scopes"][scope]
    expected = 9 if scope in {"primary", "mvp_policy_matrix"} else 10
    expected_policies = ["strict"] if scope == "primary" else ["strict", "allow_precision"]
    if settings["scenario_count"] != expected or settings["policy_names"] != expected_policies:
        raise ValueError("Scope has an invalid scenario count or policy matrix")
    manifest_path = (project_root / settings["manifest"]).resolve(strict=True)
    if not manifest_path.is_relative_to(project_root.resolve()):
        raise ValueError("Protocol manifest escapes project root")
    manifest = load_manifest(manifest_path, project_root=project_root)
    cases = [
        row for row in manifest.scenarios if row.group not in settings.get("exclude_groups", [])
    ]
    if len(cases) != expected or "s2_capacity_v2" not in [row.id for row in cases]:
        raise ValueError("Scope does not preserve the approved scenario denominator")
    if any("classification" in row.id for row in cases):
        raise ValueError("Classification preflight is not a repair scenario")
    plan = campaign_plan(
        manifest_path,
        project_root=project_root,
        scenario_ids=[row.id for row in cases],
        conditions=("full_ultra",),
        policy_names=tuple(expected_policies),
        per_run_budget_usd=per_run_budget_usd,
        campaign_budget_usd=campaign_budget_usd,
        daily_budget_usd=daily_budget_usd,
    )
    plan.update(
        protocol=protocol["schema"],
        scope=scope,
        acceptance_certified=False,
        calibration_required_before_execution=True,
        primary_gate={"target_met_minimum": 6, "denominator": 9, "policy": "strict"},
        policy_note="Explicit strict versus allow_precision. Default remains strict; policies are reported separately.",
        historical_scores_modified=False,
        pending_separate_acceptance=[
            "s2_calibration",
            "s2_two_round_search",
            "bf16_pareto_candidate",
            "hf_configuration_diff",
            "library_cases",
        ],
    )
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=ROOT / "eval/protocol_v2.json")
    parser.add_argument("--scope", choices=SCOPES, default="primary")
    parser.add_argument("--per-run-budget-usd", required=True)
    parser.add_argument("--campaign-budget-usd", required=True)
    parser.add_argument("--daily-budget-usd", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            protocol_plan(
                args.protocol,
                scope=args.scope,
                per_run_budget_usd=args.per_run_budget_usd,
                campaign_budget_usd=args.campaign_budget_usd,
                daily_budget_usd=args.daily_budget_usd,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
