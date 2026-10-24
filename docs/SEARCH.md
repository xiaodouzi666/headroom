# Bounded repair search and research integration

This implements T2.1 and integrates the T2.2 component with the repair loop.
Offline tests demonstrate software behavior; they are not s1/s2/s5 model or GPU
acceptance.

## Request and service contracts

`FixRequest` now has `max_rounds=6` (strict integer, 1 through 6),
`source_profile=None` and `research_enabled=True`. Setting `max_rounds=1`
retains the bounded single-round behavior. The optional search_mode is either
until_target (default) or bounded_pareto. The default stops at the first verified
kept configuration meeting the target. The explicit bounded mode continues after
that point, within the same 1–6 round limit, request/deadline bounds, budget and
numerical/throughput policy. It does not enable paid calls or authorize a new
runtime profile. A pinned repository profile is selected
internally by repository preparation, never authorized by an arbitrary upload.

`Services.research_factory` follows `ResearchSession.for_run`. The factory receives
the actual baseline's `env.torch`, Store, cache directory, credential/live state
and `max_calls=4`. Tests inject an offline factory. Missing versions, disabled
research or missing credentials stay explicit, without inventing documentation.

Two internal evaluation-only fields are available: `Services.diagnose` defaults
to `diagnose_with_router`, and `Services.evaluation_condition` is persisted
as provenance. These are not fields on the public request. The evaluation
harness owns its evidence restriction and diagnostic-model adapter; all model
calls must retain the existing Token Factory runtime and ledger.

## Search state and verification

The original captured source, original Lab result, original arguments, allocator
configuration and original small-batch reference remain fixed for verification.
Every candidate is compared to that same original numerical/parameter baseline.
If a previous kept step changed numerical behavior, that numerical-impact flag
remains active in later rounds; a subsequent "none" step cannot reset it.

Each round:

1. Rechecks the current kept source and the source files actually captured in its
   current evidence; asks Ultra to plan with that evidence and prior keep/revert
   decisions.
2. Applies one proposed step in an isolated PatchEngine copy. Rejected candidates
   and all repair attempts remain on disk.
3. Calls Verify against the original baseline, then judges incremental memory
   improvement and throughput against the current kept result.
4. Keeps only a completed candidate with lower measured peak and all original
   safety, loss, parameter, data/batch and numerical-policy checks satisfied.
   Missing checks are failures. A completed current state also requires reliable
   current-to-candidate timing within the throughput policy.
5. Advances only the kept source/argv/allocator pointers and fresh evidence.
   A revert changes no input files and removes no candidate/history.

The memory target is the only ordinary Verify gate that may remain false for an
intermediate keep. Original OOM has no comparable completed-run throughput;
that unavailable comparison is explicitly excluded, not presented as a speedup.
Once the current kept state completes, its throughput comparison is mandatory.
Additional Verify checks are preserved, including the OOM loss-decrease gate.
Unknown numerical equivalence cannot become a pass.

The default loop stops on a kept configuration meeting the target. Bounded
mode may continue reducing measured memory within the same keep conditions;
it does not accept increased memory merely for lower latency. Lower memory and
slightly higher latency can yield two genuine nondominated configurations.
No minimum point count or predetermined tier is required. Failed/dominated
candidates are not fabricated as configurations to fill a frontier.

Both modes stop at their configured round cap, missing required evidence/runtime
state, deadline cancellation, or a budget exception. A candidate after a
verified success must also satisfy the target; otherwise it is reverted with
verified_target_regression. The selected source, after result, verification,
arguments and downloadable patch therefore remain one consistent configuration.
A later revert, budget rejection or error cannot erase an earlier verified
success. Search completion and selected-configuration success are separate:
a bounded run reaching its configured cap is completed with reason
max_rounds_reached, not a proof of an exhaustive or optimal frontier. A budget,
deadline, needs_human or pipeline failure retains its corresponding partial
status even when a selected configuration has target_met=true.

Fresh evidence belongs to the selected configuration. When a newly kept
configuration lacks after evidence, the report clears the previous selected
after evidence/image and records after_evidence_status=unavailable; prior round
artifacts remain on disk. A further round stops with fresh_evidence_unavailable
instead of diagnosing stale evidence. At the final bounded round there is no
next prompt, so the search can end at its cap while explicitly reporting missing
after evidence.

Budget reservations and pending/settled billing remain in the existing runtime.
SIGTERM retains the last committed kept state and writes a partial report.
A round interrupted after a committed keep is recorded as kept; a configuration
not yet committed is excluded from the final frontier. No run history is deleted.


### Search outcome data

The stored run data and run_fix return include the same search object:

| Field | Meaning |
|---|---|
| mode | Explicit until_target or bounded_pareto request |
| baseline_target_met | Observed baseline goal state, or null when unavailable; never a repair result |
| first_target_met_round | First committed, verified successful repair round, or null |
| stop_reason | Machine-readable reason below; null while running |
| rounds_executed | Recorded attempted rounds, including an interrupted final round |

