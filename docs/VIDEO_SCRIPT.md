# Demo storyboard — recording pending

Target duration: 2 minutes 50 seconds. Record only after a real Nebius-backed repair passes. Do not substitute offline fixtures for the live demo or fill missing metrics with estimates.

| Time | Screen | Narration / evidence |
|---|---|---|
| 0:00–0:18 | Real saved CUDA OOM and training command | “A GPU can have enough memory for the model and still run out during training. The missing detail is what was alive at the peak.” |
| 0:18–0:45 | Home and architecture | “Headroom investigates the evidence and tests a repair. It is built with NVIDIA Nemotron 3 Ultra, Super and Nano served by Nebius Token Factory, with web research powered by Tavily.” Use this only after the model calls are actually verified. |
| 0:45–1:10 | Chosen real run, baseline timeline and expanded stack | Show original workload, captured peak and source evidence. State actual evidence-token count; do not claim a million-token request without its saved probe. |
| 1:10–1:35 | Ultra diagnosis, versioned Tavily Sources and Super diff | Explain one evidence-linked cause and the exact code/config change. Model badges and usage must match recorded calls. |
| 1:35–2:05 | Verification and retained/reverted rounds | Show before/after memory, unchanged parameter count, numerical state and any speed cost. Explain a failed candidate if present. |
| 2:05–2:30 | Main results and ablation table | Insert verified scenario counts and conditions from RESULTS. If those evaluations are incomplete, omit the claim and describe the remaining test. |
| 2:30–2:50 | Patch/report downloads and closing | “The output is a patch you can inspect and evidence you can rerun. The goal is to make memory optimization measurable.” |

Capture at 1080p with readable type. Use no unlicensed music or third-party logo assets. Owner records/uploads the video, verifies a Public link and submits it; this file performs none of those actions. Store source media only under server docs/media/.
