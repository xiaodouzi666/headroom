# Architecture

Headroom keeps execution evidence separate from model interpretation. The trusted host orchestrator owns credentials and budgets; target scripts only enter the Lab container. No model runs locally.

## Data flow

1. CLI or API validates a script or pinned public GitHub repository. API uploads are session-isolated and bounded; repository setup scripts never run on the host.
2. The orchestrator validates policy and live prerequisites before paid/GPU work, snapshots source, then captures a bounded Docker baseline.
3. The evidence analyzer reconstructs allocator history, verifies source hashes and creates JSON, Markdown and a timeline. Cache gap remains a proxy, not a fragmentation diagnosis.
4. Ultra receives bounded evidence and structured constraints. Optional Nano labels annotate the top stacks without overwriting measured categories.
5. Tavily retrieves current-version API/flag references and stores a private 24-hour cache. Retrieved text is untrusted context. A run has at most four Tavily method calls.
6. Super proposes a diff, allowed allocator environment changes and safe argv changes. A fresh candidate tree receives the patch and static/compilation checks.
7. The verifier runs the candidate and, when needed, discovers an original small-batch reference. It keeps original-baseline, parameter, numerical, policy and timing checks separate.
8. Search keeps only justified improvements, records failed attempts and reverts its source pointer without deleting evidence. At most six rounds run. Each retained configuration has a cumulative patch, environment, argv and manifest.
9. SQLite stores runs, rounds, model calls, research and ordered events. Reports derive displayed numbers from saved JSON. Unknown charges survive failures and interruptions.

## Process and queue boundaries

FastAPI provides session-scoped uploads, historical/live SSE with Last-Event-ID, safe artifact downloads and curated replay. The production scheduler launches one supervised process at a time. Its hard deadline and verified owned-container cleanup prevent an abandoned worker from freeing the queue while work remains. An uncertain cleanup halts admission. Startup does not automatically resume an old paid job.

Docker has no network, read-only source/runtime mounts, an isolated temporary directory, a writable run-artifact directory, resource limits and no inherited API keys. Optional Hugging Face cache is project-local, manifest-reviewed and read-only. Captured source and raw runs are preserved.

## Evidence and acceptance boundaries

Offline fixtures test control flow, policy and accounting; they cannot prove a model capability, repair success or accuracy. CPU executions test Trainer integration and environment behavior; they cannot establish CUDA memory reduction. Baseline GPU runs prove actual workload behavior, not an automated repair. Imported baseline replay events explicitly identify the import instead of impersonating a historical live agent trace.

An OOM baseline has no comparable completed-run throughput. Numerical equivalence can be equivalent, non-equivalent, changed, or n/a; a missing comparison is not a pass. Parameter counts are observed runtime evidence with coverage limitations. All original plan gates, including s2's failed 40% requirement, remain visible in PROGRESS.

## Remaining external dependencies

Nebius account/key, actual model access, verified billing bounds and authorized balance are required for real diagnosis/patch/search/ablation. Public HTTPS needs owner-provided Cloudflare/domain access. Final design review, video recording and Devpost submission remain owner actions.
