# Evidence-blocker contract review — 2026-10-25

This receipt covers a bounded diagnosis-contract repair and offline validation. It records no new provider request, GPU run, candidate success, or acceptance score. The next live campaign must be audited independently with its own fixed nine-scenario denominator; historical successes cannot be combined with it.

## Contract and limits

The host builds an evidence-availability catalogue from the exact outgoing evidence Markdown and its captured source metadata. It records source hashes and visible line intervals, without repeating source contents. Structured requests may identify a delivered field or source interval and state whether they block a current plan, a hypothetical alternative, or overall feasibility. Legacy responses retain optional fields and unverified provenance.

Validation emits machine-readable feedback only for deterministically checkable contradictions and invalid references or dependencies. An explicitly alternative-only request cannot silently serve as the sole blocker for an already proposed current plan. The existing supplement allowance is unchanged, and every returned diagnosis still passes all validators. Genuine missing evidence, unsupported runtime observations, semantic uncertainty, savings requirements, policy gates, and `needs_more_info` remain intact; the validator does not force readiness or propose a scenario-specific repair.

A visible parent object does **not** prove that an unobserved child field exists. Field-availability contradiction checking requires the requested field to exactly match the advertised complete field; child paths remain unknown. Source intervals are checked against actually visible numbered lines. Text availability never proves that runtime values were observed or applied.

The catalogue is capped at 8 KiB, including the final omitted-entry counter. A final size check removes entries if necessary, so a counter-width change cannot exceed the bound. It remains subject to the shared 64 KiB combined-context limit. Ultra reasoning is enabled with the existing 8192-token limit; supplement limits, request accounting, and acceptance thresholds are unchanged.

## Validation

The focused suite completed with **196 passed in 1.98 seconds** across:

- `tests/test_evidence_blockers.py`
- `tests/test_diagnosis_bounded_repair.py`
- `tests/test_diagnosis_invocation_grounding.py`
- `tests/test_diagnose_schema.py`
- `tests/test_diagnosis_schema_constraints.py`
- `tests/test_diagnose_contract.py`

Coverage includes visible versus redacted or omitted source, malformed references and ranges, current-plan dependencies, alternative-only blockers, genuine unsupported evidence, legacy compatibility, parent/child ambiguity, bounded catalogue transport, exact supplement limits, and repeated validation of subsequent replies. Mock HTTP checks preserve the actual schema/reasoning transport assertions. Existing dynamic-schema assertions were updated to include the catalogue actually sent in the request; unrelated schema fields retain exact equality checks.

Ruff `check`, Ruff `format --check` for all eight changed files, and `git diff --check` passed. This focused receipt does not replace the separately run full regression or future live acceptance.

## Retained-request read-only check

The first retained diagnosis request for each listed case was read from the existing local audit store. Its stored payload hash was checked, and the catalogue was rebuilt from the retained outgoing Markdown and captured source metadata. No raw request, source body, credential, or private database is reproduced here.

| Retained case | Source interval | Catalogue result | Runtime-observation result |
| --- | --- | --- | --- |
| s2 capacity v2 | `train.py:116–121` | Visible source text | Unsupported, unchanged |
| nanoGPT | `train.py:336` | Visible source text | Unsupported, unchanged |

These checks used **zero new provider calls and zero GPU runs**. They establish text availability in those retained requests, not diagnosis correctness, patch validity, runtime shape observation, or target attainment.

## Frozen file hashes

| File | SHA-256 |
| --- | --- |
| `headroom/evidence_blockers.py` | `d3fedd6af3252d6fe55153af8f202a8c1d62aa6785e5b91fbef8ac78b8cb775c` |
| `headroom/diagnose.py` | `7ecb52759f9be7b2cded5af5d7b4b6bf5ec510d66eae0f550fc0a346a6ef33ae` |
| `headroom/diagnosis_schema.py` | `9cf2e3fe5b14e949f6efb6ae58c82c7d169cf32396c272dffd6647641cf558eb` |
| `headroom/schemas.py` | `887db9094e2d5c80c01303e2066b0956a1a8254c52cfd350b8d4b6d8398a92c0` |
| `tests/test_evidence_blockers.py` | `0974ddbc5be10d5d03854d68c4cff96f542a7108949ad03734ae2d03d11d3398` |
| `tests/test_diagnosis_invocation_grounding.py` | `81072f24dd59abf992bd1100b0156be75a4971afaac2272c09de3eaf03893420` |
| `tests/test_diagnosis_bounded_repair.py` | `17766ef11bf5d71cd0038aa39513d6effadc5b220d50180c51f37d95ac0d47bf` |
| `tests/test_diagnosis_schema_constraints.py` | `9dce2aa69506f66203569191c9f63f4fdcf9a1a0bcc7a9b21e032516b4086ea5` |

The private focused and retained-request metadata receipts remain on the server. Their byte hashes below bind this summary without publishing their contents:

- Focused receipt SHA-256: `f18e6207a15baa97f3e68590fd8b64b5add716fcd54479285e0ee3a7fb6c38cf`.
- Retained-request metadata receipt SHA-256: `c0d9cf8f9065b0cc0357f20ba30e5721561fdb853f5e22ff59000db4070b6888`.

No production source or test file was changed while writing this report. Future model accuracy and the original acceptance gates remain unproven by these offline checks.
