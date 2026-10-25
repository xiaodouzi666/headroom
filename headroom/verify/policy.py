"""Static patch honesty checks. These guardrails are not a sandbox or an equivalence proof."""

from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath

from headroom.lab.envs import validate_allocator

MODEL_KEYS = {
    "layers",
    "width",
    "sequence",
    "features",
    "classes",
    "student_width",
    "teacher_width",
    "teacher_depth",
    "n_layer",
    "n_layers",
    "num_layers",
    "num_hidden_layers",
    "num_blocks",
    "depth",
    "n_embd",
    "hidden_size",
    "d_model",
    "embed_dim",
    "embedding_dim",
    "vocab_size",
    "block_size",
    "seq_len",
    "sequence_length",
    "max_seq_length",
    "max_position_embeddings",
    "context_length",
    "n_head",
    "num_attention_heads",
    "intermediate_size",
    "in_features",
    "out_features",
    "num_embeddings",
    "in_channels",
    "out_channels",
    "kernel_size",
}
TRAIN_KEYS = {
    "steps",
    "max_steps",
    "max_iters",
    "num_train_epochs",
    "epochs",
    "total_steps",
    "train_steps",
    "num_steps",
    "max_train_steps",
    "train_iters",
    "iterations",
    "n_steps",
    "train_size",
    "dataset_size",
    "num_samples",
    "max_train_samples",
    "limit_train_batches",
}
BATCH_KEYS = {
    "batch",
    "micro_batch",
    "batch_size",
    "micro_batch_size",
    "per_device_train_batch_size",
}
ACCUM_KEYS = {"gradient_accumulation_steps", "grad_accum_steps", "accumulation_steps"}
PRECISION_NAMES = {
    "autocast",
    "half",
    "bfloat16",
    "float16",
    "float8_e4m3fn",
    "float8_e5m2",
    "set_default_dtype",
    "set_float32_matmul_precision",
    "allow_tf32",
    "float32",
    "float64",
}
PRECISION_CLI = {"bf16", "fp16", "dtype", "mixed_precision", "tf32"}
PRECISION_KEYS = PRECISION_CLI | {
    "precision",
    "torch_dtype",
    "amp_dtype",
    "use_amp",
    "use_bf16",
    "use_fp16",
}
MEMORY_CLI = {
    "gradient_checkpointing",
    "checkpointing",
    "use_reentrant",
    "use_cache",
    "optim",
    "optimizer",
    "fused",
    "foreach",
    "torch_compile",
}
DENIED_MODULES = {
    "socket",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "ftplib",
    "paramiko",
    "subprocess",
    "ctypes",
}
DENIED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "os.system",
    "os.popen",
    "os.spawn",
    "os.exec",
    "os.fork",
    "os._exit",
    "sys.exit",
    "shutil.rmtree",
    "os.open",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.rename",
    "os.replace",
}
WRITE_METHODS = {"write_text", "write_bytes", "unlink", "rmdir", "rename", "replace", "mkdir"}
SECRET_NAMES = {"NEBIUS_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"}
SAFE_EXTENSIONS = {".py", ".json", ".toml", ".yaml", ".yml", ".cfg", ".ini"}
DENIED_PARTS = {".git", ".ssh", ".aws", ".config", ".venv", "venv", "node_modules", "runs"}


