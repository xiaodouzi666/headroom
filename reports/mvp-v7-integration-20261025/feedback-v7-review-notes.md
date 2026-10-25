# V7 isolated candidate — review notes

Base: 85435dfbdeac765f902e2f3d21740ba0fcdf7389. Worktree: .cache/feedback-v7.
No main source/report edits; no commit, merge, push, live API, GPU, credential/profile/production Store/budget reads.

## Changes

- Both Ultra and Super receive the same retained effective invocation (CLI, launch argv when present, seed, required optimizer updates, allocator allowlist and source hashes), independently of defaults in captured source.
- Prior candidate diff bytes/hash, changes, structural errors/policy locations and application hashes come only from this run's bounded round/patch artifact namespace. Current retained source and rejected candidates have separate identities.
- Super now receives the same detailed verification feedback as Ultra, including failure/exception, finite loss and parameter-count evidence.
- Joint execution/candidate/verification + availability metadata is capped at 64 KiB under ASCII-escaped JSON, conservatively covering both wire encodings. Oldest matching round IDs are omitted together, explicitly unknown; stored rounds and gates are unchanged.
- Credential-like CLI flags are redacted in execution and candidate context and in prompt-only Super base_cli. Execution and merge still use original args. Only allocator env is allowed.
- Baseline OOM + incomplete candidate accurately reports that no small-batch reference ran; discovery/run control flow and numerical gates are unchanged.

## Validation

181 focused guarded tests passed (10.03s), followed by existing patch-pipeline regression recorded in the receipt/log. Both parent and spawn guards deny production credentials/profile/database and real DNS; no API key inherited.
New tests capture actual fake SDK/router requests for both models, actual CLI overrides, retained vs rejected source, failed diff/hash/exception/finite-loss/parameter counts, structural syntax/policy line, secret sentinels and unchanged execution args.
Boundary tests cover symlink file/directory/result, outside/traversal paths, oversized/missing/malformed artifacts, recursive JSON, invalid surrogate, UTF-8 truncation/full hash, worst-case escaped multi-round context, pairing by round ID rather than position, and fail-soft candidate metadata overflow.
Existing patch protocol/schema, source-span/edit/application/response modules, CLI, manifests, evaluation policy, PLAN, target thresholds, budgets, repair rounds, required optimizer updates and fixtures are untouched.

## Deliberate limits / remaining risks

- Prompt visibility only: this does not prove V7 improves real GPU acceptance. V6 results remain authoritative until root approves and runs V7.
- Bounded context may omit old paired rounds, or omit oversized candidate detail explicitly as unknown. Artifact paths never stand in for content; no model file tools are added.
- No duplicate-candidate cache or fixture-specific recipe is added.
- The CLI redactor recognizes credential-like option names. It does not infer secrets embedded in arbitrary positional strings/source text. No environment dump is performed.
- Existing 64,000-byte standalone verification gate remains; combined solver feedback is additionally bounded to 65,536 wire bytes. Original evidence/source payloads remain under their existing independent bounds.
