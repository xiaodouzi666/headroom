# Actual optimizer group options — implementation v2

The three paths in `verification.json` are applied and frozen for independent
review. No commit, service deployment, model invocation, GPU workload or finance
change was performed by this task. The earlier 013b8e15 proposal and its receipt
remain unchanged in the parent report directory.

Changes from the first proposal: the host rejects a raw component above 65536
canonical JSON bytes; optional context pressure restores the exact saved legacy
field before the original cap check, so old observed facts stay intact; option
sampling only reads existing weak Parameter identities and cannot add identities
to the old catalog after an earlier metadata failure or a late no-grad group.

Actual values come from group dictionaries at successful base-constructor return
or step-pre, with separate stages and call ordinals. Exact built-in scalar types
and two-element list/tuple types are preserved. Tensor scalars, custom objects,
strings, non-finite/oversized values and unknown option keys remain unsupported.
Unknown option names and values never enter the new artifact. Nothing converts,
reads or copies tensor values, mutates optimizer/state, substitutes source
defaults, invents completed updates, or proves mathematical equivalence.

Guarded focused verification: **167 passed, 4 deselected, 9.02s**. The new tests
include actual installed-hook CPU SGD construction and step, native update
preservation during optional failure, untouched legacy catalog on metadata
failure/late no-grad parameters, no tensor scalar read, exact types, malformed and
oversized raw inputs, source mismatch, zero updates and near-cap legacy parity.
The existing 34-child/680-native-call CPU regression remains in this run. Four
separately named real_cpu Docker nodes were excluded; this is not a GPU acceptance
score. The unchanged 3072-byte context cap and source/run binding remain in force.

`proposed.patch`, full draft copies, pre-apply hashes, applied hashes, JUnit, guard
log and final verification metadata are retained here. Root and the independent
reviewer must finish review before a new live preparation is pinned.
