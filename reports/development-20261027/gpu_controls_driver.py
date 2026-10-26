"""Three paired human controls for scope feature validation, never agent scores."""

import difflib
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
    os.environ.pop(key, None)
from headroom.lab.runner import run_script
from headroom.verify.runner import verify_script

OUT = ROOT / "runs/repair-scope-controls-20261027"
OUT.mkdir(exist_ok=False)
BASE = OUT / "original"
CAND = OUT / "candidate"
BASE.mkdir()
CAND.mkdir()
source = (ROOT / "scenarios/s3_eval_no_grad_missing/train.py").read_text()
fixed = source.replace("def evaluate(", "@torch.no_grad()\ndef evaluate(")
assert fixed != source
(BASE / "train.py").write_text(source)
(CAND / "train.py").write_text(fixed)
patch = "".join(
    difflib.unified_diff(
        source.splitlines(True), fixed.splitlines(True), fromfile="a/train.py", tofile="b/train.py"
    )
)
policy = {
    "allow_numerics_change": False,
    "allow_model_change": False,
    "allow_batch_grad_accum": True,
    "max_throughput_regression_pct": 25,
}
receipt = {
    "provenance": "human_control",
    "purpose": "small GPU scope feature validation, not agent or MVP acceptance",
    "model_calls": 0,
    "started_at": datetime.now(UTC).isoformat(),
    "jobs": [],
}


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


save(OUT / "receipt.json", receipt)
for batch in (2, 16, 64):
    job = OUT / ("eval-batch-" + str(batch))
    job.mkdir()
    args = ["--tiny", "--device", "cuda", "--steps", "20", "--batch", str(batch), "--seed", "7"]
    baseline = run_script(
        BASE / "train.py",
        script_args=args,
        run_root=job / "lab",
        device="cuda",
        seed=1337,
        max_steps=20,
        max_seconds=60,
    )
    if baseline.get("status") != "completed":
        raise RuntimeError("Baseline did not complete; no automatic retries")
    verification = verify_script(
        baseline,
        CAND / "train.py",
        baseline_script=BASE / "train.py",
        script_args=args,
        baseline_args=args,
        run_root=job / "lab",
        device="cuda",
        seed=1337,
        required_steps=20,
        max_seconds=60,
        target="reclaim",
        reclaim_reduction_pct=20,
        policy=policy,
    )
    candidate = verification["candidate"]
    config = job / "configurations/round-01"
    config.mkdir(parents=True)
    (config / "patch.diff").write_text(patch)
    save(
        config / "manifest.json",
        {
            "round": 1,
            "provenance": "human_control",
            "policy": policy,
            "numerics_impact": "none",
            "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        },
    )
    save(config / "cli.json", {"original": args, "effective": args})
    request = {
        "target": "reclaim",
        "reclaim_reduction_pct": 20,
        "max_steps": 20,
        "seed": 1337,
        "device": "cuda",
        "policy": policy,
        "max_seconds": 60,
    }
    save(
        job / "report.json",
        {
            "scope": "human_control",
            "run": {"provenance": "human_control", "request": request},
            "rounds": [{"number": 1, "verification": verification["report"].model_dump()}],
        },
    )
    row = {
        "job": job.name,
        "batch": batch,
        "baseline_run": baseline["run_id"],
        "candidate_run": candidate["run_id"],
        "comparison": verification["report"].model_dump(),
        "pairing": verification["pairing_evidence"],
    }
    receipt["jobs"].append(row)
    save(OUT / "receipt.json", receipt)
    print(
        json.dumps(
            {
                "job": job.name,
                "status": candidate["status"],
                "target_met": row["comparison"]["target_met"],
                "reduction_pct": row["comparison"]["reduction_pct"],
            }
        ),
        flush=True,
    )
receipt["completed_at"] = datetime.now(UTC).isoformat()
save(OUT / "receipt.json", receipt)
print("controls complete", flush=True)
