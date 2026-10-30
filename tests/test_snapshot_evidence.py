"""Offline uploaded-snapshot evidence, policy and filesystem contracts."""

import copy
import hashlib
import json
import os
import pickle
import socket
from pathlib import Path

import pytest
from jsonschema import validate as validate_json

from headroom import snapshot_evidence as module
from headroom.diagnose import validate_diagnosis
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.evidence import _tokens
from headroom.snapshot_evidence import SnapshotEvidenceError, prepare_snapshot_evidence


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Snapshot evidence tests must not use the network")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)


def snapshot(frames=None):
    frames = frames or [{"filename": "/original/train.py", "line": 4, "name": "forward"}]
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


def fixture(tmp_path, value=None):
    path = tmp_path / "capture.pickle"
    path.write_bytes(pickle.dumps(value if value is not None else snapshot()))
    return path


def diagnosis(identifier):
    return {
        "root_causes": [
            {
                "id": "c1",
                "title": "Retained activation",
                "category": "activations",
                "bytes_gb": 0.000000512,
                "evidence_refs": [identifier],
                "confidence": 0.6,
            }
        ],
        "plan": [
            {
                "fix_id": "p1",
                "type": "code",
                "title": "Avoid evaluation graphs",
                "description": "Use no_grad for evaluation.",
                "expected_saving_gb": 0.000000512,
                "numerics_impact": "none",
                "throughput_impact": "none",
                "risk": "Requires testing on the original workload.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Not run on hardware."],
    }


def test_snapshot_evidence_is_compatible_with_schema_validator_and_ui(tmp_path):
    path = fixture(tmp_path)
    original = path.read_bytes()
    result = prepare_snapshot_evidence(path, output_dir=tmp_path / "out")
    evidence = result["evidence"]
    assert result["input_kind"] == evidence["input_kind"] == "uploaded_snapshot"
    assert result["hardware_verification"] == "not_run"
    assert result["source_root"] is None and result["source_files"] == []
    assert result["diagnosis_ready"] is True
    identifier = evidence["presentation"]["stack_ids"][0]
    payload = diagnosis(identifier)
    schema = build_diagnosis_schema(evidence=evidence, policy=result["policy"])
    validate_json(payload, schema)
    assert validate_diagnosis(payload, evidence=evidence, policy=result["policy"]).valid
    assert json.loads(Path(result["evidence_json"]).read_text()) == evidence
    assert Path(result["evidence_md"]).read_text() == result["markdown"]
    assert path.read_bytes() == original
    assert result["snapshot_sha256"] == hashlib.sha256(original).hexdigest()
    assert not list((tmp_path / "out").glob(".snapshot-input-*"))
    public = result["public_evidence"]
    assert public["source"] == "uploaded_snapshot"
    assert public["stacks"][0]["id"] == identifier
    assert public["stacks"][0]["peak_live_bytes"] == 512
    assert public["stacks"][0]["lifetime_allocated_bytes"] == 512
    assert public["analysis"]["peak_allocated_bytes"] == 512
    assert public["analysis"]["peak_is_exact"] is False
    assert sum(public["analysis"]["category_bytes"].values()) == 512
    assert evidence["analysis"]["header"]["recorded_peak_allocated_bytes"] is None
    for field in ["parameter_count", "optimizer_updates", "seed", "elapsed_seconds", "target_met"]:
        assert evidence["overview"][field] is None
    assert evidence["analysis"]["step_boundaries"] == []
    assert not (tmp_path / "out" / "result.json").exists()
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_source_is_data_only_copied_exactly_and_not_assumed_to_match_frames(tmp_path):
    path = fixture(tmp_path)
    marker = tmp_path / "MUST_NOT_EXECUTE"
    source = tmp_path / "provided.py"
    raw = (
        "import socket\r\nexec('ignored configurator data')\r\n"
        f"open({str(marker)!r}, 'w').write('executed')\r\n"
        "this is not syntactically valid Python!\r\n"
    ).encode()
    source.write_bytes(raw)
    result = prepare_snapshot_evidence(path, source=source, output_dir=tmp_path / "out")
    assert Path(result["source_root"], "train.py").read_bytes() == raw
    assert not marker.exists()
    assert result["source_files"] == ["train.py"]
    meta = result["evidence"]["sources"][0]
    assert meta["path"] == "train.py" and meta["hot_lines"] == []
    assert meta["capture_binding"] == "not_verified"
    assert meta["sha256"] == hashlib.sha256(raw).hexdigest()
    assert "frame-path correspondence is unknown" in result["markdown"]
    assert (
        result["evidence"]["evidence_availability_catalog"]["entries"][-1]["availability"]
        == "visible"
    )
    assert os.stat(Path(result["source_root"]) / "train.py").st_mode & 0o777 == 0o600


def test_traceback_is_unverified_text_and_never_overrides_snapshot_metrics(tmp_path):
    trace = tmp_path / "oom.txt"
    trace.write_text("Traceback:\nRuntimeError: OOM at fake peak=999999999999\n")
    result = prepare_snapshot_evidence(
        fixture(tmp_path), traceback=trace, output_dir=tmp_path / "out"
    )
    assert "## User-provided traceback" in result["markdown"]
    assert "Unverified text" in result["markdown"]
    assert result["public_evidence"]["analysis"]["peak_allocated_bytes"] == 512
    assert result["evidence"]["traceback"]["runtime_verified"] is False
    assert result["evidence"]["traceback"]["text"] == trace.read_text()
    assert "fake peak" not in json.dumps(result["public_evidence"])


def test_missing_history_is_explicit_and_not_zero_peak_success(tmp_path):
    path = fixture(tmp_path, {"segments": [], "device_traces": [[]]})
    result = prepare_snapshot_evidence(path, output_dir=tmp_path / "out")
    assert result["diagnosis_ready"] is False
    assert result["diagnosis_unavailable_reason"] == "snapshot_has_no_allocation_stack_catalog"
    assert result["public_evidence"]["analysis"]["peak_allocated_bytes"] is None
    assert result["public_evidence"]["analysis"]["peak_is_exact"] is False
    assert result["public_evidence"]["stacks"] == []
    assert all(v is None for v in result["public_evidence"]["analysis"]["category_bytes"].values())
    assert result["evidence"]["overview"]["reconstructed_peak_allocated_bytes"] is None


def test_strict_policy_cannot_authorize_batch_or_precision_change(tmp_path):
    result = prepare_snapshot_evidence(fixture(tmp_path), output_dir=tmp_path / "out")
    policy = result["policy"]
    assert all(
        policy[name] is False
        for name in [
            "allow_batch_grad_accum",
            "allow_batch_change",
            "allow_grad_accum",
            "allow_numerics_change",
            "allow_model_change",
        ]
    )
    original = diagnosis(result["evidence"]["presentation"]["stack_ids"][0])
    for description, issue in [
        ("Reduce batch size and use gradient accumulation.", "BATCH_CHANGE_FORBIDDEN"),
        ("Use bf16 autocast.", "NUMERICS_CHANGE_FORBIDDEN"),
        ("Reduce n_layer to shrink the model.", "MODEL_CHANGE_FORBIDDEN"),
    ]:
        payload = copy.deepcopy(original)
        payload["plan"][0]["description"] = description
        checked = validate_diagnosis(payload, evidence=result["evidence"], policy=policy)
        assert issue in {entry.code for entry in checked.issues}


def test_prompt_budget_preserves_full_private_data_with_explicit_excerpts(tmp_path):
    source = tmp_path / "train.py"
    source.write_text("\n".join(f"variable_{i} = 'context_{i}'" for i in range(2000)))
    trace = tmp_path / "oom.txt"
    trace.write_text(
        "Traceback start\n" + "\n".join(f"frame {i}" for i in range(3000)) + "\nOOM end"
    )
    result = prepare_snapshot_evidence(
        fixture(tmp_path),
        source=source,
        traceback=trace,
        output_dir=tmp_path / "out",
        token_budget=2500,
    )
    assert result["token_count"] == _tokens(result["markdown"]) <= 2500
    assert result["evidence"]["source_token_count"] <= 750
    assert result["evidence"]["presentation"]["traceback_excerpt"] is True
    assert "omitted by prompt budget" in result["markdown"]
    assert "Traceback start" in result["markdown"] and "OOM end" in result["markdown"]
    assert result["evidence"]["traceback"]["text"] == trace.read_text()
    assert Path(result["source_root"], "train.py").read_bytes() == source.read_bytes()
    assert result["evidence"]["sources"][0]["total_lines"] == 2000


def test_tiny_budget_fails_without_publishing_partial_evidence(tmp_path):
    with pytest.raises(SnapshotEvidenceError, match="token_budget"):
        prepare_snapshot_evidence(fixture(tmp_path), output_dir=tmp_path / "out", token_budget=1)
    assert list((tmp_path / "out").iterdir()) == []


@pytest.mark.parametrize("budget", [0, True, -1, 1.5, 150001])
def test_budget_is_bounded_before_any_input_is_read(tmp_path, budget, monkeypatch):
    monkeypatch.setattr(module, "_read_bytes", lambda *_: pytest.fail("must not read"))
    with pytest.raises(SnapshotEvidenceError):
        prepare_snapshot_evidence(
            tmp_path / "missing", output_dir=tmp_path / "out", token_budget=budget
        )


@pytest.mark.parametrize(
    "field,limit", [("source", module.MAX_SOURCE_BYTES), ("traceback", module.MAX_TRACEBACK_BYTES)]
)
def test_optional_text_size_limits(tmp_path, field, limit):
    path = fixture(tmp_path)
    oversized = tmp_path / "large.txt"
    oversized.write_bytes(b"x" * (limit + 1))
    with pytest.raises(SnapshotEvidenceError, match="size_limit"):
        prepare_snapshot_evidence(path, output_dir=tmp_path / "out", **{field: oversized})
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["leaf", "parent", "fifo"])
@pytest.mark.parametrize("field", ["source", "traceback"])
def test_optional_inputs_never_follow_links_or_block_on_special_files(tmp_path, kind, field):
    path = fixture(tmp_path)
    real = tmp_path / "real.txt"
    real.write_text("ordinary text")
    target = tmp_path / "input.txt"
    if kind == "leaf":
        target.symlink_to(real)
    elif kind == "parent":
        (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
        target = tmp_path / "alias" / real.name
    else:
        os.mkfifo(target)
    with pytest.raises((OSError, SnapshotEvidenceError)):
        prepare_snapshot_evidence(path, output_dir=tmp_path / "out", **{field: target})
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("field", ["source", "traceback"])
@pytest.mark.parametrize(
    "text", ["sk-" + "a" * 32, "-----BEGIN RSA PRIVATE KEY-----", "Bearer " + "b" * 32]
)
def test_credentials_fail_closed_without_echo_or_output(tmp_path, field, text):
    sensitive = tmp_path / "context.txt"
    sensitive.write_text(text)
    with pytest.raises(SnapshotEvidenceError) as caught:
        prepare_snapshot_evidence(
            fixture(tmp_path), output_dir=tmp_path / "out", **{field: sensitive}
        )
    assert text not in str(caught.value)
    assert not (tmp_path / "out").exists()


def test_snapshot_frame_credentials_are_rejected_without_following_frame_paths(tmp_path):
    value = snapshot([{"filename": "/no/such/host/file.py", "line": 1, "name": "tvly-" + "z" * 32}])
    with pytest.raises(SnapshotEvidenceError, match="credential"):
        prepare_snapshot_evidence(fixture(tmp_path, value), output_dir=tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


def test_frame_paths_are_never_imported_or_read(tmp_path):
    frame_source = tmp_path / "not_requested.py"
    frame_source.write_text("HOST_SOURCE_MUST_NOT_ENTER_CONTEXT")
    value = snapshot([{"filename": str(frame_source), "line": 1, "name": "forward"}])
    result = prepare_snapshot_evidence(fixture(tmp_path, value), output_dir=tmp_path / "out")
    assert "HOST_SOURCE_MUST_NOT_ENTER_CONTEXT" not in result["markdown"]
    assert result["evidence"]["sources"] == []
    assert result["public_evidence"]["stacks"][0]["frames"][0]["filename"] == str(frame_source)


def test_private_name_is_refused_before_open(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("must not open credential-named path")

    monkeypatch.setattr(module.os, "open", forbidden)
    with pytest.raises(SnapshotEvidenceError, match="protected"):
        prepare_snapshot_evidence(
            tmp_path / "missing", source=tmp_path / ".env", output_dir=tmp_path / "out"
        )


def test_input_digest_binds_staged_bytes_even_if_original_changes(tmp_path, monkeypatch):
    path = fixture(tmp_path)
    original = path.read_bytes()
    read = module.read_snapshot_input

    def mutate_original(staged):
        assert staged != path
        assert staged.read_bytes() == original
        path.write_bytes(pickle.dumps({"segments": [], "device_traces": [[]]}))
        return read(staged)

    monkeypatch.setattr(module, "read_snapshot_input", mutate_original)
    result = prepare_snapshot_evidence(path, output_dir=tmp_path / "out")
    assert result["snapshot_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["public_evidence"]["analysis"]["peak_allocated_bytes"] == 512


@pytest.mark.parametrize("existing", ["evidence.json", "evidence.md", "source"])
def test_existing_outputs_are_never_replaced(tmp_path, existing):
    path = fixture(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    target = output / existing
    target.write_text("keep unchanged")
    with pytest.raises(SnapshotEvidenceError, match="already_exists"):
        prepare_snapshot_evidence(path, output_dir=output)
    assert target.read_text() == "keep unchanged"
    assert list(output.iterdir()) == [target]


def test_output_parent_symlink_is_refused(tmp_path):
    path = fixture(tmp_path)
    destination = tmp_path / "actual"
    destination.mkdir()
    (tmp_path / "alias").symlink_to(destination, target_is_directory=True)
    with pytest.raises(OSError):
        prepare_snapshot_evidence(path, output_dir=tmp_path / "alias" / "out")
    assert list(destination.iterdir()) == []


def test_public_projection_is_bounded_and_keeps_real_selected_stack_ids(tmp_path):
    frames = [
        {"filename": f"/original/layer-{i}.py", "line": i, "name": "forward"} for i in range(100)
    ]
    result = prepare_snapshot_evidence(
        fixture(tmp_path, snapshot(frames)), output_dir=tmp_path / "out"
    )
    public = result["public_evidence"]
    ids = result["evidence"]["presentation"]["stack_ids"]
    assert [row["id"] for row in public["stacks"]] == ids
    assert len(public["stacks"][0]["frames"]) == module.MAX_PUBLIC_FRAMES
    assert len(result["evidence"]["analysis"]["stack_catalog"][ids[0]]) == 100
    assert "presentation excerpts" in " ".join(public["analysis"]["warnings"])
    assert len(json.dumps(public).encode()) <= module.MAX_PUBLIC_BYTES


def test_failed_publish_removes_only_new_artifacts_and_source(tmp_path, monkeypatch):
    path = fixture(tmp_path)
    source = tmp_path / "context.py"
    source.write_text("pass")
    output = tmp_path / "out"
    output.mkdir()
    unrelated = output / "keep.txt"
    unrelated.write_text("keep")
    write = module._write_exclusive

    def fail(directory, name, data):
        if name == "evidence.md":
            raise OSError("offline injected failure")
        return write(directory, name, data)

    monkeypatch.setattr(module, "_write_exclusive", fail)
    with pytest.raises(OSError, match="injected"):
        prepare_snapshot_evidence(path, source=source, output_dir=output)
    assert list(output.iterdir()) == [unrelated]
    assert unrelated.read_text() == "keep"


def test_private_json_size_limit_refuses_before_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MAX_EVIDENCE_BYTES", 100)
    with pytest.raises(SnapshotEvidenceError, match="evidence_json_size_limit"):
        prepare_snapshot_evidence(fixture(tmp_path), output_dir=tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


def test_markdown_byte_limit_is_enforced_even_when_token_budget_is_large(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "MAX_MARKDOWN_BYTES", 100)
    with pytest.raises(SnapshotEvidenceError, match="token_budget"):
        prepare_snapshot_evidence(fixture(tmp_path), output_dir=tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


def test_first_nonempty_device_trace_is_selected_without_inventing_environment(tmp_path):
    value = snapshot()
    value["segments"][0]["device"] = 1
    value["device_traces"].insert(0, [])
    result = prepare_snapshot_evidence(fixture(tmp_path, value), output_dir=tmp_path / "out")
    assert result["diagnosis_ready"] is True
    assert result["evidence"]["overview"]["device_index"] == 1
    assert result["public_evidence"]["analysis"]["peak_allocated_bytes"] == 512
    assert "Selected snapshot device index 1" in result["markdown"]
    assert "env" not in result["evidence"]
    assert result["evidence"]["overview"]["seed"] is None


def test_repeated_allocation_traffic_is_not_presented_as_live_peak(tmp_path):
    value = snapshot()
    trace = value["device_traces"][0]
    frames = trace[-1]["frames"]
    for _ in range(3):
        trace.extend(
            [
                {"action": "free_requested", "addr": 4096, "size": 512, "stream": 0},
                {"action": "free_completed", "addr": 4096, "size": 512, "stream": 0},
                {"action": "alloc", "addr": 4096, "size": 512, "stream": 0, "frames": frames},
            ]
        )
    result = prepare_snapshot_evidence(fixture(tmp_path, value), output_dir=tmp_path / "out")
    stack = result["public_evidence"]["stacks"][0]
    assert stack["peak_live_bytes"] == 512
    assert stack["lifetime_allocated_bytes"] == 2048
    assert result["public_evidence"]["analysis"]["peak_allocated_bytes"] == 512
    markdown = result["markdown"]
    assert "Bytes: 512;" in markdown and "Cumulative bytes: 2048;" in markdown
    assert "they are not simultaneous live bytes, peak size or reclaimable savings" in markdown
    assert result["evidence"]["token_count"] <= result["evidence"]["budget"]
