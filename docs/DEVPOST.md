## Project name
Headroom

## Tagline
Autoresearch for GPU memory: an agent that reads CUDA memory evidence, patches your PyTorch script and tests the fix on the GPU — built on NVIDIA Nemotron 3 via Nebius Token Factory.

## Inspiration
Every PyTorch engineer has met `torch.OutOfMemoryError` at 3 a.m. PyTorch can record allocations with their call stacks, but large snapshots are difficult to inspect line by line. Nemotron 3 Ultra's long-input capability on Token Factory made an evidence-driven workflow practical for this project: give the model a snapshot-derived evidence pack, ask it to explain the peak, and test its proposed fix on the hardware.

## What it does
Headroom runs your script on a real GPU with allocator history on, captures the memory snapshot at the point of failure, and sends a token-budgeted evidence pack — peak composition by call stack, hot allocation paths, fragmentation indicators, timeline and source — to Nemotron 3 Ultra for root-cause diagnosis. Nemotron 3 Super writes the patch as exact line edits; Headroom applies it, re-runs the script under the same seed, and keeps a result that meets the selected memory and numerical policy without shrinking the model or shortening training. It searches keep-or-revert for up to six rounds toward your memory target and records the PyTorch documentation consulted through Tavily.

Historically, **5 of 9** distinct scenarios have a run that met its configured memory target. The best single evaluation reached **3 of 9**. The latest October 30 evaluation reached **1 of 9**. Its first saved diagnosis rounds produced **2 of 9** valid correct first-cause diagnoses and **1 of 9** ready for patching; raw first-category matches were **5 of 9**. At the final stopping point, **4 of 9** diagnoses were valid and **1 of 9** remained ready. <!-- numbers: summary --> The target of six successful scenarios has not been reached.

- **s3 eval loop:** peak memory fell **73.4%**, with all 20 recorded scalar losses identical; input, effective-batch and objective pairing was not established for the selected latest run. <!-- numbers: best.s3_eval_no_grad_missing -->
- **s8 idle teacher:** peak memory fell **96.1%**, with identical observed scalar losses; full workload pairing was not established. <!-- numbers: best.s8_two_models_resident -->
- **s4 retained graph:** peak memory fell **89.8%** from its observed OOM peak; the candidate completed 20 updates and its first five compared losses matched the documented reference. <!-- numbers: best.s4_loss_accumulation_graph -->

In a diagnosis-only comparison on the same saved workloads, full evidence gave more first-category matches than traceback and memory-summary evidence. The full diagnosis and evidence-reference checks are reported separately in [the experiment results](https://github.com/xiaodouzi666/headroom/blob/main/docs/RESULTS.md#does-the-snapshot-matter).

The saved-snapshot CLI processes a capture without running the supplied training script and is designed to suggest an unverified patch draft. Its first two checks failed; later s2 and nanoGPT CLI checks produced valid diagnoses, and a public nanoGPT analysis displayed cited stacks. These checks produced no patch and do not count as hardware repairs. The complete result history and comparison details are in [RESULTS](https://github.com/xiaodouzi666/headroom/blob/main/docs/RESULTS.md).

## How we built it
- **Lab:** Docker-isolated runner (no network, read-only source), `torch.cuda.memory._record_memory_history`, optimizer-step hooks for step counting and loss capture, same-seed re-runs, parameter-count and training-length checks.
- **Evidence pack:** a restricted snapshot reader groups allocations by stack, reconstructs allocator history and prepares a token-budgeted representation.
- **Models on Nebius Token Factory:** Nemotron 3 Ultra for diagnosis and planning, Nemotron 3 Super for structured line-edit patches and the Tavily tool loop, and Nemotron 3 Nano for optional stack labelling.
- **Measured input handling:** Ultra accepted **268,920 input tokens** in an authentic evidence request and **500,029 input tokens** in a retrieval probe. <!-- numbers: long_context -->
- **Verification and search:** keep-or-revert rounds with per-round verification feedback sent back to the planner.
- **App:** FastAPI + SSE backend and React front end with a live timeline, memory charts, diagnosis cards with clickable evidence stacks, diff and validation views, and a public gallery of historical cases.

## Challenges we ran into
Getting patches to apply was harder than producing a plausible diagnosis: malformed or truncated unified diffs led us to exact line edits bound to the original file hash, with structured error feedback. Verification needs care — a patch can appear to save memory by shrinking the model, skipping steps or changing the objective. Headroom checks parameter counts, update counts and loss series, and records when workload pairing is incomplete. Measuring and limiting long-input model use within a small credit allowance was another engineering task.

## Accomplishments that we're proud of
Real repairs produced end to end by open models and tested on hardware; diagnoses tied to captured allocation stacks; a result history that preserves failed attempts alongside measured improvements; and an open-source project with a public results site.

## What we learned
Large context is useful when the evidence format is explicit and the model must cite recorded stack IDs. A valid JSON response is only the first step: diagnosis references, patch application and numerical comparisons need separate checks. Exact line edits made patch failures easier to explain and repair. The hardest part of an automatic optimization loop is deciding what the measurements actually support.

## What's next
Improve strategy selection, evidence requests and malformed responses exposed by the latest suite; obtain successful precision-policy comparisons; extend diagnosis to FSDP/DeepSpeed workloads; and evaluate longer training runs.

## Limitations
Historical memory-target successes come from separate runs and do not establish identical full-training behaviour. Numerical coverage varies by case, as detailed above and in RESULTS. The latest October 30 evaluation met one of nine memory targets, below the target of six; its raw first-category matches and valid correct diagnoses are reported separately. The diagnosis-only comparison is one fixed-order pass without repeats, with two unconfirmed reference causes retained in the full denominator. Both new s2 precision-policy tests and the HF Trainer repair failed to meet their requirements; a statically accepted HF configuration edit did not establish a successful repair. Saved-snapshot analysis has produced valid diagnoses, although some explanations still contain factual errors. The web interface can analyze an explicitly shared server capture by ID using new Nebius inference; external snapshot upload is optional. Neither path runs the supplied training code or proves a GPU repair. A large public upload timed out before analysis.

## Built with
Nebius Token Factory · NVIDIA Nemotron 3 Ultra · NVIDIA Nemotron 3 Super · NVIDIA Nemotron 3 Nano · Tavily · PyTorch · CUDA · Docker · FastAPI · React

## Try it
Demo: https://headroom.tail45186b.ts.net/ — open Verified runs to inspect actual repairs and download their patches, or Results for the evaluations and diagnosis comparison, without logging in. Repo: https://github.com/xiaodouzi666/headroom . Video: https://www.youtube.com/watch?v=aaXF60LryWI
