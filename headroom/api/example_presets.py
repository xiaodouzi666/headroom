"""Explicit product presets; separate from historical and benchmark inventories."""

EXAMPLE_PRESETS = {
    "s2_fp32_adamw_1b": {
        "source_sha256": "bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b",
        "recommended": {"target": "reclaim", "allocator_conf": None},
        "baseline_note": "Baseline already fits 22 GB; Reclaim asks for a further reduction.",
    },
    "s2_capacity_v2": {
        "source_sha256": "9565acfbcfc2f1eefd982c80be7ce943e09828578b9b44c3d70342bc82bf7f4c",
        "recommended": {"target": "fit:22GB", "allocator_conf": "expandable_segments:True"},
        "baseline_note": "Capacity baseline measured; this is not a verified model repair.",
    },
}

PRODUCT_EXAMPLES = (
    {
        "id": "s2_capacity_v2",
        "script": "scenarios/s2_capacity_v2/train.py",
        "title": "Capacity repair · 22 GB",
        "expected_mode": "fit",
        "root_cause": "Optimizer and activation memory",
        "gpu_baseline_verified": True,
    },
)
