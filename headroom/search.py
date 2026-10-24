"""Keep/revert decisions and independently applicable Pareto configurations."""

import difflib
import hashlib
import json
import math
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from headroom.lab.runner import copy_source
from headroom.verify.compare import REQUIRED_CHECKS
from headroom.verify.policy import safe_relative_path, validate_env_changes

HARD_CHECKS = REQUIRED_CHECKS

_TOOL_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


def finite(value, *, positive=False):
    if type(value) not in (int, float):
        return None
    try:
        valid = math.isfinite(value)
    except OverflowError:
        return None
    if not valid or value < 0 or (positive and value == 0):
        return None
    return value


def peak_gb(result):
    value = finite(result.get("peak_allocated_bytes"), positive=True)
    if value is not None:
        return value / 1e9
    return finite(result.get("peak_alloc_gb"), positive=True)


def timing_trusted(result):
    return (
        result.get("shared_gpu") is False
        and result.get("gpu_observation_complete") is True
        and result.get("status") == "completed"
        and finite(result.get("step_ms_median"), positive=True) is not None
    )


@dataclass(frozen=True)
class KeepDecision:
    keep: bool
    reason: str
    memory_improvement_pct: float | None = None
    current_throughput_regression_pct: float | None = None
    current_timing_comparable: bool = False
    notes: tuple[str, ...] = ()


def decide_keep(current, candidate, verification, *, original_baseline, policy):
    """Require original-baseline scientific gates plus improvement over current kept state."""
    checks = verification.get("checks", {})
    if not isinstance(checks, dict) or any(checks.get(key) is not True for key in HARD_CHECKS):
        return KeepDecision(False, "verification_hard_constraints_unmet")
    if original_baseline.get("status") == "oom" and checks.get("loss_decreases") is not True:
        return KeepDecision(False, "original_loss_decrease_unverified")
    if candidate.get("status") != "completed" or verification.get("completed") is not True:
        return KeepDecision(False, "candidate_not_completed")
    if (
        not policy.get("allow_model_change", False)
        and checks.get("parameter_count_unchanged") is not True
    ):
        return KeepDecision(False, "parameter_count_not_unchanged")
    equivalent = verification.get("loss_equivalence") in {"identical", "within_tol"}
    changed_authorized = (
        policy.get("allow_numerics_change") is True
        and verification.get("numerics_changed") is True
        and verification.get("loss_equivalence") == "changed"
        and checks.get("loss_tolerance") is True
    )
    no_reference_allowed = (
        verification.get("acceptance_scope") == "repository"
        and original_baseline.get("status") == "oom"
        and verification.get("loss_equivalence") == "n/a"
        and verification.get("numerical_basis") == "repository_no_reference_exception"
        and verification.get("numerics_changed") is False
        and checks.get("repository_no_reference_exception") is True
    )
    if not equivalent and not changed_authorized and not no_reference_allowed:
        return KeepDecision(False, "numerics_not_verified")
    if equivalent and checks.get("loss_tolerance") is not True:
        return KeepDecision(False, "numerics_not_verified")
    notes = []
    if no_reference_allowed:
        notes.append(
            "PLAN T1.9 repository no-reference exception: numerical equivalence is unverified (n/a)."
        )
    if original_baseline.get("status") == "oom":
        if checks.get("throughput_limit") is False:
            return KeepDecision(False, "original_throughput_constraint_failed")
        notes.append(
            "Original OOM has no comparable completed-run throughput; no speedup is certified."
        )
    elif checks.get("throughput_limit") is not True:
        return KeepDecision(False, "original_throughput_constraint_unverified")
    before, after = peak_gb(current), peak_gb(candidate)
    if before is None or after is None:
        return KeepDecision(False, "memory_improvement_unverified")
    improvement = (before - after) / before * 100
    if not math.isfinite(improvement) or improvement <= 0:
        return KeepDecision(False, "no_memory_improvement", improvement)
    regression = None
    comparable = timing_trusted(current) and timing_trusted(candidate)
    if current.get("status") == "completed":
        first, second = current.get("env", {}), candidate.get("env", {})
        hardware = all(
            first.get(key) is not None and first.get(key) == second.get(key)
            for key in ("gpu_name", "gpu_total_memory_bytes", "device")
        )
        if not comparable or not hardware:
            return KeepDecision(False, "current_throughput_unverified", improvement)
        regression = (candidate["step_ms_median"] / current["step_ms_median"] - 1) * 100
        limit = finite(policy.get("max_throughput_regression_pct", 25))
        if not math.isfinite(regression) or limit is None or regression > limit:
            return KeepDecision(
                False, "current_throughput_regression", improvement, regression, True
            )
    elif current.get("status") == "oom":
        notes.append(
            "Memory improvement is relative to the current observed OOM peak, not unobserved required memory."
        )
    else:
        return KeepDecision(False, "current_state_unverified", improvement)
    return KeepDecision(
        True,
        "memory_improved_within_constraints",
        improvement,
        regression,
        comparable,
        tuple(notes),
    )


