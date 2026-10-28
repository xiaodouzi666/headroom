"""Isolated feature/CLI bridges: temporary pools, synthetic Lab, SDK MockTransport."""

import json
import shutil
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from test_diagnosis_acceptance import profile

from headroom.acceptance import allocation as alloc
from headroom.acceptance import feature_allocation as feature
from headroom.acceptance import watch_binding as watch
from headroom.budget import BudgetLedger
from headroom.orchestrator import FixRequest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **k):
        pytest.fail("Network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)


def activate(root, intent, slot):
    scope = "F5" if slot == "clean-s3" else "F3b"
    BudgetLedger(root / ".cache/budget.db", total_limit="6", daily_limit="6")
    path, credential = profile(root)
    document = json.loads(path.read_text())
    document.update(authorized_total_usd="6", available_credit_usd="8")
    intents = {
        s: {
            "kind": kind,
            "runtime_profile": intent["runtime_profile"],
            "budget_usd": "0.30",
            "daily_budget_usd": "6",
            "payload": {"offline": s},
        }
        for group in feature.GROUPS.values()
        for s, (kind, _) in group["slots"].items()
    }
    intents[slot] = intent
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6",
        "available_gift_usd": "8",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": "6",
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.5"
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    plan["feature_scope_caps_usd"] = {"F3b": "1", "F5": "0.30"}
    for key, group in feature.GROUPS.items():
        for _, task in group["slots"].values():
            plan["task_run_caps_usd"][task] = "0.30"
        plan["task_pins"][key] = {
            "preparation_sha256": "4" * 64,
            "slot_intents_sha256": alloc.digest(
                {s: feature.intent_sha256(intents[s]) for s in group["slots"]}
            ),
        }
    authorization = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "6",
        "approval_message_ref": "offline-only",
        "statement_sha256": "5" * 64,
    }
    receipt = alloc.activate_allocation(plan, authorization, document, project_root=root)
    parent = feature.claim_feature_parent(
        root / ".cache/final48-allocation/receipt.json",
        project_root=root,
        scope=scope,
        preparation_sha256="4" * 64,
        slot_intents={s: feature.intent_sha256(intents[s]) for s in feature.GROUPS[scope]["slots"]},
    )
    binding = feature.claim_feature_child(parent, slot_id=slot, intent=intent, run_id=uuid4().hex)
    return binding, receipt, credential


@pytest.fixture
def bound_watch(tmp_path):
    root = tmp_path / "project"
    source = root / "scenarios/s1_batch_too_big"
    source.mkdir(parents=True)
    (source / "train.py").write_text("VALUE = 1\n")
    options = {
        "runtime_profile": str(root / ".cache/final48-allocation/runtime-profile.json"),
        "budget_usd": "0.30",
        "daily_budget_usd": "6",
        "research_enabled": False,
    }
    args = {
        "command": ["python", "train.py"],
        "source_root": source,
        "fix_options": options,
        "run_root": root / "runs/watch",
    }
    intent = watch.prepare_watch_intent(**{k: v for k, v in args.items() if k != "run_root"})
    binding, receipt, credential = activate(root, intent, "watch-s1")
    return root, args, intent, binding, receipt, credential


def capture_lab(change=None):
    def lab(source, command, **kw):
        from headroom.lab.runner import copy_source

        directory = Path(kw["run_root"]) / uuid4().hex
        directory.mkdir(parents=True)
        manifest = copy_source(source, directory / "source")
        result = {
            "protocol": "headroom.lab.v1",
            "status": "oom",
            "termination_reason": "oom",
            "capture_complete": True,
            "cleanup_verified": True,
            "oom": {"traceback": "fixture"},
            "env": {"device": "cuda"},
            "run_id": directory.name,
            "run_dir": str(directory),
            "execution": {"state": {"ExitCode": 1, "OOMKilled": False, "Running": False}},
        }
        data = {
            "command": ["/opt/venv/bin/python", *command[1:]],
            "source_root": str(source),
            "source": manifest,
            **{k: kw[k] for k in ("device", "max_steps", "max_seconds", "seed")},
        }
        (directory / "manifest.json").write_text(json.dumps(data))
        (directory / "result.json").write_text(json.dumps(result))
        if change == "source":
            (directory / "source/train.py").chmod(0o644)
            (directory / "source/train.py").write_text("VALUE = 2\n")
        elif change == "command":
            data["command"] = ["/opt/venv/bin/python", "other.py"]
            (directory / "manifest.json").write_text(json.dumps(data))
        elif change == "cleanup":
            result["cleanup_verified"] = False
        return result

    return lab


