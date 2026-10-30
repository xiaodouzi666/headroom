# Scratch backpressure independent review

PASS. The only executable AST change is ReferenceScratchBroker._accept. Acquiring the worker permit before accept leaves a legal client's next request in the bounded listen queue while previous replies have arrived but worker cleanup is pending. Worker count, backlog, connection deadline, quota, same-UID check, protocol and object deletion contracts are unchanged. Timeout and socket-error accept paths return the permit exactly once; successful workers return it in their existing finally block.

The deterministic regression holds both worker releases after successful replies, requires the next sequential request to wait rather than reset, then verifies successful completion and actual zero-live cleanup. The original ConnectionResetError receipt and root's60-pass9.78s receipt were checked read-only and were not rewritten or rerun by this reviewer.

No source/test edits, model calls, GPU or additional infrastructure run occurred. This is not a fixed-nine or numerical acceptance result. Final hashes and detailed checks are in independent-review.json.
