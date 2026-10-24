"""Reproduce command replay checks with a process-wide network guard."""

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TIKTOKEN_CACHE_DIR"] = str(ROOT / ".cache/tiktoken")


def denied(*args, **kwargs):
    raise AssertionError("Independent command-replay check: network forbidden")


socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
import pytest

DEFAULTS = [
    "tests/test_multicapture.py",
    "tests/test_wrapper_execution.py",
    "tests/test_watch.py",
    "tests/test_command_replay.py",
    "tests/test_evidence.py",
    "tests/test_cli.py",
    "tests/test_verify_runner.py",
]

raise SystemExit(pytest.main(["-q", *(sys.argv[1:] or DEFAULTS), "--tb=short"]))