@pytest.mark.parametrize("change", ["source", "command", "cleanup"])
def test_captured_watch_drift_never_dispatches(bound_watch, monkeypatch, change):
    _, args, intent, binding, _, _ = bound_watch
    monkeypatch.setattr(watch, "run_fix", lambda *a, **k: pytest.fail("Must not dispatch"))
    result = watch.run_bound_watch(
        **args, intent=intent, allocation_child_binding=binding, lab_runner=capture_lab(change)
    )
    assert result["status"] in {"failed", "needs_human"}
    assert result["fix"] is None


def test_watch_preflight_refuses_source_before_lab(bound_watch, monkeypatch):
    _, args, intent, binding, _, _ = bound_watch
    (args["source_root"] / "train.py").write_text("VALUE = 3\n")
    with pytest.raises(ValueError, match="intent"):
        watch.run_bound_watch(
            **args,
            intent=intent,
            allocation_child_binding=binding,
            lab_runner=lambda *a, **k: pytest.fail("No Lab"),
        )


def test_watch_normal_accounting_factory_and_second_attempt_guard(bound_watch, monkeypatch):
    from headroom.runtime import read_live_profile

    root, args, intent, binding, receipt, _ = bound_watch
    before = alloc.historical_snapshot(root)

    def repair(request, *, run_root, run_id, services):
        assert services.runtime_factory is None and services.provenance == "live"
        assert run_id == binding["run_id"]
        budget = services.budget_factory(
            run_id, request, read_live_profile(request.runtime_profile)
        )
        assert str(budget.total_limit) == "1" and str(budget.daily_limit) == "6"
        budget.open_run(run_id, ".30")
        budget.reserve(run_id, "first", ".01")
        budget.settle(run_id, "first", ".01")
        with open(receipt["profile_path"], "a") as h:
            h.write(" ")
        with pytest.raises(ValueError):
            budget.reserve(run_id, "second", ".01")
        budget.close_run(run_id)
        return {"run_id": run_id, "status": "needs_human", "target_met": False}

    monkeypatch.setattr(watch, "run_fix", repair)
    result = watch.run_bound_watch(
        **args, intent=intent, allocation_child_binding=binding, lab_runner=capture_lab()
    )
    assert result["triggered"] and result["fix"]["run_id"] == binding["run_id"]
    assert alloc.historical_snapshot(root) == before


