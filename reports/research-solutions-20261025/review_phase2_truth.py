"""Independent read-only replay of original baselines; no model outputs or source edits."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/research-solutions-20261025"
CASES = [
    ("nanogpt", "runs/nanogpt-lab-validation/5e5566267e7b45a3a7e6f75fe738ed08", "/source/model.py"),
    (
        "hf_trainer",
        "runs/hf-full-baseline-20261024/77c5ef8e0948458688116ff68f38c586",
        "/transformers/models/gpt2/modeling_gpt2.py",
    ),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


rows = []
for name, relative, origin in CASES:
    base = ROOT / relative
    result = json.loads((base / "result.json").read_text())
    manifest = json.loads((base / "manifest.json").read_text())
    snapshot = json.loads((base / "artifacts/snapshot.json").read_text())
    live, live_bytes, maximum, at_peak = {}, 0, 0, []
    errors = []
    for event in snapshot["device_traces"][0]:
        action = event["action"]
        address = event.get("addr")
        if action == "alloc":
            if address in live:
                errors.append("duplicate live allocation")
            live[address] = event
            live_bytes += event["size"]
            if live_bytes > maximum:
                maximum = live_bytes
                at_peak = list(live.values())
        elif action == "free_completed":
            previous = live.pop(address, None)
            if previous is None:
                errors.append("unknown free")
            else:
                live_bytes -= previous["size"]
    forward = sum(
        event["size"]
        for event in at_peak
        if any(
            frame.get("filename", "").endswith(origin) and frame.get("name") == "forward"
            for frame in event.get("frames", [])
        )
    )
    optimizer = sum(
        event["size"]
        for event in at_peak
        if any("/torch/optim/" in frame.get("filename", "") for frame in event.get("frames", []))
    )
    sources = []
    for relative_source, record in manifest["source"]["files"].items():
        original = Path(manifest["source_root"]) / relative_source
        sources.append(
            {
                "path": str(original.relative_to(ROOT)),
                "sha256": digest(original),
                "matches_capture": digest(original) == record["sha256"],
            }
        )
    additional = []
    if name == "nanogpt":
        for filename in ("train.py", "model.py", "configurator.py"):
            current = ROOT / ".cache/upstream/nanoGPT" / filename
            additional.append(
                {
                    "path": str(current.relative_to(ROOT)),
                    "sha256": digest(current),
                    "matches_capture": digest(current)
                    == manifest["source"]["files"][filename]["sha256"],
                }
            )
        for filename in ("train.bin", "val.bin"):
            current = ROOT / ".cache/datasets/nanogpt/headroom_synthetic" / filename
            expected = manifest["source"]["files"]["data/headroom_synthetic/" + filename]["sha256"]
            additional.append(
                {
                    "path": str(current.relative_to(ROOT)),
                    "sha256": digest(current),
                    "matches_capture": digest(current) == expected,
                }
            )
    assert not errors and result["status"] == "oom" and result["steps"] == 0
    assert all(row["matches_capture"] for row in sources + additional)
    assert forward / maximum > 0.90 and optimizer == 0
    rows.append(
        {
            "scenario_id": name,
            "baseline": relative,
            "result_sha256": digest(base / "result.json"),
            "snapshot_sha256": digest(base / "artifacts/snapshot.json"),
            "native_allocated_peak_bytes": result["peak_allocated_bytes"],
            "replayed_requested_peak_bytes": maximum,
            "replay_errors": errors,
            "forward_origin_requested_bytes_at_peak": forward,
            "forward_origin_fraction": forward / maximum,
            "optimizer_origin_requested_bytes_at_peak": optimizer,
            "captured_sources": sources,
            "current_source_and_data_checks": additional,
            "prospective_first_cause_supported": "activations",
            "limitation": "Initial captured FP32 forward OOM only; forward origin does not identify every tensor as autograd-saved. Native allocated peak remains authoritative.",
        }
    )
review = {
    "schema": "headroom.root-baseline-truth-review.v1",
    "reviewed_utc": datetime.now(UTC).isoformat(),
    "reviewer": "root",
    "method": "Independent alloc/free_completed address replay; original baseline and source/data hashes only.",
    "rows": rows,
    "s5": "Keep unverified; no harmful fragmentation proof.",
    "production_or_manifest_changes": False,
    "historical_rescoring": False,
    "model_outputs_read_for_this_review": False,
    "new_provider_or_gpu_calls": 0,
    "label_application": "Prospective version only, with frozen matching source/data/configuration and new qualification.",
}
target = OUT / "phase2-truth-root-review-20261025.json"
target.write_text(json.dumps(review, indent=2) + "\n")
print(
    json.dumps(
        {
            "path": str(target.relative_to(ROOT)),
            "sha256": digest(target),
            "rows": [
                {
                    k: r[k]
                    for k in (
                        "scenario_id",
                        "replayed_requested_peak_bytes",
                        "forward_origin_fraction",
                        "optimizer_origin_requested_bytes_at_peak",
                    )
                }
                for r in rows
            ],
        }
    )
)
