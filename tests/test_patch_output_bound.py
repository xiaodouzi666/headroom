"""Offline regressions for bounded patch output and incremental name checking."""

import json
import socket
import subprocess
from pathlib import Path

import httpx
import pytest
from patch_fixture_helpers import anchored_fixture
from test_actual_usage_budget import reviewed_fixture
from test_patch import mock_router, proposal

from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.patch import PatchEngine, apply_proposal
from headroom.patch_names import check_undefined_names
from headroom.runtime import build_live_runtime
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real network is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_only_new_undefined_names_are_rejected():
    result = check_undefined_names({"a.py": "x = 1\n"}, {"a.py": "x = missing\n"})
    assert result["status"] == "failed"
    assert result["new_diagnostics"][0]["message"] == "Undefined name \u0060missing\u0060"


def test_preexisting_dynamic_names_survive_unrelated_edits_and_line_shifts():
    before = 'exec("dynamic_value = 1")\nprint(dynamic_value)\nx = 1\n'
    after = '# shifted\nexec("dynamic_value = 1")\nprint(dynamic_value)\nx = 2\n'
    result = check_undefined_names({"a.py": before}, {"a.py": after})
    assert result["status"] == "passed"
    assert len(result["preserved_existing_diagnostics"]) == 1


def test_copying_an_existing_undefined_reference_is_new_debt():
    before = "print(dynamic_value)\n"
    result = check_undefined_names({"a.py": before}, {"a.py": before + before})
    assert result["status"] == "failed"
    assert len(result["preserved_existing_diagnostics"]) == len(result["new_diagnostics"]) == 1


def test_new_occurrence_of_old_name_on_different_line_is_not_grandfathered():
    before = "print(dynamic_value)\n"
    result = check_undefined_names({"a.py": before}, {"a.py": "print(dynamic_value + 1)\n"})
    assert result["status"] == "failed"


def test_old_diagnostic_does_not_cover_another_lexical_scope():
    before = "def first():\n    print(dynamic_value)\n"
    after = "def second():\n    print(dynamic_value)\n"
    result = check_undefined_names({"a.py": before}, {"a.py": after})
    assert result["status"] == "failed"
    assert result["preserved_existing_diagnostics"] == []


def test_noqa_cannot_hide_new_undefined_name():
    result = check_undefined_names({"a.py": "x = 1\n"}, {"a.py": "x = missing  # noqa: F821\n"})
    assert result["status"] == "failed"


