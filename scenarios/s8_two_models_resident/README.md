# Disabled reference model remains resident on the GPU

Status: full default GPU baseline measured on 2026-10-23; see the measurement below.

Ground truth: a student classifier trains with ordinary cross entropy while `distillation_weight=0`. The large reference teacher is nevertheless eagerly initialized on the same GPU and kept live for the whole run. Its parameters are frozen and it does not execute in the selected configuration. The teacher is a real compatible classifier, not a filler tensor.

Default: batch 32, 512 input features, 256 classes, width-1024 three-layer student, width-8192 twelve-layer teacher, fp32, student-only AdamW, 20 updates. Intended mode is `reclaim`. Teacher parameter-size arithmetic is approximately **2.77 GiB**; the historical anticipated total allocated peak was **2.8–3.5 GiB**, a planning estimate. The exact teacher byte count is emitted at runtime. The default run completed all 20 updates in 9.388 s with a measured allocated peak of 2.840601 GiB; exact counters and evidence are below.

Expected repair classes: keep the reference model on CPU when distillation is disabled, or load/offload it according to actual usage. Preserve the teacher architecture and student objective; removing model structure to game parameter-count checks is not a valid repair. CPU placement can preserve all parameters while avoiding GPU residency. Initialization uses the same ordered CPU RNG stream regardless of final placement so a placement-only repair can preserve the student's initial weights and synthetic data.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Flags: `--batch`, `--steps` (20), `--device`, `--tiny`, `--seed`. Tiny mode retains the unused second model. JSON Lines report teacher bytes, total parameters, losses, timing and CUDA byte metrics (null for CPU GPU-memory fields). OOM is summarized then re-raised with traceback.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `completed_20_steps`;
completed training steps: 20; runtime including container startup
but excluding cleanup: 9.388 s.

- Peak allocated: **2.840601 GiB** (3050072064 bytes).
- Peak reserved: **2.851562 GiB** (3061841920 bytes).
- Source SHA-256: `5a64c4300c2a3bc1b6005d2102f13c86c0afe348a0799b9541adddded6ad6b59`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s8_two_models_resident/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
