"""Wrapper replay uses real CPU Docker; OOM handoff cases are explicitly synthetic."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.execution import (
    captured_wrapper_descriptor,
    prepare_captured_command,
    prepare_local_command,
    replay_argv,
)
from headroom.lab.entrypoint import EntrypointCapture
from headroom.lab.runner import run_argv, run_script


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network prohibited in wrapper tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def observed_fixture(content=b"pass\n", **changes):
    entry = {
        "schema_version": 1,
        "complete": True,
        "pid": 7,
        "ppid": 1,
        "executable": "/opt/venv/bin/python",
        "startup_cwd": "/source/sub",
        "cwd": "/source/sub",
        "orig_argv": ["python", "-O", "-m", "pkg.entry", "--batch=8"],
        "startup_argv": ["-m", "--batch=8"],
        "effective_startup_argv": ["-m", "--batch=8"],
        "argv": ["/source/sub/pkg/entry.py", "--batch=8"],
        "main_file": "/source/sub/pkg/entry.py",
        "module": "pkg.entry",
    }
    entry.update(changes)
    capture = {
        "execution_entrypoint": entry,
        "execution_capture": {"captured_process_count": 1, "single_python_entrypoint": True},
    }
    manifest = {
        "source": {
            "files": {
                "sub/pkg/__init__.py": {"sha256": hashlib.sha256(b"").hexdigest()},
                "sub/pkg/entry.py": {"sha256": hashlib.sha256(content).hexdigest()},
            }
        }
    }
    return capture, manifest


def test_runtime_override_only_changes_matching_target_argv_before_main(monkeypatch):
    import os
    import sys

    original = ["python", "-O", "-m", "pkg.entry", "--batch=8"]
    monkeypatch.setattr(os, "getcwd", lambda: "/source/sub")
    monkeypatch.setattr(sys, "orig_argv", original.copy())
    monkeypatch.setattr(sys, "argv", ["-m", "--batch=8"])
    monkeypatch.setattr(sys, "executable", "/opt/venv/bin/python")
    monkeypatch.setitem(
        sys.modules,
        "__main__",
        SimpleNamespace(
            __file__="/source/sub/pkg/entry.py", __spec__=SimpleNamespace(name="pkg.entry")
        ),
    )
    proposal = {
        "expected_startup_cwd": "/source/sub",
        "expected_orig_argv": original,
        "original_target_args": ["--batch=8"],
        "effective_target_args": ["--batch=1", "literal;arg"],
    }
    monkeypatch.setenv("HEADROOM_TARGET_ARGV_OVERRIDE", json.dumps(proposal))
    capture = EntrypointCapture()
    result = capture.finish()
    assert sys.argv == ["-m", "--batch=1", "literal;arg"]
    assert sys.orig_argv == original
    assert result["startup_argv"] == ["-m", "--batch=8"]
    assert result["effective_startup_argv"] == sys.argv
    assert result["argv_override"]["applied"] is True
    assert result["argv_override"]["matched"] is True
    monkeypatch.setattr(sys, "argv", ["helper.py", "--other"])
    monkeypatch.setattr(sys, "orig_argv", ["python", "helper.py", "--other"])
    helper = EntrypointCapture().finish()
    assert sys.argv == ["helper.py", "--other"]
    assert helper["argv_override"]["applied"] is False


def test_captured_module_under_relative_cwd_preserves_wrapper_and_source_hash(tmp_path):
    command = ["/bin/sh", "launch.sh", "--batch=8"]
    package = tmp_path / "sub/pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "entry.py").write_text("pass\n")
    capture, manifest = observed_fixture()
    prepared = prepare_captured_command(tmp_path, command, capture, manifest)
    assert prepared.script == package / "entry.py"
    assert prepared.script_args == ("--batch=8",)
    descriptor = prepared.execution_entrypoint
    assert descriptor["startup_cwd_relative"] == "sub"
    assert descriptor["source_relative"] == "sub/pkg/entry.py"
    assert descriptor["argv_override_supported"] is True
    assert replay_argv(command, ["--batch=1"], execution_entrypoint=descriptor) == command
    assert (
        prepare_local_command(tmp_path, command, execution_entrypoint=descriptor).script
        == prepared.script
    )
    (package / "entry.py").write_text("print('candidate')\n")
    # Candidate content can differ; only capture handoff requires the original source hash.
    assert (
        prepare_local_command(tmp_path, command, execution_entrypoint=descriptor).script
        == prepared.script
    )
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        prepare_captured_command(tmp_path, command, capture, manifest)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"main_file": "/outside/train.py"}, "OUTSIDE_SOURCE"),
        ({"module": "wrong"}, "MODULE_MISMATCH"),
        ({"startup_cwd": "/source/other"}, "MODULE_SOURCE_UNAVAILABLE"),
        ({"startup_argv": ["-m", "--batch=1"]}, "TARGET_ARGV_MISMATCH"),
    ],
)
def test_uncertain_runtime_mapping_is_not_guessed(change, reason):
    capture, manifest = observed_fixture(**change)
    with pytest.raises(ValueError, match=reason):
        captured_wrapper_descriptor(["sh", "launch.sh"], capture, manifest)


def test_multiple_python_targets_cannot_be_selected_from_one_primary():
    capture, manifest = observed_fixture()
    capture["execution_capture"] = {
        "captured_process_count": 2,
        "single_python_entrypoint": False,
        "reason": "MULTIPLE_PYTHON_ENTRYPOINTS",
    }
    with pytest.raises(ValueError, match="MULTIPLE_PYTHON"):
        captured_wrapper_descriptor(["sh", "launch.sh"], capture, manifest)


@pytest.fixture
def wrapper_source(tmp_path):
    source = tmp_path / "source"
    package = source / "sub/pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "helper.py").write_text("VALUE = 17\n")
    (package / "entry.py").write_text(
        "from .helper import VALUE\n"
        "import json, os, sys\n"
        "print('WRAPPER:' + json.dumps({'value': VALUE, 'args': sys.argv[1:], "
        "'cwd': os.getcwd(), 'package': __package__, 'optimize': sys.flags.optimize}))\n"
    )
    (source / "launch.sh").write_text('cd sub\nexec python -O -m pkg.entry "$@"\n')
    return source


def wrapper_output(result):
    run = Path(result["run_dir"])
    text = (run / "stdout.log").read_text()
    line = next(line for line in text.splitlines() if line.startswith("WRAPPER:"))
    return json.loads(line.removeprefix("WRAPPER:"))


@pytest.mark.parametrize("inline", [False, True])
def test_real_cpu_wrapper_candidate_and_reference_apply_target_args_and_collect_sources(
    wrapper_source,
    tmp_path,
    inline,
):
    from headroom.evidence import collect_sources

    arguments = ["--batch=8", "literal space;$(text)"]
    command = (
        ["/bin/sh", "-c", 'cd sub && exec python -O -m pkg.entry "$@"', "launcher", *arguments]
        if inline
        else ["/bin/sh", "launch.sh", *arguments]
    )
    baseline = run_argv(wrapper_source, command, run_root=tmp_path / "runs", device="cpu")
    assert baseline["status"] == "completed" and baseline["capture_complete"], baseline
    run = Path(baseline["run_dir"])
    manifest = json.loads((run / "manifest.json").read_text())
    prepared = prepare_captured_command(run / "source", command, baseline, manifest)
    assert baseline["execution_capture"]["captured_process_count"] == 1
    assert wrapper_output(baseline)["args"] == arguments
    assert prepared.execution_entrypoint["startup_cwd_relative"] == "sub"
    files, warnings = collect_sources(run, manifest, {})
    assert {"sub/pkg/entry.py", "sub/pkg/helper.py", "sub/pkg/__init__.py"} <= {
        item["path"] for item in files
    }, warnings
    candidate = tmp_path / "candidate"
    shutil.copytree(prepared.source_root, candidate)
    (candidate / "sub/pkg/helper.py").chmod(0o600)
    (candidate / "sub/pkg/helper.py").write_text("VALUE = 23\n")
    for batch in (4, 1):
        args = [f"--batch={batch}", "literal space;$(text)"]
        result = run_script(
            candidate / "sub/pkg/entry.py",
            source_root=candidate,
            execution_argv=command,
            execution_entrypoint=prepared.execution_entrypoint,
            script_args=args,
            run_root=tmp_path / "runs",
            device="cpu",
        )
        assert result["status"] == "completed" and result["execution_replay"]["matched"], result
        observed = wrapper_output(result)
        assert observed == {
            "value": 23,
            "args": args,
            "cwd": "/source/sub",
            "package": "pkg",
            "optimize": 1,
        }
        replay_manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text())
        assert replay_manifest["command"] == command
        assert replay_manifest["target_argv_override"]["effective_target_args"] == args
        assert (
            result["execution_entrypoint"]["orig_argv"]
            == prepared.execution_entrypoint["python_argv"]
        )


def test_real_cpu_wrong_wrapper_target_fails_replay_matching(wrapper_source, tmp_path):
    command = ["/bin/sh", "launch.sh", "--batch=8"]
    baseline = run_argv(wrapper_source, command, run_root=tmp_path / "runs", device="cpu")
    run = Path(baseline["run_dir"])
    prepared = prepare_captured_command(
        run / "source", command, baseline, json.loads((run / "manifest.json").read_text())
    )
    candidate = tmp_path / "changed-launcher"
    shutil.copytree(prepared.source_root, candidate)
    (candidate / "launch.sh").chmod(0o600)
    (candidate / "launch.sh").write_text("cd sub\nexec python -m pkg.entry --batch=999\n")
    result = run_script(
        candidate / "sub/pkg/entry.py",
        source_root=candidate,
        execution_argv=command,
        execution_entrypoint=prepared.execution_entrypoint,
        script_args=["--batch=1"],
        run_root=tmp_path / "runs",
        device="cpu",
    )
    assert result["status"] == "error"
    assert result["reason"] == "WRAPPER_REPLAY_ENTRYPOINT_MISMATCH"
    assert wrapper_output(result)["args"] == ["--batch=999"]


def test_real_cpu_multiple_python_entries_are_explicitly_ambiguous(wrapper_source, tmp_path):
    (wrapper_source / "launch.sh").write_text("cd sub\npython -m pkg.entry\npython -m pkg.entry\n")
    command = ["/bin/sh", "launch.sh"]
    result = run_argv(wrapper_source, command, run_root=tmp_path / "runs", device="cpu")
    assert result["execution_capture"]["captured_process_count"] == 2
    assert result["execution_capture"]["reason"] == "MULTIPLE_PYTHON_ENTRYPOINTS"
    assert result["execution"]["state"]["ExitCode"] == 0


def test_watch_synthetic_oom_reaches_real_orchestrator_sdk_patch_replay_and_report(tmp_path):
    """Synthetic CUDA/memory verdicts; actual capture and candidate argv are CPU Docker."""
    from dataclasses import replace
    from decimal import Decimal

    import httpx

    from headroom.config import RuntimeConfig, candidate_models
    from headroom.llm.client import TokenFactoryClient
    from headroom.llm.cost import Pricing
    from headroom.llm.router import LLMRouter
    from headroom.orchestrator import Services, run_fix
    from headroom.search import HARD_CHECKS
    from headroom.store.db import Store
    from headroom.watch import watch_command

    source = tmp_path / "flow-source"
    source.mkdir()
    (source / "launch.sh").write_text('exec python -O train.py "$@"\n')
    (source / "train.py").write_text(
        "VALUE = 1\nimport json, sys\n"
        "print('FLOW:' + json.dumps({'value': VALUE, 'args': sys.argv[1:]}))\n"
        "if VALUE == 1:\n    raise RuntimeError('synthetic CPU failure')\n"
    )
    command = ["/bin/sh", "launch.sh", "--batch=8"]
    calls, observed = [], []
    store = Store(tmp_path / "flow.sqlite")
    diagnosis = {
        "root_causes": [
            {
                "id": "c1",
                "title": "Offline fixture",
                "category": "activations",
                "bytes_gb": 2.0,
                "evidence_refs": ["stk_fixture"],
                "confidence": 0.9,
            }
        ],
        "plan": [
            {
                "fix_id": "f1",
                "type": "code",
                "title": "Fixture edit and batch",
                "description": "Synthetic workflow test only.",
                "expected_saving_gb": 1.0,
                "numerics_impact": "none",
                "throughput_impact": "none",
                "risk": "Offline fixture only.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["No real GPU acceptance is claimed."],
    }
    proposal = {
        "diff": "diff --git a/train.py b/train.py\n--- a/train.py\n+++ b/train.py\n"
        "@@ -1,5 +1,5 @@\n-VALUE = 1\n+VALUE = 2\n import json, sys\n"
        " print('FLOW:' + json.dumps({'value': VALUE, 'args': sys.argv[1:]}))\n"
        " if VALUE == 1:\n     raise RuntimeError('synthetic CPU failure')\n",
        "env_changes": {},
        "cli_changes": ["--batch=4"],
        "notes": ["Offline fixture only."],
    }

    def runtime(run_id, store, directory):
        models = {
            name: replace(
                spec,
                pricing=Pricing(Decimal(1), Decimal(2), verified=True, source="offline fixture"),
            )
            for name, spec in candidate_models().items()
        }

        def respond(request):
            body = json.loads(request.content)
            calls.append(body)
            payload = diagnosis if len(calls) == 1 else proposal
            return httpx.Response(
                200,
                json={
                    "id": "offline-fixture",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(payload),
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                },
            )

        client = TokenFactoryClient(
            config=RuntimeConfig(models=models), transport=httpx.MockTransport(respond)
        )
        return SimpleNamespace(
            router=LLMRouter(client), client=client, evidence_token_budget=1000, close=client.close
        )

    def synthetic_oom(result, *, watch=False):
        assert result["capture_complete"] and result["cleanup_verified"]
        assert result["execution"]["state"]["ExitCode"] == 1
        return {
            **result,
            "status": "oom",
            "termination_reason": "oom",
            "oom": {"traceback": "Explicit synthetic OOM from a captured CPU exception"},
            "env": {**result["env"], "device": "cuda" if watch else "cpu"},
            "peak_allocated_bytes": 2_000_000_000,
            "peak_alloc_gb": 2.0,
        }

    def watch_lab(root, argv, **options):
        options["device"] = "cpu"
        return synthetic_oom(run_argv(root, argv, **options), watch=True)

    def baseline(script, **options):
        assert options["execution_argv"] == command
        options["device"] = "cpu"
        result = run_script(script, **options)
        assert result["execution_replay"]["matched"]
        return synthetic_oom(result)

    def evidence(run, *, output_dir, **options):
        output_dir.mkdir(parents=True)
        data = {
            "sources": [{"path": "train.py"}],
            "analysis": {"stack_catalog": {"stk_fixture": []}},
        }
        (output_dir / "evidence.json").write_text(json.dumps(data))
        (output_dir / "evidence.md").write_text("Synthetic fixture stack stk_fixture.\n")
        return {
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
            "token_count": 10,
            "analysis": data["analysis"],
        }

    def verify(before, script, **options):
        assert options["execution_argv"] == command
        assert options["script_args"] == ("--batch", "4")
        result = run_script(
            script,
            source_root=options["candidate_source_root"],
            execution_argv=command,
            execution_entrypoint=options["execution_entrypoint"],
            script_args=options["script_args"],
            run_root=options["run_root"],
            device="cpu",
        )
        assert result["status"] == "completed" and result["execution_replay"]["matched"], result
        output = (Path(result["run_dir"]) / "stdout.log").read_text()
        assert json.loads(
            next(line[5:] for line in output.splitlines() if line.startswith("FLOW:"))
        ) == {"value": 2, "args": ["--batch", "4"]}
        observed.append(result)
        return {
            "candidate": {**result, "peak_allocated_bytes": 1_000_000_000, "peak_alloc_gb": 1.0},
            "reference": None,
            "report": {
                "completed": True,
                "target_met": True,
                "loss_equivalence": "identical",
                "peak_before": 2.0,
                "peak_after": 1.0,
                "reduction_pct": 50.0,
                "notes": ["Synthetic memory/numerical verdict; CPU argv replay is measured."],
                "checks": {
                    **dict.fromkeys(HARD_CHECKS, True),
                    "parameter_count_unchanged": True,
                    "numerical_acceptance": True,
                    "loss_tolerance": True,
                    "loss_decreases": True,
                    "throughput_limit": None,
                },
            },
        }

    def repair(request, **options):
        assert request.execution_entrypoint["root_argv"] == command
        assert request.execution_entrypoint["script_args"] == ["--batch=8"]
        assert request.repository_mode is False
        return run_fix(
            request.model_copy(update={"device": "cpu", "research_enabled": False}),
            store=store,
            services=Services(
                baseline=baseline,
                evidence=evidence,
                verify=verify,
                runtime_factory=runtime,
                provenance="offline_fixture",
            ),
            **options,
        )

    try:
        result = watch_command(
            command,
            source_root=source,
            run_root=tmp_path / "watch",
            device="cuda",
            lab_runner=watch_lab,
            fix_runner=repair,
        )
        assert result["triggered"] and result["status"] == "completed", result
        assert result["exit_code"] == 0 and result["original_exit_code"] == 1
        assert len(calls) == 2 and len(observed) == 1
        fix = result["fix"]
        assert store.get_run(fix["run_id"])["provenance"] == "offline_fixture"
        assert fix["kept"]["execution_argv"] == command
        assert fix["kept"]["effective_cli"] == ["--batch", "4"]
        assert fix["kept"]["execution_entrypoint"]["script_args"] == ["--batch=8"]
        manifest = json.loads(
            (Path(fix["run_dir"]) / "configurations/round-01/manifest.json").read_text()
        )
        assert manifest["execution_argv"] == command
        assert manifest["execution_entrypoint"]["root_argv"] == command
        assert Path(result["report_path"]).is_file()
        assert (source / "train.py").read_text().startswith("VALUE = 1")
    finally:
        store.close()


def test_real_cpu_executable_wrapper_preserves_non_oom_exit(wrapper_source, tmp_path):
    from headroom.watch import watch_command

    launcher = wrapper_source / "launch.sh"
    launcher.write_text("#!/bin/sh\n" + launcher.read_text())
    launcher.chmod(0o755)
    entry = wrapper_source / "sub/pkg/entry.py"
    entry.write_text(entry.read_text() + "raise SystemExit(7)\n")
    result = watch_command(
        ["./launch.sh", "--batch=8"],
        source_root=wrapper_source,
        run_root=tmp_path / "watch",
        device="cpu",
        fix_runner=lambda *a, **k: pytest.fail("Non-OOM must not repair"),
    )
    assert result["exit_code"] == result["original_exit_code"] == 7
    assert result["repair_supported"] and not result["triggered"]
    assert result["execution_entrypoint"]["root_argv"] == ["./launch.sh", "--batch=8"]


@pytest.mark.parametrize("module", [False, True])
def test_real_cpu_verify_runner_overrides_wrapper_candidate_and_small_batch_reference(
    wrapper_source,
    tmp_path,
    module,
):
    from headroom.verify.runner import verify_script

    script = wrapper_source / ("sub/pkg/entry.py" if module else "train.py")
    if not module:
        (wrapper_source / "launch.sh").write_text('exec python -O train.py "$@"\n')
    script.write_text(
        "import argparse, torch\n"
        "p = argparse.ArgumentParser()\np.add_argument('--batch', type=int, default=8)\n"
        "args = p.parse_args()\n"
        "model = torch.nn.Linear(1, 1)\nopt = torch.optim.SGD(model.parameters(), lr=0.01)\n"
        "x = torch.ones(args.batch, 1)\n"
        "for _ in range(30):\n"
        "    opt.zero_grad()\n    loss = model(x).square().mean()\n"
        "    loss.backward()\n    opt.step()\n"
    )
    command = ["/bin/sh", "launch.sh", "--batch", "8"]
    captured = run_argv(wrapper_source, command, run_root=tmp_path / "runs", device="cpu")
    assert captured["status"] == "completed" and captured["steps"] == 20
    run = Path(captured["run_dir"])
    prepared = prepare_captured_command(
        run / "source", command, captured, json.loads((run / "manifest.json").read_text())
    )
    # Only the OOM branch selection is synthetic; both verification runs execute on CPU.
    baseline = {**captured, "status": "oom"}
    result = verify_script(
        baseline,
        prepared.script,
        baseline_script=prepared.script,
        candidate_source_root=prepared.source_root,
        baseline_source_root=prepared.source_root,
        execution_argv=command,
        execution_entrypoint=prepared.execution_entrypoint,
        script_args=["--batch", "4"],
        baseline_args=["--batch", "8"],
        run_root=tmp_path / "runs",
        device="cpu",
    )
    assert result["candidate"]["steps"] == result["reference"]["steps"] == 20
    assert result["candidate"]["execution_replay"]["matched"]
    assert result["reference"]["execution_replay"]["matched"]
    assert result["candidate"]["execution_entrypoint"]["effective_startup_argv"][1:] == [
        "--batch",
        "4",
    ]
    assert result["reference"]["execution_entrypoint"]["effective_startup_argv"][1:] == [
        "--batch",
        "1",
    ]
    assert result["reference_discovery"]["reference_batch"] == 1
    assert result["report"].target_met is False  # CPU runs do not certify a GPU repair.


def test_entrypoint_observer_restores_callable_profile_and_never_keeps_frame(monkeypatch):
    import sys

    calls = []

    def existing(frame, event, argument):
        calls.append(event)

    previous = sys.getprofile()
    sys.setprofile(existing)
    capture = None
    try:
        capture = EntrypointCapture()
        frame = SimpleNamespace(
            f_code=SimpleNamespace(co_name="<module>"),
            f_globals={"__name__": "__main__", "__file__": "/source/train.py", "__spec__": None},
        )
        capture._observer(frame, "call", None)
        assert sys.getprofile() is existing
        assert capture.main_file == "/source/train.py"
        assert capture.profile_observation == "main_frame_observed"
        assert all(
            value is not frame and value is not frame.f_globals for value in vars(capture).values()
        )
        assert "call" in calls
    finally:
        if capture is not None:
            capture.close()
        sys.setprofile(previous)


def test_entrypoint_finish_restores_observer_that_never_saw_a_main():
    import sys

    previous = sys.getprofile()
    capture = EntrypointCapture()
    assert sys.getprofile() is capture._observer
    capture.finish()
    assert sys.getprofile() is previous


def test_existing_cprofile_is_preserved():
    import cProfile
    import sys

    previous = sys.getprofile()
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        active = sys.getprofile()
        capture = EntrypointCapture()
        result = capture.finish()
        assert sys.getprofile() is active
        if active is not None and not callable(active):
            assert result["complete"] is False
            assert result["entry_observation"] == "existing_profiler_unsupported"
        # Python 3.12 cProfile uses monitoring and may not expose a sys profile
        # object. It must continue recording while our temporary observer runs.
        codes = [entry.code for entry in profiler.getstats()]
        assert EntrypointCapture.finish.__code__ in codes
    finally:
        profiler.disable()
        sys.setprofile(previous)


def test_noncallable_sys_profile_is_left_intact_and_marked_unknown(monkeypatch):
    import sys

    profiler = object()
    monkeypatch.setattr(sys, "getprofile", lambda: profiler)
    monkeypatch.setattr(sys, "setprofile", lambda *args: pytest.fail("Do not replace cProfile"))
    capture = EntrypointCapture()
    result = capture.finish()
    assert result["complete"] is False
    assert result["entry_observation"] == "existing_profiler_unsupported"
    assert sys.getprofile() is profiler
