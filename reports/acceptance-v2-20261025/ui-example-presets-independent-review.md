# UI/API example presets: independent read-only review

Date: 2026-10-25. Scope: product example selection and replay provenance only.
No production source was changed, no model or GPU was invoked, and no formal
MVP case, threshold, result, or historical public ID was replaced.

## Confirmed behavior

- `/api/examples` reads the eight original rows in `scenarios/INDEX.yaml`.
  Neither `s2_capacity_v2` nor the independent classification fixture is exposed.
- The existing `s2_fp32_adamw_1b` row is marked `expected_mode=reclaim`.
  Its own catalog receipt records a completed baseline with
  21,503,181,312 allocated bytes. This is below the 22,000,000,000-byte target.
  The different historical 21,553,250,816-byte measurement must not be described
  as this same receipt.
- Home and the API submission model default to `fix-oom`. Clicking an example
  currently changes only the example ID. The card's `reclaim` label therefore
  does not select a reclaim target.
- Example selection currently transfers only source text into the submission.
  Home does not send allocator or numerical-reference presets. Merely adding a
  capacity row would therefore omit its calibrated
  `expandable_segments:True` environment.
- This mismatch does **not** make the completed baseline pass Fix OOM:
  `headroom/verify/compare.py` requires
  `memory_target = baseline_oom and completed` for Fix OOM, and requires that
  check to be true for `target_met`. A completed s2 baseline makes it false.
  `headroom/search.py:baseline_target_met` can show that a completed baseline
  already meets the observed no-OOM goal; its own contract says that observation
  is not a verified repair or Pareto point. The orchestrator still enters the
  repair loop. The risk is an inappropriate target and unnecessary work, not
  an automatic successful repair score.
- Replay discovery reads explicitly curated terminal Store runs rather than
  limiting IDs to the example catalog. The five current public rows are
  recorded GPU baselines, all target_met=false, with an explicit no-diagnosis,
  no-patch, no-repair-verification reason. The s2 replay remains
  `826e6be46a8e5cf1991afb54375fcf02`, sourced from
  `808e39dd7b224c47881165407dc55a9a`.
  UI baseline provenance and “N/A — baseline only” labels are present.
  No false-success replay claim was found.

## Proposed minimum product change, after the current MVP audit

Keep the original eight-case inventory and original s2 public ID intact. Add a
small explicit, validated product-preset layer; do not automatically expose all
evaluation rows or calibration controls.

| Public example | Recommended target | Initial allocator | Meaning |
| --- | --- | --- | --- |
| s2_fp32_adamw_1b | reclaim | null | Historical completed optimizer-memory example; baseline already fits 22 GB |
| s2_capacity_v2 | fit:22GB | expandable_segments:True | New capacity repair example, independently calibrated above 22 GB |

The capacity preset uses the actual baseline source
`scenarios/s2_capacity_v2/train.py`, not any private optimizer/checkpoint control.
Its approved source SHA at this review is
`9565acfbcfc2f1eefd982c80be7ce943e09828578b9b44c3d70342bc82bf7f4c`.
The original s2 source remains
`bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b`.
Validate these identities when publishing the presets rather than silently
loading a changed file. The new capacity calibration measured
22,919,430,656 baseline bytes under the fixed allocator; this is human
measurement provenance, not a model success. Keep the classification fixture
out of the repair-example menu and out of the nine-model-case denominator.

The new preset need not change precision: use the existing strict default.
A separately chosen allow_precision policy remains explicit and recorded.
Do not silently interpret a capacity preset as permission to change precision.

### API resolution

Resolve defaults only when the caller omitted the field. Use Pydantic
`model_fields_set` (or an equivalent explicit supplied-field set), not
truthiness, to distinguish omission from deliberate values:

1. Omitted target for an example uses that example's recommended target.
2. Explicit target always wins, including an explicit `fix-oom` for completed
   s2. A nonblocking explanation may point out the mismatch; do not rewrite it.
3. Omitted allocator uses the example's fixed preset. Explicit allocator null
   intentionally clears it; a custom valid string overrides it. Such a run is
   no longer represented as using the calibrated capacity environment.
4. No example selected means no example defaults. A pasted script must not
   inherit allocator/reference state from a previously selected card.
5. Validate the resolved values with existing target, allocator, and reference
   validation. Build FixRequest, queue metadata, report provenance, and public
   run metadata from this same resolved submission.

Expose a bounded `recommended` object and source/provenance information in the
example response, not an arbitrary request dictionary. Whitelist target,
allocator_conf, and any future explicitly approved reference metadata; do not
spread untrusted catalog properties into FixRequest. No automatic precision
override is needed for these two presets.

### Home selection and manual override

Track target selection as automatic versus manually edited:

- Initially automatic: choosing old s2 selects Reclaim; choosing capacity
  selects Fit and 22 GB.
- Any manual target or fit-limit edit switches to manual mode, even if its value
  happens to equal the old default. Later card clicks preserve that choice.
- Offer an explicit “Use recommended target” action to return to automatic
  mode; show the current recommendation alongside a custom target.
- Selecting a capacity example supplies its allocator preset explicitly in the
  submitted request. Show that environment choice in the run details.
- Switching to pasted-script mode clears only automatically inherited example
  settings; keep a manually chosen target. Do not leak hidden allocator or
  reference presets into the pasted-script request.

This behavior prevents a target silently changing after the user edits it and
makes UI and direct-API omission semantics consistent.

### Replay and acceptance boundaries

Do not remap the historical s2 replay to the new source or relabel it as repair.
After a genuine new model run exists, use the existing replay curator first in
dry mode, then publish the selected artifact with its actual success/failure,
policy, source, and allocator provenance. Human calibration controls cannot
supply a model-repair replay. Failed genuine model runs may be shown honestly as
failed attempts, but do not fulfill a success gate.

The formal nine-slot CLI MVP and its 6/9 gate are unaffected by this product
preset work. Its source-frozen run and independent audit should finish before
these later source edits and the corresponding new validation.

## Necessary checks when implementing

- Old public IDs and source hashes stay intact; only approved capacity source is
  added. Classification/control sources are absent from the repair catalog.
- Omitted versus explicit target, allocator null, and custom allocator resolve
  correctly. Queue metadata and FixRequest contain identical effective values.
- Existing card clicks use recommendations only in automatic mode; manual target
  edits survive subsequent selection; explicit reset restores recommendations.
- Paste mode cannot inherit the capacity allocator/reference.
- A completed baseline with Fix OOM still has memory_target=false.
- Baseline replays keep “baseline only” labels; capacity calibration is not a
  model score; true new replays retain source and policy provenance.
- API unit integration can capture FixRequest with a stub runner, without
  GPU/API spending. Run focused UI tests, typecheck/build, and an actual browser
  selection/submission inspection after integration. Separate later real-run
  acceptance from those offline checks.

## Observed source anchors

This review inspected `headroom/api/app.py` catalog/submission/queue/replay
paths, `web/src/App.tsx` Home and Replay rendering,
`web/src/data.ts` provenance labels,
`headroom/orchestrator.py` baseline flow,
`headroom/search.py` observed-baseline semantics,
and `headroom/verify/compare.py` final target gate.
Read-only database inspection used SQLite URI mode=ro and query_only=ON;
no stored run was modified.