@dataclass(frozen=True)
class PatchPolicy:
    allow_numerics_change: bool = False
    allow_model_change: bool = False
    allow_batch_grad_accum: bool = True
    allow_batch_change: bool | None = None
    allow_grad_accum: bool | None = None
    max_throughput_regression_pct: float = 25.0

    def __post_init__(self):
        for name in ("allow_numerics_change", "allow_model_change", "allow_batch_grad_accum"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")
        for name in ("allow_batch_change", "allow_grad_accum"):
            if getattr(self, name) is not None and type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean or None")
        value = self.max_throughput_regression_pct
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("throughput tolerance must be finite and nonnegative")

    @property
    def batch_allowed(self):
        return (
            self.allow_batch_grad_accum
            and self.allow_batch_change is not False
            and self.allow_grad_accum is not False
        )


def normalize_policy(value=None) -> PatchPolicy:
    if value is None:
        return PatchPolicy()
    if isinstance(value, PatchPolicy):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("policy must be PatchPolicy or mapping")
    unknown = set(value) - {field.name for field in fields(PatchPolicy)}
    if unknown:
        raise ValueError("unknown patch policy fields: " + ", ".join(sorted(unknown)))
    return PatchPolicy(**dict(value))


@dataclass(frozen=True)
class PolicyIssue:
    code: str
    message: str
    path: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class PolicyReport:
    allowed: bool
    issues: tuple[PolicyIssue, ...] = ()
    notes: tuple[str, ...] = ()
    requires_runtime_verification: bool = True


def safe_relative_path(value: str, root=None) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", value)
        or value.startswith("/")
    ):
        raise ValueError("patch path must be a plain relative POSIX path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("patch path contains traversal or empty components")
    if any(
        part.lower() in DENIED_PARTS
        or part.lower().startswith(".env")
        or part.lower()
        in {"credentials.json", "secrets.json", "secrets.yaml", "secrets.yml", "token.json"}
        for part in path.parts
    ):
        raise ValueError("patch path targets protected metadata or credentials")
    if path.suffix.lower() not in SAFE_EXTENSIONS:
        raise ValueError("unsupported patch target extension")
    if root is not None:
        base = Path(root).resolve(strict=True)
        current = base
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("patch path traverses a symbolic link")
        if not current.resolve().is_relative_to(base):
            raise ValueError("patch path escapes source root")
    return str(path)


def validate_env_changes(changes) -> tuple[PolicyIssue, ...]:
    if not isinstance(changes, Mapping):
        return (PolicyIssue("INVALID_ENVIRONMENT", "Environment changes must be a mapping."),)
    issues = []
    for key, value in changes.items():
        if key != "PYTORCH_CUDA_ALLOC_CONF":
            issues.append(
                PolicyIssue("ENVIRONMENT_FORBIDDEN", "Only the Lab allocator setting may change.")
            )
        else:
            try:
                validate_allocator(value)
            except (ValueError, TypeError):
                issues.append(
                    PolicyIssue("INVALID_ALLOCATOR", "Unsupported allocator configuration.")
                )
    return tuple(issues)


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return parent + "." + node.attr if parent else "<expression>." + node.attr
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        return str(node.slice.value)
    return ""


def _number(node, constants):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        try:
            value = float(node.value)
            return value if math.isfinite(value) else None
        except (OverflowError, ValueError):
            return None
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _number(node.operand, constants)
        return None if value is None else value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left, right = _number(node.left, constants), _number(node.right, constants)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            elif isinstance(node.op, ast.FloorDiv):
                result = left // right
            else:
                return None
            return result if math.isfinite(result) else None
        except (OverflowError, ZeroDivisionError):
            return None
    return None


def _key(value):
    return value.rsplit(".", 1)[-1].lstrip("-").replace("-", "_").lower()


def _bindings(tree):
    constants = {}
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = _number(node.value, constants)
                for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    if isinstance(target, ast.Name) and value is not None:
                        constants[target.id] = value
    values = defaultdict(list)
    interesting = MODEL_KEYS | TRAIN_KEYS | BATCH_KEYS | ACCUM_KEYS

    def add(name, value):
        name = _key(name)
        if name in interesting and value is not None:
            values[name].append(
                (_number(value, constants), ast.dump(value, include_attributes=False))
            )
            if isinstance(value, ast.IfExp):
                add(name, value.body)
                add(name, value.orelse)

    def add_assignment(target, value):
        if isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(value.elts):
                for element, component in zip(target.elts, value.elts, strict=True):
                    add_assignment(element, component)
            elif (
                isinstance(value, ast.IfExp)
                and isinstance(value.body, (ast.Tuple, ast.List))
                and isinstance(value.orelse, (ast.Tuple, ast.List))
                and len(target.elts) == len(value.body.elts) == len(value.orelse.elts)
            ):
                for element, left, right in zip(
                    target.elts, value.body.elts, value.orelse.elts, strict=True
                ):
                    add_assignment(element, ast.IfExp(test=value.test, body=left, orelse=right))
            else:
                for element in target.elts:
                    add_assignment(element, value)
        else:
            add(_name(target), value)

    constructors = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _key(_name(node.func)) in {
            "linear",
            "embedding",
            "conv1d",
            "conv2d",
            "conv3d",
            "transformerencoderlayer",
            "transformerdecoderlayer",
        }:
            name = _name(node.func)
            occurrence = constructors[name]
            constructors[name] += 1
            for index, argument in enumerate(node.args[:2]):
                values[f"constructor:{name}:{occurrence}:{index}"].append(
                    (_number(argument, constants), ast.dump(argument))
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                add_assignment(target, node.value)
        elif isinstance(node, ast.keyword) and node.arg:
            add(node.arg, node.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    add(key.value, value)
        elif isinstance(node, ast.Call) and _name(node.func).endswith("add_argument"):
            flag = next(
                (
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("--")
                ),
                None,
            )
            default = next((kw.value for kw in node.keywords if kw.arg == "default"), None)
            if flag and default is not None:
                add(flag, default)
        elif (
            isinstance(node, ast.For)
            and _key(_name(node.target))
            in {"step", "epoch", "iteration", "iter", "batch_idx", "it"}
            and isinstance(node.iter, ast.Call)
            and _name(node.iter.func) == "range"
            and node.iter.args
        ):
            bound = node.iter.args[0] if len(node.iter.args) == 1 else node.iter.args[1]
            values["loop:" + _name(node.target)].append(
                (_number(bound, constants), ast.dump(bound))
            )
    return dict(values)


def _precision(tree):
    result, aliases = Counter(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (node.module or "") + "." + alias.name
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if _key(_name(target)) in PRECISION_KEYS:
                    result[ast.dump(node, include_attributes=False)] += 1
        elif isinstance(node, ast.keyword) and node.arg in PRECISION_KEYS:
            result[ast.dump(node, include_attributes=False)] += 1
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in PRECISION_KEYS:
                    result[ast.dump(key) + ":" + ast.dump(value)] += 1
        if isinstance(node, (ast.Attribute, ast.Name)):
            name = _name(node)
            root, dot, tail = name.partition(".")
            name = aliases.get(root, root) + (dot + tail if dot else "")
            if _key(name) in PRECISION_NAMES or "8bit" in name.lower():
                result[ast.dump(node, include_attributes=False)] += 1
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _key(_name(node.func)) in {"float", "double", "to", "type"}
            and (_key(_name(node.func)) != "to" or any(kw.arg == "dtype" for kw in node.keywords))
        ):
            result[ast.dump(node, include_attributes=False)] += 1
    return result


def _security_findings(tree):
    findings, aliases = [], {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (node.module or "") + "." + alias.name

    def resolve(name):
        first, dot, rest = name.partition(".")
        return aliases.get(first, first) + (dot + rest if dot else "")

    for node in ast.walk(tree):
        code, detail = None, None
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(module.split(".")[0] in DENIED_MODULES for module in modules):
                code, detail = (
                    "NETWORK_OR_PROCESS_FORBIDDEN",
                    "Patch adds network/process/foreign-code import.",
                )
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in SECRET_NAMES
        ):
            code, detail = "SECRET_ACCESS_FORBIDDEN", "Patch references a credential variable."
        if isinstance(node, ast.Call):
            name = resolve(_name(node.func))
            if (
                name in DENIED_CALLS
                or name.split(".")[0] in DENIED_MODULES
                or name.startswith(("os.exec", "os.spawn"))
            ):
                code, detail = (
                    "NETWORK_OR_PROCESS_FORBIDDEN",
                    "Patch adds dynamic execution, process or network access.",
                )
            if name == "open" or name.endswith(".open"):
                filename = (
                    node.args[0]
                    if name == "open" and node.args
                    else getattr(node.func, "value", None)
                )
                if (
                    isinstance(filename, ast.Call)
                    and _key(_name(filename.func)) == "path"
                    and filename.args
                ):
                    filename = filename.args[0]
                literal = (
                    filename.value
                    if isinstance(filename, ast.Constant) and isinstance(filename.value, str)
                    else None
                )
                if literal is not None and (
                    (literal.startswith("/") and not literal.startswith("/out/"))
                    or ".." in PurePosixPath(literal).parts
                ):
                    code, detail = (
                        "FILESYSTEM_ESCAPE",
                        "New file access escapes the permitted area.",
                    )
                elif literal is None:
                    code, detail = (
                        "FILESYSTEM_ACCESS_UNVERIFIED",
                        "New dynamic file access needs review.",
                    )
                mode_node = (
                    node.args[1]
                    if name == "open" and len(node.args) > 1
                    else next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
                )
                mode = (
                    mode_node.value
                    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str)
                    else "r"
                    if mode_node is None
                    else "unknown"
                )
                if (mode == "unknown" or any(c in mode for c in "wax+")) and (
                    literal is None or not literal.startswith("/out/")
                ):
                    code, detail = "FILESYSTEM_ESCAPE", "New file writes must stay in /out."
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "read_text",
                "read_bytes",
            }:
                receiver = node.func.value
                value = (
                    receiver.args[0]
                    if isinstance(receiver, ast.Call)
                    and _key(_name(receiver.func)) == "path"
                    and receiver.args
                    else None
                )
                literal = (
                    value.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    else None
                )
                if literal is None:
                    code, detail = (
                        "FILESYSTEM_ACCESS_UNVERIFIED",
                        "New dynamic file read needs review.",
                    )
                elif (
                    literal.startswith("/") and not literal.startswith("/out/")
                ) or ".." in PurePosixPath(literal).parts:
                    code, detail = "FILESYSTEM_ESCAPE", "New file read escapes the permitted area."
            if isinstance(node.func, ast.Attribute) and node.func.attr in WRITE_METHODS:
                receiver = node.func.value
                value = (
                    receiver.args[0]
                    if isinstance(receiver, ast.Call)
                    and _key(_name(receiver.func)) == "path"
                    and receiver.args
                    else None
                )
                literal = (
                    value.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    else None
                )
                if (
                    literal is None
                    or not literal.startswith("/out/")
                    or ".." in PurePosixPath(literal).parts
                ):
                    code, detail = (
                        "FILESYSTEM_ESCAPE",
                        "New filesystem writes must use literal /out paths.",
                    )
        if code:
            # The signature includes the expression, not only a count of unsafe operations.
            findings.append(
                (code, detail, getattr(node, "lineno", 0), ast.dump(node, include_attributes=False))
            )
    return findings


def _structured_bindings(text):
    values = defaultdict(list)
    for match in re.finditer(
        r"""(?m)(?:^|[{,])\s*["']?([A-Za-z_][A-Za-z0-9_]*)["']?\s*[:=]\s*([^,\n#}]+)""", text
    ):
        name, raw = _key(match[1]), match[2].strip()
        if name in MODEL_KEYS | TRAIN_KEYS | BATCH_KEYS | ACCUM_KEYS:
            try:
                number = float(raw)
                number = number if math.isfinite(number) else None
            except ValueError:
                number = None
            values[name].append((number, raw))
    return dict(values)


def _binding_issues(before, after, policy, path, notes):
    issues = []
    for key, old in before.items():
        new = after.get(key, [])
        if old == new:
            continue
        old_numbers = [value for value, _ in old if value is not None]
        new_numbers = [value for value, _ in new if value is not None]
        if (
            len(old_numbers) == len(old) == len(new_numbers) == len(new)
            and old_numbers == new_numbers
        ):
            continue
        reduced = len(new) < len(old) or any(b < a for a, b in zip(old_numbers, new_numbers))
        unresolved = any(value is None for value, _ in new)
        if key in MODEL_KEYS or key.startswith("constructor:"):
            if not policy.allow_model_change:
                issues.append(
                    PolicyIssue(
                        "MODEL_SHRUNK" if reduced else "MODEL_CHANGED",
                        "Model shape must remain unchanged.",
                        path,
                    )
                )
            elif not any("MODEL_CHANGE_APPROVED" in note for note in notes):
                issues.append(
                    PolicyIssue(
                        "MODEL_CHANGE_UNLABELED",
                        "Authorized model changes require MODEL_CHANGE_APPROVED in notes.",
                        path,
                    )
                )
        elif key in TRAIN_KEYS or key.startswith("loop:"):
            if reduced or unresolved or not new:
                issues.append(
                    PolicyIssue(
                        "TRAINING_TRUNCATED",
                        "Training/data limits may not shrink or become unverifiable.",
                        path,
                    )
                )
        elif key in BATCH_KEYS | ACCUM_KEYS and not policy.batch_allowed:
            issues.append(
                PolicyIssue(
                    "BATCH_CHANGE_FORBIDDEN", "Batch/accumulation changes are disabled.", path
                )
            )
    for key in after.keys() - before.keys():
        if key in TRAIN_KEYS:
            issues.append(
                PolicyIssue(
                    "TRAINING_TRUNCATED", "New training/data limits need a trusted baseline.", path
                )
            )
        elif (
            key in MODEL_KEYS or key.startswith("constructor:")
        ) and not policy.allow_model_change:
            issues.append(
                PolicyIssue("MODEL_CHANGED", "A new shape override needs permission.", path)
            )
        elif key in BATCH_KEYS | ACCUM_KEYS and not policy.batch_allowed:
            issues.append(
                PolicyIssue(
                    "BATCH_CHANGE_FORBIDDEN", "Batch/accumulation changes are disabled.", path
                )
            )
    return issues


def _single_number(bindings, keys, default=None):
    values = {value for key in keys for value, _ in bindings.get(key, [])}
    return (
        next(iter(values))
        if len(values) == 1 and None not in values
        else default
        if not values
        else None
    )


def check_source_changes(
    before: Mapping[str, str], after: Mapping[str, str], *, policy=None, notes: Sequence[str] = ()
) -> PolicyReport:
    policy = normalize_policy(policy)
    issues, observations = [], []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path, ""), after.get(path, "")
        if old == new:
            continue
        issues.extend(_source_text_issues(path, new, check_security=False))
        if path not in after:
            issues.append(
                PolicyIssue(
                    "MODEL_SHRUNK", "Whole-file deletion is not an accepted memory repair.", path
                )
            )
            continue
        if path.lower().endswith(".py"):
            try:
                old_tree, new_tree = ast.parse(old), ast.parse(new)
            except SyntaxError as error:
                issues.append(
                    PolicyIssue(
                        "SYNTAX_INVALID", "Python source does not parse.", path, error.lineno
                    )
                )
                continue
            old_values, new_values = _bindings(old_tree), _bindings(new_tree)
            previous = Counter(
                (code, signature) for code, _, _, signature in _security_findings(old_tree)
            )
            for code, detail, line, signature in _security_findings(new_tree):
                if previous[(code, signature)]:
                    previous[(code, signature)] -= 1
                else:
                    issues.append(PolicyIssue(code, detail, path, line))
            if not policy.allow_numerics_change and _precision(old_tree) != _precision(new_tree):
                issues.append(
                    PolicyIssue(
                        "NUMERICS_CHANGE_FORBIDDEN",
                        "Precision/cast changes require permission.",
                        path,
                    )
                )
            for kind in (ast.Break, ast.Continue):
                if sum(isinstance(n, kind) for n in ast.walk(new_tree)) > sum(
                    isinstance(n, kind) for n in ast.walk(old_tree)
                ):
                    issues.append(
                        PolicyIssue("TRAINING_TRUNCATED", "Patch introduces loop skipping.", path)
                    )
            old_calls = Counter(
                _key(_name(n.func)) for n in ast.walk(old_tree) if isinstance(n, ast.Call)
            )
            new_calls = Counter(
                _key(_name(n.func)) for n in ast.walk(new_tree) if isinstance(n, ast.Call)
            )
            if any(new_calls[name] < old_calls[name] for name in ("backward", "step")):
                issues.append(
                    PolicyIssue("TRAINING_TRUNCATED", "Patch removes backward/update calls.", path)
                )

            def module_calls(tree):
                return Counter(
                    _name(n.func)
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and re.search(
                        r"(?:^|\.)(?:nn|torch\.nn)\.(?:Linear|Embedding|Conv[123]d|TransformerEncoderLayer|TransformerDecoderLayer|Sequential|ModuleList)$",
                        _name(n.func),
                    )
                )

            old_modules, new_modules = module_calls(old_tree), module_calls(new_tree)
            if (
                any(new_modules[name] < count for name, count in old_modules.items())
                and not policy.allow_model_change
            ):
                issues.append(
                    PolicyIssue("MODEL_SHRUNK", "Patch removes model-construction calls.", path)
                )
        else:
            old_values, new_values = _structured_bindings(old), _structured_bindings(new)
            precision_pattern = re.compile(
                r"""(?m)(?:^|[{,])\s*["']?("""
                + "|".join(sorted(PRECISION_KEYS))
                + r""")["']?\s*[:=]\s*([^,\n#}]+)"""
            )
            if not policy.allow_numerics_change and precision_pattern.findall(
                old
            ) != precision_pattern.findall(new):
                issues.append(
                    PolicyIssue(
                        "NUMERICS_CHANGE_FORBIDDEN",
                        "Configuration precision changes require permission.",
                        path,
                    )
                )
        issues.extend(_binding_issues(old_values, new_values, policy, path, notes))
        if any(old_values.get(key) != new_values.get(key) for key in BATCH_KEYS | ACCUM_KEYS):
            old_batch, new_batch = (
                _single_number(old_values, BATCH_KEYS),
                _single_number(new_values, BATCH_KEYS),
            )
            old_accum, new_accum = (
                _single_number(old_values, ACCUM_KEYS, 1),
                _single_number(new_values, ACCUM_KEYS, 1),
            )
            if (
                None not in (old_batch, new_batch, old_accum, new_accum)
                and old_batch * old_accum != new_batch * new_accum
            ):
                issues.append(
                    PolicyIssue(
                        "EFFECTIVE_BATCH_CHANGED",
                        "Batch times accumulation must preserve samples per update.",
                        path,
                    )
                )
            observations.append(
                "Batch changes require paired data-order/effective-batch verification."
            )
    unique = tuple(dict.fromkeys(issues))
    return PolicyReport(not unique, unique, tuple(dict.fromkeys(observations)))


