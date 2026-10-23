from decimal import Decimal

import pytest

from headroom.llm.cost import Pricing, Usage, calculate_cost


def price(**kwargs):
    return Pricing("1.23456789", "3.87654321", verified=True, source="offline price", **kwargs)


def test_decimal_exactness_and_reasoning_not_counted_twice():
    usage = Usage.from_payload(
        {
            "prompt_tokens": 1234567,
            "completion_tokens": 98765,
            "total_tokens": 1333332,
            "completion_tokens_details": {"reasoning_tokens": 87654},
        }
    )
    expected = (
        Decimal(1234567) * Decimal("1.23456789") + Decimal(98765) * Decimal("3.87654321")
    ) / Decimal(1_000_000)
    assert calculate_cost(usage, price()).usd == expected


def test_cached_tokens_are_a_subset_and_use_separate_verified_rate():
    usage = Usage(100, 20, 120, cached_tokens=80)
    pricing = Pricing("1", "3", "0.1", verified=True, source="offline")
    assert calculate_cost(usage, pricing).usd == Decimal("0.000088")
    assert calculate_cost(usage, price()).reason == "missing_cached_input_price"
    assert calculate_cost(Usage(100, 20, 120), pricing).reason == "missing_cached_token_usage"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"prompt_tokens": 1, "completion_tokens": None},
        {"prompt_tokens": True, "completion_tokens": 1},
        {"prompt_tokens": 1.5, "completion_tokens": 1},
        {"prompt_tokens": -1, "completion_tokens": 1},
        {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 99},
        {
            "prompt_tokens": 10,
            "completion_tokens": 1,
            "prompt_tokens_details": {"cached_tokens": 11},
        },
    ],
)
def test_invalid_usage_stays_unknown(payload):
    usage = Usage.from_payload(payload)
    assert usage is None
    assert calculate_cost(usage, price()).usd is None


def test_unverified_prices_are_not_reported_as_actual_cost():
    cost = calculate_cost(Usage(100, 20, 120), Pricing("1", "3"))
    assert cost.status == "unknown"
    assert cost.usd is None


@pytest.mark.parametrize("invalid", [0.1, -1, "NaN", "Infinity", True])
def test_price_rejects_invalid_or_imprecise_input(invalid):
    with pytest.raises((ValueError, TypeError)):
        Pricing(invalid, "1")
