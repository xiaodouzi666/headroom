#!/usr/bin/env python3
"""Build only from reviewed files and a hash-locked dependency export; never send the repo."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from headroom.lab.runtime_image import IMAGE, lock_digest

ALLOWED_INDEX_LINES = {
    "--index-url https://pypi.org/simple",
    "--extra-index-url https://download.pytorch.org/whl/cu124",
}
CONTEXT_FILES = {
    "Dockerfile",
    "requirements.txt",
    "verify_runtime.py",
    "lock.sha256",
    ".dockerignore",
    "context.json",
}


def validate_requirements(text):
    """Only immutable package versions/hashes and the two reviewed public indexes."""
    if not isinstance(text, str) or len(text.encode()) > 4 * 1024 * 1024:
        raise ValueError("Dependency export must fit 4 MiB")
    packages = 0
    for logical in text.replace("\\\n", " ").splitlines():
        line = logical.strip()
        if not line or line.startswith("#") or line in ALLOWED_INDEX_LINES:
            continue
        if (
            not re.fullmatch(
                r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+(?:\s*;[^\\\n]+?)?(?:\s+--hash=sha256:[a-f0-9]{64})+",
                line,
            )
            or "--" in line.split("--hash=", 1)[0]
            or any(
                value in line
                for value in (
                    "@",
                    "http:",
                    "https:",
                    "file:",
                    "--trusted-host",
                    "--index",
                    " -r ",
                    " -e ",
                )
            )
        ):
            raise ValueError("Dependency export contains an unreviewed source or unpinned package")
        packages += 1
    if not packages:
        raise ValueError("Dependency export is empty")
    return packages


def _read_public_file(path, limit):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("Build inputs must be bounded regular files")
    return path.read_bytes()


def prepare_context(root, *, uv="uv", run=subprocess.run):
    root = Path(root).resolve()
    digest = lock_digest(root)
    # The export uses only the checked-in lock. Host credentials, pip/uv indexes,
    # authentication helpers and configuration are not inherited.
    cache = root / ".cache"
    (cache / "tmp").mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "UV_CACHE_DIR": str(cache / "uv"),
        "UV_PYTHON_INSTALL_DIR": str(root / ".tools/python"),
        "UV_PYTHON_DOWNLOADS": "never",
        "TMPDIR": str(cache / "tmp"),
    }
    result = run(
        [
            uv,
            "export",
            "--project",
            str(root),
            "--frozen",
            "--offline",
            "--no-dev",
            "--no-emit-project",
            "--no-annotate",
            "--no-header",
            "--emit-index-url",
            "--format",
            "requirements.txt",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "Locked offline dependency export failed; run uv sync with the checked-in lock first"
        )
    requirements = result.stdout
    count = validate_requirements(requirements)
    if lock_digest(root) != digest:
        raise RuntimeError("uv.lock changed during dependency export")
    folder = cache / "lab-build" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    folder.mkdir(parents=True, mode=0o700)
    for name in ("Dockerfile", "verify_runtime.py"):
        (folder / name).write_bytes(_read_public_file(root / "lab-image" / name, 64 * 1024))
    (folder / "requirements.txt").write_text(requirements)
    (folder / "lock.sha256").write_text(digest + "\n")
    (folder / ".dockerignore").write_text(
        "*\n!Dockerfile\n!requirements.txt\n!verify_runtime.py\n!lock.sha256\n"
    )
    manifest = {
        "image": IMAGE,
        "uv_lock_sha256": digest,
        "locked_package_lines": count,
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()},
        "source_context": "explicit allowlist; no project source, .env, runs, caches or host venv",
    }
    (folder / "context.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if {p.name for p in folder.iterdir()} != CONTEXT_FILES:
        raise RuntimeError("Unexpected build context entry")
    return folder, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Export and retain reviewed build inputs; do not build",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if not uv:
        parser.error("uv is required for a frozen offline dependency export")
    folder, manifest = prepare_context(root, uv=uv)
    print(json.dumps({"context": str(folder), **manifest}, indent=2), flush=True)
    if args.prepare_only:
        return 0
    docker = shutil.which("docker")
    if not docker:
        parser.error("Docker is required to build the Lab image")
    # Only this small retained allowlist directory is sent to Docker.
    result = subprocess.run(
        [
            docker,
            "build",
            "--tag",
            IMAGE,
            "--build-arg",
            "HEADROOM_LOCK_SHA256=" + manifest["uv_lock_sha256"],
            str(folder),
        ],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