def policy_key(policy):
    return hashlib.sha256(
        json.dumps(dict(policy), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def pareto_point(number, result, verification, *, policy, artifacts, provenance):
    peak = peak_gb(result)
    trusted = timing_trusted(result)
    step = finite(result.get("step_ms_median"), positive=True)
    return {
        "round": number,
        "peak_gb": peak,
        "step_ms": step,
        "timing_trusted": trusted,
        "numerics": verification.get("loss_equivalence", "n/a"),
        "numerics_changed": verification.get("numerics_changed", False),
        "policy_key": policy_key(policy),
        "policy": dict(policy),
        "artifacts": dict(artifacts),
        "provenance": provenance,
        "target_met": verification.get("target_met") is True,
        "display_peak": f"{peak:.3f} GB" if peak is not None else "unknown",
        "display_step": f"{step:.3f} ms"
        if step is not None and trusted
        else "unknown / shared timing",
    }


def dominates(left, right):
    """Unknown/shared timing or different numerics policy is incomparable, never dominant."""
    if left.get("policy_key") != right.get("policy_key"):
        return False
    if (left.get("numerics"), left.get("numerics_changed")) != (
        right.get("numerics"),
        right.get("numerics_changed"),
    ):
        return False
    if left.get("timing_trusted") is not True or right.get("timing_trusted") is not True:
        return False
    values = [
        finite(point.get(key), positive=True)
        for point in (left, right)
        for key in ("peak_gb", "step_ms")
    ]
    if any(value is None for value in values):
        return False
    lp, lt, rp, rt = values
    return lp <= rp and lt <= rt and (lp < rp or lt < rt)


def pareto_front(points):
    return [
        point
        for index, point in enumerate(points)
        if not any(
            other_index != index and dominates(other, point)
            for other_index, other in enumerate(points)
        )
    ]


def _source_files(root):
    result = {}
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        try:
            safe_relative_path(relative, root)
        except ValueError:
            continue
        if path.is_file() and not path.is_symlink():
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Cumulative patch source exceeds its per-file bound")
            result[relative] = path.read_text()
    return result


def _json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def write_cumulative_patch(
    original, candidate, destination, *, env_changes, effective_cli, base_cli, metadata
):
    """Snapshot configuration with a diff checked against a fresh copy of the original."""
    original, candidate, destination = (
        Path(original).resolve(),
        Path(candidate).resolve(),
        Path(destination),
    )
    destination.mkdir(parents=True, exist_ok=False)
    errors = validate_env_changes(env_changes)
    if errors:
        raise ValueError("Cumulative environment violates allocator policy")
    before, after = _source_files(original), _source_files(candidate)
    if before.keys() - after.keys():
        raise ValueError("Cumulative patch cannot delete original source")
    chunks, changed = [], []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, ""), after.get(name, "")
        if old == new:
            continue
        changed.append(name)
        chunks.append("diff --git a/" + name + " b/" + name + "\n")
        for line in difflib.unified_diff(
            old.splitlines(True),
            new.splitlines(True),
            fromfile="a/" + name if name in before else "/dev/null",
            tofile="b/" + name,
        ):
            chunks.append(
                line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            )
    patch = destination / "patch.diff"
    patch.write_text("".join(chunks))
    check = {"status": "not_needed", "reason": "environment_or_cli_only", "changed_files": changed}
    if changed:
        git = shutil.which("git", path=_TOOL_ENV["PATH"])
        if git is None:
            raise ValueError("Git is required to verify the cumulative patch")
        check_root = destination / "original-check"
        copy_source(original, check_root, (destination.resolve(),))
        completed = subprocess.run(
            [git, "-c", "core.hooksPath=/dev/null", "apply", "--check", str(patch.resolve())],
            cwd=check_root,
            env=_TOOL_ENV,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        check = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "changed_files": changed,
        }
        if completed.returncode:
            _json(destination / "apply-check.json", check)
            raise ValueError("Cumulative patch does not apply to the original source")
    _json(destination / "apply-check.json", check)
    (destination / "env.sh").write_text(
        "".join(f"export {key}={shlex.quote(value)}\n" for key, value in env_changes.items())
    )
    _json(destination / "cli.json", {"original": list(base_cli), "effective": list(effective_cli)})
    _json(
        destination / "manifest.json",
        {
            **metadata,
            "changed_files": changed,
            "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "apply_check": check,
        },
    )
    return {
        "patch": str(patch),
        "env": str(destination / "env.sh"),
        "cli": str(destination / "cli.json"),
        "manifest": str(destination / "manifest.json"),
    }


def write_pareto(directory, points):
    directory = Path(directory)
    points = json.loads(json.dumps(points, allow_nan=False))
    frontier = pareto_front(points)
    result = {
        "points": points,
        "frontier": frontier,
        "limitations": [
            "Different numerical policies/observed numerics are not compared.",
            "Shared or unknown timing cannot establish dominance.",
            "Points inherit run provenance; offline fixtures are not model/GPU acceptance.",
        ],
    }
    _json(directory / "pareto.json", result)
    rows = [
        "# Retained configurations",
        "",
        "| Round | Peak | Step time | Numerics | Patch |",
        "|---|---|---|---|---|",
    ]
    for point in frontier:
        rows.append(
            f"| {point['round']} | {point['display_peak']} | {point['display_step']} | {point['numerics']} | [patch]({point['artifacts']['patch']}) |"
        )
    rows.extend(["", *["- " + note for note in result["limitations"]], ""])
    temporary = directory / "pareto.md.tmp"
    temporary.write_text("\n".join(rows))
    temporary.replace(directory / "pareto.md")
    return result


def select_research_topics(step, *, limit=2):
    text = " ".join(str(step.get(key, "")) for key in ("title", "description", "type")).casefold()
    checks = (
        ("checkpoint", ("checkpoint", "use_reentrant")),
        (
            "allocator",
            ("pytorch_cuda_alloc_conf", "expandable_segments", "max_split_size_mb", "allocator"),
        ),
        ("adamw", ("adamw", "fused", "foreach")),
        ("bitsandbytes", ("bitsandbytes", "8-bit", "8bit", "paged optimizer")),
        ("compile", ("torch.compile",)),
        ("fsdp", ("fsdp",)),
    )
    return [topic for topic, needles in checks if any(needle in text for needle in needles)][:limit]
