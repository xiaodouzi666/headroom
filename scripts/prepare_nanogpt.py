#!/usr/bin/env python3
"""Fetch the pinned nanoGPT source and prepare deterministic synthetic input data."""

import json
import subprocess
from pathlib import Path

import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / "repos/nanogpt.yaml").read_text())
    repo = root / spec["source_cache"]
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--no-checkout", "--filter=blob:none", spec["repository"], str(repo)],
            check=True,
        )
    origin = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if origin != spec["repository"]:
        raise RuntimeError("Existing cache origin differs from the pinned repository")
    dirty = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if dirty:
        raise RuntimeError("Existing source cache has changes; refusing to replace them")
    subprocess.run(["git", "-C", str(repo), "fetch", "origin", spec["ref"]], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "--detach", spec["ref"]], check=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    ).stdout.strip()
    if head != spec["ref"]:
        raise RuntimeError("Source pin mismatch")
    data = root / spec["dataset_cache"]
    data.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1337)
    for split in ("train", "val"):
        values = rng.integers(0, 50304, size=262144, dtype=np.uint16)
        path = data / f"{split}.bin"
        if path.exists():
            if path.read_bytes() != values.tobytes():
                raise RuntimeError(f"Existing {split} dataset differs; preserve it for review")
        else:
            values.tofile(path)
    result = {
        "ref": head,
        "source": str(repo),
        "data": str(data),
        "train_bytes": (data / "train.bin").stat().st_size,
        "val_bytes": (data / "val.bin").stat().st_size,
        "gpu_baseline_run": False,
    }
    (root / "reports/nanogpt-preparation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
