# Super patch fix: current-source integration

The root-applied patch and generic prompt clarification are recorded in application.json.
The current production tree passed **294 tests in 103.11 seconds**, including real CPU
Docker wrapper execution. This is a targeted integration result, not a new full-suite
or live-MVP acceptance claim.

The original integration (287 passed, 7 failed) remains at
integration-20261024T224639Z-6d19d25c-receipt.json. Its new private response evidence
showed CapabilityNotVerified before any patch request: reviewed_fixture declared only
Ultra's mock reasoning capability. Root authorized the sole test fixture correction,
adding the same offline declaration for Super without changing prices, output caps,
budget logic or negative assertions. The successful rerun receipt is integration-20261024T225006Z-4b4386a8-receipt.json.
All **236 source/test/prompt/PLAN hashes** were unchanged during that rerun.

Reproduction from the server workspace:
    source scripts/env.sh
    .venv/bin/python reports/super-patch-fix-20261025/integration_driver.py

The driver writes a fresh timestamped result and source lists. Its guard installs
before imports and in spawn children; actual parent/spawn self-checks reject real
credentials, profile, production SQLite and DNS. API environment keys are removed.
Requests use SDK MockTransport; real Docker targets are CPU with the existing
network-none sandbox. No real model request, GPU workload or live-ledger write occurred.

actual-source-integration-summary.json contains the full test list, commands,
guard hash, source links, historical failure and all three final static-check receipts.
Ruff check, Ruff format check (318 files), and git diff --check all passed.
The original draft and its 94-test evidence remain under
.cache/setup/super-patch-fix-20261025/ without reclassification.
