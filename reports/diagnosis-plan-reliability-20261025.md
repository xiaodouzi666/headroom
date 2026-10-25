# Diagnosis plan reliability: bounded output repair — 2026-10-25

This change starts from main `69144d1`. It addresses the observed gap between
reading an invocation correctly and producing an executable, policy-permitted
plan. No provider request or GPU execution was made for this implementation.
Historical v7 results and the four-call diagnostic probe remain unchanged.

## Evidence and applicable public designs

The final nanoGPT probe read the retained batch and accumulation values correctly,
but copied script argument indices into the execution argument namespace. It
also proposed a forbidden sequence-length reduction. v7 s1 and s6 had separate
model-change and precision-policy violations that previously received no bounded
correction opportunity. Those observations are output-contract failures; they
are not proof of an otherwise successful GPU repair.

Primary sources checked directly:

- [JSON Schema enum](https://json-schema.org/understanding-json-schema/reference/enum)
  specifies finite allowed values. Here it constrains host-issued reference IDs,
  not numerical conclusions or free-text plan semantics.
- [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json)
  documents schema-based structured responses and model-dependent support. The
  application still validates the response locally and checks evidence/policy.
  Schema validity does not establish scientific correctness.
- [Anthropic effective tools](https://www.anthropic.com/research/writing-tools-for-agents)
  describes clear names and contracts, concise relevant output, actionable
  validation feedback and outcome-based evaluation. We apply those interface
  principles to the existing Nemotron router; Anthropic's measured outcomes are
  not evidence that these changes improve Nemotron success rates.

## Implemented contracts

1. The bounded lexical view assigns an explicit `source` and copyable
   `evidence_ref` to every displayed, non-redacted token. Optional
   `invocation_refs` are constrained to precisely those IDs by the request
   schema. Repeated options retain distinct indices; unsupported CLI syntax has
   a literal identity without invented parser semantics. References omitted by
   the 4 KiB view or hidden by redaction are not advertised. The execution object
   remains capped at 16 KiB and combined solver context at 64 KiB.
2. Host reference resolution is reported separately from strict legacy literal
   claims. A correct reference cannot repair a contradictory legacy claim. Empty
   references remain unverified; resolved references do not prove target parsing,
   effective configuration, a plan's use of the value, or mathematics.
3. Existing diagnosis validators now provide bounded, actionable JSON paths and
   error rules for policy, stack/reference, shape/type and savings failures.
   All errors share the existing `max_supplements` allowance. No new retry pool
   or permission is introduced. Output diagnoses are never silently rewritten.
4. Router schema mismatch can be corrected only when a complete JSON response
   and an existing supplement slot are available. The full post-response
   validator also runs, so correcting a reference cannot hide a policy error.
   If the allowance is zero or exhausted, the original response-validation
   exception still propagates: historical failed-response and scoring semantics
   stay intact. Invalid JSON, filtering, truncation, network and budget failures
   do not enter this repair path. Per-call request audit and billing hooks are
   unchanged.
5. Diagnosis and patch instructions separate source-established mathematical
   prerequisites from future measured outcomes. Missing future timing/memory
   measurements alone are not a reason to block an otherwise justified candidate;
   unknown input ranges, loss/update semantics, precedence or permissions remain
   real blockers. The host never forces `needs_more_info=false`.

## Verification and limits

The focused tests exercise the real router/SDK with HTTPX MockTransport: wrong
reference, then a forbidden plan, then a compliant response; persistent failures
at existing limits; genuine evidence gaps stopping without extra calls; all
postvalidators running after schema correction; raw failure preservation at
exhaustion; schema error data excluding invalid values/unknown field names;
secret/truncated/omitted token handling; and bounded context/error feedback.
Each mocked provider response retains its ledger entry. There is no live spending.

Final focused run: **333 passed in 48.11 seconds**, covering diagnosis, schema,
invocation/runtime context, request audit, admission, diagnosis acceptance and
orchestration. Ruff passed on all changed Python files; `git diff --check` passed.
The new bounded-repair file contributed 23 tests at that checkpoint. Earlier historical acceptance
failures exposed a changed failed-response boundary; production was corrected and
the original acceptance assertions were retained.

The change does not resolve s2 capacity, s4/s7 numerical pairing, or genuine s5
allocator-evidence gaps. It supplies no fixture-specific repair answer or manual
candidate. Only a subsequent bounded, fully audited diagnosis → patch → GPU →
numerical-verification run can establish improved repair success. No new success
rate is claimed by these offline checks.


## Additional training-update invariant

The diagnosis and patch prompts now explicitly separate evaluation mode from
freezing. [PyTorch autograd documentation](https://docs.pytorch.org/docs/2.14/notes/autograd.html#evaluation-mode-nn-module-eval)
confirms that `eval()` affects module behavior and is independent of disabling
gradients. File/comment labels do not authorize changing the set of trainable or
actually updated parameters. The default contract preserves both sets and their
update/state/scheduler semantics; precision permission does not authorize
removing parameter updates. This adds no scenario name, control implementation or
prescribed optimizer strategy to a model request.

The [official optimizer-in-backward tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html)
was also checked. It addresses gradient lifetime and optimizer intermediates,
with configuration/scheduler integration caveats. It is a possible research
source for a model, not an automatically applicable repair or evidence that a
specific training loop is equivalent. No implementation from our manual controls
was inserted into diagnosis or patch context.


After the additional training-update prompt invariant, two contract tests were
added. Final diagnosis/orchestrator/Watch unit selection: **73 passed, 12
real-CPU-Docker/timeout selections deselected**; Ruff passed. The bounded-repair
file now contains 25 tests. These checks do not establish live model success.
