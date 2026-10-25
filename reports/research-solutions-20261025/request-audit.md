# Prepared model request evidence

Source: [HTTPX request event hooks](https://www.python-httpx.org/advanced/event-hooks/),
retrieved 2026-10-25. HTTPX defines a request hook as running after request
preparation and before network transmission. This is a local preparation boundary,
not proof that the provider received or interpreted a body.

The client now hashes the exact SDK-serialized body in that hook, including the
router schema message, merged reasoning fields, tool declarations, and every
supplementary turn. The runtime persists bounded body evidence on the reserved
LLM attempt before transport. Store only permits one capture on a pending attempt
with matching role/model/attempt; final settlement retains it and is unchanged.

No headers, credentials files, or environment are logged. The stored body copy is
limited to 256 KiB and redacts the known runtime API credential, named secret fields
and bearer values. The exact raw-body hash remains separate from the stored-copy
hash. Arbitrary secrets inside source code cannot be identified in general; this
is an explicit scoped sanitizer, not a claim of comprehensive secret detection.
Oversized/invalid bodies retain hash, byte count and explicit omission status.

A local audit-storage failure prevents transport. Existing conservative billing
logic still retains the reserved unknown amount; no new cancellation or free-call
assumption is introduced. Historical requests are not reconstructed as new evidence.

The evaluator's initial-message copy now includes invocation context, candidate
evidence and verification feedback. It remains labeled pre-router, non-wire, and
excludes subsequent turns; the actual prepared body evidence is in
llm_calls.request_evidence.

Offline SDK MockTransport tests compare captured hashes against actual transport
bytes, cover schema/reasoning/supplement context, retries, runtime ledger linkage,
redaction without modifying dispatch, immutable capture, size/invalid cases,
audit failures and evaluator copy parity. No paid invocation is claimed by these
tests.
