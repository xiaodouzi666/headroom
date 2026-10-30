# Stored server capture analysis — 30 October 2026

Implemented, committed and deployed as 8f8701a. On Home, open Diagnose my snapshot, keep Stored server capture selected, choose s2 or nanoGPT and use the existing judge token to start a new analysis. The browser sends a small ID request; it does not download and re-upload the capture. The server copies only the fixed allowlisted capture into a private job, then uses the normal real Nebius pipeline. Original captures stay unchanged. This path runs no GPU workload.

## Verification

- Backend guarded focused checks: 84 passed in 23.64s. Initial fixture failure retained; test client lifespan fixture corrected, product gates unchanged.
- UI checks: 35 passed, TypeScript passed. Independent safety review passed.
- Two real stored input copies matched pinned hashes; source files remained unchanged.
- Eleven public GET checks passed; Results now exposes R9, R8 and all five prior curated entries.
- Real Chrome s2 analysis: job 8db19d724c3747f89e50a8f3e708b339, two real Ultra requests, exact net cost $0.04492144, valid needs-human diagnosis, no patch, no GPU and verified cleanup. Expandable stack citations and reconstructed memory composition displayed.

This is functional analysis evidence, not a correct automatic repair. The response incorrectly called optimizer state the largest category despite temporaries being slightly larger; its suggested foreach setting was already present. Cited stack sums are host-computed, but prose still needs review.

The current server s2 pickle SHA differs from the previous temporary local upload copy. Both records remain distinguished; this new test used the pinned server source and its identical private copy. No old receipt was overwritten.

## Submission

The existing Submitted 5/5 entry was edited through local Chrome after the Devpost connector required reauthentication. The public story and output-quality feedback were saved and read back; private v5 instructions with the same existing token were uploaded, saved and their filename read back. The public story was also verified on the project page. No new credential, payment, subscription or rules acceptance was performed. The public video remains unchanged.

## Limits

Valid-token tasks retain original gift-only allocation, per-task estimate ceiling, admission deadline, owner isolation, worker limits and 24-hour analysis retention. Original curated captures are retained. External snapshot upload remains an optional separate path; its new 360-second authenticated window has offline checks but no successful large-file public retest. Earlier upload timeouts remain failures. Ordinary Run tasks continue collecting captures automatically, with candidate captures only when a candidate actually executes.

R8 and R9 each had zero targets among nine. R10 later completed all nine with 0/9 memory targets, 4/9 valid correct first causes and 0/9 ready diagnoses; its independent review is in ../r10-20261030-review/. No acceptance denominator or threshold changed.