def _argv_options(argv):
    positional, options, index = [], {}, 0
    while index < len(argv):
        token = argv[index]
        if not isinstance(token, str) or any(c in token for c in "\x00\n\r"):
            raise ValueError("CLI arguments must be plain strings")
        if not token.startswith("--"):
            positional.append(token)
            index += 1
            continue
        flag, separator, value = token.partition("=")
        if not re.fullmatch(r"--[A-Za-z][A-Za-z0-9_-]*", flag):
            raise ValueError("invalid CLI flag")
        if not separator:
            value = None
            if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                index += 1
                value = argv[index]
        key = _key(flag)
        if key in options:
            raise ValueError("duplicate CLI option")
        options[key] = (flag, value)
        index += 1
    return positional, options


def merge_cli_changes(base_cli, changes) -> list[str]:
    positional, existing = _argv_options(base_cli)
    extra, replacements = _argv_options(changes)
    if extra:
        raise ValueError("CLI changes may contain only long-option overrides")
    existing.update(replacements)
    result = list(positional)
    for flag, value in existing.values():
        result.append(flag)
        if value is not None:
            result.append(value)
    return result


def _explicit_cli_batch_pair(options):
    """Read only unambiguous, explicit supported flags; never infer defaults.

    This is the host's existing long-option syntax, not execution of a target
    parser. Other batch/accumulation aliases or non-integer inputs remain unknown.
    """
    names = {"batch_size", "gradient_accumulation_steps"}
    if set(options) & (BATCH_KEYS | ACCUM_KEYS) != names:
        return None
    values = []
    for name in ("batch_size", "gradient_accumulation_steps"):
        flag, raw = options[name]
        if flag != "--" + name or not isinstance(raw, str):
            return None
        # Match the existing CLI value size bound before integer conversion.
        if not re.fullmatch(r"[0-9]{1,1000}", raw):
            return None
        value = int(raw)
        if value <= 0:
            return None
        values.append(value)
    return tuple(values)


