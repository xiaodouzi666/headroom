"""Native pickle -> real evidence/schema validation -> offline fake-model artifacts only."""

import dataclasses
import hashlib
import json
import os
import pickle
import socket
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

import headroom.snapshot_diagnosis as core
from headroom.api.snapshot_routes import public_result
from headroom.budget import BudgetExceeded
from headroom.config import ULTRA_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import LLMError, TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.runtime import RuntimeNotReady
from headroom.snapshot_diagnosis import (
    SnapshotDiagnosisRequest,
    SnapshotServices,
    canonical_hash,
    run_snapshot_diagnosis,
)
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Snapshot core tests must never use a network or live runtime")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(core, "_live_runtime", denied)


def native_snapshot():
    frames = [{"filename": "/untrusted/train.py", "line": 7, "name": "forward"}]
    return {
        "segments": [
            {
                "device": 0,
                "address": 4096,
                "total_size": 512,
                "blocks": [
                    {
                        "address": 4096,
                        "size": 512,
                        "state": "active_allocated",
                        "requested_size": 512,
                        "frames": frames,
                    }
                ],
            }
        ],
        "device_traces": [
            [
                {"action": "segment_alloc", "addr": 4096, "size": 512, "stream": 0},
                {"action": "alloc", "addr": 4096, "size": 512, "stream": 0, "frames": frames},
            ]
        ],
    }


@pytest.fixture
def upload(tmp_path):
    path = tmp_path / "upload.pickle"
    path.write_bytes(pickle.dumps(native_snapshot(), protocol=pickle.HIGHEST_PROTOCOL))
    return path


