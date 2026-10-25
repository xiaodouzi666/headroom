"""Explicit, bounded numerical reference protocol shared by execution entrypoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_REFERENCE_CPU_BYTES = 16 * 1024**3
MAX_REFERENCE_DISK_BYTES = 64 * 1024**3


class NumericalReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    strategy: Literal[
        "legacy_small_batch", "original_saved_tensor_offload", "original_workload_checkpoint"
    ] = "legacy_small_batch"
    cpu_saved_tensor_limit_bytes: int = Field(
        default=MAX_REFERENCE_CPU_BYTES, ge=1, le=MAX_REFERENCE_CPU_BYTES
    )
    disk_saved_tensor_limit_bytes: int = Field(default=0, ge=0, le=MAX_REFERENCE_DISK_BYTES)
    max_seconds: int | None = Field(default=None, ge=1, le=480)

    @model_validator(mode="after")
    def explicit_offload(self):
        if self.strategy == "legacy_small_batch" and (
            self.cpu_saved_tensor_limit_bytes != MAX_REFERENCE_CPU_BYTES
            or self.disk_saved_tensor_limit_bytes
            or self.max_seconds is not None
        ):
            raise ValueError(
                "Offload resource settings require the explicit original-workload strategy"
            )
        if self.strategy == "original_workload_checkpoint" and (
            self.cpu_saved_tensor_limit_bytes != MAX_REFERENCE_CPU_BYTES
            or self.disk_saved_tensor_limit_bytes
        ):
            raise ValueError(
                "Checkpoint references do not use saved-tensor offload resource settings"
            )
        return self

    def verify_kwargs(self):
        if self.strategy == "legacy_small_batch":
            return {}
        if self.strategy == "original_workload_checkpoint":
            return {
                "reference_strategy": self.strategy,
                "reference_max_seconds": self.max_seconds,
            }
        return {
            "reference_strategy": self.strategy,
            "reference_offload_bytes": self.cpu_saved_tensor_limit_bytes,
            "reference_offload_disk_bytes": self.disk_saved_tensor_limit_bytes,
            "reference_max_seconds": self.max_seconds,
        }
