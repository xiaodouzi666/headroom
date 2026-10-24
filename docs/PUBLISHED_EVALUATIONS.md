# Published evaluations

Results now has a separate **Published evaluations** section above browser-session
runs. It reads saved campaign evidence; loading, selecting, or downloading a
campaign never starts a workload, calls a provider, reads credentials, or spends
credit. A clean instance has no publication manifest and shows
**Evaluation publication pending**.

## Read-only endpoints

- `GET /api/evaluations` returns the explicitly curated catalog, or
  `{"status":"pending","evaluations":[]}`.
- `GET /api/evaluations/{id}` returns that campaign's public rows, recomputed
  summary, paired ablation, and evidence-limited conclusions.
- Unlisted IDs return 404. Invalid or unavailable published evidence returns 503,
  which is distinct from an unpublished empty catalog.

No run directory is scanned automatically. The endpoints use only
`<data_root>/public-evaluations.json` and
`<data_root>/published-evaluations/<id>.json`; the default data root is
`runs/api`. Reads are bounded regular-file reads without following symlinks.
The catalog supports up to 20 explicitly selected campaigns; each document is
limited to 2 MiB and 1,000 rows.

## Publishing reviewed evidence

An operator must first review the selected saved `campaign.json`, its provenance,
source runs and measurements. Copy that existing file into
`runs/api/published-evaluations/<id>.json`, then create a catalog such as:

```json
{
  "version": 1,
  "campaigns": [
    {"id": "reviewed-campaign", "title": "Reviewed evaluation campaign"}
  ]
}
```

This example describes the format; the repository does not install this catalog
or any fixture as public evidence. Use an ID consisting of lowercase letters,
digits, hyphens or underscores, at most 64 characters, starting with a letter or
digit. The corresponding file is
`runs/api/published-evaluations/reviewed-campaign.json`.

The public projection excludes host paths, audit directories, raw provider
responses, runtime configuration, source text and unstructured diagnostics.
It preserves scenario/condition/policy identity, provenance, explicit outcomes,
measurements, run IDs and source hashes. Report-produced percentage values may
be bounded finite Decimal strings; the projection preserves their exact text and
includes them in measured aggregates. Booleans, NaN/infinity, malformed strings
and unsupported precision remain unknown. Review the title and authored labels
before publication. The API does not certify that a manually altered file is
authentic; publication remains an operator decision based on original evidence.

A document marked `offline_fixture` forces all its rows to stay fixtures even
if an embedded row or summary claims otherwise. Embedded aggregate claims are
ignored and recomputed. Unknown provenance is not eligible for live scores.
Duplicate scenario-policy-condition rows are rejected instead of inflating a
summary. Paired diagnosis comparisons require exactly one row in all three
conditions, matching source hashes and effective policies, and authored/scored
truth. Excluded groups and unknown outcomes stay visible. Publishing an explicitly
labeled fixture for UI review is distinct from publishing a real benchmark.

## Tables and offline Markdown export

The Results table includes all planned per-scenario fields, a live-only summary
row, measured/unknown denominators, known versus unknown total cost, the
three-condition comparison, per-pair evidence and exclusions. Measured means are
not averages with missing values replaced by zero. Throughput is not inferred
from step time. Conclusions state denominators and descriptive paired differences
without declaring statistical significance or acceptance of a plan gate.

Campaign execution automatically writes the same Markdown tables. Existing
saved evidence can be rendered without rerunning an evaluation:

```bash
uv run python scripts/render_evaluation.py path/to/campaign.json > campaign-review.md
```

The input must be a bounded regular campaign JSON file with explicit provenance.
The command reads that input and prints Markdown; it does not update RESULTS,
change the original file, or enable live execution.

## Application and completion facts

Evaluation rows distinguish an observed application attempt from the configuration
eventually selected by keep/revert search. The primary columns are:

- **Any patch/config applied**: at least one recorded application succeeded.
  A later revert does not erase that fact.
- **Selected round** and **Selected patch/config applied**: the final retained
  configuration, checked against that round's application evidence.
- **Selected completed**: the corresponding verifier's explicit completion fact.
  The before/after measurements refer to this selected configuration.

The per-row round details retain each attempt's application result, candidate
completion and keep/revert decision. A candidate that completed but failed
numerical or policy validation can therefore remain visible even when it was
reverted. A configuration with only allowed argv/environment changes can count
as applied despite an empty source diff.

Workflow status and target success do not imply workload completion or successful
application. Missing historical artifacts remain unknown. Live-only summary
counts retain true, false and unknown outcomes separately; offline fixture rows
remain excluded from live scores.

## Per-round evidence in Run

Every round displays its preserved verification values, checks, notes, decision
and provenance. If the report renderer safely retained a complete UTF-8 patch
(`diff_status=available`), the UI can expand it and download those exact bytes as
`round-NN.patch.diff`, including a reverted round. Missing, rejected or incomplete
patch evidence never receives a download button. The final cumulative patch and
Pareto configuration downloads remain separate.
