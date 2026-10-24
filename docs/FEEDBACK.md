# Tool feedback

Token Factory observations remain pending credentials and credit confirmation.
Tavily observations below come from the authorized live run on 2026-10-24.


## TAVILY-001 — Search depth does not pin the PyTorch version

Observed 2026-10-24 00:57 UTC using tavily-python 0.8.5. For the same query
`PyTorch 2.5 torch.utils.checkpoint use_reentrant False`, with max_results=2 and
the same official/GitHub domain restriction, both basic and advanced returned
the same two URLs: PyTorch main checkpoint documentation and the main-branch
checkpoint.py source. Basic took 2.932 seconds and reported 1 credit; advanced
took 4.297 seconds and reported 2 credits. Advanced snippets contained 1,461/2,300
characters versus basic's 1,357/1,445. These are single observations, not a latency
benchmark or proof that one depth is generally more accurate.

Implication for Headroom: a version number in the search query does not establish
that the result applies to that installed version. A version-sensitive repair
must inspect a pinned documentation/source URL. More text or a higher score alone
does not establish better evidence. This observation does not change the plan's
research strategy or acceptance criteria.

Evidence: `reports/probe-tavily-20261024T005720856027Z-332161bd.json`, operations
`search_basic` and `search_advanced`. Only metadata, shapes and content lengths
were retained; no raw page content or credentials were saved.

## TAVILY-002 — Pinned extraction works; zero reported credits is not a free tier claim

In the same live run, basic extraction returned the exact requested PyTorch 2.5
checkpoint URL and pytorch/pytorch issue 102223 URL. Their nonempty raw_content
lengths were 17,645 and 14,925 characters, with empty failed_results arrays.
Observed client elapsed times were 1.335 and 0.148 seconds respectively. Both
responses supplied title, URL, raw_content, images, response_time, usage and
request_id fields; images was empty. Each response reported usage.credits=0.

Implication for Headroom: validate the requested URL, nonempty raw_content, and
failed_results instead of relying on an HTTP success alone. Keep API-reported
usage separate from account billing: this run reported 3 credits in total, and
the refreshed free-plan account counter independently moved from 0 to 3/1,000.
The zero extract values do not prove that later extraction is free; the account
page prices basic extraction in groups of five URLs. The historical issue is an
extraction fixture and does not establish its applicability to installed PyTorch.

Evidence: `reports/probe-tavily-20261024T005720856027Z-332161bd.json`, operations
`extract_checkpoint` and `extract_issue`, plus
`reports/tavily-account-after-20261024T005808Z.json` for the account observation.
