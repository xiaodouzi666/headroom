"""Offload references are opt-in, source-bound, capped and fail closed."""

import gc
import hashlib
import json
from pathlib import Path

import pytest

from headroom.verify.compare import compare_runs
from headroom.verify.offload import (
    MAX_SAVED_BYTES,
    PROTOCOL,
    STRATEGY,
    OffloadLimitExceeded,
    SavedTensorOffload,
    reference_proof,
    validate_limit,
)
from headroom.verify.pairing import CONTRACTS
from headroom.verify.runner import verify_script

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scenarios/s4_loss_accumulation_graph/train.py"
SOURCE_HASH = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()


def measured(status="completed"):
    return {
        "protocol": "headroom.lab.v1",
        "capture_complete": True,
        "cleanup_verified": True,
        "run_id": "baseline-oom" if status == "oom" else "candidate",
        "status": status,
        "steps": 20 if status == "completed" else 0,
        "loss_series": [1 - i * 0.01 for i in range(20)],
        "peak_allocated_bytes": 2_000_000_000,
        "peak_reserved_bytes": 3_000_000_000,
        "step_ms_median": 100,
        "shared_gpu": False,
        "gpu_observation_complete": True,
        "parameter_count": 161,
        "parameter_count_complete": True,
        "parameter_count_source": "lab_module_parameter_hooks",
        "image_id": "pinned-image",
        "env": {
            "device": "cuda",
            "torch": "2.5.1+cu124",
            "cuda": "12.4",
            "seed": 7,
            "seeded": dict.fromkeys(("python", "torch", "numpy"), True),
            "deterministic_algorithms": True,
            "gpu_name": "fixture GPU",
            "gpu_total_memory_bytes": 24 * 2**30,
        },
        "precision_observation": {
            "protocol": "headroom.precision.v1",
            "source": "lab_runtime_precision_observer_v1",
            "complete": True,
            "device": "cuda",
            "errors": {},
            "precision": "fp32",
            "root_modes": {"fp32": 20, "bf16": 0, "unknown": 0},
        },
        "pairing_capture": {
            "protocol": "headroom.pairing.v1",
            "complete": True,
            "source_contract": {
                "supported": True,
                "profile": "s4",
                "contract_sha256": CONTRACTS["s4"]["digest"],
                "source_sha256": SOURCE_HASH,
                "objective": "fixed-objective",
            },
            "tensors": {"inputs": "actual-data-fingerprint", "targets": "actual-label-fingerprint"},
            "initial_parameters": ["initial-parameter-hash"],
            "updates": [{"step": i + 1, "effective_batch": 8, "backwards": 1} for i in range(20)],
        },
    }


def reference():
    item = measured()
    item["original_baseline_binding"] = {
        "valid": True,
        "baseline_run_id": "baseline-oom",
        "source_sha256": SOURCE_HASH,
        "original_args": [],
    }
    item["reference_offload"] = {
        "script_args": [],
        "request_verified": True,
        "protocol": PROTOCOL,
        "mode": STRATEGY,
        "source_sha256": SOURCE_HASH,
        "torch": "2.5.1+cu124",
        "pin_memory": False,
        "max_saved_bytes": MAX_SAVED_BYTES,
        "entered": True,
        "exited": True,
        "failure": None,
        "cuda_copies": 10,
        "unpacked_tensors": 10,
        "peak_saved_bytes": 1024,
        "performance_comparable": False,
    }
    return item


