"""Patch pipeline tests use MockTransport, temporary local Git indexes and no target execution."""

import dataclasses
import difflib
import hashlib
import json
import socket
from pathlib import Path

import httpx
import pytest

from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter
from headroom.patch import PatchEngine, PatchProposal, apply_proposal, validate_diff


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Real network forbidden in patch tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def diff_for(before, after, name="train.py"):
    return "".join(
        difflib.unified_diff(
            before.splitlines(True),
            after.splitlines(True),
            fromfile="a/" + name,
            tofile="b/" + name,
        )
    )


def proposal(before, after, **extra):
    return {
        "diff": diff_for(before, after),
        "env_changes": {},
        "cli_changes": [],
        "notes": [],
        **extra,
    }


@pytest.fixture
def project(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("n_layer = 12\nmax_steps = 20\nx = 1\n")
    return source


def patch_config():
    models = candidate_models()
    models["super"] = dataclasses.replace(
        models["super"],
        capabilities=VerifiedCapabilities(
            reasoning_method="chat_template_kwargs", evidence="offline test fixture"
        ),
    )
    return RuntimeConfig(models=models)


def mock_router(payloads, requests, completion_tokens=100):
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        payload = payloads[min(len(requests) - 1, len(payloads) - 1)]
        return httpx.Response(
            200,
            json={
                "id": "offline-patch",
                "object": "chat.completion",
                "created": 0,
                "model": SUPER_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": completion_tokens,
                    "total_tokens": 200 + completion_tokens,
                },
            },
        )

    return LLMRouter(
        TokenFactoryClient(config=patch_config(), transport=httpx.MockTransport(handler))
    )


def test_applies_in_fresh_git_copy_and_original_unchanged(project, tmp_path):
    before = (project / "train.py").read_text()
    after = before.replace("x = 1", "x = 2  # release temporary earlier")
    original = hashlib.sha256((project / "train.py").read_bytes()).hexdigest()
    result = apply_proposal(project, proposal(before, after), work_root=tmp_path / "work")
    assert result.applied, dataclasses.asdict(result)
    assert (Path(result.candidate_dir) / "train.py").read_text() == after
    assert hashlib.sha256((project / "train.py").read_bytes()).hexdigest() == original
    assert not (project / ".git").exists()
    assert (Path(result.candidate_dir) / ".git").is_dir()
    assert "--3way" in result.attempts[0].apply_command
    assert result.attempts[0].compile_exit_code == 0
    assert result.runtime_verified is False
    assert Path(result.artifact_dir, "source-manifest.json").exists()


def test_secret_files_and_symlinks_are_not_copied(project, tmp_path):
    (project / ".env").write_text("OFFLINE_PLACEHOLDER=never-copy\n")
    (project / "token.json").write_text("{}")
    (project / "linked.py").symlink_to(tmp_path / "external.py")
    before = (project / "train.py").read_text()
    result = apply_proposal(
        project, proposal(before, before.replace("x = 1", "x = 2")), work_root=tmp_path / "work"
    )
    assert result.applied
    assert not Path(result.candidate_dir, ".env").exists()
    assert not Path(result.candidate_dir, "token.json").exists()
    assert not Path(result.candidate_dir, "linked.py").exists()


@pytest.mark.parametrize(
    "name",
    [
        "../outside.py",
        "/tmp/outside.py",
        ".git/config",
        ".env",
        "credentials.json",
        "foo/../../outside.py",
    ],
)
def test_unsafe_patch_paths_never_apply(project, tmp_path, name):
    payload = {"diff": diff_for("x=1\n", "x=2\n", name), "env_changes": {}, "cli_changes": []}
    result = apply_proposal(project, payload, work_root=tmp_path / "work")
    assert not result.applied and result.reason == "UNSAFE_OR_INVALID_PATCH"


def test_conflicting_git_headers_are_rejected(project):
    patch = "diff --git a/evil.py b/evil.py\n" + diff_for("x=1\n", "x=2\n", "train.py")
    with pytest.raises(ValueError):
        validate_diff(patch, project)


def test_symlink_target_and_deletion_rejected(project, tmp_path):
    (project / "escape.py").symlink_to(tmp_path / "other.py")
    with pytest.raises(ValueError):
        validate_diff(diff_for("x=1\n", "x=2\n", "escape.py"), project)
    deletion = "--- a/train.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x=1\n"
    with pytest.raises(ValueError):
        validate_diff(deletion, project)


def test_no_git_fails_closed_but_keeps_candidate(project, tmp_path, monkeypatch):
    before = (project / "train.py").read_text()
    monkeypatch.setattr("headroom.patch.shutil.which", lambda *a, **k: None)
    result = apply_proposal(
        project, proposal(before, before.replace("x = 1", "x = 2")), work_root=tmp_path / "work"
    )
    assert result.reason == "GIT_UNAVAILABLE"
    assert Path(result.candidate_dir).exists()


