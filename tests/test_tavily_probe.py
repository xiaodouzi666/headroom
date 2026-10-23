"""Offline-only T0.5 tests. Every attempted real network request fails the test."""

import importlib.util
import json
from pathlib import Path

import pytest
import requests

SPEC = importlib.util.spec_from_file_location(
    "tavily_probe", Path(__file__).resolve().parents[1] / "scripts/probe_tavily.py"
)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
CANARY = "offline-only-credential-+value"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests must not send HTTP requests")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f'TAVILY_API_KEY="{CANARY}"\nNEBIUS_API_KEY=second-offline-only-secret\n')
    path.chmod(0o600)
    return path


class FixtureClient:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        if self.failure == "exception":
            raise RuntimeError(f"Authorization: Bearer {CANARY}; credential={CANARY}")
        return {
            "query": kwargs["query"],
            "results": [
                {
                    "url": PROBE.CHECKPOINT_URL,
                    "title": f"fixture {CANARY}",
                    "content": "fixture search excerpt",
                    "score": 0.9,
                }
            ],
            "response_time": 0.01,
            "usage": {"credits": 1 if kwargs["search_depth"] == "basic" else 2},
            "request_id": "offline-fixture",
            "headers": {"Authorization": CANARY},
        }

    def extract(self, **kwargs):
        self.calls.append(("extract", kwargs))
        if self.failure == "partial" and kwargs["urls"] == [PROBE.ISSUE_URL]:
            return {
                "results": [],
                "failed_results": [{"url": PROBE.ISSUE_URL, "error": f"fixture denial {CANARY}"}],
                "usage": {"credits": 0},
            }
        return {
            "results": [{"url": kwargs["urls"][0], "raw_content": "fixture page"}],
            "failed_results": [],
            "usage": {"credits": 0},
            "response_time": 0.01,
        }


def test_default_dry_run_never_constructs_client_and_is_not_acceptance(env_file, tmp_path):
    def forbidden_client(key):
        raise AssertionError("client constructed without --execute")

    code, path, report = PROBE.run_probe(
        env_file=env_file, report_dir=tmp_path / "reports", client_factory=forbidden_client
    )
    assert code == 78
    assert report["status"] == "not_executed"
    assert report["attempted_requests"] == 0
    assert not report["api_checks_passed"] and not report["task_accepted"]
    assert all(item["status"] == "not_executed" for item in report["operations"])
    assert CANARY not in path.read_text()


def test_missing_key_blocks_execute_and_ignores_ambient_key(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", CANARY)
    missing = tmp_path / "missing.env"
    code, _, report = PROBE.run_probe(execute=True, env_file=missing, report_dir=tmp_path)
    assert code == 78 and report["reason"] == "missing_credential"
    assert report["attempted_requests"] == 0


def test_nonprivate_env_blocks_execute(env_file, tmp_path):
    env_file.chmod(0o644)
    code, _, report = PROBE.run_probe(execute=True, env_file=env_file, report_dir=tmp_path)
    assert code == 78 and report["reason"] == "env_permissions_must_be_600"
    assert report["attempted_requests"] == 0


def test_offline_success_records_four_operations_without_secrets(env_file, tmp_path):
    client = FixtureClient()
    code, path, report = PROBE.run_probe(
        execute=True,
        env_file=env_file,
        report_dir=tmp_path,
        client_factory=lambda key: client,
    )
    assert code == 0 and report["api_checks_passed"]
    assert not report["task_accepted"]  # Live evidence plus FEEDBACK is still required.
    assert report["attempted_requests"] == 4
    assert [method for method, _ in client.calls] == ["search", "search", "extract", "extract"]
    assert [args["search_depth"] for method, args in client.calls if method == "search"] == [
        "basic",
        "advanced",
    ]
    assert {args["urls"][0] for method, args in client.calls if method == "extract"} == {
        PROBE.CHECKPOINT_URL,
        PROBE.ISSUE_URL,
    }
    assert all(args["include_usage"] for _, args in client.calls)
    assert report["credits_total_reported"] == 3
    assert all(entry["elapsed_seconds"] >= 0 for entry in report["operations"])
    serialized = path.read_text()
    assert CANARY not in serialized and "second-offline-only-secret" not in serialized
    assert "fixture page" not in serialized  # No raw extracted page content is saved.
    assert "response_schema" in serialized and "[REDACTED]" in serialized
    assert json.loads(serialized) == report


@pytest.mark.parametrize("failure", ["partial", "exception"])
def test_failed_operation_is_nonzero_and_error_text_is_redacted(env_file, tmp_path, failure):
    code, path, report = PROBE.run_probe(
        execute=True,
        env_file=env_file,
        report_dir=tmp_path,
        client_factory=lambda key: FixtureClient(failure),
    )
    assert code == 1 and not report["api_checks_passed"]
    assert any(item["status"] == "failed" for item in report["operations"])
    assert CANARY not in path.read_text()


@pytest.mark.parametrize(
    "response", [None, [], {}, {"results": []}, {"results": [{"url": "x", "content": "y"}]}]
)
def test_malformed_search_is_not_success(response):
    assert PROBE.classify_response(PROBE.operations()[0], response)[0] == "failed"


def test_extract_wrong_url_and_partial_failure_are_not_success():
    operation = PROBE.operations()[2]
    valid = {"results": [{"url": PROBE.CHECKPOINT_URL, "raw_content": "fixture"}]}
    assert PROBE.classify_response(operation, valid) == ("succeeded", None)
    assert (
        PROBE.classify_response(
            operation, {**valid, "failed_results": [{"url": PROBE.CHECKPOINT_URL}]}
        )[0]
        == "failed"
    )
    assert (
        PROBE.classify_response(
            operation, {"results": [{"url": PROBE.ISSUE_URL, "raw_content": "fixture"}]}
        )[0]
        == "failed"
    )


def test_missing_credit_value_stays_unknown():
    summary = PROBE.response_summary({"results": []}, ())
    assert summary["credits"] is None and summary["credits_source"] == "not_reported"


def test_reports_are_unique_even_with_repeated_dry_run(env_file, tmp_path):
    first = PROBE.run_probe(env_file=env_file, report_dir=tmp_path)[1]
    second = PROBE.run_probe(env_file=env_file, report_dir=tmp_path)[1]
    assert first != second and first.is_file() and second.is_file()
