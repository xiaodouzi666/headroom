# Headroom

**Headroom turns a CUDA out-of-memory crash into a verified patch.** Point it at a PyTorch script, and it runs the script on a real GPU with allocator history on, captures the memory snapshot at the moment of failure, hands the evidence to NVIDIA Nemotron 3 Ultra on Nebius Token Factory for a root-cause diagnosis, writes a patch with Nemotron 3 Super, and re-runs the script under the same seed. It keeps a patch only when the result meets the selected memory and numerical policy without shrinking the model or shortening training.

**Built with NVIDIA Nemotron 3 (Ultra / Super / Nano) on Nebius Token Factory.** Web research powered by Tavily.

- **Live demo:** [Headroom](https://headroom.tail45186b.ts.net/) — open Verified runs to inspect real repairs, diagnoses, cited stacks and downloadable patches.
- **Video (3 min):** https://www.youtube.com/watch?v=aaXF60LryWI
- **License:** [Apache-2.0](LICENSE)
- GPU measurements below use a single RTX 3090 Ti. [Results and source runs](docs/RESULTS.md) record the workload and comparison behind each outcome.

## What it does

1. **Capture.** The script runs inside an isolated Docker container (no network, read-only source) with `torch.cuda.memory._record_memory_history` enabled. On OOM — or at the end of a reclaim capture — Headroom dumps the allocator snapshot, the traceback, the loss series and the step timings. Allocation history is used to reconstruct the peak.
2. **Diagnose.** The snapshot is compressed into an evidence pack (peak composition by call stack, allocation hot paths, fragmentation indicators, timeline) and sent, together with the source, to **Nemotron 3 Ultra**. Ultra returns ranked root causes with allocation-stack references and a repair plan that respects the user's policy.
3. **Patch.** **Nemotron 3 Super** writes the patch as exact line edits against the original file hash; Headroom applies and compiles it. **Nemotron 3 Nano** provides optional allocation-stack labels.
4. **Verify.** The patched script re-runs under the same seed. Headroom compares peak memory, step time, the available loss series and the parameter count against the baseline or a documented reference. A patch cannot pass by shrinking the model or shortening training.
5. **Search.** Keep what works, revert what doesn't, up to six rounds, until the memory target is met — and, when the policy allows it, retain alternative configurations with their measured trade-offs.
6. **Cite.** When a fix depends on version-specific behaviour (`torch.utils.checkpoint`, `PYTORCH_CUDA_ALLOC_CONF`, fused optimizers), Headroom can retrieve PyTorch documentation through **Tavily** and list the recorded sources in the report.

## Diagnose your own OOM

Capture allocator history in your training process, then save the snapshot when it fails:

```python
torch.cuda.memory._record_memory_history(max_entries=200_000)
# ... run your workload; in its OutOfMemoryError handler:
torch.cuda.memory._dump_snapshot("snapshot.pickle")
```

```bash
uv run headroom diagnose --snapshot snapshot.pickle --traceback oom.txt --source train.py
```

The traceback and source are optional. Headroom analyzes the saved evidence and attempts to produce a diagnosis with cited stacks and, when source is supplied, a patch draft. This command does not run the supplied script. The draft is marked **unverified: not run on hardware**. The first two live checks failed. Subsequent real s2 and nanoGPT CLI checks produced valid diagnoses, and a public nanoGPT upload displayed a valid diagnosis with inspectable stack references. No patch was produced in those checks; some model explanations still contain factual errors. See [CLI setup, outputs and retention](docs/CLI.md#diagnose-a-saved-cuda-snapshot).

## Results

The recorded suite contains eight synthetic PyTorch training cases and pinned nanoGPT. Within the recorded repair campaigns, the table selects the lowest successful candidate peak for each scenario, choosing the latest campaign run on ties; [RESULTS](docs/RESULTS.md) gives its run, source revision and complete history. Memory uses decimal GB, calculated from the recorded byte counts.

| Scenario | Historical memory target | Peak before → after | Numerical comparison |
|---|---|---|---|
| [s3 eval loop without no_grad](docs/RESULTS.md) | Met | 2.44 GB → 0.65 GB (−73.4%) | 20 losses identical; workload pairing matched | <!-- numbers: best.s3_eval_no_grad_missing -->
| [s8 unused teacher on GPU](docs/RESULTS.md) | Met | 3.10 GB → 0.12 GB (−96.1%) | 20 scalar losses identical; workload pairing incomplete | <!-- numbers: best.s8_two_models_resident -->
| [s4 retained loss graph](docs/RESULTS.md) | Met | 24.77 GB (OOM) → 2.53 GB (−89.8%) | First 5 reference losses identical; candidate completed 20 updates | <!-- numbers: best.s4_loss_accumulation_graph -->
| [s2 fp32 AdamW](docs/RESULTS.md) | Met | 22.92 GB → 18.64 GB (−18.7%) | 20 losses within tolerance; workload pairing incomplete | <!-- numbers: best.s2_capacity_v2 -->
| [s1 batch too large](docs/RESULTS.md) | Met | 24.75 GB (OOM) → 14.30 GB (−42.2%) | First 5 reference losses identical; candidate completed 20 updates | <!-- numbers: best.s1_batch_too_big -->
| [s7 frozen parameters in optimizer](docs/RESULTS.md) | Not met | — | No qualifying historical target result |
| [s6 full-vocabulary fp32 logits](docs/RESULTS.md) | Not met | — | No qualifying historical target result |
| [s5 variable-length allocations](docs/RESULTS.md) | Not met | — | No qualifying historical target result |
| [nanoGPT pinned workload](docs/RESULTS.md) | Not met | — | No qualifying historical target result |

Historically, **5 of 9** distinct scenarios have a run that met its configured memory target. The best single evaluation reached **3 of 9**. The latest October 30 evaluation reached **0 of 9**. Its first saved diagnosis rounds produced **5 of 9** valid correct first-cause diagnoses and **4 of 9** ready for patching; raw first-category matches were **6 of 9**. No final diagnosis remained ready when the evaluation stopped. <!-- numbers: summary -->

### Does the snapshot matter?

Same nine saved workloads, diagnosis only, one request per condition:

| Diagnosis input / model | First-cause matches | Valid and correct | Mean input tokens | Model cost (USD) | Mean elapsed |
|---|---:|---:|---:|---:|---:|
| Full evidence + Ultra | 6/9 | 4/9 | 46,496 | $0.464260 | 8.498 s | <!-- numbers: ablation.full_ultra -->
| Traceback + memory summary + Ultra | 2/9 | 2/9 | 11,009 | $0.09866092 | 4.691 s | <!-- numbers: ablation.traceback_ultra -->
| Full evidence + Super | 6/9 | 4/9 | 46,496 | $0.1308225 | 5.681 s | <!-- numbers: ablation.full_super -->

First-cause matches compare the first category in strict JSON with the reference cause. Valid and correct also requires the full diagnosis, evidence references and policy checks to pass. Full evidence produced more category matches in this pass; these are diagnosis results and do not add automatic repair successes.

[Experiment details](docs/RESULTS.md#does-the-snapshot-matter).

### Long inputs on Token Factory

Nemotron 3 Ultra accepted **268,920 input tokens** in an authentic evidence request and **500,029 input tokens** in a separate retrieval probe through Token Factory. <!-- numbers: long_context -->

Headroom sends a token-budgeted, snapshot-derived evidence pack with relevant source. The larger input capacity lets it retain more allocation context in one request.

## Quickstart

Linux host with an NVIDIA GPU, Docker with GPU support, Python 3.12 and `uv`. Add your private keys and complete the model configuration and spending setup in [Runtime setup](docs/RUNTIME.md) before the model-backed command.

```bash
git clone https://github.com/xiaodouzi666/headroom.git && cd headroom
uv sync --locked --python 3.12
bash scripts/build_lab_image.sh
cp .env.example .env && chmod 600 .env   # add NEBIUS_API_KEY, TAVILY_API_KEY
# Complete docs/RUNTIME.md, then:
uv run headroom fix scenarios/s3_eval_no_grad_missing/train.py --target reclaim --reclaim-reduction-pct 30
```

The s3 example already fits in GPU memory; this command asks Headroom to reduce its peak usage. Use `--target fix-oom` for a workload that actually runs out of memory.

`headroom fix` prints a live timeline and writes `report.md` and the evidence pack under `runs/jobs/<id>/` by default, plus `patch.diff` when a candidate is kept. `headroom snapshot <script>` captures without calling a model; `headroom watch -- <command>` captures CUDA OOM evidence and attempts repair for supported Python entrypoints. `headroom serve` starts the web app on port 8000. See [CLI](docs/CLI.md) and [Runtime setup](docs/RUNTIME.md).

## How we use Nebius Token Factory and NVIDIA Nemotron

| Role | Model | Why this model |
|---|---|---|
| Diagnosis and repair planning | `nvidia/Nemotron-3-Ultra-550b-a55b` | Reads the evidence pack and source in one request and returns stack references and a policy-aware plan |
| Patch writing and repair | `nvidia/nemotron-3-super-120b-a12b` | Structured exact line edits and function calling for the Tavily research tool |
| Optional stack labelling | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | A smaller model for short allocation-stack descriptions |

All model calls use Token Factory's OpenAI-compatible API (`us-central1`). Headroom records returned token usage and calculates request costs when pricing and usage are complete. Tavily supplies runtime documentation search and extraction, cached per query.

## Limitations

The historical table combines separate runs and workload versions. s3 has a paired, identical full loss series; s1 and s4 compare the first five backward-loss values against documented references. s2 uses a tolerance-based comparison, and s2/s8 lack complete input, effective-batch and objective pairing. An OOM baseline only shows the peak reached before failure; s1's candidate peak is reconstructed. Verification covers short training runs, not full training quality. Distributed training and compiled extensions are outside the current repair workflow.

Four scenarios have no recorded target success in this history. The latest October 30 evaluation met none of its nine memory targets, below the target of six; matching a cause was often insufficient to produce a usable patch. The first-cause counts use the first saved diagnosis round, which can include correction requests within that round; raw category matches and validated diagnoses are separate measures. The two additional s2 precision-policy tests did not pass, and HF Trainer repair failed after a configuration edit passed its static check. They produced no successful memory-versus-speed comparison or new successful gallery cases.

The diagnosis comparison is one fixed-order pass without repeats; s5 and nanoGPT have unconfirmed reference causes and remain in its denominator. Two full-evidence Ultra replies were truncated. Long-input probes establish request handling, not diagnosis quality or the maximum context size. The saved-snapshot path now has real valid CLI and public-web diagnoses, but some model explanations still misstate category totals or inferred runtime settings. A large-file public upload timed out before analysis. Server-stored capture analysis is the default webpage flow; external-file upload is optional. Both use real Nebius inference and require the judge token on the public deployment. Preset live examples and the historical Verified runs gallery are available.

## Related work

Headroom builds on existing memory-analysis and optimization tools. PyTorch's [memory_viz](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html) visualizes allocator snapshots; NVIDIA's [Megatron Bridge tools](https://docs.nvidia.com/nemo/megatron-bridge/nightly/skills/nemo-mbridge-memory-snapshot-analysis/SKILL.html) analyze and compare allocation traces. [GPU-Boost](https://github.com/its-arnavtech/GPU-Boost) combines script analysis and bounded benchmarks with human-approved edits, validation and rollback. [pt-snap-cli](https://pypi.org/project/pt-snap-cli/) provides snapshot queries and agent workflows through its CLI and skills. [MOA](https://arxiv.org/html/2606.31368v1) studies profiling-guided memory optimization for C/C++ codebases. Headroom focuses on PyTorch script repair: diagnoses cite captured allocation stacks, and its full repair workflow tests candidate patches on a GPU against memory and numerical checks before reporting a verified repair.

## Repository

`headroom/` (Lab, evidence, LLM routing, verify, search, API) · `scenarios/` (synthetic cases) · `repos/` (pinned repository fixtures) · `web/` (React app) · `docs/` (architecture, CLI, evaluation, feedback) · `reports/` (campaign records). [Current document evidence](reports/docs-r13-20261030/README.md) and [earlier verification notes](reports/final48h-docs-20261029/README.md).

Development checks: `uv run pytest -q`, `uv run ruff check .`, `gitleaks detect`.

License: Apache-2.0. Thanks to PyTorch, nanoGPT, Hugging Face Transformers, Nebius, NVIDIA and Tavily.
