"""Bounded original-workload references using PyTorch 2.5.1 saved-tensor offload.

This is a numerical reference, never a candidate memory/performance measurement.
Only reviewed standalone pairing contracts are supported. Copies stay lossless;
no CPU arithmetic, batch rewrite, or mixed precision is introduced.
"""

from __future__ import annotations

import hashlib
import json
import weakref
from pathlib import Path

from headroom.verify.offload_disk import (
    MAX_DISK_BYTES,
    DiskTensor,
    DiskTensorStore,
    validate_disk_limit,
)
from headroom.verify.pairing import derive_pairing, source_contract
from headroom.verify.precision import observed_precision

PROTOCOL = "headroom.reference_saved_tensor_offload.v1"
STRATEGY = "original_saved_tensor_offload"
LEGACY_STRATEGY = "legacy_small_batch"
MAX_SAVED_BYTES = 16 * 1024**3


def validate_limit(value):
    if type(value) is not int or not 1 <= value <= MAX_SAVED_BYTES:
        raise ValueError("reference offload saved-tensor limit must be 1..16 GiB")
    return value


class OffloadLimitExceeded(RuntimeError):
    """A numerical reference exceeded its explicit saved-tensor CPU budget."""


class SavedTensorOffload:
    """Delegate lossless copies to the pinned torch API and bound live CPU copies."""

    def __init__(
        self, script, script_args, output, max_saved_bytes=MAX_SAVED_BYTES, max_disk_bytes=0
    ):
        import torch

        self.limit = validate_limit(max_saved_bytes)
        self.script = Path(script)
        self.output = Path(output)
        validate_disk_limit(max_disk_bytes)
        contract = source_contract(self.script)
        if not contract.get("supported"):
            raise ValueError("reference offload requires a reviewed standalone source contract")
        if str(torch.__version__).split("+")[0] != "2.5.1":
            raise ValueError(
                "reference offload currently supports the reviewed torch 2.5.1 runtime"
            )
        self.data = {
            "protocol": PROTOCOL,
            "mode": STRATEGY,
            "source_sha256": hashlib.sha256(self.script.read_bytes()).hexdigest(),
            "script_args": list(script_args),
            "torch": str(torch.__version__),
            "pin_memory": False,
            "max_saved_bytes": self.limit,
            "entered": False,
            "exited": False,
            "failure": None,
            "packed_tensors": 0,
            "unpacked_tensors": 0,
            "cuda_copies": 0,
            "live_saved_bytes": 0,
            "peak_saved_bytes": 0,
            "performance_comparable": False,
            "backend": "disk" if max_disk_bytes else "cpu",
            "max_disk_bytes": max_disk_bytes,
        }
        # These are the exact pack/unpack functions used by the official API.
        delegate = torch.autograd.graph.save_on_cpu(pin_memory=False)
        self._pack = delegate.pack_hook
        self._unpack = delegate.unpack_hook
        self.disk = (
            DiskTensorStore(self.output, max_disk_bytes, self.limit) if max_disk_bytes else None
        )
        self.context = torch.autograd.graph.saved_tensors_hooks(self.pack, self.unpack)

    def _release(self, size):
        self.data["live_saved_bytes"] -= size

    def pack(self, tensor):
        size = tensor.numel() * tensor.element_size() if tensor.is_cuda else 0
        if self.disk is not None and size:
            packed = self.disk.pack(tensor)
            self.data["packed_tensors"] += 1
            self.data["cuda_copies"] += 1
            return packed
        if self.data["live_saved_bytes"] + size > self.limit:
            self.data["failure"] = "saved_tensor_cpu_budget_exceeded"
            raise OffloadLimitExceeded(
                "Original-workload reference saved-tensor CPU budget exceeded"
            )
        packed = self._pack(tensor)
        self.data["packed_tensors"] += 1
        if size:
            self.data["cuda_copies"] += 1
            self.data["live_saved_bytes"] += size
            self.data["peak_saved_bytes"] = max(
                self.data["peak_saved_bytes"], self.data["live_saved_bytes"]
            )
            weakref.finalize(packed[1], self._release, size)
        return packed

    def unpack(self, packed):
        self.data["unpacked_tensors"] += 1
        if isinstance(packed, DiskTensor):
            return self.disk.unpack(packed)
        return self._unpack(packed)

    def __enter__(self):
        self.context.__enter__()
        self.data["entered"] = True
        return self

    def __exit__(self, *exc):
        try:
            return self.context.__exit__(*exc)
        finally:
            self.data["exited"] = True
            if self.disk is not None:
                self.disk.close()
                self.data["disk"] = self.disk.evidence()
                self.data["failure"] = self.disk.failure
            (self.output / "reference-offload.json").write_text(
                json.dumps(self.data, indent=2, allow_nan=False) + "\n"
            )


def bind_original_baseline(baseline, script, script_args):
    """Read preserved host argv and bind the exact source to the actual OOM capture."""
    from headroom.lab.runner import read_artifact_json, selected_capture_directory

    try:
        directory = Path(baseline["run_dir"])
        manifest = read_artifact_json(directory / "manifest.json")
        selected_capture_directory(directory, baseline, manifest)
        command = manifest["command"]
        if (
            not isinstance(command, list)
            or not all(isinstance(item, str) for item in command)
            or "headroom.lab.run_target" not in command
            or "--script" not in command
        ):
            raise ValueError("Baseline is not a preserved standalone Lab wrapper execution")
        recorded_args = command[command.index("--") + 1 :] if "--" in command else []
        source_hash = hashlib.sha256(Path(script).read_bytes()).hexdigest()
        contract = baseline.get("pairing_capture", {}).get("source_contract", {})
        valid = (
            baseline.get("protocol") == "headroom.lab.v1"
            and baseline.get("status") == "oom"
            and baseline.get("capture_complete") is True
            and baseline.get("cleanup_verified") is True
            and contract.get("supported") is True
            and source_hash == contract.get("source_sha256")
            and recorded_args == list(script_args)
        )
        return {
            "valid": valid,
            "baseline_run_id": baseline.get("run_id"),
            "source_sha256": source_hash,
            "original_args": recorded_args,
            "reason": "Preserved baseline source/argv match"
            if valid
            else "Preserved baseline source/argv or capture does not match",
        }
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"valid": False, "reason": "Baseline binding unavailable: " + str(error)}


