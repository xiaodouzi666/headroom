"""Prepare only: documented prices and three real probe CLI dry-runs."""

import builtins
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import runpy
import socket
from decimal import Decimal
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/promo-checkpoint-preparation-20261024"
CATALOGUE = ROOT / "reports/tokenfactory-catalogue-promo-20261024T145241Z/report.json"
CHAT_DOC = "https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion"
PRICE_DOC = "https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference"
BILLING_DOC = "https://docs.tokenfactory.nebius.com/other-capabilities/billing"
ENDPOINT = "https://api.tokenfactory.us-central1.nebius.com/v1/"
MODELS = {
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "super": "nvidia/nemotron-3-super-120b-a12b",
}
ATTEMPTS = []
original_open, original_io_open, original_os_open = builtins.open, io.open, os.open
original_getenv = os.getenv
original_getitem = type(os.environ).__getitem__
original_socket = socket.socket


def check_path(path):
    if isinstance(path, (str, bytes, os.PathLike)):
        resolved = Path(os.fsdecode(path)).resolve()
        if resolved == ROOT / ".env":
            ATTEMPTS.append("real_env_read")
            raise PermissionError("Real project .env is forbidden")


def guarded_open(path, *args, **kwargs):
    check_path(path)
    return original_open(path, *args, **kwargs)


def guarded_io_open(path, *args, **kwargs):
    check_path(path)
    return original_io_open(path, *args, **kwargs)


def guarded_os_open(path, *args, **kwargs):
    check_path(path)
    return original_os_open(path, *args, **kwargs)


def guarded_getitem(self, name):
    if name in {"NEBIUS_API_KEY", "TAVILY_API_KEY"}:
        ATTEMPTS.append("credential_environment_read")
        raise PermissionError("Credential environment read is forbidden")
    return original_getitem(self, name)


def refuse_network(*args, **kwargs):
    ATTEMPTS.append("network")
    raise PermissionError("Network forbidden during preparation")


class GuardedSocket(original_socket):
    def connect(self, *args, **kwargs):
        if self.family in {socket.AF_INET, socket.AF_INET6}:
            return refuse_network()
        return super().connect(*args, **kwargs)

    def connect_ex(self, *args, **kwargs):
        if self.family in {socket.AF_INET, socket.AF_INET6}:
            return refuse_network()
        return super().connect_ex(*args, **kwargs)


builtins.open, io.open, os.open = guarded_open, guarded_io_open, guarded_os_open
type(os.environ).__getitem__ = guarded_getitem
socket.socket = GuardedSocket
socket.getaddrinfo = refuse_network
socket.create_connection = refuse_network


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    path = OUT / name
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


now = dt.datetime.now(dt.UTC).isoformat()
source_hash = digest(ROOT / "scripts/probe_models.py")
plan_hash = digest(ROOT / "docs/PLAN.md")
catalogue_hash = digest(CATALOGUE)
catalogue = json.loads(CATALOGUE.read_text())
assert catalogue["mode"] == "catalogue_only"
assert catalogue["inference_requests"] == 0
assert len(catalogue["catalogues"]) == 2
assert all(row["http_status"] == 200 for row in catalogue["catalogues"])
us = next(row for row in catalogue["catalogues"] if row["endpoint"] == ENDPOINT)
advertised = {row["id"]: row["advertised_metadata"] for row in us["models"]}
reviewed = {}
for role, model in MODELS.items():
    data = advertised[model]
    price = data["pricing"]
    assert all(
        Decimal(price[key]) == 0
        for key in ("request", "image", "price_per_video_second", "price_per_minute")
    )
    assert Decimal(price["input_cache_read"]) <= Decimal(price["prompt"])
    assert type(data["context_length"]) is int and data["context_length"] > 0
    reviewed[model] = {
        "input_usd_per_million": str(Decimal(price["prompt"]) * 1000000),
        "output_usd_per_million": str(Decimal(price["completion"]) * 1000000),
        "prompt_token_ceiling": data["context_length"],
        "output_cap_field": "max_completion_tokens",
        "input_ceiling_basis": "Full advertised context; conservative documented context bound, not local tokenizer estimate",
        "output_cap_evidence": CHAT_DOC,
        "cached_input_usd_per_million": str(Decimal(price["input_cache_read"]) * 1000000),
        "fee_components_per_request": {
            key: price[key]
            for key in ("request", "image", "price_per_video_second", "price_per_minute")
        },
        "live_capability_accepted": False,
    }
