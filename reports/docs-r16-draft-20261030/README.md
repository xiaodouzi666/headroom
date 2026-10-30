# R16 documentation drafts — not applied

The three proposed files are README.md, docs/RESULTS.md and docs/DEVPOST.md under this report directory, with individual diffs. Their original public paths remain unchanged. These copies keep relative links appropriate to their eventual repository destinations. R17 may supersede this draft after its own outcome; no R17 result is presumed here.

| Claim | Independently checked R16 value | Inspectable source / pointer |
| --- | --- | --- |
| Executed / fixed denominator / threshold | 9 / 9 / 6 | R16 summary /metrics/attempted_rows, /metrics/fixed_denominator, /metrics/minimum_memory_targets |
| Memory targets | 1/9, s3 only | Raw campaign rows; summary /metrics/memory_targets |
| Raw first-category matches | 5/9 | Eight existing raw round-01 diagnosis artifacts joined to authored truth; s6 is missing, s5/nanoGPT truth is unverified |
| Valid correct first causes | 2/9 | Same raw diagnosis flags and categories; summary /metrics/valid_correct_first_causes |
| First-round ready / ready valid correct | 1/9 / 1/9 | Same raw flags; summary /metrics/valid_ready_diagnoses and /metrics/ready_valid_correct_first_causes |
| Final valid / ready | 4/9 / 1/9 | Latest existing diagnosis per case, counting absent s6 as unknown; terminal review /final_valid_diagnoses and /final_ready_diagnoses |
| Charged / known actual / actual total | $0.59904366 / $0.57097152 / unknown | Summary /metrics/cost; conservative bounds remain distinct from actual |
| s3 selected run | e4da7f935eed426aa7fd447cd4ee56ec, source 53dc8f4 | Original s3 report, R16 summary row 2 |
| s3 before / after peak | 2,435,717,632 / 648,419,840 bytes | s3 report /run/baseline/peak_allocated_bytes and /run/after/peak_allocated_bytes |
| s3 numerical scope | 20 identical scalar values, seed matched; input/batch/objective unknown | Original s3 report /run/baseline/loss_series, /run/after/loss_series and /rounds/0/verification/checks |
| Historical distinct / best single | 5/9 / 3/9 unchanged | Preserved R15 versioned manifest; new target s3 is already a member of the previous five |
| Published evaluations | 12 entries, old entries/files unchanged | R16 publication-applied.json /entries and /old_entries_and_files_unchanged |

numbers-checklist.json binds each claim to an exact file SHA and JSON pointer, and lists the per-case raw checks. s6 has no saved diagnosis; its failed report records Pipeline failed: ResponseValidationError. It is not silently converted into a category mismatch or a valid diagnosis.

The s3 lowest after-peak ties R15 exactly, so the documented latest-on-tie rule selects R16. Its first category is now activations and matches the authored reference. This does not improve its numerical-pairing scope. R15's original table row, number manifest and report remain unchanged. The entire RESULTS suffix after Full campaign history is byte-identical, as recorded in the checklist.

No public document, Devpost page, historical result, model request or GPU workload was changed by preparing these drafts.