def reference_proof(reference, candidate, required_steps=20, *, baseline=None):
    """Fail closed; an opt-in reference must include runtime/source/argv proof."""
    reference = reference or {}
    candidate = candidate or {}
    baseline = baseline or {}
    evidence = reference.get("reference_offload", {})
    capture = reference.get("pairing_capture", {})
    pairing = derive_pairing(reference, candidate, required_steps)
    env, other_env = reference.get("env", {}), candidate.get("env", {})
    original_capture = baseline.get("pairing_capture", {})
    binding = reference.get("original_baseline_binding", {})
    before_precision = observed_precision(baseline)
    reference_precision = observed_precision(reference)
    disk = evidence.get("disk", {})
    disk_enabled = evidence.get("backend") == "disk"
    checks = {
        "original_reference_precision": (
            before_precision in {"fp32", "bf16"} and reference_precision == before_precision
        ),
        "bounded_storage_cleanup": (
            (evidence.get("backend", "cpu") == "cpu" and evidence.get("max_disk_bytes", 0) == 0)
            or (
                disk_enabled
                and type(evidence.get("max_disk_bytes")) is int
                and 0 < evidence["max_disk_bytes"] <= MAX_DISK_BYTES
                and disk.get("max_disk_bytes") == evidence["max_disk_bytes"]
                and type(disk.get("peak_disk_bytes")) is int
                and 0 < disk["peak_disk_bytes"] <= evidence["max_disk_bytes"]
                and disk.get("live_disk_bytes") == 0
                and type(evidence.get("max_saved_bytes")) is int
                and type(disk.get("peak_staging_tensor_bytes")) is int
                and 0 < disk["peak_staging_tensor_bytes"] <= evidence["max_saved_bytes"] // 2
                and type(disk.get("disk_tensors_created")) is int
                and disk["disk_tensors_created"] > 0
                and type(disk.get("disk_tensors_unpacked")) is int
                and disk["disk_tensors_unpacked"] > 0
                and disk.get("cleanup_verified") is True
                and disk.get("failure") is None
                and reference.get("reference_spill_cleanup", {}).get("verified") is True
            )
        ),
        "original_baseline_bound": (
            binding.get("valid") is True
            and bool(baseline.get("run_id"))
            and binding.get("baseline_run_id") == baseline.get("run_id")
            and binding.get("source_sha256") == evidence.get("source_sha256")
            and binding.get("original_args") == evidence.get("script_args")
            and evidence.get("source_sha256")
            == original_capture.get("source_contract", {}).get("source_sha256")
            and bool(original_capture.get("tensors"))
            and original_capture.get("tensors") == capture.get("tensors")
            and bool(original_capture.get("initial_parameters"))
            and original_capture.get("initial_parameters") == capture.get("initial_parameters")
        ),
        "requested_execution_verified": evidence.get("request_verified") is True,
        "offload_executed": (
            evidence.get("protocol") == PROTOCOL
            and evidence.get("mode") == STRATEGY
            and evidence.get("entered") is True
            and evidence.get("exited") is True
            and evidence.get("failure") is None
            and evidence.get("pin_memory") is False
            and type(evidence.get("cuda_copies")) is int
            and evidence["cuda_copies"] > 0
            and type(evidence.get("unpacked_tensors")) is int
            and evidence["unpacked_tensors"] > 0
            and type(evidence.get("peak_saved_bytes")) is int
            and type(evidence.get("max_saved_bytes")) is int
            and 0 <= evidence["peak_saved_bytes"] <= evidence["max_saved_bytes"] <= MAX_SAVED_BYTES
            and (disk_enabled or evidence["peak_saved_bytes"] > 0)
            and evidence.get("performance_comparable") is False
        ),
        "source_matches_capture": bool(
            evidence.get("source_sha256")
            and evidence.get("source_sha256")
            == capture.get("source_contract", {}).get("source_sha256")
        ),
        "same_runtime": bool(
            env.get("device") == other_env.get("device") == "cuda"
            and env.get("torch") == other_env.get("torch") == evidence.get("torch")
            and str(env.get("torch")).split("+")[0] == "2.5.1"
            and env.get("cuda") == other_env.get("cuda")
            and env.get("cuda")
            and env.get("gpu_name") == other_env.get("gpu_name")
            and env.get("gpu_name")
            and env.get("PYTORCH_CUDA_ALLOC_CONF") == other_env.get("PYTORCH_CUDA_ALLOC_CONF")
            and reference.get("image_id") == candidate.get("image_id")
            and reference.get("image_id")
        ),
        "complete_reference": (
            reference.get("protocol") == "headroom.lab.v1"
            and reference.get("capture_complete") is True
            and reference.get("cleanup_verified") is True
            and reference.get("status") == "completed"
            and reference.get("steps") == required_steps
            and reference.get("shared_gpu") is False
            and reference.get("gpu_observation_complete") is True
        ),
        **pairing["checks"],
    }
    return {"valid": all(value is True for value in checks.values()), "checks": checks}
