"""Synthetic GPU-memory fixture; run only in the isolated Lab sandbox."""

import argparse
import json
import time

import torch
from torch import nn


class ResidualBlock(nn.Module):
    def __init__(self, width: int) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(width)
        self.ff = nn.Sequential(nn.Linear(width, 4 * width), nn.GELU(), nn.Linear(4 * width, width))

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return inputs + self.ff(self.norm(inputs))


class ResidualMLP(nn.Module):
    def __init__(self, width: int, depth: int) -> None:
        super().__init__()
        self.blocks = nn.ModuleList(ResidualBlock(width) for _ in range(depth))

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        hidden = inputs
        for block in self.blocks:
            hidden = block(hidden)
        return hidden.mean(dim=1)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--tiny", action="store_true", help="Plumbing test, not GPU acceptance")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    if args.steps < 1 or (args.batch is not None and args.batch < 1):
        parser.error("--steps and --batch must be positive")
    return args


def emit(event: str, device: torch.device, **metrics: object) -> None:
    if device.type == "cuda":
        metrics.update(
            allocated_bytes=torch.cuda.memory_allocated(device),
            reserved_bytes=torch.cuda.memory_reserved(device),
            peak_allocated_bytes=torch.cuda.max_memory_allocated(device),
            peak_reserved_bytes=torch.cuda.max_memory_reserved(device),
        )
    print(json.dumps({"event": event, **metrics}, allow_nan=False), flush=True)


def setup(args: argparse.Namespace) -> torch.device:
    torch.manual_seed(args.seed)
    if args.device == "cpu":
        torch.set_num_threads(1)
    return torch.device(args.device)


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def optimizer_state_bytes(optimizer: torch.optim.Optimizer) -> int:
    return sum(
        value.numel() * value.element_size()
        for state in optimizer.state.values()
        for value in state.values()
        if isinstance(value, torch.Tensor)
    )


def optimizer_inventory(optimizer: torch.optim.Optimizer) -> dict:
    parameters = [parameter for group in optimizer.param_groups for parameter in group["params"]]
    initialized = [parameter for parameter in parameters if parameter in optimizer.state]
    moments = [
        optimizer.state[parameter].get(name)
        for parameter in initialized
        for name in ("exp_avg", "exp_avg_sq")
    ]
    valid = all(
        isinstance(optimizer.state[parameter].get(name), torch.Tensor)
        and optimizer.state[parameter][name].shape == parameter.shape
        and optimizer.state[parameter][name].dtype == torch.float32
        and optimizer.state[parameter][name].device == parameter.device
        for parameter in initialized
        for name in ("exp_avg", "exp_avg_sq")
    )
    return {
        "parameters_total": len(parameters),
        "parameters_initialized": len(initialized),
        "initialized_parameter_numel": sum(parameter.numel() for parameter in initialized),
        "all_parameter_states_initialized": len(initialized) == len(parameters),
        "moment_layout_valid": valid,
        "moment_tensor_bytes": sum(
            value.numel() * value.element_size()
            for value in moments
            if isinstance(value, torch.Tensor)
        ),
        "cuda_moment_tensor_bytes": sum(
            value.numel() * value.element_size()
            for value in moments
            if isinstance(value, torch.Tensor) and value.device.type == "cuda"
        ),
    }


def main() -> None:
    args = arguments()
    device = setup(args)
    width, depth, sequence = (32, 2, 8) if args.tiny else (2048, 32, 128)
    batch = args.batch if args.batch is not None else 2
    model = ResidualMLP(width, depth).to(device=device, dtype=torch.float32)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=False)
    inputs = torch.randn(batch, sequence, width, device=device)
    targets = torch.randn(batch, width, device=device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    emit(
        "scenario_start",
        device,
        scenario="s2_optimizer_classification_v2",
        batch=batch,
        steps=args.steps,
        width=width,
        depth=depth,
        sequence_length=sequence,
        parameter_count=parameter_count,
        parameter_dtype="float32",
        tiny=args.tiny,
        expected_adam_moment_bytes=parameter_count * 8,
        measured_gpu_acceptance=False,
    )
    model.train()
    for step in range(1, args.steps + 1):
        synchronize(device)
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        predictions = model(inputs)
        loss = (predictions - targets).square().mean()
        loss.backward()
        optimizer.step()
        synchronize(device)
        emit(
            "step",
            device,
            step=step,
            loss=loss.item(),
            step_ms=(time.perf_counter() - started) * 1000,
            parameter_count=parameter_count,
            optimizer_state_bytes=optimizer_state_bytes(optimizer),
            optimizer_inventory=optimizer_inventory(optimizer),
        )
    emit(
        "completed",
        device,
        steps=args.steps,
        parameter_count=parameter_count,
        optimizer_inventory=optimizer_inventory(optimizer),
    )


if __name__ == "__main__":
    try:
        main()
    except torch.OutOfMemoryError:
        # Peak counters survive stack unwinding; startup/previous-step readings
        # alone are not a measurement of the peak at failure.
        if torch.cuda.is_initialized():
            emit("summary", torch.device("cuda"), status="oom")
        raise
