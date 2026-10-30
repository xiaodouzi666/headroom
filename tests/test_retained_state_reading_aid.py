"""Actual search-state transitions must not apply reverted or superseded diffs."""

import json

import pytest
from test_orchestrator import search_run

from headroom.retained_state import retained_state_reading_aid


def test_two_historical_keeps_do_not_make_both_current():
    context = {"selected_round": 2}
    history = [
        {"round": 1, "decision": "keep", "candidate_selected": True},
        {"round": 2, "decision": "keep", "candidate_selected": True},
        {"round": 3, "decision": "revert", "candidate_selected": False},
    ]
    aid = retained_state_reading_aid(context, history)
    assert aid["current_source_basis"] == "retained_candidate"
    assert aid["current_retained_round"] == 2
    assert [row["is_current_retained_round"] for row in aid["prior_candidates"]] == [
        False,
        True,
        False,
    ]
    assert history[0]["candidate_selected"] is True


def test_reverted_candidate_does_not_replace_baseline():
    aid = retained_state_reading_aid(
        {"selected_round": None},
        [
            {
                "round": 2,
                "decision": "revert",
                "candidate_selected": False,
                "selected_after_round": None,
                "diff": "UNTRUSTED_CANDIDATE_BYTES",
            },
        ],
    )
    assert aid["current_source_basis"] == "original_baseline"
    assert aid["prior_candidates"][0]["is_current_retained_round"] is False
    assert "UNTRUSTED_CANDIDATE_BYTES" not in json.dumps(aid)


@pytest.mark.parametrize(
    "context", [None, {}, {"selected_round": True}, {"selected_round": 0}, {"selected_round": 7}]
)
def test_missing_or_malformed_current_selection_cannot_be_rebuilt_from_history(context):
    aid = retained_state_reading_aid(
        context, [{"round": 1, "decision": "keep", "candidate_selected": True}]
    )
    assert aid["selection_known"] is False
    assert aid["current_source_basis"] == "unknown"
    assert aid["prior_candidates"][0]["is_current_retained_round"] is None


def test_inconsistent_history_does_not_establish_retained_bytes():
    aid = retained_state_reading_aid({"selected_round": 2}, [{"round": 2, "decision": "revert"}])
    assert aid["prior_candidates"][0]["is_current_retained_round"] is None


def test_live_request_builders_receive_actual_post_revert_selection(tmp_path):
    result, store, calls, _, _ = search_run(
        tmp_path,
        [
            {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25},
            {
                "before": "VALUE = 2\n",
                "after": "VALUE = 3\n",
                "peak": 20,
                "loss": "changed",
                "checks": {"numerical_acceptance": False},
            },
            {"before": "VALUE = 2\n", "after": "VALUE = 4\n", "peak": 19, "target": True},
        ],
    )
    try:
        assert result["target_met"]
        ultra = json.loads(calls[4]["messages"][-1]["content"])
        patch = json.loads(calls[5]["messages"][-1]["content"])["evidence_context"]
        for context in (ultra, patch):
            aid = context["retained_state_reading_aid"]
            assert aid["current_retained_round"] == 1
            assert [row["is_current_retained_round"] for row in aid["prior_candidates"]] == [
                True,
                False,
            ]
            assert aid["current_source_basis"] == "retained_candidate"
    finally:
        store.close()
