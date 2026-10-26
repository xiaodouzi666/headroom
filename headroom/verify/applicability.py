"""Empirical applicability of archived repairs at exact observed contexts.

This is an offline, read-only audit of a trusted local archive. Hashes detect
changes relative to a supplied scope, not forgery of the archive and its scope.
Finite observations are not a proof of equivalence or a success prediction.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import asdict
from pathlib import Path

from headroom.patch_validation import verify_exact_application
from headroom.verify.compare import compare_runs
from headroom.verify.pairing import derive_pairing, source_contract
from headroom.verify.policy import normalize_policy
from headroom.verify.precision import observed_precision

PROTOCOL = "headroom.repair_scope.v1"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_FILES = 5000
HEX = re.compile(r"[0-9a-f]{64}")
RUN_ID = re.compile(r"[0-9a-f]{32}")
LIMITATIONS = [
    "Exact observed points only; no interpolation, extrapolation, or future success guarantee.",
    "Historical reinspection and human controls do not add model repair or MVP successes.",
    "Trusted local archive; hashes provide change detection, not authenticity or adversarial security.",
    "Cooperative pinned standalone s1/s3/s4 targets only; no generic equivalence proof.",
    "V1 requires a completed original baseline; OOM and transformed references remain unknown.",
    "Runtime precision and scalar losses do not prove every internal operation or final parameter value.",
    "Host load and sampled GPU sharing can confound timing; no speed superiority is certified.",
]


class _MissingEvidence(Exception):
    pass


def _canonical(value):
    def validate(item, depth=0):
        if depth > 64:
            raise ValueError("JSON nesting exceeds limit")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                validate(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                validate(child, depth + 1)
            return
        raise ValueError("Expected finite JSON values with string object keys")

    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parts(value):
    if (
        type(value) is not str
        or not value
        or len(value) > 2048
        or value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Expected a bounded plain relative path")
    return value.split("/")


def _safe_path(root, relative):
    current = root
    parts = _parts(relative)
    for index, component in enumerate(parts):
        current = current / component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Symlink evidence is not supported")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Evidence ancestor must be a directory")
    return current


def _read_bytes(path, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("Evidence must be a bounded regular file")
        content = handle.read(limit + 1)
        if len(content) > limit:
            raise ValueError("Evidence exceeds size limit")
    return content


def _decode(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Nonfinite JSON constant")

    try:
        value = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
        _canonical(value)
        return value
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid bounded JSON evidence") from exc


def load_json(path):
    """Read a bounded JSON input, rejecting linked ancestors, duplicate keys and NaN."""
    path = Path(path).absolute()
    try:
        checked = _safe_path(Path(path.anchor), path.relative_to(path.anchor).as_posix())
        return _decode(_read_bytes(checked, MAX_JSON_BYTES))
    except OSError as exc:
        raise ValueError("JSON input is unavailable or unsafe") from exc


def _root(path):
    path = Path(path).absolute()
    try:
        checked = _safe_path(Path(path.anchor), path.relative_to(path.anchor).as_posix())
        if not stat.S_ISDIR(checked.lstat().st_mode):
            raise ValueError("Evidence root must be a directory")
        return checked
    except OSError as exc:
        raise ValueError("Evidence root is unavailable") from exc


class _Archive:
    def __init__(self, root):
        self.root = root
        self.evidence = {}

    def bytes(self, relative, limit=MAX_JSON_BYTES):
        try:
            value = _read_bytes(_safe_path(self.root, relative), limit)
        except FileNotFoundError as exc:
            raise _MissingEvidence(relative) from exc
        except OSError as exc:
            raise ValueError("Evidence is unavailable or unsafe") from exc
        self.evidence[relative] = {
            "sha256": hashlib.sha256(value).hexdigest(),
            "bytes": len(value),
        }
        return value

    def json(self, relative):
        value = _decode(self.bytes(relative))
        if type(value) is not dict:
            raise ValueError("Evidence JSON must be an object")
        return value


def _integer(value, name, minimum=1):
    if type(value) is not int or not minimum <= value <= 100000:
        raise ValueError(name + " must be a bounded integer")
    return value


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(name + " must be finite and nonnegative")
    return value


def _argv(value):
    if (
        type(value) is not list
        or len(value) > 256
        or any(type(arg) is not str or "\x00" in arg for arg in value)
        or sum(len(arg.encode()) for arg in value) > 65536
    ):
        raise ValueError("Expected bounded string argv")
    return value


def _source(archive, directory, manifest):
    record = manifest.get("source")
    if type(record) is not dict or type(record.get("files")) is not dict:
        raise _MissingEvidence("source manifest")
    entries = record["files"]
    if not entries or len(entries) > MAX_FILES:
        raise ValueError("Invalid source inventory length")
    source_dir = _safe_path(archive.root, directory + "/source")
    if not stat.S_ISDIR(source_dir.lstat().st_mode):
        raise ValueError("Source root must be a directory")
    actual_names = set()
    for here, directories, files in os.walk(source_dir, followlinks=False):
        for name in directories:
            if not stat.S_ISDIR((Path(here) / name).lstat().st_mode):
                raise ValueError("Linked or special source directory")
        for name in files:
            actual_names.add((Path(here) / name).relative_to(source_dir).as_posix())
            if len(actual_names) > MAX_FILES:
                raise ValueError("Source inventory exceeds limit")
    if actual_names != set(entries):
        raise ValueError("Source inventory differs from observed files")
    total = 0
    for name, entry in sorted(entries.items()):
        _parts(name)
        if (
            type(entry) is not dict
            or type(entry.get("sha256")) is not str
            or not HEX.fullmatch(entry["sha256"])
            or type(entry.get("bytes")) is not int
            or not 0 <= entry["bytes"] <= MAX_SOURCE_BYTES
        ):
            raise ValueError("Invalid source entry")
        total += entry["bytes"]
        if total > MAX_SOURCE_BYTES:
            raise ValueError("Source tree exceeds size limit")
        content = archive.bytes(directory + "/source/" + name, entry["bytes"])
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Source file does not match manifest")
    if type(record.get("total_bytes")) is not int or record["total_bytes"] != total:
        raise ValueError("Source total does not match manifest")
    return _digest(entries)


def _script(manifest, args):
    command = manifest.get("command")
    _argv(command)
    prefix = ["/opt/venv/bin/python", "-m", "headroom.lab.run_target", "--script"]
    if command[:4] != prefix or len(command) < 15:
        raise _MissingEvidence("unsupported standalone invocation")
    expected = [
        "--output",
        "/out",
        "--max-steps",
        str(manifest.get("max_steps")),
        "--max-seconds",
        str(manifest.get("max_seconds")),
        "--seed",
        str(manifest.get("seed")),
        "--device",
        "cuda",
    ]
    if command[5:15] != expected:
        raise ValueError("Lab command does not match manifest controls")
    if command[15:] != (["--", *args] if args else []):
        raise ValueError("Lab command does not match recorded argv")
    if manifest.get("target_argv_override") is not None:
        raise _MissingEvidence("unsupported argv override")
    script = command[4]
    if not script.startswith("/source/"):
        raise ValueError("Unexpected standalone source path")
    relative = script[len("/source/") :]
    _parts(relative)
    return relative


def _environment(result, manifest):
    env = result.get("env")
    if type(env) is not dict:
        raise _MissingEvidence("runtime environment")
    text_keys = ("python", "torch", "cuda", "gpu_name")
    integer_keys = ("cudnn", "gpu_total_memory_bytes", "seed")
    for key in text_keys:
        if type(env.get(key)) is not str or not env[key]:
            raise _MissingEvidence("environment." + key)
    for key in integer_keys:
        if type(env.get(key)) is not int or env[key] < 0:
            raise _MissingEvidence("environment." + key)
    if env.get("device") != "cuda":
        raise _MissingEvidence("CUDA observation")
    image = manifest.get("image_id")
    if type(image) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise _MissingEvidence("runtime image identity")
    if result.get("image_id") != image:
        raise ValueError("Result and manifest image identities differ")
    if manifest.get("seed") != env["seed"]:
        raise ValueError("Result and manifest seed identities differ")
    for key in ("PYTORCH_CUDA_ALLOC_CONF", "CUBLAS_WORKSPACE_CONFIG"):
        if key not in env:
            raise _MissingEvidence("environment." + key)
        if env[key] is not None and type(env[key]) is not str:
            raise ValueError("Invalid runtime environment observation: " + key)
    allocator = env["PYTORCH_CUDA_ALLOC_CONF"]
    return {
        **{key: env[key] for key in (*text_keys, *integer_keys)},
        "image_id": image,
        "device": "cuda",
        "allocator_conf": allocator,
        "deterministic_algorithms": env.get("deterministic_algorithms"),
        "seeded": env.get("seeded"),
        "CUBLAS_WORKSPACE_CONFIG": env.get("CUBLAS_WORKSPACE_CONFIG"),
    }


def _capture(result, run_id):
    if result.get("run_id") != run_id or result.get("protocol") != "headroom.lab.v1":
        raise ValueError("Lab result identity or protocol mismatch")
    if result.get("status") not in {"completed", "oom", "error", "timeout"}:
        raise ValueError("Invalid Lab status")
    _integer(result.get("steps"), "observed steps", 0)
    if type(result.get("loss_series")) is not list:
        raise _MissingEvidence("loss series")
    for value in result["loss_series"]:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid observed loss")
    for key in ("capture_complete", "cleanup_verified"):
        if result.get(key) is not True:
            raise _MissingEvidence(key)


def _pairing_available(result, contract):
    capture = result.get("pairing_capture")
    if type(capture) is not dict or capture.get("protocol") != "headroom.pairing.v1":
        return False
    complete = capture.get("complete")
    if type(complete) is not bool:
        return False
    tensors, parameters, updates = (
        capture.get("tensors"),
        capture.get("initial_parameters"),
        capture.get("updates"),
    )
    if (
        type(tensors) is not dict
        or set(tensors) != set(contract["tensor_names"])
        or type(parameters) is not list
        or not parameters
        or type(updates) is not list
        or not updates
    ):
        return False

    def tensor(value):
        if (
            type(value) is not dict
            or type(value.get("sha256")) is not str
            or not HEX.fullmatch(value["sha256"])
            or type(value.get("dtype")) is not str
            or not value["dtype"].startswith("torch.")
            or type(value.get("shape")) is not list
            or any(type(dim) is not int or dim < 0 for dim in value["shape"])
        ):
            raise ValueError("Invalid tensor fingerprint")

    for value in tensors.values():
        tensor(value)
    names = set()
    for value in parameters:
        tensor(value)
        name = value.get("name")
        if type(name) is not str or not name or name in names:
            raise ValueError("Invalid initialized parameter fingerprint")
        names.add(name)
    for index, update in enumerate(updates, 1):
        if (
            type(update) is not dict
            or set(update) != {"step", "effective_batch", "training_forwards", "backwards"}
            or any(type(value) is not int or value < 1 for value in update.values())
            or update["step"] != index
        ):
            raise ValueError("Invalid runtime update observation")
    if complete and len(updates) != result["steps"]:
        raise ValueError("Complete pairing update count disagrees with observed steps")
    return complete


def _observe(root, selection):
    archive = _Archive(root)
    observation = {
        "selection": selection,
        "context": None,
        "status": "unknown",
        "reasons": [],
        "metrics": {},
        "evidence": archive.evidence,
        "provenance": "unknown",
    }
    job, number = selection["job"], selection["round"]
    try:
        report = archive.json(job + "/report.json")
        rounds = report.get("rounds")
        if type(rounds) is not list:
            raise _MissingEvidence("rounds")
        matches = [
            row
            for row in rounds
            if type(row) is dict and type(row.get("number")) is int and row["number"] == number
        ]
        if len(matches) != 1:
            raise ValueError("Selection must name exactly one recorded round")
        row = matches[0]
        verification = row.get("verification")
        if type(verification) is not dict or type(verification.get("run_ids")) is not dict:
            raise _MissingEvidence("candidate verification")
        run = report.get("run")
        if type(run) is not dict or type(run.get("request")) is not dict:
            raise _MissingEvidence("original request")
        request = run["request"]
        steps = _integer(request.get("max_steps"), "required steps")
        _integer(request.get("seed"), "seed", 0)
        if "max_seconds" not in request or "device" not in request:
            raise _MissingEvidence("requested execution limits/device")
        max_seconds = _integer(request["max_seconds"], "requested max_seconds")
        if max_seconds > 3600 or request["device"] != "cuda":
            raise ValueError("Unsupported requested execution limits/device")
        target = request.get("target")
        if type(target) is not str:
            raise ValueError("Target must be explicit")
        reclaim = _number(request.get("reclaim_reduction_pct", 30), "reclaim percentage")
        if reclaim > 100:
            raise ValueError("Invalid reclaim target")
        if type(request.get("policy")) is not dict:
            raise _MissingEvidence("explicit requested policy")
        policy = asdict(normalize_policy(request["policy"]))
        config_path = job + f"/configurations/round-{number:02d}"
        config = archive.json(config_path + "/manifest.json")
        if type(config.get("round")) is not int or config["round"] != number:
            raise ValueError("Configuration round mismatch")
        if type(config.get("policy")) is not dict:
            raise _MissingEvidence("explicit configuration policy")
        if asdict(normalize_policy(config["policy"])) != policy:
            raise ValueError("Configuration policy mismatch")
        provenance = config.get("provenance")
        if type(provenance) is not str or not provenance or len(provenance) > 80:
            raise ValueError("Configuration provenance is required")
        observation["provenance"] = provenance
        if run.get("provenance") != provenance:
            raise ValueError("Configuration/run provenance mismatch")
        impact = config.get("numerics_impact")
        if impact not in {"none", "minor", "significant"}:
            raise ValueError("Numerical impact must be explicit")
        patch = archive.bytes(config_path + "/patch.diff")
        patch_sha = hashlib.sha256(patch).hexdigest()
        if config.get("patch_sha256") != patch_sha or not patch:
            raise ValueError("Selected patch digest mismatch or empty patch")
        cli = archive.json(config_path + "/cli.json")
        original, effective = _argv(cli.get("original")), _argv(cli.get("effective"))
        results, manifests, sources, environments = {}, {}, {}, {}
        contracts = {}
        for role in ("baseline", "candidate"):
            run_id = verification["run_ids"].get(role)
            if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
                raise ValueError("Lab run id must be 32 lowercase hexadecimal characters")
            directory = job + "/lab/" + run_id
            result = archive.json(directory + "/result.json")
            manifest = archive.json(directory + "/manifest.json")
            _capture(result, run_id)
            source_hash = _source(archive, directory, manifest)
            args = original if role == "baseline" else effective
            script = _script(manifest, args)
            if manifest.get("max_steps") != steps or type(manifest.get("max_steps")) is not int:
                raise ValueError("Manifest and requested step counts differ")
            if manifest.get("seed") != request["seed"] or type(manifest.get("seed")) is not int:
                raise ValueError("Manifest and requested seeds differ")
            if (
                type(manifest.get("max_seconds")) is not int
                or manifest["max_seconds"] != max_seconds
                or manifest.get("device") != request["device"]
            ):
                raise ValueError("Manifest and requested execution limits/device differ")
            environments[role] = _environment(result, manifest)
            contract = source_contract(_safe_path(root, directory + "/source/" + script))
            recorded = result.get("pairing_capture", {}).get("source_contract")
            if not contract.get("supported") or not isinstance(recorded, dict):
                raise _MissingEvidence("pinned source contract")
            if contract != recorded:
                raise ValueError("Source contract differs from captured source")
            embedded = run.get("baseline" if role == "baseline" else "after")
            # Embedded after belongs to the selected round only. Nonselected
            # rounds may coexist in a historical report.
            selected = report.get("selected_configuration", {}).get("round")
            if (
                embedded is not None
                and (role == "baseline" or selected == number)
                and _canonical(embedded) != _canonical(result)
            ):
                raise ValueError("Embedded result differs from standalone Lab artifact")
            results[role], manifests[role] = result, manifest
            sources[role], contracts[role] = source_hash, contract
        original_dir = job + "/lab/" + verification["run_ids"]["baseline"] + "/source"
        candidate_dir = job + "/lab/" + verification["run_ids"]["candidate"] + "/source"
        try:
            application = verify_exact_application(
                patch.decode("utf-8"),
                _safe_path(root, original_dir),
                _safe_path(root, candidate_dir),
            )
        except UnicodeError as exc:
            raise ValueError("Patch must be UTF-8 text") from exc
        left_files = manifests["baseline"]["source"]["files"]
        right_files = manifests["candidate"]["source"]["files"]
        changed = {
            name
            for name in set(left_files) | set(right_files)
            if left_files.get(name) != right_files.get(name)
        }
        if {item["path"] for item in application["files"]} != changed:
            raise ValueError("Source-tree changes differ from declared patch files")
        before, after = results["baseline"], results["candidate"]
        if before["status"] != "completed" or before["steps"] != steps:
            raise _MissingEvidence("completed original baseline at requested steps")
        baseline_pairing = before.get("pairing_capture", {})
        pairing_available = {
            role: _pairing_available(result, contracts[role]) for role, result in results.items()
        }
        pairing = (
            derive_pairing(before, after, required_steps=steps)
            if all(pairing_available.values())
            else {
                "checks": dict.fromkeys(("same_inputs", "same_effective_batch", "same_objective"))
            }
        )
        precision = {
            "baseline": observed_precision(before),
            "candidate": observed_precision(after),
        }
        observation["context"] = {
            "source_tree_sha256": sources,
            "patch_sha256": patch_sha,
            "workload": {
                "profile": contracts["baseline"]["profile"],
                "contract_sha256": contracts["baseline"]["contract_sha256"],
                "inputs_sha256": _digest(baseline_pairing.get("tensors")),
                "initial_parameters_sha256": _digest(baseline_pairing.get("initial_parameters")),
                "updates_sha256": _digest(baseline_pairing.get("updates")),
            },
            "original_argv": original,
            "effective_argv": effective,
            "target": target,
            "reclaim_reduction_pct": reclaim,
            "required_steps": steps,
            "max_seconds": max_seconds,
            "device": request["device"],
            "policy": policy,
            "environment": environments,
            "observed_precision": precision,
        }
        compared = compare_runs(
            before,
            after,
            target=target,
            policy=policy,
            pairing=pairing["checks"],
            numerics_impact=impact,
            required_steps=steps,
            reclaim_reduction_pct=reclaim,
        ).model_dump()
        for field in (
            "completed",
            "target_met",
            "loss_equivalence",
            "peak_before",
            "peak_after",
            "max_loss_delta",
            "numerics_changed",
            "comparison_precision",
        ):
            if field in verification and _canonical(verification[field]) != _canonical(
                compared[field]
            ):
                raise ValueError("Saved verification disagrees with recomputed " + field)
        if "checks" in verification:
            if type(verification["checks"]) is not dict:
                raise ValueError("Saved verification checks must be an object")
            for key, value in compared["checks"].items():
                if key in verification["checks"] and _canonical(
                    verification["checks"][key]
                ) != _canonical(value):
                    raise ValueError("Saved verification check disagrees with recomputation")
        observation["metrics"] = {
            key: compared[key]
            for key in (
                "peak_before",
                "peak_after",
                "reduction_pct",
                "loss_equivalence",
                "max_loss_delta",
                "throughput_regression_pct",
                "target_met",
            )
        }
        checks = compared["checks"]
        concrete_failures = []
        if after["status"] != "completed":
            concrete_failures.append("candidate ended with " + after["status"])
        if after["steps"] != steps:
            concrete_failures.append("candidate did not complete the requested updates")
        failure_observable = {
            "memory_target": checks.get("measured_cuda_peaks") is True,
            "loss_tolerance": checks.get("loss_comparable") is True,
            "throughput_limit": (
                compared["throughput_regression_pct"] is not None
                and checks.get("gpu_observation_clear") is True
                and checks.get("same_gpu_hardware") is True
            ),
            "numerics_policy": "unknown" not in precision.values(),
            "parameter_policy": (
                compared["parameter_count_before"] is not None
                and compared["parameter_count_after"] is not None
                and compared["parameter_count_before"] != compared["parameter_count_after"]
            ),
        }
        for key, observable in failure_observable.items():
            if observable and checks.get(key) is False:
                concrete_failures.append(key + " failed")
        for key, value in pairing["checks"].items():
            if value is False:
                concrete_failures.append(key + " failed")
        if concrete_failures:
            observation["status"] = "tested_fail"
            observation["reasons"] = concrete_failures
        else:
            supporting = (
                compared["target_met"]
                and all(value is True for value in pairing["checks"].values())
                and "unknown" not in precision.values()
                and checks.get("loss_series_aligned_to_updates") is True
                and checks.get("gpu_observation_clear") is True
                and environments["baseline"] == environments["candidate"]
                and all(pairing_available.values())
            )
            if supporting:
                observation["status"] = "tested_pass"
                observation["reasons"] = [
                    "All required observations hold at this exact recorded context."
                ]
            else:
                observation["reasons"] = [
                    "The available evidence does not establish every stricter applicability check."
                ]
        return observation
    except _MissingEvidence as exc:
        observation["reasons"] = ["Evidence unavailable or unsupported: " + str(exc)]
        return observation
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Invalid or inconsistent applicability evidence schema") from exc


def _implementation_hashes():
    names = (
        "applicability.py",
        "compare.py",
        "pairing.py",
        "precision.py",
        "policy.py",
        "checkpoint.py",
        "offload.py",
    )
    directory = Path(__file__).parent
    result = {
        "headroom/verify/" + name: hashlib.sha256(
            _read_bytes(directory / name, MAX_JSON_BYTES)
        ).hexdigest()
        for name in names
    }
    result["headroom/patch_validation.py"] = hashlib.sha256(
        _read_bytes(directory.parent / "patch_validation.py", MAX_JSON_BYTES)
    ).hexdigest()
    return result


def build_scope(evidence_root: Path, selections: list[dict]) -> dict:
    """Inspect up to 128 explicit archived job/round pairs without executing targets."""
    root = _root(evidence_root)
    if type(selections) is not list or not 1 <= len(selections) <= 128:
        raise ValueError("Select between 1 and 128 observations")
    seen = set()
    clean = []
    for selection in selections:
        if type(selection) is not dict or set(selection) != {"job", "round"}:
            raise ValueError("Selections require exactly job and round")
        _parts(selection["job"])
        number = _integer(selection["round"], "round")
        identity = (selection["job"], number)
        if identity in seen:
            raise ValueError("Duplicate observation selection")
        seen.add(identity)
        clean.append({"job": selection["job"], "round": number})
    scope = {
        "protocol": PROTOCOL,
        "selections": clean,
        "observations": [_observe(root, item) for item in clean],
        "implementation_hashes": _implementation_hashes(),
        "limitations": list(LIMITATIONS),
    }
    _canonical(scope)
    # Match the CLI's pretty JSON wire format, not only the smaller canonical
    # encoding, so every generated record can be read by the bounded loader.
    encoded = json.dumps(scope, indent=2, allow_nan=False) + "\n"
    if len(encoded.encode()) > MAX_JSON_BYTES:
        raise ValueError("Scope record exceeds the JSON input size limit")
    return scope


def check_scope(evidence_root: Path, scope: dict, query: dict) -> dict:
    """Rebuild all evidence before making an exact-context lookup; no extrapolation."""
    try:
        if type(scope) is not dict or scope.get("protocol") != PROTOCOL:
            raise ValueError("Unsupported scope protocol")
        rebuilt = build_scope(evidence_root, scope.get("selections"))
        if _canonical(rebuilt) != _canonical(scope):
            raise ValueError("Scope or archived evidence changed; rebuild and review explicitly")
        if type(query) is not dict or not query:
            raise ValueError("Query must be a complete nonempty context object")
        key = _canonical(query)
        matches = [
            item
            for item in rebuilt["observations"]
            if item["context"] is not None and _canonical(item["context"]) == key
        ]
        if not matches:
            fields = set()
            for item in rebuilt["observations"]:
                context = item["context"]
                if context is not None:
                    for field in set(context) | set(query):
                        if (
                            field not in context
                            or field not in query
                            or _canonical(context[field]) != _canonical(query[field])
                        ):
                            fields.add(field)
            return {
                "status": "unknown",
                "reasons": [
                    "No exact recorded context matches; untested conditions are not inferred."
                ],
                "mismatched_fields": sorted(fields)[:64],
                "matching_observations": [],
            }
        statuses = {item["status"] for item in matches}
        status = (
            "tested_fail"
            if "tested_fail" in statuses
            else ("tested_pass" if statuses == {"tested_pass"} else "unknown")
        )
        return {
            "status": status,
            "reasons": [
                "A recorded failure dominates conflicting passes; otherwise every matching observation must pass."
            ],
            "matching_observations": [
                {
                    "selection": item["selection"],
                    "status": item["status"],
                    "provenance": item["provenance"],
                }
                for item in matches
            ],
            "mismatched_fields": [],
        }
    except (ValueError, OSError, TypeError, RecursionError, OverflowError) as exc:
        return {
            "status": "invalid_evidence",
            "reasons": [str(exc)],
            "matching_observations": [],
            "mismatched_fields": [],
        }
