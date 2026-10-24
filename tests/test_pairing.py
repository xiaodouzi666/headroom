"""Trusted source scope and real CPU Docker pairing, without model/GPU calls."""

import copy
import json
from pathlib import Path

import pytest

from headroom.lab.runner import run_script
from headroom.verify.pairing import CONTRACTS, derive_pairing, source_contract
from headroom.verify.runner import verify_script

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {"s3": "s3_eval_no_grad_missing", "s4": "s4_loss_accumulation_graph"}
ARGS = ["--tiny", "--device", "cpu", "--steps", "20"]


def source(profile):
    return (ROOT / "scenarios" / SCENARIOS[profile] / "train.py").read_text()


def repaired(profile, text):
    if profile == "s3":
        return text.replace("def evaluate(", "@torch.no_grad()\ndef evaluate(")
    return (
        text.replace("loss.backward(retain_graph=True)", "loss.backward()")
        .replace("total_loss += loss", "total_loss += loss.item()")
        .replace("total_loss=total_loss.item()", "total_loss=total_loss")
    )


def script_at(tmp_path, text, name):
    directory = tmp_path / name
    directory.mkdir()
    script = directory / "train.py"
    script.write_text(text)
    return script


@pytest.mark.parametrize("profile", ["s3", "s4"])
def test_pinned_source_and_reviewed_memory_edits_only(tmp_path, profile):
    for index, text in enumerate((source(profile), repaired(profile, source(profile)))):
        contract = source_contract(script_at(tmp_path, text, str(index)))
        assert contract["supported"]
        assert contract["profile"] == profile
        assert contract["contract_sha256"] == CONTRACTS[profile]["digest"]


@pytest.mark.parametrize(
    "before,after",
    [
        ("torch.randn(1, sequence, width", "torch.ones(1, sequence, width"),
        ("train_targets = torch.randn", "train_targets = torch.ones"),
        (
            "(predictions - train_targets).square().mean()",
            "(predictions - train_targets).abs().mean()",
        ),
        ("lr=1e-3", "lr=2e-3"),
        ("train_inputs = torch.randn(1,", "train_inputs = torch.randn(2,"),
        ("loss.backward()", "loss.backward(); loss.backward()"),
    ],
)
def test_changed_data_target_objective_batch_or_update_is_unsupported(tmp_path, before, after):
    text = source("s3")
    assert before in text
    contract = source_contract(script_at(tmp_path, text.replace(before, after), "changed"))
    assert not contract["supported"]


def test_arbitrary_script_and_identical_seed_are_not_proof(tmp_path):
    contract = source_contract(script_at(tmp_path, "print('unreviewed')", "unknown"))
    assert not contract["supported"]
    proof = derive_pairing({"env": {"seed": 7}}, {"env": {"seed": 7}})
    assert all(value is None for value in proof["checks"].values())
    assert len(proof["reasons"]) == 2


@pytest.mark.parametrize("profile", ["s3", "s4"])
def test_real_cpu_default_verifier_produces_auditable_pairing(tmp_path, profile):
    baseline_script = script_at(tmp_path, source(profile), "baseline")
    candidate_script = script_at(tmp_path, repaired(profile, source(profile)), "candidate")
    root = tmp_path / "runs"
    baseline = run_script(baseline_script, script_args=ARGS, run_root=root, device="cpu")
    assert baseline["status"] == "completed", baseline
    result = verify_script(
        baseline,
        candidate_script,
        script_args=ARGS,
        run_root=root,
        device="cpu",
        target="reclaim",
    )
    proof = result["pairing_evidence"]
    assert proof["checks"] == dict.fromkeys(
        ("same_inputs", "same_effective_batch", "same_objective"), True
    ), (proof, baseline.get("pairing_capture"), result["candidate"].get("pairing_capture"))
    assert result["report"].loss_equivalence == "identical"
    # CPU proof cannot close a GPU-memory/throughput gate.
    assert not result["report"].target_met
    assert result["candidate"]["cleanup_verified"]
    capture = result["candidate"]["pairing_capture"]
    assert capture["complete"] and capture["bytes_hashed"] > 0 and capture["hash_seconds"] > 0
    assert len(capture["updates"]) == 20
    assert "hash time excluded" in result["candidate"]["timing_note"]
    saved = json.loads((Path(result["candidate"]["run_dir"]) / "verification.json").read_text())
    assert saved["pairing_evidence"] == proof

    # Every piece of proof matters even if the seeds still match.
    for key in ("tensors", "initial_parameters", "updates"):
        changed = copy.deepcopy(result["candidate"])
        if key == "tensors":
            first = next(iter(changed["pairing_capture"][key]))
            changed["pairing_capture"][key][first]["sha256"] = "0" * 64
        elif key == "initial_parameters":
            changed["pairing_capture"][key][0]["sha256"] = "0" * 64
        else:
            changed["pairing_capture"][key][0]["effective_batch"] += 1
        checks = derive_pairing(baseline, changed)["checks"]
        expected = {
            "tensors": "same_inputs",
            "initial_parameters": "same_objective",
            "updates": "same_effective_batch",
        }[key]
        assert checks[expected] is False

    if profile == "s4":
        changed_batch = verify_script(
            baseline,
            candidate_script,
            script_args=[*ARGS, "--batch", "1"],
            run_root=root,
            device="cpu",
            target="reclaim",
        )
        assert changed_batch["candidate"]["pairing_capture"]["complete"]
        assert changed_batch["pairing_evidence"]["checks"]["same_inputs"] is False
        assert changed_batch["pairing_evidence"]["checks"]["same_effective_batch"] is False
        assert changed_batch["report"].loss_equivalence == "n/a"
        unsupported = script_at(
            tmp_path,
            repaired(profile, source(profile)).replace(
                "targets = torch.randn", "targets = torch.ones"
            ),
            "changed-target",
        )
        unknown = verify_script(
            baseline,
            unsupported,
            script_args=ARGS,
            run_root=root,
            device="cpu",
            target="reclaim",
        )
        assert unknown["candidate"]["status"] == "completed"
        assert unknown["report"].loss_equivalence == "n/a"
        assert all(value is None for value in unknown["pairing_evidence"]["checks"].values())
        assert "pinned" in unknown["candidate"]["pairing_capture"]["reason"]


