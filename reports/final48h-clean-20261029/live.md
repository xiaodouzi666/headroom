# F5 clean-checkout live attempt

**The clean-checkout CLI was invoked correctly, but the live Quickstart did not run.** Run 01b872b7d4e24bd9a1109827777e4529 stopped as needs_human / runtime_not_ready before baseline capture or model dispatch.

| Check | Observed result |
| --- | --- |
| Clean checkout | /tmp/headroom-f5-20261029-krupo1aa/repo at 6c7cde25b7b17ef2aaf236aa2c6543abb57f8499 |
| Source identity | All 126 bound files matched; Git status was clean |
| Actual CLI | The checkout's own .venv/bin/headroom; own interpreter shebang and package root verified |
| CLI exit | 78 |
| Supervisor wall time | 3.2357087871059775 seconds, within 480 seconds |
| Runtime refusal | Private regular .env file with mode 0600 is required |
| Baseline / repair rounds / model calls | Not run / 0 / 0 |
| Report produced | Yes, describing the prerequisite failure |
| Cleanup | Verified |
| Actual model cost | $0 net; exact, settled |
| F5 live Quickstart acceptance | Not met |

The installed console, CLI module and execution bridge hashes match the files in the independent checkout. The console imports that checkout's package; the observed receipt names its package root and console path. The shared budget/profile paths did not substitute the original source checkout.

The worker failed the private credential-file prerequisite before executing the GPU workload. This audit did not read any credential value, create a replacement file, rerun the command or alter the source. There is no baseline result, candidate, numerical comparison or new repair success. In particular, this is not a case of the baseline already satisfying fix-oom.

The earlier clean-install/preflight evidence remains separate. This live attempt neither repeats that installation nor establishes the remaining release/tag/push checklist. [live-receipt.json](live-receipt.json) records the sanitized execution facts and hashes of the original outcome, CLI receipt, report and settlement.