def check_cli_changes(base_cli, changes, *, policy=None, notes=()) -> PolicyReport:
    policy = normalize_policy(policy)
    try:
        _, before = _argv_options(base_cli)
        positional, after = _argv_options(changes)
    except (TypeError, ValueError):
        return PolicyReport(False, (PolicyIssue("CLI_INVALID", "Invalid argv override."),))
    if positional:
        return PolicyReport(
            False,
            (PolicyIssue("CLI_INVALID", "Positional/shell commands are forbidden in overrides."),),
        )
    issues = []
    allowed = MODEL_KEYS | TRAIN_KEYS | BATCH_KEYS | ACCUM_KEYS | PRECISION_CLI | MEMORY_CLI
    for key, (_, value) in after.items():
        prior = before.get(key, (None, None))[1]
        changed = key not in before or value != prior
        if key not in allowed:
            issues.append(
                PolicyIssue(
                    "CLI_OPTION_FORBIDDEN", "CLI override is outside memory/shape controls."
                )
            )
        if key in TRAIN_KEYS and changed:
            issues.append(
                PolicyIssue("TRAINING_TRUNCATED", "CLI may not override training/data limits.")
            )
        if key in MODEL_KEYS and changed:
            if not policy.allow_model_change:
                issues.append(PolicyIssue("MODEL_SHRUNK", "CLI shape changes need permission."))
            elif not any("MODEL_CHANGE_APPROVED" in note for note in notes):
                issues.append(
                    PolicyIssue(
                        "MODEL_CHANGE_UNLABELED", "Authorized shape changes must be labeled."
                    )
                )
        if key in PRECISION_CLI and changed and not policy.allow_numerics_change:
            issues.append(
                PolicyIssue("NUMERICS_CHANGE_FORBIDDEN", "CLI precision changes need permission.")
            )
        if key in BATCH_KEYS | ACCUM_KEYS and changed and not policy.batch_allowed:
            issues.append(
                PolicyIssue(
                    "BATCH_CHANGE_FORBIDDEN", "CLI batch/accumulation changes are disabled."
                )
            )
        if value is not None and (any(c in value for c in ";|&$\x60\n\r") or len(value) > 1000):
            issues.append(
                PolicyIssue("CLI_INVALID", "CLI values contain shell syntax or exceed limits.")
            )
    old_pair = _explicit_cli_batch_pair(before)
    new_pair = _explicit_cli_batch_pair({**before, **after})
    if old_pair is not None and new_pair is not None:
        old_product, new_product = old_pair[0] * old_pair[1], new_pair[0] * new_pair[1]
        if old_product != new_product:
            issues.append(
                PolicyIssue(
                    "EFFECTIVE_BATCH_CHANGED",
                    "Explicit CLI batch_size * gradient_accumulation_steps changed from "
                    f"{old_pair[0]} * {old_pair[1]} = {old_product} to "
                    f"{new_pair[0]} * {new_pair[1]} = {new_product}. "
                    "Preserve the original explicit product; runtime equivalence remains unverified.",
                )
            )
    return PolicyReport(
        not issues,
        tuple(dict.fromkeys(issues)),
        ("Effective batch and update counts need runtime verification.",),
    )


