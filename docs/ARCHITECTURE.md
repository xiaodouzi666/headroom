# Architecture

Headroom keeps execution evidence separate from model interpretation. The trusted host orchestrator owns credentials and budgets; target scripts only enter the Lab container. No model runs locally.

## Data flow

1. CLI or API validates a script or pinned public GitHub repository. API uploads are session-isolated and bounded; repository setup scripts never run on the host.
2. The orchestrator validates policy and live prerequisites before paid/GPU work, snapshots source, then captures a bounded Docker baseline.
3. The evidence analyzer reconstructs allocator history, verifies source hashes and creates JSON, Markdown and a timeline. Cache gap remains a proxy, not a fragmentation diagnosis.
4. Ultra receives bounded evidence and structured constraints. Optional Nano labels annotate the top stacks without overwriting measured categories.
5. Super chooses Tavily search/extract calls through a bounded native tool loop. Original call IDs and retrieved results are retained; only actually retrieved or cached official references become Sources. All repair rounds share five logical model turns and four tool dispatch slots, in addition to the existing four-call Tavily quota and private 24-hour cache. Retrieved text is untrusted; unknown charges stop further work. Live tool-capability acceptance remains pending.
6. Super proposes a diff, allowed allocator environment changes and safe argv changes. A fresh candidate tree receives the patch and static/compilation checks.
7. The verifier runs the candidate and, when needed, discovers an original small-batch reference. It keeps original-baseline, parameter, numerical, policy and timing checks separate.
8. Search keeps only justified improvements, records failed attempts and reverts its source pointer without deleting evidence. At most six rounds run. Each retained configuration has a cumulative patch, environment, argv and manifest.
9. SQLite stores runs, rounds, model calls, research and ordered events. Reports derive displayed numbers from saved JSON. Unknown charges survive failures and interruptions.

## Process and queue boundaries

FastAPI provides owner-session uploads, historical/live SSE with Last-Event-ID and safe artifact downloads. The owner withdrew the Replay product (former T3.3); current source removes its cards, public listing/access exception and CLI command. Historical files remain archived, and actual target-command rerun/configuration replay is preserved. The production scheduler launches one supervised process at a time. Its hard deadline and verified owned-container cleanup prevent an abandoned worker from freeing the queue while work remains. An uncertain cleanup halts admission. Startup does not automatically resume an old paid job.

Docker has no network, read-only source/runtime mounts, an isolated temporary directory, a writable run-artifact directory, resource limits and no inherited API keys. Optional Hugging Face cache is project-local, manifest-reviewed and read-only. Captured source and raw runs are preserved.

## Evidence and acceptance boundaries

Offline fixtures test control flow, policy and accounting; they cannot prove a model capability, repair success or accuracy. CPU executions test Trainer integration and environment behavior; they cannot establish CUDA memory reduction. Baseline GPU runs prove actual workload behavior, not an automated repair. Archived baseline imports retain their historical provenance and never impersonate a live agent trace; they are not an active Replay product.

An OOM baseline has no comparable completed-run throughput. Numerical equivalence can be equivalent, non-equivalent, changed, or n/a; a missing comparison is not a pass. Parameter counts are observed runtime evidence with coverage limitations. Historical failed gates, including s2's original 40% requirement, remain visible in PROGRESS. The approved prospective s2 split and the user-withdrawn Replay requirement are recorded separately; the original plan file is preserved.

Client and diagnosis acceptance have separate prepare/execute drivers. Preparation pins authentic capture files and request bytes without reading account credentials. Explicit live execution uses the same router, reviewed profile and global durable budget ledger as repair runs, with a separate acceptance Store. Local token estimates and transport fixtures never earn live acceptance.

## Remaining external dependencies

Nebius account/key, actual model access, verified billing bounds and authorized balance are required for real diagnosis/patch/search/ablation. Public deployment is deferred until the owner's final confirmation; HTTPS, authentication and delivery must then be verified. Final design review, video recording and Devpost submission remain owner actions.


## Current qualification and accounting state

R3 achieved 3/9 targets (s3, s4, s8) and 4/9 valid correct first causes, with two
unknown truths. The unchanged six-of-nine gates remain unmet. A Super HTTP 529
request with unknown cost left the campaign partial and further paid dispatch
halted. See the [R3 summary](../reports/acceptance-v2-r3-20261025/independent-audit-summary.md)
and [public audit](../reports/acceptance-v2-r3-20261025/independent-audit-public.json).

The 3030-test/305-source receipt qualifies that campaign source. Subsequent
Replay removal and explicit existing-ledger selection passed the separate
3121-test backend qualification, 73 frontend tests and build/browser checks. The latter shares a selected canonical database across execution,
API observation and standalone acceptance, with no new funding, history reset or
unknown-charge release. Public prior work covers both individual memory methods
and combined optimization workflows; an advantage for this implementation has
not been demonstrated.

## Exact repair-scope lookup

The optional scope builder/checker is read-only and does not invoke the solver.
It recomputes patch application, source identities, pairing and the existing
comparison over an explicit set of archived rounds, retaining failures and
provenance. Its stricter applicability state is separate from original
acceptance. No point is inferred from neighboring configurations. See
[Repair scope](REPAIR_SCOPE.md) for the trusted-archive boundary and current
s1/s3/s4, completed-baseline limitation.
