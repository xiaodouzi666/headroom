# Shared snapshot SDK fixture migration — 2026-10-30

Only tests/test_snapshot_allocation_binding.py and tests/test_snapshot_retry.py changed. Production intent, validators, budget guards, histories and F3 implementation were untouched.

The shared SDK fixture and its spawned web worker now derive a synthetic provider response from the actual on-wire SnapshotDiagnosisIntent schema. They select an allowed reference that exists in the supplied visible peak set, omit bytes_gb, and validate the response against that exact schema. They do not make an invalid legacy complete-Diagnosis response pass a production guard.

The direct consumers are the ordinary bound snapshot run, private CLI flow, private owner-scoped web worker, and snapshot-retry normal-runtime test. The retry test's temporary local adapter was removed in favor of the same shared fixture. No other SDK helper consumers were found in the test directory.

Each relevant flow checks private/snapshot-intent.json as the unchanged structured provider-intent source, its canonical hash in private/snapshot-quantity-provenance.json, and the matching evidence.json hash. It asserts host-derived 512 bytes / 0.000000512 GB, unverified causal contribution, and hardware verification not_run. The public/derived diagnosis has the host-computed number; the saved provider intent has no bytes_gb field.

## Verification

Under unchanged closing_guarded_v4 parent and spawned-process negative probes:

- tests/test_snapshot_allocation_binding.py
- tests/test_feature_allocation.py
- tests/test_snapshot_public_binding.py
- tests/test_snapshot_retry.py::test_normal_runtime_and_sdk_use_retry_ledger_without_runtime_injection

**60 passed in 7.85s**, exit 0. See focused-initial.log/json. Temporary fixtures and SDK MockTransport only; no real provider, GPU, production claims or ledger writes. This targeted group is separate from the earlier 20 pin checks, with overlapping tests; counts must not be added as one suite.

The earlier schema_mismatch failure remains preserved in reports/snapshot-repair-20261030/intent-route-pins-focused-initial.log/json (19 passed / 1 failed). It demonstrated that the old test response incorrectly supplied bytes_gb to the new protocol. No historical live output was changed.

Final ruff, formatting and diff checks plus exact test-file hashes are recorded in final-checks.json.
