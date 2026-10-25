# Protocol-v2 repair r2: independent final audit

The fixed-nine campaign did not pass: target **3/9**, independently valid correct first cause **4/9**, with two unknown truths. Both original minimum-six requirements remain. The campaign's raw category-match summary reports six matches among seven known labels; two of those are not accepted as valid diagnoses by the independent audit. Do not substitute that raw label-match count for the audited gate.

Execution source: `3e8281e1a344a469b025133897aad4d1c6c23e40`. Campaign: `runs/evaluation/live/20261025T104308792414Z-88c59353/campaign.json`, SHA256 `00c984eaf91bf76b244d3f1aa95752be7c392198832300eafffe4d8247d7c0e8`. It finished all nine rows in 1593.647 seconds with no financial halt; campaign process exit 1 is retained. The nine CLI chains are complete: three exit 0, six exit 78.

All 297 tested/reviewed/current source entries match, with no artifact read errors or changed artifacts. Full guarded regression passed 2,825 tests in 742.79 seconds; frontend 73 tests and build passed. The initial interrupted full failure (one obsolete token-cap fixture) and focused 81 passing follow-up remain in the report directory.

| Scenario | Final status | Target | Valid correct cause | Run ID |
| --- | --- | --- | --- | --- |
| s1_batch_too_big | completed | yes | yes | adc7e667237f46a5a9f71a619fab5c31 |
| s2_capacity_v2 | needs_human | no | no | 4e558dd64eb34a3a949490b6e15ad465 |
| s3_eval_no_grad_missing | completed | yes | yes | c70202edcf304291855328cce223a5df |
| s4_loss_accumulation_graph | completed | yes | yes | 100a6e2f2f2f462584e3d3a4fe0cd729 |
| s5_fragmentation_varlen | needs_human | no | unknown | 174e8c3851d54317b1bd7eb8de75edb7 |
| s6_full_vocab_logits_fp32 | needs_human | no | no | e3005dc58ffd4a46aa8a9032807f80c1 |
| s7_frozen_params_optimizer_state | needs_human | no | yes | 2232ff4dd65340f9b1ca2641677469f8 |
| s8_two_models_resident | needs_human | no | no | b6f0085eb8494cef9f6d78a3ed6d45e7 |
| nanogpt | needs_human | no | unknown | cc76ed8d31b246ae96cff4593a39dedf |

## Charges and remaining funded limits

56 additional settled attempts: known actual subtotal **$1.26789928**, plus nine unknown charges retained at their verified upper bounds **$0.02688174**, yielding conservative **$1.29478102**. The exact actual total remains unknown. All original 97 runs / 517 attempts are unchanged; the shared ledger now contains 106 closed runs / 573 settled attempts, with no open reservation or halt.

Runtime conservative total is **$7.895203196** against the unchanged funded lifetime partition **$14.17775754**. Lifetime remaining is **$6.282554344**; same UTC-day remaining is **$5.182339516** against **$9.99964904**. Subsequent dispatch uses the smaller current limit and full request reservations. The retained external **$1.82224246**, including unknown **$1.049344**, remains accounted for. No recharge, unknown-debt release, history exclusion or new pool occurred.

All nine runs remained within their nominal $0.60 actual-usage limit in this campaign; the maximum was s2 at $0.36627002. This observed result is not a proof that actual-usage stop mode can never cross its nominal threshold on a final request. Lifetime/day full-request guards remain the hard funded bounds.

## Diagnosed follow-up work

s1 now has a real model-generated successful candidate and an independently executed baseline-derived checkpoint reference; it is not scored from the earlier human control. The selected candidate completed 20 updates at 14.297204736GB versus 24.750424064GB before. The recorded comparison basis is the first five backward scalars from that reference, with zero observed delta and unchanged original tolerance; it does not claim a stronger numerical comparison than the saved artifact.

s2's patch artifacts separately prove 11 of 12 responses ended in length truncation, often using the full 4000 tokens for reasoning. The final complete patch had an unquoted flag parsed as an undefined Python name, which the existing syntax compilation did not catch. s5/s6 request future verification results before a candidate exists. s7's rejected freeze changes training behavior; its later reference questions also reveal ambiguous default-fallback presentation. s8 has unresolved invocation/policy interpretation and invalid dependency metadata. nanoGPT remains unsuccessful. All failed candidates, rejected responses and charges stay in their original runs.

Wire evidence confirms 18 Ultra diagnostic requests with thinking enabled and 16384 completion cap, and 23 Super patch requests with thinking enabled and 4000 cap. Store lacks finish_reason: 15 patch outputs reaching the cap is not by itself proof of truncation. The stronger s2 claim above comes from separately saved patch response artifacts.

The next bounded repair iteration will address supported generic defects. No threshold, old result, or unknown truth is changed here. The existing Phase2 driver remains an unexecuted draft because this MVP result fails.

## Audit artifacts

- [Independent audit, reversible public projection](independent-audit-public.json)
- [Reasoning wire audit, reversible public projection](reasoning-wire-audit-public.json)
- [Independent finance review](finance-independent-review.json)

Raw audit bytes remain private 0600 at their original paths. Their SHA256 values are `7cf8dc9ac127bc904c3650b58ff0c76646c764214ab81b9bdd128e23725d603f` and `0cbfd42ee1ca2296a0df4cf470fbaafd9122e3a97f18b84e265b3ab9538a08c3`; both public transformations round-trip to the original JSON. Canonical PLAN, historical manifests, previous scores and all controls remain preserved.
