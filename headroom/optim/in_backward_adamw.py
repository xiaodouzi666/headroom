"""Research control: FP32 AdamW updates as each leaf gradient becomes ready.

Based on PyTorch's optimizer-step-in-backward tutorial and its 2.5.1 AdamW
functional implementation. This is not a generated repair or model success.
Use only a single ordinary backward per logical step, with no gradient
accumulation, gradient clipping, AMP/GradScaler, closures, distributed reduction,
compiled execution, or higher-order gradients. The algorithm updates every
parameter that receives a gradient; it never freezes or omits model parameters.

The public step() finishes one logical update. Per-parameter callbacks invoke
the functional kernel, not optimizer.step(), so observers see one logical step.
"""

from __future__ import annotations

import torch
from torch.optim.adamw import adamw


class AdamWInBackward(torch.optim.AdamW):
    """Restricted, explicit research optimizer for the pinned torch runtime."""

    def __init__(self, params, *args, **kwargs):
        if str(torch.__version__).split("+")[0] != "2.5.1":
            raise RuntimeError("AdamWInBackward is reviewed only for torch 2.5.1")
        for name in ("foreach", "fused", "capturable", "differentiable"):
            if kwargs.get(name) not in (False, None):
                raise ValueError(name + " is unsupported by the FP32 research control")
            kwargs[name] = False
        self._configured = False
        self._pending = set()
        self._handles = []
        self._failed = False
        self._closed = False
        self.logical_steps = 0
        self.parameter_updates = 0
        super().__init__(params, *args, **kwargs)
        self._groups = {}
        self._index_groups()
        for parameter in self._groups:
            if parameter.requires_grad:
                self._handles.append(
                    parameter.register_post_accumulate_grad_hook(self._update_parameter)
                )
        self._configured = True

    def _index_groups(self):
        groups = {}
        for group in self.param_groups:
            if any(group[name] for name in ("foreach", "fused", "capturable", "differentiable")):
                raise ValueError("Only the eager single-tensor FP32 AdamW algorithm is supported")
            for parameter in group["params"]:
                if parameter in groups:
                    raise ValueError("Duplicate parameters are unsupported")
                if parameter.dtype != torch.float32 or parameter.layout != torch.strided:
                    raise TypeError("Only dense FP32 parameters are supported")
                if not parameter.is_leaf:
                    raise ValueError("Only leaf parameters are supported")
                groups[parameter] = group
        self._groups = groups

    def add_param_group(self, param_group):
        if self._configured:
            raise RuntimeError("Adding parameters after hook installation is unsupported")
        return super().add_param_group(param_group)

    def _update_parameter(self, parameter):
        if self._closed or self._failed:
            raise RuntimeError("Research optimizer is closed or previously failed")
        if parameter in self._pending:
            self._failed = True
            raise RuntimeError("Multiple backwards before a logical step are unsupported")
        if torch.is_grad_enabled():
            self._failed = True
            raise RuntimeError("Higher-order gradients are unsupported")
        if parameter.grad is None:
            return
        if parameter.grad.is_sparse or parameter.grad.dtype != torch.float32:
            self._failed = True
            raise TypeError("Only dense unscaled FP32 gradients are supported")
        group = self._groups[parameter]
        params, grads, averages, squares, maxima, steps = [], [], [], [], [], []
        try:
            has_complex = self._init_group(
                {**group, "params": [parameter]},
                params,
                grads,
                group["amsgrad"],
                averages,
                squares,
                maxima,
                steps,
            )
            with torch.no_grad():
                adamw(
                    params,
                    grads,
                    averages,
                    squares,
                    maxima,
                    steps,
                    foreach=False,
                    capturable=False,
                    differentiable=False,
                    fused=False,
                    grad_scale=None,
                    found_inf=None,
                    has_complex=has_complex,
                    amsgrad=group["amsgrad"],
                    beta1=group["betas"][0],
                    beta2=group["betas"][1],
                    lr=group["lr"],
                    weight_decay=group["weight_decay"],
                    eps=group["eps"],
                    maximize=group["maximize"],
                )
            parameter.grad = None
            self._pending.add(parameter)
            self.parameter_updates += 1
        except BaseException:
            self._failed = True
            raise

    def step(self, closure=None):
        if closure is not None:
            raise ValueError("Closures are unsupported")
        if self._closed or self._failed:
            raise RuntimeError("Research optimizer is closed or previously failed")
        if not self._pending:
            raise RuntimeError("A logical step requires a completed ordinary backward")
        self._pending.clear()
        self.logical_steps += 1

    def zero_grad(self, set_to_none=True):
        if self._pending:
            raise RuntimeError("Finish the logical step before zero_grad")
        return super().zero_grad(set_to_none=set_to_none)

    def state_dict(self):
        if self._pending:
            raise RuntimeError("Checkpoint only at a completed logical step boundary")
        return super().state_dict()

    def load_state_dict(self, state_dict):
        if self._pending:
            raise RuntimeError("Restore only at a completed logical step boundary")
        result = super().load_state_dict(state_dict)
        self._index_groups()
        return result

    def close(self):
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._closed = True
