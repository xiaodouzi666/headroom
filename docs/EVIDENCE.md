# Evidence packs

`headroom evidence <run_id>` builds a bounded Markdown prompt, full analysis JSON
and a PNG timeline from a Lab run. A full run-directory path is also accepted.
The default prompt budget is 150,000 tokens, measured with `cl100k_base`.
No model or research service is called. Passing artifact/unit checks does not
by itself pass the scenario-specific T1.2 acceptance gates in docs/PLAN.md.

```sh
source scripts/env.sh
uv run headroom evidence /path/to/a/headroom/run --budget 150000
```

## Reconstructed memory

The analyzer replays allocator events and reconstructs physical block sizes. In
PyTorch 2.5.1, ALLOC/FREE traces carry requested bytes, while allocator counters
measure physical block sizes, including alignment and unsplit slack. Summing
requested sizes is not a valid allocated-memory curve. The replay applies the
native allocator's rounding, segment boundaries, splitting and pending-free
behavior, then checks its terminal blocks and peak against the captured evidence.
The relevant implementation is
[PyTorch v2.5.1 CUDACachingAllocator](https://github.com/pytorch/pytorch/blob/v2.5.1/c10/cuda/CUDACachingAllocator.cpp#L1412).
Unsupported policies, missing history and inconsistent counters are reported;
they do not silently become exact peaks.

Peak composition uses blocks alive at the reconstructed peak. Terminal snapshot
blocks are used for validation and terminal free-block statistics, not substituted
for peak blocks. Stacks are grouped by complete signatures before representative
frames are selected for display. Classification is an explicit heuristic:
AdamW moment initialization is optimizer state; foreach update intermediates
remain temporaries. Unknown allocations remain unknown.

A high reserved-minus-allocated indicator is a cache-gap proxy required by the
original acceptance plan. It does not prove harmful fragmentation. Confirmation
and supporting evidence are separate fields. No code interprets that proxy alone
as a demonstrated OOM cause.

## Time and source evidence

The timeline's horizontal axis is allocator event index, not elapsed seconds.
OOM markers preserve their actual event indices. New captures record optimizer
hook wall_time_us; where allocator time_us is available, step markers map to the
last allocator event before the hook. Old captures without timestamps show an
explicit limitation instead of invented step positions.

The prompt includes the captured main Python script and discovered local modules,
with original line numbers. Every included file is checked against the run's
source hash. Path traversal, sensitive filenames and symlinks are rejected.
Static source observations such as `total_loss += loss` are labeled as static
patterns; they are not inserted into runtime allocation stacks.

## Budget and files

Source code uses at most 30% of the requested prompt budget. When the whole prompt
is too long, the renderer reduces stack/hot-path counts, then non-hot source,
then timeline rows, retaining core measurements and limitations. It counts the
final Markdown, not a character heuristic. Budgets too small to preserve the
minimum evidence produce an error. Full structured analysis is kept in JSON
outside the prompt budget; trimming the prompt does not discard the raw captures.

The host reads a bounded regular JSON export with no symlink following. It never
unpickles target artifacts. Snapshot JSON is limited to 512 MiB; source traversal
is limited to 64 Python files and 4 MiB total. These operational read bounds are
explicit errors/limitations, not substituted measurements. Tokenizer data is
cached under the project .cache/tiktoken directory.

## Validation

- `tests/test_evidence_analysis.py`: native-block replay, exact peak versus terminal
  composition, missing history, aggregation, lifetimes and timestamp alignment.
- `tests/test_evidence.py`: real token limits, source lookup/hash/path boundaries,
  rendering and retained full analysis.
- `scripts/verify_evidence.py`: the saved real s1/s2/s4/s5 acceptance fixtures;
  every original threshold is checked without relaxation. Its report includes
  failures and does not automatically mark T1.2 accepted.

Current scenario results are recorded in PROGRESS.md, docs/RESULTS.md and the
unique reports/evidence-acceptance-*.json reports.
