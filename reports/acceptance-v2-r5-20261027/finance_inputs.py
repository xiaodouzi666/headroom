"""Read-only adapter for fixed R4 artifacts and externally pinned R5 probe files.

No SQLite, API, GPU, credential/environment or write operations. Runtime callers
must pin both this module and finance_chain.py in their reviewed source manifest.
"""

from dataclasses import dataclass

import finance_chain as finance

R4_DIRECTORY = "reports/acceptance-v2-r4-20261027/"
R4_PATHS = {
    "audit": R4_DIRECTORY + "independent-audit-history-v2-final.json",
    "execution": R4_DIRECTORY + "execution.json",
    "campaign": "runs/evaluation/live/20261027T002717226380Z-119f2528/campaign.json",
    "cap": R4_DIRECTORY + "cap-review.json",
    "preflight": R4_DIRECTORY + "preflight.json",
}


@dataclass(frozen=True)
class ArtifactPin:
    path: str
    sha256: str


def read_pin(pin, records):
    """Reuse the reviewed no-follow, bounded file reader; never trust a fresh hash."""
    finance.need(isinstance(pin, ArtifactPin), "artifact_pin_type")
    finance.need(
        type(pin.sha256) is str and finance.SHA.fullmatch(pin.sha256) is not None,
        "external_frozen_pin_required",
    )
    raw = finance.R4.restricted_funding_bytes(pin.path, {pin.path}, records)
    finance.need(finance.digest(raw) == pin.sha256, "external_artifact_pin")
    return raw


def load_r4_root_inputs(r4_after_pin):
    """Return real R4 verifier inputs plus an exact file-hash inventory, no DB read."""
    records = {}
    r4_raw = {
        name: read_pin(ArtifactPin(path, finance.R4_FIXED_PINS[name]), records)
        for name, path in R4_PATHS.items()
    }
    r4_documents = {name: finance.parse(raw) for name, raw in r4_raw.items()}
    legacy_documents, legacy_hashes = {}, {}
    for name, (path, expected) in finance.R4.HISTORY_PINS.items():
        raw = read_pin(ArtifactPin(path, expected), records)
        legacy_documents[name] = finance.parse(raw)
        legacy_hashes[path] = expected
    source_bytes = {}
    for pin in finance.R4.FUNDING_PINS:
        source_bytes[pin["path"]] = read_pin(ArtifactPin(pin["path"], pin["sha256"]), records)
    funding, retirement, allocation, profile = (
        finance.parse(source_bytes[path])
        for path in (
            finance.R4.FUNDING_PATH,
            finance.R4.RETIREMENT_PATH,
            finance.R4.ALLOCATION_PATH,
            finance.R4.PROFILE,
        )
    )
    for entry in retirement["entrypoints"]:
        read_pin(ArtifactPin(entry["path"], entry["closed_sha256"]), records)
        if "archived_path" in entry:
            read_pin(ArtifactPin(entry["archived_path"], entry["original_sha256"]), records)
    review = finance.parse(
        read_pin(
            ArtifactPin(
                R4_DIRECTORY + "root-review.json", r4_documents["preflight"]["review_sha256"]
            ),
            records,
        )
    )
    driver_raw = read_pin(
        ArtifactPin(R4_DIRECTORY + "run_mvp_v2.py", review["driver_sha256"]),
        records,
    )
    driver = finance.R4.driver_funding_pins(driver_raw.decode("utf-8"))
    after = read_pin(r4_after_pin, records)
    return {
        "legacy_documents": legacy_documents,
        "legacy_hashes": legacy_hashes,
        "funding_args": [
            funding,
            retirement,
            allocation,
            profile,
            r4_documents["cap"],
            driver,
            dict(records),
        ],
        "r4_documents": r4_documents,
        "r4_raw": r4_raw,
        "r4_after": after,
    }, records