def test_checker_is_isolated_and_uses_stdin_without_candidate_execution(monkeypatch):
    calls = []

    def checked(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    monkeypatch.setattr("headroom.patch_names.subprocess.run", checked)
    result = check_undefined_names({"a.py": "x = 1\n"}, {"a.py": "x = 2\n"})
    assert result["status"] == "passed" and len(calls) == 2
    for argv, kwargs in calls:
        assert argv[1:4] == ["-I", "-m", "ruff"]
        assert "--isolated" in argv and "--no-cache" in argv and "--ignore-noqa" in argv
        assert argv[-1] == "-" and kwargs["input"].startswith("x = ")
        assert kwargs["timeout"] == 30
        assert "PYTHONPATH" not in kwargs["env"]
        assert kwargs["cwd"] != Path("a.py").parent


def test_missing_checker_fails_closed(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing Ruff runtime")

    monkeypatch.setattr("headroom.patch_names.subprocess.run", missing)
    result = check_undefined_names({"a.py": "x=1\n"}, {"a.py": "x=2\n"})
    assert result["status"] == "error" and result["reason"] == "NAME_CHECK_UNAVAILABLE"


@pytest.mark.parametrize(
    "code,stdout",
    [(2, "[]"), (0, "not-json"), (1, "[]"), (0, "[{}]"), (1, '[{"code":"OTHER"}]')],
)
def test_invalid_checker_output_is_not_a_pass(monkeypatch, code, stdout):
    monkeypatch.setattr(
        "headroom.patch_names.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], code, stdout, ""),
    )
    result = check_undefined_names({"a.py": "x=1\n"}, {"a.py": "x=2\n"})
    assert result["status"] == "error"


def test_new_unquoted_flag_caught_after_compile_without_target_run(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    before = 'import argparse\nparser = argparse.ArgumentParser()\nparser.add_argument("--size")\n'
    after = before.replace('"--size"', "--chunks")
    (source / "train.py").write_text(before)
    result = apply_proposal(source, proposal(before, after), work_root=tmp_path / "work")
    assert not result.applied and result.reason == "NEW_UNDEFINED_NAME"
    assert result.attempts[0].compile_exit_code == 0
    assert "chunks" in result.attempts[0].detail
    inner = Path(result.patch_path).parent
    receipt = json.loads((inner / "name-check.json").read_text())
    assert receipt["status"] == "failed"
    assert (source / "train.py").read_text() == before


def test_name_error_feedback_reuses_existing_bounded_repair_loop(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    requests = []
    router = mock_router([proposal(before, "x = missing\n"), proposal(before, "x = 2\n")], requests)
    try:
        result = PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "offline"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(result.attempts) == len(requests) == 2
    assert result.attempts[0].reason == "NEW_UNDEFINED_NAME"
    assert "NEW_UNDEFINED_NAME" in json.dumps(requests[1])
    assert all(p["chat_template_kwargs"] == {"enable_thinking": False} for p in requests)


def budgeted_patch(tmp_path, *, total="3", finish="stop"):
    profile = reviewed_fixture(tmp_path)
    budget = BudgetLedger(tmp_path / "own-budget.db", total_limit=total, daily_limit=total)
    budget.open_run("run", "0.6", budget_mode="actual_usage")
    store = Store(tmp_path / "own-store.db")
    store.create_run("run")
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    requests, pending = [], []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        pending.append(budget.snapshot("run"))
        content = json.dumps(anchored_fixture(proposal(before, "x = 2\n"), payload))
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 4000 if finish == "length" else 100,
                    "total_tokens": 4100 if finish == "length" else 200,
                    "prompt_tokens_details": {"cached_tokens": 0},
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    bundle = build_live_runtime(
        "run",
        profile=profile,
        budget=budget,
        store=store,
        env_file=tmp_path / ".env",
        transport=httpx.MockTransport(respond),
    )
    try:
        try:
            result = PatchEngine(bundle.router, max_repairs=0).generate_and_apply(
                source, {"fix_id": "offline"}, work_root=tmp_path / "work"
            )
        except BudgetExceeded as error:
            result = error
        rows = store.llm_calls("run")
    finally:
        bundle.close()
        store.close()
    return result, requests, pending, rows


def test_real_sdk_wire_turns_thinking_off_without_clamping_reservation(tmp_path):
    result, requests, pending, rows = budgeted_patch(tmp_path)
    assert result.applied and len(requests) == len(rows) == 1
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert requests[0]["max_tokens"] == 4000
    assert pending[0]["reserved_or_actual_usd"] == "1.056576"
    assert rows[0]["provider_cost_upper_usd"] == "1.056576"
    assert rows[0]["request_evidence"]["payload"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }


def test_insufficient_global_pool_does_not_dispatch_even_when_thinking_is_off(tmp_path):
    result, requests, _, rows = budgeted_patch(tmp_path, total="1")
    assert isinstance(result, BudgetExceeded)
    assert requests == [] and rows == []


def test_length_remains_rejected_even_with_complete_visible_json(tmp_path):
    result, requests, _, rows = budgeted_patch(tmp_path, finish="length")
    assert not result.applied and result.reason == "LLM_RESPONSE_REJECTED"
    assert len(requests) == len(rows) == 1
    assert result.attempts[0].compile_exit_code is None
    response = json.loads(Path(result.attempts[0].response_artifact).read_text())
    assert response["finish_reason"] == "length" and response["validation_reason"] == "truncated"


def test_checker_unavailable_stops_without_requesting_model_repairs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    requests = []
    router = mock_router([proposal(before, "x = 2\n")], requests)
    monkeypatch.setattr(
        "headroom.patch.check_undefined_names",
        lambda *args: {
            "status": "error",
            "reason": "NAME_CHECK_UNAVAILABLE",
            "new_diagnostics": [],
            "detail": "checker missing",
        },
    )
    try:
        result = PatchEngine(router).generate_and_apply(
            source, {"fix_id": "offline"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied and result.reason == "NAME_CHECK_UNAVAILABLE"
    assert len(result.attempts) == len(requests) == 1
