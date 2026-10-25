# Annotation frame transport review — r2 preparation

The r1 audit identified complete annotation output coverage but poor agreement with the existing heuristic. Its model requests sent only each selected stack's final twelve frames. The r2 change preserves the full common stacks under explicit transport limits. It does not alter annotation labels, agreement thresholds, model reasoning settings, or acceptance scores.

The private candidate has now been integrated into production with the reviewed source and test hashes. The current r2 full regression remains a separate qualification; this report records the completed offline focused work only.

## Evidence and limits

Across the eight saved r1 synthetic captures, the selected inputs contain **119 stacks and 7364 frames**, with at most 109 frames per stack and at most 1271 UTF-8 bytes in a string field. The complete pre-change per-case frame payloads were 118644–179897 bytes. These observed sizes fit the selected transport bounds:

- At most 40 selected stacks; inputs exceeding 4096 source stack records are explicitly skipped before a router call. Omitted unselected stack counts are reported.
- At most 256 frames per selected stack. Under frame or aggregate limits, selection alternates between the two ends and cycles across stacks. Retained frames are emitted in original order, with exact zero-based retained ranges and omitted counts.
- String fields are bounded to 4096 UTF-8 bytes and each frame to 2048 bytes after JSON string escaping. Altered or unavailable fields are explicitly marked.
- The message content is capped at 224 KiB including the HTTP JSON-string escaping layer, leaving 32 KiB below the existing 256 KiB prepared-body capture limit for the fixed schema/envelope. A final exact-size check fails closed.

The payload contains stack IDs, filename/name/line fields, and neutral coverage metadata. It does not provide heuristic categories, labels, allocation byte counts, or benchmark repair answers. Nano reasoning remains disabled and the output cap remains 3000. Existing agreement computation and acceptance=false semantics remain unchanged.

These limits apply to outgoing transport and its selected-frame processing. The existing source-binding fingerprint still hashes complete selected original frame data; **224 KiB is not an end-to-end process-memory or source-reading limit**.

## Offline validation

**62 focused tests passed** across the new transport tests and existing annotation, evidence, and request-audit tests. Ruff check, Ruff format --check, and the original patch application check passed. The private module-injection harness produced one pytest plugin-rewrite warning; no test failed. Production integration and its full regression are separately controlled by the root agent.

Eight MockTransport calls through the real SDK serialized the saved r1 inputs. All **119 selected stacks and all 7364 filename/name/line frames** were retained exactly and in order. The largest complete request body was **190705 bytes**. All eight request bodies passed the existing prepared-body capture function, and their wire settings remained reasoning=false with max_completion_tokens=3000. Large, escaped, malformed, and excessive inputs were covered by synthetic negative tests, including explicit omission and preservation of both ends.

This is an offline input-preservation result. It does **not** establish improved live agreement, classification correctness, memory-target success, or actual new API cost. No provider call or GPU run occurred, and the original T2.3 agreement requirement remains outstanding until new, independently audited evidence is available. More input may change cost; the unchanged runtime budget gates remain authoritative.

## Review artifacts

- `annotation-focused.log`: focused test and formatting output.
- `annotation-retained-replay.log`: metadata-only historical-input replay results; no raw prompts, frames, labels, hidden reasoning, or private database contents.
- `annotation-validation-files.json`: an array of file paths and SHA-256 digests binding the integrated source/test and these public review artifacts.

The saved r1 outcomes and raw audit receipts remain unchanged. No historical success is reused as a new r2 result.
