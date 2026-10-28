# F3 explicit numerical tiers — offline implementation

This change prepares two independent s2 requests and evaluates their numerical requirements. It does not execute a campaign, allocate funds, call a model, run a GPU, or certify a new repair. The latest fixed-nine and historical campaign scores are unchanged.

## Contract and compatibility

Policy.numerical_requirement accepts legacy (default), exact-loss20-v1, or observed-bf16-v1. The default Policy.model_dump() and nested/JSON serialization still contain exactly the original four keys. Existing resolve_policies(default) and resolve_policies(strict) remain equal. Existing tolerances, parameter/memory/throughput gates and protocol-v2 acceptance thresholds remain unchanged. The independent F3 strict tier name is scoped to headroom.final48.s2-tiers.v1; it does not redefine the old evaluation policy alias.

exact-loss20-v1 requires a completed original baseline and candidate with exactly 20 updates, all 20 recorded finite backward loss scalars bitwise identical, known unchanged observed precision, no numerical change, and independently established equal inputs/effective batch/objective. Comparison uses IEEE-754 binary64 representations after the existing Lab .item() capture, including signed zero. It does not compare every parameter or optimizer tensor bitwise. Unknown pairing or precision fails this explicit tier. The actual s2 source is still unsupported by the existing bounded pairing contract; a test confirms this has not been silently expanded. Therefore the current s2 strict tier cannot honestly be declared accepted merely because its scalars match.

observed-bf16-v1 requires explicit numerical-change permission and actual complete BF16 precision observations to finish. Existing tolerance and all safety checks still apply. A valid FP32 intermediate improvement may be kept while target_met remains false, so search continues toward the BF16 tier. Permission alone, a model assertion, or unknown precision cannot complete the tier.

The verifier records numerical_requirement and numerical_requirement_evidence (per-check results, observed precision, pairing booleans/null, scope and limitations), with checks.numerical_tier for explicit modes. The search independently recomputes the requirement against the original baseline; it rejects nonexact strict candidates and unsupported BF16 target claims. Legacy reports are not accepted as proof for a new explicit tier.

Only explicit F3 requests append the requirement and scope to diagnosis evidence and patch context. Global prompts and the previously frozen nine native-admission/profile files are unchanged. PatchPolicy accepts the new field; the default patch request removes its legacy value to preserve the old request shape.

## Pure helpers

headroom.acceptance.final48_tiers.prepare_s2_tiers(base: FixRequest) returns two separate validated requests (strict, allow_precision). It preserves source/arguments, runtime configuration, caps, seed and search settings, and requires fit:22GB, 20 updates, the fixed model and standalone mode. Source selection/pinning remains the caller's responsibility; this helper does not read or execute that source.

summarize_s2_tier(tier, request, result) accepts supplied run observations or the canonical report envelope with run and verification. It recomputes numerical and ordinary memory checks, retains reported values separately when needed, and exposes tier_met, observations and selected artifact links without promoting memory-only success. Callers must execute requests independently and preserve their actual run IDs/patches. No live runner or allocation is added here.

## Verification receipt

Final focused run: **287 passed in 7.50 seconds**, with an outer DNS/socket deny guard (zero attempted network access). Scope: test_final48_tiers, test_compare, test_search, test_orchestrator, test_evaluation, test_patch, test_honesty, test_protocol_v2. Tests use synthetic observations, MockTransport and temporary local Git/source fixtures on azuki, never model/GPU outcomes. An end-to-end mock search continues through two nonexact strict candidates instead of stopping; the legacy path keeps its prior prompt-policy shape.

All eight changed/new source/test files had identical before/after test hashes. Ruff and format checks passed; scoped gitleaks found zero leaks. The previous nine native-admission/profile files still match their frozen receipt. The initial test log and the intermediate failure log are retained: two added pipeline test fixtures initially contained a literal backslash-n instead of a newline; correcting those fixtures yielded the passing run. Do not add overlapping earlier test counts.

Pending: independent review, eventual authorized integration/execution of the two F3 requests, and genuine source-bound pairing support/evidence if strict s2 acceptance is expected. No two-tier performance numbers, Pareto dominance, historical score changes, or parameter/optimizer bitwise claims are introduced.