def diagnosis(reference):
    return {
        "root_causes": [
            {
                "id": "c1",
                "title": "Offline fixture: activation hypothesis",
                "category": "activations",
                "bytes_gb": 0.000000512,
                "evidence_refs": [reference],
                "confidence": 0.5,
            }
        ],
        "plan": [
            {
                "fix_id": "p1",
                "type": "code",
                "title": "Inspect activation lifetime",
                "description": "Preserve source semantics while reducing unnecessary live storage.",
                "expected_saving_gb": 0.0000001,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Synthetic test hypothesis; no hardware verification.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Offline fixture, not a real model diagnosis or GPU result."],
    }


class OfflineRuntimeFactory:
    """Exercise the real router/schema and persist a fake wire receipt under the supplied job."""

    def __init__(self, mutate=None, *, finish_reason="stop"):
        self.mutate = mutate
        self.finish_reason = finish_reason
        self.calls = []
        self.requests = []
        self.closed = False
        self.client = None

    def __call__(self, run_id, store, directory):
        assert store.path == directory / "private" / "calls.db"
        self.calls.append((run_id, store.path, directory))
        evidence = json.loads((directory / "evidence.json").read_text())
        reference = next(iter(evidence["analysis"]["stack_catalog"]))
        payload = diagnosis(reference)
        if self.mutate:
            payload = self.mutate(payload)

        def respond(request):
            body = json.loads(request.content)
            self.requests.append(body)
            # Test-only receipt. The live runtime has its own private Store request hooks.
            receipt = directory / "private" / "offline-wire.json"
            receipt.write_bytes(request.content)
            receipt.chmod(0o600)
            store.add_llm_call(
                run_id,
                {
                    "role": "diagnose",
                    "model": ULTRA_MODEL,
                    "outcome": "response",
                    "settled": True,
                    "cost_usd": None,
                    "request_evidence": {"wire_payload": body},
                    "provenance": "offline_fixture",
                },
            )
            return httpx.Response(
                200,
                json={
                    "id": "offline-snapshot-diagnosis",
                    "object": "chat.completion",
                    "created": 0,
                    "model": ULTRA_MODEL,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": self.finish_reason,
                            "message": {
                                "role": "assistant",
                                "content": payload
                                if isinstance(payload, str)
                                else json.dumps(payload),
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 200,
                        "completion_tokens": 100,
                        "total_tokens": 300,
                    },
                },
            )

        models = candidate_models()
        models["ultra"] = dataclasses.replace(
            models["ultra"],
            capabilities=VerifiedCapabilities(
                reasoning_method="chat_template_kwargs", evidence="offline fixture"
            ),
        )
        client = TokenFactoryClient(
            config=RuntimeConfig(models=models),
            transport=httpx.MockTransport(respond),
            max_http_retries=0,
        )
        self.client = client

        def close():
            self.closed = True
            client.close()

        return SimpleNamespace(router=LLMRouter(client), client=client, close=close)


def execute(upload, tmp_path, factory, *, source=None, patch_factory=None):
    options = {"runtime_factory": factory}
    if patch_factory is not None:
        options["patch_factory"] = patch_factory
    result = run_snapshot_diagnosis(
        SnapshotDiagnosisRequest(snapshot=upload, source=source),
        run_root=tmp_path / "jobs",
        run_id="a" * 32,
        services=SnapshotServices(**options),
    )
    projected = public_result(
        json.dumps(result, allow_nan=False),
        identifier=result["run_id"],
        status=result["status"],
    )
    assert "run_id" not in projected and "status" not in projected
    assert projected["verification"]["status"] == "not_run"
    assert projected["provenance"] == "offline_fixture"
    assert projected["cost_usd"] == result["cost_usd"]
    return result


def test_native_upload_reaches_real_validator_and_produces_bound_unverified_artifacts(
    upload, tmp_path, monkeypatch
):
    factory = OfflineRuntimeFactory()
    actual = core.validate_diagnosis
    validations = []

    def validate(*args, **kwargs):
        verdict = actual(*args, **kwargs)
        validations.append(verdict)
        return verdict

    monkeypatch.setattr(core, "validate_diagnosis", validate)
    result = execute(upload, tmp_path, factory)
    job = tmp_path / "jobs" / result["run_id"]
    assert result["status"] == "completed"
    assert result["provenance"] == "offline_fixture"
    assert len(validations) == 1 and validations[0].valid
    assert factory.closed and len(factory.requests) == 1
    assert factory.requests[0]["max_tokens"] == 2000
    system_messages = "\n".join(
        message["content"]
        for message in factory.requests[0]["messages"]
        if message["role"] == "system"
    )
    assert "2000-token completion cap" in system_messages
    assert "16384-token completion cap" not in system_messages
    assert factory.requests[0]["chat_template_kwargs"]["enable_thinking"] is False
    assert factory.requests[0]["model"] == ULTRA_MODEL
    assert result["verification"] == {
        "status": "not_run",
        "message": "Not run — bring the patch to your GPU",
    }
    assert result["patch"] == {"status": "unavailable", "diff": None}
    assert result["evidence"]["analysis"]["peak_is_exact"] is False
    binding = result["evidence"]["diagnosis_binding"]
    assert binding["snapshot_sha256"] == hashlib.sha256(upload.read_bytes()).hexdigest()
    assert binding["diagnosis_sha256"] == canonical_hash(result["diagnosis"])
    assert (
        binding["evidence_json_sha256"]
        == hashlib.sha256((job / "evidence.json").read_bytes()).hexdigest()
    )
    refs = {
        reference
        for cause in result["diagnosis"]["root_causes"]
        for reference in cause["evidence_refs"]
    }
    assert refs <= {stack["id"] for stack in result["evidence"]["stacks"]}
    assert json.loads((job / "diagnosis.json").read_text()) == result
    assert json.loads((job / "public-report.json").read_text()) == result
    markdown = (job / "diagnosis.md").read_text()
    assert "Unverified: not run on hardware" in markdown
    assert "offline_fixture" in markdown
    assert "The uploaded source was not run" in markdown
    assert result["cost_usd"] is None
    assert "Unknown." in markdown


def test_without_source_never_constructs_the_patch_engine(upload, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("A source-free snapshot cannot produce an applied patch draft")

    factory = OfflineRuntimeFactory()
    result = execute(upload, tmp_path, factory, patch_factory=forbidden)
    assert result["status"] == "completed"
    assert result["patch"]["status"] == "unavailable"
    assert not list((tmp_path / "jobs").rglob("patch.diff"))


def test_source_is_text_only_and_draft_is_still_not_hardware_verified(upload, tmp_path):
    sentinel = tmp_path / "SOURCE_MUST_NOT_RUN"
    source = tmp_path / "user_source.py"
    source.write_text(
        "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('ran')\n"
    )
    original = source.read_bytes()
    observed = []

    class Draft:
        def __init__(self, router, **limits):
            assert isinstance(router, LLMRouter)
            assert limits == {"max_repairs": 0, "max_completion_tokens": 2000}

        def generate_and_apply(self, source_root, step, **options):
            source_root = Path(source_root)
            assert (source_root / "train.py").read_bytes() == original
            assert options["source_files"] == ["train.py"]
            assert options["policy"]["allow_numerics_change"] is False
            assert options["context"]["hardware_verification"] == "not_run"
            assert options["context"]["input_kind"] == "uploaded_snapshot"
            assert step.fix_id == "p1"
            work = options["work_root"]
            work.mkdir(parents=True)
            path = work / "patch.diff"
            path.write_text("--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
            observed.append(path)
            return SimpleNamespace(applied=True, patch_path=path)

    factory = OfflineRuntimeFactory()
    result = execute(upload, tmp_path, factory, source=source, patch_factory=Draft)
    assert result["status"] == "completed" and len(observed) == 1
    assert result["patch"]["status"] == "unverified"
    assert result["verification"]["status"] == "not_run"
    assert result["provenance"] == "offline_fixture"
    assert not sentinel.exists()
    assert source.read_bytes() == original
    assert (tmp_path / "jobs" / result["run_id"] / "patch.diff").read_text() == result["patch"][
        "diff"
    ]
    assert (
        "unverified patch draft"
        in (tmp_path / "jobs" / result["run_id"] / "diagnosis.md").read_text()
    )


@pytest.mark.parametrize(
    "corruption", ["unknown_stack", "missing_fields", "invalid_json", "nonfinite"]
)
def test_invalid_provider_output_never_becomes_a_valid_diagnosis(upload, tmp_path, corruption):
    def mutate(payload):
        if corruption == "unknown_stack":
            payload["root_causes"][0]["evidence_refs"] = ["stk_" + "f" * 16]
        elif corruption == "missing_fields":
            payload.pop("verification")
        elif corruption == "invalid_json":
            return "{not-json"
        else:
            payload["root_causes"][0]["bytes_gb"] = float("nan")
        return payload

    factory = OfflineRuntimeFactory(mutate)
    result = execute(upload, tmp_path, factory)
    assert result["status"] in {"failed", "needs_human"}
    assert result["diagnosis"] is None
    assert result["evidence"]["diagnosis_binding"] is None
    assert result["patch"]["status"] == "unavailable"
    assert result["cost_usd"] is None
    assert factory.closed
    assert (tmp_path / "jobs" / result["run_id"] / "diagnosis.md").is_file()


def test_harmful_pickle_is_rejected_before_any_runtime_is_prepared(tmp_path):
    sentinel = tmp_path / "REDUCE_MUST_NOT_RUN"

    class Evil:
        def __reduce__(self):
            return os.system, ("touch " + str(sentinel),)

    upload = tmp_path / "evil.pickle"
    upload.write_bytes(pickle.dumps({"segments": [], "device_traces": [[]], "ignored": Evil()}))
    calls = []

    def forbidden(*args):
        calls.append(args)
        pytest.fail("Malicious pickle reached runtime preparation")

    result = execute(upload, tmp_path, forbidden)
    assert calls == []
    assert not sentinel.exists()
    assert result["status"] == "failed" and result["error"] == "snapshot_input_rejected"
    assert result["diagnosis"] is None
    assert result["cost_usd"] == 0.0  # Explicitly rejected before any runtime/dispatch.
    assert (tmp_path / "jobs" / result["run_id"] / "diagnosis.md").is_file()


@pytest.mark.parametrize("allowance", ["0.30001", "1", "0", "-0.01", "NaN", "Infinity"])
def test_request_cannot_exceed_the_existing_snapshot_allowance(upload, allowance):
    with pytest.raises((ValidationError, ValueError)):
        SnapshotDiagnosisRequest(snapshot=upload, budget_usd=allowance)


def test_runtime_refusal_keeps_readable_private_and_public_failure_artifacts(upload, tmp_path):
    def refused(*args):
        raise RuntimeNotReady("private provider profile detail must not appear in public output")

    result = execute(upload, tmp_path, refused)
    job = tmp_path / "jobs" / result["run_id"]
    assert result["status"] == "failed" and result["error"] == "runtime_unavailable"
    assert result["cost_usd"] == 0.0
    assert result["diagnosis"] is None
    assert result["evidence"]["diagnosis_binding"] is None
    assert (job / "private/calls.db").is_file()
    assert (job / "evidence.json").is_file()
    assert "private provider profile" not in json.dumps(result)
    assert "Diagnosis could not finish: runtime_unavailable" in (job / "diagnosis.md").read_text()


def test_private_store_and_fake_wire_receipt_stay_inside_the_job(upload, tmp_path):
    factory = OfflineRuntimeFactory()
    result = execute(upload, tmp_path, factory)
    job = tmp_path / "jobs" / result["run_id"]
    run_id, store_path, given_directory = factory.calls[0]
    assert run_id == result["run_id"] and given_directory == job
    assert store_path == job / "private/calls.db"
    assert store_path.stat().st_mode & 0o777 == 0o600
    assert (job / "private").stat().st_mode & 0o777 == 0o700
    assert (job / "private/offline-wire.json").is_file()
    assert list(tmp_path.rglob("calls.db")) == [store_path]
    store = Store(store_path)
    try:
        calls = store.llm_calls(run_id)
        assert len(calls) == 1
        assert calls[0]["cost_usd"] is None
        assert calls[0]["request_evidence"]["wire_payload"]["messages"]
    finally:
        store.close()
    for name in ("public-report.json", "diagnosis.json", "diagnosis.md"):
        text = (job / name).read_text()
        assert "wire_payload" not in text and "request_evidence" not in text
        assert str(store_path) not in text


def test_custom_patch_factory_without_explicit_offline_runtime_is_rejected(upload, tmp_path):
    with pytest.raises(ValueError, match="explicit offline runtime"):
        run_snapshot_diagnosis(
            SnapshotDiagnosisRequest(snapshot=upload),
            run_root=tmp_path / "jobs",
            services=SnapshotServices(patch_factory=lambda *args: None),
        )


def test_no_allocation_stacks_stop_before_runtime_preparation(tmp_path):
    upload = tmp_path / "no-stacks.pickle"
    upload.write_bytes(pickle.dumps({"segments": [], "device_traces": [[]]}))
    calls = []

    def forbidden(*args):
        calls.append(args)
        pytest.fail("A capture with no usable allocation stack reached runtime preparation")

    result = execute(upload, tmp_path, forbidden)
    assert calls == []
    assert result["status"] in {"failed", "needs_human"}
    assert result["diagnosis"] is None
    assert result["cost_usd"] == 0.0


def test_schema_only_advertises_visible_stack_references(upload, tmp_path):
    capture = native_snapshot()
    blocks, allocations = [], []
    for index in range(70):
        frame = [{"filename": "/untrusted/train.py", "line": index + 1, "name": "forward"}]
        address = 4096 + index * 512
        blocks.append(
            {
                "address": address,
                "size": 512,
                "requested_size": 512,
                "state": "active_allocated",
                "frames": frame,
            }
        )
        allocations.append(
            {"action": "alloc", "addr": address, "size": 512, "stream": 0, "frames": frame}
        )
    capture["segments"][0].update(total_size=70 * 512, blocks=blocks)
    capture["device_traces"] = [
        [
            {"action": "segment_alloc", "addr": 4096, "size": 70 * 512, "stream": 0},
            *allocations,
        ]
    ]
    upload.write_bytes(pickle.dumps(capture))
    hidden = []

    def mutate(payload):
        evidence = json.loads((tmp_path / "jobs" / ("a" * 32) / "evidence.json").read_text())
        visible = set(evidence["presentation"]["stack_ids"])
        absent = set(evidence["analysis"]["stack_catalog"]) - visible
        assert absent
        hidden.append(min(absent))
        payload["root_causes"][0]["evidence_refs"] = hidden
        return payload

    factory = OfflineRuntimeFactory(mutate)
    result = execute(upload, tmp_path, factory)
    assert result["status"] in {"failed", "needs_human"}
    assert result["diagnosis"] is None
    schema_message = factory.requests[0]["messages"][0]["content"]
    schema = json.loads(schema_message.splitlines()[1])
    allowed = schema["$defs"]["RootCause"]["properties"]["evidence_refs"]["items"]["enum"]
    assert hidden[0] not in allowed


def test_api_projection_rejects_a_different_job_identity_or_registry_status(upload, tmp_path):
    result = execute(upload, tmp_path, OfflineRuntimeFactory())
    raw = json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="identity"):
        public_result(raw, identifier="b" * 32, status=result["status"])
    with pytest.raises(ValueError, match="identity"):
        public_result(raw, identifier=result["run_id"], status="failed")


def test_needs_more_information_remains_a_bound_diagnosis_without_a_patch(upload, tmp_path):
    def mutate(payload):
        payload["needs_more_info"] = True
        payload["notes"].append("Source semantics were not established.")
        return payload

    result = execute(upload, tmp_path, OfflineRuntimeFactory(mutate))
    assert result["status"] == "needs_human"
    assert result["diagnosis"]["needs_more_info"] is True
    assert result["evidence"]["diagnosis_binding"]["diagnosis_sha256"] == canonical_hash(
        result["diagnosis"]
    )
    assert result["patch"] == {"status": "unavailable", "diff": None}
    assert result["cost_usd"] is None


def test_model_budget_refusal_is_projectable_and_does_not_claim_a_provider_charge(upload, tmp_path):
    def refused(*args):
        raise BudgetExceeded("private budget amount must not appear in public output")

    result = execute(upload, tmp_path, refused)
    assert result["status"] == "budget_exceeded"
    assert result["error"] == "budget_exceeded"
    assert result["cost_usd"] == 0.0
    assert "private budget amount" not in json.dumps(result)
    assert result["verification"]["status"] == "not_run"


def test_rejected_patch_draft_keeps_the_diagnosis_and_no_downloadable_patch(upload, tmp_path):
    source = tmp_path / "text_only.py"
    source.write_text("raise AssertionError('source must not run')\\n")

    class RejectDraft:
        def __init__(self, *args, **kwargs):
            pass

        def generate_and_apply(self, *args, **kwargs):
            return SimpleNamespace(applied=False, patch_path=None)

    result = execute(
        upload, tmp_path, OfflineRuntimeFactory(), source=source, patch_factory=RejectDraft
    )
    assert result["diagnosis"] is not None
    assert result["patch"] == {"status": "unavailable", "diff": None}
    assert not (tmp_path / "jobs" / result["run_id"] / "patch.diff").exists()
    assert result["verification"]["status"] == "not_run"


@pytest.mark.parametrize(
    "private_path",
    [
        "/home/offline-person/project/train.py",
        "/Users/offline-person/project/train.py",
        "/Users/offline person/project/train.py",
        "/private/var/tmp/offline-person/train.py",
        "C:" + chr(92) + "Users" + chr(92) + "offline-person" + chr(92) + "train.py",
    ],
)
def test_public_paths_are_redacted_before_hashing_but_private_evidence_is_preserved(
    upload, tmp_path, private_path
):
    capture = native_snapshot()
    capture["segments"][0]["blocks"][0]["frames"][0]["filename"] = private_path
    upload.write_bytes(pickle.dumps(capture))

    def mutate(payload):
        payload["notes"].append("Inspect source at " + private_path)
        payload["plan"][0]["description"] += " Source: " + private_path
        return payload

    result = execute(upload, tmp_path, OfflineRuntimeFactory(mutate))
    assert result["status"] == "completed"
    public = json.dumps(result)
    assert private_path not in public
    assert "[path]/train.py" in result["diagnosis"]["notes"][-1]
    binding = result["evidence"]["diagnosis_binding"]
    assert binding["diagnosis_sha256"] == canonical_hash(result["diagnosis"])
    assert all(
        private_path != frame["filename"]
        for stack in result["evidence"]["stacks"]
        for frame in stack["frames"]
    )
    job = tmp_path / "jobs" / result["run_id"]
    original_evidence = json.loads((job / "evidence.json").read_text())
    assert any(
        frame["filename"] == private_path
        for frames in original_evidence["analysis"]["stack_catalog"].values()
        for frame in frames
    )
    private_diagnosis = json.loads((job / "private/diagnosis-validation.json").read_text())
    assert private_path in private_diagnosis["diagnosis"]["notes"][-1]
    assert private_path not in (job / "diagnosis.md").read_text()


def test_runtime_close_failure_still_writes_projectable_readable_outputs(upload, tmp_path):
    original = OfflineRuntimeFactory()

    def factory(*args):
        runtime = original(*args)
        real_close = runtime.close

        def broken_close():
            real_close()
            raise OSError("private close failure /home/offline-person/private-file")

        runtime.close = broken_close
        return runtime

    result = execute(upload, tmp_path, factory)
    assert result["status"] == "failed" and result["error"] == "worker_error"
    assert result["diagnosis"] is not None
    assert result["cost_usd"] is None
    assert original.closed
    job = tmp_path / "jobs" / result["run_id"]
    for name in ("public-report.json", "diagnosis.json", "diagnosis.md"):
        assert (job / name).is_file()
        assert "private close failure" not in (job / name).read_text()
        assert "/home/offline-person" not in (job / name).read_text()
    cleanup = json.loads((job / "private/cleanup-failures.json").read_text())
    assert cleanup == {"steps": ["runtime_close"]}
    assert "Unverified: not run on hardware" in (job / "diagnosis.md").read_text()


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            (
                "Change /home/offline-person/model.py, keep the original loss normalization; "
                "compare /home/offline-person/reference.py."
            ),
            (
                "Change [path]/model.py, keep the original loss normalization; "
                "compare [path]/reference.py."
            ),
        ),
        (
            (
                "Change /Users/offline person/model.py and preserve the batch in "
                "/Users/offline person/reference.py"
            ),
            "Change [path]/model.py and preserve the batch in [path]/reference.py",
        ),
        (
            (
                r"Compare C:\Users\offline person\model.py with "
                r"C:\Users\offline person\reference.py; keep weighting unchanged."
            ),
            "Compare [path]/model.py with [path]/reference.py; keep weighting unchanged.",
        ),
    ],
)
def test_path_redaction_preserves_interleaved_repair_constraints(
    upload, tmp_path, description, expected
):
    def mutate(payload):
        payload["plan"][0]["description"] = description
        return payload

    result = execute(upload, tmp_path, OfflineRuntimeFactory(mutate))
    assert result["status"] == "completed"
    assert result["diagnosis"]["plan"][0]["description"] == expected
    binding = result["evidence"]["diagnosis_binding"]
    assert binding["diagnosis_sha256"] == canonical_hash(result["diagnosis"])
    job = tmp_path / "jobs" / result["run_id"]
    assert expected in (job / "diagnosis.md").read_text()


