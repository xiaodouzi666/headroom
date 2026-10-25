"""Pure offline versioning checks; never imports dispatchers or accesses a ledger."""

import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "acceptance-v2-r2-20261025"
ROOT = HERE.parents[1]


def source(name, directory=HERE):
    return (directory / name).read_text()


def tree(value):
    return ast.dump(ast.parse(value), include_attributes=False)


def main():
    checks = {}

    def check(name, value):
        checks[name] = bool(value)
        assert value, name

    driver = source("run_mvp_v2.py")
    restored = driver.replace(
        "reports/acceptance-v2-r3-20261025", "reports/acceptance-v2-r2-20261025"
    ).replace("reviewed_r3_budget", "reviewed_r2_budget")
    restored = restored.replace(
        'FUNDING = ROOT / "reports/acceptance-v2-r2-20261025/funding-transition.json"',
        'FUNDING = OUT / "funding-transition.json"',
    )
    restored = restored.replace("mvp_v2_repair_round_3", "mvp_v2_repair_round_2")
    restored = restored.replace("mvp-v2-repair-r3-strict.lock", "mvp-v2-repair-r2-strict.lock")
    check(
        "driver_only_versioned_paths_purpose_lock",
        tree(restored) == tree(source("run_mvp_v2.py", OLD)),
    )
    auditor = (
        source("audit_mvp_v2.py")
        .replace("reports/acceptance-v2-r3-20261025", "reports/acceptance-v2-r2-20261025")
        .replace("independent_v2_r3_mvp", "independent_v2_r2_mvp")
    )
    check(
        "full_source_and_acceptance_audit_gates_unchanged",
        tree(auditor) == tree(source("audit_mvp_v2.py", OLD)),
    )
    for name in ("ledger_state_r2.py", "test_ledger_state_r2.py", "full_regression_driver.py"):
        check(name + "_byte_identical", (HERE / name).read_bytes() == (OLD / name).read_bytes())
    assignments = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in ast.parse(source("audit_reasoning_wire.py")).body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in {"EXPECTED_THINKING", "ROLES", "EXPECTED_CAP_FIELD"}
    }
    check(
        "thinking_role_contract",
        assignments["EXPECTED_THINKING"] == {"diagnose": True, "patcher": False},
    )
    check(
        "cap_contract",
        assignments["ROLES"]
        == {
            "diagnose": ("nvidia/Nemotron-3-Ultra-550b-a55b", 16384),
            "patcher": ("nvidia/nemotron-3-super-120b-a12b", 4000),
        },
    )
    check("exact_cap_field", assignments["EXPECTED_CAP_FIELD"] == "max_completion_tokens")
    check("profile_retained", 'PROFILE = ".cache/tokenfactory-runtime-v2-r2.json"' in driver)
    check("lifetime_pool_retained", 'POOL = Decimal("14.17775754")' in driver)
    check("daily_pool_retained", 'DAILY_POOL = Decimal("9.99964904")' in driver)
    check(
        "funding_receipt_retained",
        'FUNDING = ROOT / "reports/acceptance-v2-r2-20261025/funding-transition.json"' in driver,
    )
    for name in (
        "cap-review.json",
        "root-review.json",
        "preflight.json",
        "execution.json",
        "execution.log",
    ):
        check(name + "_not_created", not (HERE / name).exists())
    for path in HERE.glob("*.py"):
        compile(path.read_text(), str(path), "exec")
    print(
        json.dumps(
            {
                "schema": "headroom.r3_tools_offline_selfcheck.v1",
                "checks": checks,
                "passed": len(checks),
                "new_model_calls": 0,
                "new_gpu_runs": 0,
                "live_ledger_read": False,
                "cap_prepared": False,
                "dispatcher_invoked": False,
                "source_pins": [
                    {
                        "path": str(p.relative_to(ROOT)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in sorted(HERE.glob("*.py"))
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
