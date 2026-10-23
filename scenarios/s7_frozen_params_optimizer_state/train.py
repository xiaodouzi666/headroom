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


SCENARIO = "s7_frozen_params_optimizer_state"


class HeadOnlyFineTuner(nn.Module):
    def __init__(self, width, depth, classes, device):
        super().__init__()
        self.backbone = nn.Sequential(
            *[
                layer
                for _ in range(depth)
                for layer in (nn.Linear(width, width, device=device), nn.GELU())
            ]
        )
        self.head = nn.Linear(width, classes, device=device)
        # Intended contract: train only the head. eval() does not disable gradients.
        self.backbone.eval()

    def forward(self, x):
        return self.head(self.backbone(x))


def state_bytes(optimizer, parameters):
    return sum(
        value.numel() * value.element_size()
        for parameter in parameters
        for value in optimizer.state[parameter].values()
        if torch.is_tensor(value)
    )


def run(args, device):
    batch = args.batch if args.batch is not None else (2 if args.tiny else 8)
    width, depth, classes = (32, 2, 8) if args.tiny else (8192, 16, 256)
    model = HeadOnlyFineTuner(width, depth, classes, device)
    # Defect: backbone requires_grad was never disabled and all parameters enter AdamW.
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=False)
    emit(
        "workload",
        batch=batch,
        width=width,
        depth=depth,
        classes=classes,
        intended_trainable="head",
        parameter_count=sum(p.numel() for p in model.parameters()),
        backbone_parameter_count=sum(p.numel() for p in model.backbone.parameters()),
        actual_trainable_parameter_count=sum(
            p.numel() for p in model.parameters() if p.requires_grad
        ),
    )
    inputs = torch.randn(batch, width, device=device)
    labels = torch.randint(classes, (batch,), device=device)
    losses = []
    for step in range(args.steps):
        sync(device)
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        logits = model(inputs)
        loss = F.cross_entropy(logits, labels)
        loss.backward()
        optimizer.step()
        value = float(loss.detach())
        del loss, logits
        sync(device)
        losses.append(value)
        emit(
            "step",
            step=step + 1,
            loss=value,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            backbone_optimizer_state_bytes=state_bytes(optimizer, model.backbone.parameters()),
            **memory(device),
        )
    emit(
        "summary",
        scenario=SCENARIO,
        status="completed",
        steps=args.steps,
        loss_series=losses,
        **memory(device),
    )


if __name__ == "__main__":
    main()
