"""CLI errors/status are structured and must not echo credentials."""

import json
import sys

import pytest

from headroom.monitoring import MonitorStateError
from scripts import check_health


@pytest.mark.parametrize(
    "result,expected",
    [
        ({"healthy": True, "alert_due": False}, 0),
        ({"healthy": False, "alert_due": False}, 1),
        ({"healthy": False, "alert_due": True}, 2),
    ],
)
def test_exit_status_and_explicit_notification_switch(monkeypatch, capsys, result, expected):
    calls = []

    def check(**kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(check_health, "check", check)
    monkeypatch.setattr(
        sys, "argv", ["check_health.py", "--state", "/tmp/health-test.json", "--notify"]
    )
    with pytest.raises(SystemExit) as error:
        check_health.main()
    assert error.value.code == expected and calls[0]["notify"] is True
    assert json.loads(capsys.readouterr().out) == result


def test_state_error_does_not_claim_delivery_or_print_private_io_exception(monkeypatch, capsys):
    def fail(**kwargs):
        assert kwargs["notify"] is False
        raise OSError("private-url-and-token-must-not-appear")

    monkeypatch.setattr(check_health, "check", fail)
    monkeypatch.setattr(sys, "argv", ["check_health.py"])
    with pytest.raises(SystemExit) as error:
        check_health.main()
    assert error.value.code == 3
    output = capsys.readouterr().out
    assert "private-url" not in output
    assert json.loads(output)["notification_sent"] is None


def test_fixed_state_error_code_is_visible(monkeypatch, capsys):
    def fail(**kwargs):
        raise MonitorStateError("check_already_running")

    monkeypatch.setattr(check_health, "check", fail)
    monkeypatch.setattr(sys, "argv", ["check_health.py"])
    with pytest.raises(SystemExit):
        check_health.main()
    assert json.loads(capsys.readouterr().out)["reason"] == "check_already_running"