def check_parameter_counts(before, after, *, policy=None, notes=()) -> PolicyReport:
    policy = normalize_policy(policy)
    if type(before) is not int or type(after) is not int or before < 0 or after < 0:
        return PolicyReport(
            False,
            (
                PolicyIssue(
                    "PARAMETER_COUNT_UNVERIFIED", "Both observed parameter counts are required."
                ),
            ),
        )
    if before != after:
        if not policy.allow_model_change:
            return PolicyReport(
                False,
                (
                    PolicyIssue(
                        "MODEL_SHRUNK" if after < before else "MODEL_CHANGED",
                        "Observed parameter counts differ.",
                    ),
                ),
            )
        if not any("MODEL_CHANGE_APPROVED" in note for note in notes):
            return PolicyReport(
                False,
                (
                    PolicyIssue(
                        "MODEL_CHANGE_UNLABELED", "Authorized count changes must be labeled."
                    ),
                ),
            )
    return PolicyReport(
        True, notes=("Parameter count alone does not prove functional equivalence.",)
    )


_CREDENTIAL_PATTERN = re.compile(
    r"(?:\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b|\btvly-[A-Za-z0-9_-]{12,}\b|"
    r"\bhf_[A-Za-z0-9]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b|"
    r"""\b[A-Za-z_]*(?:api_key|access_token|secret|password)\b\s*[:=]\s*["'][^"'\n]{8,}["'])""",
    re.IGNORECASE,
)


