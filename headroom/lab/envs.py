"""Explicit environment construction for secret-free Lab execution."""

import re

HOST_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"}


def validate_options(device: str, max_steps: int, max_seconds: float, seed: int) -> None:
    if device not in {"cpu", "cuda"}:
        raise ValueError("device must be cpu or cuda")
    if not 1 <= max_steps <= 10000:
        raise ValueError("max_steps must be between 1 and 10000")
    if not 0 < max_seconds <= 3600:
        raise ValueError("max_seconds must be in (0, 3600]")
    if not 0 <= seed < 2**32:
        raise ValueError("seed must fit an unsigned 32-bit integer")


def validate_allocator(value: str | None) -> str | None:
    if value is None:
        return None
    if not value or len(value) > 512:
        raise ValueError("allocator configuration is empty or too long")
    allowed = {
        "backend",
        "expandable_segments",
        "max_split_size_mb",
        "max_non_split_rounding_mb",
        "garbage_collection_threshold",
        "roundup_power2_divisions",
    }
    seen = set()
    for entry in value.split(","):
        key, separator, argument = entry.partition(":")
        if not separator or key not in allowed or key in seen:
            raise ValueError("unsupported or duplicate allocator option")
        seen.add(key)
        if key == "backend":
            valid = argument in {"native", "cudaMallocAsync"}
        elif key == "expandable_segments":
            valid = argument in {"True", "False"}
        elif key == "garbage_collection_threshold":
            valid = bool(re.fullmatch(r"0\.\d+", argument)) and 0 < float(argument) < 1
        else:
            valid = bool(re.fullmatch(r"[1-9]\d{0,5}", argument))
        if not valid:
            raise ValueError(f"invalid allocator option: {key}")
    return value


def container_environment(
    *,
    device: str,
    max_steps: int,
    max_seconds: float,
    seed: int,
    allocator_conf: str | None = None,
    command_mode: bool = False,
) -> dict:
    validate_options(device, max_steps, max_seconds, seed)
    allocator_conf = validate_allocator(allocator_conf)
    result = {
        "PATH": "/opt/venv/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "HF_HOME": "/tmp/headroom-hf",
        "HF_HUB_CACHE": "/tmp/headroom-hf/hub",
        "HF_DATASETS_CACHE": "/tmp/headroom-hf/datasets",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "TMPDIR": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": str(seed),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "/runtime/headroom/lab:/runtime" if command_mode else "/runtime",
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        "CUDA_VISIBLE_DEVICES": "0" if device == "cuda" else "",
        "HEADROOM_CONTROL_DIR": "/control",
    }
    if allocator_conf:
        result["PYTORCH_CUDA_ALLOC_CONF"] = allocator_conf
    if command_mode:
        result.update(
            {
                "HEADROOM_CAPTURE": "1",
                "HEADROOM_OUTPUT_DIR": "/out",
                "HEADROOM_MAX_STEPS": str(max_steps),
                "HEADROOM_MAX_SECONDS": str(max_seconds),
                "HEADROOM_SEED": str(seed),
                "HEADROOM_DEVICE": device,
            }
        )
    return result