def test_compile_never_imports_or_executes_target(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    marker = tmp_path / "executed"
    before = f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\nx = 1\n"
    (source / "train.py").write_text(before)
    result = apply_proposal(
        source, proposal(before, before.replace("x = 1", "x = 2")), work_root=tmp_path / "work"
    )
    assert result.applied and result.attempts[0].compile_exit_code == 0
    assert not marker.exists()


def test_compile_invalid_return_is_rejected_without_execution(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("x=1\n")
    result = apply_proposal(source, proposal("x=1\n", "return 1\n"), work_root=tmp_path / "work")
    assert result.reason == "COMPILE_FAILED"
    assert result.attempts[0].compile_exit_code != 0


def test_env_only_and_argv_overrides(project, tmp_path):
    result = apply_proposal(
        project,
        {
            "diff": "",
            "env_changes": {"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
            "cli_changes": ["--batch_size", "4", "--gradient_accumulation_steps", "8"],
        },
        work_root=tmp_path / "work",
        base_cli=["--batch_size", "32", "--max_steps", "20"],
    )
    assert result.applied
    assert result.effective_cli == (
        "--batch_size",
        "4",
        "--max_steps",
        "20",
        "--gradient_accumulation_steps",
        "8",
    )
    assert (
        Path(result.artifact_dir, "env.sh")
        .read_text()
        .startswith("export PYTORCH_CUDA_ALLOC_CONF=")
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"diff": "", "env_changes": {}, "cli_changes": [], "unexpected": True},
        {"diff": 5, "env_changes": {}, "cli_changes": []},
        {"diff": "", "env_changes": {"PYTHONPATH": "/tmp/evil"}, "cli_changes": []},
        {"diff": "", "env_changes": {}, "cli_changes": ["python", "-c", "malicious"]},
    ],
)
def test_strict_proposal_and_environment_rejections(project, tmp_path, payload):
    result = apply_proposal(project, payload, work_root=tmp_path / "work")
    assert not result.applied


def test_real_router_generates_patch_with_super_and_4000_cap(project, tmp_path):
    before = (project / "train.py").read_text()
    requests = []
    router = mock_router([proposal(before, before.replace("x = 1", "x = 2"))], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1", "type": "code"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied
    assert (
        len(requests) == 1
        and requests[0]["model"] == SUPER_MODEL
        and requests[0]["max_tokens"] == 4000
    )
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.attempts[0].llm_usage["completion_tokens"] == 100
    assert result.attempts[0].llm_cost["usd"] is None
    assert (
        json.loads(Path(result.artifact_dir, "result.json").read_text())["runtime_verified"]
        is False
    )


def test_policy_repair_against_original_with_failure_history(project, tmp_path):
    before = (project / "train.py").read_text()
    requests = []
    router = mock_router(
        [
            proposal(before, before.replace("n_layer = 12", "n_layer = 6")),
            proposal(before, before.replace("x = 1", "x = 2")),
        ],
        requests,
    )
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(result.attempts) == 2
    assert all(r["chat_template_kwargs"] == {"enable_thinking": False} for r in requests)
    assert result.attempts[0].reason == "MODEL_SHRUNK"
    assert all(Path(item.candidate_dir).exists() for item in result.attempts)
    assert len({item.candidate_dir for item in result.attempts}) == 2
    assert "MODEL_SHRUNK" in requests[1]["messages"][-1]["content"]
    assert (project / "train.py").read_text() == before


def test_initial_plus_three_repairs_maximum(project, tmp_path):
    requests = []
    bad = {"diff": diff_for("not the original\n", "x = 2\n"), "env_changes": {}, "cli_changes": []}
    router = mock_router([bad], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied and len(requests) == 4 and len(result.attempts) == 4
    assert all(item.reason == "PATCH_APPLY_FAILED" for item in result.attempts)
    assert len({item.candidate_dir for item in result.attempts}) == 4


def test_compile_failure_can_be_repaired(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("x=1\n")
    requests = []
    router = mock_router([proposal("x=1\n", "return 1\n"), proposal("x=1\n", "x=2\n")], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            source, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and result.attempts[0].reason == "COMPILE_FAILED"


def test_default_live_disabled_stops_without_repair_storm(project, tmp_path):
    with TokenFactoryClient(config=patch_config()) as client:
        result = PatchEngine(LLMRouter(client)).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    assert not result.applied and len(result.attempts) == 1
    assert "disabled" in result.attempts[0].detail


def test_completion_over_cap_is_not_applied_or_retried(project, tmp_path):
    before = (project / "train.py").read_text()
    requests = []
    router = mock_router(
        [proposal(before, before.replace("x = 1", "x = 2"))], requests, completion_tokens=4001
    )
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied and len(requests) == 1
    assert "PATCH_COMPLETION_LIMIT_EXCEEDED" in result.attempts[0].detail


def test_constructor_limits_and_proposal_schema():
    with TokenFactoryClient() as client:
        router = LLMRouter(client)
        with pytest.raises(ValueError):
            PatchEngine(router, max_repairs=4)
        with pytest.raises(ValueError):
            PatchEngine(router, max_completion_tokens=4001)
    assert (
        PatchProposal.model_validate({"diff": "", "env_changes": {}, "cli_changes": []}).notes == []
    )


def test_source_secret_is_rejected_before_model_dispatch_or_copy(project, tmp_path):
    (project / "train.py").write_text("token='" + "tvly-" + "c" * 24 + "'\n")
    requests = []
    router = mock_router([{"diff": "", "env_changes": {}, "cli_changes": []}], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied and result.reason == "EMBEDDED_CREDENTIAL"
    assert not requests and not Path(result.artifact_dir, "baseline").exists()
    assert "c" * 24 not in Path(result.artifact_dir, "result.json").read_text()


def test_empty_source_selection_returns_a_rejection(project, tmp_path):
    requests = []
    router = mock_router([{"diff": "", "env_changes": {}, "cli_changes": []}], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work", source_files=[]
        )
    finally:
        router.client.close()
    assert result.reason == "SOURCE_CONTEXT_REJECTED" and not requests


def test_copied_source_is_rescanned_before_dispatch(project, tmp_path, monkeypatch):
    from headroom.patch import copy_source

    requests = []

    def changed_copy(*args, **kwargs):
        manifest = copy_source(*args, **kwargs)
        path = Path(args[1]) / "train.py"
        path.chmod(0o644)
        path.write_text("token='" + "tvly-" + "d" * 24 + "'\n")
        return manifest

    monkeypatch.setattr("headroom.patch.copy_source", changed_copy)
    router = mock_router([{"diff": "", "env_changes": {}, "cli_changes": []}], requests)
    try:
        result = PatchEngine(router).generate_and_apply(
            project, {"fix_id": "f1"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.reason == "EMBEDDED_CREDENTIAL" and not requests
    assert "d" * 24 not in Path(result.artifact_dir, "result.json").read_text()


def test_pinned_nanogpt_patch_preserves_equals_cli_and_original(tmp_path):
    source = Path(__file__).resolve().parents[1] / ".cache/upstream/nanoGPT"
    if not source.is_dir():
        pytest.skip("Pinned local nanoGPT checkout not present")
    requests = []
    router = mock_router(
        [
            {
                "diff": "",
                "env_changes": {"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
                "cli_changes": ["--batch_size", "4", "--gradient_accumulation_steps", "8"],
            }
        ],
        requests,
    )
    try:
        result = PatchEngine(router).generate_and_apply(
            source,
            {"fix_id": "f1"},
            work_root=tmp_path / "work",
            source_files=["train.py", "model.py"],
            base_cli=["--batch_size=32", "--gradient_accumulation_steps=1"],
            source_profile="pinned_nanogpt",
            sandboxed=True,
        )
    finally:
        router.client.close()
    assert result.applied, dataclasses.asdict(result)
    assert result.effective_cli == ("--batch_size=4", "--gradient_accumulation_steps=8")
    inner = Path(result.patch_path).parent
    assert json.loads((inner / "cli.json").read_text())["effective"] == list(result.effective_cli)
    assert len(requests) == 1


def test_model_cannot_edit_immutable_nanogpt_configurator(tmp_path):
    source = Path(__file__).resolve().parents[1] / ".cache/upstream/nanoGPT"
    if not source.is_dir():
        pytest.skip("Pinned local nanoGPT checkout not present")
    before = (source / "configurator.py").read_text()
    after = before + "\n# Memory patch tries to edit immutable reviewed loader.\n"
    payload = {
        "diff": diff_for(before, after, "configurator.py"),
        "env_changes": {},
        "cli_changes": [],
    }
    requests = []
    router = mock_router([payload], requests)
    try:
        result = PatchEngine(router, max_repairs=0).generate_and_apply(
            source,
            {"fix_id": "f1"},
            work_root=tmp_path / "work",
            source_files=["train.py", "model.py"],
            source_profile="pinned_nanogpt",
            sandboxed=True,
        )
    finally:
        router.client.close()
    assert not result.applied and result.reason == "SOURCE_PROFILE_UNVERIFIED"
    assert len(requests) == 1
    assert (
        json.loads(Path(result.patch_path).with_name("result.json").read_text())["status"]
        == "rejected"
    )