def _source_text_issues(path, text, *, check_security=True, allowed_findings=()):
    issues = []
    match = _CREDENTIAL_PATTERN.search(text)
    if match:
        issues.append(
            PolicyIssue(
                "EMBEDDED_CREDENTIAL",
                "Source may contain a credential; content was not disclosed.",
                path,
                text.count("\n", 0, match.start()) + 1,
            )
        )
    if path.lower().endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, RecursionError) as error:
            return tuple(
                issues
                + [
                    PolicyIssue(
                        "SOURCE_SYNTAX_INVALID",
                        "Source cannot be parsed safely.",
                        path,
                        getattr(error, "lineno", None),
                    )
                ]
            )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and any(part.startswith(".env") for part in PurePosixPath(node.value).parts)
            ):
                issues.append(
                    PolicyIssue(
                        "ENV_FILE_ACCESS",
                        "Source references an environment credential file.",
                        path,
                        node.lineno,
                    )
                )
            if isinstance(node, ast.ImportFrom) and node.module == "dotenv":
                issues.append(
                    PolicyIssue(
                        "ENV_FILE_ACCESS",
                        "Source imports environment-file loading.",
                        path,
                        node.lineno,
                    )
                )
            if isinstance(node, ast.Import) and any(alias.name == "dotenv" for alias in node.names):
                issues.append(
                    PolicyIssue(
                        "ENV_FILE_ACCESS",
                        "Source imports environment-file loading.",
                        path,
                        node.lineno,
                    )
                )
            if isinstance(node, ast.Call) and _key(_name(node.func)) in {
                "load_dotenv",
                "dotenv_values",
            }:
                issues.append(
                    PolicyIssue(
                        "ENV_FILE_ACCESS",
                        "Source calls environment-file loading.",
                        path,
                        node.lineno,
                    )
                )
        if check_security:
            allowed = Counter(allowed_findings)
            for code, detail, line, signature in _security_findings(tree):
                if allowed[(code, signature)]:
                    allowed[(code, signature)] -= 1
                else:
                    issues.append(PolicyIssue(code, detail, path, line))
    return tuple(dict.fromkeys(issues))


