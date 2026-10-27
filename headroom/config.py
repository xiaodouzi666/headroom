"""Reviewed probe constants and disabled-by-default candidate runtime settings."""

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
# Exact identity observed in the 2026-10-24 catalogue and minimal Nano response.
# Selecting this ID does not enable live use or certify the full capability suite.
NANO_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
LIGHTNING_MODEL = "nvidia/Nemotron-3_5-Lightning"
# T0.4 observed server prompt tokens in the largest successful prescribed sample.
# This is a tested lower bound, not the exact provider context maximum;900k hit429.
# Evidence: reports/live-campaign-20261025/ultra-long-500000/report.json.
ULTRA_MAX_INPUT_TOKENS = 500029
EVIDENCE_TOKEN_BUDGET = min(150000, (3 * ULTRA_MAX_INPUT_TOKENS) // 5)
REASONING_METHOD = "chat_template_kwargs"
JSON_METHOD = "json_schema"

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
    # Evidence certifies this exact request combination completed in one sample.
    # It does not certify server recognition, a token budget, or quality gains.
    low_effort_method: str | None = None
    low_effort_evidence: str | None = None
    low_effort_evidence_sha256: str | None = None
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
        if self.low_effort_method not in {None, "chat_template_kwargs"}:
            raise ValueError("Unsupported low-effort request method")
        if self.low_effort_method is None:
            if self.low_effort_evidence is not None or self.low_effort_evidence_sha256 is not None:
                raise ValueError("Low-effort evidence requires its request method")
        else:
            if self.reasoning_method != "chat_template_kwargs" or self.json_method != "json_schema":
                raise ValueError(
                    "Low-effort requires the tested thinking and JSON-schema combination"
                )
            if (
                type(self.low_effort_evidence) is not str
                or not self.low_effort_evidence.strip()
                or len(self.low_effort_evidence) > 2048
            ):
                raise ValueError("Low-effort requires independent saved probe evidence")
            digest = self.low_effort_evidence_sha256
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("Low-effort evidence requires an exact SHA256")
        configured = (
            self.json_method != "text"
            or self.reasoning_method is not None
            or self.token_budget_method is not None
            or self.low_effort_method is not None
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
    output_cap_field: str = "max_tokens"

    def __post_init__(self):
        if not self.model_id.startswith("nvidia/") or any(c.isspace() for c in self.model_id):
            raise ValueError("Model ID must be a nonempty nvidia/ model identifier")
        if self.capabilities.low_effort_method is not None and self.model_id != SUPER_MODEL:
            raise ValueError("The reviewed low-effort request combination is specific to Super")
        if not 0 < self.timeout_seconds <= 600:
            raise ValueError("Model timeout must be positive and at most 600 seconds")
        if self.model_verified and not self.evidence:
            raise ValueError("A verified model requires saved catalogue/probe evidence")
        if self.output_cap_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("Unsupported output cap field")
        if self.output_cap_field != "max_tokens" and not self.evidence:
            raise ValueError("A nondefault output cap field requires saved probe evidence")


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
