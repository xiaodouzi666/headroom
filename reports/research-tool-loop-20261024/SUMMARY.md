# Native Tavily tool loop — offline handoff

Base: 20e9956. Source and tests are frozen; no commit or push was performed.

Production now asks Super to choose native tavily_search / tavily_extract through
the existing router. One instance persists across repair rounds, with five
logical model turns and four tool dispatch slots. ResearchSession separately
keeps its original persistent four-method-attempt ceiling and cache.

144 related tests passed in 15.68 seconds; scoped Ruff and git diff --check passed.
The independent runner installs DNS/INET and real-project-.env denial before
test imports. Real SDK/router/budget callbacks use MockTransport; Tavily replies
and Lab metrics are fixtures. 429/503 unknown billing permits one mock HTTP
attempt and blocks the retry before dispatch.

The saved three-round fixture used five model calls, four tool dispatches and
three fake Tavily method calls, with one actual local cache hit. Its research
correctly stays partial: the allocator topic did not extract allocator docs and
the last topic had no model turns left. Its synthetic target_met value is not
live model/GPU acceptance.

See receipt.json for exact source/log hashes and the archived report/transcripts.
No service calls, GPU execution, real credentials, profile updates or additional
spending authorization were involved.
