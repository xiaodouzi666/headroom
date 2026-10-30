# R15 observation-scope audit — read-only

Six actual SDK request payloads in the isolated R15 store were inspected read-only.
`wire-excerpts.json` retains source/run-bound observations, matching catalogue
entries, exact relevant feedback, final questions and immutable request hashes.
It contains no source text, account records or credentials.

The availability catalogue correctly promises literal text delivery only. Its
`runtime_values_verified=false` means **that catalogue** performed no runtime
verification. It cannot negate a separate cooperative capture's own reported
status/scope/completeness. The compact system already says this distinction.
However the repair's `literal_observations` repeats that runtime values and
semantic prerequisites **remain unverified**, without limiting that statement
to the availability check. s2 then asks to confirm the already observed20-update
count. This is a plausible wording mechanism, not a demonstrated model-causal
experiment.

The s2 parameter request is only partly redundant: moments/shapes/dtypes/devices
are not parameter-catalog counts. s8 also already has catalog8/2886912numel and a
clearly reported registered-count mismatch, but dtype is still not captured.
The recommendation never makes those unobserved fields verified. s7 separately
combines a runtime field with source106-108 bounds, and asks for intended frozen
flags contrary to the reported actual training flags/updates. Nulling its bounds
only fixes the evidence syntax; it does not authorize changing trained parameters.

`scope-clarification-proposal.patch` changes only text in two feedback producers
and explicitly states null bounds for non-source refs in the compact prompt.
It changes no schema, validator decision, runtime verification flag, readiness
flag, price, token cap, call count, budget or scenario-specific answer. It is a
proposal only: the production files were not edited or retested by this audit.
