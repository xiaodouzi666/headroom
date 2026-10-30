# Snapshot retry preflight root cause — 2026-10-30

Affected run: afa13b5096eb4194a805df299d7d7f93. Its preserved public result says failed/runtime_unavailable. Evidence generation and cleanup completed; the private worker log is empty. The original RuntimeNotReady exception text was not persisted, so the following is a deterministic reproduction under the matching worker limit, not a recovered original traceback.

## Direct observations

A read-only query of that run's existing records found a closed strict_reservation budget run with zero budget attempts and zero Store LLM calls. No ledger, claim, source or output was changed during this investigation. No .env/key was read by the investigator, and no SDK/provider request or GPU operation occurred.

In separate fresh processes, the existing snapshot _worker_limits() applied the same 2,147,483,648-byte RLIMIT_AS and 60-second CPU limit. The existing reviewed profile parsed successfully in both processes.

Without framework-disable switches, Ultra billing.load_auditor() failed with:
`RuntimeNotReady: Reviewed local tokenizer assets or dependencies unavailable`.

A direct PromptAuditor construction then exposed the underlying import failure:
`ImportError: libcusparseLt-294d6944.so.0: failed to map segment from shared object`.

With USE_TORCH=0, USE_TF=0 and USE_FLAX=0 set only in the second investigation process, the same tokenizer auditor loaded successfully under the same limits. Torch was not imported. The tokenizer path imports transformers.PreTrainedTokenizerFast; framework auto-detection unnecessarily loads PyTorch/CUDA libraries into this snapshot-only process. LocalEstimateAdmission.load_auditor wraps ImportError as RuntimeNotReady before any request reservation.

## Reconstructed final-request preflight

The saved evidence JSON/Markdown and visible stack IDs were passed through the current snapshot diagnosis prompt, schema builder, LLMRouter schema prepend and TokenFactoryClient request construction. The SDK entry point was replaced by a non-network sentinel and execution stopped in before_attempt after the read-only admission calculation. All socket connections and DNS lookups were denied. No raw prompt, source or credentials are exported here.

| Field | Observed value |
| --- | --- |
| Reconstructed request SHA-256 | 7ecee1f57a48a56157100301f0363e3df1a0e25aa652a74d7c5e414fa3dfda67 |
| Compact request bytes | 82,513 |
| Native response_format bytes | 4,839 |
| Configured native-format byte limit | 16,384 |
| Local model-template tokens | 28,812 |
| Serialized native-format local tokens | 1,514 |
| Estimated input tokens including existing margin | 34,383 |
| Explicit output cap | 2,000 |
| enable_thinking | false |
| Result with framework imports disabled | accepted_offline |

The reconstructed body hash is not an observed provider wire hash: the real attempt failed before a request-evidence record was created.

## Minimal correction and limits

Set USE_TORCH=0 / USE_TF=0 / USE_FLAX=0 in the trusted snapshot worker before the first transformers import. Keep the 2 GiB address-space limit, CPU deadline, funding checks, source nonexecution, output cap and reviewed tokenizer assets unchanged. Validate this with a fresh-process test; a process that has already imported torch does not test the intended containment path.

This reproduction rules out a schema-size or tokenizer-domain obstruction for the reconstructed request after the import problem is removed. It does not claim a new successful model diagnosis or repair. It also does not establish that no other runtime fault can ever occur. The code already reads its .env directly; adding dotenv loading is not the mechanism needed for this reproduced failure.
