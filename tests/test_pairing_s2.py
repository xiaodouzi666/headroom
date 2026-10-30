"""Pinned s2 scope plus small actual CPU captures; no model/GPU calls."""

import copy
import hashlib
import json
import socket
import time
import tracemalloc
from pathlib import Path

import pytest
import torch

from headroom.lab import runner
from headroom.solver_context import runtime_input_observations
from headroom.verify import pairing
from headroom.verify.pairing import CONTRACTS, PairingCapture, derive_pairing, source_contract

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("s2_capacity_v2", "s2_fp32_adamw_1b")
SOURCE_SHA = {
    "s2_capacity_v2": "9565acfbcfc2f1eefd982c80be7ce943e09828578b9b44c3d70342bc82bf7f4c",
    "s2_fp32_adamw_1b": "bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b",
}


@pytest.fixture(autouse=True)
def no_network_or_gpu(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network/model/GPU access forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(torch.cuda, "_lazy_init", denied)
    monkeypatch.setattr(runner, "gpu_state", denied)


def source(profile):
    value = (ROOT / "scenarios" / profile / "train.py").read_text()
    assert hashlib.sha256(value.encode()).hexdigest() == SOURCE_SHA[profile]
    return value


def script_at(tmp_path, text, name):
    directory = tmp_path / name
    directory.mkdir()
    path = directory / "train.py"
    path.write_text(text)
    return path


def memory_edit(text, checkpoint=False):
    text = text.replace("foreach=True", "foreach=False")
    if checkpoint:
        text = text.replace(
            "from torch import nn",
            "from torch import nn\nfrom torch.utils.checkpoint import checkpoint",
        ).replace(
            "hidden = block(hidden)",
            "hidden = checkpoint(block, hidden, use_reentrant=False, preserve_rng_state=True)",
        )
    return text


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("kind", ["original", "foreach", "combined"])
def test_exact_s2_versions_and_listed_memory_edits(tmp_path, profile, kind):
    text = source(profile)
    if kind != "original":
        text = memory_edit(text, checkpoint=kind == "combined")
    result = source_contract(script_at(tmp_path, text, "case"))
    assert result["supported"] and result["profile"] == profile
    assert result["contract_sha256"] == CONTRACTS[profile]["digest"]
    assert result["objective"] == "fixed_tensors_residual_mlp_adamw_mse_mean_v1"
    assert result["tensor_names"] == ["inputs", "targets"]
    assert result["optimizer_foreach_disabled"] == (kind != "original")
    assert result["checkpointed"] == (kind == "combined")


@pytest.mark.parametrize(
    "old,new",
    [
        ("lr=1e-4", "lr=2e-4"),
        ("foreach=False", "foreach=False, weight_decay=0.0"),
        ("foreach=False", "foreach=False, fused=True"),
        ("foreach=False", "foreach=None"),
        ("model.parameters()", "[next(model.parameters())]"),
        ("torch.optim.AdamW", "torch.optim.Adam"),
        ("targets = torch.randn", "targets = torch.ones"),
        ("inputs = torch.randn", "inputs = torch.ones"),
        ("square().mean()", "square().sum()"),
        ("dtype=torch.float32", "dtype=torch.bfloat16"),
        ("else 24", "else 12"),
        ("optimizer.step()", "optimizer.step(); optimizer.step()"),
        ("loss.backward()", "loss.backward(); loss.backward()"),
        ("range(1, args.steps + 1)", "range(1, 2)"),
        ("use_reentrant=False", "use_reentrant=True"),
        ("preserve_rng_state=True", "preserve_rng_state=False"),
        ("checkpoint(block, hidden", "checkpoint(block, hidden.detach()"),
    ],
)
def test_semantic_or_unreviewed_s2_edits_fail_closed(tmp_path, old, new):
    text = memory_edit(source("s2_capacity_v2"), checkpoint=True)
    assert old in text
    assert not source_contract(script_at(tmp_path, text.replace(old, new), "changed"))["supported"]


def test_optimizer_in_backward_is_not_assumed_equivalent(tmp_path):
    text = source("s2_capacity_v2")
    text = (
        text.replace(
            "optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=True)",
            "optimizers = {p: torch.optim.AdamW([p], lr=1e-4, foreach=False) "
            "for p in model.parameters()}\n"
            "    def update(p):\n"
            "        optimizers[p].step()\n"
            "        optimizers[p].zero_grad(set_to_none=True)\n"
            "    for p in model.parameters():\n"
            "        p.register_post_accumulate_grad_hook(update)",
        )
        .replace("        optimizer.zero_grad(set_to_none=True)\n", "")
        .replace("        optimizer.step()\n", "")
    )
    assert not source_contract(script_at(tmp_path, text, "in-backward"))["supported"]


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16, torch.int64])
def test_streamed_fingerprint_matches_full_bytes_with_bounded_host_chunks(
    tmp_path, monkeypatch, dtype
):
    capture = PairingCapture(script_at(tmp_path, source("s2_capacity_v2"), "source"))
    tensor = torch.arange(37).to(dtype)
    expected = hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest()
    copied = []
    original = torch.Tensor.cpu

    def observe(value, *args, **kwargs):
        copied.append(value.numel() * value.element_size())
        return original(value, *args, **kwargs)

    monkeypatch.setattr(pairing, "HASH_CHUNK_BYTES", 16)
    monkeypatch.setattr(torch.Tensor, "cpu", observe)
    result = capture._fingerprint(tensor)
    assert result["sha256"] == expected
    assert len(copied) > 1 and max(copied) <= 16
    assert capture.bytes_hashed == tensor.numel() * tensor.element_size()


