"""Bounded source contracts and actual runtime observations for numerical pairing.

Only the pinned standalone s1/s3/s4 programs and listed memory-only AST edits
are supported. This is evidence for cooperative targets, not an authentication
boundary against deliberate hook tampering.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import time
import weakref
from pathlib import Path
from typing import Any

PROTOCOL = "headroom.pairing.v1"
# Normalized full-program AST hashes, pinned to the reviewed scenario sources.
CONTRACTS = {
    "s1": {
        "digest": "f3fedffd6687879dcd7c0b452a49dac26d119dd8898dad9b3ef650af478c1c6e",
        "inputs": ("inputs", "targets"),
    },
    "s3": {
        "digest": "0cf09407bc09810ccd15da2c71e73c8ddc2d17827f3498dda5c9bf86bd6d066e",
        "inputs": ("train_inputs", "train_targets", "eval_inputs", "eval_targets"),
    },
    "s4": {
        "digest": "1c188d7ee917a9ca4d536033d43c3d3aa9cd5ad3ba1005dda2ecd6fd8167f1a0",
        "inputs": ("inputs", "targets"),
    },
}


def _call(node: ast.AST, expression: str) -> bool:
    return ast.dump(node, include_attributes=False) == ast.dump(
        ast.parse(expression, mode="eval").body, include_attributes=False
    )


class _MemoryEdits(ast.NodeTransformer):
    """Normalize only reviewed s3/s4 edits, leaving every other AST node pinned."""

    def visit_FunctionDef(self, node):
        if node.name == "evaluate":
            node.decorator_list = [
                item for item in node.decorator_list if not _call(item, "torch.no_grad()")
            ]
            body = []
            for item in node.body:
                if (
                    isinstance(item, ast.With)
                    and len(item.items) == 1
                    and item.items[0].optional_vars is None
                    and _call(item.items[0].context_expr, "torch.no_grad()")
                ):
                    body.extend(item.body)
                else:
                    body.append(item)
            node.body = body
        return self.generic_visit(node)

    def visit_Call(self, node):
        if (
            _call(node.func, "loss.backward")
            and not node.args
            and (
                not node.keywords
                or (
                    len(node.keywords) == 1
                    and node.keywords[0].arg == "retain_graph"
                    and isinstance(node.keywords[0].value, ast.Constant)
                    and type(node.keywords[0].value.value) is bool
                )
            )
        ):
            node.keywords = []
        # A reporting keyword does not participate in the training objective.
        if isinstance(node.func, ast.Name) and node.func.id == "emit":
            for keyword in node.keywords:
                if (
                    keyword.arg == "backward_retain_graph"
                    and isinstance(keyword.value, ast.Constant)
                    and type(keyword.value.value) is bool
                ):
                    keyword.value = ast.Constant(True)
                if keyword.arg == "total_loss" and (
                    _call(keyword.value, "total_loss") or _call(keyword.value, "total_loss.item()")
                ):
                    keyword.value = ast.Name(id="total_loss", ctx=ast.Load())
        return self.generic_visit(node)

    def visit_AugAssign(self, node):
        if (
            isinstance(node.target, ast.Name)
            and node.target.id == "total_loss"
            and isinstance(node.op, ast.Add)
            and any(
                _call(node.value, value)
                for value in ("loss", "loss.item()", "loss.detach()", "loss.detach().item()")
            )
        ):
            node.value = ast.Name(id="loss", ctx=ast.Load())
        return self.generic_visit(node)


class _CheckpointEdits(ast.NodeTransformer):
    """Normalize only an imported, non-reentrant call of the pinned block.

    The full normalized program still has to match a reviewed digest. No batch,
    accumulation, precision, objective, or optimizer edits are normalized.
    """

    def __init__(self, tree):
        self.direct = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "torch.utils.checkpoint"
            and node.level == 0
            and len(node.names) == 1
            and node.names[0].name == "checkpoint"
            and node.names[0].asname is None
            for node in tree.body
        )
        self.qualified = any(
            isinstance(node, ast.Import)
            and len(node.names) == 1
            and node.names[0].name == "torch.utils.checkpoint"
            and node.names[0].asname is None
            for node in tree.body
        )
        self.changed = False

    def visit_Call(self, node):
        recognized = (self.direct and _call(node.func, "checkpoint")) or (
            self.qualified and _call(node.func, "torch.utils.checkpoint.checkpoint")
        )
        keywords = {item.arg: item.value for item in node.keywords}
        if (
            recognized
            and len(node.args) == 2
            and _call(node.args[0], "block")
            and _call(node.args[1], "hidden")
            and len(keywords) == len(node.keywords)
            and set(keywords) in ({"use_reentrant"}, {"use_reentrant", "preserve_rng_state"})
            and _call(keywords["use_reentrant"], "False")
            and (
                "preserve_rng_state" not in keywords
                or _call(keywords["preserve_rng_state"], "True")
            )
        ):
            self.changed = True
            return ast.copy_location(
                ast.Call(
                    func=ast.Name(id="block", ctx=ast.Load()), args=[node.args[1]], keywords=[]
                ),
                node,
            )
        return self.generic_visit(node)

    def normalize(self, tree):
        tree = self.visit(tree)
        if self.changed:
            tree.body = [
                node
                for node in tree.body
                if not (
                    self.direct
                    and isinstance(node, ast.ImportFrom)
                    and node.module == "torch.utils.checkpoint"
                    and node.level == 0
                    and len(node.names) == 1
                    and node.names[0].name == "checkpoint"
                    and node.names[0].asname is None
                )
                and not (
                    self.qualified
                    and isinstance(node, ast.Import)
                    and len(node.names) == 1
                    and node.names[0].name == "torch.utils.checkpoint"
                    and node.names[0].asname is None
                )
            ]
        return tree


def source_contract(script: Path) -> dict[str, Any]:
    try:
        with script.open("rb") as handle:
            source = handle.read(131073)
        if len(source) > 131072:
            raise ValueError("source exceeds 128 KiB contract limit")
        tree = ast.parse(source)
        normalized = _MemoryEdits().visit(tree)
        checkpoint_edits = _CheckpointEdits(normalized)
        normalized = checkpoint_edits.normalize(normalized)
        digest = hashlib.sha256(ast.dump(normalized, include_attributes=False).encode()).hexdigest()
        profile = next((name for name, item in CONTRACTS.items() if item["digest"] == digest), None)
        if profile is None or (checkpoint_edits.changed and profile != "s1"):
            return {
                "supported": False,
                "reason": "source outside pinned s1/s3/s4 AST contracts",
                "source_sha256": hashlib.sha256(source).hexdigest(),
            }
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        loop = next(n for n in main.body if isinstance(n, ast.For))
        return {
            "supported": True,
            "profile": profile,
            "contract_sha256": digest,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "capture_line": loop.lineno,
            "checkpointed": checkpoint_edits.changed,
            "tensor_names": list(CONTRACTS[profile]["inputs"]),
            "objective": "fixed_tensors_residual_mlp_sgd_mse_mean_v1",
        }
    except (OSError, SyntaxError, ValueError, StopIteration) as exc:
        return {"supported": False, "reason": f"source contract unavailable: {type(exc).__name__}"}


class PairingCapture:
    """Hash initialized values once, then observe actual forwards/backwards/updates."""

    def __init__(self, script: Path):
        self.script = str(script)
        self.contract = source_contract(script)
        self.reason = self.contract.get("reason", "initialization capture not reached")
        self.tensors: dict[str, Any] = {}
        self.fingerprints: dict[str, Any] = {}
        self.initial_parameters: list[Any] = []
        self.updates: list[dict[str, int]] = []
        self.training_forwards = 0
        self.checkpoint_recomputations = 0
        self.backwards = 0
        self.hash_seconds = 0.0
        self.bytes_hashed = 0
        self.captured = False
        self.valid = True
        self.previous_trace = None

    def install(self):
        if not self.contract["supported"]:
            return
        self.previous_trace = sys.gettrace()
        if self.previous_trace is not None:
            self.reason = "existing Python tracer prevents isolated capture"
            return
        sys.settrace(self._trace)

    def close(self):
        if sys.gettrace() == self._trace:
            sys.settrace(self.previous_trace)

    def _fingerprint(self, tensor):
        import torch

        if not isinstance(tensor, torch.Tensor) or tensor.layout != torch.strided:
            raise ValueError("unsupported tensor layout/type")
        size = tensor.numel() * tensor.element_size()
        self.bytes_hashed += size
        if self.bytes_hashed > 512 * 1024 * 1024:
            raise ValueError("initial fingerprints exceed 512 MiB limit")
        raw = tensor.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes()
        return {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
        }

    def _trace(self, frame, event, arg):
        if frame.f_code.co_filename != self.script or frame.f_code.co_name != "main":
            return None
        if event == "line" and frame.f_lineno == self.contract["capture_line"]:
            started = None
            try:
                import torch

                # Preserve asynchronous target initialization time in the original
                # Lab interval; only our subsequent copy/hash work is subtracted.
                devices = {
                    frame.f_locals[name].device
                    for name in self.contract["tensor_names"]
                    if getattr(frame.f_locals[name], "is_cuda", False)
                }
                for device in devices:
                    torch.cuda.synchronize(device)
                started = time.perf_counter()
                for name in self.contract["tensor_names"]:
                    tensor = frame.f_locals[name]
                    self.fingerprints[name] = self._fingerprint(tensor)
                    self.tensors[name] = (weakref.ref(tensor), tensor._version)
                self.initial_parameters = [
                    {"name": name, **self._fingerprint(parameter)}
                    for name, parameter in frame.f_locals["model"].named_parameters()
                ]
                self.optimizer = weakref.ref(frame.f_locals["optimizer"])
                self.captured = True
                self.reason = "captured initialized tensors before training loop"
            except Exception as exc:  # noqa: BLE001 - unsupported capture remains unknown
                self.valid = False
                self.reason = f"initialization capture failed: {type(exc).__name__}: {exc}"
            finally:
                self.hash_seconds = time.perf_counter() - started if started is not None else 0.0
                self.close()
            return None
        return self._trace

    def _stable(self):
        for reference, version in self.tensors.values():
            tensor = reference()
            if tensor is None or tensor._version != version:
                self.valid = False
                self.reason = "input/target was released or mutated after fingerprint"
        return self.valid and self.captured

    def forward(self, args):
        if not self._stable():
            return
        # A reviewed non-reentrant checkpoint re-enters inner blocks during the
        # ordinary backward. It is not a second training root forward. The full
        # pinned AST excludes user forwards/gradient accumulation in this phase.
        if self.contract.get("checkpointed") and self.backwards == 1:
            self.checkpoint_recomputations += 1
            return
        training = self.contract["tensor_names"][0]
        if len(args) == 1 and args[0] is self.tensors[training][0]():
            self.training_forwards += 1
        elif (
            self.contract["profile"] != "s3"
            or len(args) != 1
            or (args[0] is not self.tensors["eval_inputs"][0]())
        ):
            self.valid = False
            self.reason = "root forward did not use the captured input tensor"

    def backward(self, tensor, frame):
        if not self._stable():
            return
        if (
            frame.f_code.co_filename != self.script
            or frame.f_code.co_name != "main"
            or frame.f_locals.get("loss") is not tensor
            or any(
                frame.f_locals.get(name) is not reference()
                for name, (reference, _) in self.tensors.items()
            )
        ):
            self.valid = False
            self.reason = "backward call did not match the pinned main loss/data"
        self.backwards += 1

    def step(self, optimizer):
        if not self._stable():
            return
        if optimizer is not self.optimizer() or self.training_forwards != 1 or self.backwards != 1:
            self.valid = False
            self.reason = "expected one observed training forward/backward per optimizer update"
        name = self.contract["tensor_names"][0]
        self.updates.append(
            {
                "step": len(self.updates) + 1,
                "effective_batch": self.fingerprints[name]["shape"][0],
                "training_forwards": self.training_forwards,
                "backwards": self.backwards,
            }
        )
        self.training_forwards = self.backwards = 0

    def evidence(self, steps):
        complete = (
            self.contract["supported"]
            and self.captured
            and self.valid
            and steps > 0
            and len(self.updates) == steps
            and self.training_forwards == self.backwards == 0
        )
        return {
            "protocol": PROTOCOL,
            "complete": complete,
            "reason": self.reason,
            "source_contract": self.contract,
            "tensors": self.fingerprints,
            "initial_parameters": self.initial_parameters,
            "updates": self.updates,
            "hash_seconds": self.hash_seconds,
            "checkpoint_recomputation_root_forwards": self.checkpoint_recomputations,
            "bytes_hashed": self.bytes_hashed,
            "timing": "one initialization hash, excluded from Lab optimizer intervals",
            "coverage": "pinned standalone AST + actual tensors and per-update hooks; "
            "cooperative target only; command mode and arbitrary scripts unsupported",
        }


def derive_pairing(before, after, required_steps=20):
    """Unknown proof stays unknown; source/seed/config equality alone is insufficient."""
    checks = dict.fromkeys(("same_inputs", "same_effective_batch", "same_objective"))
    left = (before or {}).get("pairing_capture", {})
    right = (after or {}).get("pairing_capture", {})
    reasons = []
    for label, evidence in (("reference", left), ("candidate", right)):
        if not (
            evidence.get("protocol") == PROTOCOL
            and evidence.get("complete")
            and len(evidence.get("updates", [])) == required_steps
        ):
            reasons.append(f"{label}: " + evidence.get("reason", "pairing capture unavailable"))
    if not reasons:
        lc, rc = left["source_contract"], right["source_contract"]
        trusted = lc.get("profile") == rc.get("profile") and lc.get("profile") in CONTRACTS
        trusted = trusted and all(
            contract.get("supported")
            and contract.get("contract_sha256") == CONTRACTS[contract["profile"]]["digest"]
            for contract in (lc, rc)
        )
        if trusted:
            checks["same_inputs"] = left["tensors"] == right["tensors"]
            checks["same_effective_batch"] = left["updates"] == right["updates"]
            checks["same_objective"] = (
                lc["objective"] == rc["objective"]
                and left["initial_parameters"] == right["initial_parameters"]
            )
            reasons = [name + " differs" for name, passed in checks.items() if not passed]
        else:
            reasons.append("source contracts unavailable or different")
    return {
        "protocol": PROTOCOL,
        "checks": checks,
        "reasons": reasons,
        "source": "Lab runtime fingerprints and pinned source contracts",
        "reference_run": (before or {}).get("run_id"),
        "candidate_run": (after or {}).get("run_id"),
    }
