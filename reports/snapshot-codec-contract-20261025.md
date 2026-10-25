# Snapshot stack/frame interning v1 — 2026-10-25

## Trigger and status

The preserved s1 v2 native snapshot.json is reported as 1,284,045,979 bytes, above the existing 512 MiB JSON read gate. It was not loaded, rewritten, compacted, or replaced by this work, and its failed/readability evidence remains intact. No historical pickle was loaded.

The implementation adds a versioned lossless export and a bounded shared decoder. All original events, unknown fields, scalar types/values, frame order, repeated frames, and stack order are preserved. Native snapshot.pickle remains unchanged. This report establishes CPU compatibility and bounded-decoding behavior; the final scheduled v3 GPU capture must establish actual large-capture readability.

## Wire contract

The encoded JSON envelope has exactly six fields:

- __headroom_snapshot__: stack-frames
- version: integer 1
- frame_table: native JSON frame objects
- stack_table: ordered arrays of integer frame IDs
- snapshot: the native tree with each frames field explicitly tagged
- stats: recomputable counts and sizes

A frames field containing a stack becomes {"stack": stack_id}. Every other native frames value becomes {"literal": encoded_value}. Consequently an original {"stack": 0} is literal data, and cannot be mistaken for a reference. Absent frames fields remain absent; empty stacks remain empty. All indices are exact nonnegative integers, not bool/float/string coercions, and must refer to an existing table entry. Stack-to-stack references and reference cycles are not part of the format.

Typed interning keys distinguish 1, 1.0, True, and the sign of zero. Nested frame metadata and unknown native fields are retained. Native tuples are converted to JSON arrays, matching the existing native_snapshot export semantics; object instances and nonfinite values remain unsupported.

Legacy native JSON remains readable. A discriminator field alone is not enough to reinterpret a native snapshot. The compound discriminator/table/payload envelope signature is reserved by the protocol; complete encoded envelopes have strict version, field, type and recomputed-statistic checks. A deliberately constructed legacy object exactly matching that reserved envelope is inherently ambiguous and is not claimed as a supported separate representation.

## Shared decoding and bounds

Decoded stack lists and nested frame lists/dictionaries use read-only list/dict subclasses. They retain isinstance(list/dict), standard JSON serialization, equality, slicing/read access and deepcopy behavior; duplicate stack references share the same object. Public mutators raise, and re-initialization cannot modify an existing shared object. This is an internal cooperative immutable interface, not a defense against deliberate calls to list/dict base mutation methods.

Only the shared immutable stack type receives identity caching in evidence_analysis. Its existing canonical JSON signature, digest, classification and result construction are unchanged, but repeated events do not repeatedly serialize the same stack. Native mutable lists retain the old processing path.

Fixed default limits:

| Resource | Limit |
| --- | ---: |
| Snapshot file read | **512 MiB, unchanged** |
| Unique frames | 131,072 |
| Unique stacks | 65,536 |
| Frames per stack | 512 |
| Total frame IDs across stack table | 2,000,000 |
| Stack reference fields in payload | 2,000,000 |
| Theoretical expanded frame visits | 64,000,000 |
| Theoretical expanded frame nodes, including object keys | 256,000,000 |
| Theoretical expanded frame JSON bytes | 8 GiB |
| Nodes in one frame | 4,096 |
| Serialized bytes in one frame | 65,536 |
| Sum of serialized unique frame bytes | 64 MiB |
| Non-expanded payload value nodes | 8,000,000 |
| Native/expanded nesting depth | 128 |

Theoretical expansion counters are computed from per-frame/per-stack costs and each reference; frames are not materialized once per event. Node/string limits are checked while constructing frame keys, before an oversized aggregate can be serialized. Limits also apply to unused table rows. Recomputed statistics must equal the stored statistics; lowering a claimed count cannot bypass enforcement.

The loader uses bounded regular-file reads with O_NOFOLLOW/O_NONBLOCK, rejects duplicate JSON keys and nonfinite numbers, and cannot be configured above 512 MiB. Sparse oversized files and symlinks are negative cases. Unsupported values, malformed encodings, or resource overages fail closed; no event or stack is truncated to fit. Encoder errors remain ordinary capture/export failures rather than successful empty evidence.

## Integration

The common production reader is headroom.lab.snapshot_codec.read_snapshot_artifact(path). It now serves:

- build_evidence;
- diagnosis acceptance source/history checks;
- long-evidence acceptance, preserving original encoded-file SHA pins and explicitly labeling record pointers as decoded-native view pointers;
- s2 calibration and s2 calibration audit, including decoding any already independently verified historical indentation normalization;
- the final s1 research driver, integrated by its owner.

The hooks owner made only the serializer import and snapshot.json writer change to encode_snapshot(snapshot). It avoids cloning the entire native snapshot before interning. The pickle writer and existing native_snapshot helper remain unchanged. Finalization interruption tests target the new JSON-export seam and keep their previous partial-capture/non-acceptance assertions.

## CPU evidence

- Final integrated focused suite: **301 passed in 33.77 seconds**, including codec, evidence, analysis, client/diagnosis acceptance, s2 audit, finalization, logical updates, hooks and precision. Ruff and git diff --check passed.
- Codec-specific suite: **63 cases**, including exact native/encoded full analysis equivalence, actual build_evidence and long_evidence outputs, shared identity, nested read-only behavior, deepcopy/JSON, unknown fields and literal marker collisions, exact scalar types, malformed versions/references/stats, each resource bound, and unchanged file-size rejection.
- Independent reviewer: 46 existing evidence/analysis tests passed, with 17 additional full native versus decode(encode(native)) analysis-dictionary comparisons; zero differences and zero unsupported cases. The three checked source hashes did not change. Receipt: reports/research-solutions-20261025/snapshot-codec-independent-equivalence.json.
- The hooks/precision owner separately ran 107 integration tests after the serializer seam change.

A CPU-only synthetic example with 2,000 events and the same ordered 40-frame stack encoded 4,809,861 native JSON bytes into 132,658 bytes. It retained all 2,000 events and 80,000 logical frame visits using one shared stack and 40 frames. One observed run took 0.4101 seconds to encode and 0.0066 seconds to decode. These timings and size reduction are illustrative and are not GPU or acceptance results.

## Frozen source identities

- headroom/lab/snapshot_codec.py: 67f74ae4f5c7b2ddab23ff6222c409c7133d1f9e9721f3de80150b34c5229d73
- headroom/evidence_analysis.py: 902fa48ec9c5337fffc58c2fcb9bb1fe8215020f032f922cc96ace849af61c80
- headroom/lab/hooks.py, serializer integrated by its owner: 9f8952fc9fab02e3816ae9cae24d861ed6cb9706b89a52d3d690d734f2282825

No model/GPU calls, budget changes, old-result recomputation, or historical artifact replacement were performed for this codec work. No scientific or competition acceptance gate was lowered.
