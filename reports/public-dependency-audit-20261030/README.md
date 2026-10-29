# Public dependency advisory review — 2026-10-30

This is a bounded, read-only dependency review, not a penetration test, full SBOM audit, or statement that the service is free of vulnerabilities. Exact installed versions were read with importlib.metadata (no application/package imports); only public package names and versions were sent to PyPI. Raw version-advisory responses are retained in pypi-version-advisories.json.

## Results

| Installed dependency | Official PyPI version response |
| --- | --- |
| FastAPI 0.162.0 | No advisory records returned |
| Starlette 1.9.0 | No advisory records returned |
| Uvicorn 0.54.0 | No advisory records returned |
| python-multipart 0.0.32 | No advisory records returned |
| Pydantic 2.14.1 | No advisory records returned |
| Jinja2 3.1.6 | No advisory records returned |
| OpenAI SDK 3.37.0 | No advisory records returned |
| HTTPX 0.28.1 | No advisory records returned |
| Torch 2.5.1+cu124 | Base release 2.5.1 returned 22 advisory records, 19 distinct CVE aliases |

PyPI responses are an advisory index, not a complete risk inventory. Some Torch records describe later-version operator bugs while their indexed affected range also includes this release; duplicates and broad ranges must not be reported as 19 independently verified exploits against Headroom. The CUDA wheel was mapped to its base public release; wheel contents and transitive/native components were not separately scanned.

## Confirmed old Torch dependency risk

Two maintainer advisories explicitly include 2.5.1:

- [CVE-2025-32434 / GHSA-53q9-r3pm-6pq6](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6): unsafe deserialization remains possible despite weights_only=True in releases through 2.5.1; that issue was fixed in 2.6.0.
- [CVE-2026-24747 / GHSA-63cw-57p8-fm3p](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p): malformed checkpoint metadata/opcodes can corrupt memory and potentially execute code through weights_only loading in releases through 2.9.1; fixed in 2.10.0.

These are unresolved vulnerable-version dependencies. Upgrading merely to 2.6 would address the first but not the second. A tested image/runtime upgrade is needed; this audit did not change the pinned Torch version or claim compatibility of a replacement.

Reachability assessment from current source:

- The only first-party torch.load call found in headroom/ and scripts/ is headroom/verify/offload_disk.py, in DiskTensorStore.unpack. It loads a tensor previously serialized by the same DiskTensorStore, not an uploaded checkpoint endpoint. The corresponding save uses exclusive, no-follow files under a generated owned directory.
- SavedTensorOffload is entered by headroom.lab.run_target inside the Lab container, launched by headroom/lab/runner.py. Thus this reviewed call is not a public API-process unpickler. An untrusted script in that container may still tamper with its own process/files; static script policy is not a security sandbox.
- Public anonymous submissions select server-owned examples. Credentialed judges may supply Python source, which is intentionally executed only inside the Lab sandbox; the API rejects arbitrary repository input. These are different trust boundaries from loading an arbitrary checkpoint in the host API process.
- Snapshot import uses a custom primitive-only unpickler with forbidden class/persistent lookups and a prior opcode/size/graph validation pass. It does not route uploaded snapshots through torch.load. Snapshot submissions are currently disabled by deployment policy, as reported by root; this child did not change or re-read private deployment settings.
- Therefore no direct unauthenticated uploaded-checkpoint-to-host torch.load route was found in this bounded review. This is not proof that every indirect library path, malicious script, native operator, container escape or future feature is safe. Keep the sandbox/resource protections and plan the dependency upgrade separately.

## Public web stack checks

Current Starlette 1.9.0 is outside the affected ranges of the maintainer advisories reviewed:

- [Host poisoning](https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr): affected through 1.0.0, fixed 1.0.1.
- [Path-to-authority poisoning](https://github.com/Kludex/starlette/security/advisories/GHSA-jp82-jpqv-5vv3): affected before 1.3.0.
- [URL-encoded form limits ignored](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq): affected before 1.3.1.
- [Arbitrary HTTPEndpoint method dispatch](https://github.com/Kludex/starlette/security/advisories/GHSA-x746-7m8f-x49c): affected before 1.1.0.
- [Windows StaticFiles UNC access](https://github.com/Kludex/starlette/security/advisories/GHSA-wqp7-x3pw-xc5r): affected before 1.1.0; POSIX not affected.
- [FileResponse Range CPU exhaustion](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8): affected 0.39.0 through 0.49.0, fixed 0.49.1.

The application's routes use explicit FastAPI methods; body parsing uses bounded streaming JSON or the custom multipart path. Public files use open_regular plus StreamingResponse, not StaticFiles/FileResponse; these source observations reduce exposure to the named paths independently of the version comparison.

python-multipart 0.0.32 is beyond the reviewed fixes for [unbounded headers](https://github.com/Kludex/python-multipart/security/advisories/GHSA-pp6c-gr5w-3c5g) in 0.0.27, [preamble/epilogue work](https://github.com/Kludex/python-multipart/security/advisories/GHSA-mj87-hwqh-73pj) in 0.0.26 and [nondefault filename traversal](https://github.com/Kludex/python-multipart/security/advisories/GHSA-wp53-j4wj-2cfg) in 0.0.22. Headroom additionally ignores uploaded filenames and enforces fixed fields, part sizes and header-byte caps.

Jinja2 3.1.6 is the upstream [security release](https://github.com/pallets/jinja/releases/tag/3.1.6) containing the attr-filter sandbox fix; the [advisory](https://github.com/pallets/jinja/security/advisories/GHSA-cpwx-vrp4-4pq7) lists affected releases through 3.1.5. Headroom's use is the hash-pinned tokenizer chat template in llm/preflight.py, not a public template editor.

## Limits and next actions

The reviewed web-package versions did not reveal an applicable indexed advisory, while Torch has explicit upstream vulnerabilities. These observations do not remove the application's separately identified slow-upload and artifact-volume resource risks; those have their own code changes and focused receipts. Native CUDA/NVIDIA/kernel/container-runtime vulnerabilities, all transitive packages, JavaScript dependency advisories and a complete source audit are outside this short review. No malicious checkpoint or exploit was executed, no service was restarted, and no dependency was installed or upgraded.