def test_proven_original_workload_reference_uses_unchanged_tolerance():
    original, candidate = measured("oom"), measured()
    ref = reference()
    ref["peak_allocated_bytes"] = 100  # Reference memory/timing must never score candidate.
    ref["step_ms_median"] = 90000
    report = compare_runs(original, candidate, reference=ref, reference_strategy=STRATEGY)
    assert report.target_met and report.loss_equivalence == "identical"
    assert report.checks["original_workload_offload_reference"]
    assert report.checks["loss_comparable"]
    assert report.peak_after == 2.0
    assert report.numerical_basis == "original_workload_offload_first_five_backward_scalars"
    candidate["loss_series"][0] += 0.01
    failed = compare_runs(original, candidate, reference=ref, reference_strategy=STRATEGY)
    assert failed.loss_equivalence == "changed" and not failed.target_met
    assert failed.loss_tolerance == 1e-3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["reference_offload"].update(request_verified=False),
        lambda r: r["reference_offload"].update(source_sha256="other-source"),
        lambda r: r["reference_offload"].update(exited=False),
        lambda r: r["reference_offload"].update(failure="saved_tensor_cpu_budget_exceeded"),
        lambda r: r["reference_offload"].update(cuda_copies=0),
        lambda r: r["reference_offload"].update(peak_saved_bytes=MAX_SAVED_BYTES + 1),
        lambda r: r["env"].update(torch="2.6.0"),
        lambda r: r["env"].update(PYTORCH_CUDA_ALLOC_CONF="backend:cudaMallocAsync"),
        lambda r: r["pairing_capture"]["tensors"].update(inputs="different-data"),
        lambda r: r["pairing_capture"]["updates"][0].update(effective_batch=1),
        lambda r: r["pairing_capture"].update(initial_parameters=["different-init"]),
        lambda r: r.update(cleanup_verified=False),
        lambda r: r.update(steps=19),
        lambda r: r.update(image_id="different-image"),
    ],
)
def test_bad_proof_cannot_be_upgraded_by_matching_loss_or_explicit_pairing(mutation):
    ref = reference()
    mutation(ref)
    report = compare_runs(
        measured("oom"),
        measured(),
        reference=ref,
        reference_strategy=STRATEGY,
        pairing=dict.fromkeys(("same_inputs", "same_effective_batch", "same_objective"), True),
    )
    assert not report.target_met
    assert report.loss_equivalence == "n/a"
    assert not report.checks["original_workload_offload_reference"]
    # The historical/default scalar gate remains a separate, unchanged contract.
    legacy = compare_runs(measured("oom"), measured(), reference=ref)
    assert "original_workload_offload_reference" not in legacy.checks


def test_repository_no_reference_exception_is_preserved():
    report = compare_runs(
        measured("oom"), measured(), reference_strategy=STRATEGY, acceptance_scope="repository"
    )
    assert report.checks["repository_no_reference_exception"]
    assert report.loss_equivalence == "n/a"
    assert report.numerical_basis == "repository_no_reference_exception"


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, MAX_SAVED_BYTES + 1])
def test_limits_reject_invalid_or_excessive_values(bad):
    with pytest.raises(ValueError):
        validate_limit(bad)


def test_live_copy_cap_is_checked_before_copy_and_freed_with_saved_tensor():
    class Tensor:
        is_cuda = True

        def numel(self):
            return 2

        def element_size(self):
            return 4

    class Packed:
        pass

    instance = object.__new__(SavedTensorOffload)
    instance.limit = 8
    instance.disk = None
    instance.data = {
        "live_saved_bytes": 0,
        "peak_saved_bytes": 0,
        "packed_tensors": 0,
        "cuda_copies": 0,
        "failure": None,
    }
    calls = []
    instance._pack = lambda tensor: (calls.append("copy") or "cuda", Packed())
    saved = instance.pack(Tensor())
    assert instance.data["live_saved_bytes"] == 8
    with pytest.raises(OffloadLimitExceeded):
        instance.pack(Tensor())
    assert calls == ["copy"]
    del saved
    gc.collect()
    assert instance.data["live_saved_bytes"] == 0


def test_runner_preserves_original_argv_and_attempts_only_one_reference(monkeypatch, tmp_path):
    from headroom.verify import runner

    calls = []

    def fake_lab(script, **kwargs):
        calls.append((script, kwargs))
        result = measured() if len(calls) == 1 else reference()
        if len(calls) > 1:
            result["reference_offload"]["script_args"] = kwargs["script_args"]
        return result

    monkeypatch.setattr(runner, "run_script", fake_lab)
    args = ["--batch=8", "--seed", "7"]
    baseline = measured("oom")
    baseline["run_dir"] = str(tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "command": [
                    "/opt/venv/bin/python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                    "--",
                    *args,
                ],
            }
        )
    )
    result = verify_script(
        baseline,
        SCRIPT,
        baseline_script=SCRIPT,
        script_args=args,
        baseline_args=args,
        reference_strategy=STRATEGY,
    )
    assert len(calls) == 2
    assert calls[1][1]["script_args"] == args
    assert calls[1][1]["reference_offload_bytes"] == MAX_SAVED_BYTES
    assert "reference_offload_bytes" not in calls[0][1]
    assert result["report"].target_met
    assert result["reference_discovery"]["strategy"] == STRATEGY


