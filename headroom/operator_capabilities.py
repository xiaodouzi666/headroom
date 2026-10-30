"""Small host-owned operator metadata; availability never proves target applicability."""

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from headroom.observation_feedback import bound_optimizer_observation

MAX_CATALOG_BYTES = 4096
MAX_OPERATOR_SOURCE_BYTES = 32768
_PACKAGE_ROOT = Path(__file__).parent
_SOURCE_SHA256 = "4990d71729b1db73e7eccddbddc6e55dbf872e23fb0a092ec4d7903067c7677b"


def _owned_source():
    """Read only the fixed owned module through non-following directory descriptors."""
    root = child = None
    try:
        root = os.open(_PACKAGE_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        child = os.open("optim", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        descriptor = os.open(
            "in_backward_adamw.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=child
        )
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_OPERATOR_SOURCE_BYTES:
                return None
            source = handle.read(MAX_OPERATOR_SOURCE_BYTES + 1)
        if len(source) > MAX_OPERATOR_SOURCE_BYTES:
            return None
        digest = hashlib.sha256(source).hexdigest()
        if digest != _SOURCE_SHA256:
            return None
        return {
            "module": "headroom.optim.in_backward_adamw",
            "sha256": digest,
            "bytes": len(source),
        }
    except (OSError, ValueError):
        return None
    finally:
        for descriptor in (child, root):
            if descriptor is not None:
                os.close(descriptor)


def runtime_operator_catalog(*, execution_context=None):
    """Describe optional real APIs without choosing a repair or granting a policy."""
    catalog = {
        "schema": "headroom.runtime_operator_catalog.v1",
        "provenance": "host_owned_reviewed_source_metadata",
        "current_target_applicability": "unverified",
        "current_runtime_availability": "unverified",
        "runtime_scope": {
            "standard_lab": "Headroom Docker Lab mounts the owned package read-only at /runtime/headroom",
            "external_runtime": (
                "Unknown. A user GPU, external snapshot or other runtime needs the corresponding "
                "Headroom package and this exact module SHA; this catalog does not establish installation."
            ),
        },
        "selection": (
            "Optional, not a default OOM repair. Consider only when the original optimizer is AdamW, "
            "measured optimizer/gradient lifetime supports sufficient savings, and every precondition "
            "is supported. Other direct lifetime/device repairs remain candidates. Preserve genuine "
            "unknowns, the objective, precision, policy and all verification gates."
        ),
        "operators": [],
    }
    source = _owned_source()
    if source is None:
        catalog["status"] = "unavailable_or_unverified"
        catalog["reason"] = "owned_source_could_not_be_verified"
    else:
        catalog["status"] = "owned_source_verified"
        catalog["operators"] = [
            {
                "id": "adamw_fp32_step_in_backward_v1",
                "source": source,
                "symbol": "AdamWInBackward",
                "python_import": "from headroom.optim.in_backward_adamw import AdamWInBackward",
                "api": {
                    "constructor": (
                        "AdamWInBackward(params, *args, **kwargs), mirroring the existing "
                        "torch.optim.AdamW groups and hyperparameters."
                    ),
                    "step": (
                        "Keep one ordinary backward followed by one outer step() per original update; "
                        "the outer step closes the logical update while leaf hooks update and release gradients."
                    ),
                    "state": "state_dict/load_state_dict only at completed logical-step boundaries; close() removes hooks.",
                },
                "requires": [
                    "Observed torch 2.5.1; dense unscaled FP32 leaf parameters with no duplicate/shared parameters.",
                    "The original optimizer is eager unfused single-tensor AdamW; foreach/fused/capturable/differentiable are False.",
                    "Preserve every original updated parameter, parameter group and lr/betas/eps/weight_decay/amsgrad/maximize setting.",
                    "Exactly one ordinary backward per original optimizer update; preserve data, RNG, objective and update cadence.",
                ],
                "incompatible": [
                    "Gradient accumulation or multiple backwards before step; gradient clipping or other global-gradient operations.",
                    "AMP/GradScaler/scaled gradients, closures, DDP/distributed reduction, compiled or higher-order execution.",
                ],
                "limits": (
                    "Not a conversion of SGD or another optimizer to AdamW. Runtime guards reject "
                    "some structural violations but cannot certify absent clipping/scaling/distributed semantics. "
                    "Availability is not target applicability, equivalence, savings or success; all real "
                    "candidate, numerical, parameter, memory and throughput checks still apply. This metadata is "
                    "not allocation evidence and never expands a selected numerical-reference source "
                    "contract; its preflight may reject the resulting candidate."
                ),
            }
        ]
    observation = bound_optimizer_observation(execution_context)
    if (
        observation is not None
        and observation.get("status") == "observed"
        and all(
            observation.get(field) is True
            for field in (
                "capture_complete",
                "reported_complete",
                "logical_boundary_complete",
                "parameter_update_sets_complete",
                "optimizer_call_counts_consistent",
            )
        )
    ):
        updates = observation.get("updates")
        classes = updates.get("optimizer_classes") if isinstance(updates, Mapping) else None
        if (
            isinstance(classes, list)
            and len(classes) == 1
            and type(classes[0]) is str
            and classes[0]
            in {
                "torch.optim.sgd.SGD",
                "torch.optim.adam.Adam",
                "torch.optim.adagrad.Adagrad",
                "torch.optim.rmsprop.RMSprop",
                "torch.optim.adadelta.Adadelta",
                "torch.optim.adamax.Adamax",
                "torch.optim.asgd.ASGD",
                "torch.optim.radam.RAdam",
                "torch.optim.rprop.Rprop",
                "torch.optim.nadam.NAdam",
                "torch.optim.sparse_adam.SparseAdam",
            }
            and updates.get("unrecognized_optimizer_class_records") == 0
            and type(updates.get("unrecognized_optimizer_class_records")) is int
            and type(observation.get("logical_updates")) is int
            and observation["logical_updates"] > 0
        ):
            catalog["operators"] = []
            catalog["excluded_operators"] = [
                {
                    "id": "adamw_fp32_step_in_backward_v1",
                    "selection_status": "not_applicable_to_observed_optimizer_class",
                    "reported_optimizer_classes": list(classes),
                    "selected_run_id": observation["selected_run_id"],
                    "source_sha256": observation["source_sha256"],
                    "basis": (
                        "The complete selected-run observation reports a different optimizer family. "
                        "Do not convert that optimizer to AdamW. Reported tags do not authenticate a "
                        "native implementation; unknown, custom or mixed optimizers are not excluded."
                    ),
                }
            ]
    if len(json.dumps(catalog, ensure_ascii=True, allow_nan=False).encode()) > MAX_CATALOG_BYTES:
        raise ValueError("Operator metadata exceeds its bounded catalog")
    return catalog