@pytest.mark.parametrize(
    ("mutate", "finish_reason", "reason"),
    [
        (lambda payload: "{not-json", "stop", "invalid_json"),
        (lambda payload: payload, "length", "truncated"),
        (lambda payload: {"unexpected": "field"}, "stop", "schema_mismatch"),
    ],
)
def test_snapshot_model_failures_keep_private_response_evidence_without_retry(
    upload, tmp_path, mutate, finish_reason, reason
):
    factory = OfflineRuntimeFactory(mutate, finish_reason=finish_reason)
    result = execute(upload, tmp_path, factory)
    job = tmp_path / "jobs" / result["run_id"]
    receipt = job / "private" / "model-error.json"
    saved = json.loads(receipt.read_text())
    assert result["status"] == "failed" and result["error"] == "diagnosis_unavailable"
    assert result["diagnosis"] is None and result["patch"]["diff"] is None
    assert len(factory.requests) == 1 and factory.closed
    assert saved["error_type"] == "ResponseValidationError"
    assert saved["error_reason"] == reason and saved["finish_reason"] == finish_reason
    assert saved["phase"] == "diagnose" and saved["usage"]["completion_tokens"] == 100
    response = saved["response"]
    assert response["utf8_bytes"] > 0 and not response["excerpt_truncated"]
    assert response["sha256"] == hashlib.sha256(response["text_excerpt"].encode()).hexdigest()
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert receipt.parent.stat().st_mode & 0o777 == 0o700
    assert "model-error.json" not in (job / "public-report.json").read_text()
    assert json.loads((job / "private" / "cleanup.json").read_text())["cleanup_verified"]