def clean_fixture(tmp_path):
    from headroom import cli_execution

    clean = tmp_path / "clean"
    shutil.copytree(
        cli_execution.PACKAGE_ROOT / "headroom",
        clean / "headroom",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(cli_execution.PACKAGE_ROOT / name, clean / name)
    source = clean / "scenarios/s3_eval_no_grad_missing"
    source.mkdir(parents=True)
    (source / "train.py").write_text("VALUE = 1\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Offline",
            "-c",
            "user.email=offline@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(clean), *args], check=True, capture_output=True)
    return clean, source


def test_f5_clean_pins_reject_dirty_or_extra_sources(tmp_path):
    from headroom.cli_execution import feature_checkout, prepare_feature_fix_intent

    clean, source = clean_fixture(tmp_path)
    request = FixRequest(script=str(source / "train.py"), source_root=str(source), budget_usd=".30")
    intent = prepare_feature_fix_intent(request, checkout=clean)
    assert feature_checkout(intent) == clean
    (clean / "headroom/extra.py").write_text("VALUE=1\n")
    with pytest.raises(ValueError, match="sources"):
        feature_checkout(intent)
    (clean / "headroom/extra.py").unlink()
    (source / "train.py").write_text("VALUE=2\n")
    with pytest.raises(ValueError, match="unchanged"):
        feature_checkout(intent)


@pytest.mark.parametrize("change", ["none", "mode", "symlink", "command", "source", "binding"])
def test_private_watch_context_is_verified_without_lab(bound_watch, tmp_path, change):
    _, args, intent, binding, _, _ = bound_watch
    path = tmp_path / "context.json"
    if change == "binding":
        binding["run_id"] = "forged"
    path.write_text(json.dumps({"binding": binding, "intent": intent}))
    path.chmod(0o644 if change == "mode" else 0o600)
    if change == "symlink":
        target = path
        path = tmp_path / "linked"
        path.symlink_to(target)
    if change == "command":
        args["command"] = ["python", "train.py", "--other=1"]
    if change == "source":
        (args["source_root"] / "train.py").write_text("CHANGED=1\n")
    arguments = {k: v for k, v in args.items() if k != "run_root"}
    if change == "none":
        assert watch.load_watch_feature_context(path, **arguments) == (binding, intent)
    else:
        with pytest.raises((ValueError, OSError)):
            watch.load_watch_feature_context(path, **arguments)


def test_f5_actual_installed_console_imports_own_clean_checkout_and_removes_pythonpath(tmp_path):
    import site
    import sys
    import time

    import test_cli_execution as fixture

    from headroom.cli_execution import prepare_feature_fix_intent
    from headroom.store.db import Store

    root = tmp_path / "allocation"
    root.mkdir()
    clean, source = clean_fixture(tmp_path)
    request = FixRequest(
        script=str(source / "train.py"),
        source_root=str(source),
        runtime_profile=str(root / ".cache/final48-allocation/runtime-profile.json"),
        budget_usd=".30",
        daily_budget_usd="6",
        research_enabled=False,
    )
    intent = prepare_feature_fix_intent(request, checkout=clean)
    binding, receipt, _ = activate(root, intent, "clean-s3")
    control = tmp_path / "control"
    control.mkdir()
    run_id = binding["run_id"]
    store = Store(control / "store.db")
    store.create_run(
        run_id,
        {
            "status": "queued",
            "request": request.model_dump(),
            "run_dir": str(control / "jobs" / run_id),
            "allocation_child_binding": binding,
            "feature_intent": intent,
        },
    )
    store.close()

    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(clean / ".venv")],
        check=True,
        capture_output=True,
        timeout=30,
    )
    packages = (
        clean / f".venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    )
    (packages / "00-clean.pth").write_text(str(clean) + "\n")
    dependencies = [p for p in site.getsitepackages() if Path(p).is_dir()]
    (packages / "10-dependencies.pth").write_text("\n".join(dependencies) + "\n")
    fixture.child_environment(control)
    bootstrap = (control / "python-startup/sitecustomize.py").read_text()
    prefix = "import sys\nsys.path.append(" + repr(str(fixture.ROOT / "tests")) + ")\n"
    suffix = """
if os.environ.get("HEADROOM_EVALUATION_CONTEXT"):
    (CASE/"f5-environment.json").write_text(__import__("json").dumps({
        "pythonpath":os.environ.get("PYTHONPATH"),"pythonhome":os.environ.get("PYTHONHOME"),
        "budget_path":os.environ.get("HEADROOM_BUDGET_DB_PATH")}))
"""
    bootstrap_path = packages / "offline_f5_bootstrap.py"
    bootstrap_path.write_text(prefix + bootstrap + suffix)
    (packages / "99-offline-fixture.pth").write_text(
        "import runpy; runpy.run_path(" + repr(str(bootstrap_path)) + ")\n"
    )
    console = clean / ".venv/bin/headroom"
    console.write_text(
        "#!" + str(clean / ".venv/bin/python") + "\nfrom headroom.cli import main\nmain()\n"
    )
    console.chmod(0o755)
    values = [
        request.model_dump(),
        str(control / "store.db"),
        str(control / "jobs"),
        run_id,
        "full_ultra",
        str(control / "audit"),
        str(control / f"worker-result-{run_id}.json"),
        time.monotonic() + 30,
        None,
        binding,
        intent,
    ]
    result, cli = fixture.execute_case(control, values)
    assert result.returncode == 0, result.stderr
    assert cli["package_root"] == str(clean) and cli["run_dispatched"]
    dispatch = json.loads((control / "dispatch.json").read_text())
    assert Path(dispatch["headroom_file"]).is_relative_to(clean)
    environment = json.loads((control / "f5-environment.json").read_text())
    assert environment == {
        "pythonpath": None,
        "pythonhome": None,
        "budget_path": receipt["ledger_path"],
    }
    assert dispatch["run_id"] == run_id


def test_cli_watch_reads_private_binding_and_enters_bound_capture(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from headroom.cli import app
    from headroom.orchestrator import Policy
    from headroom.verify.reference_config import NumericalReference
    from headroom.watch import watch_command

    root = tmp_path / "project"
    source = root / "scenarios/s1_batch_too_big"
    source.mkdir(parents=True)
    (source / "train.py").write_text("VALUE=1\n")
    profile_path = root / ".cache/final48-allocation/runtime-profile.json"
    options = {
        "target": "fix-oom",
        "search_mode": "until_target",
        "budget_usd": ".30",
        "daily_budget_usd": "6",
        "runtime_profile": str(profile_path),
        "policy": Policy(),
        "allocator_conf": None,
        "numerical_reference": NumericalReference(),
    }
    command = ["python", "train.py"]
    intent = watch.prepare_watch_intent(command, source_root=source, fix_options=options)
    binding, _, _ = activate(root, intent, "watch-s1")
    context = tmp_path / "watch-context.json"
    context.write_text(json.dumps({"binding": binding, "intent": intent}))
    context.chmod(0o600)
    monkeypatch.setenv("HEADROOM_WATCH_FEATURE_CONTEXT", str(context))
    seen = []

    def capture(command, **kwargs):
        return watch_command(command, **(kwargs | {"lab_runner": capture_lab()}))

    def repair(request, **kwargs):
        seen.append(kwargs)
        return {"run_id": kwargs["run_id"], "status": "needs_human", "target_met": False}

    monkeypatch.setattr(watch, "watch_command", capture)
    monkeypatch.setattr(watch, "run_fix", repair)
    # Keep run artifacts in the temporary project; never use the real Watch run root.
    import headroom.watch as ordinary_watch

    monkeypatch.setattr(ordinary_watch, "PROJECT_ROOT", root)
    result = CliRunner().invoke(
        app,
        [
            "watch",
            "--source-root",
            str(source),
            "--runtime-profile",
            str(profile_path),
            "--budget",
            ".30",
            "--daily-budget",
            "6",
            "--",
            *command,
        ],
    )
    assert result.exit_code == 1, result.output
    assert len(seen) == 1 and seen[0]["run_id"] == binding["run_id"]
    assert seen[0]["services"].runtime_factory is None


def test_watch_bound_factory_dispatches_sdk_mock_and_settles_known_cost(bound_watch, monkeypatch):
    import httpx

    from headroom.runtime import build_live_runtime, read_live_profile
    from headroom.store.db import Store

    root, args, intent, binding, _receipt, credential = bound_watch
    calls = []

    def transport(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "offline fixture"},
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )

    def repair(request, *, run_root, run_id, services):
        profile = read_live_profile(request.runtime_profile)
        budget = services.budget_factory(run_id, request, profile)
        budget.open_run(run_id, request.budget_usd, budget_mode=profile.run_budget_mode)
        store = Store(root / "fixture-store.db")
        store.create_run(run_id, {"provenance": "offline_fixture"})
        bundle = build_live_runtime(
            run_id,
            profile=profile,
            budget=budget,
            store=store,
            env_file=credential,
            transport=httpx.MockTransport(transport),
            max_http_retries=0,
        )
        try:
            bundle.client.complete(
                "patcher", [{"role": "user", "content": "Offline fixture"}], max_tokens=10
            )
        finally:
            bundle.close()
            state = budget.close_run(run_id)
            store.close()
        assert state["billing_complete"] is True and state["pending_attempts"] == 0
        return {
            "run_id": run_id,
            "status": "needs_human",
            "target_met": False,
            "provenance": "offline_fixture",
        }

    monkeypatch.setattr(watch, "run_fix", repair)
    result = watch.run_bound_watch(
        **args, intent=intent, allocation_child_binding=binding, lab_runner=capture_lab()
    )
    assert result["fix"]["provenance"] == "offline_fixture"
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["profile", "budget", "source"])
def test_f5_request_must_match_top_level_authorization_before_verification(
    tmp_path, monkeypatch, change
):
    from headroom.cli_execution import prepare_feature_fix_intent, verify_invocation_allocation

    clean, source = clean_fixture(tmp_path)
    request = FixRequest(
        script=str(source / "train.py"),
        source_root=str(source),
        runtime_profile=str(tmp_path / "profile.json"),
        budget_usd=".30",
        daily_budget_usd="6",
    )
    intent = prepare_feature_fix_intent(request, checkout=clean)
    update = {
        "profile": {"runtime_profile": str(tmp_path / "different.json")},
        "budget": {"budget_usd": ".31"},
        "source": {"script": str(source / "different.py")},
    }[change]
    if change == "source":
        (source / "different.py").write_text("VALUE=1\n")
    request = request.model_copy(update=update)
    intent["payload"]["queued_request"] = request.model_dump(mode="json")
    monkeypatch.setattr(
        feature,
        "verify_feature_child_binding",
        lambda *a, **k: pytest.fail("Malformed intent must refuse first"),
    )
    with pytest.raises(ValueError, match="F5"):
        verify_invocation_allocation(
            {"scope": "F5", "slot_id": "clean-s3"}, request, uuid4().hex, feature_intent=intent
        )


