"""A bounded reading aid for current selection versus historical candidate snapshots."""

from collections.abc import Mapping


def retained_state_reading_aid(execution_context, candidates):
    """Describe orchestration identifiers only, without inferring source or outcomes.

    candidate_selected in old history is a snapshot from that round's end. Two
    earlier keep rounds can both say true; only the current execution selection
    identifies the retained round for this request. Missing metadata stays unknown.
    """
    context = execution_context if isinstance(execution_context, Mapping) else {}
    selected = context.get("selected_round")
    known = "selected_round" in context and (
        selected is None or type(selected) is int and 1 <= selected <= 6
    )
    basis = (
        ("original_baseline" if selected is None else "retained_candidate") if known else "unknown"
    )
    history = []
    if isinstance(candidates, list):
        for item in candidates[:6]:
            if not isinstance(item, Mapping):
                continue
            number = item.get("round")
            if type(number) is not int or not 1 <= number <= 6:
                continue
            decision = item.get("decision")
            decision = decision if decision in ("keep", "revert") else None
            current = (number == selected) if known else None
            # Inconsistent history cannot establish the currently retained bytes.
            if current and decision != "keep":
                current = None
            history.append(
                {
                    "round": number,
                    "recorded_decision": decision,
                    "is_current_retained_round": current,
                }
            )
    return {
        "schema": "headroom.retained_state_reading_aid.v1",
        "selection_known": known,
        "current_source_basis": basis,
        "current_retained_round": selected if known else None,
        "source_identity_reference": "execution_context.source_files",
        "edit_coordinate_basis": "current source documents, never a prior candidate diff or artifact path",
        "history_scope": "candidate_selected and selected_after_round in older entries describe that round's end, not the current request",
        "prior_candidates": history,
        "scope": "orchestration selection only; not source equivalence or verification proof",
    }
