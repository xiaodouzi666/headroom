"""Read-only tensor fingerprints for explicitly labeled research controls.

Snapshots happen before the training loop and in its finally block. They are
not injected into user/model repairs and do not constitute model acceptance.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import torch


class TrainingControlCapture:
    def __init__(self, output="/out", max_bytes=32 * 1024**3, chunk_bytes=32 * 1024**2):
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 64 * 1024**2:
            raise ValueError("chunk_bytes must be within 64 MiB")
        self.output = Path(output)
        self.max_bytes, self.chunk_bytes = max_bytes, chunk_bytes
        self.bytes_hashed = 0

    def tensor(self, tensor):
        if tensor.layout != torch.strided or not tensor.is_contiguous():
            raise ValueError("Research fingerprint requires a contiguous dense tensor")
        size = tensor.numel() * tensor.element_size()
        self.bytes_hashed += size
        if self.bytes_hashed > self.max_bytes:
            raise ValueError("Research snapshot byte budget exceeded")
        flat = tensor.detach().view(-1)
        chunk = max(1, self.chunk_bytes // tensor.element_size())
        digest = hashlib.sha256()
        for start in range(0, flat.numel(), chunk):
            raw = flat[start : start + chunk].cpu().view(torch.uint8).numpy().tobytes()
            digest.update(raw)
        return {
            "sha256": digest.hexdigest(),
            "dtype": str(tensor.dtype),
            "shape": list(tensor.shape),
            "bytes": size,
        }

    def snapshot(self, name, model, optimizer, inputs=None):
        started = time.perf_counter()
        self.bytes_hashed = 0
        parameters = dict(model.named_parameters())
        names = {parameter: name for name, parameter in parameters.items()}
        state = {}
        for parameter_name, parameter in parameters.items():
            state[parameter_name] = {}
            for key, value in sorted(optimizer.state.get(parameter, {}).items()):
                if isinstance(value, torch.Tensor):
                    state[parameter_name][key] = self.tensor(value)
                elif type(value) in (int, float, bool) and math.isfinite(value):
                    state[parameter_name][key] = value
                else:
                    raise TypeError("Unsupported optimizer state in research snapshot")
        groups = []
        for group in optimizer.param_groups:
            groups.append(
                {
                    "parameters": [names[parameter] for parameter in group["params"]],
                    "settings": {
                        key: group[key]
                        for key in ("lr", "betas", "eps", "weight_decay", "amsgrad", "maximize")
                    },
                }
            )
        payload = {
            "protocol": "headroom.optimizer_research_fingerprints.v1",
            "kind": "human_authored_research_control",
            "counts_toward_model_acceptance": False,
            "parameters": {key: self.tensor(value) for key, value in parameters.items()},
            "optimizer_state": state,
            "parameter_groups": groups,
            "inputs": {key: self.tensor(value) for key, value in (inputs or {}).items()},
            "bytes_hashed": self.bytes_hashed,
            "hash_seconds": time.perf_counter() - started,
            "timing": "outside training loop; first Lab interval may include initial hashing",
        }
        (self.output / ("control-" + name + ".json")).write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n"
        )
        return payload
