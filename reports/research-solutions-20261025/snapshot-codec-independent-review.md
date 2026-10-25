# Independent snapshot codec review

Verdict: **no blocking issue remains in the reviewed codec/analysis version for bounded integration and the planned S1 reference validation**. This review does not certify the new real S1 snapshot, the MVP score, or complete project acceptance.

## Independent evidence

- Codec SHA256: 67f74ae4f5c7b2ddab23ff6222c409c7133d1f9e9721f3de80150b34c5229d73.
- Analysis SHA256: 902fa48ec9c5337fffc58c2fcb9bb1fe8215020f032f922cc96ace849af61c80.
- Codec tests: **63 passed in 1.82s**.
- Existing evidence-analysis and evidence tests, run under an independent in-memory equivalence wrapper: **46 passed in 6.32s**. Every successful analyzer call was also evaluated on decode(encode(native)); **17 complete result dictionaries compared equal, zero unsupported inputs and zero differences**. The original test assertions remained active.
- Before/after hashes match. Exact pins and comparison counts are in snapshot-codec-independent-equivalence.json. No GPU/API calls or production edits were made by this reviewer.

## Format and correctness

Every frames field is explicitly either a stack reference or a literal wrapper, so native data such as a frames value of {stack: 0} is preserved as data. Frame intern keys retain scalar type, negative zero, dictionary order, nested fields and frame order. Tuples normalize to JSON arrays, as in ordinary JSON serialization.

The versioned envelope has an exact field set. Booleans cannot serve as integer versions or indices; negative/out-of-range references, malformed table types, ambiguous tags and mismatched claimed statistics are rejected. The only references are stack-to-frame and payload-to-stack; frame contents are literal data and do not recursively evaluate tags. Consequently the encoded reference graph has no reference cycles.

An isolated legacy native field named __headroom_snapshot__ is preserved. The combination of that marker with frame_table, stack_table, or all of version/snapshot/stats is a reserved envelope signature and is validated strictly. The codec does not claim that an arbitrary native object intentionally identical to the complete reserved format can be distinguished from an envelope.

## Resource boundary

The regular-file reader still has a hard **512 MiB** maximum; it rejects a higher requested cap, symlinks, oversized files, duplicate JSON keys and nonfinite JSON values. It never loads pickle. Existing oversized historical files remain oversized and are not reclassified as successfully readable.

The decoder independently recomputes the frame/stack counts, table bytes, stack entries, references, depth, payload-node count and theoretical expanded frame/node/byte totals. The configured maxima include 131072 frames, 65536 stacks, stack depth 512, 2 million stack entries, 2 million references, 64 million logical expanded frames, 256 million expanded frame nodes and 8 GiB logical frame bytes. These logical expansion limits **do not raise the 512 MiB input gate** and do not promise that arbitrary downstream full serialization is cheap. Shared decoding avoids allocating one physical copy per reference; current analysis serializes each immutable shared stack signature once.

## Shared object compatibility

FrozenStack and nested frozen dictionaries/lists preserve isinstance/list/dict, iteration, slicing, equality and standard JSON encoding behavior used by the analyzer. Normal mutation methods reject writes; public repeated __init__ no longer mutates shared aliases. copy/deepcopy retain the immutable objects. The reviewed current analysis/evidence consumers read these objects and do not require mutable copied frames.

This is ordinary API immutability, not security against explicit calls to built-in base mutation methods. An adversarial caller using list.__setitem__ or dict.__setitem__ can bypass subclass overrides; that limitation is not hidden or used as an authenticity claim.

## Issues resolved during review

- Inherited re-initialization could mutate shared aliases. Construction moved into __new__; public __init__ is non-mutating, with regression coverage.
- A marker-only native field was mistaken for an encoded envelope. Recognition now requires the reserved structural signature, and legacy/native collision tests cover the ordinary case.

## Remaining independent gates

The actual new S1 reference must separately demonstrate 20 updates, real peak/precision qualification, encoded snapshot bytes within 512 MiB and successful use of the original analysis path. Full-suite source binding, reference/candidate numerical pairing, true model repairs and the unchanged 6/9 gate remain separate. Historical snapshots, pickle files, failed receipts and historical scores are not rewritten by this review.
