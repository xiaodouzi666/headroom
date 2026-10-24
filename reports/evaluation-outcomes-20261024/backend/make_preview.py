"""Persist actual run_fix output using SDK MockTransport and synthetic Lab observations."""

import builtins
import io
import json
import os
import socket
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
denied_attempts = []


def denied(*args, **kwargs):
    denied_attempts.append("network")
    raise RuntimeError("External DNS/INET is forbidden for retained offline preview")


socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied


def guard(original):
    def checked(path, *args, **kwargs):
        if (
            isinstance(path, (str, bytes, os.PathLike))
            and Path(os.fsdecode(path)).absolute() == ROOT / ".env"
        ):
            denied_attempts.append("real_env")
            raise RuntimeError("Real .env is forbidden")
        return original(path, *args, **kwargs)

    return checked


builtins.open = guard(builtins.open)
io.open = guard(io.open)
os.open = guard(os.open)

from test_orchestrator import search_run

from headroom.api.evaluations import _public_row
from headroom.evaluation import Scenario, campaign_tables, render_campaign, result_row

output = ROOT / "runs/validation/evaluation-outcomes-20261024" / uuid4().hex
output.mkdir(parents=True, exist_ok=False)
rows = []
for mode in ("keep_revert", "all_revert", "budget_after_keep", "error_after_keep"):
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
    work = output / mode
    work.mkdir()
    result, store, requests, _, _ = search_run(work, plans, **options)
    try:
        case = Scenario(
            id=mode,
            group="synthetic",
            script="train.py",
            source_root=".",
            target="fit:22GB",
            expected_baseline="completed",
            ground_truth="activations",
        )
        row = result_row(
            case, "full_ultra", result, store.usage(result["run_id"]), provenance="offline_fixture"
        )
        row["policy_name"] = "default"
        row["policy"] = result["report"]["run"]["request"]["policy"]
        rows.append(row)
    finally:
        store.close()
document = campaign_tables(
    {
        "mode": "campaign",
        "provenance": "offline_fixture",
        "status": "finished",
        "search_mode": "until_target",
        "rows": rows,
    }
)
(output / "campaign.json").write_text(json.dumps(document, indent=2) + "\n")
(output / "campaign.md").write_text(render_campaign(document))
public = campaign_tables(
    {**document, "rows": [_public_row(row, "offline_fixture") for row in rows]}
)
(output / "public-campaign.json").write_text(json.dumps(public, indent=2) + "\n")
receipt = {
    "provenance": "offline_fixture",
    "description": "Actual orchestrator/SDK/patch files with synthetic Lab observations; not GPU or model acceptance",
    "campaign": str(output / "campaign.json"),
    "public_campaign": str(output / "public-campaign.json"),
    "denied_attempts": denied_attempts,
    "actual_api_calls": 0,
    "gpu_tasks": 0,
    "rows": [
        {
            key: row.get(key)
            for key in (
                "scenario_id",
                "run_id",
                "run_dir",
                "patch_applied",
                "patch_applied_rounds",
                "selected_round",
                "selected_patch_applied",
                "selected_completed",
                "round_outcomes",
            )
        }
        for row in rows
    ],
}
Path(__file__).with_name("retained-preview.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps(
        {
            "campaign": receipt["campaign"],
            "public_campaign": receipt["public_campaign"],
            "provenance": "offline_fixture",
            "rows": len(rows),
            "denied_attempts": denied_attempts,
        },
        indent=2,
    )
)
