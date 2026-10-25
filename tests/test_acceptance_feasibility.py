import copy
import json
import subprocess
import sys

import pytest

from headroom.acceptance.feasibility import audit_fixed_state_capacity


def audit(**overrides):
    inputs = {
        "optimizer_state_bytes": 8_593_604_608,
        "minimum_state_fraction": "0.4",
        "fit_limit_bytes": 22_000_000_000,
        "observed_peak_bytes": 21_553_250_816,
    }
    inputs.update(overrides)
    return audit_fixed_state_capacity(**inputs)


def test_historical_s2_conflict_is_explained_without_passing_failed_gate():
    result = audit()
    assert result["derivation"]["largest_integer_peak_bytes"] == 21_484_011_520
    assert result["compatibility"]["status"] == "incompatible"
    assert result["observed"]["state_share_requirement_met"] is False
    assert result["observed"]["baseline_already_fits"] is True
    assert result["acceptance_certified"] is False
    assert result["historical_results_modified"] is False


def test_equal_upper_bound_cannot_begin_above_capacity_target():
    result = audit(
        optimizer_state_bytes=40,
        fit_limit_bytes=100,
        observed_peak_bytes=100,
    )
    assert result["compatibility"]["status"] == "incompatible"
    assert result["observed"]["state_share_requirement_met"] is True


def test_fractional_byte_window_contains_no_valid_baseline_peak():
    result = audit(
        optimizer_state_bytes=10,
        minimum_state_fraction="0.99",
        fit_limit_bytes=10,
        observed_peak_bytes=None,
    )
    assert result["derivation"]["exact_peak_upper_bound_bytes"] == {
        "numerator": 1000,
        "denominator": 99,
    }
    assert result["derivation"]["largest_integer_peak_bytes"] == 10
    assert result["compatibility"]["status"] == "incompatible"


def test_integer_window_is_not_a_claim_of_workload_or_repair_success():
    result = audit(
        optimizer_state_bytes=41,
        fit_limit_bytes=100,
        observed_peak_bytes=None,
    )
    assert result["compatibility"]["status"] == "not_ruled_out"
    assert result["derivation"]["largest_integer_peak_bytes"] == 102
    assert result["observed"]["state_share_requirement_met"] is None
    assert result["acceptance_certified"] is False


@pytest.mark.parametrize("missing", ["optimizer_state_bytes", "fit_limit_bytes"])
def test_missing_input_remains_unknown(missing):
    result = audit(**{missing: None})
    assert result["compatibility"]["status"] == "unknown"
    assert missing in result["compatibility"]["reason"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"optimizer_state_bytes": True},
        {"optimizer_state_bytes": -1},
        {"optimizer_state_bytes": 1.5},
        {"fit_limit_bytes": 0},
        {"fit_limit_bytes": False},
        {"observed_peak_bytes": 0},
        {"observed_peak_bytes": -2},
        {"observed_peak_bytes": 1},
        {"minimum_state_fraction": 0.4},
        {"minimum_state_fraction": "0"},
        {"minimum_state_fraction": "1.001"},
        {"minimum_state_fraction": "NaN"},
        {"minimum_state_fraction": "Infinity"},
        {"minimum_state_fraction": "1/0"},
    ],
)
def test_invalid_or_inconsistent_inputs_are_rejected(overrides):
    with pytest.raises((TypeError, ValueError)):
        audit(**overrides)


def test_rational_input_is_exact_and_caller_values_do_not_change():
    inputs = {
        "optimizer_state_bytes": 8_593_604_608,
        "minimum_state_fraction": "2/5",
        "fit_limit_bytes": 22_000_000_000,
        "observed_peak_bytes": 21_553_250_816,
    }
    before = copy.deepcopy(inputs)
    result = audit_fixed_state_capacity(**inputs)
    assert inputs == before
    assert result == audit()
    json.dumps(result, allow_nan=False)


def test_cli_requires_no_runtime_profile_and_produces_json():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "headroom.acceptance.feasibility",
            "--optimizer-state-bytes",
            "8593604608",
            "--minimum-state-fraction",
            "0.4",
            "--fit-limit-bytes",
            "22000000000",
            "--observed-peak-bytes",
            "21553250816",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout) == audit()
    assert completed.stderr == ""
