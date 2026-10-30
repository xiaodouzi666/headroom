# Bounded reference scratch core

This adds a host-owned byte broker for numerical-reference disk spill, independent of the public 512 MiB Lab artifact volume. The target receives only one private Unix socket; the host object directory is never mounted in the target. The broker does not import Torch or deserialize tensor/pickle bytes.

## Contract

- ReferenceScratchBroker(root, max_bytes, socket_path=None, max_objects=4096, peer_uid=None).start() creates a new owned empty root and a short socket in a fresh private /tmp endpoint directory by default. The public properties are root, socket_path and nonce. Host methods are evidence() and close().
- Host evidence includes schema, nonce, root, socket_path, owner_pid, owner_process_identity, max_bytes, object/byte counts, peak_reserved_bytes and cleanup_verified.
- The wire protocol has only create, append, finalize, read with offset, and delete. IDs are random opaque 32-hex strings. It accepts no path, executes no target strings and returns only fixed error messages.
- JSON control headers are at most 4096 bytes; binary chunks at most 4 MiB; live objects at most 4096; simultaneous connections at most two; each connection has an absolute ten-second I/O deadline. The endpoint is mode 0600 in an owned 0700 directory; Linux peer UID must match.
- Aggregate serialized-byte admission is enforced outside the target. Under one host lock, each append reserves its complete chunk before opening/writing. Short writes or failures retain the full reservation. Space is refunded only after identity-checked unlink and confirmed absence. Both initial admission and each append preserve at least 1 GiB of host free disk.
- Finalized objects are immutable. Reads are bounded, seekable RPC operations; repeat unpack preserves the same object. Object replacement, symlinks, unknown IDs, malformed fields and out-of-range offsets fail closed.
- close() stops connections/workers before deleting owned objects, unlinks only the recorded socket identity, and writes a small host receipt. cleanup_owned_scratch(root, expected_nonce=...) supports supervisor recovery after owner process exit. It checks PID/start identity, root/nonce/UID and regular owned object names; live/unknown owners and unexpected files/links are refused.
- The CPU staging and public artifact/memory limits are unchanged. This is a trusted host service enforcing a target-external quota, not a claim that the host filesystem has a new kernel/project quota.

## Offload integration

SavedTensorOffload accepts keyword-only scratch_socket. A positive disk budget with a socket selects RemoteDiskTensorStore; no socket keeps the existing local implementation. A socket with zero disk budget is rejected.

The target uses Torch save/load only inside its container. A file-like writer appends serialized bytes to the service; a seekable reader requests bounded offsets. The host never unpickles. The target's cleanup ACK is insufficient for verification: host_broker references additionally require a source-request-bound host reference_scratch receipt with matching explicit cap, valid nonce, request_verified=true, cleanup_verified=true, zero live bytes/objects, and positive peak within the cap. The host peak must cover the target-reported serialized peak.

The lifecycle integrator must bind the actual socket path to the fixed container socket, preserve it in the host manifest, verify the storage_backend branch, stop/remove the target before broker cleanup, and attach the final host receipt. Docker/runner/run_target/API-queue lifecycle integration is owned by the root agent and is separately reviewed/tested.

## Core verification

107 v4-guarded tests passed in 7.50 seconds; Ruff, format and diff checks passed. This includes malformed/path/symlink requests, quota concurrency, short-write/failed-unlink retention, bounded connections and slow-drip deadlines, host reserve, wrong peer/cap, exact object bounds, real CPU Torch serialization/unpack twice through RPC, target-only proof rejection, and actual tiny-byte CLI SIGKILL/supervisor recovery.

The initial core run (104 passing tests before three hardening checks) is retained. The core unit run used no GPU, Docker workload, live model, large scratch allocation, privilege elevation or historical deletion. Largest configured object budget used by those unit tests is 16 KiB. The separately authorized integration smokes below do not change the fixed-nine score or threshold.


## Separately authorized real-container integration

The v5-guarded CPU Docker smoke passed (one test, 5.69 seconds), running the unchanged pinned s4 source with --tiny and three CPU updates, 8 MiB staging and a positive 16 MiB disk cap. Its offload request, socket mount, allowlisted offload JSON export and all cleanup were verified. As expected, CPU tensors produced no CUDA spill; host peak was zero.

One additional explicitly authorized tiny CUDA infrastructure smoke then used the same original source with --tiny/three updates, 8 MiB staging and 16 MiB disk. It completed with 63 actual CUDA tensors spilled and unpacked through the host broker. The broker wrote/peaked at 396,900 serialized bytes across 3,087 RPC requests; capture wall time was 3.2904 seconds and total runner time 7.4696 seconds. The host request, export, target, artifact and broker cleanup were all verified. All live object/byte counts returned to zero; the GPU process inventory was empty before and after. Eight relevant implementation hashes were unchanged across this run.

The tiny run is a plumbing test, not a twenty-update numerical-reference or fixed-nine repair result. Its small-object overhead cannot establish full-size 24+ GiB throughput. The current broker fsyncs once per finalized object, not per append. No new model call or credit charge occurred. Original full-size reference wall-clock controls remain unchanged.

Fresh immutable run/receipt identities and source hashes are in integration-verification.json. The raw source run is runs/research/reference-scratch-smoke-20261030/b430d596fb6647a2b6117d37fafa1ef5.


## Review follow-up

Independent review found that the stated host-peak/client-peak consistency requirement was missing from the first proof implementation. The final proof now requires a genuine integer client serialized peak greater than zero and no larger than the host's recorded peak. A host peak of eleven bytes versus a twelve-byte target peak is explicitly rejected. This changed only the proof check and its negative fixture.

The focused proof/offload regression then passed 74 guarded tests in 0.42 seconds, with Ruff, format and diff checks passing. The earlier actual CPU/CUDA plumbing receipts and their original source hashes remain preserved; no container/GPU run was repeated for this postcondition check. Final hashes are in peak-hardening-verification.json.
