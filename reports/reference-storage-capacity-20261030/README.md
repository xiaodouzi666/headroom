# Reference disk capacity conflict — confirmed, not repaired by deleting files

R14 s4's original-workload saved-tensor reference requested **16 GiB CPU staging and 64 GiB disk spill**. The preserved manifest placed its writable /out in the public Lab's **512 MiB tmpfs artifact volume**. DiskTensorStore requires the explicit positive disk limit plus a 1 GiB free-space reserve, so this reference cannot pass admission on that volume regardless of the host's free /home capacity. It failed at zero updates with the exact free-space-reserve error; cleanup completed.

The zero-spill hypothesis is disproven: SavedTensorOffload already does not construct DiskTensorStore when max_disk_bytes=0. Skipping that guard would not repair this positive 64 GiB request. Removing its reserve would also not make 64 GiB of output fit in 512 MiB.

## Safety boundaries retained

No runs/cache files were deleted. No artifact quota, source/acceptance policy, nine-case denominator, numerical tolerance, historical result, optimizer or model/GPU call changed.

The current artifact-volume implementation supports only a bounded tmpfs volume with a hard maximum of 512 MiB. There is no existing independent reference scratch backend. Read-only host checks show Docker backed by extfs/ext4, no quota mount option observed, and noninteractive sudo unavailable. This establishes the currently configured mechanism, not a universal claim that quotas can never be enabled.

An ordinary host bind or unrestricted local volume plus the application's byte counter is not a replacement for the current kernel-enforced writable-space boundary. A 64 GiB tmpfs would consume memory and conflict with the reference container's 32 GiB memory hard limit. A proper repair needs a distinct owned, kernel-bounded disk scratch mechanism (for example an independently managed finite filesystem or a bounded storage service) with explicit lifetime/cleanup and unchanged public /out. No such privileged backend was silently installed or claimed here.

## Guarded regression checks

107 focused tests passed in 0.85 seconds: the new storage-capacity cases plus existing offload-reference and artifact-volume tests. They cover zero-spill avoiding disk admission, positive spill failing before allocation when reserve is insufficient (including this exact 512 MiB/64 GiB conflict), the exact admissible boundary, serialized-byte aggregate cap, and refusal to enlarge the public artifact-volume limit. Ruff, format and diff checks passed.

The first test command selected a nonexistent test filename and ran no tests; that error is preserved separately. The final command uses tests/test_artifact_volume.py.

These tests certify the unchanged fail-closed guards and confirm the incompatibility. They do **not** certify a working 64 GiB scratch backend or a new successful s4 reference. audit.json binds the facts to the preserved actual manifest/result.
