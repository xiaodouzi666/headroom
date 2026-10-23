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


SCENARIO = "s6_full_vocab_logits_fp32"


def run(args, device):
    batch = args.batch if args.batch is not None else (2 if args.tiny else 8)
    length, width, vocabulary = (16, 32, 128) if args.tiny else (2048, 128, 131072)
    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    embedding = nn.Embedding(vocabulary, width, device=device, dtype=dtype)
    projection = nn.Linear(width, vocabulary, bias=False, device=device, dtype=dtype)
    model = nn.Sequential(
        embedding, nn.Linear(width, width, device=device, dtype=dtype), nn.GELU(), projection
    )
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3)
    emit(
        "workload",
        batch=batch,
        sequence_length=length,
        width=width,
        vocabulary=vocabulary,
        parameter_count=sum(p.numel() for p in model.parameters()),
        dtype=str(dtype),
        full_fp32_logits_bytes=batch * length * vocabulary * 4,
    )
    # Fixed examples make the 20-step loss series meaningful for this synthetic training task.
    tokens = torch.randint(vocabulary, (batch, length), device=device)
    labels = torch.randint(vocabulary, (batch, length), device=device)
    losses = []
    for step in range(args.steps):
        sync(device)
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        low_precision_logits = model(tokens)
        # Defect: both full logits and their fp32 copy remain live through full-vocabulary CE.
        logits = low_precision_logits.float()
        loss = F.cross_entropy(logits.reshape(-1, vocabulary), labels.reshape(-1))
        loss.backward()
        optimizer.step()
        value = float(loss.detach())
        del loss, logits, low_precision_logits
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
