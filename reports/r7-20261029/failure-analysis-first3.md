# R7 first-three failure analysis — 2026-10-29

Read-only analysis of the first three completed cells in
runs/final48-f3/execution-20261029-v1/campaign.json. No source, request, score,
claim, ledger or preserved run artifact was modified; no model/GPU call or retry
was performed. This is not a re-score or the final R7 campaign outcome.

## Findings

| Scenario / run | Observed stopping chain | Output-cap evidence | Classification |
| --- | --- | --- | --- |
| s1 / e82cd9646adc44fabb86270591701803 | Round 1 diagnosis valid and ready. Patcher attempt 1 had overlapping source edits; attempts 2–4 removed the outer training-update loop and were rejected as TRAINING_TRUNCATED. Round 2 ultimately returned valid needs_more_info. | Round-2 first response hit 2,000 tokens with finish_reason=length; the bounded retry produced a complete 1,722-token response. Round-1 diagnosis used 881 tokens. | Genuine bad patches; one recovered truncation; genuine missing update observations plus a demonstrably mistaken source-reading claim. |
| s2 / 6330dcf4e44b4accb09b73110dda0183 | Valid diagnosis, no schema/reference issues, needs_more_info=true before patching. Requested input/update association and effective batch observations. | Complete valid 1,900-token response; no recorded truncation/validation failure. | Capture coverage limitation, with additional model caution. |
| s3 / ce2e4bf037a84b349d178c5bd661230b | Proposed no_grad for evaluation, but also an alternative checkpoint/microbatch plan. Both responses claimed only alternative evidence blockers while setting needs_more_info=true; final response remained invalid. | Complete 1,596- and 1,567-token responses, no recorded truncation. | Model ignored supplied runtime facts and violated the stated dependency contract. The application's top-level stop reason also obscures this validation failure. |

The authoritative diagnosis files are under:
runs/final48-f3/execution-20261029-v1/jobs/<run_id>/rounds/<round>/diagnosis.json.
Per-round verification-feedback.json records whether any candidate actually ran.

## s1: rejection was correct; some second-round uncertainty was avoidable

The retained final patch removes:

    for step in range(1, args.steps + 1):

and substitutes one accumulation loop with one optimizer.step(), retaining an
undefined step variable in its emitted record. It therefore does not preserve
20 optimizer updates. This is not evidence of a false-positive policy rejection.

Exact patch:
jobs/e82cd9646adc44fabb86270591701803/rounds/01/patches/patch-engine-d3e446342f724a00b8a01f4acb30a47d/attempt-4/patch-e8314e0f1cec498daf2f591590c67f88/patch.diff
(relative to the execution directory above). attempts 1–4 have their original
reason and policy report in attempt-1.json through attempt-4.json.

The second-round model said hidden and block were undefined in ResidualMLP.
The exact request already included numbered source lines 27–29 defining both:
hidden = inputs; for block in self.blocks; hidden = block(hidden). Source SHA
668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28.
This premise is contradicted by supplied text, not by newly inferred ground truth.

Other requested facts were genuinely unobserved: the source-bound initial inputs
[32, 2048, 256] were supplied, but the baseline OOM occurred before the first
optimizer update. The request correctly recorded logical_updates.status =
not_reached and zero observed updates. Initial shape alone does not establish
the complete update contract or numerical equivalence.

Later minimal work: constrain edits to preserve the original outer update loop
and supply exact failed structural checks to the patcher; correct literal source
premises using the delivered line identities. Do not weaken TRAINING_TRUNCATED,
invent observed updates, or call this a successful repair.

## s2: explicit instrumentation gap, not dropped successful observations

The retained baseline completed 20 updates. Its pairing_capture nevertheless says
complete=false, updates=[], source_contract.supported=false, reason:
source outside pinned s1/s3/s4 AST contracts. headroom/verify/pairing.py:20 defines
those supported contracts; headroom/solver_context.py:256–264 therefore produces
runtime_input_observations.status=unsupported. This is a confirmed coverage gap,
not a serializer dropping a valid s2 pairing capture.

The baseline stdout does contain a scenario_start record with batch=24, width=2048,
depth=34 and sequence_length=128. That emitter record was not exposed as a
source-bound optimizer-input observation in the solver request. It is weaker than
the requested per-update tensor identity and cannot retroactively create it.

Evidence:
jobs/6330dcf4e44b4accb09b73110dda0183/lab/3822a1d44c2543239ce69b3af38bbc38/result.json
(pairing_capture), the adjacent stdout.log, and rounds/01/diagnosis.json.