def test_hash_total_limit_is_profile_bound_not_unlimited(tmp_path, monkeypatch):
    capture = PairingCapture(script_at(tmp_path, source("s2_capacity_v2"), "source"))
    assert CONTRACTS[capture.contract["profile"]]["max_fingerprint_bytes"] == 6 * 1024**3
    assert CONTRACTS[capture.contract["profile"]]["max_hash_seconds"] == 60.0
    assert "max_fingerprint_bytes" not in CONTRACTS["s1"]
    monkeypatch.setitem(CONTRACTS["s2_capacity_v2"], "max_fingerprint_bytes", 8)
    capture._fingerprint(torch.ones(2))
    with pytest.raises(ValueError, match="reviewed byte limit"):
        capture._fingerprint(torch.ones(1))
    with pytest.raises(ValueError, match="non-contiguous"):
        other = PairingCapture(tmp_path / "source" / "train.py")
        monkeypatch.setitem(CONTRACTS["s2_capacity_v2"], "max_fingerprint_bytes", 128)
        other._fingerprint(torch.ones(2, 2).t())


def test_hash_time_budget_is_checked_between_bounded_copies(tmp_path, monkeypatch):
    capture = PairingCapture(script_at(tmp_path, source("s2_capacity_v2"), "source"))
    clock = iter([0.0, 0.0, 60.0])
    monkeypatch.setattr(pairing.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(pairing, "HASH_CHUNK_BYTES", 4)
    with pytest.raises(ValueError, match="hash time limit"):
        capture._fingerprint(torch.ones(4))
    assert not capture.evidence(20)["complete"]


def test_real_cpu_hash_memory_and_elapsed_are_bounded(tmp_path, monkeypatch):
    capture = PairingCapture(script_at(tmp_path, source("s2_capacity_v2"), "source"))
    tensor = torch.arange(2_097_153, dtype=torch.float32)
    copied = []
    original = torch.Tensor.cpu

    def observe(value, *args, **kwargs):
        copied.append(value.numel() * value.element_size())
        return original(value, *args, **kwargs)

    monkeypatch.setattr(torch.Tensor, "cpu", observe)
    tracemalloc.start()
    started = time.monotonic()
    value = capture._fingerprint(tensor)
    elapsed = time.monotonic() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert copied == [4 * 1024**2, 4 * 1024**2, 4]
    assert peak < 2 * pairing.HASH_CHUNK_BYTES + 1024**2
    assert elapsed < 60
    (tmp_path / "hash-observation.json").write_text(
        json.dumps(
            {
                "bytes_hashed": capture.bytes_hashed,
                "copy_sizes": copied,
                "elapsed_seconds": elapsed,
                "python_tracemalloc_peak_bytes": peak,
                "sha256": value["sha256"],
                "scope": "CPU 8MiB+4B fixture; traced Python allocations are not total process RSS",
            },
            indent=2,
        )
    )


def test_old_unsupported_record_cannot_be_promoted_by_new_contract(tmp_path):
    contract = source_contract(script_at(tmp_path, source("s2_capacity_v2"), "new"))
    old = {
        "run_id": "historical",
        "steps": 20,
        "capture_complete": True,
        "pairing_capture": {
            "protocol": pairing.PROTOCOL,
            "complete": False,
            "reason": "source outside pinned s1/s3/s4 AST contracts",
            "source_contract": {"supported": False},
            "updates": [],
        },
    }
    saved = copy.deepcopy(old)
    assert not old["pairing_capture"]["complete"]
    assert all(value is None for value in derive_pairing(old, old)["checks"].values())
    view = runtime_input_observations(old, [{"sha256": contract["source_sha256"]}])
    assert view["status"] == "unsupported"
    assert old == saved


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("checkpoint", [False, True])
def test_real_cpu_s2_observed_twenty_updates_and_pairing(tmp_path, profile, checkpoint):
    baseline_script = script_at(tmp_path, source(profile), "baseline")
    candidate_script = script_at(tmp_path, memory_edit(source(profile), checkpoint), "candidate")
    args = ["--tiny", "--device", "cpu", "--steps", "20"]
    results = [
        runner.run_script(script, script_args=args, run_root=tmp_path / "runs", device="cpu")
        for script in (baseline_script, candidate_script)
    ]
    for result, script in zip(results, (baseline_script, candidate_script), strict=True):
        assert result["status"] == "completed", result
        assert result["steps"] == 20 and result["cleanup_verified"]
        assert len(result["loss_series"]) == 20
        capture = result["pairing_capture"]
        assert capture["complete"], capture
        assert len(capture["updates"]) == 20
        assert len(capture["initial_parameters"]) > 0 and capture["bytes_hashed"] > 0
        assert all(u["training_forwards"] == u["backwards"] == 1 for u in capture["updates"])
        view = runtime_input_observations(
            result, [{"sha256": hashlib.sha256(script.read_bytes()).hexdigest()}]
        )
        assert view["status"] == "observed", view
        assert view["optimizer_input_name"] == "inputs"
        assert view["effective_batch_per_optimizer_update"] == (
            24 if profile == "s2_capacity_v2" else 2
        )
        assert view["observed_optimizer_updates"] == 20
        assert result["env"]["device"] == "cpu"
    proof = derive_pairing(*results)
    assert proof["checks"] == dict.fromkeys(
        ("same_inputs", "same_effective_batch", "same_objective"), True
    ), proof
    assert (
        results[1]["pairing_capture"]["checkpoint_recomputation_root_forwards"] > 0
        if checkpoint
        else True
    )
    changed = copy.deepcopy(results[1])
    changed["pairing_capture"]["updates"][0]["effective_batch"] += 1
    assert derive_pairing(results[0], changed)["checks"]["same_effective_batch"] is False
    changed = copy.deepcopy(results[1])
    changed["pairing_capture"]["initial_parameters"][0]["sha256"] = "0" * 64
    assert derive_pairing(results[0], changed)["checks"]["same_objective"] is False
