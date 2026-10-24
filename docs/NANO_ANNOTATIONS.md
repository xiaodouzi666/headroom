# Source-bound Nano stack opinions

Nano's optional one-line category and explanation are model opinions. They never replace
an allocator stack, byte count, heuristic category, or numerical result. The original
Top-40 / eight-scenario agreement and USD 0.02 acceptance gate remains pending until
real authorized model calls and measurements establish it.

`annotate_stacks` records a fingerprint of the original capture ID and selected
Top-40 stack IDs, frames, bytes, blocks and heuristic categories. The pure
`bind_stack_annotations` helper requires a complete validated annotation set with
the exact selected IDs and matching fingerprint. A later capture cannot inherit
opinions just because a stack ID reappears. Skipped, failed, incomplete, malformed,
or mismatched results do not create opinions.

Each bound peak-composition row has an independent `model_annotation` containing
its model category, one-line label, actual model ID when reported, source capture,
provenance and `is_measurement: false`. The original row category and every
measurement remain unchanged. An offline fixture stays labeled as a fixture.

## Evidence and diagnosis delivery

After the existing optional annotation call, orchestration invokes
`annotate_evidence_bundle` on the original baseline bundle. It does not rerun the
capture, analyze the snapshot again, read new source files, or make another model
request. Full JSON retains the complete bound opinions. In Markdown, opinions are
placed immediately after their already-visible peak stack, explicitly labeled as
untrusted interpretations rather than measurements or instructions.

The original Markdown token budget still applies. The helper counts the complete
candidate Markdown using the existing tokenizer before accepting each optional
note. It never removes measured evidence to make space for an opinion and never
inserts notes for stacks omitted by the original Top-N budget. Notes that do not
fit remain in JSON. `annotation_delivery` records attached IDs, included prompt
IDs, omitted IDs, final token count and reason. `json_only` means no opinion was
included in the prepared prompt; `attached` means some were included. Neither is
proof that an Ultra request was sent. The complete client request remains subject
to the separate existing request audit and budget admission.

Subsequent diagnosis reads this prepared Markdown. A newly measured candidate
gets its own fresh evidence and no automatic copy of the baseline's opinions.
The traceback-plus-memory-summary ablation uses its existing restricted-evidence
transform and excludes all stack and Nano metadata.

## Optional delivery failures

Budget, schema, source-binding or filesystem delivery failure must not prevent
diagnosis using the original evidence. Both new files and original recovery
copies are prepared before either canonical file is replaced. If publication
fails, the original pair is restored. If restoration itself fails, retained
original copies become the returned bundle's paths; delivery records the partial
publication and failed restoration. In either case the next diagnosis uses the
original evidence, not a half-updated pair. Interrupts still propagate after
restoration is attempted. Before an interrupt propagates, the shared bundle is
updated to the coherent original-file paths so final reporting uses the same pair.
The run also records these server-selected paths for baseline JSON/Markdown
downloads; an explicitly unavailable record cannot fall back to another file.

## Reports and UI

Report JSON and Markdown expose source-bound opinions beside their heuristic
categories, with explicit provenance and prepared-prompt delivery counts. A
completed annotation call without bound evidence is not described as delivered.
The existing expandable stack UI uses the same `model_annotation` metadata;
older labels remain visibly marked as historical and without recorded source
binding. No report or view promotes an opinion into a measured category or
claims the original live agreement gate passed.