def scan_source_forbidden(
    source, *, source_files=None, source_profile=None, sandboxed=False
) -> PolicyReport:
    """Pre-upload/pre-LLM guard; reports only filenames/reason codes, never matched source.

    A Mapping[str, str] accepts API uploads without writing them. A Path scans bounded
    regular source/config files, or exactly the caller-selected context files.
    .env/credential files are never opened. Runtime Docker remains mandatory.
    """
    issues, texts = [], {}
    allowed_findings = {}
    profile_notes = []
    if source_profile is not None:
        if (
            source_profile != "pinned_nanogpt"
            or isinstance(source, Mapping)
            or sandboxed is not True
        ):
            return PolicyReport(
                False,
                (
                    PolicyIssue(
                        "SOURCE_PROFILE_FORBIDDEN",
                        "Pinned source profiles require a verified local sandbox and directory input.",
                    ),
                ),
            )
        try:
            allowed_findings = _nanogpt_profile_findings(Path(source))
        except (ValueError, OSError, UnicodeError):
            return PolicyReport(
                False,
                (
                    PolicyIssue(
                        "SOURCE_PROFILE_UNVERIFIED",
                        "Pinned nanoGPT files or immutable configurator do not match their reviewed hashes.",
                    ),
                ),
            )
        profile_notes.append(
            "Pinned nanoGPT baseline AST allowances; Docker no-network, read-only source, safe equals-only argv required."
        )
    if isinstance(source, Mapping):
        for name, text in source.items():
            try:
                safe_relative_path(name)
            except (TypeError, ValueError):
                issues.append(PolicyIssue("SOURCE_PATH_FORBIDDEN", "Invalid source filename."))
                continue
            if not isinstance(text, str) or len(text.encode()) > 2 * 1024 * 1024:
                issues.append(
                    PolicyIssue("SOURCE_SIZE_INVALID", "Source text exceeds its limit.", name)
                )
                continue
            texts[name] = text
    else:
        import os

        base = Path(source).resolve(strict=True)
        if not base.is_dir():
            return PolicyReport(
                False, (PolicyIssue("SOURCE_ROOT_INVALID", "Source root must be a directory."),)
            )
        if source_files is None:
            names = []
            excluded = DENIED_PARTS | {
                ".cache",
                ".tools",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
                "secrets",
                "credentials",
            }
            for directory, dirs, files in os.walk(base, followlinks=False):
                dirs[:] = [
                    name
                    for name in dirs
                    if name not in excluded and not (Path(directory) / name).is_symlink()
                ]
                for name in files:
                    relative = str((Path(directory) / name).relative_to(base))
                    if (
                        Path(name).suffix.lower() in SAFE_EXTENSIONS
                        and not name.startswith(".env")
                        and name
                        not in {
                            "credentials.json",
                            "secrets.json",
                            "secrets.yaml",
                            "secrets.yml",
                            "token.json",
                        }
                    ):
                        names.append(relative)
        else:
            names = list(source_files)
        total = 0
        for name in sorted(set(names)):
            try:
                safe_relative_path(name, base)
                path = base / name
                if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("source leaf unavailable")
                if len(texts) >= 5000 or total + path.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("source set too large")
                text = path.read_text()
                total += len(text.encode())
                texts[name] = text
            except (OSError, ValueError, UnicodeError):
                issues.append(
                    PolicyIssue(
                        "SOURCE_UNREADABLE_OR_UNSAFE",
                        "Source file cannot be safely inspected.",
                        name,
                    )
                )
    for name, text in texts.items():
        issues.extend(
            _source_text_issues(name, text, allowed_findings=allowed_findings.get(name, ()))
        )
    return PolicyReport(
        not issues,
        tuple(dict.fromkeys(issues)),
        tuple(profile_notes)
        + ("Static inspection is incomplete; execute targets only in the Lab sandbox.",),
    )


