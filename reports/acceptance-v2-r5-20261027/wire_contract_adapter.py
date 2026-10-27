"""Integration example only; root must freeze all real post-execution pins.

This adds prepared-wire mode evidence, not an independent financial/acceptance
audit. It does not establish server recognition, outcome benefit, or which
failure caused a fallback. Never pass receipt booleans as verifier results.
There is deliberately no CLI and no import-time dispatch.
"""

WIRE_SOURCE = "reports/acceptance-v2-r5-20261027/audit_reasoning_wire.py"
WIRE_SOURCE_SHA = "124696f14e5c92a796d275bcf1d8e8c69507e926ef2635feb70240b07e884e1b"


def audit_after_execution(
    driver,
    *,
    expected_review_sha256,
    preflight_path,
    expected_preflight_sha256,
    execution_path,
    expected_execution_sha256,
    campaign_path,
    expected_campaign_sha256,
):
    # All expected hashes come from the independent final audit's reviewed input
    # inventory. Computing fresh "expected" hashes here would defeat the binding.
    require = driver.require
    review_raw = driver._read_pinned(
        str(driver.REVIEW.relative_to(driver.ROOT)), expected_review_sha256
    )
    _profile, binding, finance, adapter, inventory = driver.active_profile_binding()
    review = finance.parse(review_raw)
    require(
        review["driver_sha256"] == driver.sha(driver.DRIVER)
        and review["cap_sha256"] == driver.sha(driver.CAP)
        and review["source_pins"] == driver.old.inventory()
        and review["manifest_sha256"] == driver.sha(driver.MANIFEST),
        "root review execution/source identities changed",
    )
    require(
        driver.old.verify_quality(review["quality_receipt"]["path"]) == review["quality_receipt"],
        "frozen full regression receipt changed",
    )
    cap, ids = driver.verify_cap()
    require(
        review["runtime_profile_binding"] == binding
        and cap["catalogue"]["runtime_profile_binding"] == binding
        and review["scenario_ids"] == ids,
        "review and cap must bind verified active capability chain",
    )
    preflight_raw = driver._read_pinned(preflight_path, expected_preflight_sha256)
    execution_raw = driver._read_pinned(execution_path, expected_execution_sha256)
    campaign_raw = driver._read_pinned(campaign_path, expected_campaign_sha256)
    preflight = finance.parse(preflight_raw)
    execution = finance.parse(execution_raw)
    campaign = finance.parse(campaign_raw)
    require(
        preflight["review_sha256"] == expected_review_sha256
        and preflight["base_funding_profile_sha256"] == driver.PROFILE_SHA
        and preflight["active_profile_path"] == driver.ACTIVE_PROFILE
        and preflight["active_profile_sha256"] == driver.ACTIVE_PROFILE_SHA
        and preflight["scenario_ids"] == ids
        and campaign["manifest_sha256"] == review["manifest_sha256"],
        "execution must bind the reviewed active profile and manifest",
    )
    argv = preflight["argv"]
    require(
        type(argv) is list and argv.count("--runtime-profile") == 1,
        "unique actual runtime profile option required",
    )
    require(
        argv[argv.index("--runtime-profile") + 1] == driver.ACTIVE_PROFILE,
        "actual runtime profile differs",
    )
    links = execution["campaigns"]
    require(
        type(links) is list
        and len(links) == 1
        and links[0]["path"] == campaign_path
        and links[0]["sha256"] == expected_campaign_sha256,
        "exact execution-to-campaign binding required",
    )
    # Replay the historical dispatch qualification from its frozen snapshot,
    # never against the now-increased post-campaign ledger.
    dispatch = finance.verify_r5_dispatch(
        driver._read_pinned(*driver.PROBE_ARTIFACT_PINS["after"]),
        cap,
        preflight,
        active_profile_path=driver.ACTIVE_PROFILE,
        active_profile_sha256=driver.ACTIVE_PROFILE_SHA,
    )
    require(dispatch["accepted"] is True, "reviewed dispatch finance failed")

    auditor = driver._load_pinned_module("r5_reasoning_wire_auditor", WIRE_SOURCE, WIRE_SOURCE_SHA)
    transition = binding["profile_transition"]
    # These booleans are emitted only after the actual verifiers above succeeded.
    root_validation = {
        "valid": True,
        "root_review_sha256": expected_review_sha256,
        "active_profile_sha256": driver.ACTIVE_PROFILE_SHA,
        "funding_chain_verified": binding["funding_chain_verified"],
        "capability_transition_verified": transition["valid"],
        "active_profile_runtime_verified": binding["active_profile_runtime_verified"],
        "transition_receipt_sha256": driver.PROFILE_TRANSITION_SHA,
        "low_effort_probe_receipt_sha256": driver.PROBE_ARTIFACT_PINS["probe_receipt"][1],
        "funding_transition_sha256": driver.FUNDING_SHA,
    }
    contract = auditor.bind_verified_contract(
        pins=auditor.ReasoningContractPins(
            active_profile_sha256=driver.ACTIVE_PROFILE_SHA,
            root_review_sha256=expected_review_sha256,
            transition_receipt_sha256=driver.PROFILE_TRANSITION_SHA,
            probe_receipt_sha256=driver.PROBE_ARTIFACT_PINS["probe_receipt"][1],
            funding_transition_sha256=driver.FUNDING_SHA,
        ),
        active_profile_raw=driver._read_pinned(driver.ACTIVE_PROFILE, driver.ACTIVE_PROFILE_SHA),
        probe_receipt_raw=driver._read_pinned(*driver.PROBE_ARTIFACT_PINS["probe_receipt"]),
        root_review_validation=root_validation,
        transition_validation=transition,
    )
    result = auditor.audit(
        driver.ROOT / execution_path, driver.ROOT / campaign_path, contract=contract
    )
    adapter.verify_inputs_still_pinned(inventory)
    driver._read_pinned(preflight_path, expected_preflight_sha256)
    driver._read_pinned(execution_path, expected_execution_sha256)
    driver._read_pinned(campaign_path, expected_campaign_sha256)
    return result
