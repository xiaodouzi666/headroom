# Supported callsite reading aid — proposal only

R17 s1 rounds 3 and 4 selected checkpointing, but Super introduced a new _forward_impl method and wrapped it. The current static reference family only normalizes the original unchanged per-block module call. Both candidates therefore failed the unchanged source-contract preflight before GPU execution.

The draft proposal.patch does not add a family or repair program. It extracts the existing reviewed transform's exact original AST matcher into a shared helper, without changing that matcher or transform result. A new optional metadata helper projects the recognized original callsite into the same path/source SHA/SourceSpan IDs already used by the patch engine. The numerical-reference context can then carry those static coordinates to both Ultra and Super.

The aid says where the already-reviewed family applies. It supplies the existing expression and original line range, not replacement code, a benchmark patch, a chosen strategy or a new reference result. The model must independently select a compliant repair and write its own patch. A new wrapper method or moved forward body remains outside this site's existing family; the normalized-AST and all GPU/numerical/parameter/memory/speed gates are unchanged.

Activation requires the actual checkpoint reference strategy, active original OOM family, supported original/retained source, identical original/retained SHA and contract digest, and an exact complete source document. Unknown, stale or unsupported source, unsafe path, bad SourceSpan IDs, missing digest or oversize input yields no aid. An already changed retained source is not relabelled as the original. Reads use the existing bounded source-document reader and occur only after the cheap active-family gate.

The proposed aid cap is 1024 bytes inside the existing 12 KiB numerical-reference context and combined 64 KiB solver cap. If enrichment does not fit, retain the original context and leave the callsite unknown. No prior fact is deleted or truncated to make the aid fit. Exact status/metadata gates still say no reference execution or candidate equivalence has been proved.

proposal.patch and the three .py.txt files are drafts only. They parse/compile as source text but have not been imported, applied or tested. No production/test file, model request, GPU workload or accepted scenario was changed.

Before application, the necessary focused tests are:

- The shared recognizer produces the same original transform AST/bytes as before; unsupported wrappers remain unsupported.
- Valid exact source SHA plus original SourceSpan IDs resolves the already-reviewed call; CRLF, multiline calls and Unicode line positions preserve exact physical line coordinates.
- Wrong family, inactive/completed-baseline path, stale source/contract SHA, missing source, unsafe path or malformed IDs never advertises a callsite.
- Source128KiB, aid1024B, reference12KiB and combined64KiB boundaries remain hard; overflow keeps the old context and no invented completeness.
- A fresh Ultra request and a fresh Super request receive the same source-bound aid; metadata does not change needs_more_info, policy or verification.
- The saved R17 wrapper candidates still fail the original preflight; no historical run is rescored.

static-coordinate-capacity.json uses the actual original source solely to illustrate physical coordinates and serialization size. It is not an executed patch or a new model response. The new helper itself is not executed by that illustration.
