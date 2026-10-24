"""Generate and safely apply Token Factory patches to fresh, nonexecuted source copies."""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from headroom.lab.runner import copy_source
from headroom.llm.client import CapabilityNotVerified, LLMError
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.patch_evidence import save_patch_response
from headroom.verify.policy import (
    PatchPolicy,
    PolicyIssue,
    PolicyReport,
    check_cli_changes,
    check_source_changes,
    merge_cli_changes,
    nanogpt_cli,
    normalize_policy,
    safe_relative_path,
    scan_source_forbidden,
    validate_env_changes,
)

PROMPTS = Path(__file__).parent / "prompts"
MAX_SOURCE_CONTEXT_BYTES = 128 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
_TOOL_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


class PatchProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    diff: str = Field(max_length=512000)
    env_changes: dict[str, str]
    cli_changes: list[Annotated[str, StringConstraints(max_length=1000)]] = Field(max_length=60)
    notes: list[Annotated[str, StringConstraints(max_length=2000)]] = Field(
        default_factory=list, max_length=20
    )


@dataclass(frozen=True)
class PatchAttempt:
    index: int
    status: str
    reason: str
    candidate_dir: str | None = None
    patch_path: str | None = None
    changed_files: tuple[str, ...] = ()
    apply_command: tuple[str, ...] = ()
    apply_mode: str | None = None
    compile_exit_code: int | None = None
    policy_report: PolicyReport | None = None
    detail: str | None = None
    llm_usage: dict[str, Any] | None = None
    llm_cost: dict[str, Any] | None = None
    response_artifact: str | None = None


@dataclass(frozen=True)
class PatchResult:
    status: str
    candidate_dir: str | None
    patch_path: str | None
    env_changes: dict[str, str]
    cli_changes: tuple[str, ...]
    effective_cli: tuple[str, ...]
    attempts: tuple[PatchAttempt, ...]
    policy_report: PolicyReport
    reason: str
    artifact_dir: str
    notes: tuple[str, ...] = ()
    original_source_root: str | None = None
    runtime_verified: bool = False

    @property
    def applied(self) -> bool:
        return self.status == "applied"


