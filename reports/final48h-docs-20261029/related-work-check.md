# Related-work wording check

Checked: 2026-10-29 (Asia/Shanghai). Scope: primary public documentation and papers, plus the supplied FINAL_48H template and the existing 2026-10-27 prior-art report. This is a bounded documentation check, not an independent reproduction or a proof that no comparable system exists. No model, GPU, or financial operation was run.

## Recommended README replacement

Headroom builds on existing memory-analysis and optimization tools. PyTorch's [memory_viz](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html) visualizes allocator snapshots; NVIDIA's [Megatron Bridge tools](https://docs.nvidia.com/nemo/megatron-bridge/nightly/skills/nemo-mbridge-memory-snapshot-analysis/SKILL.html) analyze and compare allocation traces. [GPU-Boost](https://github.com/its-arnavtech/GPU-Boost) combines script analysis and bounded benchmarks with human-approved edits, validation and rollback. [pt-snap-cli](https://pypi.org/project/pt-snap-cli/) provides snapshot queries and agent workflows through its CLI and skills. [MOA](https://arxiv.org/html/2606.31368v1) studies profiling-guided memory optimization for C/C++ codebases. Headroom focuses on PyTorch script repair: diagnoses cite captured allocation stacks, and its full repair workflow tests candidate patches on a GPU against memory and numerical checks before reporting a verified repair.

Keep this mode distinction in Limitations or the snapshot-upload description:

> Uploaded snapshots produce a diagnosis and an unverified patch draft. Hardware verification requires a runnable workload and a GPU re-run.

The paragraph deliberately describes implemented workflow scope without claiming that the exact combination is a world first or that Headroom outperforms these systems.

## Findings behind the edits

| Template claim | Finding and recommended handling | Primary source checked |
|---|---|---|
| “pieces have precedents; the combination does not” / “the first agent” | Not established. The previous prior-art report explicitly says its search is bounded and cannot establish absence. Finding no exact match among these sources is insufficient for exclusivity, even with “to our knowledge.” Replace with the concrete workflow description above. | Local source: `reports/development-20261027/prior-art.md:3,9,23,62`; template `docs/FINAL_48H.md:214`. |
| GPU-Boost analyses scripts statically and proposes edits | Static analysis is supported, but this is incomplete as a comparison and must not become “static only.” The official README describes synthetic benchmarks, temporary trial validation, explicit approval of deterministic changes, application, validation, and rollback. The documented distinction is human approval for every applied change, not absence of validation or execution. | [GPU-Boost README](https://github.com/its-arnavtech/GPU-Boost/blob/main/README.md), “What It Does” and human-approved optimization workflow; [raw source](https://raw.githubusercontent.com/its-arnavtech/GPU-Boost/main/README.md). |
| pt-snap-cli provides query and MCP access | Version-dependent and now stale if written in the present tense. PyPI 0.2.0 documents CLI queries and MCP tools. PyPI 0.4.1 and the current repository README document CLI plus agent skills and explicitly state “there is no MCP server.” The current concise replacement should say CLI and skills; historical MCP belongs only in this report. | [0.2.0 release](https://pypi.org/project/pt-snap-cli/0.2.0/), MCP Server; [0.4.1 release](https://pypi.org/project/pt-snap-cli/0.4.1/), Agent Skills; [current README](https://github.com/codeasier/pt-snap-cli/blob/main/README.md), Agent Skills; [skills guide](https://github.com/codeasier/pt-snap-cli/blob/main/docs/en/skills.md). |
| Headroom goes from snapshot to a hardware-verified result | Scope must distinguish the full repair workflow from uploaded-snapshot diagnosis. FINAL_48H itself specifies “not run — bring the patch to your GPU” for uploaded results. Not every diagnosis has an accepted patch, and rejected/unexecuted candidates must not be described as verified. | Local source: `docs/FINAL_48H.md:91,93,101`; use actual run evidence for individual successful repairs. |
| PyTorch memory_viz renders snapshots for humans | Supported as a visualization description. It shows allocation timelines, allocator states, and stack traces. Avoid implying that recorded allocator data cover all CUDA memory: the official docs distinguish allocations outside the PyTorch allocator. | [PyTorch CUDA memory documentation](https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html), Understanding CUDA Memory Usage / Active Memory Timeline / Allocator State History. |
| NVIDIA skill supplies scripts for humans | Too narrow as a comparison. Its tools reconstruct history, group by source, compare two snapshots, and expose text/JSON output. Calling them analysis/comparison tools accurately covers the documented interface without excluding agents. | [Megatron Bridge memory-snapshot skill](https://docs.nvidia.com/nemo/megatron-bridge/nightly/skills/nemo-mbridge-memory-snapshot-analysis/SKILL.html), What It Is / Pick a Script. |
| MOA profiling → LLM → patch with syntax validation | Broadly supported, with an important boundary: §3.4 describes language-server syntax validation, but the evaluation also includes manual semantic review and expert acceptance. Do not say MOA has only syntax checks in every evaluation. The subject is OpenHarmony C/C++; cite it as a 2026 preprint. | [MOA v1](https://arxiv.org/html/2606.31368v1), §3.4, §4.1, §4.4. |
| AutoKernel and autoresearch are loops “for speed” | Overcompressed. AutoKernel documents profiling, benchmark/keep/revert, and correctness checks. Autoresearch optimizes validation bits per byte under a fixed training-time budget, so it is not simply speed optimization. They may be omitted from the short paragraph, or described with those actual objectives. | [AutoKernel README](https://github.com/RightNow-AI/autokernel/blob/main/README.md), How It Works; [autoresearch README](https://github.com/karpathy/autoresearch), How it works. |
| Checkmate, DTR, ZeRO-Offload address memory/time trade-offs | Supported at a high level. Checkmate chooses rematerialization schedules using optimization and profile costs; DTR performs online eviction/recomputation; ZeRO-Offload moves data/computation to CPU while limiting transfer/compute overhead. These are precedents for automatic memory optimization, not direct evidence that the Headroom workflow has been duplicated. | [Checkmate](https://arxiv.org/abs/1910.02653), [DTR](https://arxiv.org/abs/2006.09616), [ZeRO-Offload](https://arxiv.org/abs/2101.06840), paper abstracts. |
| Scoped, artifact-bound repair verification is wholly new | Unsupported. CertiPatch is a neighboring-domain precedent for constrained frozen-model repair with declared evaluation scope and artifact verification. This does not make it an exact PyTorch memory-repair comparator; it does prevent claiming the general evidence concept as new. | [CertiPatch author repository](https://github.com/aliuyar1234/certipatch), Description / Why CertiPatch; consistent with existing local prior-art report. |

## pt-snap-cli version evidence

The 0.2.0 PyPI page is dated 2026-08-08 and lists an MCP service for querying snapshots. The 0.4.1 page is dated 2026-10-12 and uses CLI/agent skills instead. The repository README independently matches the latter; the GitHub connector returned its modification date as 2026-10-11T17:46:22Z. These observations explain why the requested older MCP wording should be corrected, while preserving the intended acknowledgment of agent-accessible snapshot analysis. No claim is made that querying or agent-assisted diagnosis is unique to Headroom.

## Other nearby wording to correct

The DEVPOST template at `docs/FINAL_48H.md:233` also says the workflow became possible “for the first time” and suggests giving the model “the whole snapshot.” Neither follows from the related-work evidence. Its own implementation description at line 242 says the evidence pack is token-budgeted. Prefer “a larger snapshot-derived evidence pack” unless the specific measured request demonstrably includes the complete relevant representation. A model context-window capability is not evidence of workflow priority, and a large probe is not production diagnosis or a successful repair.

## What this check does not establish

- No world-first priority, exhaustive absence of comparable systems, or superiority over the named tools.
- No independent reproduction of comparator performance or safety claims.
- No automatic equivalence between snapshot analysis, patch proposal, candidate execution, and an accepted hardware-tested repair.
- No new Headroom success counts or changes to historical acceptance criteria.

Only this report was written by this check. README, DEVPOST, RESULTS, FEEDBACK, source code, deployment, and billing state were not changed.
