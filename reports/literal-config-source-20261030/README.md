# Literal configuration source dependencies — 2026-10-30

The source collector previously omitted an executed local configuration reader when it was neither imported nor on an allocation stack. A real nanoGPT R8 bundle retained train.py and model.py while train.py:77 referenced a local configurator through exec(open(...).read()).

The change in headroom/evidence.py discovers only that precise static read-and-exec shape with a literal relative Python path and a read text mode. It requires a complete captured startup cwd inside /source, resolves against that directory rather than the referring file's parent, and omits candidates with an explicit chdir/fchdir in that source or unavailable cwd. It does not evaluate any source, path expression, configuration value or target code. The new observation explicitly leaves read-time cwd, execution and applied configuration unverified.

Only manifest-allowlisted Python files enter the existing queue and O_NOFOLLOW directory/file reader. Secret paths, outside paths, symlinks, changed source hashes, file/total-byte and shared 64-module bounds retain their original checks. This adds no recursive directory walk or filename/parameter/scenario-specific repair. Dynamic expressions and ordinary open calls do not add source files.

## Verification

The complete new dependency tests plus complete existing test_evidence suite passed under the unchanged v4 parent/spawn guard: **49 passed in 8.08s**. This includes launch import-root behavior, secret/symlink boundaries, captured hashes and evidence budgets. Ruff, format and diff checks passed; source remained unchanged during checks.

The initial broader run was **73 passed, 11 failed**. The failures were existing CPU Docker command-replay/wrapper cases returning ARTIFACT_EXPORT_FAILED/CAPTURE_ROSTER_INCOMPLETE before source collection. They remain in focused-initial.log. A single representative case was then run with git HEAD d64b6db's unchanged evidence module loaded by a temporary pytest plugin after the same guard installed; it failed identically with ARTIFACT_EXPORT_FAILED, image_id=null and cleanup_verified=true. This before/after comparison isolates that representative failure from the collector edit. It does not mark the other ten integrations as passed or establish their deeper infrastructure cause. No guard was bypassed and the worktree was not swapped.

The actual saved nanoGPT bundle was collected only in memory. It now includes train.py, model.py and the 47-line configurator.py, plus the static dependency at train.py:77. Five original manifest/source/evidence hashes remained unchanged. No historical evidence was rewritten. See nanogpt-offline-collection.json.

No provider request, GPU job, deployment, claim or new repair success is represented here.
