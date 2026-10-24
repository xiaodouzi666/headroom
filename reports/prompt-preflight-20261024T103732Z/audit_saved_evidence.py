"""Reproduce audits from saved evidence, stopping the real client before SDK invocation."""

import copy
import hashlib
import json
import os
import socket
from pathlib import Path


def denied(*args, **kwargs):
    raise AssertionError("Independent CPU audit guard: no network or model execution")


socket.getaddrinfo = denied
socket.create_connection = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
original_env_getitem = type(os.environ).__getitem__


def guarded_env_getitem(self, name):
    if name in {"NEBIUS_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"}:
        raise AssertionError("Credentials must not be read")
    return original_env_getitem(self, name)


type(os.environ).__getitem__ = guarded_env_getitem
original_path_open = Path.open


def guarded_path_open(self, *args, **kwargs):
    if self.name.startswith(".env"):
        raise AssertionError("dotenv must not be read")
    return original_path_open(self, *args, **kwargs)


Path.open = guarded_path_open

import httpx

from headroom.diagnose import Diagnosis, build_diagnosis_messages
from headroom.evidence import _tokens
from headroom.llm.client import TokenFactoryClient
from headroom.llm.preflight import TOKENIZER_REVISION, PromptAuditor
from headroom.llm.router import LLMRouter

root = Path.cwd()
os.environ["TIKTOKEN_CACHE_DIR"] = str(root / ".cache/tiktoken")
out = Path(__file__).resolve().parent
source_path = root / "reports/t1.2-acceptance.json"
source = json.loads(source_path.read_text())
auditor = PromptAuditor(root / ".cache/tokenizers/nemotron-3-ultra" / TOKENIZER_REVISION)
records = {}


class CapturedBeforeSDK(Exception):
    pass


for scenario, artifacts in source["artifacts"].items():
    evidence_path = Path(artifacts["evidence_md"]["path"])
    evidence = evidence_path.read_bytes()
    assert hashlib.sha256(evidence).hexdigest() == artifacts["evidence_md"]["sha256"]
    evidence_json_path = Path(artifacts["evidence_json"]["path"])
    evidence_json = evidence_json_path.read_bytes()
    assert hashlib.sha256(evidence_json).hexdigest() == artifacts["evidence_json"]["sha256"]
    prior = json.loads(evidence_json)
    captured = []

    def before_attempt(role, spec, attempt, body, captured=captured):
        captured.append(body)
        raise CapturedBeforeSDK()

    with TokenFactoryClient(
        transport=httpx.MockTransport(denied), before_attempt=before_attempt
    ) as client:
        router = LLMRouter(client)
        messages = build_diagnosis_messages(
            evidence.decode(), goal="fit:22GB", policy={"allow_numerics_change": False}
        )
        try:
            router.chat("diagnose", messages, Diagnosis, max_tokens=4000)
        except CapturedBeforeSDK:
            pass
        assert len(client.ledger.entries) == 0
    assert len(captured) == 1
    body = captured[0]
    actual = auditor.audit(body)
    (out / (scenario + "-local-audit.json")).write_text(json.dumps(actual, indent=2) + "\n")
    hypothetical = copy.deepcopy(body)
    hypothetical["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": "headroom_response", "schema": Diagnosis.model_json_schema()},
    }
    extra = auditor.audit(hypothetical)
    assert actual["local_template"] == extra["local_template"]
    (out / (scenario + "-schema-domain-audit.json")).write_text(json.dumps(extra, indent=2) + "\n")
    evidence_tokens = _tokens(evidence.decode())
    assert evidence_tokens == prior["token_count"]
    records[scenario] = {
        "evidence_source": artifacts["evidence_md"],
        "evidence_json_source": artifacts["evidence_json"],
        "prior_evidence_tokenizer": prior["tokenizer"],
        "prior_evidence_only_cl100k_estimate": prior["token_count"],
        "recomputed_evidence_only_cl100k_estimate": evidence_tokens,
        "evidence_utf8_bytes": len(evidence),
        "full_request_pinned_local_template_tokens": actual["local_template"]["tokens"],
        "full_request_compact_json_local_estimate": actual["request"][
            "serialized_json_local_tokens_estimate"
        ],
        "full_request_compact_json_utf8_bytes": actual["request"]["compact_json_utf8_bytes"],
        "hypothetical_extra_response_schema_local_estimate": extra["extra_schema"][
            "serialized_json_local_tokens_estimate"
        ],
        "captured_output_cap": {"max_tokens": body["max_tokens"]},
        "local_report": scenario + "-local-audit.json",
        "hypothetical_schema_report": scenario + "-schema-domain-audit.json",
        "provider_billable_token_ceiling": None,
        "no_counts_added_together": True,
    }
summary = {
    "source_acceptance_path": str(source_path),
    "source_acceptance_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    "construction": "Existing diagnosis builder and real router/client before_attempt payload; stopped before SDK invocation; offline MockTransport tripwire.",
    "scenario_goal": "fit:22GB",
    "scenario_policy": {"allow_numerics_change": False},
    "current_request_format": "default text fallback; schema already in router system message",
    "hypothetical_response_schema": "Offline domain audit only; does not verify or enable provider JSON-schema capability.",
    "scenarios": records,
    "network_guard": "DNS/create_connection/socket.connect/socket.connect_ex refused process-wide",
    "credential_guard": "NEBIUS/TAVILY/OPENAI/HF token environment reads and dotenv Path.open refused",
    "cl100k_cache_sha256": hashlib.sha256(
        (root / ".cache/tiktoken/9b5ad71b2ce5302211f9c61530b329a4922fc6a4").read_bytes()
    ).hexdigest(),
    "model_api_requests": 0,
    "gpu_runs": 0,
    "paid_cost_usd": "0",
    "provider_tokenizer_match_verified": False,
    "provider_billable_token_ceiling": None,
    "live_authorized": False,
}
(out / "evidence-audits.json").write_text(json.dumps(summary, indent=2) + "\n")
print(
    json.dumps(
        {
            k: {
                f: v[f]
                for f in (
                    "prior_evidence_only_cl100k_estimate",
                    "full_request_pinned_local_template_tokens",
                    "full_request_compact_json_local_estimate",
                    "hypothetical_extra_response_schema_local_estimate",
                )
            }
            for k, v in records.items()
        },
        indent=2,
    )
)
