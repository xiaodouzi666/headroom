"""Shared-ledger configuration, exercised only against isolated offline databases."""

import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from headroom import budget as budget_module
from headroom import cli, orchestrator
from headroom.acceptance.common import acceptance_run
from headroom.api.app import ApiSettings, create_app
from headroom.api.availability import AvailabilityMonitor, read_local_budget
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.ledger_path import (
    BUDGET_DB_ENV,
    LedgerPathError,
    select_budget_database,
)
from headroom.runtime import RuntimeNotReady


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in (BUDGET_DB_ENV, "HEADROOM_DAILY_BUDGET_USD", "HEADROOM_RUN_BUDGET_USD"):
        monkeypatch.delenv(name, raising=False)


def initialized(tmp_path, name="shared.db"):
    path = tmp_path / name
    BudgetLedger(path, daily_limit="2", total_limit="2")
    return path


def select(root, path):
    return select_budget_database(root, environ={BUDGET_DB_ENV: str(path)})


def test_default_selection_keeps_creation_behavior_and_does_not_open(tmp_path):
    choice = select_budget_database(tmp_path, environ={})
    assert choice.path == tmp_path / ".cache/budget.db"
    assert choice.require_existing is False
    assert not choice.path.exists()
    BudgetLedger(choice.path, require_existing=choice.require_existing)
    assert choice.path.is_file()


@pytest.mark.parametrize("invalid", ["", " ", "relative.db", "~/ledger.db", "/no-such-ledger"])
def test_invalid_explicit_selection_never_uses_default(tmp_path, invalid):
    with pytest.raises(LedgerPathError):
        select(tmp_path, invalid)
    assert not (tmp_path / ".cache").exists()


@pytest.mark.parametrize("variant", ["parent", "duplicate_separator", "dot", "space"])
def test_noncanonical_paths_are_rejected(tmp_path, variant):
    path = initialized(tmp_path)
    value = {
        "parent": str(tmp_path / ".." / tmp_path.name / path.name),
        "duplicate_separator": str(tmp_path) + "//" + path.name,
        "dot": str(tmp_path) + "/./" + path.name,
        "space": " " + str(path),
    }[variant]
    with pytest.raises(LedgerPathError):
        select(tmp_path / "clone", value)


@pytest.mark.parametrize("kind", ["leaf", "parent"])
def test_any_symlink_component_is_rejected(tmp_path, kind):
    real = tmp_path / "real"
    real.mkdir()
    path = initialized(real)
    if kind == "leaf":
        alias = tmp_path / "alias.db"
        alias.symlink_to(path)
    else:
        parent = tmp_path / "alias"
        parent.symlink_to(real, target_is_directory=True)
        alias = parent / path.name
    with pytest.raises(LedgerPathError, match="symlink"):
        select(tmp_path / "clone", alias)


@pytest.mark.parametrize(
    "kind", ["empty", "garbage", "unrelated", "view", "incomplete", "directory", "fifo"]
)
def test_only_initialized_regular_ledgers_are_accepted(tmp_path, kind):
    path = tmp_path / "input"
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind in {"empty", "garbage"}:
        path.write_bytes(b"" if kind == "empty" else b"not sqlite")
    else:
        with sqlite3.connect(path) as conn:
            if kind == "view":
                conn.execute("CREATE VIEW budget_runs AS SELECT 'id' AS id")
            elif kind == "incomplete":
                conn.execute("CREATE TABLE budget_runs(id TEXT)")
            else:
                conn.execute("CREATE TABLE unrelated(value TEXT)")
    before = path.read_bytes() if path.is_file() else None
    with pytest.raises(LedgerPathError):
        select(tmp_path / "clone", path)
    if before is not None:
        assert path.read_bytes() == before
    assert not (tmp_path / "clone/.cache").exists()


def test_existing_path_uri_encodes_reserved_filename_characters(tmp_path):
    path = initialized(tmp_path, "ledger ?# ü.db")
    choice = select(tmp_path / "clone", path)
    ledger = BudgetLedger(choice.path, require_existing=True)
    ledger.open_run("encoded", "0.1")
    assert ledger.close_run("encoded")["total_actual_usd"] == "0"


