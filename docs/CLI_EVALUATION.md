# Real CLI execution in evaluation campaigns

Live evaluation cases execute the installed `headroom` console script. The supervisor replaces its owned worker with that script using `execve`; the PID and original 480-second deadline stay the same. The CLI parses the actual `fix` arguments and calls `run_fix` once. This is not a second repair, a replay of an existing result, or an exit code calculated from workflow status.

The recorded `invocation_kind` is `installed_console_script`. This confirms the installed entrypoint and its actual operating-system exit; it does not claim a separate `uv run` launcher was executed. Existing historical campaigns have no such evidence and are not retroactively upgraded.

## Shared execution and budget

A bounded private JSON file passes the assigned run ID, existing Store path, case directory, evaluation condition, approved request, source hash and deadline. It contains no credentials or precomputed repair result. The CLI consumes the internal environment variable before dispatch, verifies its argv/import root/console digest and queued Store intent, and claims the invocation once with exclusive creation.

The parsed request must equal the approved request before model or Lab execution. Target, run/day budget, policy, steps, runtime profile and search mode are explicit CLI arguments. A discovered project YAML cannot silently change them. The CLI injects the same Store, run ID and condition services into the existing `run_fix`; runtime creation, global budget reservation, actual/bounded/unknown accounting and cleanup remain in their original implementations. A claimed invocation is never automatically retried.

A private raw worker result is saved before the CLI prints its final JSON and chooses its existing exit status. Result-file failure does not trigger a second call. The CLI receipt records actual return/exit state; the supervisor verifies the run ID, PID, result digest and OS exit against that receipt.

## Repository preparation

For a scenario declaring a repository URL, exact ref and command, the same case invokes the real `--repo/--ref/--cmd` CLI path and `prepare_repository` once, within the original deadline. The evaluator does not prepare it once and then clone/prepare it again.

The pinned nanoGPT path retains its reviewed three-file hash checks, source profile, interpreter flags, dataset argument rewrite and deterministic synthetic data hashes. The final script hash must match the scenario pin before dispatch. Repository preparation retains its existing public behavior: a valid local cached checkout is preferred; a missing/invalid checkout may cause a pinned Git fetch. This does not create another model or GPU run.

A generic local repository scenario without URL/ref continues through the existing local `--source-root/--cmd` CLI path. It cannot acquire the privileged pinned nanoGPT profile by naming a local directory. Pinned profile cases lacking their original repository identity fail before dispatch.

## Exit evidence and acceptance

The original CLI exit mapping is unchanged: completed returns 0; needs_human and budget_exceeded return 78; timeout returns 124; other failures return 1. A valid nonzero CLI result retains its real run status and partial report. Infrastructure failure, missing or inconsistent result evidence, deadline expiry and unverified cleanup still prevent successful supervised execution.

`evaluation_timing.cli` and each live campaign row's `cli` field preserve the receipt. `verified=true` means the invocation/result/OS-exit evidence agrees; it does not mean the exit code is 0 or the repair target passed. A deadline-killed CLI with no natural return has `observed_exit_code=null`, not a fabricated 124. The actual signal/process exit remains in `worker_exit_code`.

The original nine-run exit-0 requirement and the repair-quality thresholds are separate checks. A completed run can legitimately exit 0 while its target is false. Conversely, a safe retained candidate does not change a genuine CLI 78 into 0. Timeline events, model-call counts, usage, loss, target and reports must still satisfy their own original gates.

## Verification boundary

The implementation tests invoke the actual installed console script with offline test-only injection after exec. They cover same PID/UUID, one dispatch, explicit policy/config precedence, actual 0/78/124/1, replay refusal, source/request drift, real repository preparation with offline Git fixtures, and a real `run_fix → build_live_runtime → SDK MockTransport → Store/ledger` chain. These are software tests, not live model or GPU acceptance. A future authorized live campaign must supply the actual nine-run evidence.