def test_untrusted_error_and_response_are_never_copied_to_public_outputs(upload, tmp_path):
    marker = "private-offline-marker"
    response_text = marker + "é" * (core._PRIVATE_RESPONSE_BYTES + 100)
    original = OfflineRuntimeFactory()

    def factory(*args):
        runtime = original(*args)

        def rejected(*args, **kwargs):
            raise ResponseValidationError(
                marker + " arbitrary exception text",
                reason=marker,
                response=SimpleNamespace(
                    text=response_text, finish_reason=marker, role=marker, usage=None
                ),
            )

        runtime.router.chat = rejected
        return runtime

    result = execute(upload, tmp_path, factory)
    job = tmp_path / "jobs" / result["run_id"]
    saved = json.loads((job / "private/model-error.json").read_text())
    assert saved["error_reason"] == "unknown"
    assert saved["finish_reason"] is None and saved["role"] is None
    response = saved["response"]
    assert response["excerpt_truncated"]
    assert len(response["text_excerpt"].encode()) <= core._PRIVATE_RESPONSE_BYTES
    assert response["sha256"] == hashlib.sha256(response_text.encode()).hexdigest()
    assert (
        saved["exception_sha256"]
        == hashlib.sha256((marker + " arbitrary exception text").encode()).hexdigest()
    )
    for name in ["public-report.json", "diagnosis.json", "diagnosis.md"]:
        assert marker not in (job / name).read_text()
    assert marker not in json.dumps(result)
    assert original.closed


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("Token Factory HTTP 503; attempts=1", "http_error"),
        ("Token Factory timeout; attempts=1", "timeout"),
        ("Token Factory returned a refusal", "refusal"),
        ("private-offline-marker arbitrary exception", "unclassified_llm_error"),
    ],
)
def test_snapshot_client_error_records_only_safe_reason(upload, tmp_path, message, reason):
    def refused(*args):
        raise LLMError(message)

    result = execute(upload, tmp_path, refused)
    job = tmp_path / "jobs" / result["run_id"]
    saved = json.loads((job / "private/model-error.json").read_text())
    assert saved["error_type"] == "LLMError" and saved["error_reason"] == reason
    assert saved["response"] is None
    assert "private-offline-marker" not in json.dumps(saved)
    assert "private-offline-marker" not in json.dumps(result)