def test_selection_is_immutable_after_environment_changes(tmp_path, monkeypatch):
    first = initialized(tmp_path, "first.db")
    second = initialized(tmp_path, "second.db")
    monkeypatch.setenv(BUDGET_DB_ENV, str(first))
    choice = select_budget_database(tmp_path / "clone")
    monkeypatch.setenv(BUDGET_DB_ENV, str(second))
    assert choice.path == first and choice.require_existing


def test_disappearance_between_validation_and_sqlite_open_never_creates(tmp_path, monkeypatch):
    path = initialized(tmp_path)
    real_validate = budget_module.validate_existing_ledger_path

    def remove_after_validation(value, **kwargs):
        checked = real_validate(value, **kwargs)
        checked.unlink()
        return checked

    monkeypatch.setattr(budget_module, "validate_existing_ledger_path", remove_after_validation)
    with pytest.raises(LedgerPathError):
        BudgetLedger(path, require_existing=True)
    assert not path.exists()


def test_existing_mode_rechecks_schema_before_writes(tmp_path):
    path = initialized(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE budget_attempts")
    before = path.read_bytes()
    with pytest.raises(LedgerPathError):
        BudgetLedger(path, require_existing=True)
    assert path.read_bytes() == before


def test_two_instances_keep_history_and_unknown_charges(tmp_path):
    path = initialized(tmp_path)
    a = BudgetLedger(path, daily_limit="2", total_limit="2", require_existing=True)
    b = BudgetLedger(path, daily_limit="2", total_limit="2", require_existing=True)
    a.open_run("old", "0.5")
    a.reserve("old", "unknown", "0.2")
    a.settle("old", "unknown", None)
    a.close_run("old")
    assert b.snapshot("old")["conservative_charge_usd"] == "0.2"
    assert b.snapshot("old")["unknown_attempts"] == 1
    with pytest.raises(BudgetExceeded):
        b.open_run("new", "0.1")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("SELECT count(*) FROM budget_attempts").fetchone()[0] == 1


@pytest.mark.parametrize("daily,total", [("1", "2"), ("2", "1")])
def test_full_provider_reservation_obeys_existing_day_and_total(tmp_path, daily, total):
    path = initialized(tmp_path)
    b = BudgetLedger(path, require_existing=True, daily_limit=daily, total_limit=total)
    b.open_run("run", "0.6", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded):
        b.reserve("run", "too_large", "1.1")
    assert b.snapshot("run")["pending_attempts"] == 0


def test_two_instances_cannot_admit_same_funds_twice(tmp_path):
    path = initialized(tmp_path)
    a = BudgetLedger(path, require_existing=True, daily_limit="1", total_limit="1")
    b = BudgetLedger(path, require_existing=True, daily_limit="1", total_limit="1")
    a.open_run("first", "0.6")
    with pytest.raises(BudgetExceeded):
        b.open_run("second", "0.6")
    a.close_run("first")
    b.open_run("second", "0.6")


def monitor_for(root, monkeypatch, profile=None):
    settings = ApiSettings(project_root=root)
    if profile is None:
        profile = SimpleNamespace(
            authorized_total_usd="2",
            base_url="https://api.tokenfactory.us-central1.nebius.com/v1/",
        )
    monitor = AvailabilityMonitor(settings, enabled=False, profile_loader=lambda path: profile)
    return settings, monitor


def test_api_http_reads_same_database_and_retains_selection(tmp_path, monkeypatch):
    path = initialized(tmp_path)
    ledger = BudgetLedger(path, daily_limit="2", total_limit="2")
    ledger.open_run("history", "0.2")
    ledger.reserve("history", "one", "0.2")
    ledger.settle("history", "one", "0.1")
    ledger.close_run("history")
    clone = tmp_path / "clone"
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "1")
    settings, monitor = monitor_for(clone, monkeypatch)
    monkeypatch.setenv(BUDGET_DB_ENV, str(tmp_path / "not-selected.db"))
    with TestClient(
        create_app(
            settings, worker=lambda *a, **kw: pytest.fail("No job"), availability_monitor=monitor
        )
    ) as client:
        result = client.get("/api/health").json()["local_budget"]
    assert result["status"] == "available"
    assert result["remaining_usd"] == "0.9"
    assert not (clone / ".cache/budget.db").exists()


