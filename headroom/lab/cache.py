"""Optional project-owned, manifest-checked offline HF data mount; never user cache."""

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

NAMES = {
    "config.json",
    "generation_config.json",
    "model.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "vocab.txt",
    "merges.txt",
    "spiece.model",
    "tokenizer.model",
}


def validated_hf_cache(project_root: Path) -> Path | None:
    """Require an explicit SHA256 manifest and data-only regular leaves.

    This validates integrity against an operator-reviewed manifest, not the origin
    or semantic safety of weights. Pickles, code, symlinks, tokens and Hub account
    caches are unsupported. No files are downloaded, created or modified here.
    """
    base = project_root / ".cache" / "huggingface"
    if not base.exists() and not base.is_symlink():
        return None
    if (project_root / ".cache").is_symlink() or base.is_symlink() or not base.is_dir():
        raise ValueError("HF cache must be a project-owned regular directory")
    manifest = base / "manifest.json"
    descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise ValueError("HF cache manifest must be a bounded regular file")
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("HF cache manifest schema must be version 1")
    entries = data.get("files")
    if not isinstance(entries, dict) or len(entries) > 10000:
        raise ValueError("HF cache manifest files must be a bounded mapping")
    for name, digest in entries.items():
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) for part in path.parts)
            or (
                path.name not in NAMES
                and not re.fullmatch(r"model-\d+-of-\d+[.]safetensors", path.name)
            )
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("HF cache manifest contains an unsupported data entry")
    seen, total = set(), 0
    for directory, dirs, files in os.walk(base, followlinks=False):
        if any((Path(directory) / name).is_symlink() for name in dirs):
            raise ValueError("HF cache directory links are forbidden")
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(base).as_posix()
            if relative == "manifest.json":
                continue
            if relative not in entries:
                raise ValueError("HF cache contains an unlisted file; refusing mount")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as handle:
                info = os.fstat(handle.fileno())
                total += info.st_size
                if not stat.S_ISREG(info.st_mode) or total > 8 * 1024**3:
                    raise ValueError("HF cache must contain regular files within 8 GiB")
                digest = hashlib.sha256()
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != entries[relative]:
                raise ValueError("HF cache hash mismatch; refusing mount")
            seen.add(relative)
    if seen != set(entries):
        raise ValueError("HF cache manifest references missing data")
    return base
