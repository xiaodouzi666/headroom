"""DRAFT ONLY: bounded, cooperative, value-only optimizer group metadata.

No torch import. No tensor conversion, arbitrary object repr, source default
inference, optimizer mutation, or evidence of a completed optimizer update.
"""

import json
import math
import re
import weakref

OPTIONS = (
    "lr",
    "momentum",
    "weight_decay",
    "dampening",
    "nesterov",
    "betas",
    "eps",
    "amsgrad",
    "maximize",
    "foreach",
    "fused",
    "capturable",
    "differentiable",
    "initial_lr",
    "alpha",
    "rho",
    "lr_decay",
    "initial_accumulator_value",
    "lambd",
    "t0",
    "etas",
    "step_sizes",
    "momentum_decay",
    "decoupled_weight_decay",
)
MAX_OPTIMIZERS = 256
MAX_GROUPS = 64
MAX_GROUP_KEYS = 64
MAX_CONFIGS = 64
MAX_RECORDS = 256
MAX_MEMBERS = 16384
MAX_RAW_BYTES = 65536


def _scalar(value):
    if value is None:
        return ["none", None]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int and -(2**63) <= value < 2**63:
        return ["int", value]
    if type(value) is float and math.isfinite(value):
        return ["float", value]
    return ["unsupported", None]


def encode_option(name, value):
    # Preserve the exact built-in scalar/container types. Never cast objects,
    # tensor scalars, numpy scalars, custom sequences or subclasses.
    if name in {"betas", "etas", "step_sizes"} and type(value) in (tuple, list):
        if len(value) != 2:
            return ["unsupported", None]
        values = [_scalar(item) for item in value]
        if any(item[0] not in {"int", "float"} for item in values):
            return ["unsupported", None]
        return ["tuple" if type(value) is tuple else "list", values]
    return _scalar(value)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


class OptimizerGroupOptionObserver:
    def __init__(self):
        self._identities = {}
        self._identity_count = 0
        self._configs = {}
        self._records = {}
        self._member_count = 0
        self.complete = True
        self.stopped = False
        self.events = {"base_constructor_return": 0, "step_pre": 0}

    def observe(self, optimizer, *, stage, call, identify):
        # Optional observer failures must never replace the target's native
        # result. Deadline/step-limit BaseExceptions still propagate.
        try:
            self._observe(optimizer, stage=stage, call=call, identify=identify)
        except Exception:  # noqa: BLE001 - optional metadata must not replace native behavior
            self.complete = False
            self.stopped = True

    def _observe(self, optimizer, *, stage, call, identify):
        if stage not in self.events or type(call) is not int or not 0 <= call <= 65536:
            raise ValueError("unsupported observation boundary")
        self.events[stage] += 1
        if self.events[stage] > 65536:
            raise ValueError("observation event limit")
        if self.stopped:
            return
        identity = self._identities.get(id(optimizer))
        if identity is None or identity[0]() is not optimizer:
            if self._identity_count >= MAX_OPTIMIZERS:
                raise ValueError("optimizer identity limit")
            self._identity_count += 1
            identity = (weakref.ref(optimizer), f"o{self._identity_count:04d}")
            self._identities[id(optimizer)] = identity
        # Access only the real instance dictionary and exact built-in
        # containers. Do not traverse properties or arbitrary mapping objects.
        attributes = object.__getattribute__(optimizer, "__dict__")
        if type(attributes) is not dict:
            raise ValueError("unsupported optimizer attributes")
        groups = attributes.get("param_groups")
        if type(groups) is not list or not 0 < len(groups) <= MAX_GROUPS:
            raise ValueError("unsupported optimizer groups")
        for index, group in enumerate(groups):
            if type(group) is not dict or len(group) > MAX_GROUP_KEYS:
                raise ValueError("unsupported optimizer group")
            params = group.get("params")
            if type(params) not in (list, tuple) or len(params) > 8192:
                raise ValueError("unsupported optimizer parameters")
            parameter_ids = [identify(parameter) for parameter in params]
            if any(
                type(token) is not str or re.fullmatch(r"p[0-9]{5,6}", token) is None
                for token in parameter_ids
            ):
                raise ValueError("unsupported parameter identity")
            if len(set(parameter_ids)) != len(parameter_ids):
                raise ValueError("duplicate optimizer parameter")
            present = {name: encode_option(name, group[name]) for name in OPTIONS if name in group}
            unknown_keys = sum(
                type(key) is not str or key not in (*OPTIONS, "params") for key in group
            )
            config = {"present": present, "unrecognized_option_keys": unknown_keys}
            config_key = canonical(config)
            new_config = config_key not in self._configs
            if new_config and len(self._configs) >= MAX_CONFIGS:
                raise ValueError("configuration limit")
            config_record = self._configs.get(config_key) or {
                "id": f"c{len(self._configs) + 1:03d}",
                **config,
            }
            config_id = config_record["id"]
            key = canonical([identity[1], index, stage, config_id, parameter_ids])
            new_record = key not in self._records
            if new_record and (
                len(self._records) >= MAX_RECORDS or self._member_count + len(params) > MAX_MEMBERS
            ):
                raise ValueError("group record limit")
            record = (
                dict(self._records[key])
                if not new_record
                else {
                    "optimizer_id": identity[1],
                    "group_index": index,
                    "stage": stage,
                    "config_id": config_id,
                    "parameter_ids": parameter_ids,
                    "first_call": call,
                    "last_call": call,
                    "observations": 0,
                }
            )
            record["last_call"] = call
            record["observations"] += 1
            trial = self.snapshot()
            if new_config:
                trial["configurations"].append(config_record)
            trial["groups"] = [
                value for existing, value in self._records.items() if existing != key
            ] + [record]
            # New records/configs are byte-checked atomically. Unchanged rows
            # only grow bounded counters; reserve 4096 bytes for all such growth.
            if (new_config or new_record) and len(canonical(trial).encode()) > MAX_RAW_BYTES - 4096:
                raise ValueError("raw metadata byte limit")
            if new_config:
                self._configs[config_key] = config_record
            self._records[key] = record
            if new_record:
                self._member_count += len(params)
            if unknown_keys or any(value[0] == "unsupported" for value in present.values()):
                self.complete = False

    def snapshot(self):
        return {
            "protocol": "headroom.optimizer_group_options.v1",
            "complete": bool(sum(self.events.values())) and self.complete and not self.stopped,
            "stopped_at_limit_or_error": self.stopped,
            "events": dict(self.events),
            "configurations": list(self._configs.values()),
            "groups": list(self._records.values()),
        }
