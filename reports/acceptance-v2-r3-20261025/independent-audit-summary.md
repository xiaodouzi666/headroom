# Protocol-v2 R3 independent audit — 2026-10-25

The last of three bounded repair iterations after the approved protocol-v2 baseline reached **3/9 targets**, with **4/9 valid correct first causes** and two unknown cause truths. The required six successes and six valid correct causes remain unchanged. No result from another campaign or human control is counted.

| Scenario | Outcome |
|---|---|
| s1 | Needs human input; no selected successful candidate |
| s2 capacity v2 | Selected candidate completed; 22.564 GB remains above the 22 GB target |
| s3 | Target met |
| s4 | Target met |
| s5 | Needs human input; first-cause truth unknown |
| s6 | Bounded diagnosis supplement still lacks sufficient evidence |
| s7 | Needs human input; first cause correct but no successful repair |
| s8 | Target met |
| nanoGPT | Budget protection halted the run on unknown provider charge |

The campaign is **partial**, not a completed acceptance pass. The unchanged reasoning-wire auditor refused it with ValueError: unfinished campaign; this refusal is preserved in [audit status](reasoning-wire-audit-status.json). No campaign status or auditor was edited to manufacture a pass.

The independent audit verified all 305 tested execution source entries and preserved prior runs and charges. Qualification for this source was 3030 offline backend tests; that count is not evidence of model repair quality. The source-bound execution commit was 344cbae4b9b7df37673d2ccab9ed9ad990981e51.

The ledger recorded 59 new attempts with known actual subtotal **$1.20596190** and conservative retained charge **$1.31587236**, including **$0.10991046** of unknown actual costs. Actual total remains unknown. One unresolved request blocks further paid dispatch; there are no pending attempts. Campaign aggregate known_cost_usd=0 does not represent its true known subtotal; the figures here are independently reconstructed from the ledger. All-time retained charge is $9.211075556 within the unchanged $14.17775754 lifetime envelope; same-day charge is $6.133181884 within $9.99964904. These are internal model-budget records, not a provider invoice, live credit balance or card charge.

Private UI/backend tests and a frontend build overlapped part of the GPU campaign before they were stopped. Timing results therefore have a possible host-load confound; they must not establish a speed advantage. No automatic rescore or rerun was performed.

Evidence: [execution receipt](execution.json), [lossless public audit projection](independent-audit-public.json). The private original audit SHA is fd77ff7590e760d61341a898f9db2d873e7f2d9b5f1a30eecd15f3347c7c4bfd; its source-hash mapping was converted to an array for publication with a verified exact JSON round trip.

Frank subsequently withdrew the Replay product feature (former T3.3). Its removal is product maintenance, not an acceptance success, and retains historical run files. Public deployment remains deferred until Frank's final confirmation. Main evaluation, policy comparisons, ablations, submission and judging availability are not established by this campaign.