def test_unsupported_source_does_not_execute_offload_or_small_batch_fallback(monkeypatch, tmp_path):
    from headroom.verify import runner

    script = tmp_path / "unknown.py"
    script.write_text("raise RuntimeError('must not execute')")
    calls = []
    monkeypatch.setattr(runner, "run_script", lambda *a, **k: calls.append(k) or measured())
    result = verify_script(
        measured("oom"),
        script,
        baseline_script=script,
        baseline_args=[],
        reference_strategy=STRATEGY,
    )
    assert len(calls) == 1 and result["reference"] is None
    assert not result["report"].target_met


def test_no_explicit_reference_can_bypass_original_execution_binding():
    with pytest.raises(ValueError, match="own bound reference"):
        verify_script(
            measured("oom"),
            SCRIPT,
            baseline_script=SCRIPT,
            reference=reference(),
            reference_strategy=STRATEGY,
        )


def test_lab_rejects_arbitrary_source_before_execution(tmp_path):
    from headroom.lab.runner import run_script

    script = tmp_path / "unknown.py"
    script.write_text("raise RuntimeError('must not execute')")
    with pytest.raises(ValueError, match="reviewed"):
        run_script(script, reference_offload_bytes=1024)


@pytest.mark.parametrize("change", ["source", "argv", "initial_parameters", "inputs"])
def test_original_baseline_binding_rejects_a_different_workload(change, tmp_path):
    from headroom.verify.offload import bind_original_baseline

    baseline = measured("oom")
    baseline["run_dir"] = str(tmp_path)
    (tmp_path / "artifacts").mkdir()
    args = ["--batch", "8"]
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "command": [
                    "python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                    "--",
                    *args,
                ],
            }
        )
    )
    if change == "source":
        baseline["pairing_capture"]["source_contract"]["source_sha256"] = "other"
    if change == "argv":
        args = ["--batch", "1"]
    binding = bind_original_baseline(baseline, SCRIPT, args)
    if change in {"source", "argv"}:
        assert not binding["valid"]
        return
    ref = reference()
    ref["original_baseline_binding"] = binding
    ref["reference_offload"]["script_args"] = args
    if change == "initial_parameters":
        baseline["pairing_capture"]["initial_parameters"] = ["different"]
    else:
        baseline["pairing_capture"]["tensors"]["inputs"] = "different"
    assert not reference_proof(ref, measured(), baseline=baseline)["valid"]


def test_explicit_none_script_args_match_executed_empty_argv(monkeypatch, tmp_path):
    from headroom.lab import runner

    artifact = tmp_path / "artifacts"
    artifact.mkdir()
    (artifact / "reference-offload.json").write_text(
        json.dumps(
            {
                "protocol": PROTOCOL,
                "mode": STRATEGY,
                "source_sha256": SOURCE_HASH,
                "script_args": [],
                "max_saved_bytes": 1024,
            }
        )
    )
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"run_dir": str(tmp_path), "target_artifact_dir": str(artifact)}

    monkeypatch.setattr(runner, "_run", fake_run)
    result = runner.run_script(SCRIPT, script_args=None, reference_offload_bytes=1024)
    assert result["reference_offload"]["request_verified"]
    assert calls[0]["command"][-2:] == ["--reference-offload-bytes", "1024"]


@pytest.mark.parametrize("change", ["missing", "mixed", "different", "baseline_missing"])
def test_offload_reference_requires_observed_original_precision(change):
    baseline, ref = measured("oom"), reference()
    if change == "missing":
        ref.pop("precision_observation")
    elif change == "mixed":
        ref["precision_observation"]["root_modes"]["bf16"] = 1
    elif change == "different":
        ref["precision_observation"].update(
            precision="bf16", root_modes={"fp32": 0, "bf16": 20, "unknown": 0}
        )
    else:
        baseline.pop("precision_observation")
    report = compare_runs(baseline, measured(), reference=ref, reference_strategy=STRATEGY)
    assert not report.target_met and report.loss_equivalence == "n/a"


def test_offload_reference_does_not_override_explicit_candidate_precision_policy():
    candidate = measured()
    candidate["precision_observation"].update(
        precision="bf16", root_modes={"fp32": 0, "bf16": 20, "unknown": 0}
    )
    result = compare_runs(
        measured("oom"),
        candidate,
        reference=reference(),
        reference_strategy=STRATEGY,
        policy={"allow_numerics_change": True},
    )
    assert result.checks["original_workload_offload_reference"]
    assert result.numerics_changed and result.loss_tolerance == 0.02
    assert result.target_met


