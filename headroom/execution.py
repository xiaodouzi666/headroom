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


def prepare_local_command(source_root: Path, command: str | Sequence[str]) -> PreparedCommand:
    source = Path(source_root).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Command source_root must be a directory")
    argv = command_argv(command)
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


def replay_argv(command: Sequence[str], script_args: Sequence[str]) -> list[str]:
    """Replace only target arguments; interpreter options and -m remain immutable."""
    parsed = parse_command(command)
    if not parsed.repair_supported or parsed.args_index is None:
        raise ValueError(parsed.repair_reason or "Command cannot be replayed")
    argv = [*parsed.argv[: parsed.args_index], *script_args]
    updated = parse_command(argv)
    if not updated.repair_supported or updated.args_index != parsed.args_index:
        raise ValueError("Invalid replacement target argv")
    return argv
