"""Bounded, declarative project settings for the local fix CLI.

Project files cannot select providers, authorize spending, or change evidence scope.
"""

import os
import stat
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from headroom.lab.envs import validate_allocator
from headroom.orchestrator import Policy
from headroom.verify.compare import parse_target
from headroom.verify.reference_config import NumericalReference

MAX_CONFIG_BYTES = 16384
BatchFlag = Literal["--batch", "--batch_size", "--batch-size"]


class ProjectConfigError(ValueError):
    """A safe-to-display project configuration error."""


class BatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    arg: BatchFlag
    value: Annotated[int, Field(ge=1)] | None = None


class ProjectConfig(BaseModel):
    """Only existing repair controls, plus legacy batch discovery metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    version: Literal[1] = 1
    script: str | None = None
    script_args: list[str] = Field(default_factory=list, max_length=100)
    target: str = "fix-oom"
    reclaim_reduction_pct: float = Field(default=30, gt=0, le=100)
    policy: Policy = Field(default_factory=Policy)
    numerical_reference: NumericalReference = Field(default_factory=NumericalReference)
    allocator_conf: str | None = None
    max_steps: int = Field(default=20, ge=1, le=10000)
    max_seconds: int = Field(default=120, ge=1, le=3600)
    seed: int = Field(default=1337, ge=0, lt=2**32)
    device: Literal["cpu", "cuda"] = "cuda"
    max_rounds: int = Field(default=6, ge=1, le=6)
    search_mode: Literal["until_target", "bounded_pareto"] = "until_target"
    batch: Annotated[int, Field(ge=1)] | BatchConfig | None = None
    batch_arg: BatchFlag | None = None

    @field_validator("allocator_conf")
    @classmethod
    def supported_allocator(cls, value):
        return validate_allocator(value)

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("version must be an integer")
        return value

    @field_validator("script")
    @classmethod
    def relative_script(cls, value):
        if value is not None and (
            not value or "\0" in value or Path(value).is_absolute() or ".." in Path(value).parts
        ):
            raise ValueError("script must be a relative path within the project")
        return value

    @field_validator("script_args")
    @classmethod
    def literal_arguments(cls, values):
        if any("\0" in value for value in values):
            raise ValueError("script arguments cannot contain NUL")
        return values

    @field_validator("target")
    @classmethod
    def known_target(cls, value):
        parse_target(value)
        return value


class _ProjectLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    """Reject duplicate keys rather than silently changing a policy setting."""
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ProjectConfigError("Project configuration keys must be unique strings.")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_ProjectLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_project_config(path: Path) -> ProjectConfig:
    """Read a regular, non-symlink YAML file without executing or importing its code."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFIG_BYTES:
                raise ProjectConfigError("Project configuration must be a regular file <= 16 KiB.")
            content = handle.read(MAX_CONFIG_BYTES + 1)
        if len(content) > MAX_CONFIG_BYTES:
            raise ProjectConfigError("Project configuration exceeds 16 KiB.")
        document = yaml.load(content, Loader=_ProjectLoader)
        if not isinstance(document, dict):
            raise ProjectConfigError("Project configuration must contain a YAML mapping.")
        return ProjectConfig.model_validate(document)
    except ProjectConfigError:
        raise
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
        TypeError,
        RecursionError,
    ):
        # Validation/YAML errors can contain the offending value; do not echo raw project content.
        raise ProjectConfigError(
            "Invalid project configuration: check supported fields, types, ranges, and file safety."
        ) from None


def find_project_config(
    explicit: Path | None,
    *,
    script: Path | None,
    source_root: Path | None,
    remote_repository: bool = False,
) -> Path | None:
    """Autodiscover only the selected local project, never a downloaded repository."""
    if explicit is not None:
        return explicit
    if remote_repository:
        return None
    root = source_root if source_root is not None else script.parent if script else Path.cwd()
    candidate = root / "headroom.yaml"
    return candidate if candidate.exists() or candidate.is_symlink() else None


def configured_script(config: ProjectConfig, path: Path) -> Path | None:
    if config.script is None:
        return None
    root = path.parent.resolve()
    script = (root / config.script).resolve()
    if not script.is_relative_to(root):
        raise ProjectConfigError(
            "Configured script must remain inside the configuration directory."
        )
    return script
