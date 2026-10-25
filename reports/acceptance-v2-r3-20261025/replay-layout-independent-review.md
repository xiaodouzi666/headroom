# Replay path compatibility: independent review

Reviewed the frozen candidate patch identified in replay-layout-independent-review.json. No blocking finding.

The production change is one exact fullmatch allowlist entry for the actual PatchEngine nested patch.diff layout: rounds 01–06, a lowercase 32-hex engine directory, attempts 1–4, and a lowercase 32-hex patch directory. Existing single-layer paths remain supported. Candidate source, raw responses, credential files and pickle artifacts are not newly admitted.

The original secure file reader, symlink refusal, 64 MiB file / 128 MiB aggregate bounds and report/DB/application/capture/event bindings remain unchanged. New tests include invalid layouts, symlinked path components and evidence mismatches. The implementer reports 88 focused tests; this independent review did not repeat them.

This review invoked no curation, API or GPU execution and wrote no database or production file. Eligibility to display an existing repair is not a new execution or acceptance success; saved failed/unknown states remain unchanged.
