#!/usr/bin/env python3
"""Import existing, hash-checked baseline captures as explicitly labeled local replays."""

import hashlib
import json
import shutil
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from headroom.evidence import build_evidence
from headroom.lab.runner import PROJECT_ROOT
from headroom.report import generate_report
from headroom.store.db import Store


def main():
    root = PROJECT_ROOT
    accepted = json.loads((root / "reports/t1.2-acceptance.json").read_text())
    sources = []
    for key, artifacts in accepted["artifacts"].items():
        evidence = Path(artifacts["evidence_json"]["path"])
        if (
            hashlib.sha256(evidence.read_bytes()).hexdigest()
            != artifacts["evidence_json"]["sha256"]
        ):
            raise ValueError("Saved evidence hash differs")
        sources.append((key, evidence.parent.parent, evidence.parent))
    current = json.loads((root / "reports/lab-gpu-acceptance-20261024T021625Z.json").read_text())
    capture = Path(current["runs"]["s3_a"]["run_dir"])
    existing = capture / "evidence-replay"
    if not (existing / "evidence.json").exists():
        bundle = build_evidence(capture, output_dir=existing)
        existing = Path(bundle["evidence_json"]).parent
    sources.append(("s3", capture, existing))
    store = Store(root / "runs/headroom.db")
    imported = []
    try:
        for case, capture, evidence_root in sources:
            raw = json.loads((capture / "result.json").read_text())
            digest = hashlib.sha256((evidence_root / "evidence.json").read_bytes()).hexdigest()
            rid = uuid5(NAMESPACE_URL, "headroom-baseline:" + digest).hex
            if store.get_run(rid) is not None:
                imported.append({"run_id": rid, "case": case, "existing": True})
                continue
            output = root / "runs/jobs" / rid
            target = output / "evidence/before"
            target.mkdir(parents=True, exist_ok=False)
            for name in ("evidence.json", "evidence.md", "timeline.png"):
                shutil.copyfile(evidence_root / name, target / name)
            evidence = json.loads((target / "evidence.json").read_text())
            run = {
                "run_id": rid,
                "status": "completed",
                "provenance": "recorded_baseline",
                "target": case + " baseline replay",
                "target_met": False,
                "baseline": raw,
                "run_dir": str(output),
                "public_replay": True,
                "reason": "Recorded GPU baseline only; no model diagnosis, patch, or repair verification was performed.",
                "source_run_id": raw.get("run_id"),
                "source_evidence_sha256": digest,
                "import_note": "Replay import event is new; baseline measurements retain original source evidence.",
            }
            store.create_run(rid, data=run)
            generate_report(
                output,
                run,
                evidence={"before": evidence},
                rounds=[],
                usage=store.usage(rid),
                artifacts={"before_png": "evidence/before/timeline.png"},
            )
            store.add_event(
                rid,
                "report.written",
                {
                    "provenance": "recorded_baseline",
                    "action": "import_existing_capture",
                    "source_run_id": raw.get("run_id"),
                    "source_evidence_sha256": digest,
                    "repair_performed": False,
                },
            )
            imported.append({"run_id": rid, "case": case, "target_met": False})
        report = {
            "provenance": "recorded_baseline",
            "replays": imported,
            "T3.3_accepted": False,
            "missing": [
                "verified s2 two-round repair",
                "verified nanoGPT repair",
                "verified reclaim repair",
            ],
            "paid_model_calls": 0,
            "new_gpu_runs": 0,
        }
        (root / "reports/baseline-replays.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