def test_no_grad_context_is_supported_but_training_no_grad_is_not(tmp_path):
    text = source("s3")
    start = text.index("    model.eval()", text.index("def evaluate("))
    end = text.index("\n\ndef main()", start)
    body = text[start:end]
    context = (
        text[:start]
        + "    with torch.no_grad():\n"
        + "".join(
            "    " + line if line.strip() else line for line in body.splitlines(keepends=True)
        )
        + text[end:]
    )
    assert source_contract(script_at(tmp_path, context, "eval-context"))["supported"]
    assert not source_contract(
        script_at(
            tmp_path,
            text.replace("def main()", "@torch.no_grad()\ndef main()"),
            "training-context",
        )
    )["supported"]


def test_runtime_input_mutation_and_missing_forward_fail_closed(tmp_path):
    import weakref

    import torch

    from headroom.verify.pairing import PairingCapture

    capture = PairingCapture(script_at(tmp_path, source("s4"), "source"))
    tensor = torch.ones(2, 2)
    capture.tensors = {"inputs": (weakref.ref(tensor), tensor._version)}
    capture.captured = True
    tensor.add_(1)
    capture.forward((tensor,))
    assert not capture.valid
    assert "mutated" in capture.reason

    second = PairingCapture(tmp_path / "source" / "train.py")
    second.captured = True
    second.tensors = {"inputs": (weakref.ref(tensor), tensor._version)}
    second.fingerprints = {"inputs": {"shape": [2, 2]}}
    optimizer = torch.optim.SGD([torch.nn.Parameter(torch.ones(1))], lr=0.1)
    second.optimizer = weakref.ref(optimizer)
    second.step(optimizer)
    assert not second.evidence(1)["complete"]
    assert "one observed" in second.reason


def test_hash_cost_is_excluded_once_from_step_intervals_only(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from headroom.lab import hooks

    session = hooks.CaptureSession(tmp_path, device="cpu")
    session.started_at = 1.0
    session.last_step_at = 2.0
    session.pairing_capture = SimpleNamespace(hash_seconds=1.25, step=lambda optimizer: None)
    monkeypatch.setattr(hooks.time, "perf_counter", lambda: 5.0)
    session._optimizer_step(None, (), {})
    assert session.step_records[0]["step_ms"] == 1750
    assert session.step_records[0]["elapsed_ms"] == 4000
    monkeypatch.setattr(hooks.time, "perf_counter", lambda: 6.0)
    session._optimizer_step(None, (), {})
    assert session.step_records[1]["step_ms"] == 1000
    assert session.started_at == 1.0


def test_pending_cuda_setup_is_synchronized_before_hash_clock(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import torch

    from headroom.verify import pairing

    class FakeTensor:
        is_cuda = True
        device = torch.device("cuda:0")
        _version = 0

    class FakeOptimizer:
        pass

    capture = pairing.PairingCapture(script_at(tmp_path, source("s4"), "timing"))
    events = []
    values = [FakeTensor(), FakeTensor()]
    frame = SimpleNamespace(
        f_code=SimpleNamespace(co_filename=capture.script, co_name="main"),
        f_lineno=capture.contract["capture_line"],
        f_locals={
            "inputs": values[0],
            "targets": values[1],
            "model": SimpleNamespace(named_parameters=list),
            "optimizer": FakeOptimizer(),
        },
    )
    monkeypatch.setattr(torch.cuda, "synchronize", lambda device: events.append("synchronize"))
    monkeypatch.setattr(pairing.time, "perf_counter", lambda: events.append("clock") or 10.0)
    monkeypatch.setattr(capture, "_fingerprint", lambda tensor: events.append("hash") or {})
    capture._trace(frame, "line", None)
    assert capture.captured
    assert events == ["synchronize", "clock", "hash", "hash", "clock"]
