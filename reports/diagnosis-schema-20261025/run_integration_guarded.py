"""Private test runner: no real account keys or INET sockets, including spawn children."""

import builtins
import io
import os
import socket
from pathlib import Path

PROJECT = Path("/home/xiaodouzi/workspace/headroom")
_real_open, _io_open = builtins.open, io.open


def safe_open(original):
    def guarded(file, *args, **kwargs):
        if (
            isinstance(file, (str, bytes, os.PathLike))
            and Path(os.fsdecode(file)).resolve() == PROJECT / ".env"
        ):
            raise PermissionError("Offline suite cannot read real project credentials")
        return original(file, *args, **kwargs)

    return guarded


builtins.open, io.open = safe_open(_real_open), safe_open(_io_open)
os.open = safe_open(os.open)
for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
    os.environ.pop(key, None)


def denied(*args, **kwargs):
    raise AssertionError("Independent offline guard denied real DNS/INET connection")


_real_connect, _real_connect_ex = socket.socket.connect, socket.socket.connect_ex


def connect(self, address):
    return (
        denied()
        if self.family in (socket.AF_INET, socket.AF_INET6)
        else _real_connect(self, address)
    )


def connect_ex(self, address):
    return (
        denied()
        if self.family in (socket.AF_INET, socket.AF_INET6)
        else _real_connect_ex(self, address)
    )


socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
if __name__ == "__main__":
    import pytest

    raise SystemExit(
        pytest.main(
            [
                "-q",
                "tests/test_diagnosis_schema_constraints.py",
                "tests/test_diagnose_schema.py",
                "tests/test_diagnose_contract.py",
                "tests/test_diagnosis_acceptance.py",
                "tests/test_llm_router.py",
                "tests/test_orchestrator.py",
                "tests/test_bounded_search.py",
                "tests/test_actual_usage_budget.py",
                "tests/test_verification_feedback.py",
                "tests/test_runtime_budget.py",
            ]
        )
    )