@pytest.mark.parametrize("when", ["selection", "after_selection"])
def test_invalid_or_disappearing_explicit_api_ledger_stays_unknown(tmp_path, monkeypatch, when):
    path = initialized(tmp_path)
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    if when == "selection":
        path.unlink()
    _, monitor = monitor_for(tmp_path / "clone", monkeypatch)
    if when == "after_selection":
        path.unlink()
    try:
        result = monitor.snapshot()["local_budget"]
    finally:
        monitor.close()
    assert result["status"] == "unknown"
    assert result["remaining_usd"] is None
    assert not path.exists()


def test_readonly_existing_requirement_never_treats_missing_as_fresh_pool(tmp_path):
    path = tmp_path / "missing.db"
    result = read_local_budget(path, daily_limit="1", total_limit="1", require_existing=True)
    assert result["status"] == "unknown" and result["remaining_usd"] is None
    assert not path.exists()


@pytest.mark.parametrize("valid", [True, False])
def test_real_cli_routes_normal_preflight_to_explicit_ledger(tmp_path, monkeypatch, valid):
    from test_runtime_budget import fixture_runtime

    clone = tmp_path / "clone"
    clone.mkdir()
    source = clone / "input.py"
    source.write_text("print('offline')\n")
    path = initialized(tmp_path) if valid else tmp_path / "missing.db"
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    seen = []
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "0.9")
    monkeypatch.setattr(orchestrator, "PROJECT_ROOT", clone)
    monkeypatch.setattr(orchestrator, "read_live_profile", lambda *a: profile)

    def stop_before_client(run_id, **kwargs):
        seen.append((kwargs["budget"].path, kwargs["budget"].daily_limit))
        raise RuntimeNotReady("Offline boundary reached before creating a provider client")

    monkeypatch.setattr(orchestrator, "build_live_runtime", stop_before_client)
    result = CliRunner().invoke(
        cli.app,
        [
            "fix",
            str(source),
            "--runtime-profile",
            str(clone / "profile.json"),
            "--daily-budget",
            "0.9",
        ],
    )
    assert result.exit_code != 0
    assert len(seen) == int(valid)
    if valid:
        assert seen[0][0] == path and str(seen[0][1]) == "0.9"
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT count(*) FROM budget_runs").fetchone()[0] == 1
            assert conn.execute("SELECT count(*) FROM budget_attempts").fetchone()[0] == 0
    assert not (clone / ".cache/budget.db").exists()


def test_acceptance_uses_shared_fixture_ledger_without_model_dispatch(tmp_path, monkeypatch):
    from test_client_acceptance import runtime_fixture

    profile, env = runtime_fixture(tmp_path)
    path = initialized(tmp_path)
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    with acceptance_run(
        case_id="shared-path",
        artifact_dir=tmp_path / "artifact",
        profile_path=profile,
        run_limit_usd="0.1",
        daily_limit_usd="1",
        execute=True,
        live_authorized=True,
        project_root=tmp_path,
        transport=httpx.MockTransport(lambda request: pytest.fail("No inference")),
        env_file=env,
    ) as session:
        assert session.budget.path == path
        assert session.budget.require_existing is True
    record = json.loads((tmp_path / "artifact/runtime.json").read_text())
    assert record["calls"] == [] and record["cleanup_errors"] == []
    assert not (tmp_path / ".cache/budget.db").exists()