pricing = {
    "verified": True,
    "verified_at": now,
    "source": str(CATALOGUE.relative_to(ROOT)) + "; " + CHAT_DOC + "; " + PRICE_DOC,
    "output_caps_include_reasoning": True,
    "models": reviewed,
    "review_scope": "Documented conservative token bounds and fresh advertised pricing for three explicit text probes only; no spending authorization",
    "endpoint": ENDPOINT,
    "catalogue_sha256": catalogue_hash,
    "authorization_granted": False,
    "tax_included_in_token_prices": False,
    "limitations": [
        "Documented provider contract is not empirical Ultra capability verification.",
        "No claim that advertised context is the account's currently usable long-input limit.",
        "Ordinary input price conservatively covers lower cached-input price; script cost is not a reconciled invoice.",
        "Any unknown usage/model identity, provider bound violation, failed capability or rate/account limit stops all later requests.",
        "No runtime profile, repair, Tavily, long-input, concurrency or automatic retry is authorized.",
    ],
}
write("pricing-reviewed.json", pricing)
write(
    "official-review.json",
    {
        "reviewed_at": now,
        "catalogue": {
            "path": str(CATALOGUE.relative_to(ROOT)),
            "sha256": catalogue_hash,
            "observed_at": catalogue["timestamp_utc"],
        },
        "sources": [
            {
                "url": CHAT_DOC,
                "checked_by": "child public documentation read",
                "facts": [
                    "max_completion_tokens bounds generated completion tokens, including visible output and reasoning.",
                    "The max_tokens field documentation says prompt token count plus requested maximum output cannot exceed model context.",
                ],
                "inference": "Using the entire advertised context as input reservation is conservative under the documented context constraint; it is not a measured prompt count.",
            },
            {
                "url": PRICE_DOC,
                "checked_by": "root public source review reported in task",
                "facts": [
                    "Root reported ordinary Ultra/Super prices match fresh authenticated catalogue."
                ],
            },
            {
                "url": BILLING_DOC,
                "checked_by": "root public source review reported in task",
                "facts": [
                    "Root reported Netherlands 21 percent tax; account transaction reconciliation remains separate."
                ],
            },
        ],
        "unsupported_claims": [
            "Ultra successful inference",
            "Super native schema/tools passed",
            "Invoice reconciled",
            "Spending approved",
        ],
    },
)
probe = runpy.run_path(str(ROOT / "scripts/probe_models.py"), run_name="checkpoint_probe_readonly")
prices = probe["validate_prices"](pricing, set(MODELS), MODELS)
cases = [
    ("ultra-chat", "ultra", "chat", 1024, "1.051648"),
    ("super-schema", "super", "json_schema", 256, "0.0788736"),
    ("super-tools", "super", "tools", 256, "0.0788736"),
]
prepared = []
for name, role, method, limit, cap in cases:
    argv = [
        "--suite",
        "capabilities",
        "--roles",
        role,
        "--capability-method",
        method,
        "--base-url",
        ENDPOINT,
        "--model-id",
        role + "=" + MODELS[role],
        "--max-completion-tokens",
        str(limit),
        "--max-retries",
        "0",
        "--budget-usd",
        cap,
        "--pricing-file",
        str(OUT / "pricing-reviewed.json"),
    ]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = probe["main"](argv)
    plan = json.loads(buffer.getvalue())
    assert code == 0 and plan["network_requests"] == 0 and plan["live"] is False
    assert plan["accepted"] is False
    paid = [row for row in plan["plan"] if row["role"] is not None]
    assert len(plan["plan"]) == 3 and len(paid) == 1
    assert paid[0]["role"] == role and paid[0]["method"] == method
    assert paid[0]["concurrency_group"] is None
    spec = probe["Probe"](**{key: value for key, value in paid[0].items() if key != "model"})
    payload, metadata = probe["make_payload"](spec, prices[role], limit)
    upper = prices[role].cost(prices[role].prompt_token_ceiling, limit)
    assert upper == Decimal(cap)
    assert payload["max_completion_tokens"] == limit
    assert "max_tokens" not in payload
    write(name + ".plan.json", plan)
    write(
        name + ".request-audit.json",
        {
            "status": "ready_for_review",
            "execute": False,
            "live_authorized": False,
            "cli_argv": argv,
            "payload": payload,
            "metadata": metadata,
            "token_reservation_usd": str(upper),
            "max_inference_requests": 1,
            "catalogue_get_requests_per_execution": 2,
            "max_retries": 0,
        },
    )
    prepared.append(
        {
            "case": name,
            "status": "ready",
            "token_reservation_usd": str(upper),
            "plan": name + ".plan.json",
        }
    )
total = sum((Decimal(row["token_reservation_usd"]) for row in prepared), Decimal(0))
assert total == Decimal("1.2093952")
assert total <= Decimal("1.25")
assert Decimal("1.25") * Decimal("1.21") <= Decimal(2)
assert digest(ROOT / "scripts/probe_models.py") == source_hash
assert digest(ROOT / "docs/PLAN.md") == plan_hash
assert digest(CATALOGUE) == catalogue_hash
assert not ATTEMPTS
assert not (ROOT / ".cache/tokenfactory-runtime.json").exists()
receipt = {
    "prepared_at": now,
    "preparation_status": "ready",
    "live_execution_status": "refused",
    "live_execution_reasons": [
        "new_checkpoint_spending_authorization_not_granted",
        "refresh_account_and_review_prior_result_before_each_dispatch",
    ],
    "api_requests": 0,
    "inference_requests": 0,
    "tavily_requests": 0,
    "gpu_runs": 0,
    "credential_reads": 0,
    "guard_attempts": ATTEMPTS,
    "guard_scope": "Independent DNS/INET and actual project .env/credential environment guard installed before probe module import; actual main dry-run and actual validate_prices/make_payload executed.",
    "cases": prepared,
    "reserved_token_total_usd": str(total),
    "authorized_token_cap_usd": None,
    "proposed_token_cap_usd": "1.25",
    "proposed_gross_envelope_usd": "2",
    "reported_tax_rate": "0.21",
    "reservation_plus_reported_tax_usd": str(total * Decimal("1.21")),
    "token_cap_plus_reported_tax_usd": str(Decimal("1.25") * Decimal("1.21")),
    "account_credit": "Refresh before authorized execution; no account credentials or balance read by this preparation",
    "runtime_profile_absent": True,
    "source_sha256": {
        "scripts/probe_models.py": source_hash,
        "docs/PLAN.md": plan_hash,
        str(CATALOGUE.relative_to(ROOT)): catalogue_hash,
    },
    "files": {p.name: digest(p) for p in sorted(OUT.iterdir()) if p.is_file()},
}
write("receipt.json", receipt)
print(
    json.dumps(
        {
            "preparation_status": receipt["preparation_status"],
            "live_execution_status": receipt["live_execution_status"],
            "cases": prepared,
            "reserved_token_total_usd": str(total),
            "guard_attempts": ATTEMPTS,
        },
        indent=2,
    )
)