Stop reasons are target_met, max_rounds_reached, diagnosis_needs_more_info,
diagnosis_supplement_exhausted, fresh_evidence_unavailable, deadline,
budget_exceeded, runtime_not_ready and pipeline_error. The human-readable run
reason and individual round decision retain the concrete context. A baseline
already fitting its target does not set repair target_met, does not create a
Pareto point, and does not invent a patch or first successful repair round.

## Independent configurations and Pareto output

Every keep writes `configurations/round-NN/` containing:

- `patch.diff`: cumulative relative to the original source.
- `env.sh`: only validated cumulative allocator overrides.
- `cli.json`: original and full effective argv.
- `manifest.json` and `apply-check.json`: provenance, policy, hash and independent
  application check against a fresh original copy.
- The original-check copy, retained as check evidence.

Changes from separate rounds are therefore never mislabeled as independently
applicable incremental patches. Environment/CLI-only configurations have an empty
code diff and explicitly record that no code-application check was necessary.
No-newline-at-EOF source is preserved with standard Git diff markers.

`pareto.json` and `pareto.md` contain all kept points and the nondominated set.
A point dominates another only if both have trustworthy, finite timing and memory,
the same policy fingerprint and the same numerical-equivalence category.
Shared/unknown timing cannot establish dominance. Different numerical policies
are not pooled to fabricate a cross-policy winner.

The main report displays the retained configuration table and links each tier's
patch, env and argv. All displayed measurement strings are represented in report
JSON and checked by the existing number audit. Top-level `patch.diff`,
`env.sh` and `cli.json` remain compatibility copies of the final kept tier;
report links point directly to that tier.

## Bounded runtime research

Research follows the APIs/flags actually proposed in the selected plan step:
checkpointing/use_reentrant, allocator options, AdamW/fused/foreach,
bitsandbytes, torch.compile or FSDP. At most two distinct topics are explored
per run. Each exploration performs search plus extract, under the component's
four-call per-run reservation and 24-hour cache. Repeated topics reuse their
already recorded context. Search is never performed before the Nebius runtime
preflight and baseline complete.

Only a production live run reads the private regular mode-0600 .env to obtain
TAVILY_API_KEY. The implementation does not read that file during offline tests.
Research disabled, no applicable topic, missing credential/version or an
unavailable research session is reported explicitly. Optional research failure
does not manufacture a source and does not block a valid patch. Provider quota,
credits and unknown outcomes remain the component's actual recorded values.

Patch context contains the component's untrusted-data wrapper and at most
24,000 UTF-8 bytes of research text per topic. Truncation is labeled; full
component evidence remains cached/recorded. Sources are included in the final
report and the component writes each method operation to Store.research.

## Nano annotations and progress events

After original evidence and captured-source safety checks, production live runs
may call `annotate_stacks` through the existing runtime. Offline fixture runs skip
Nano. Annotations are stored in `annotations.json` and run metadata, linked from
the report, and never rewrite raw evidence categories. Unknown agreement or an
eight-scene acceptance result is not fabricated. The runtime owns the separate
per-run Nano amount ceiling.

The existing `diagnose.done`, `patch.written` and `annotate.done` event types
carry actual newly recorded LLM calls, models, elapsed time and cost. An omitted
or unknown value stays null. There are no role-derived model badges or new event
kinds.

## Validation and outstanding acceptance

Tests use synthetic provenance, the real LLM client/router with MockTransport,
fake Tavily clients and DNS/socket denial. They cover keep/revert/keep,
nonaccumulating original verification, original-to-final diff application, six-
and one-round bounds, budget/deadline interruption with kept artifacts, interrupted
Pareto publication, source/model defaults, policy-separated Pareto, shared/unknown
timing, research reuse/missing credentials/context/sources, real-record events,
report number audit and optional Nano gating.

The original s2 acceptance asks for a no-numerics two-round result and also a
default-policy frontier containing a bf16 tier. That conflict remains unresolved;
this implementation does not weaken the policy or synthesize either result.
Actual >=2-round s2 fitting, the requested real dual-tier frontier, and s1/s5
end-to-end research-source acceptance remain live experiment gates.


Final local integration regression for this handoff: **257 passed in 7.19s**
across eleven related Python test modules under an additional process-wide
DNS/socket denial guard; scoped Ruff passed. The search/orchestrator/report
subset has 67 cases. These are offline implementation checks, not live model,
GPU repair or competition acceptance.


Bounded-mode implementation checks are reproduced with:

    .venv/bin/python reports/bounded-pareto-20261024/offline_tests.py -q tests/test_bounded_search.py tests/test_orchestrator.py tests/test_search.py

The independent runner denies DNS/sockets and access to the real project .env
before importing pytest. Tests use the real SDK/router with MockTransport,
synthetic measurements and the existing isolated patch checks; no model API or
GPU acceptance is claimed. The report directory preserves test logs and a
source-hashed receipt.
