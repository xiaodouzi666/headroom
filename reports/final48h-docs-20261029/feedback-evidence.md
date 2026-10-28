# Feedback revision evidence — 29 October 2026

This is a documentation-only review of the committed Headroom records at `b2a923133f22b2a03a412780c213c76290f1f96c`. No new inference, research-provider request, GPU workload, account lookup or financial operation was performed. The existing numeric records and campaign outcomes are unchanged.

## Deliverables and preservation

- `docs/FEEDBACK.md`: five readable feedback paragraphs, followed by exactly five actionable suggestions and a concise table of earlier observations.
- Paragraph sentence counts: Token Factory 8; Ultra 8; Super 7; Nano 6; Tavily 7.
- `feedback-before.md`: an exact byte-for-byte copy of `b2a9231:docs/FEEDBACK.md`, including its historical wording, pending states and numeric records.
- Original file: 32,995 bytes; SHA-256 `645baf1a841c89a9dc020f3d49305ac3905453eb082bb3200f8173a8ad3c7220`.
- The original text was moved to this separate archive because retaining it verbatim inside the rewritten feedback would conflict with the requested language check. The clean table retains its technical observations, including failures and incomplete evidence, and links the exact archive.
- No new account identifier, payment instrument, contact information, credential or billing export was added. The archive contains only already-committed public content; its historical usage estimates and development limits have not been rewritten as card charges.

## Evidence and wording decisions

| Topic | Saved evidence checked | What the rewritten feedback says |
|---|---|---|
| Onboarding | Existing task history separates account setup, promotional access and API-key configuration; no complete start-to-finish timer is recorded. | State the steps without inventing an elapsed time. |
| Endpoint availability | [Initial endpoint observations](../tokenfactory-minimal-20261024.json): US directory 18 entries, default directory 30; both contain the four inspected NVIDIA models. | Describe only the measured directories and the US inference endpoint; avoid exclusive-region or provider-wide claims. |
| API controls | [Capability review](../live-campaign-20261025/capability-review.json): tiny JSON fixtures, tool classifiers, template/effort pairs, ineffective system prefixes and Lightning reasoning limits. | Distinguish an accepted request from a demonstrated parameter effect. |
| Real Ultra evidence | [Client receipt](../t1.3-acceptance-20261025.json): 268,920 input tokens, 10.9135856 seconds; the free-text interpretation overstates fragmentation. | Round elapsed time to 10.91 seconds and retain the interpretation failure. |
| Long-input probe | [500k response](../live-campaign-20261025/ultra-long-500000/report.json): 500,029 server input tokens, exact needle, 17.9796622 seconds; [900k response](../live-campaign-20261025/ultra-long-900000/report.json): HTTP 429, retry-after 255, no server usage. | Round to 17.98 seconds; identify 900k as the probe label, not a verified provider token count; do not turn rate limiting into context overflow or a one-million-token success. |
| Ultra diagnosis | [Eight-workload review](../live-campaign-20261025/diagnosis-attempt4-review.json): seven first-category matches, eight valid reference sets, zero reported reasoning for all eight; forbidden proposals and an incomplete diagnosis remain. | Keep category matching, citation validity, semantic policy and repair correctness separate. |
| Reasoning settings | The capability review contains Super off samples with longer total output; the eight-workload result has no paired on/off quality experiment. | Describe an observed workable setting without asserting better speed, accuracy or lower total cost. |
| Super patching | [v2 findings](../live-campaign-20261025/mvp-v2-repair-findings.md), [v3 review](../live-campaign-20261025/mvp-v3-repair-review.json), [v4 review](../live-campaign-20261025/mvp-v4-candidate-verification-review.json), [v7 source-span review](../live-campaign-20261025/mvp-v7-source-span-review.json). | Retain completion exhaustion, missing line separators, placement errors and the distinction between compilation and successful repair. |
| Nano labels | The v4 review has four complete valid sets among eight synthetic workloads, none at 80% heuristic agreement; the maximum is 27.2727%. | Keep the eight-workload denominator, show 27.3% rounded, and label the comparator as heuristics rather than human ground truth. |
| Tavily | [Initial probe](../probe-tavily-20261024T005720856027Z-332161bd.json), [component reuse](../research-component-20261024T022414Z.json), and v4 research records. | Preserve successful versioned extraction, same-result search comparison, local-cache reuse, missing required citations and uncertain applicability of issue reports. |
| Cost uncertainty | Earlier feedback and saved response records distinguish missing cache split from absent total usage. | Preserve unknown exact usage cost without publishing new personal billing data or treating missing fields as zero. |
| Historical outcomes | Exact old feedback plus the [R6 report](../acceptance-v2-r6-20261027/README.md). | Keep prior failures and pre-dispatch stops visible; no score pooling, rescoring or new repair result. |

## Verification receipt

The following checks read existing JSON and Markdown only. They are document consistency checks, not new model or GPU results. No software regression suite was run for these prose changes.

```json
{
  "archive_matches_committed_bytes": true,
  "forbidden_phrase_matches": 0,
  "actionable_items": 5,
  "directory_model_counts": [
    18,
    30
  ],
  "real_evidence_tokens": 268920,
  "real_evidence_elapsed_rounded": 10.91,
  "long_probe_tokens": 500029,
  "long_probe_elapsed_rounded": 17.98,
  "diagnosis_first_cause": [
    7,
    8
  ],
  "all_eight_reference_sets_valid": true,
  "synthetic_annotation_complete": [
    4,
    8
  ],
  "max_completed_heuristic_agreement_pct": 27.3,
  "v4_patch_outcomes": {
    "UNSAFE_OR_INVALID_PATCH": 88,
    "STATIC_CHECKS_PASSED": 2,
    "PATCH_APPLY_FAILED": 19,
    "LLM_RESPONSE_REJECTED": 1
  },
  "research_api_calls": 8,
  "research_credits": "7"
}
```

The required case-insensitive expression `gate|ledger|reservation|HTTP 529|no claim|not presented|withdrawn` has zero matches in `docs/FEEDBACK.md`. The verbatim archive is intentionally outside that lexical requirement.

Additional checks: 31 relative document links resolve; `git diff --check -- docs/FEEDBACK.md` passed. Gitleaks scanned the three documentation files with redaction enabled and found zero leaks; the local scan receipt is `.cache/feedback-document-scan.json`. The final Nano sentence retains the saved missing-or-wrong-call distinction rather than inventing which failure occurred.
