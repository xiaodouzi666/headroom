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
for key in tuple(os.environ):
    if key.startswith(("NEBIUS_", "TAVILY_", "OPENAI_", "ANTHROPIC_", "HEADROOM_")) or key.endswith(("_API_KEY", "_API_TOKEN")) or key in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
        os.environ.pop(key, None)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["NVIDIA_VISIBLE_DEVICES"] = "void"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def protected(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return False
    path = Path(os.fsdecode(value)).resolve()
    if path.is_relative_to(ROOT):
        relative = path.relative_to(ROOT)
        if relative.parts and (relative.parts[0] == "runs" or relative.parts[0].startswith(".env")):
            return True
        if relative.parts and relative.parts[0] == ".cache":
            if len(relative.parts) < 2 or relative.parts[1] not in {"tokenizers", "upstream"}:
                return True
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


# Closing-only hardening: new final48/public-api paths did not exist in R6.
def closing_audit(event, args):
    if event == "open" and args and protected(args[0]):
        raise PermissionError("Closing regression denies production file access")
    if event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate"}:
        if args and protected(args[0]):
            raise PermissionError("Closing regression denies production mutations")
    if event in {"os.rename", "os.link", "os.symlink"}:
        if any(protected(value) for value in args[:2]):
            raise PermissionError("Closing regression denies production mutations")
    if event == "subprocess.Popen":
        command = args[1]
        if not isinstance(command, (list, tuple)):
            raise PermissionError("Closing regression requires explicit subprocess argv")
        words = [str(value) for value in command]
        executable = Path(words[0]).name if words else ""
        if executable in {"sh", "bash", "zsh", "curl", "wget", "ssh", "scp", "nvidia-smi", "systemctl", "service", "tailscale"}:
            raise PermissionError("Closing regression denies external network/service commands")
        if executable == "git" and any(word in {"fetch", "pull", "push", "ls-remote"} for word in words[1:]):
            raise PermissionError("Closing regression denies remote Git commands")
        if executable == "git" and "clone" in words and any("://" in word or word.startswith("git@") for word in words):
            raise PermissionError("Closing regression permits local Git fixtures only")
        if executable == "docker":
            if any(word in {"pull", "push", "build", "login", "exec"} for word in words[1:]):
                raise PermissionError("Closing regression denies Docker network/build/exec")
            if any(word in {"create", "run"} for word in words[1:]):
                isolated = "--network=none" in words or any(words[i:i+2] == ["--network", "none"] for i in range(len(words)-1))
                if not isolated:
                    raise PermissionError("Closing regression requires CPU Docker network none")
                if "--privileged" in words or any(word.startswith("--device") or word.startswith("--runtime") for word in words):
                    raise PermissionError("Closing regression denies privileged/device Docker")
sys.addaudithook(closing_audit)

_original_guard_probe = guard_probe
def closing_guard_probe(channel=None):
    checks = _original_guard_probe()
    for name, relative in (
        ("final48_profile", ".cache/final48-allocation/runtime-profile.json"),
        ("final48_registry", ".cache/final48-allocation-registry.sqlite3"),
        ("public_api_database", "runs/public-api/headroom.db"),
        ("private_environment_variant", ".env.private"),
    ):
        try:
            (ROOT / relative).read_bytes()
        except PermissionError:
            checks[name] = "denied"
        else:
            raise AssertionError("Closing guard missing: " + name)
    for name, command in (
        ("gpu_subprocess", ["docker", "run", "--gpus", "all"]),
        ("networked_container", ["docker", "run", "fixture"]),
        ("service_command", ["systemctl", "--user", "status", "headroom-api"]),
    ):
        try:
            audit("subprocess.Popen", (None, command, None, None))
            closing_audit("subprocess.Popen", (None, command, None, None))
        except PermissionError:
            checks[name] = "denied"
        else:
            raise AssertionError("Closing process guard missing: " + name)
    if channel is not None:
        channel.send(checks)
        channel.close()
    return checks
guard_probe = closing_guard_probe


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
    if os.environ.get("CLOSING_GUARD_PROBE_ONLY") == "1":
        raise SystemExit(0)
    import pytest

    raise SystemExit(pytest.main(["-q", *sys.argv[1:]]))
