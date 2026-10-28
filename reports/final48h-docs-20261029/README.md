# F4 result-number evidence notes

This is a read-only extraction at source revision `b2a923133f22b2a03a412780c213c76290f1f96c`
on 2026-10-29. No model, GPU, ledger, allocation, or service call was made.
The original campaign thresholds and denominators are unchanged.

[numbers.json](numbers.json) is the canonical replacement manifest. It contains
7 independent protocol-v2 campaign receipts (R0–R6), all 63 scenario rows,
5 selected historical target successes, the complete latest R6 rows, and
source-bound long-context observations. Every direct claim names a path, JSON
pointer and SHA-256; each derived conversion names its inputs and formula.
The selected fields of untracked raw run reports are retained in
`source_excerpts`, together with their original file hashes. Those excerpts are
data copies, not a fresh execution or an independent reconstruction of missing
artifacts. Four successful selections were also checked against the existing
tracked public gallery; the R2 s1 result is not in that gallery.

## Corrected headline

- Latest measured campaign: R6, 2/9 memory targets; 3/9 valid correct first causes,
  with 5 unknown. R7 has not run.
- Historical protocol-v2 scenario coverage: 5 distinct target successes
  (s1, s2, s3, s4, s8), not a combined success rate. R4–R6 covers only 4; using
  the current gallery as the whole history would omit R2 s1.
- Best single campaign: 3/9. The required threshold is still 6/9.
- Among the selected historical successes, only s3 has 20 identical compared
  loss scalars and every recorded pairing check matched. This is empirical
  evidence, not mathematical proof. s1 and s4 compare only the first 5 scalars;
  s2 is tolerance-based; s2 and s8 retain unknown input/batch/objective pairing.

The historical-best rule is minimum candidate peak among independently recorded
target successes, with the latest campaign chosen on ties. Unaccepted candidates
are never put in a successful after column. All selected successful cases have
the full run ID, executed source commit, original report SHA, audit pointer,
requested target, numerical basis and parameter-count evidence.

## Template claims requiring correction

| Draft claim | Source-supported replacement |
| --- | --- |
| R7 is the latest result | R6 is the latest preserved measured campaign; R7 not run. |
| Historical automatic repairs 4/9 | Protocol-v2 R0–R6 has 5 distinct scenarios with target_met; R4–R6 and the current successful gallery have 4. Keep these scopes distinct. |
| Every successful repair has identical losses over 20 updates | The candidate update count and compared loss count differ for s1/s4. s2 uses tolerance and has a nonzero maximum delta. s2/s8 pairing is unknown. |
| s4 before/after both cover 20 updates | Baseline OOMed after 12 updates; candidate completed 20, with first-five reference comparison. |
| s2 baseline 21.6 GB | Selected R5 capacity-v2 baseline is 22,919,430,656 bytes = 22.919430656 decimal GB; this is a revised workload. |
| “6–7/9 across the last four campaigns” | Independent valid-first-cause counts R3–R6 are 4, 6, 6, 3. Raw category agreement is a different measure. |
| All nine root causes are known | s5 truth is an unverified fragmentation candidate; nanoGPT truth is unverified. Keep unknowns in the fixed denominator. |
| A nine-scenario campaign costs about $1.5–2 | Observed conservative subtotals vary by campaign and include incomplete/early-stop runs; actual totals remain unknown. |
| “10–15 minutes of GPU time” | Recorded totals are end-to-end wall time; this extraction does not establish GPU compute time. |
| A real 900k-token input was measured/rejected | The probe's nominal requested size was 900,000, local cl100k count 720,011, and provider prompt-token count unknown after HTTP 429. |
| 500k is the maximum context | 500,029 provider prompt tokens is an observed successful lower bound, not the provider maximum. |
| Evidence packs in all runs were 20k–30k tokens | No fixed range is established for all calls; use actual per-call input evidence. |
| s2 strict/bf16 tiers, ablation, HF repair results | These prospective experiments have not run; no placeholder result rows or invented improvements. |

The 268,920 real-evidence request is from
[the T1.3 receipt](../t1.3-acceptance-20261025.json);
the 500,029 success and nominal 900k rejection are from
[the T0.4 receipt](../t0.4-acceptance-20261025.json).
Both are preserved observations, not claims about current service limits.

## Units and timing

GB means decimal bytes / 1,000,000,000. GiB is stored separately as bytes /
1,073,741,824. Reductions are calculated from integer allocated-byte peaks with
Decimal arithmetic; rounded display percentages do not replace the exact bytes.
An OOM peak measures only allocations observed before failure; it does not reveal
the memory necessary to complete the unmodified workload. Completed candidate
steps do not extend the observed baseline.

Step intervals are recorded instrumentation measurements, not certified
throughput on an OOM baseline. The campaign time sums in the manifest add
recorded per-run end-to-end wall times, not GPU-only time. Conservative charges
are historical retained amounts, not a provider invoice or current balance.
The disjoint R0–R6 known sum is $7.68754786 and the conservative sum is
$7.91770552; neither includes all other project activity.

## Preservation and verification

The original docs/RESULTS.md is retained byte-for-byte after the new
`Full campaign history` heading. Its original SHA and length are in
`history_preservation`. The repeated historical title is intentionally retained
so the entire former document remains an exact suffix.

The extraction read existing reports and checked the four already-curated
successful byte pairs and numerical comparison counts against the public
gallery. The separate numeric checker completed successfully against all 79 original
sources; see [number-check.json](number-check.json). It checks the current README
and DEVPOST metric scopes, not arbitrary prose or all historical documents.
32 focused tests include full CLI failure on modified document numbers, wrong
scenario binding and changed raw source bytes. Ruff and format checks passed.
No hardware experiment or model request was run for this documentation check.

Manifest inventory: 1780 typed claims, including 626 numeric claims, from 79 source files. Original RESULTS: 62257 bytes, SHA-256 `c7654466d9930e6ad4f86bf9261112ad491c1f68efcf408de60cace68f2e4a7c`.

## Final documentation checks

[document-check.json](document-check.json) confirms zero forbidden phrase matches
in README, DEVPOST and FEEDBACK, no missing local Markdown links, only VIDEO_URL
placeholders, exact preservation of the old RESULTS suffix, and unchanged
original plan hashes. [template-changes.md](template-changes.md) explains
source-required corrections to the supplied prose. The whole committed history
through b2a9231 passed gitleaks (57 commits, zero findings); final changed files
are additionally checked by the mandatory staged pre-commit scanner.

No video URL, new experiment results, judge credential or Devpost submission was
invented. The deployment remains read-only while the separate A/C decisions are
pending.
