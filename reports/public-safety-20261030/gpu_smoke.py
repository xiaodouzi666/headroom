"""One authorized minimal GPU Lab smoke. No model/Tavily/provider calls."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from headroom.lab.runner import gpu_state, run_script
from headroom.lab.snapshot_codec import read_snapshot_artifact

root = Path.cwd()
cache = root / ".cache/public-safety-20261030/gpu-smoke"
cache.mkdir(parents=True, exist_ok=True)
report = root / "reports/public-safety-20261030/gpu-smoke.json"
before = gpu_state()
receipt = {
    "started_at": datetime.now(UTC).isoformat(),
    "model_calls": 0,
    "model_cost_usd": "0",
    "tavily_calls": 0,
    "scope": "2-step CUDA Lab artifact smoke only; not automatic repair or acceptance improvement",
    "preflight_available": before.get("available"),
    "preflight_compute_process_count": len(before.get("processes", [])),
}
if not before.get("available") or before.get("processes"):
    receipt.update(status="skipped_gpu_unavailable_or_busy", executed=False)
    report.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    raise SystemExit(0)
source = cache / "source"
source.mkdir(exist_ok=True)
script = source / "smoke.py"
script.write_text(
    "import torch\nmodel = torch.nn.Linear(16, 16).cuda()\noptimizer = torch.optim.SGD(model.parameters(), lr=0.01)\nfor step in range(2):\n    x = torch.randn(8, 16, device='cuda')\n    loss = model(x).square().mean()\n    loss.backward()\n    optimizer.step()\n    optimizer.zero_grad()\n"
)
result = run_script(script, device="cuda", max_steps=2, max_seconds=30, run_root=cache / "runs")
artifact = Path(result["artifact_dir"])
snapshot = read_snapshot_artifact(artifact / "snapshot.json")
files = {}
for name in ("result.json", "snapshot.json", "snapshot.pickle", "memory_stats.json"):
    p = artifact / name
    files[name] = {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
receipt.update(
    executed=True,
    run_id=result["run_id"],
    run_dir=result["run_dir"],
    status=result["status"],
    steps=result.get("steps"),
    capture_complete=result.get("capture_complete"),
    peak_alloc_gb=result.get("peak_alloc_gb"),
    cleanup_verified=result["cleanup_verified"],
    artifact_export=result["execution"].get("artifact_export"),
    artifact_cleanup=result["execution"].get("artifact_cleanup"),
    storage_admission=result.get("storage_admission"),
    snapshot_segment_count=len(snapshot.get("segments", [])),
    snapshot_device_trace_groups=len(snapshot.get("device_traces", [])),
    files=files,
    finished_at=datetime.now(UTC).isoformat(),
)
receipt["passed"] = bool(
    result["status"] == "completed"
    and result.get("steps") == 2
    and result.get("capture_complete")
    and result["cleanup_verified"]
    and result["execution"].get("artifact_export", {}).get("export_verified")
    and isinstance(snapshot, dict)
    and snapshot.get("device_traces")
)
report.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt), flush=True)
assert receipt["passed"]
