"""Offline prompt-budget and source trust-boundary checks."""

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.evidence import (
    _read_source,
    _sample_timeline,
    _tokens,
    build_evidence,
    collect_sources,
)


def analysis_fixture():
    stacks = [
        {
            "stack_id": f"stk_{index:03d}",
            "category": "activations",
            "bytes": 1024 + index,
            "blocks": 1,
            "allocations": 3,
            "short_lived_bytes": 16,
            "frames": [
                {"filename": "/source/train.py", "line": 3, "name": "train"},
                {
                    "filename": "/opt/venv/torch/autograd/__init__.py",
                    "line": 42,
                    "name": "backward",
                },
            ],
        }
        for index in range(80)
    ]
    return {
        "header": {
            "peak_allocated_bytes": 100000,
            "peak_reserved_bytes": 200000,
            "oom_requested_bytes": 123456,
            "fragmentation_confirmed": False,
            "history_complete": False,
            "warnings": ["History prefix is missing."],
        },
        "timeline": [
            {
                "event_index": index,
                "allocated_bytes": 100000 - index,
                "reserved_bytes": 200000,
                "is_oom": index == 160,
            }
            for index in range(200)
        ],
        "peak_composition": copy.deepcopy(stacks),
        "allocation_hot_paths": copy.deepcopy(stacks),
        "stack_catalog": {row["stack_id"]: row["frames"] for row in stacks},
        "peak_event_index": 0,
        "oom_events": [{"event_index": 160, "size": 123456}],
        "category_bytes": {"activations": 100000},
        "coverage": {"trace_events_total": 200},
    }


@pytest.fixture
def captured_run(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "source").mkdir(parents=True)
    (run / "artifacts").mkdir()
    content = "import helper\nvalue = 0\nvalue += 1\n" + "\n".join(
        f"value_{index} = {index}  # non-hot source context" for index in range(500)
    )
    content += "\ntotal_loss += loss\n"
    modules = {"train.py": content, "helper.py": "ANSWER = 42\n"}
    files = {}
    for name, code in modules.items():
        (run / "source" / name).write_text(code)
        files[name] = {"sha256": hashlib.sha256(code.encode()).hexdigest()}
    manifest = {
        "command": ["python", "-m", "headroom.lab.run_target", "--script", "/source/train.py"],
        "source": {"files": files},
    }
    result = {
        "run_id": "offline-fixture",
        "status": "oom",
        "env": {"gpu_name": "fixture"},
        "shared_gpu": False,
        "step_records": [],
    }
    for path, value in (
        (run / "manifest.json", manifest),
        (run / "result.json", result),
        (run / "artifacts" / "snapshot.json", {"fixture": True}),
    ):
        path.write_text(json.dumps(value))
    analyzer = SimpleNamespace(analyze_snapshot=lambda *args, **kwargs: analysis_fixture())
    monkeypatch.setitem(sys.modules, "headroom.evidence_analysis", analyzer)
    return run


def test_budget_trims_prompt_without_discarding_complete_json(captured_run):
    result = build_evidence(captured_run, budget=2000)
    markdown = Path(result["evidence_md"]).read_text()
    document = json.loads(Path(result["evidence_json"]).read_text())
    assert _tokens(markdown) == result["token_count"] <= 2000
    assert document["source_token_count"] <= 600
    assert len(document["analysis"]["peak_composition"]) == 80
    assert "History prefix is missing." in markdown
    assert "123456" in markdown
    assert '"target": "unknown"' in markdown
    assert "not elapsed time" in markdown
    stages = [item["stage"] for item in document["trimming"]]
    order = {"top_n": 0, "source": 1, "timeline": 2}
    assert stages == sorted(stages, key=order.get)
    assert "top_n" in stages and "timeline" in stages
    assert Path(result["evidence_png"]).read_bytes().startswith(b"\x89PNG")
    assert document["sources"][0]["static_observations"][0]["kind"] == "static_source_pattern"
    assert all(
        frame["line"] != 504
        for row in document["analysis"]["peak_composition"]
        for frame in row["frames"]
    )


