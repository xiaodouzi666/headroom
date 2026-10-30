# R8/R9 Results publication plan — reviewed, not applied

The authoritative source is public-evidence/public-evaluations.json.
The active runtime copy is runs/public-api/submissions/public-evaluations.json.
Both currently have five entries and SHA256
7bb4a68e5798205a65bf912568ecc29ba79d947c0cf654ed7a867d56ce0a3b0e.

The candidate manifest in publication-candidate/public-evaluations.json contains
seven entries in this order: R9, R8, existing R7, R6, R5, Watch and live-demo.
Existing titles, order relative to each other and campaign bytes are preserved.
There is no latest field. EvaluationView.tsx selects catalog[0], so R9 is default.

The candidate was validated using the existing _registry and _campaign helpers
with all seven documents in an isolated temporary directory. No live directory
was changed. receipt.json lists exact source paths and hashes.

For the publishing operator:

1. Recheck candidate receipt, source hashes and the unchanged current registry.
2. Copy only the two new staged campaign documents to
   public-evidence/published-evaluations/r8-20261030.json and r9-20261030.json,
   using temporary files followed by atomic replacement. Preserve all five
   existing documents byte-for-byte.
3. Install the reviewed merged manifest atomically LAST. Do not replace the
   source registry with either single-entry staging registry.
4. Include the two new campaign files and merged manifest in the reviewed
   commit/deployment. scripts/serve_public.py is the existing publication loader:
   it validates every curated campaign, copies documents to the runtime data
   root and copies the manifest last. It is not a standalone merge tool.
5. During the root-managed deployment, check service idle/cleanup state as usual.
   After startup verify GET /api/evaluations has seven entries with R9 first;
   GET /api/evaluations/r8-20261030 and /r9-20261030 return the reviewed nine rows.
   Verify /results defaults to R9 and each historical option still loads.
   Compare installed source/runtime hashes; do not submit a new task.

No separate dedicated merge/publish script was found. The frozen summarize-r8
and summarize-r9 scripts create review-only staging, and scripts/render_evaluation.py
renders Markdown only. Neither is authorization to publish.

Keep headline outcome honest: both R8 and R9 have 0/9 memory targets and did not
meet the six-target threshold. R9's 6/9 valid-correct count is a separate
diagnostic metric. These staged campaigns intentionally contain no overall
acceptance banner. No model/GPU operation or paid invocation is needed to publish.
