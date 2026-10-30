# Authenticated Snapshot upload window: prepared change only

The current public s2 upload timed out after 30 seconds before analysis. This proposal gives only a successfully authenticated judge Snapshot upload up to 120 seconds. Anonymous/local compatibility uploads retain 30 seconds. The ordinary Run body deadline stays at 30 seconds. Public Snapshot authentication, browser-owner and Origin checks run before reservation/body parsing; invalid tokens do not get the longer window.

The three-slot bound counts receiving, queued and running jobs together. At most three accepted uploads can occupy those slots; a valid token holder could now keep them occupied for up to two minutes rather than half a minute. This is a bounded availability tradeoff, not an identity guarantee or elimination of denial of service. There is no new public anonymous access or model authorization.

The 480-second task clock starts when the receiving row is reserved. Upload time is deducted from that same clock, so 120 seconds of upload leaves at most 360 seconds for queue wait and execution. The route still uses min(upload window, remaining task time). File limits remain snapshot 50 MiB, traceback 256 KiB, source 1 MiB, plus 64 KiB total framing allowance: 51.3125 MiB request body maximum. Three simultaneous request bodies are at most 153.9375 MiB under the existing per-request limits. Streaming writes, header/part validation, directory safety, shared public storage admission, worker memory/file/process/deadline limits and retention are unchanged.

Timeout, disconnect and cancellation keep their existing fail_upload/parser-close paths and release active admission state. Partial uploads remain subject to existing 24-hour retention and shared storage admission. The 16 GiB storage threshold and 8 GiB free-space reserve are admission checks, not running hard filesystem quotas. No claim is made that repeated authorized uploads use zero disk space.

The pending patch adds three narrow backend cases: authenticated 120-second selection, unauthenticated 30-second selection, and a shorter total task deadline taking precedence. The test exercises real timeout cleanup with an artificially shortened context rather than waiting minutes. Existing authentication, three-slot, file-size, disconnect and total-deadline tests must also pass after application.

The UI will explain HTTP 408 as an upload timeout before analysis started, preserving other error distinctions. The current separate model-rejection/no-patch wording fix is already tested and is not repeated in this pending backend patch.

Files are only prepared in reports. Python AST parsing and git apply --check passed; no patch was applied and no proposed behavior is claimed tested. After R8 is terminal, apply this exact patch, run the targeted checks, freeze hashes, and deploy in a safe idle window. Do not retry the large real file before that change is deployed.