Later minimal work: add a separately reviewed s2 observational contract/capture
adapter and expose accurately scoped existing runtime configuration where safe.
Re-test identity and update association offline before any separately authorized
rerun. Do not mark the old capture observed or assume source defaults are runtime proof.
The proposed optimizer-loop change might avoid batch prerequisites, but its
numerical/throughput acceptability was not measured in this run.

## s3: the requested exact fields were already sent

Both actual diagnose requests supplied:

- runtime_input_observations.status = observed;
- optimizer_input_name = train_inputs;
- effective_batch_per_optimizer_update = 1;
- observed_optimizer_updates = 20 and one training forward/backward per update.

These values appear both at the relevant top-level observation fields and in
logical_updates. The complete 137-line source was supplied; its SHA is
7fedcae13989b309cc5a034e62284094829057654aebb2e716c3413dfb0fea67.

The model nevertheless requested the optimizer input as missing. Its declarations
used alternative_plan with blocked_plan_ids=[fix_microbatch_accum], while the
delivered prompt explicitly requires alternative/overall scopes to have empty
ID lists. It also treated only alternative prerequisites as a blocker for the
current no_grad proposal. headroom/evidence_blockers.py:270–283 and :337–349
correctly rejected these declarations. There is no evidence here that those
validator errors were false positives.

Confirmed reporting defect: headroom/orchestrator.py:722–745 checks
diagnosis.needs_more_info before classifying an invalid checked diagnosis.
Consequently s3's top-level reason says to restart with new evidence even though
the exact observations were already provided and checked.valid=false.
The original issues remain preserved in diagnosis.json; nothing was incorrectly
accepted. A later minimal correction should classify exhausted invalid output
separately, preserving the same fail-closed behavior.

A second narrowly scoped improvement is to advertise exact observed child-field
references in the availability catalog. Currently only the parent and selected
subcontainers are advertised; headroom/evidence_blockers.py:311–316 deliberately
does not infer child presence from a visible parent. Exposing the actual
optimizer_input_name/effective_batch fields would allow deterministic literal
contradiction feedback without treating presence as proof of all mathematical
preconditions. This is a coverage improvement, not permission to clear a genuine
needs_more_info flag automatically.

## Historical s3 comparison and limits

The successful preserved run 84f929ba8ace49b3829df6455419641d used the same source
SHA and also received observed runtime input/update data. Its valid initial
diagnosis proposed only evaluation no_grad and no evidence requests:
runs/evaluation/live/20261027T022818939585Z-151818b1/jobs/84f929ba8ace49b3829df6455419641d/rounds/01/diagnosis.json.

Its request asked for thinking=true and 16,384 maximum completion tokens; observed
usage was 6,636 completion tokens including 6,054 reasoning tokens. R7 used the
approved thinking=false / 2,000 policy. This is an observed protocol difference,
not a controlled causal result. Current s3 responses did not hit that output cap,
so blaming truncation for s3 is unsupported. Different capture content and model
sampling also prevent attributing the outcome solely to thinking mode.

Request evidence was read in SQLite read-only mode from runs/headroom.db,
llm_calls IDs 777/782/783 (s1), 785 (s2), 787/788 (s3), and 766 (historical s3).
Only selected non-secret facts are summarized here; raw prompts, responses and
provider payloads are not exported. The private call IDs and immutable per-run
files allow follow-up checking without changing the ongoing fixed 12-cell study.


## Deferred reporting-only patch and focused checks

Do not apply while the fixed campaign is running. The smallest proposed change
is within the existing not-ready branch of headroom/orchestrator.py:722–749:
when checked.valid is false and the existing bounded diagnosis attempt is ending,
record a distinct validation-failure reason and issue codes before considering the
model's needs_more_info flag. Keep status needs_human, the same stopping behavior,
all original diagnosis artifacts and the existing response/round limits. The
message should ask the operator to inspect validation issues rather than imply
that new external evidence is always missing. Do not clear needs_more_info,
promote any step, rewrite old reports or add an extra diagnostic request.

Focused offline checks should cover:
1. Invalid diagnosis + needs_more_info=true + exhausted bounded supplement:
   validation-specific stop reason/message; original issues retained; zero patch
   applications and no extra model request.
2. Valid diagnosis + needs_more_info=true: existing additional-information reason
   remains intact; no patch execution.
3. Invalid diagnosis without needs_more_info: preserve the existing bounded
   supplement/round termination behavior, not a newly introduced retry.
4. Valid ready diagnosis: normal patch path unchanged.
5. Loading the preserved R7 s3 report still yields its original saved reason and
   invalid issues; a future renderer may explain both without overwriting history.

This classification patch addresses a confirmed diagnostic-reporting defect.
It does not assert that s3 would repair successfully or that its alternative
checkpoint plan is admissible.