def verify_probe_authorization(
    authorization_artifact_pins, *, expected_request_sha256, ledger_before_sha256
):
    """Bind the request to independent prepared + reviewed root-freeze artifacts."""
    finance.need(
        type(expected_request_sha256) is str
        and finance.SHA.fullmatch(expected_request_sha256) is not None,
        "frozen_expected_request_required",
    )
    finance.need(
        type(authorization_artifact_pins) is dict
        and set(authorization_artifact_pins) == {"prepared", "freeze"},
        "independent_authorization_artifacts",
    )
    records = {}
    prepared_pin = authorization_artifact_pins["prepared"]
    prepared = finance.parse(read_pin(prepared_pin, records))
    freeze = finance.parse(read_pin(authorization_artifact_pins["freeze"], records))
    finance.need(
        prepared["scope"] == freeze["scope"] == "super_low_effort_schema_code_probe_v1"
        and freeze["reviewed"] is True
        and freeze["r4_terminal"] is True
        and freeze["reviewer"] == "root"
        and type(freeze["source_revision"]) is str
        and finance.re.fullmatch(r"[0-9a-f]{40}", freeze["source_revision"]) is not None
        and freeze["prepared_sha256"] == prepared_pin.sha256
        and prepared["profile_sha256"] == freeze["profile_sha256"] == finance.BASE_PROFILE_SHA
        and prepared["profile_path"] == str(finance.ROOT / finance.R4.PROFILE)
        and prepared["request_sha256"] == freeze["request_sha256"] == expected_request_sha256
        and freeze["ledger_before_sha256"] == ledger_before_sha256,
        "root_freeze_identity",
    )
    finance.need(
        finance.R4.money(prepared["run_limit_usd"])
        == finance.R4.money(freeze["run_limit_usd"])
        == finance.PROBE_MAX_NET_USD
        and finance.R4.money(prepared["daily_limit_usd"])
        == finance.R4.money(freeze["daily_limit_usd"])
        == finance.DAILY
        and 0 < finance.R4.money(prepared["reservation_upper_usd"]) <= finance.PROBE_MAX_NET_USD
        and type(prepared["max_completion_tokens"]) is int
        and prepared["max_completion_tokens"] == 4000
        and type(prepared["sdk_retries"]) is int
        and prepared["sdk_retries"] == 0
        and type(prepared["client_retries"]) is int
        and prepared["client_retries"] == 0
        and type(prepared["maximum_dispatches"]) is int
        and prepared["maximum_dispatches"] == 1
        and prepared["promote_profile"] is False,
        "frozen_single_probe_limits",
    )
    # Binding the reviewed regression artifact is not a substitute for the
    # driver's separate original quality/source gate.
    read_pin(
        ArtifactPin(
            freeze["full_regression_receipt_path"], freeze["full_regression_receipt_sha256"]
        ),
        records,
    )
    return expected_request_sha256, records


def load_probe_inputs(pins, *, expected_request_sha256):
    """Load only the five explicit probe artifacts and unchanged original profile."""
    finance.need(
        type(pins) is dict
        and set(pins)
        == {
            "before",
            "after",
            "calls",
            "probe_receipt",
            "request_payload",
        },
        "complete_probe_artifact_pins",
    )
    records = {}
    raw = {name: read_pin(pin, records) for name, pin in pins.items()}
    profile = read_pin(ArtifactPin(finance.R4.PROFILE, finance.BASE_PROFILE_SHA), records)
    return {
        "before": raw["before"],
        "after": raw["after"],
        "calls": raw["calls"],
        "probe_receipt": raw["probe_receipt"],
        "request_payload_raw": raw["request_payload"],
        "before_sha256": pins["before"].sha256,
        "after_sha256": pins["after"].sha256,
        "probe_receipt_sha256": pins["probe_receipt"].sha256,
        "base_profile_sha256": finance.BASE_PROFILE_SHA,
        "base_profile_raw": profile,
        "expected_request_sha256": expected_request_sha256,
    }, records


def verify_frozen_root_and_probe(
    *,
    r4_after_pin,
    probe_artifact_pins,
    dynamic_pins,
    authorization_artifact_pins,
    expected_request_sha256,
):
    """Compose actual files into a sealed proof. PENDING refuses before file reads."""
    finance.require_frozen_pins(dynamic_pins, stage="probe")
    _, authorization_records = verify_probe_authorization(
        authorization_artifact_pins,
        expected_request_sha256=expected_request_sha256,
        ledger_before_sha256=dynamic_pins["probe_before"],
    )
    r4_inputs, r4_records = load_r4_root_inputs(r4_after_pin)
    probe_inputs, probe_records = load_probe_inputs(
        probe_artifact_pins,
        expected_request_sha256=expected_request_sha256,
    )
    report = finance.parse(probe_inputs["probe_receipt"])
    finance.need(
        report.get("freeze_sha256") == authorization_artifact_pins["freeze"].sha256,
        "capability_report_frozen_authorization",
    )
    records = dict(r4_records)
    for extra in (probe_records, authorization_records):
        finance.need(
            all(records.get(k, v) == v for k, v in extra.items()),
            "stable_shared_artifact_identity",
        )
        records.update(extra)
    proof = finance.verify_root_and_probe(
        r4_inputs=r4_inputs,
        probe_inputs=probe_inputs,
        pins=dynamic_pins,
    )
    return proof, records


def verify_inputs_still_pinned(records):
    """Re-read before dispatch and at audit end; no changed history is tolerated."""
    current = {}
    for path, expected in records.items():
        read_pin(ArtifactPin(path, expected), current)
    return True
