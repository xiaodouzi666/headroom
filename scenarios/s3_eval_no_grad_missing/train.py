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
    parser.add_argument("--seed", type=int, default=7)
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


def evaluate(model: nn.Module, inputs: torch.Tensor, targets: torch.Tensor) -> float:
    model.eval()
    # BUG: eval() changes module behavior but does not turn off autograd.
    predictions = model(inputs)
    validation_loss = (predictions - targets).square().mean()
    return validation_loss.item()


def main() -> None:
    args = arguments()
    device = setup(args)
    width, depth, sequence = (32, 2, 8) if args.tiny else (768, 8, 512)
    batch = args.batch if args.batch is not None else (2 if args.tiny else 16)
    model = ResidualMLP(width, depth).to(device)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3)
    train_inputs = torch.randn(1, sequence, width, device=device)
    train_targets = torch.randn(1, width, device=device)
    eval_inputs = torch.randn(batch, sequence, width, device=device)
    eval_targets = torch.randn(batch, width, device=device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    emit(
        "scenario_start",
        device,
        scenario="s3_eval_no_grad_missing",
        batch=batch,
        steps=args.steps,
        width=width,
        depth=depth,
        sequence_length=sequence,
        parameter_count=parameter_count,
        parameter_dtype="float32",
        tiny=args.tiny,
        train_batch=1,
        measured_gpu_acceptance=False,
    )
    for step in range(1, args.steps + 1):
        synchronize(device)
        started = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        predictions = model(train_inputs)
        loss = (predictions - train_targets).square().mean()
        loss.backward()
        optimizer.step()
        # The helper releases its graph on return; the defect is peak waste,
        # not an intentionally retained list of predictions or an epoch leak.
        validation_loss = evaluate(model, eval_inputs, eval_targets)
        synchronize(device)
        emit(
            "step",
            device,
            step=step,
            loss=loss.item(),
            validation_loss=validation_loss,
            step_ms=(time.perf_counter() - started) * 1000,
            parameter_count=parameter_count,
        )
    emit("completed", device, steps=args.steps, parameter_count=parameter_count)


if __name__ == "__main__":
    main()
