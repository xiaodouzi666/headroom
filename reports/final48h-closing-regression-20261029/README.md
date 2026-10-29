# Closing engineering check — 2026-10-29

**The one final full regression did not pass.** Its original log and receipt are preserved. Focused follow-ups identify harness and fixture problems; they are not a second full-suite result and do not change real model/GPU acceptance scores.

## Original full run

- Source: e6cf7a220bd59846e74e057a1a972526e514e2ed.
- Result: **4182 passed, 185 failed, 18 errors**, exit **1**, pytest **653.25 s**, driver **655.17 s**.
- All **436** source entries were unchanged before/after. Original PLAN and executed guard hashes were unchanged.
- Exact command, timestamp and environment: [launch](launch.json). [Full log](full-regression-20261029T042732Z-b4d55445.log), [full receipt](full-regression-20261029T042732Z-b4d55445-receipt.json).
- No second full suite was executed.

## Exact failure classification

| Initial root cause | Failures | Setup errors |
|---|---:|---:|
| Closing harness treated dir_fd paths as relative to cwd | 130 | 0 |
| Closing harness mistook workload --device cpu for a Docker host device flag | 32 | 4 |
| API fixtures explicitly/defaulted to the real project root | 16 | 0 |
| Guard refused historical JSON under real runs/ | 1 | 14 |
| Obsolete publication fixtures / expected catalog | 2 | 0 |
| Snapshot fixture input rejection, later focused checks passed | 3 | 0 |
| Short spawn admission deadline | 1 | 0 |
| **Total** | **185** | **18** |

[failure-summary.json](failure-summary.json) maps every one of the 203 unsuccessful node IDs. The first summary parser incorrectly required long underscore borders and joined some pytest sections; its preserved preliminary output is **not authoritative**.

## Focused follow-ups, reported separately

| Selected follow-up | Result | Pytest time |
|---|---|---:|
| 158 original non-CPU unsuccessful nodes, revised harness | 136 passed, 22 failed | 69.22 s |
| 16 API fixture isolation checks after the minimal test fix | 16 passed | 2.89 s |
| 3 secure-retention checks after preserving the os.open capability identity | 3 passed | 0.46 s |
| 13 representative CPU nodes | 13 passed | 73.94 s |
| 9 previously excluded publication/snapshot nodes plus short-deadline check | 9 passed, 1 failed | 15.25 s |

The first focused wrapper saved its first-group result, then lost its SSH stdout connection before launching CPU checks. That interruption is recorded in [focused-result.json](focused-result.json); the unstarted 36-node CPU group is not claimed as executed. Subsequent selected checks ran detached with file-backed results. All focused execution finished at **04:53:57 UTC**, before the unchanged shared **04:55:34 UTC** deadline.

The three API test files now set ApiSettings.project_root to pytest's temporary root: test_availability.py, test_before_evidence_downloads.py, and test_search_mode_interfaces.py. Security assertions and production code are unchanged. Unused-import/format cleanup occurred after the CPU batch and is recorded separately.

## Remaining limitations

- **Still failing:** tests/test_api_deadline.py::test_waiting_job_expires_without_starting_and_slow_report_does_not_delay_watchdog. The test changes the admission deadline to **1.2 s**. Its second submission raises **AdmissionError(504): Source preparation exceeded its admission deadline** before the intended queued-wait/watchdog assertions. The threshold was not adjusted. This is a real test failure in the guarded environment; the root cause and effect under normal deployment deadlines remain unresolved.
- [Temporary job evidence](deadline-temporary-state.json) records the existing isolated fixture database, not production state. Its first job ended timeout at the overall deadline; the second ended timeout / preparation_deadline_exceeded. Both have api_worker_finished=true and api_cleanup_verified=true. These rows establish timeout/cleanup behavior, not correctness of later assertions that were never reached.
- test_build_wrapper_uses_synced_project_python_without_dotenv_or_system_python remains blocked by the explicit shell-command guard. No actual image build/network was permitted.
- test_existing_saved_lab_result_cannot_supply_missing_parameter_evidence requests another historical Lab JSON not included in the three approved isolated copies; that read remains blocked.
- **23 CPU nodes were not rechecked**, [listed here](cpu-not-rechecked.json). Representative passes must not be generalized to them.

## Isolation and evidence integrity

The original guard is preserved byte-for-byte. New harness versions fix path/argument interpretation without enabling production credentials/databases, DNS/INET, GPU jobs, privileged devices, host networking, service changes, or image pulls/builds. Parent and multiprocessing-spawn negative probes are saved for each revision. Historical tests read only exact, read-only copies of three whitelisted non-secret JSON artifacts in an isolated temporary directory. Production databases remain denied.

[CPU cleanup evidence](cpu-cleanup.json) contains **17** saved records from the actual CPU representative batch; every record has cleanup_verified=true. There were **zero real model requests and zero GPU jobs**.

Repository-wide ruff check ., three-file ruff format --check, and git diff --check passed after fixture cleanup. The scoped .ruff.toml excludes only Python execution-evidence files in this report directory: their exact bytes and receipt hashes are preserved rather than rewritten for style. Production/test lint rules are unchanged.

[Final receipt](final-receipt.json) records outcomes and source differences. Do not add focused pass counts to the old full count or describe the current project as having passed a new complete regression.

The staged secret scan initially flagged 66 source SHA256 values across six
inventories. All were recomputed against 11 tracked public source files and
matched. The added exclusions require both an exact report filename and the
exact verified digest; no credential pattern or whole directory was excluded.
See [digest review](gitleaks-digest-review.json).

The Ruff pre-commit hooks use the same narrowly scoped archive exclusion for
this directory's execution scripts, following the existing immutable-evidence
pattern. Actual product and test files still run both hooks; the gitleaks hook
continues to scan all staged files. No hook was disabled.
