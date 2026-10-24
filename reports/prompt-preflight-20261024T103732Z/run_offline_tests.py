import socket


def denied(*args, **kwargs):
    raise AssertionError("Independent process network guard: no network")


socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
import pytest

raise SystemExit(pytest.main(["-q", "tests/test_prompt_preflight.py"]))
