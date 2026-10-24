"""Replay the offline integration checks with a spawn-compatible network guard."""

import socket
import sys


def refuse(*args, **kwargs):
    raise AssertionError("Independent process-wide network guard: no external access")


socket.getaddrinfo = refuse
socket.create_connection = refuse
socket.socket.connect = refuse
socket.socket.connect_ex = refuse

if __name__ == "__main__":
    import pytest

    raise SystemExit(
        pytest.main(
            sys.argv[1:]
            or [
                "-q",
                "tests/test_llm_client.py",
                "tests/test_llm_cost.py",
                "tests/test_llm_router.py",
                "tests/test_annotate.py",
                "tests/test_orchestrator.py",
                "tests/test_api.py",
                "tests/test_api_deadline.py",
            ]
        )
    )
