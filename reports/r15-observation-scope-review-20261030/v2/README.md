# Applied scope clarification v2

Root reviewed and authorized the initial three-wording-location proposal. This
version keeps the compact body at80 lines, updates the one old exact-text test
assertion, and adds two independent scope/range negative tests. It is applied and
frozen for final root review; no commit/deployment/model/GPU call was performed.

Only two Python string constants change: an availability check makes no runtime
determination and does not negate independent scoped observations. The original
`runtime_values_verified=false` flags, validity rules and readiness rules remain
unchanged. AST comparison with string values removed is identical. The compact
prompt explicitly says non-source evidence refs have both line bounds null.

Guard v5 focused checks: **148 passed in3.48s**. The independent scope case keeps
an observed runtime sibling and its20-update observation unchanged while the
availability producer remains non-verifying; its genuine unknown stays
needs_more_info=true/not ready even after the reason declaration is corrected.
The runtime-reference/source-range case still fails the original validator.
Actual wire/compact/ordinary/study/snapshot compatibility and bounded retry tests
also pass. Ruff check and format check pass. Original30a proposal and real R15
wire excerpts remain retained unchanged in the parent report directory.
