"""Spawn-safe independent guards for offline interface regressions."""

import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TIKTOKEN_CACHE_DIR"] = os.path.join(ROOT, ".cache/tiktoken")
sys.path.insert(0, ROOT)


def denied(*args, **kwargs):
    raise AssertionError("Independent DNS/socket guard: external access forbidden")


socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied


def no_real_env(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes)):
        path = os.path.abspath(os.fsdecode(args[0]))
        if path == os.path.join(ROOT, ".env"):
            raise AssertionError("Independent audit guard: real project .env access forbidden")


sys.addaudithook(no_real_env)
if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main(sys.argv[1:]))
