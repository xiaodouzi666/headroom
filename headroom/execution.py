"""Replayable Python entrypoints without importing or executing user code.

The argv is authoritative. A source path locates editable code; it never replaces
a module invocation. Unsupported launchers remain capture-only in Watch.
"""

import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

PYTHON_COMMANDS = frozenset(
    {"python", "python3", "python3.12", "/opt/venv/bin/python", "/opt/venv/bin/python3"}
)


@dataclass(frozen=True)
class PythonCommand:
    kind: str
    argv: tuple[str, ...]
    python_flags: tuple[str, ...] = ()
    script: str | None = None
    script_args: tuple[str, ...] = ()
    capture_expected: bool = True
    repair_supported: bool = False
    repair_reason: str | None = None
    module: str | None = None
    args_index: int | None = None


def command_argv(command: str | Sequence[str]) -> tuple[str, ...]:
    parts = shlex.split(command) if isinstance(command, str) else command
    if isinstance(parts, (str, bytes)) or not isinstance(parts, Sequence):
        raise TypeError("Command must be an argv sequence or a quoted command string")
    if (
        not parts
        or len(parts) > 256
        or any(not isinstance(arg, str) or "\x00" in arg for arg in parts)
        or not parts[0]
        or sum(len(arg.encode("utf-8")) for arg in parts) > 65536
    ):
        raise ValueError("Command argv must fit 256 entries and 64 KiB without NUL bytes")
    return tuple(parts)


def parse_command(command: Sequence[str]) -> PythonCommand:
    if isinstance(command, (str, bytes)):
        raise TypeError("Watch expects argv, not a shell string")
    argv = command_argv(command)
    if argv[0] not in PYTHON_COMMANDS:
        return PythonCommand("command", argv, repair_reason="COMMAND_REPAIR_UNSUPPORTED")
    flags, index, capture, unsupported = [], 1, True, False
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            break
        if token == "-" or not token.startswith("-"):
            break
        if token.startswith("-c"):
            return PythonCommand(
                "python_inline",
                argv,
                tuple(flags),
                capture_expected=capture,
                repair_reason="PYTHON_INLINE_REPAIR_UNSUPPORTED",
            )
        if token.startswith("-m"):
            module = token[2:]
            if not module:
                index += 1
                module = argv[index] if index < len(argv) else ""
            arguments = argv[index + 1 :]
            reason = _reason(capture, unsupported, arguments)
            if not module or not all(part.isidentifier() for part in module.split(".")):
                reason = "INVALID_MODULE_ENTRYPOINT"
            return PythonCommand(
                "python_module",
                argv,
                tuple(flags),
                script_args=arguments,
                capture_expected=capture,
                repair_supported=reason is None,
                repair_reason=reason,
                module=module,
                args_index=index + 1,
            )
        flags.append(token)
        if token in {"-W", "-X", "--check-hash-based-pycs"}:
            index += 1
            if index >= len(argv):
                unsupported = True
            else:
                flags.append(argv[index])
        elif token.startswith(("-W", "-X", "--check-hash-based-pycs=")):
            pass
        elif token.startswith("--"):
            unsupported = True
        elif all(letter in "bBdE iIOPqRsSuvx".replace(" ", "") for letter in token[1:]):
            if any(letter in token[1:] for letter in "EIS"):
                capture = False
        else:
            unsupported = True
        index += 1
    if index >= len(argv) or argv[index] == "-":
        return PythonCommand(
            "python_stdin_or_option",
            argv,
            tuple(flags),
            capture_expected=capture,
            repair_reason="NO_SCRIPT_REPAIR_ENTRYPOINT",
        )
    token, arguments = argv[index], argv[index + 1 :]
    script = token.removeprefix("/source/")
    path = PurePosixPath(script)
    reason = _reason(capture, unsupported, arguments)
    if path.is_absolute() or ".." in path.parts or "\\" in script or path.suffix != ".py":
        reason = "SCRIPT_OUTSIDE_REPAIR_SOURCE"
    return PythonCommand(
        "python_script",
        argv,
        tuple(flags),
        str(path),
        arguments,
        capture,
        reason is None,
        reason,
        args_index=index + 1,
    )


def _reason(capture, unsupported, arguments):
    if not capture:
        return "SITECUSTOMIZE_DISABLED"
    if unsupported:
        return "INTERPRETER_OPTION_UNSUPPORTED"
    if len(arguments) > 100:
        return "REPAIR_ARGV_LIMIT"
    return None


def source_entrypoint(parsed: PythonCommand, available: set[str]) -> str | None:
    """Locate a normal local import target from the captured source manifest."""
    if parsed.kind == "python_script":
        return parsed.script if parsed.script in available else None
    if parsed.kind != "python_module" or not parsed.module:
        return None
    module = parsed.module.replace(".", "/")
    # A regular package precedes a same-name module; modules precede namespace packages.
    if f"{module}/__init__.py" in available:
        target = f"{module}/__main__.py"
    elif f"{module}.py" in available:
        target = f"{module}.py"
    else:
        target = f"{module}/__main__.py"
    return target if target in available else None


