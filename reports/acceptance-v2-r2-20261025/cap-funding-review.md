# Ultra completion cap, funding partition and standalone probe retirement review

The preparation and tests below ran in an isolated server copy. The root agent subsequently applied the two reviewed patches, closed the seven known standalone paid entrypoints, and created a distinct r2 profile. The original profile and ledger history were retained; funding-independent-review.json records the independent read-only check. No model or GPU request was made by this preparation/review.

## Scope and bounds

The original PLAN T1.4 does not specify an 8192 output-token acceptance limit. Its actual Ultra single-call cost ceiling of $0.35 remains; T1.5 explicitly limits Super patch completion to 4000 and that is unchanged. The proposed diagnosis constant and prompt increase to 16384 total completion tokens, including hidden reasoning and final JSON. The standalone diagnosis adapter already imports this constant and rebuilds its exact prepared payload; no duplicate adapter production edit is needed. Existing prepared bundles remain invalid after source pins change.

Official endpoint documentation: https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md . The root reviewer retrieved the 44081-byte document with SHA c5da9a21ba477a377b2f4e533e4288b6cedb43a4a522317b065bbe9057dac9a8. It defines max_completion_tokens as visible plus reasoning tokens, with integer minimum 0 and no explicit maximum in this generic schema. max_tokens default 8192 is not a maximum. This does not prove that the specific model accepts or usefully completes a 16384 request: none has been sent. Generic reasoning_effort and NVIDIA NIM reasoning_budget are not enabled.

At the existing verified Ultra 1048576 prompt-token ceiling and $1/$3 per million input/output prices, every POST must reserve $1.097728, up from $1.073152. The difference is $0.024576. A 150000-token actual uncached input plus all 16384 output tokens would cost $0.199152, but actual input/usage and the unchanged $0.35 acceptance check remain authoritative. Per-run $0.6, 480 seconds, full provider-bound admission, SDK retry policy and all pass lines stay unchanged.

A new reviewed profile is required; the old profile's 8192 ceiling rejects 16384 before POST or charge. Settlement releases unused reservation, not a payment/card refund. A fixture with all 16384 tokens consumed by reasoning and no JSON still settles its bill and fails response validation. Reaching the cap alone does not establish finish_reason=length when the particular persisted artifact lacks finish_reason.

The constant is role-wide: default diagnose routes to Ultra, but later full_super diagnosis ablation would also inherit 16384 and correctly fail the old Super profile ceiling. This patch does not establish that ablation's live qualification or raise the Super patch 4000 gate. Its later protocol must be explicit.

## Validation history

All private tests used the frozen full_guarded.py runner, which denies real credentials, profile/ledger/Store reads, network and GPU. The first cap-focused run retained 174 passes and one failure because a historical provider-overflow fixture still reported 8193; the second run preserved its assertions and changed the fixture to 16385, yielding 175 passes. A separate dependent group initially had 84 passes and one analogous old 8193 overflow fixture failure; with only that fixture adjusted, 85 passed. The full original logs are retained. The isolated ledger draft has 17 synthetic passes.

ultra-16384.patch has eight files and git apply --check succeeded without applying. validation.json binds the base/source hashes and logs. The independent private ledger_state_r2.py copies the old full-history/canonical/unknown/open/halt checks, with LIFETIME_POOL=14.17775754 and DAILY_POOL=9.99964904. It does not mutate any old helper global or authorize funding by itself.

## Funding boundary

The zero-sum proposal keeps total work commitments at $16 net: $14.17775754 runtime plus $1.82224246 external already charged or conservatively retained. The latter includes the $1.049344 unknown external request, which is not released. The original gross equation is 16*1.21 +0.89 buffer +10 judging reserve =30.25 gift. Trial credit and the newly displayed billing balance are not added. Retiring the old external unused allocation is a required separate gate before the new runtime profile activates.

The read-only post-r1 review is reports/acceptance-v2-r1-20261025/finance-independent-review.json. All old 88/488 rows match their frozen projection; 9 runs and 29 calls were added, all settled with one Store row each and attempt=1. New known actual subtotal $0.79450272, conservative $0.79925580; unknown total remains null. Runtime conservative lifetime is now $6.600422176. Under the old pool remaining lifetime is $3.399226864, daily $6.477120536. Under the proposed zero-sum lifetime pool, remaining lifetime would be $7.577335364; daily remains $6.477120536. No real funds or ledger values were changed by this calculation.

## Standalone probe retirement

scripts/probe_models.py and its cached historical copy do not consult allocation.json; CLI budget/available-credit flags alone can instantiate their own Budget. A no-switch refusal gate before key, pricing, output creation and transport must close the non-catalogue CLI path. Offline dry-run and official catalogue GET remain usable. Historical low-level pure functions remain for offline format/accounting regression, so this is a closure of known execution entrypoints, not a claim to sandbox arbitrary Python code. Cached direct-paid scripts must retain their original bytes and SHA in an archive, then receive refusal stubs at their old paths. Future paid capability checks use the shared runtime ledger.

## Delivery evidence

The root agent applied ultra-16384.patch (ef1bb740b3eaaab4c9245345abd1442b5ef6afa821e24b3fdda73135c96889db) and standalone-probe-retirement.patch (661c72cce323c752cc06a647e5015f9e86e88b850411962e741e1a6d422ed851). Retirement validation: 165 guarded tests passed; Ruff check/format and git apply --check passed. Its six new negative cases cover fully armed legacy CLI flags and mixed catalogue/paid plans. An existing historical catalogue-adapter test bypasses the new CLI gate only under a GET-only in-memory HTTP fixture, retaining its fee-drift rejection assertions. The independent peer review found no blocker and affirmed the CLI-versus-arbitrary-Python boundary.

The cache inventory scanned 24353 regular UTF-8 Python files. Six known cached standalone Budget/HTTP probe entrypoints were archived byte-for-byte and replaced by refusal stubs by the root agent. The five unreadable files were intentional non-UTF8 test fixtures; runtime client libraries and third-party client implementations were not retired. A separate symlink-alias check found no aliases into project probe scripts. The public closure receipt includes the tracked CLI as the seventh entrypoint.

Test logs below include the first failed runs as well as subsequent passes. The two failures were observed fixture drift after raising the completion cap, not production financial stop failures: an 8193 output was no longer over-limit. Each fixture now reports 16385, preserving the original fail-closed assertions. No pass line or financial assertion was weakened.
