"""Read-only contract for the Lab image's own Python and locked dependencies."""

import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path

IMAGE = "headroom-lab:py312-cu124-runtime-v1"
CONTRACT = "python312-self-contained-v1"
CONTRACT_LABEL = "org.headroom.lab-runtime"
LOCK_LABEL = "org.headroom.uv-lock-sha256"


def lock_digest(project_root: Path) -> str:
    path = Path(project_root) / "uv.lock"
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
        raise ValueError("Lab uv.lock must be a bounded regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_runtime_image(document: dict, expected_lock: str) -> dict:
    labels = document.get("labels") if isinstance(document, dict) else None
    if not isinstance(labels, dict) or labels.get(CONTRACT_LABEL) != CONTRACT:
        raise RuntimeError(
            "Lab runtime image is missing or incompatible; run bash scripts/build_lab_image.sh"
        )
    if labels.get(LOCK_LABEL) != expected_lock:
        raise RuntimeError(
            "Lab image dependencies differ from uv.lock; rebuild with bash scripts/build_lab_image.sh"
        )
    image_id = document.get("id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise RuntimeError("Lab image identity could not be verified")
    return {
        "image": IMAGE,
        "image_id": image_id,
        "runtime_contract": CONTRACT,
        "uv_lock_sha256": expected_lock,
    }


def require_runtime_image(project_root, *, executable, environment):
    """Inspect local Docker metadata only: no pull, container, GPU, key or network."""
    expected = lock_digest(Path(project_root))
    try:
        result = subprocess.run(
            [
                executable,
                "image",
                "inspect",
                IMAGE,
                "--format",
                '{"id":{{json .Id}},"labels":{{json .Config.Labels}}}',
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError("missing image")
        document = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise RuntimeError(
            "Lab runtime image is unavailable; run bash scripts/build_lab_image.sh"
        ) from None
    return validate_runtime_image(document, expected)