@pytest.fixture
def fake_tensor_torch(monkeypatch):
    import sys
    from types import SimpleNamespace

    class Tensor:
        def __init__(self, raw=b"12345678", device="cuda"):
            self.raw, self.device = raw, device
            self.dtype, self.shape = "float32", (len(raw) // 4,)

        def numel(self):
            return len(self.raw) // 4

        def element_size(self):
            return 4

        def detach(self):
            return self

        def cpu(self):
            return self

        def to(self, device):
            return Tensor(self.raw, device)

    def save(tensor, output):
        output.write(b"HEAD")
        output.write(tensor.raw)

    def load(handle, *, map_location, weights_only):
        assert map_location == "cpu" and weights_only is True
        assert handle.read(4) == b"HEAD"
        return Tensor(handle.read(), "cpu")

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(Tensor=Tensor, save=save, load=load))
    return Tensor


def test_disk_reference_preserves_file_for_repeated_unpack_and_cleans(fake_tensor_torch, tmp_path):
    from headroom.verify.offload_disk import DiskTensorStore

    store = DiskTensorStore(tmp_path, 1024, 1024)
    packed = store.pack(fake_tensor_torch())
    assert store.peak_bytes == 12  # Includes serialization header.
    assert packed.path.exists()
    for _ in range(2):
        restored = store.unpack(packed)
        assert restored.raw == b"12345678" and restored.device == "cuda"
        assert packed.path.exists()
    assert store.unpacked == 2
    store.close()
    assert store.cleanup_verified and not store.directory.exists() and store.live_bytes == 0


def test_disk_hard_cap_includes_header_and_removes_partial_file(fake_tensor_torch, tmp_path):
    from headroom.verify.offload_disk import DiskTensorStore

    store = DiskTensorStore(tmp_path, 11, 1024)
    with pytest.raises(RuntimeError, match="disk byte budget"):
        store.pack(fake_tensor_torch())
    assert store.failure == "saved_tensor_disk_budget_exceeded"
    assert store.peak_bytes <= 11 and store.live_bytes == 0 and not store.files
    store.close()
    assert store.cleanup_verified


def test_spill_cleanup_rejects_symlinks_without_touching_target(tmp_path):
    from headroom.verify.offload_disk import SPILL_PREFIX, cleanup_spill

    outside = tmp_path / "outside"
    outside.mkdir()
    data = outside / "keep"
    data.write_text("preserve")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / (SPILL_PREFIX + "linked")).symlink_to(outside, target_is_directory=True)
    receipt = cleanup_spill(artifacts)
    assert not receipt["verified"] and data.read_text() == "preserve"


def test_host_spill_cleanup_waits_for_verified_container_stop(monkeypatch, tmp_path):
    from headroom.lab import runner
    from headroom.verify import offload_disk

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setattr(
        runner,
        "_run",
        lambda **kw: {
            "run_dir": str(tmp_path),
            "target_artifact_dir": str(artifacts),
            "cleanup_verified": False,
        },
    )

    def forbidden_cleanup(_):
        raise AssertionError("Must not clean a container whose stop is unverified")

    monkeypatch.setattr(offload_disk, "cleanup_spill", forbidden_cleanup)
    result = runner.run_script(
        SCRIPT,
        reference_offload_bytes=1024,
        reference_offload_disk_bytes=2048,
    )
    assert not result["reference_spill_cleanup"]["verified"]


@pytest.mark.parametrize(
    "field,bad",
    [
        ("peak_staging_tensor_bytes", 0),
        ("peak_staging_tensor_bytes", MAX_SAVED_BYTES // 2 + 1),
        ("peak_staging_tensor_bytes", True),
        ("disk_tensors_created", 0),
        ("disk_tensors_unpacked", 0),
        ("disk_tensors_unpacked", True),
    ],
)
def test_disk_execution_receipt_must_prove_staging_bound_and_actual_work(field, bad):
    from headroom.verify.offload_disk import MAX_DISK_BYTES

    ref = reference()
    ref["reference_offload"].update(
        backend="disk",
        max_disk_bytes=MAX_DISK_BYTES,
        peak_saved_bytes=0,
        disk={
            "max_disk_bytes": MAX_DISK_BYTES,
            "peak_disk_bytes": 4096,
            "live_disk_bytes": 0,
            "cleanup_verified": True,
            "failure": None,
            "peak_staging_tensor_bytes": 2048,
            "disk_tensors_created": 1,
            "disk_tensors_unpacked": 2,
        },
    )
    ref["reference_spill_cleanup"] = {"verified": True}
    assert reference_proof(ref, measured(), baseline=measured("oom"))["valid"]
    ref["reference_offload"]["disk"][field] = bad
    assert not reference_proof(ref, measured(), baseline=measured("oom"))["valid"]