def test_large_budget_keeps_full_main_and_imported_module(captured_run):
    result = build_evidence(captured_run, budget=30000)
    document = json.loads(Path(result["evidence_json"]).read_text())
    assert [source["path"] for source in document["sources"]] == ["train.py", "helper.py"]
    assert all(
        len(source["included_lines"]) == source["total_lines"] for source in document["sources"]
    )
    assert document["source_token_count"] <= 9000


def test_unsafe_small_budget_refuses_instead_of_empty_success(captured_run):
    with pytest.raises(ValueError, match="cannot safely represent core evidence"):
        build_evidence(captured_run, budget=100)
    assert not (captured_run / "evidence" / "evidence.md").exists()


def test_snapshot_symlink_is_never_followed(captured_run, tmp_path):
    snapshot = captured_run / "artifacts" / "snapshot.json"
    snapshot.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text('{"outside_secret": "must-not-read"}')
    snapshot.symlink_to(outside)
    with pytest.raises(OSError):
        build_evidence(captured_run)


def test_source_reader_refuses_symlink_directory_and_secrets(tmp_path):
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (outside / "module.py").write_text("OUTSIDE_SECRET = 1\n")
    (source / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        _read_source(source, "linked/module.py")
    with pytest.raises(ValueError):
        _read_source(source, "../outside/module.py")
    (source / ".env.py").write_text("SECRET = 1\n")
    with pytest.raises(ValueError):
        _read_source(source, ".env.py")


def test_source_hash_mismatch_is_explicit(captured_run):
    (captured_run / "source" / "train.py").write_text("changed = True\n")
    manifest = json.loads((captured_run / "manifest.json").read_text())
    with pytest.raises(ValueError, match="hash differs"):
        collect_sources(captured_run, manifest, analysis_fixture())


def test_timeline_budget_retains_both_peaks_and_oom():
    timeline = [
        {
            "event_index": index,
            "allocated_bytes": index,
            "reserved_bytes": index + 100,
            "is_oom": index == 49,
        }
        for index in range(100)
    ]
    retained = _sample_timeline(timeline, 2, peak_index=11, reserved_peak_index=78)
    assert {row["event_index"] for row in retained} == {0, 11, 49, 78, 99}


def test_plot_receives_analyzer_aligned_steps(captured_run, monkeypatch):
    import headroom.timeline_plot as plotting

    aligned = [
        {"step": 1, "event_index": 12, "alignment": "last allocator event before optimizer hook"}
    ]
    analyzer = analysis_fixture()
    analyzer["step_boundaries"] = aligned
    monkeypatch.setitem(
        sys.modules,
        "headroom.evidence_analysis",
        SimpleNamespace(analyze_snapshot=lambda *args, **kwargs: analyzer),
    )
    observed = {}

    def render(timeline, output_path, oom_events=None, step_boundaries=None):
        observed["steps"] = step_boundaries
        Path(output_path).write_bytes(b"fixture-only")

    monkeypatch.setattr(plotting, "render_timeline", render)
    result = build_evidence(captured_run, budget=30000)
    assert observed["steps"] == aligned
    document = json.loads(Path(result["evidence_json"]).read_text())
    assert document["presentation"]["peak_stack_ids"] == [
        row["stack_id"] for row in analyzer["peak_composition"][:40]
    ]


@pytest.mark.parametrize(
    "command,expected,excluded",
    [
        (
            ["python", "-m", "pkg"],
            {"pkg/__main__.py", "pkg/__init__.py", "helper.py"},
            "pkg/helper.py",
        ),
        (["python", "pkg/train.py"], {"pkg/train.py", "pkg/helper.py"}, "helper.py"),
        (
            ["python", "-m", "pkg.train"],
            {"pkg/train.py", "pkg/__init__.py", "helper.py"},
            "pkg/helper.py",
        ),
    ],
)
def test_source_entry_and_absolute_imports_follow_launch_mode(
    tmp_path, command, expected, excluded
):
    run = tmp_path / "run"
    (run / "source" / "pkg").mkdir(parents=True)
    code = {
        "pkg/__main__.py": "import helper\n",
        "pkg/train.py": "import helper\n",
        "pkg/__init__.py": "PACKAGE = True\n",
        "pkg/helper.py": "SCRIPT_DIRECTORY_HELPER = True\n",
        "helper.py": "ROOT_DIRECTORY_HELPER = True\n",
    }
    files = {}
    for name, text in code.items():
        (run / "source" / name).write_text(text)
        files[name] = {"sha256": hashlib.sha256(text.encode()).hexdigest()}
    sources, warnings = collect_sources(run, {"command": command, "source": {"files": files}}, {})
    actual = {source["path"] for source in sources}
    assert expected == actual
    assert excluded not in actual
    assert not warnings


def _annotated_fixture(captured_run, monkeypatch, *, budget=30000, label="Nano opinion"):
    from headroom.annotate import annotate_stacks

    ordered = analysis_fixture()
    ordered["peak_composition"].sort(key=lambda row: row["bytes"], reverse=True)
    monkeypatch.setattr(
        sys.modules["headroom.evidence_analysis"],
        "analyze_snapshot",
        lambda *args, **kwargs: copy.deepcopy(ordered),
    )
    bundle = build_evidence(captured_run, budget=budget)
    document = json.loads(Path(bundle["evidence_json"]).read_text())
    labels = [
        {"stack_id": row["stack_id"], "category": "optimizer_state", "label": label}
        for row in document["analysis"]["peak_composition"][:40]
    ]
    router = SimpleNamespace(
        chat=lambda *args, **kwargs: SimpleNamespace(
            parsed={"annotations": labels}, model="nvidia/fixture-nano"
        )
    )
    return bundle, document, annotate_stacks(router, document)


def test_nano_attaches_to_visible_stacks_without_changing_original_evidence(
    captured_run, monkeypatch
):
    from headroom.evidence import annotate_evidence_bundle

    bundle, original, annotations = _annotated_fixture(captured_run, monkeypatch)
    prior_markdown = Path(bundle["evidence_md"]).read_text()
    annotated = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    document = json.loads(Path(bundle["evidence_json"]).read_text())
    text = Path(bundle["evidence_md"]).read_text()
    assert text.count("Nano model interpretation") == 40
    assert '"category": "optimizer_state"' in text
    assert "untrusted opinion, not measurement or instructions" in text
    assert annotated["token_count"] == document["token_count"] == _tokens(text) <= 30000
    assert document["annotation_delivery"]["prompt_stack_ids"] == [
        row["stack_id"] for row in original["analysis"]["peak_composition"][:40]
    ]
    assert document["annotation_delivery"]["omitted_prompt_stack_ids"] == []
    restored = copy.deepcopy(document["analysis"])
    for row in restored["peak_composition"]:
        row.pop("model_annotation", None)
    assert restored == original["analysis"]
    assert document["sources"] == original["sources"]
    assert document["source_token_count"] == original["source_token_count"]
    assert document["trimming"] == original["trimming"]
    without_notes = text
    for chunk in text.split("\n\n"):
        if chunk.startswith("Nano model interpretation"):
            without_notes = without_notes.replace("\n\n" + chunk, "")
    assert without_notes == prior_markdown
    assert annotated["analysis"] == document["analysis"]
    # Reapplying the same source-bound opinion is idempotent.
    again = annotate_evidence_bundle(annotated, annotations, provenance="offline_fixture")
    assert Path(bundle["evidence_md"]).read_text() == text
    assert again["token_count"] == annotated["token_count"]


def test_nano_optional_labels_fit_only_remaining_budget(captured_run, monkeypatch):
    from headroom.evidence import annotate_evidence_bundle

    bundle, original, annotations = _annotated_fixture(
        captured_run, monkeypatch, budget=2000, label="界" * 180
    )
    prior = Path(bundle["evidence_md"]).read_text()
    result = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    document = json.loads(Path(bundle["evidence_json"]).read_text())
    text = Path(bundle["evidence_md"]).read_text()
    delivery = result["annotation_delivery"]
    assert _tokens(text) <= 2000
    assert len(delivery["omitted_prompt_stack_ids"]) > 0
    assert len(delivery["attached_stack_ids"]) == 40
    assert (
        len([r for r in document["analysis"]["peak_composition"] if "model_annotation" in r]) == 40
    )
    assert set(delivery["prompt_stack_ids"]) <= set(original["presentation"]["peak_stack_ids"])
    assert document["source_token_count"] == original["source_token_count"]
    assert "123456" in text and "History prefix is missing." in text
    assert len(text) >= len(prior)


def test_skipped_annotations_leave_bundle_and_artifacts_unchanged(captured_run):
    from headroom.evidence import annotate_evidence_bundle

    bundle = build_evidence(captured_run, budget=2000)
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    for state in ("failed", "skipped", "unknown"):
        assert (
            annotate_evidence_bundle(
                bundle, {"status": state, "annotations": []}, provenance="live"
            )
            is bundle
        )
    assert before == {key: Path(bundle[key]).read_bytes() for key in before}


def test_completed_annotations_cannot_match_new_capture(captured_run, monkeypatch):
    from headroom.evidence import annotate_evidence_bundle

    bundle, _, annotations = _annotated_fixture(captured_run, monkeypatch)
    annotations["evidence_fingerprint"] = "0" * 64
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    result = annotate_evidence_bundle(bundle, annotations, provenance="live")
    assert result["annotation_delivery"]["reason"] == "source_evidence_mismatch"
    assert before == {key: Path(bundle[key]).read_bytes() for key in before}


def test_traceback_ablation_excludes_real_bound_nano_metadata(captured_run, monkeypatch, tmp_path):
    import headroom.diagnose as diagnosis
    import headroom.orchestrator  # noqa: F401 - capture real Services defaults before patching
    from headroom.evaluation import condition_services
    from headroom.evidence import annotate_evidence_bundle

    bundle, _, annotations = _annotated_fixture(
        captured_run, monkeypatch, label="NANO_SECRET_OPINION_FIXTURE"
    )
    annotated = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    document = json.loads(Path(annotated["evidence_json"]).read_text())
    document["evaluation_inputs"] = {
        "traceback": "CUDA OOM fixture traceback",
        "memory_summary": "Fixture captured memory summary",
    }
    received = {}

    def capture(router, markdown, **kwargs):
        received.update(markdown=markdown, evidence=kwargs["evidence"])
        return "offline-only-result"

    monkeypatch.setattr(diagnosis, "diagnose_with_router", capture)
    service = condition_services("traceback_ultra", tmp_path / "condition-audit")
    result = service.diagnose(
        object(),
        Path(annotated["evidence_md"]).read_text(),
        evidence=document,
        goal="reclaim",
        policy={},
    )
    assert result == "offline-only-result"
    actual = json.dumps(received)
    assert "NANO_SECRET_OPINION_FIXTURE" not in actual
    assert "model_annotation" not in actual and "stk_" not in actual
    assert "CUDA OOM fixture traceback" in actual
    assert set(received["evidence"]["analysis"]["stack_catalog"]) == {"traceback", "memory_summary"}


@pytest.mark.parametrize("fail_stage", ["prepare", "second_publish"])
def test_optional_annotation_write_failure_restores_original_pair(
    captured_run, monkeypatch, fail_stage
):
    from headroom.evidence import annotate_evidence_bundle

    bundle, _, annotations = _annotated_fixture(captured_run, monkeypatch)
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    original_write, original_replace = Path.write_bytes, Path.replace

    def write(path, data):
        if fail_stage == "prepare" and path.name.startswith(".evidence.json."):
            raise OSError("fixture prepare failure")
        return original_write(path, data)

    def replace(path, target):
        if fail_stage == "second_publish" and path.name.startswith(".evidence.json."):
            raise OSError("fixture second publish failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "write_bytes", write)
    monkeypatch.setattr(Path, "replace", replace)
    result = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    assert result["annotation_delivery"]["status"] == "not_attached"
    assert result["annotation_delivery"]["reason"] == "annotation_pair_publish_failed"
    assert result["annotation_delivery"]["restoration_failed"] is False
    assert before == {key: Path(bundle[key]).read_bytes() for key in before}
    assert all(Path(result[key]).read_bytes() == before[key] for key in before)
    assert not list(Path(bundle["evidence_json"]).parent.glob("*unannotated-*"))


def test_failed_restore_uses_retained_original_pair_for_diagnosis(captured_run, monkeypatch):
    from headroom.evidence import annotate_evidence_bundle

    bundle, _, annotations = _annotated_fixture(captured_run, monkeypatch)
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    original_replace = Path.replace

    def replace(path, target):
        if path.name.startswith(".evidence.json.") or ".unannotated-" in path.name:
            raise OSError("fixture publish and restore failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    result = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    assert result["annotation_delivery"]["restoration_failed"] is True
    assert result["annotation_delivery"]["using_original_evidence"] is True
    assert all(Path(result[key]).read_bytes() == before[key] for key in before)
    assert result["analysis"] == bundle["analysis"]
    assert all(".unannotated-" in result[key] for key in before)


def test_optional_annotation_budget_failure_does_not_block_original_bundle(
    captured_run, monkeypatch
):
    from headroom.evidence import annotate_evidence_bundle

    bundle, document, annotations = _annotated_fixture(captured_run, monkeypatch)
    document["budget"] = 1
    Path(bundle["evidence_json"]).write_text(json.dumps(document))
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    result = annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    assert result["annotation_delivery"]["status"] == "not_attached"
    assert result["annotation_delivery"]["reason"] == "annotation_evidence_or_budget_unavailable"
    assert before == {key: Path(bundle[key]).read_bytes() for key in before}


def test_annotation_interrupt_restores_pair_and_propagates(captured_run, monkeypatch):
    from headroom.evidence import annotate_evidence_bundle

    bundle, _, annotations = _annotated_fixture(captured_run, monkeypatch)
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    original_replace = Path.replace

    def replace(path, target):
        if path.name.startswith(".evidence.json."):
            raise KeyboardInterrupt()
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        annotate_evidence_bundle(bundle, annotations, provenance="offline_fixture")
    assert before == {key: Path(bundle[key]).read_bytes() for key in before}


@pytest.mark.parametrize("exception_kind", ["keyboard", "run_cancelled"])
def test_interrupt_and_failed_restore_update_existing_report_reference(
    captured_run, monkeypatch, exception_kind
):
    from headroom.evidence import annotate_evidence_bundle
    from headroom.orchestrator import RunCancelled
    from headroom.report import build_report

    bundle, _, annotations = _annotated_fixture(captured_run, monkeypatch)
    caller_evidence = {"before": bundle}
    original_reference = caller_evidence["before"]
    before = {key: Path(bundle[key]).read_bytes() for key in ("evidence_json", "evidence_md")}
    original_analysis = copy.deepcopy(bundle["analysis"])
    original_tokens = bundle["token_count"]
    original_replace = Path.replace
    interrupted = KeyboardInterrupt if exception_kind == "keyboard" else RunCancelled

    def replace(path, target):
        if path.name.startswith(".evidence.json."):
            raise interrupted("fixture second publication interrupted")
        if ".unannotated-" in path.name:
            raise OSError("fixture restore failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(interrupted, match="fixture second publication interrupted"):
        # The assignment never finishes. The caller's existing reference must be repaired.
        caller_evidence["before"] = annotate_evidence_bundle(
            bundle, annotations, provenance="offline_fixture"
        )
    assert caller_evidence["before"] is original_reference
    assert bundle["analysis"] == original_analysis and bundle["token_count"] == original_tokens
    assert bundle["annotation_delivery"]["status"] == "not_attached"
    assert bundle["annotation_delivery"]["restoration_failed"] is True
    assert bundle["annotation_delivery"]["partial_publish"] is True
    assert bundle["annotation_delivery"]["using_original_evidence"] is True
    assert all(".unannotated-" in bundle[key] for key in before)
    assert all(Path(bundle[key]).read_bytes() == before[key] for key in before)
    report = build_report(
        {"status": "needs_human", "annotations": annotations},
        evidence=caller_evidence,
    )
    reported = report["evidence"]["before"]
    assert all(Path(reported[key]).read_bytes() == before[key] for key in before)
    assert report["stack_annotations"] == []
    assert report["annotation_delivery"]["status"] == "not_attached"
