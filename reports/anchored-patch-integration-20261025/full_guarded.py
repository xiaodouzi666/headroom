"""Full offline regression: guard credentials, live databases, INET and GPU in spawn too."""

import builtins
import io
import json
import multiprocessing
import os
import socket
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path("/home/xiaodouzi/workspace/headroom")
PROTECTED = {
    ROOT / ".env",
    ROOT / ".cache/tokenfactory-runtime.json",
    ROOT / ".cache/budget.db",
    ROOT / "runs/headroom.db",
    ROOT / "runs/acceptance/headroom.db",
}
for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY"):
    os.environ.pop(key, None)
os.environ["CUDA_VISIBLE_DEVICES"] = ""


def protected(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return False
    path = Path(os.fsdecode(value)).resolve()
    return path in PROTECTED or (
        path.name.endswith(("-wal", "-shm")) and path.with_name(path.name[:-4]) in PROTECTED
    )


def safe_open(original):
    def guarded(file, *args, **kwargs):
        if protected(file):
            raise PermissionError("Integration cannot access live credentials/profile/databases")
        return original(file, *args, **kwargs)

    return guarded


builtins.open = safe_open(builtins.open)
io.open = safe_open(io.open)
os.open = safe_open(os.open)


def denied(*_args, **_kwargs):
    raise PermissionError("Integration denies real DNS/INET")


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


def audit(event, args):
    if event == "sqlite3.connect":
        value = str(args[0])
        if value.startswith("file:"):
            value = unquote(urlparse(value).path)
        if protected(value):
            raise PermissionError("Integration cannot open production databases")
    elif event == "subprocess.Popen":
        command = args[1]
        if isinstance(command, (list, tuple)) and any(
            str(item) == "--gpus" or str(item).startswith("--gpus=") for item in command
        ):
            raise PermissionError("Integration permits CPU Docker only")


sys.addaudithook(audit)


def guard_probe(channel=None):
    import sqlite3

    checks = {}
    for name, action in (
        ("real_env", lambda: (ROOT / ".env").read_bytes()),
        ("real_profile", lambda: (ROOT / ".cache/tokenfactory-runtime.json").read_bytes()),
        (
            "real_db",
            lambda: sqlite3.connect(
                "file:" + str(ROOT / ".cache/budget.db") + "?mode=ro", uri=True
            ),
        ),
        ("dns", lambda: socket.getaddrinfo("example.invalid", 443)),
    ):
        try:
            action()
        except PermissionError:
            checks[name] = "denied"
        else:
            raise AssertionError("Independent guard missing: " + name)
    checks["api_key_env_absent"] = all(
        name not in os.environ for name in ("NEBIUS_API_KEY", "TAVILY_API_KEY")
    )
    if channel is not None:
        channel.send(checks)
        channel.close()
    return checks


if __name__ == "__main__":
    parent = guard_probe()
    context = multiprocessing.get_context("spawn")
    incoming, outgoing = context.Pipe(duplex=False)
    process = context.Process(target=guard_probe, args=(outgoing,))
    process.start()
    outgoing.close()
    if not incoming.poll(20):
        process.terminate()
        process.join(5)
        raise RuntimeError("Spawn guard self-check timed out")
    spawned = incoming.recv()
    incoming.close()
    process.join(10)
    if process.exitcode != 0 or spawned != parent:
        raise RuntimeError("Spawn guard self-check failed")
    print(json.dumps({"guard_parent": parent, "guard_spawn": spawned}), flush=True)
    import pytest

    raise SystemExit(pytest.main(["-q", *sys.argv[1:]]))