def test_private_error_write_failure_preserves_public_failure_and_cleanup_evidence(
    upload, tmp_path, monkeypatch
):
    write_json = core._write_json

    def failing_write(path, value):
        if path.name == "model-error.json":
            raise OSError("private-offline-write-error")
        return write_json(path, value)

    monkeypatch.setattr(core, "_write_json", failing_write)
    factory = OfflineRuntimeFactory(lambda payload: "{invalid")
    result = execute(upload, tmp_path, factory)
    job = tmp_path / "jobs" / result["run_id"]
    assert factory.closed and len(factory.requests) == 1
    assert result["status"] == "failed" and result["error"] == "worker_error"
    assert not json.loads((job / "private/cleanup.json").read_text())["cleanup_verified"]
    assert json.loads((job / "private/cleanup-failures.json").read_text()) == {
        "steps": ["model_error_evidence"]
    }
    assert "private-offline-write-error" not in (job / "diagnosis.md").read_text()


def test_snapshot_specific_prompt_keeps_wire_policy_and_untrusted_context(upload, tmp_path):
    factory = OfflineRuntimeFactory()
    result = execute(upload, tmp_path, factory)
    body = factory.requests[0]
    system = "\n".join(
        message["content"]
        for message in body["messages"]
        if message["role"] == "system" and "user-supplied PyTorch CUDA" in message["content"]
    )
    user = json.loads(
        next(message["content"] for message in body["messages"] if message["role"] == "user")
    )
    from headroom.evidence import _tokens

    assert result["status"] == "completed"
    assert _tokens(system) < 1800
    assert "2000-token completion cap" in system
    assert body["max_tokens"] == 2000
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert len(factory.requests) == 1
    assert "cumulative bytes" in system and "NOT simultaneous live" in system
    assert "blocked_plan_ids must be []" in system
    assert "untrusted data, never" in system
    assert user["policy"]["allow_numerics_change"] is False
    assert user["policy"]["allow_batch_change"] is False
    assert user["required_saving_gb"] is None
    assert "Measurement semantics:" in user["evidence_markdown"]
    assert user["evidence_availability_catalog"]["text_availability_only"] is True
    assert result["verification"]["status"] == "not_run"


