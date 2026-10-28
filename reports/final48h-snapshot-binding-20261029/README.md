# Snapshot feature allocation bridge — offline verification

The normal snapshot workflow now accepts a trusted budget factory without replacing its runtime. It retains `build_live_runtime`, `open_run`/`close_run` and `live_model` provenance. A bound request revalidates the registered feature child, receipt/profile/ledger identity and the actual uploaded file hashes before opening its run and before every reservation. Upload paths are excluded from the intent, allowing content-identical server copies; source, traceback and snapshot bytes and sizes remain pinned.

The Web server can receive `snapshot_allocation_parent` privately through `create_app`. The manager uses only its fixed `snapshot-web` slot, claims before spawning, and settles only after a terminal result, verified process-group cleanup and the core's private `cleanup.json` receipt. HTTP accepts only the existing upload fields and cannot select a receipt, slot, claim or amount. Default `None` preserves the normal configuration; no public flag or deployed service was changed.

The CLI's private `HEADROOM_SNAPSHOT_FEATURE_BINDING` file is checked by `load_snapshot_feature_binding(path, request=..., project_root=...)`: current-user ownership, mode 0600, bounded regular file, no symlinks, registered snapshot slot, actual input hashes and run identity. It then uses `snapshot_feature_context(binding, project_root=...)` around the normal workflow. A trusted controller must call `snapshot_cleanup_verified(run_root, run_id)` and verify normal return before settling. Missing receipts, aborts and cleanup failures cannot be treated as clean. These controls neither create funding nor authorize calls.

## Checks

[75 tests passed in 10.79 seconds](focused-tests.txt), including 9 new cases and the 66 existing snapshot core/route cases. The new tests traverse real `CliRunner` and `create_app` entry points, native snapshot parsing, the normal runtime and SDK client, real temporary allocation accounting, the spawned Web worker, owner downloads and cleanup. SDK `MockTransport` returns synthetic responses and charges; no provider or GPU is contacted. `live_model` in these fixtures confirms the normal code branch, not real model evidence. Ruff check/format passed; the redacted publication scan is recorded in [receipt.json](receipt.json).

The new cases also reject HTTP receipt selection, foreign-owner reads, nonprivate/symlink binding files, changed uploads and substitution of an offline runtime factory. Public outputs continue to say that the patch has not run on hardware.

## Remaining acceptance

No actual allocation, judge token, live s2/nanoGPT/Web diagnosis, measured repair or real charge was created. Public submission remains disabled. A reviewed private parent, approved funding and real acceptance runs are still required. CLI claim/settlement orchestration remains a trusted controller responsibility, separate from merely invoking the CLI.
