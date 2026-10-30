"""Static original-source coordinates do not supply a repair or prove execution."""

import copy
import hashlib
import json

import pytest
from test_reference_context import SCRIPT, bound_baseline, context

from headroom.patch_spans import source_span_document
from headroom.solver_context import MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES
from headroom.verify.checkpoint import transform_source
from headroom.verify.reference_callsites import checkpoint_callsite_reading_aid


def pair(tmp_path):
    ctx = context(bound_baseline(tmp_path))
    return source_span_document(SCRIPT.parent, SCRIPT.name), ctx


def test_factory_repeats_only_the_existing_source_call_and_never_a_replacement(tmp_path):
    document, ctx = pair(tmp_path)
    before = copy.deepcopy((document, ctx))
    aid = checkpoint_callsite_reading_aid(document, ctx)
    assert aid == ctx["reviewed_checkpoint_callsites"]
    assert aid["source_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert aid["entrypoint_name"] == SCRIPT.name
    assert "Basename only" in aid["path_scope"]
    assert aid["sites"] == [
        {
            "start_id": "L000029",
            "end_id": "L000029",
            "existing_call": "block(hidden)",
            "family": "non_reentrant_activation_checkpoint",
        }
    ]
    assert "path" not in aid["sites"][0]
    assert "replacement" not in aid["sites"][0]
    assert aid["reference_execution_verified"] is None
    assert aid["candidate_equivalence_verified"] is None
    assert document["lines"][28]["id"] == aid["sites"][0]["start_id"]
    assert len(json.dumps(aid, ensure_ascii=True).encode()) <= 1024
    assert len(json.dumps(ctx, ensure_ascii=True).encode()) <= MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES
    assert (document, ctx) == before


@pytest.mark.parametrize(
    "case",
    [
        "strategy",
        "inactive",
        "unsupported",
        "capability",
        "precondition",
        "missing_preconditions",
        "empty_preconditions",
        "contract",
        "digest",
        "family",
        "retained",
    ],
)
def test_unknown_unbound_or_unsupported_reference_cannot_advertise_coordinates(tmp_path, case):
    document, ctx = pair(tmp_path)
    if case == "strategy":
        ctx["selected_strategy"] = "legacy_small_batch"
    elif case == "inactive":
        ctx["source_contract_boundary"]["active_for_this_oom_baseline"] = False
    elif case == "unsupported":
        ctx["original_source"]["status"] = "unknown"
    elif case == "capability":
        ctx["capability_status"] = "unavailable_under_current_preconditions"
    elif case == "precondition":
        key = next(iter(ctx["explicit_reference_preconditions"]))
        ctx["explicit_reference_preconditions"][key] = False
    elif case == "missing_preconditions":
        del ctx["explicit_reference_preconditions"]
    elif case == "empty_preconditions":
        ctx["explicit_reference_preconditions"] = {}
    elif case == "contract":
        ctx["retained_source"]["normalized_contract_sha256"] = "0" * 64
    elif case == "digest":
        document["source_sha256"] = "0" * 64
    elif case == "family":
        ctx["source_contract_boundary"]["reviewed_edit_families"] = []
    else:
        ctx["retained_source"]["source_sha256"] = "0" * 64
    assert checkpoint_callsite_reading_aid(document, ctx) is None


@pytest.mark.parametrize(
    "case",
    ["absolute", "secret_path", "bad_ids", "surrogate_path", "surrogate_text", "empty", "newline"],
)
def test_malformed_documents_fail_unknown_without_reading_another_file(tmp_path, case):
    document, ctx = pair(tmp_path)
    if case == "absolute":
        document["path"] = "/private/train.py"
    elif case == "secret_path":
        document["path"] = ".env.py"
    elif case == "bad_ids":
        document["lines"][28]["id"] = "L000030"
    elif case == "surrogate_path":
        document["path"] = "bad" + chr(0xD800) + ".py"
    elif case == "surrogate_text":
        document["lines"][0]["text"] += chr(0xD800)
    elif case == "empty":
        document["lines"] = []
    else:
        document["newline"] = "invalid"
    assert checkpoint_callsite_reading_aid(document, ctx) is None


def test_nested_document_name_is_only_a_hint_not_a_guessed_root_path(tmp_path):
    document, ctx = pair(tmp_path)
    document["path"] = "nested/train.py"
    aid = checkpoint_callsite_reading_aid(document, ctx)
    assert aid["entrypoint_name"] == "train.py"
    assert "path" not in aid["sites"][0]
    assert "copy that document" in aid["path_scope"].lower()


def test_optional_oversize_coordinates_are_omitted(tmp_path, monkeypatch):
    document, ctx = pair(tmp_path)
    monkeypatch.setattr("headroom.verify.reference_callsites.MAX_CALLSITE_AID_BYTES", 1)
    assert checkpoint_callsite_reading_aid(document, ctx) is None


def test_reference_transform_bytes_remain_identical_to_reviewed_prior_version():
    assert hashlib.sha256(transform_source(SCRIPT.read_bytes())).hexdigest() == (
        "9e0a0e5718e83ef0d18df3f03403e86e519c4f55d5609aa6dc22df149bbfb59f"
    )