@pytest.mark.parametrize("tamper", ["profile", "child_state", "tracked_code", "workload"])
def test_f5_budget_factory_uses_small_scope_and_reverifies_each_reserve(
    tmp_path, monkeypatch, tamper
):
    import sqlite3
    from types import SimpleNamespace

    from headroom.cli_execution import allocation_budget_factory, prepare_feature_fix_intent
    from headroom.ledger_path import BUDGET_DB_ENV
    from headroom.runtime import read_live_profile

    root = tmp_path / "allocation"
    root.mkdir()
    clean, source = clean_fixture(tmp_path)
    request = FixRequest(
        script=str(source / "train.py"),
        source_root=str(source),
        runtime_profile=str(root / ".cache/final48-allocation/runtime-profile.json"),
        budget_usd=".30",
        daily_budget_usd="6",
    )
    intent = prepare_feature_fix_intent(request, checkout=clean)
    binding, receipt, _ = activate(root, intent, "clean-s3")
    monkeypatch.setenv(BUDGET_DB_ENV, receipt["ledger_path"])
    spec = SimpleNamespace(
        allocation_child_binding=binding,
        queued_request=request.model_dump(),
        feature_intent=intent,
        run_id=binding["run_id"],
    )
    budget = allocation_budget_factory(spec)(
        binding["run_id"], request, read_live_profile(request.runtime_profile)
    )
    assert budget.total_limit == __import__("decimal").Decimal(".30")
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "first", ".01")
    budget.settle(binding["run_id"], "first", ".01")
    if tamper == "profile":
        with open(receipt["profile_path"], "a") as handle:
            handle.write(" ")
    elif tamper == "tracked_code":
        with (clean / "headroom/__init__.py").open("a") as handle:
            handle.write("\n# changed after first attempt\n")
    elif tamper == "workload":
        (source / "train.py").write_text("VALUE=2\n")
    else:
        with sqlite3.connect(root / ".cache/final48-allocation-registry.sqlite3") as conn:
            conn.execute(
                "UPDATE feature_children SET state='settled' WHERE run_id=?", (binding["run_id"],)
            )
    with pytest.raises(ValueError):
        budget.reserve(binding["run_id"], "second", ".01")
    assert budget.snapshot(binding["run_id"])["pending_attempts"] == 0


