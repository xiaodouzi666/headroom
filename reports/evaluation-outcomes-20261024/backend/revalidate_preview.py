"""Read-only revalidation of the retained offline outcomes after the identity fix."""

import builtins
import hashlib
import io
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
blocked = []


def denied(*args, **kwargs):
    blocked.append("network")
    raise RuntimeError("External network forbidden")


socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied


def guard(original):
    def checked(path, *args, **kwargs):
        if (
            isinstance(path, (str, bytes, os.PathLike))
            and Path(os.fsdecode(path)).absolute() == ROOT / ".env"
        ):
            blocked.append("real_env")
            raise RuntimeError("Real .env forbidden")
        return original(path, *args, **kwargs)

    return checked


builtins.open = guard(builtins.open)
io.open = guard(io.open)
os.open = guard(os.open)
from headroom.evaluation import evaluation_outcomes

metadata = json.loads(Path(__file__).with_name("retained-preview.json").read_text())
campaign = Path(metadata["campaign"])
document = json.loads(campaign.read_text())
before = {
    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in campaign.parent.rglob("*")
    if path.is_file() and not path.is_symlink()
}
verified = []
for row in document["rows"]:
    report = json.loads((Path(row["run_dir"]) / "report.json").read_text())
    current = evaluation_outcomes(
        {"report": report, "run_dir": row["run_dir"], "kept": report["run"]["kept"]}
    )
    original = {key: row[key] for key in current}
    if current != original:
        raise AssertionError("Retained offline facts changed: " + row["scenario_id"])
    verified.append(row["scenario_id"])
after = {
    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in campaign.parent.rglob("*")
    if path.is_file() and not path.is_symlink()
}
receipt = {
    "provenance": "offline_fixture",
    "campaign": str(campaign),
    "rows_unchanged": verified,
    "artifact_hashes_unchanged": before == after,
    "files_checked": len(before),
    "blocked_external_attempts": blocked,
    "actual_api_calls": 0,
    "gpu_tasks": 0,
}
Path(__file__).with_name("preview-revalidation.json").write_text(
    json.dumps(receipt, indent=2) + "\n"
)
print(json.dumps(receipt, indent=2))
raise SystemExit(0 if before == after and len(verified) == 4 else 1)
