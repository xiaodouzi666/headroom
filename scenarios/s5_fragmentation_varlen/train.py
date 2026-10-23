"""Deliberately inefficient synthetic workload; default GPU calibration is pending."""

import argparse
import json
import time

import torch
from torch import nn
from torch.nn import functional as F


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument(
        "--tiny", action="store_true", help="Small plumbing fixture; not acceptance"
    )
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.steps < 1 or (args.batch is not None and args.batch < 1):
        parser.error("steps and batch must be positive")
    torch.manual_seed(args.seed)
    return args


def memory(device):
    if device.type != "cuda":
        return {"peak_allocated_bytes": None, "peak_reserved_bytes": None}
    stats = torch.cuda.memory_stats(device)
    return {
        "allocated_bytes": torch.cuda.memory_allocated(device),
        "reserved_bytes": torch.cuda.memory_reserved(device),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
        "inactive_split_bytes": stats.get("inactive_split_bytes.all.current", 0),
        "allocation_retries": stats.get("num_alloc_retries", 0),
    }


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, allow_nan=False), flush=True)


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main():
    args = arguments()
    device = torch.device(args.device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    emit(
        "configuration",
        scenario=SCENARIO,
        batch=args.batch,
        steps=args.steps,
        device=args.device,
        tiny=args.tiny,
        seed=args.seed,
        calibrated=False,
    )
    try:
        run(args, device)
    except torch.OutOfMemoryError:
        emit("summary", scenario=SCENARIO, status="oom", **memory(device))
        raise


SCENARIO = "s5_fragmentation_varlen"


class TokenMLP(nn.Module):
    def __init__(self, width, depth, device):
        super().__init__()
        self.layers = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(width, 4 * width, device=device),
                    nn.GELU(),
                    nn.Linear(4 * width, width, device=device),
                )
                for _ in range(depth)
            ]
        )

    def forward(self, x):
        for layer in self.layers:
            x = x + layer(x)
        return x


def run(args, device):
    batch = args.batch if args.batch is not None else (2 if args.tiny else 8)
    width, depth, base_length, stride = (32, 2, 16, 1) if args.tiny else (1024, 6, 2048, 32)
    model = TokenMLP(width, depth, device)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)
    lengths = [base_length + stride * offset for offset in (0, 3, 1, 6, 2, 8, 4, 7, 5, 9)]
    emit(
        "workload",
        batch=batch,
        width=width,
        depth=depth,
        sequence_lengths=lengths,
        parameter_count=sum(p.numel() for p in model.parameters()),
    )
    losses = []
    for step in range(args.steps):
        sync(device)
        started = time.perf_counter()
        length = lengths[step % len(lengths)]
        optimizer.zero_grad(set_to_none=True)
        # Real padded token batches vary in length; all activations participate in the loss.
        inputs = torch.randn(batch, length, width, device=device)
        outputs = model(inputs)
        loss = F.mse_loss(outputs, inputs)
        loss.backward()
        optimizer.step()
        value = float(loss.detach())
        del loss, outputs, inputs
        sync(device)
        losses.append(value)
        emit(
            "step",
            step=step + 1,
            sequence_length=length,
            loss=value,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            **memory(device),
        )
    emit(
        "summary",
        scenario=SCENARIO,
        status="completed",
        steps=args.steps,
        loss_series=losses,
        fragmentation_confirmed=False,
        **memory(device),
    )


if __name__ == "__main__":
    main()