@dataclass(frozen=True)
class PreparedCommand:
    source_root: Path
    script: Path
    script_args: tuple[str, ...]
    execution_argv: tuple[str, ...]
    execution_entrypoint: dict | None = None


def prepare_local_command(
    source_root: Path, command: str | Sequence[str], *, execution_entrypoint: dict | None = None
) -> PreparedCommand:
    source = Path(source_root).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Command source_root must be a directory")
    argv = command_argv(command)
    if execution_entrypoint is not None:
        script, arguments = _wrapper_target(source, argv, execution_entrypoint)
        return PreparedCommand(source, script, arguments, argv, execution_entrypoint)
    parsed = parse_command(argv)
    if not parsed.repair_supported:
        raise ValueError(parsed.repair_reason)
    if parsed.kind == "python_module":
        module = parsed.module.replace(".", "/")
        candidates = (f"{module}/__init__.py", f"{module}/__main__.py", f"{module}.py")
    else:
        candidates = (parsed.script,)
    available = {name for name in candidates if (source / name).is_file()}
    relative = source_entrypoint(parsed, available)
    if relative is None:
        raise ValueError("REPAIR_SOURCE_UNAVAILABLE_OR_LINKED")
    script = source / relative
    if script.is_symlink() or any(
        (source / parent).is_symlink() for parent in Path(relative).parents
    ):
        raise ValueError("REPAIR_SOURCE_UNAVAILABLE_OR_LINKED")
    if not script.resolve().is_relative_to(source):
        raise ValueError("REPAIR_SOURCE_UNAVAILABLE_OR_LINKED")
    return PreparedCommand(source, script, parsed.script_args, argv)


def replay_argv(
    command: Sequence[str], script_args: Sequence[str], *, execution_entrypoint: dict | None = None
) -> list[str]:
    """Replace only target arguments; interpreter options and -m remain immutable."""
    if execution_entrypoint is not None:
        argv = command_argv(command)
        if (
            execution_entrypoint.get("kind") != "captured_wrapper"
            or tuple(execution_entrypoint.get("root_argv", ())) != argv
            or execution_entrypoint.get("argv_override_supported") is not True
        ):
            raise ValueError("WRAPPER_TARGET_ARGV_OVERRIDE_UNSUPPORTED")
        command_argv(["python", "target.py", *script_args])
        if len(script_args) > 100:
            raise ValueError("REPAIR_ARGV_LIMIT")
        return list(argv)
    parsed = parse_command(command)
    if not parsed.repair_supported or parsed.args_index is None:
        raise ValueError(parsed.repair_reason or "Command cannot be replayed")
    argv = [*parsed.argv[: parsed.args_index], *script_args]
    updated = parse_command(argv)
    if not updated.repair_supported or updated.args_index != parsed.args_index:
        raise ValueError("Invalid replacement target argv")
    return argv


def _source_relative(value, *, allow_root=False):
    """Map an absolute in-container path to the copied /source tree."""
    if not isinstance(value, str) or "\x00" in value or "\\" in value:
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    try:
        relative = path.relative_to("/source")
    except ValueError:
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE") from None
    if not allow_root and str(relative) == ".":
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    return str(relative)


def _container_path(cwd, value):
    import posixpath

    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    return posixpath.normpath(value if value.startswith("/") else posixpath.join(cwd, value))