@pytest.mark.parametrize("name", ["torch.py", "json.py"])
def test_f5_rejects_git_ignored_workload_modules_that_lab_would_copy(tmp_path, name):
    from headroom.cli_execution import feature_checkout, prepare_feature_fix_intent

    clean, source = clean_fixture(tmp_path)
    request = FixRequest(script=str(source / "train.py"), source_root=str(source), budget_usd=".30")
    intent = prepare_feature_fix_intent(request, checkout=clean)
    (clean / ".git/info/exclude").write_text("scenarios/s3_eval_no_grad_missing/" + name + "\n")
    (source / name).write_text("raise RuntimeError('must never execute')\n")
    assert (
        subprocess.run(
            ["git", "-C", str(clean), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == ""
    )
    with pytest.raises(ValueError, match="workload"):
        feature_checkout(intent)


def test_bound_watch_context_cannot_capture_twice_even_without_oom(bound_watch):
    root, args, intent, binding, _, _ = bound_watch
    calls = []

    def lab(source, command, **kwargs):
        calls.append(command)
        result = capture_lab()(source, command, **kwargs)
        result.update(status="completed", termination_reason="normal_exit")
        result["execution"]["state"]["ExitCode"] = 0
        return result

    first = watch.run_bound_watch(
        **args, intent=intent, allocation_child_binding=binding, lab_runner=lab
    )
    assert first["watch_id"] == binding["run_id"] and not first["triggered"]
    with pytest.raises(FileExistsError):
        watch.run_bound_watch(
            **args, intent=intent, allocation_child_binding=binding, lab_runner=lab
        )
    assert len(calls) == 1
    other = args | {"run_root": root / "different-run-root"}
    with pytest.raises(ValueError, match="assigned project"):
        watch.run_bound_watch(
            **other, intent=intent, allocation_child_binding=binding, lab_runner=lab
        )
    assert len(calls) == 1