def _write_json(path: Path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _read_source(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("source must be a bounded regular text file")
    return path.read_text()


def validate_diff(diff: str, source_root: str | Path) -> tuple[str, ...]:
    if not diff.strip():
        return ()
    if "\x00" in diff or len(diff.encode()) > 512000:
        raise ValueError("diff is oversized or contains NUL")
    forbidden = r"^(?:rename (?:from|to)|copy (?:from|to)|similarity index|dissimilarity index|old mode|new mode|deleted file mode|GIT binary patch|Binary files)"
    if re.search(forbidden, diff, re.MULTILINE):
        raise ValueError("renames, deletions, binary and mode changes are forbidden")
    for line in diff.splitlines():
        if line.startswith(("index ", "new file mode ")) and re.search(
            r"\b(?:120000|160000)\b", line
        ):
            raise ValueError("symlink/submodule mode is forbidden")
        if line.startswith("new file mode ") and line != "new file mode 100644":
            raise ValueError("new files must have regular nonexecutable mode")
    try:
        parsed = PatchSet(diff.splitlines(keepends=True))
    except (UnidiffParseError, ValueError) as error:
        raise ValueError("invalid unified diff") from error
    if not parsed or len(parsed) > 20:
        raise ValueError("diff must touch between one and twenty files")
    files = []
    for item in parsed:
        if item.is_removed_file or item.target_file == "/dev/null":
            raise ValueError("source file deletion is forbidden")
        if not item.target_file.startswith("b/"):
            raise ValueError("target diff header must use b/ prefix")
        target = safe_relative_path(item.target_file[2:], source_root)
        if item.source_file != "/dev/null" and (
            not item.source_file.startswith("a/") or item.source_file[2:] != target
        ):
            raise ValueError("source/target headers must describe the same relative file")
        if not item:
            raise ValueError("diff contains a file without hunks")
        if target in files:
            raise ValueError("duplicate diff target")
        files.append(target)
    git_headers = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            match = re.fullmatch(r"diff --git a/([A-Za-z0-9_./-]+) b/([A-Za-z0-9_./-]+)", line)
            if not match or match[1] != match[2]:
                raise ValueError("invalid or inconsistent git diff header")
            git_headers.append(safe_relative_path(match[2], source_root))
    if git_headers and git_headers != files:
        raise ValueError("git and unified file headers disagree")
    return tuple(files)


def _run_tool(argv: Sequence[str], cwd: Path, *, input_text: str | None = None, timeout=30):
    return subprocess.run(
        list(argv),
        cwd=cwd,
        input=input_text,
        env=_TOOL_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _git_prefix(git: str) -> list[str]:
    return [
        git,
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "protocol.allow=never",
    ]


def _source_context(root: Path, selected: Sequence[str] | None) -> dict:
    files = (
        list(selected)
        if selected is not None
        else sorted(
            str(path.relative_to(root))
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}
        )
    )
    sources, omitted, used = {}, [], 0
    for name in files:
        name = safe_relative_path(name, root)
        text = _read_source(root / name)
        size = len(text.encode())
        if used + size > MAX_SOURCE_CONTEXT_BYTES:
            omitted.append(name)
            continue
        sources[name] = "\n".join(
            f"{index:04d}: {line}" for index, line in enumerate(text.splitlines(), 1)
        )
        used += size
    if not sources:
        raise ValueError(
            "no supported source fits the prompt context; select relevant source files"
        )
    return {"sources": sources, "omitted_files": omitted, "source_bytes": used}


def _make_root(work_root: str | Path, prefix: str) -> Path:
    root = Path(work_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / (prefix + "-" + uuid.uuid4().hex)
    target.mkdir(mode=0o700)
    return target


def _result(
    directory: Path,
    source: Path,
    proposal: PatchProposal | None,
    attempt: PatchAttempt,
    base_cli=(),
    cli_equals=False,
) -> PatchResult:
    valid = attempt.status == "applied"
    report = attempt.policy_report or PolicyReport(
        False, (PolicyIssue(attempt.reason, attempt.detail or attempt.reason),)
    )
    result = PatchResult(
        status=attempt.status,
        candidate_dir=attempt.candidate_dir,
        patch_path=attempt.patch_path,
        env_changes=dict(proposal.env_changes) if valid and proposal else {},
        cli_changes=tuple(proposal.cli_changes) if valid and proposal else (),
        effective_cli=tuple(merge_cli_changes(base_cli, proposal.cli_changes))
        if valid and proposal
        else tuple(base_cli),
        attempts=(attempt,),
        policy_report=report,
        reason=attempt.reason,
        artifact_dir=str(directory),
        notes=tuple(proposal.notes) if proposal else (),
        original_source_root=str(source),
    )
    if valid and cli_equals:
        result = replace(
            result, effective_cli=tuple(nanogpt_cli(result.effective_cli, require_equals=False))
        )
        _write_json(
            directory / "cli.json",
            {"overrides": list(result.cli_changes), "effective": list(result.effective_cli)},
        )
    _write_json(directory / "result.json", asdict(result))
    return result


def apply_proposal(
    source_root: str | Path,
    proposal: PatchProposal | Mapping[str, Any],
    *,
    work_root: str | Path,
    policy: PatchPolicy | Mapping[str, Any] | None = None,
    base_cli: Sequence[str] = (),
    cli_equals: bool = False,
) -> PatchResult:
    """Never execute a target: copy, validate, git apply --3way, static check, py_compile."""
    policy = normalize_policy(policy)
    source = Path(source_root).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("source_root must be a directory")
    directory = _make_root(work_root, "patch")
    candidate = directory / "candidate"
    attempt = PatchAttempt(1, "rejected", "INVALID_PROPOSAL", candidate_dir=str(candidate))
    try:
        parsed = (
            proposal
            if isinstance(proposal, PatchProposal)
            else PatchProposal.model_validate(proposal, strict=True)
        )
    except ValidationError:
        return _result(directory, source, None, attempt, base_cli, cli_equals=cli_equals)
    try:
        paths = validate_diff(parsed.diff, source)
        issues = list(validate_env_changes(parsed.env_changes))
        cli_report = check_cli_changes(
            base_cli, parsed.cli_changes, policy=policy, notes=parsed.notes
        )
        issues.extend(cli_report.issues)
        if not paths and not parsed.env_changes and not parsed.cli_changes:
            issues.append(PolicyIssue("NO_CHANGE", "A proposal must contain an actual change."))
        if issues:
            attempt = replace(
                attempt, reason=issues[0].code, policy_report=PolicyReport(False, tuple(issues))
            )
            return _result(directory, source, parsed, attempt, base_cli, cli_equals=cli_equals)
        manifest = copy_source(source, candidate, (Path(work_root).resolve(), directory))
        for name in manifest["files"]:
            copied = candidate / name
            copied.chmod(0o755 if copied.stat().st_mode & 0o111 else 0o644)
        _write_json(directory / "source-manifest.json", manifest)
        patch_path = directory / "patch.diff"
        patch_path.write_text(parsed.diff)
        attempt = replace(attempt, patch_path=str(patch_path), changed_files=paths)
        before = {
            name: _read_source(candidate / name) for name in paths if (candidate / name).exists()
        }
        if paths:
            git = shutil.which("git", path=_TOOL_ENV["PATH"])
            if git is None:
                return _result(
                    directory,
                    source,
                    parsed,
                    replace(attempt, status="failed", reason="GIT_UNAVAILABLE"),
                    base_cli,
                    cli_equals=cli_equals,
                )
            prefix = _git_prefix(git)
            for arguments in (["init", "--quiet", "--template="], ["add", "--all"]):
                initialized = _run_tool(prefix + arguments, candidate)
                if initialized.returncode:
                    return _result(
                        directory,
                        source,
                        parsed,
                        replace(
                            attempt,
                            status="failed",
                            reason="GIT_PREPARATION_FAILED",
                            detail=initialized.stderr[-2000:],
                        ),
                        base_cli,
                        cli_equals=cli_equals,
                    )
            checked = _run_tool(
                prefix + ["apply", "--3way", "--check", "-"], candidate, input_text=parsed.diff
            )
            if checked.returncode:
                return _result(
                    directory,
                    source,
                    parsed,
                    replace(
                        attempt,
                        status="failed",
                        reason="PATCH_APPLY_FAILED",
                        detail=checked.stderr[-2000:],
                    ),
                    base_cli,
                    cli_equals=cli_equals,
                )
            command = prefix + ["apply", "--3way", "-"]
            applied = _run_tool(command, candidate, input_text=parsed.diff)
            mode = (
                "three_way_command_direct_fallback"
                if "Falling back to direct application" in applied.stderr
                else "three_way"
            )
            attempt = replace(attempt, apply_command=tuple(command), apply_mode=mode)
            if applied.returncode:
                return _result(
                    directory,
                    source,
                    parsed,
                    replace(
                        attempt,
                        status="failed",
                        reason="PATCH_APPLY_FAILED",
                        detail=applied.stderr[-2000:],
                    ),
                    base_cli,
                    cli_equals=cli_equals,
                )
        after = {name: _read_source(candidate / name) for name in paths}
        report = check_source_changes(before, after, policy=policy, notes=parsed.notes)
        attempt = replace(attempt, policy_report=report)
        if not report.allowed:
            return _result(
                directory, source, parsed, replace(attempt, reason=report.issues[0].code), base_cli
            )
        python_files = [str(candidate / name) for name in paths if name.lower().endswith(".py")]
        if python_files:
            compiled = _run_tool(
                [sys.executable, "-I", "-S", "-m", "py_compile", *python_files], candidate
            )
            attempt = replace(attempt, compile_exit_code=compiled.returncode)
            if compiled.returncode:
                return _result(
                    directory,
                    source,
                    parsed,
                    replace(
                        attempt,
                        status="failed",
                        reason="COMPILE_FAILED",
                        detail=compiled.stderr[-2000:],
                    ),
                    base_cli,
                    cli_equals=cli_equals,
                )
        env_text = "".join(
            f"export {key}={shlex.quote(value)}\n" for key, value in parsed.env_changes.items()
        )
        (directory / "env.sh").write_text(env_text)
        _write_json(
            directory / "cli.json",
            {
                "overrides": parsed.cli_changes,
                "effective": merge_cli_changes(base_cli, parsed.cli_changes),
            },
        )
        return _result(
            directory,
            source,
            parsed,
            replace(attempt, status="applied", reason="STATIC_CHECKS_PASSED"),
            base_cli,
            cli_equals=cli_equals,
        )
    except (ValueError, OSError, subprocess.SubprocessError, RecursionError) as error:
        detail = str(error)[:2000] if isinstance(error, ValueError) else type(error).__name__
        attempt = replace(
            attempt, status="rejected", reason="UNSAFE_OR_INVALID_PATCH", detail=detail
        )
        return _result(directory, source, parsed, attempt, base_cli, cli_equals=cli_equals)


class PatchEngine:
    def __init__(
        self, router: LLMRouter, *, max_repairs: int = 3, max_completion_tokens: int = 4000
    ):
        if not isinstance(router, LLMRouter):
            raise TypeError("PatchEngine requires the Token Factory LLMRouter")
        if type(max_repairs) is not int or not 0 <= max_repairs <= 3:
            raise ValueError("max_repairs must be between zero and three")
        if type(max_completion_tokens) is not int or not 1 <= max_completion_tokens <= 4000:
            raise ValueError("completion cap must be between one and 4000")
        self.router = router
        self.max_repairs = max_repairs
        self.max_completion_tokens = max_completion_tokens

    def generate_and_apply(
        self,
        source_root: str | Path,
        plan_step,
        *,
        work_root: str | Path,
        policy: PatchPolicy | Mapping[str, Any] | None = None,
        source_files: Sequence[str] | None = None,
        base_cli: Sequence[str] = (),
        context: Mapping[str, Any] | None = None,
        source_profile: str | None = None,
        sandboxed: bool = False,
    ) -> PatchResult:
        policy = normalize_policy(policy)
        source = Path(source_root).resolve(strict=True)
        step = plan_step.model_dump() if hasattr(plan_step, "model_dump") else dict(plan_step)
        directory = _make_root(work_root, "patch-engine")
        snapshot = directory / "baseline"
        source_report = scan_source_forbidden(
            source, source_files=source_files, source_profile=source_profile, sandboxed=sandboxed
        )
        if not source_report.allowed:
            result = PatchResult(
                "rejected",
                None,
                None,
                {},
                (),
                tuple(base_cli),
                (),
                source_report,
                source_report.issues[0].code,
                str(directory),
                original_source_root=str(source),
            )
            _write_json(directory / "result.json", asdict(result))
            return result
        if source_profile == "pinned_nanogpt":
            try:
                nanogpt_cli(base_cli)
            except (TypeError, ValueError):
                issue = PolicyIssue(
                    "NANOGPT_CLI_FORBIDDEN",
                    "Pinned nanoGPT requires equals-only options and no config-file positional arguments.",
                )
                result = PatchResult(
                    "rejected",
                    None,
                    None,
                    {},
                    (),
                    tuple(base_cli),
                    (),
                    PolicyReport(False, (issue,)),
                    issue.code,
                    str(directory),
                    original_source_root=str(source),
                )
                _write_json(directory / "result.json", asdict(result))
                return result
        manifest = copy_source(source, snapshot, (Path(work_root).resolve(), directory))
        _write_json(directory / "source-manifest.json", manifest)
        snapshot_report = scan_source_forbidden(
            snapshot, source_files=source_files, source_profile=source_profile, sandboxed=sandboxed
        )
        if not snapshot_report.allowed:
            result = PatchResult(
                "rejected",
                None,
                None,
                {},
                (),
                tuple(base_cli),
                (),
                snapshot_report,
                snapshot_report.issues[0].code,
                str(directory),
                original_source_root=str(source),
            )
            _write_json(directory / "result.json", asdict(result))
            return result
        try:
            source_context = _source_context(snapshot, source_files)
        except (ValueError, OSError, UnicodeError):
            issue = PolicyIssue(
                "SOURCE_CONTEXT_REJECTED", "No safely bounded source context is available."
            )
            result = PatchResult(
                "rejected",
                None,
                None,
                {},
                (),
                tuple(base_cli),
                (),
                PolicyReport(False, (issue,)),
                issue.code,
                str(directory),
                original_source_root=str(source),
            )
            _write_json(directory / "result.json", asdict(result))
            return result
        requested = {
            "plan_step": step,
            "policy": asdict(policy),
            "base_cli": list(base_cli),
            **source_context,
            "evidence_context": dict(context or {}),
        }
        messages = [
            {"role": "system", "content": (PROMPTS / "patch.md").read_text()},
            {"role": "user", "content": json.dumps(requested, allow_nan=False)},
        ]
        attempts = []
        last = None
        for index in range(self.max_repairs + 1):
            response = None
            ledger_start = len(self.router.client.ledger.entries)
            response_path = directory / f"attempt-{index + 1}-response.json"
            try:
                response = self.router.chat(
                    "patcher",
                    messages,
                    PatchProposal,
                    max_tokens=self.max_completion_tokens,
                    reasoning=False,
                )
                if response.usage is None:
                    raise LLMError("PATCH_USAGE_UNVERIFIED")
                if response.usage.completion_tokens > self.max_completion_tokens:
                    raise LLMError("PATCH_COMPLETION_LIMIT_EXCEEDED")
            except BaseException as error:
                if isinstance(error, ResponseValidationError):
                    response = error.response
                records = self.router.client.ledger.entries[ledger_start:]
                try:
                    response_artifact = save_patch_response(
                        response_path, response, error=error, records=records
                    )
                except Exception as artifact_error:
                    error.add_note("Private patch-response evidence could not be saved.")
                    raise error from artifact_error
                if not isinstance(error, LLMError):
                    raise
                protocol = records[-1] if records else None
                reason = str(error)
                attempt = PatchAttempt(
                    index + 1,
                    "failed",
                    "LLM_RESPONSE_REJECTED",
                    detail=reason[:2000],
                    llm_usage=(
                        asdict(response.usage)
                        if response and response.usage
                        else asdict(protocol.usage)
                        if protocol and protocol.usage
                        else None
                    ),
                    llm_cost=(
                        response.cost.as_dict()
                        if response
                        else protocol.cost.as_dict()
                        if protocol
                        else None
                    ),
                    response_artifact=response_artifact,
                )
                attempts.append(attempt)
                _write_json(directory / f"attempt-{index + 1}.json", asdict(attempt))
                if (
                    isinstance(error, CapabilityNotVerified)
                    or "Live model requests are disabled" in reason
                    or "PATCH_USAGE_" in reason
                    or "PATCH_COMPLETION_" in reason
                ):
                    break
                failure = {"reason": attempt.reason, "detail": attempt.detail}
            else:
                response_artifact = save_patch_response(
                    response_path,
                    response,
                    records=self.router.client.ledger.entries[ledger_start:],
                )
                last = apply_proposal(
                    snapshot,
                    response.parsed,
                    work_root=directory / f"attempt-{index + 1}",
                    policy=policy,
                    base_cli=base_cli,
                    cli_equals=source_profile == "pinned_nanogpt",
                )
                if last.applied and source_profile is not None:
                    candidate_report = scan_source_forbidden(
                        Path(last.candidate_dir),
                        source_files=source_files,
                        source_profile=source_profile,
                        sandboxed=sandboxed,
                    )
                    if not candidate_report.allowed:
                        rejected_attempt = replace(
                            last.attempts[0],
                            status="rejected",
                            reason=candidate_report.issues[0].code,
                            policy_report=candidate_report,
                        )
                        last = replace(
                            last,
                            status="rejected",
                            reason=rejected_attempt.reason,
                            policy_report=candidate_report,
                            attempts=(rejected_attempt,),
                            env_changes={},
                            cli_changes=(),
                            effective_cli=tuple(base_cli),
                        )
                        _write_json(Path(last.artifact_dir) / "result.json", asdict(last))
                attempt = replace(
                    last.attempts[0],
                    index=index + 1,
                    llm_usage=asdict(response.usage),
                    llm_cost=response.cost.as_dict(),
                    response_artifact=response_artifact,
                )
                attempts.append(attempt)
                _write_json(directory / f"attempt-{index + 1}.json", asdict(attempt))
                if last.applied:
                    result = replace(
                        last,
                        attempts=tuple(attempts),
                        artifact_dir=str(directory),
                        original_source_root=str(source),
                    )
                    _write_json(directory / "result.json", asdict(result))
                    return result
                failure = {
                    "reason": attempt.reason,
                    "detail": attempt.detail,
                    "policy_issues": [asdict(issue) for issue in attempt.policy_report.issues]
                    if attempt.policy_report
                    else [],
                    "previous_proposal": response.parsed,
                }
            messages = [
                {"role": "system", "content": (PROMPTS / "patch_fix.md").read_text()},
                {
                    "role": "user",
                    "content": json.dumps({**requested, "repair": failure}, allow_nan=False),
                },
            ]
        if last is None:
            result = PatchResult(
                "failed",
                None,
                None,
                {},
                (),
                tuple(base_cli),
                tuple(attempts),
                PolicyReport(False),
                attempts[-1].reason,
                str(directory),
                original_source_root=str(source),
            )
        else:
            result = replace(
                last,
                attempts=tuple(attempts),
                artifact_dir=str(directory),
                original_source_root=str(source),
            )
        _write_json(directory / "result.json", asdict(result))
        return result
