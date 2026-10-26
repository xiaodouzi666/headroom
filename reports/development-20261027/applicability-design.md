# Empirical repair applicability: bounded v1 design

Date: 2026-10-27 (Asia/Shanghai).

This addition audits exact points represented by explicitly selected archived
job/round pairs. It does not run source, launch GPU jobs, invoke models, access
the budget ledger, or change any original acceptance rule.

## Public API

- `build_scope(evidence_root: Path, selections: list[dict]) -> dict`
- `check_scope(evidence_root: Path, scope: dict, query: dict) -> dict`
- `load_json(path) -> JSON value`: bounded strict JSON for CLI inputs.

Each selection contains exactly `job` (relative archive directory) and
`round` (positive integer). At most 128 unique selections are allowed.
The output protocol is `headroom.repair_scope.v1`.

## Evidence and decisions

The importer derives all paths from the explicit archive root, job name,
round number and strict 32-character Lab run identifiers. It does not follow
absolute paths supplied inside a report. It binds the report, configuration,
patch, CLI arguments, independent Lab results/manifests, and every copied
source file by SHA-256. Full source inventories must match their directories.

The existing read-only `verify_exact_application` reconstructs the patch and
compares candidate bytes. Its declared file set must equal the full
baseline-to-candidate source inventory difference. The original pinned source
contract is recomputed. Runtime tensor/parameter fingerprints and update
records are checked before `derive_pairing` and `compare_runs` are recomputed.
Saved verdict fields, when supplied, must agree with the recomputation.

A point includes both source inventories, patch, original/effective arguments,
baseline input/initial-parameter/update fingerprints, target, required updates,
policy, observed precision, and both runtime environments. Environment includes
container image, Python/PyTorch/CUDA/cuDNN, GPU and capacity, seed, allocator,
and deterministic controls. Equality is exact canonical JSON equality; it does
not coerce numeric types or infer behavior at smaller workloads.

Statuses:
- `tested_pass`: the existing target requirements and the stricter available
  workload, precision and environment observations all hold.
- `tested_fail`: an available observation establishes a target, numerical,
  workload-pairing, or required-update failure.
- `unknown`: a complete claim cannot be supported; absent measurements are not
  failures. V1 does not admit OOM/transformed-reference or unsupported-source
  claims.
- `invalid_evidence`: check-time archive/scope/schema/hash inconsistency.
  Build-time malformed evidence raises `ValueError`.

The checker rebuilds all selected evidence and compares the complete scope,
including implementation hashes, before querying it. At an exact repeated
point, an observed failure overrides passes; otherwise unknown prevents a
unanimous pass. Configured provenance is retained, including `human_control`.
This audit never adds a model repair success or changes historical scores.

## Bounds and trust

JSON inputs are at most 2 MiB each, reject duplicate keys and nonfinite numbers,
and have bounded nesting. Source trees are at most 32 MiB and 5,000 files.
Paths reject traversal, linked ancestors/leaves and special files. This is a
trusted local archive audit, not protection against a concurrent malicious
filesystem writer or an attacker who forges both the archive and its scope.

Finite scalar-loss/runtime observations are not mathematical equivalence or
future-success proofs. Runtime hooks are cooperative. The scope does not
certify speed superiority; CPU load and sampled GPU sharing remain limitations.

## Implementation-time smoke observations

Read-only inspection of existing R3 s3 round 2 returns `tested_pass`, with
the same 73.378694% measured reduction and 20 matched updates already recorded
in that historical run. This is historical reinspection, not a new trial.

The three separately prepared human controls at eval batch 2, 16 and 64 return
`tested_fail` because their recorded memory reduction misses their 20% target.
The importer preserves these failures and their human-control provenance.

Ruff check and format passed on the module. Root-owned tests, integration and
delivery receipts remain separate from this design record.
