"""Existing retrieval provenance is displayed without performing or upgrading research."""

import copy

import pytest

from headroom.report import build_report, check_report_numbers, render_markdown

TARGET = "https://docs.pytorch.org/docs/2.5/generated/torch.optim.AdamW.html"
OTHER = "https://docs.pytorch.org/docs/2.5/checkpoint.html"


def source(url=TARGET, match=True, **changes):
    return {
        "url": url,
        "title": "Documentation",
        "kind": "documentation",
        "version_match": match,
        **changes,
    }


def operation(url=TARGET, method="extract", cached=False, **changes):
    return {
        "provider": "tavily",
        "method": method,
        "status": "cached" if cached else "succeeded",
        "cache_hit": cached,
        "api_calls": 0 if cached else 1,
        "torch_version": "2.5.1+cu124",
        "results": [source(url, content_characters=120)],
        **changes,
    }


def document(operations=None, sources=None, target=TARGET, status="partial"):
    research = {"status": status}
    if operations is not None:
        research["operations"] = operations
    if target is not None:
        research["target_documentation_url"] = target
    return build_report(
        {"status": "needs_human", "research": research},
        sources=[source()] if sources is None else sources,
    )


@pytest.mark.parametrize("cached", [False, True])
def test_matching_successful_nonempty_extract_reports_observed_provenance_only(cached):
    doc = document([operation(cached=cached)])
    before = copy.deepcopy(doc)
    text = render_markdown(doc)
    assert "Recorded version match: matched" in text
    assert "extract / " + ("cached" if cached else "succeeded") in text
    assert ("cache; no new API call" if cached else "live API call") in text
    assert (
        "Target-document extraction: observed in retained " + ("cache" if cached else "live call")
        in text
    )
    assert "API compatibility remains unverified" in text
    assert "Research status: partial" in text
    assert doc == before and doc["summary"]["target_met"] is None
    assert not check_report_numbers(doc, text)


def test_runtime_version_and_search_only_do_not_certify_target_extraction():
    sources = [
        source(f"https://docs.pytorch.org/docs/{v}/generated/torch.optim.AdamW.html", False)
        for v in ("main", "2.11", "2.12")
    ]
    op = operation(method="search", results=[{**s, "content_characters": 120} for s in sources])
    doc = document([op], sources)
    text = render_markdown(doc)
    assert text.count("Recorded version match: not matched") == 3
    assert text.count("search / succeeded / live API call / runtime torch 2.5.1+cu124") == 3
    assert "Target-document extraction: not observed in retained operations" in text
    assert "Research status: partial" in text


@pytest.mark.parametrize(
    "mutation",
    [
        "search",
        "wrong_topic",
        "issue",
        "empty",
        "bool_size",
        "failed",
        "mismatch",
        "unknown_match",
        "unknown_provider",
        "cache_conflict",
        "missing_provenance",
    ],
)
def test_incomplete_or_different_evidence_does_not_claim_matched_target_extract(mutation):
    op = operation()
    if mutation == "search":
        op["method"] = "search"
    elif mutation == "wrong_topic":
        op["results"][0]["url"] = OTHER
    elif mutation == "issue":
        op["results"][0]["kind"] = "issue"
    elif mutation == "empty":
        op["results"][0]["content_characters"] = 0
    elif mutation == "bool_size":
        op["results"][0]["content_characters"] = True
    elif mutation == "failed":
        op["status"] = "failed"
    elif mutation == "mismatch":
        op["results"][0]["version_match"] = False
    elif mutation == "unknown_match":
        op["results"][0].pop("version_match")
    elif mutation == "unknown_provider":
        op.pop("provider")
    elif mutation == "cache_conflict":
        op["cache_hit"] = True
    else:
        op.pop("api_calls")
    text = render_markdown(document([op]))
    assert "Target-document extraction: observed" not in text


def test_legacy_source_without_fields_stays_unknown_even_with_version_url():
    doc = document(None, [{"url": TARGET, "title": "Legacy"}], target=None, status="succeeded")
    text = render_markdown(doc)
    assert "Recorded version match: unknown; retrieval: unknown" in text
    assert "Target-document extraction: unknown (exact target URL not recorded)" in text
    assert "Research status: succeeded" in text


def test_exact_target_not_reconstructed_from_topics_or_runtime_metadata():
    doc = document([operation()], target=None)
    doc["run"]["research"]["topics"] = ["adamw"]
    text = render_markdown(doc)
    assert "Target-document extraction: unknown (exact target URL not recorded)" in text
    assert "extract / succeeded" in text


def test_operation_order_and_multiple_retrieval_provenances_remain_visible():
    text = render_markdown(document([operation(method="search"), operation(cached=True)]))
    assert "search / succeeded / live API call" in text
    assert "extract / cached / cache; no new API call" in text


@pytest.mark.parametrize("flag", [None, "true", 1])
def test_version_flag_requires_recorded_boolean(flag):
    text = render_markdown(document([], [source(match=flag)]))
    assert "Recorded version match: unknown" in text


def test_malformed_or_omitted_metadata_remains_unknown_and_visible():
    for ops in (None, [None], [{"results": "bad"}], [operation(OTHER)] * 65):
        text = render_markdown(document(ops))
        assert "Target-document extraction: observed" not in text
        if ops is None or ops != [operation(OTHER)] * 65:
            assert "unknown" in text
    text = render_markdown(document([operation(OTHER)] * 65))
    assert "operation metadata missing or omitted" in text
    assert "retained operation metadata incomplete" in text


def test_provenance_is_whitelisted_and_escaped_without_raw_body_or_cache_keys():
    op = operation(
        torch_version="<script>\n## forged",
        request_id="PRIVATE_REQUEST",
        cache_key="PRIVATE_KEY",
        context="PRIVATE_BODY",
    )
    doc = document([op], [source(title="<script>\n## forged")])
    text = render_markdown(doc)
    assert "<script>" not in text and "\n## forged" not in text
    assert "PRIVATE" not in text


def test_no_recorded_sources_never_becomes_research_pass():
    doc = document([], [], target=None, status="skipped")
    text = render_markdown(doc)
    assert "No runtime research sources recorded." in text
    assert "Research status: skipped" in text
    assert "Target-document extraction: unknown" in text


def test_malformed_method_status_values_remain_unknown_without_render_failure():
    text = render_markdown(document([operation(method={}, status=[])]))
    assert "unknown method / unknown" in text
    assert "Target-document extraction: observed" not in text
