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


SCENARIO = "s8_two_models_resident"


class Classifier(nn.Module):
    def __init__(self, features, width, depth, classes, device):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(features, width),
            nn.GELU(),
            *[layer for _ in range(depth - 1) for layer in (nn.Linear(width, width), nn.GELU())],
            nn.Linear(width, classes),
        )
        self.to(device)

    def forward(self, x):
        return self.layers(x)


def run(args, device):
    batch = args.batch if args.batch is not None else (2 if args.tiny else 32)
    features, student_width, teacher_width, teacher_depth, classes = (
        (16, 32, 64, 2, 8) if args.tiny else (512, 1024, 8192, 12, 256)
    )
    student = Classifier(features, student_width, 3, classes, device)
    # Defect: the disabled teacher is eagerly created on the GPU and remains resident.
    teacher = Classifier(features, teacher_width, teacher_depth, classes, device).eval()
    teacher.requires_grad_(False)
    distillation_weight = 0.0
    optimizer = torch.optim.AdamW(student.parameters(), lr=1e-4, foreach=False)
    emit(
        "workload",
        batch=batch,
        features=features,
        student_width=student_width,
        teacher_width=teacher_width,
        teacher_depth=teacher_depth,
        distillation_weight=distillation_weight,
        parameter_count=sum(p.numel() for p in student.parameters())
        + sum(p.numel() for p in teacher.parameters()),
        teacher_parameter_bytes=sum(p.numel() * p.element_size() for p in teacher.parameters()),
    )
    inputs = torch.randn(batch, features, device=device)
    labels = torch.randint(classes, (batch,), device=device)
    losses = []
    for step in range(args.steps):
        sync(device)
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        logits = student(inputs)
        loss = F.cross_entropy(logits, labels)
        if distillation_weight > 0:
            with torch.no_grad():
                teacher_logits = teacher(inputs)
            loss = loss + distillation_weight * F.mse_loss(logits, teacher_logits)
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