def test_offline_acceptance_cannot_follow_external_shared_ledger(tmp_path, monkeypatch):
    from test_client_acceptance import runtime_fixture

    fixture = tmp_path / "fixture"
    profile, env = runtime_fixture(fixture)
    path = initialized(tmp_path)
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    real_connect = sqlite3.connect
    external_opens = []

    def forbid_external_connection(database, *args, **kwargs):
        value = os.fspath(database)
        decoded = unquote(urlsplit(value).path) if value.startswith("file:") else value
        if Path(decoded).resolve() == path:
            external_opens.append(value)
            pytest.fail("Offline acceptance must not open an external ledger, even read-only")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", forbid_external_connection)
    with (
        pytest.raises(ValueError, match="fixture-owned"),
        acceptance_run(
            case_id="external",
            artifact_dir=fixture / "artifact",
            profile_path=profile,
            run_limit_usd="0.1",
            daily_limit_usd="1",
            execute=True,
            live_authorized=True,
            project_root=fixture,
            transport=httpx.MockTransport(lambda request: pytest.fail("No inference")),
            env_file=env,
        ),
    ):
        pytest.fail("External ledger must never be opened by offline acceptance")
    assert external_opens == []
    with real_connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM budget_runs").fetchone()[0] == 0


@pytest.mark.parametrize("consumer", ["writer", "api"])
def test_replaced_valid_ledger_is_not_silently_adopted(tmp_path, monkeypatch, consumer):
    path = initialized(tmp_path)
    other = initialized(tmp_path, "other.db")
    monkeypatch.setenv(BUDGET_DB_ENV, str(path))
    ledger = BudgetLedger(path, require_existing=True)
    _, monitor = monitor_for(tmp_path / "clone", monkeypatch)
    other.replace(path)
    try:
        if consumer == "writer":
            with pytest.raises(LedgerPathError, match="identity"):
                ledger.open_run("wrong-pool", "0.1")
        else:
            value = monitor.snapshot()["local_budget"]
            assert value["status"] == "unknown" and value["remaining_usd"] is None
    finally:
        monitor.close()
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM budget_runs").fetchone()[0] == 0


def test_selector_identity_stays_bound_through_admission(tmp_path):
    path = initialized(tmp_path)
    other = initialized(tmp_path, "other.db")
    choice = select(tmp_path / "clone", path)
    other.replace(path)
    with pytest.raises(LedgerPathError, match="identity"):
        BudgetLedger(
            choice.path,
            require_existing=choice.require_existing,
            expected_identity=choice.file_identity,
        )


def test_initialized_legacy_schema_keeps_history_when_migrated(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE budget_runs (id TEXT PRIMARY KEY, day TEXT, limit_usd TEXT, status TEXT, halt_reason TEXT)"
        )
        conn.execute(
            "CREATE TABLE budget_attempts (id TEXT PRIMARY KEY, run_id TEXT, upper_usd TEXT, charged_usd TEXT, actual_usd TEXT, settled INTEGER)"
        )
        conn.execute(
            "INSERT INTO budget_runs VALUES ('history',?,'1','closed',NULL)",
            (budget_module.current_utc_day(),),
        )
        conn.execute("INSERT INTO budget_attempts VALUES ('one','history','0.2','0.1','0.1',1)")
    choice = select(tmp_path / "clone", path)
    b = BudgetLedger(choice.path, require_existing=True, expected_identity=choice.file_identity)
    assert b.snapshot("history")["total_actual_usd"] == "0.1"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM budget_runs").fetchone()[0] == 1
        assert conn.execute("SELECT actual_usd FROM budget_attempts").fetchone()[0] == "0.1"


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_existing_sidecars_must_be_regular_nonsymlinks(tmp_path, suffix, kind):
    path = initialized(tmp_path)
    sidecar = path.with_name(path.name + suffix)
    sidecar.unlink(missing_ok=True)
    if kind == "symlink":
        target = tmp_path / "unrelated"
        target.write_text("not used")
        sidecar.symlink_to(target)
    elif kind == "directory":
        sidecar.mkdir()
    else:
        os.mkfifo(sidecar)
    with pytest.raises(LedgerPathError, match="sidecar"):
        select(tmp_path / "clone", path)
