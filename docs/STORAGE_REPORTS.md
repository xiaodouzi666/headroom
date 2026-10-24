# Storage and report contracts

This implementation prepares the storage/report portions of T1.7 and T1.8. Offline
persistence/rendering tests do not satisfy the live model-driven CLI loop, required
LLM calls, a successful model repair, or `git apply --check` on its eventual patch.
The original acceptance gates remain in `docs/PLAN.md`.

## Store API

```python
from headroom.store.db import Store

store = Store("runs/headroom.sqlite")
run = store.create_run("run-id", target="fix-oom", status="baseline")
store.add_event("run-id", "run.started", {"mode": "offline-preparation"})
store.update_run("run-id", status="needs_human", reason="Awaiting model access")
```

All methods return plain dictionaries or lists of dictionaries:

- `create_run(run_id=None, data=None, **fields)` and `update_run(run_id, data=None,
  **fields)` merge JSON payload fields; identity/timestamps/event counters are
  managed by the store. Updates cannot replace these reserved fields.
- `get_run(run_id)` returns a dictionary or `None`; `list_runs(limit=100)` returns
  newest-first rows. Missing parent runs on writes raise `KeyError`.
- `add_event(run_id, kind, data=None)` accepts the C.6 event vocabulary plus concrete `run.preflight`, `run.queued`,
  `evidence.started`, `patch.started`, `report.started`, `report.written`,
  `verify.reference`, and `budget.reserved` lifecycle events, and returns
  `id`, `run_id`, `kind`, `sequence`, `created_at`, plus both nested `data` and
  payload fields. `events(run_id, after_sequence=0)` reads in sequence order.
- `add_round(run_id, data=None, **fields)` allocates the next positive `number`.
  Explicit `number` must be that next number. `rounds(run_id)` reads rows.
- `add_llm_call(run_id, data=None, **fields)` accepts `model`, `role`, `cost_usd`
  (decimal string, Decimal, or null), `input_tokens`, `output_tokens`, and arbitrary
  JSON metadata. It also accepts the current ledger shape `cost={usd,status,...}`
  and `usage={prompt_tokens,completion_tokens,...}`. Each attempted provider call,
  including retries and failures, must be appended by the caller exactly once.
  The store does not dispatch or retry calls. `llm_calls(run_id)` reads records.
- `add_research(run_id, data=None, **fields)` / `research(run_id)` preserve research
  metadata without converting credits to dollar costs.
- `usage(run_id=None)` reports `calls`, `known_cost_usd`, `total_cost_usd`,
  `unknown_cost_calls`, `complete`, token totals, known token subtotals, and
  `by_model` groups. Any unknown cost makes the total null, while the known
  subtotal remains available. Missing token counts likewise make their total
  null. Zero calls or an explicitly reported zero charge remain distinguishable
  from a call whose charge is unknown. Money aggregation uses Decimal; float,
  nonfinite, negative, and unreasonably large precision inputs are rejected.
- `close()` disposes pooled database connections.

The SQLModel tables are exactly `runs`, `rounds`, `events`, `llm_calls`, and
`research`. SQLite uses WAL, foreign keys, a busy timeout, and one Session per
operation. Every write obtains `BEGIN IMMEDIATE`; event counter increment and
insertion commit together. A unique `(run_id, sequence)` constraint provides an
additional invariant. Sequence order means database allocation/commit order, not
an assertion about the wall-clock time of concurrent external work. Never share
a Session between worker threads. JSON payloads reject nonfinite numbers.

## Report API and measurement provenance

```python
from headroom.report import generate_report

report = generate_report(
    "runs/run-id",
    {"run_id": "run-id", "status": "needs_human", "target": "fix-oom", "baseline": baseline_result},
    evidence={"before": before_evidence_bundle},
    verification={
        "after": after_result,
        "target_met": False,
        "loss_equivalence": "n/a",
        "checks": checks,
    },
    diagnosis=diagnosis_dict,
    rounds=round_dicts,
    sources=source_dicts,
    usage=store.usage("run-id"),
    artifacts={
        "before_png": "baseline/evidence/timeline.png",
        "after_png": "after/evidence/timeline.png",
        "patch": "patch.diff",
    },
)
```

