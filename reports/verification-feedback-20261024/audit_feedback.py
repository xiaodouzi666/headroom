"""Reproduce feedback with the real SDK mock; no model or GPU calls."""

import json
import sys
from pathlib import Path
from tempfile import mkdtemp

import offline_tests  # installs independent DNS/socket and real .env guards before app imports

ROOT = Path(offline_tests.ROOT)
sys.path.insert(0, str(ROOT / "tests"))

from test_orchestrator import search_run

REPORT = ROOT / "reports/verification-feedback-20261024"
RAW = ROOT / "runs/verification-feedback-cpu-20261024"
RAW.mkdir(exist_ok=True)
workspace = Path(mkdtemp(prefix="feedback-", dir=RAW))
plans = [
    {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25, "ms": 110},
    {
        "before": "VALUE = 2\n",
        "after": "VALUE = 3\n",
        "peak": 20,
        "ms": 115,
        "loss": "changed",
        "checks": {"numerical_acceptance": False, "loss_tolerance": False, "same_inputs": None},
        "verification_extra": {
            "max_loss_delta": 0.125,
            "loss_tolerance": 0.001,
            "peak_before": 30.0,
            "peak_after": 20.0,
            "numerical_basis": "original_plan_full_backward_scalar_series",
            "snapshot": "EXCLUDED_SYNTHETIC_SNAPSHOT",
        },
    },
    {"before": "VALUE = 2\n", "after": "VALUE = 4\n", "peak": 19, "ms": 120, "target": True},
]
result, store, calls, verifies, _ = search_run(workspace, plans)
try:
    request = json.loads(calls[4]["messages"][-1]["content"])
    feedback = request["verification_feedback"]
    rejected = feedback[1]
    assert rejected["verification"]["max_loss_delta"] == 0.125
    assert rejected["candidate"]["peak_allocated_bytes"] == 20_000_000_000
    assert rejected["selected_after_round"]["peak_allocated_bytes"] == 25_000_000_000
    assert not rejected["candidate_selected"]
    assert "EXCLUDED_SYNTHETIC_SNAPSHOT" not in json.dumps(request)
    receipt = {
        "provenance": "offline_fixture",
        "validation": "SDK MockTransport, synthetic Lab observations, real isolated patch application; not live API/GPU acceptance",
        "run_dir": result["run_dir"],
        "decision_sequence": [row["decision"] for row in store.rounds(result["run_id"])],
        "model_request_count": len(calls),
        "verification_count": len(verifies),
        "round_3_feedback_bytes": len(json.dumps(feedback, ensure_ascii=False).encode()),
        "round_3_feedback": feedback,
        "fixture_target_met": result["target_met"],
    }
    (REPORT / "request-round-3.json").write_text(json.dumps(calls[4], indent=2) + "\n")
    (REPORT / "audit-feedback.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: receipt[key]
                for key in (
                    "provenance",
                    "run_dir",
                    "decision_sequence",
                    "model_request_count",
                    "verification_count",
                    "round_3_feedback_bytes",
                )
            },
            indent=2,
        )
    )
finally:
    store.close()
