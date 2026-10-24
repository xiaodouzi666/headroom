"""Prepare a reviewable candidate tree without changing the real Git index."""

import hashlib
import json
import os
import subprocess
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEW_SOURCES = (
    "docs/LAB_RUNTIME.md",
    "headroom/lab/runtime_image.py",
    "headroom/lab/deadline.py",
    "lab-image/verify_runtime.py",
    "scripts/build_lab_image.py",
    "tests/test_lab_deadline.py",
    "tests/test_runtime_image.py",
    "tests/test_phase0_runtime_image.py",
)


def main():
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = ROOT / ".cache/portable-checkout" / stamp
    destination.mkdir(parents=True)
    index = ROOT / ".git/index"
    before = hashlib.sha256(index.read_bytes()).hexdigest()
    environment = dict(os.environ, GIT_INDEX_FILE=str(destination / "candidate.index"))

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, env=environment, text=True).strip()

    git("read-tree", "HEAD")
    git("add", "-u")
    git("add", "--", *NEW_SOURCES)
    tree = git("write-tree")
    paths = git("ls-tree", "-r", "--name-only", tree).splitlines()
    assert not any(
        part in {".env", ".venv", ".cache", ".tools"} for name in paths for part in Path(name).parts
    )
    archive = destination / "candidate.tar"
    git("archive", "--format=tar", "--output=" + str(archive), tree)
    checkout = destination / "checkout"
    checkout.mkdir()
    with tarfile.open(archive) as package:
        package.extractall(checkout, filter="data")
    after = hashlib.sha256(index.read_bytes()).hexdigest()
    assert after == before
    record = {
        "kind": "candidate_tracked_tree_not_committed",
        "base_commit": git("rev-parse", "HEAD"),
        "candidate_tree": tree,
        "checkout": str(checkout),
        "file_count": len(paths),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "real_index_unchanged": before == after,
        "checkout_has_venv": (checkout / ".venv").exists(),
        "checkout_has_env": (checkout / ".env").exists(),
        "added_source_files": NEW_SOURCES,
    }
    (destination / "candidate.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