`build_report(run, **kwargs)` constructs the JSON document without file access;
`render_markdown(document)` renders it; `generate_report(output_dir, run, **kwargs)`
writes `report.json` and `report.md` and returns that same document. Each output
file is replaced atomically. The two files are not a multi-file atomic transaction;
regenerate the pair if interrupted between the replacements.

Inputs are plain JSON-compatible dictionaries/lists. Evidence may be a single
before bundle or `{before: bundle, after: bundle}`. Bundles retain their original
`analysis.header`, `category_bytes`, warnings, stack evidence and provenance.
Lab results are `run.baseline` and `verification.after` (fallback `run.after`).
`peak_allocated_bytes`, `peak_reserved_bytes`, `capture_complete`,
`step_ms_median`/`step_ms`, `status`, `steps`, `loss_series` and `shared_gpu` retain
Lab meanings. Exact peak evidence is required for a reduction percentage;
conflicting result/header values disable that calculation and add a warning.
Without complete measurements the figure is `unknown`, never an invented zero.
No target-met assertion is accepted without a completed after-run; the renderer
otherwise reports the caller's verifier judgment and does not independently
certify it. Model root-cause byte estimates and projected savings remain labelled
as hypotheses/plans. Step-time change is not presented as an independent
throughput benchmark. Cache gaps alone do not prove fragmentation.

Reports contain Summary, Root causes, Fixes, Verification, Timeline, Peak
composition, Allocator notes, Sources, Model usage & cost, and Evidence
limitations. Partial/needs-human reports use the same sections. Relative before/
after PNG, patch and environment links are emitted only for existing regular
files inside the output directory. Traversal, absolute paths, outside symlinks
and URL-scheme artifacts are rejected or omitted with warnings. No placeholder
image or patch is created. Sources accept HTTP(S) URLs only. Untrusted text is
escaped for HTML and Markdown; rendered patches are HTML-escaped preformatted
text. Rendering never executes or applies a patch.

Displayed GB and percentage strings are derived once into `report.json`, and
`report.md` uses those strings. GB is decimal bytes / 1,000,000,000. The checker
verifies every GB/GiB/percentage figure against JSON string values, including
quoted supplied text; it verifies numeric provenance, not scientific correctness.

```bash
uv run python scripts/check_report_numbers.py runs/run-id
uv run pytest -q tests/test_store.py tests/test_report.py
```

Tests include SQLite restarts, WAL/table shape, concurrent writes across four
Store instances, event/round rollback, exact known and unknown cost accounting,
partial reports, missing figures, tampered numbers, unsafe text/paths, and the
retained real T1.2 acceptance metadata when present. The actual s2 optimizer
share remains below its unchanged threshold; s5's high cache gap remains
unconfirmed fragmentation. These artifacts are used as read-only test inputs;
no GPU workload or provider request is made by these tests.


## Selected configuration handoff

Reports now expose `selected_configuration` from the persisted `run.kept` and
original request. It preserves the selected round, original/effective execution
argv, target arguments and allocator setting. Argument arrays preserve token
boundaries; they are displayed as escaped JSON, never executed or converted into
a shell command. Missing historical metadata stays null or absent rather than
being reconstructed from the last attempted round.

The Run page's main downloads include `cli.json` and `configuration.json`.
The latter is the selected tier's `manifest.json`, served through the API
without creating another manifest. The report's retained configuration table
links patch, environment, CLI and manifest files; its selected configuration
section repeats the files associated with the displayed selection.

A source diff does not include CLI arguments or environment changes. A CLI-only
or environment-only repair can legitimately have an empty diff. Reproduction
requires the original source, source patch, recorded environment and effective
target arguments. For captured wrappers, the manifest also supplies the
execution argv and target descriptor; Lab uses these to apply and verify its
targeted override. An ordinary shell does not consume this descriptor. Users
running outside Lab must explicitly update their launcher/configuration; see
[Command-mode repair](COMMAND_MODE.md#reproducing-a-kept-wrapper-configuration).

The JSON preview is an audit aid, not an automatic execution tool or a new
repair acceptance claim. Offline tests cover CLI-only selection, retained
selection after a later reverted round, descriptor/argument display, unknown
historical fields, file links and HTML escaping.