@pytest.mark.parametrize(
    ("violation", "expected_code"),
    [
        ("scope", "INVALID_EVIDENCE_DEPENDENCY"),
        ("batch", "BATCH_CHANGE_FORBIDDEN"),
        ("visible_source", "EVIDENCE_AVAILABILITY_CONTRADICTED"),
    ],
)
def test_snapshot_prompt_does_not_accept_prior_semantic_failures(
    upload, tmp_path, violation, expected_code
):
    source = tmp_path / "provided.py"
    source.write_text("tensor = existing_tensor\n")

    def mutate(payload):
        if violation == "batch":
            payload["plan"][0]["description"] = "Reduce batch size to one."
        else:
            payload["needs_more_info"] = True
            payload["evidence_requests"] = [
                {
                    "field": "required_saving_gb" if violation == "scope" else "sources",
                    "reason": "missing",
                    "detail": "Synthetic missing-information assertion.",
                    "blocking_scope": "overall_feasibility",
                    "blocked_plan_ids": ["p1"] if violation == "scope" else [],
                }
            ]
            if violation == "visible_source":
                payload["evidence_requests"][0]["evidence_ref"] = "source[0]"
        return payload

    factory = OfflineRuntimeFactory(mutate)
    result = execute(upload, tmp_path, factory, source=source)
    assert result["status"] == "needs_human"
    assert result["diagnosis"] is None and result["patch"]["diff"] is None
    assert len(factory.requests) == 1
    saved = json.loads(
        (tmp_path / "jobs" / result["run_id"] / "private/diagnosis-validation.json").read_text()
    )
    assert expected_code in {issue["code"] for issue in saved["issues"]}


