# Verified runs preparation — 2026-10-28

The gallery data is prepared for review. Public routes remain disabled; this work does not restore the earlier replay interface, execute a model/GPU workload, or change a budget.

| Scenario | Recorded outcome | Peak before → selected after, bytes | Numerical comparison |
| --- | --- | --- | --- |
| s3 | Target met | 2,435,717,632 → 648,419,840 | 20 losses identical |
| s8 | Target met | 3,100,141,568 → 121,791,488 | 20 losses identical; runtime pairing checks incomplete |
| s4 | Target met | 24,768,717,824 (OOM) → 2,533,996,544 | First five losses match the original-workload offload reference; candidate completed 20 updates |
| s2 | Target met | 22,919,430,656 → 18,639,258,624 | 20 losses within tolerance, max delta 4.76837158203125e-7; runtime pairing checks incomplete |
| s1 | Not solved | 24,750,424,064 (OOM) → no selected repair | Executed candidate was reverted because numerical reference evidence was unavailable |
| nanoGPT | Not solved | 24,705,183,744 (OOM) → no selected repair | Executed candidate still OOM after one completed optimizer update; configuration changes only |

The four historical successes are supported by their independent campaign audits. s2 is an fp32 tolerance-based result; no bit-identical s2 result or bf16 comparison run was found. Parameter counts remain equal in all four selected repairs. Historical records were not altered.

[selection-review.json](selection-review.json) checks the newest matching records in the read-only database. [selection.json](selection.json) pins the six reviewed IDs and audit files. [extraction-receipt.json](extraction-receipt.json) records original artifact paths, hashes and extraction fingerprints.

Prepared data: [verified-runs.json](../../public-evidence/verified-runs.json), plus six report bundles and five nonempty code diffs under `public-evidence/verified-assets/`. Each failure's rejected candidate is kept separate from the selected-result fields. nanoGPT changed runtime configuration to batch_size=8 and gradient_accumulation_steps=4; its historical code diff was empty, so no patch download is offered. Its capture records one completed optimizer update and six backward-loss scalars before OOM. Only s2 has recorded Tavily sources: four documentation links, all marked as not version-matched. Other cards state that no Tavily source links were recorded.

Every diagnosis card is explicitly the **initial diagnosis**. Its evidence binding checks the first round's captured model request, exact baseline evidence text, stack-frame hash and the corresponding measured byte fields. Later diagnoses are never joined to baseline stacks by ID alone. Full frames are retained with user host paths removed; peak-live and lifetime-allocated bytes remain separate.

The safe reusable reader is `load_initial_diagnosis(run_dir, *, database, project_root)` in `headroom/api/diagnosis_evidence.py`. It returns the bound diagnosis/stack envelope or `None`, reads fixed bounded artifacts and captured calls, and does not register routes. The caller must authorize access to the run first.

Reproduce the offline extraction check:

```bash
.venv/bin/python -m scripts.publish_verified \
  --selection reports/verified-preparation-20261028/selection.json --check
```

The focused tests cover real published measurements, unknown pairing, failed candidates, changed/missing request bindings, stack/byte substitution, bounded reads, asset tampering and symlinks. Test and secret-scan results are recorded in [quality.json](quality.json). This preparation does not satisfy live-run, mobile-network, or video acceptance items.
