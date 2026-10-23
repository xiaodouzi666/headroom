"""Candidate plan settings. Defaults are not Token Factory probe results."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from headroom.llm.cost import Pricing

OFFICIAL_BASE_URLS = (
    "https://api.tokenfactory.us-central1.nebius.com/v1/",
    "https://api.tokenfactory.nebius.com/v1/",
)
ULTRA_MODEL = "nvidia/Nemotron-3-Ultra-550b-a55b"
SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NANO_MODEL = "nvidia/nvidia-nemotron-3-nano-30b-a3b"
LIGHTNING_MODEL = "nvidia/Nemotron-3_5-Lightning"
ULTRA_MAX_INPUT_TOKENS = None
EVIDENCE_TOKEN_BUDGET = None  # T0.4 must determine min(150000, floor(0.6 * measured maximum)).
REASONING_METHOD = None
JSON_METHOD = None

ROLE_MODELS = MappingProxyType(
    {
        "ultra": "ultra",
        "diagnose": "ultra",
        "diagnostician": "ultra",
        "planner": "ultra",
        "super": "super",
        "patch": "super",
        "patcher": "super",
        "verifier": "super",
        "nano": "nano",
        "annotate": "nano",
        "annotator": "nano",
        "summarize": "nano",
        "summarizer": "nano",
    }
)


def normalize_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Token Factory base URL must be a string")
    candidate = value if value.endswith("/") else value + "/"
    if candidate not in OFFICIAL_BASE_URLS:
        raise ValueError("Only the two official Token Factory HTTPS endpoints are allowed")
    return candidate


@dataclass(frozen=True)
class VerifiedCapabilities:
    """Only populate nondefault methods from saved successful probe evidence."""

    json_method: str = "text"
    reasoning_method: str | None = None
    token_budget_method: str | None = None
    tools: bool = False
    reasoning_on: str | None = None
    reasoning_off: str | None = None
    evidence: str | None = None

    def __post_init__(self):
        if self.json_method not in {"text", "json_object", "json_schema"}:
            raise ValueError("Unsupported JSON method")
        if self.reasoning_method not in {
            None,
            "chat_template_kwargs",
            "system_prefix",
            "reasoning_effort",
        }:
            raise ValueError("Unsupported reasoning method")
        if self.token_budget_method not in {None, "reasoning_budget", "max_thinking_tokens"}:
            raise ValueError("Unsupported token-budget method")
        configured = (
            self.json_method != "text"
            or self.reasoning_method is not None
            or self.token_budget_method is not None
            or self.tools
        )
        if configured and not self.evidence:
            raise ValueError("Nondefault capability methods require saved probe evidence")
        if self.reasoning_method == "reasoning_effort" and not (
            self.reasoning_on and self.reasoning_off
        ):
            raise ValueError("reasoning_effort requires tested on and off values")


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    timeout_seconds: float
    capabilities: VerifiedCapabilities = field(default_factory=VerifiedCapabilities)
    pricing: Pricing | None = None
    model_verified: bool = False
    evidence: str | None = None

    def __post_init__(self):
        if not self.model_id.startswith("nvidia/") or any(c.isspace() for c in self.model_id):
            raise ValueError("Model ID must be a nonempty nvidia/ model identifier")
        if not 0 < self.timeout_seconds <= 600:
            raise ValueError("Model timeout must be positive and at most 600 seconds")
        if self.model_verified and not self.evidence:
            raise ValueError("A verified model requires saved catalogue/probe evidence")


def candidate_models():
    return {
        "ultra": ModelSpec(ULTRA_MODEL, 600),
        "super": ModelSpec(SUPER_MODEL, 120),
        "nano": ModelSpec(NANO_MODEL, 120),
    }


@dataclass(frozen=True)
class RuntimeConfig:
    base_url: str = OFFICIAL_BASE_URLS[0]
    live_enabled: bool = False
    models: Mapping[str, ModelSpec] = field(default_factory=candidate_models)

    def __post_init__(self):
        object.__setattr__(self, "base_url", normalize_base_url(self.base_url))
        if set(self.models) != {"ultra", "super", "nano"}:
            raise ValueError("Models must provide ultra, super and nano roles")
        if not all(isinstance(spec, ModelSpec) for spec in self.models.values()):
            raise ValueError("Each model entry must be a ModelSpec")
        object.__setattr__(self, "models", MappingProxyType(dict(self.models)))

    def model_for(self, role: str) -> ModelSpec:
        if role not in ROLE_MODELS:
            raise ValueError("Unknown LLM role")
        return self.models[ROLE_MODELS[role]]