NANOGPT_REF = "3adf61e154c3fe3fca428ad6bc3818b27a3b8291"
NANOGPT_HASHES = {
    "train.py": "413bd97b40bb400a2a0d01230e2946f056c263ebac1b7281c2367d964a123085",
    "configurator.py": "5cc23aca26b4ab3c0d9e5f82740f4781f9444f42718c15abcee70d93c5aabe8f",
    "model.py": "7c01703240dbec5d554527dc666e35b3df8391d0b117fddc07afcf325a21d11c",
}


def _nanogpt_profile_findings(source):
    """Permit only unsafe AST expressions from the exact reviewed local baseline.

    The caller authorizes this profile only for the pinned repository in a no-network
    Lab with read-only source. Uploaded mappings never receive these allowances.
    """
    project = Path(__file__).resolve().parents[2]
    baseline_payloads = None
    for baseline in (
        project / ".cache/upstream/nanoGPT",
        project / ".cache/reviewed/nanogpt" / NANOGPT_REF,
    ):
        try:
            if any(
                path.is_symlink()
                for path in (baseline, *baseline.parents)
                if path != project and path.is_relative_to(project)
            ):
                continue
            payloads = {}
            for name, expected in NANOGPT_HASHES.items():
                safe_relative_path(name, baseline)
                original = baseline / name
                if original.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("profile baseline too large")
                payload = original.read_bytes()
                if hashlib.sha256(payload).hexdigest() != expected:
                    raise ValueError("profile baseline mismatch")
                payloads[name] = payload
            baseline_payloads = payloads
            break
        except (OSError, ValueError):
            continue
    if baseline_payloads is None:
        raise ValueError("reviewed profile baseline unavailable")
    result = {}
    for name, expected in NANOGPT_HASHES.items():
        payload = baseline_payloads[name]
        safe_relative_path(name, source)
        current = source / name
        if not current.is_file() or current.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("profile source missing")
        if (
            name == "configurator.py"
            and hashlib.sha256(current.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("profile configurator changed")
        tree = ast.parse(payload.decode())
        result[name] = tuple(
            (code, signature) for code, _, _, signature in _security_findings(tree)
        )
    return result


def nanogpt_cli(argv, *, require_equals=True):
    """Reject positional config-file execution; optionally format validated overrides."""
    remaining = list(argv)
    prefix = []
    if remaining and Path(remaining[0]).name in {"python", "python3"}:
        prefix.append(remaining.pop(0))
    if remaining and remaining[0] == "train.py":
        prefix.append(remaining.pop(0))
    if prefix and Path(prefix[0]).name in {"python", "python3"} and prefix[-1] != "train.py":
        raise ValueError("nanoGPT entrypoint must be train.py")
    if require_equals:
        if any(
            not re.fullmatch(r"--[A-Za-z_][A-Za-z0-9_]*=[^\x00\n\r]+", token) for token in remaining
        ):
            raise ValueError("nanoGPT accepts only explicit --key=value arguments")
        return prefix + remaining
    positional, options = _argv_options(remaining)
    if positional or any(value is None for _, value in options.values()):
        raise ValueError("nanoGPT accepts no positional config files or value-free options")
    return prefix + [flag + "=" + value for flag, value in options.values()]
