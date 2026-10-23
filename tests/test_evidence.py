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