def test_snapshot_disallowed_numerics_still_fails_schema_without_retry(upload, tmp_path):
    def mutate(payload):
        payload["plan"][0]["numerics_impact"] = "minor"
        return payload

    factory = OfflineRuntimeFactory(mutate)
    result = execute(upload, tmp_path, factory)
    assert result["status"] == "failed" and result["diagnosis"] is None
    assert len(factory.requests) == 1
    error = json.loads(
        (tmp_path / "jobs" / result["run_id"] / "private/model-error.json").read_text()
    )
    assert error["error_reason"] == "schema_mismatch"


def test_snapshot_valid_diagnosis_can_keep_genuine_unknown_without_patch(upload, tmp_path):
    def mutate(payload):
        payload["plan"] = []
        payload["needs_more_info"] = True
        payload["evidence_requests"] = [
            {
                "field": "source",
                "reason": "missing",
                "detail": "Source text is required before suggesting an edit.",
                "blocking_scope": "overall_feasibility",
                "blocked_plan_ids": [],
            }
        ]
        return payload

    factory = OfflineRuntimeFactory(mutate)
    result = execute(upload, tmp_path, factory)
    assert result["status"] == "needs_human"
    assert result["diagnosis"] is not None
    assert result["diagnosis"]["needs_more_info"] is True
    assert result["diagnosis"]["plan"] == []
    assert result["patch"]["status"] == "unavailable"
    assert result["verification"]["status"] == "not_run"
    assert len(factory.requests) == 1