def captured_wrapper_descriptor(command, capture, manifest):
    """Resolve a single captured Python main, never parse or execute a shell program."""
    argv = command_argv(command)
    if parse_command(argv).kind != "command":
        raise ValueError("CAPTURE_WRAPPER_REQUIRED")
    inventory = capture.get("execution_capture", {})
    entry = capture.get("execution_entrypoint") or {}
    if inventory.get("single_python_entrypoint") is not True:
        raise ValueError(inventory.get("reason") or "CAPTURE_ENTRYPOINT_AMBIGUOUS")
    if entry.get("schema_version") != 1 or entry.get("complete") is not True:
        raise ValueError("CAPTURE_ENTRYPOINT_INCOMPLETE")
    original = command_argv(entry.get("orig_argv"))
    # The runtime observation must come from the mounted interpreter, even when
    # its argv[0] was a shell alias. Never import a target to discover an entrypoint.
    executable = entry.get("executable", "")
    if executable not in PYTHON_COMMANDS and executable != "/opt/venv/bin/python3.12":
        raise ValueError("CAPTURE_INTERPRETER_UNSUPPORTED")
    child = parse_command(["python", *original[1:]])
    if not child.repair_supported and child.repair_reason != "SCRIPT_OUTSIDE_REPAIR_SOURCE":
        raise ValueError(child.repair_reason or "CAPTURE_PYTHON_ENTRYPOINT_UNSUPPORTED")
    cwd = entry.get("startup_cwd")
    cwd_relative = _source_relative(cwd, allow_root=True)
    source_relative = _source_relative(entry.get("main_file"))
    if PurePosixPath(source_relative).suffix != ".py":
        raise ValueError("CAPTURE_PYTHON_ENTRYPOINT_UNSUPPORTED")
    files = manifest.get("source", {}).get("files", {})
    if source_relative not in files:
        raise ValueError("CAPTURE_SOURCE_UNAVAILABLE_OR_LINKED")
    if child.kind == "python_script":
        expected = _source_relative(_container_path(cwd, original[child.args_index - 1]))
        if entry.get("module") is not None:
            raise ValueError("CAPTURE_MODULE_MISMATCH")
    elif child.kind == "python_module":
        prefix = "" if cwd_relative == "." else cwd_relative + "/"
        local_files = {name.removeprefix(prefix) for name in files if name.startswith(prefix)}
        relative = source_entrypoint(child, local_files)
        if relative is None:
            raise ValueError("CAPTURE_MODULE_SOURCE_UNAVAILABLE")
        expected = prefix + relative
        if entry.get("module") not in {child.module, child.module + ".__main__"}:
            raise ValueError("CAPTURE_MODULE_MISMATCH")
    else:
        raise ValueError("CAPTURE_PYTHON_ENTRYPOINT_UNSUPPORTED")
    if expected != source_relative:
        raise ValueError("CAPTURE_ENTRYPOINT_SOURCE_MISMATCH")
    startup = entry.get("startup_argv")
    effective = entry.get("effective_startup_argv")
    if (
        not isinstance(startup, list)
        or startup[1:] != list(child.script_args)
        or not isinstance(effective, list)
        or not effective
    ):
        raise ValueError("CAPTURE_TARGET_ARGV_MISMATCH")
    command_argv(["python", "target.py", *effective[1:]])
    digest = files[source_relative].get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("CAPTURE_SOURCE_HASH_UNAVAILABLE")
    return {
        "schema_version": 1,
        "kind": "captured_wrapper",
        "root_argv": list(argv),
        "source_relative": source_relative,
        "startup_cwd_relative": cwd_relative,
        "python_argv": list(original),
        "script_args": list(child.script_args),
        "module": entry.get("module"),
        "source_sha256": digest,
        "cli_changes_supported": True,
        "argv_override_supported": True,
        "effective_script_args": effective[1:],
        "capture_pid": entry.get("pid"),
    }


def _wrapper_target(source, argv, descriptor):
    if (
        not isinstance(descriptor, dict)
        or descriptor.get("schema_version") != 1
        or descriptor.get("kind") != "captured_wrapper"
        or tuple(descriptor.get("root_argv", ())) != argv
        or descriptor.get("cli_changes_supported") is not True
        or descriptor.get("argv_override_supported") is not True
        or parse_command(argv).kind != "command"
    ):
        raise ValueError("WRAPPER_EXECUTION_DESCRIPTOR_MISMATCH")
    relative = descriptor.get("source_relative")
    if (
        not isinstance(relative, str)
        or PurePosixPath(relative).is_absolute()
        or ".." in PurePosixPath(relative).parts
        or "\\" in relative
        or PurePosixPath(relative).suffix != ".py"
    ):
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    cwd = descriptor.get("startup_cwd_relative")
    if (
        not isinstance(cwd, str)
        or not cwd
        or PurePosixPath(cwd).is_absolute()
        or ".." in PurePosixPath(cwd).parts
        or "\\" in cwd
    ):
        raise ValueError("CAPTURE_ENTRYPOINT_OUTSIDE_SOURCE")
    command_argv(descriptor.get("python_argv"))
    args = descriptor.get("script_args")
    if not isinstance(args, list) or len(args) > 100:
        raise ValueError("WRAPPER_TARGET_ARGV_INVALID")
    command_argv(["python", relative, *args])
    script = source / relative
    if (
        not script.is_file()
        or script.is_symlink()
        or any((source / parent).is_symlink() for parent in Path(relative).parents)
        or not script.resolve().is_relative_to(source)
    ):
        raise ValueError("CAPTURE_SOURCE_UNAVAILABLE_OR_LINKED")
    return script, tuple(args)


def prepare_captured_command(source_root, command, capture, manifest):
    """Create a replay descriptor only from the captured source and runtime main."""
    import hashlib

    source = Path(source_root).resolve(strict=True)
    argv = command_argv(command)
    descriptor = captured_wrapper_descriptor(argv, capture, manifest)
    script, args = _wrapper_target(source, argv, descriptor)
    if hashlib.sha256(script.read_bytes()).hexdigest() != descriptor["source_sha256"]:
        raise ValueError("CAPTURE_SOURCE_HASH_MISMATCH")
    return PreparedCommand(source, script, args, argv, descriptor)


def same_wrapper_entrypoint(expected, observed):
    """Source bytes may change; execution target, interpreter argv and cwd may not."""
    keys = (
        "kind",
        "root_argv",
        "source_relative",
        "startup_cwd_relative",
        "python_argv",
        "script_args",
        "module",
        "cli_changes_supported",
        "argv_override_supported",
    )
    return isinstance(observed, dict) and all(
        expected.get(key) == observed.get(key) for key in keys
    )
