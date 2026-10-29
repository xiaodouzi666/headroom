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


def actual_path(value, dir_fd=None):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return value
    value = os.fsdecode(value)
    if os.path.isabs(value) or dir_fd is None or dir_fd == -1:
        return value
    try:
        base = os.readlink("/proc/self/fd/" + str(dir_fd))
        if not os.path.isabs(base) or base.endswith(" (deleted)"):
            raise ValueError("invalid directory descriptor")
        return Path(base) / value
    except (OSError, TypeError, ValueError) as error:
        raise PermissionError("Closing regression cannot resolve dir_fd") from error


def safe_open(original):
    def guarded(file, *args, **kwargs):
        if protected(actual_path(file, kwargs.get('dir_fd'))):
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
def docker_options(words):
    # Parse only the Docker command prefix. The workload argv starts after image.
    index = 2
    options = []
    flags = {"--read-only", "--rm", "--init", "-i", "-t"}
    takes_value = {
        "--name", "--network", "--cap-drop", "--security-opt", "--memory",
        "--cpus", "--pids-limit", "--user", "--tmpfs", "--workdir",
        "--log-driver", "--entrypoint", "--mount", "--env", "--label", "--ulimit",
    }
    while index < len(words):
        word = words[index]
        if not word.startswith("-"):
            if not word:
                raise PermissionError("Closing regression requires an explicit image")
            return options
        name = word.split("=", 1)[0]
        if name in {"--gpus", "--device", "--device-cgroup-rule", "--device-read-bps",
                    "--device-write-bps", "--privileged", "--runtime"}:
            raise PermissionError("Closing regression denies privileged/device Docker")
        if name in flags:
            options.append((name, None))
            index += 1
        elif name in takes_value:
            if "=" in word:
                value = word.split("=", 1)[1]
                index += 1
            else:
                if index + 1 >= len(words):
                    raise PermissionError("Closing regression refuses incomplete Docker options")
                value = words[index + 1]
                index += 2
            options.append((name, value))
        else:
            raise PermissionError("Closing regression refuses unknown Docker host options")
    raise PermissionError("Closing regression requires an explicit image")


def closing_audit(event, args):
    # Python's open audit event omits dir_fd. Relative opens are checked by the
    # wrappers above, which possess it; absolute C-level opens are checked here.
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.isabs(os.fsdecode(args[0])) and protected(args[0]):
            raise PermissionError("Closing regression denies production file access")
    if event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate"}:
        index = 1 if event in {"os.remove", "os.rmdir"} else 2
        fd = args[index] if len(args) > index else None
        if args and protected(actual_path(args[0], fd)):
            raise PermissionError("Closing regression denies production mutations")
    if event in {"os.rename", "os.link"}:
        if any(protected(actual_path(args[i], args[i+2] if len(args)>i+2 else None)) for i in (0,1)):
            raise PermissionError("Closing regression denies production mutations")
    if event == "os.symlink" and protected(actual_path(args[1],args[2] if len(args)>2 else None)):
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
            if len(words)<2 or words[1] in {"pull","push","build","login","exec"}:
                raise PermissionError("Closing regression denies Docker network/build/exec")
            if words[1] in {"create","run"}:
                options=docker_options(words)
                if ("--network","none") not in options:
                    raise PermissionError("Closing regression requires CPU Docker network none")
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

    # Resolve relative operations against their actual descriptor, not cwd.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="headroom-guard-probe-") as temporary:
        descriptor=os.open(temporary,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.mkdir("runs",dir_fd=descriptor)
            os.mkdir(".cache",dir_fd=descriptor)
            fd=os.open(".cache",os.O_RDONLY|os.O_DIRECTORY,dir_fd=descriptor)
            os.close(fd)
            checks["temporary_dir_fd_paths"]="allowed"
        finally:
            os.close(descriptor)
    descriptor=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
    try:
        for label,callback in (
            ("production_env_via_dir_fd",lambda: os.open(".env",os.O_RDONLY,dir_fd=descriptor)),
            ("production_runs_via_dir_fd",lambda: closing_audit("os.mkdir",("runs/probe",0o700,descriptor))),
            ("production_cache_via_dir_fd",lambda: closing_audit("os.mkdir",(".cache/probe",0o700,descriptor))),
            ("unresolved_dir_fd",lambda: actual_path("relative",99999999)),
        ):
            try: callback()
            except PermissionError: checks[label]="denied"
            else: raise AssertionError("Closing dir_fd guard missing: "+label)
    finally:
        os.close(descriptor)
    closing_audit("subprocess.Popen",(None,["docker","create","--network","none","sha256:fixture","python","train.py","--device","cpu"],None,None))
    checks["cpu_workload_device_argument"]="allowed"
    for words in (
        ["docker","create","--network","none","--device","/dev/nvidia0","sha256:fixture","python"],
        ["docker","create","--network","none","--runtime=nvidia","sha256:fixture","python"],
        ["docker","create","--network","host","sha256:fixture","python"],
    ):
        try: closing_audit("subprocess.Popen",(None,words,None,None))
        except PermissionError: pass
        else: raise AssertionError("Closing Docker boundary guard missing")
    checks["host_device_runtime_network_options"]="denied"

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
