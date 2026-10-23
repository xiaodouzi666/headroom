# Disabled reference model remains resident on the GPU

Status: source preparation only, **not calibrated on the 24 GiB GPU**. No measured peak or acceptance pass is claimed.

Ground truth: a student classifier trains with ordinary cross entropy while `distillation_weight=0`. The large reference teacher is nevertheless eagerly initialized on the same GPU and kept live for the whole run. Its parameters are frozen and it does not execute in the selected configuration. The teacher is a real compatible classifier, not a filler tensor.

Default: batch 32, 512 input features, 256 classes, width-1024 three-layer student, width-8192 twelve-layer teacher, fp32, student-only AdamW, 20 updates. Intended mode is `reclaim`. Teacher parameter-size arithmetic is approximately **2.77 GiB**; anticipated total allocated peak is **2.8–3.5 GiB**, unmeasured. The exact teacher byte count is emitted at runtime. Actual peak and 20-step runtime await calibration.

Expected repair classes: keep the reference model on CPU when distillation is disabled, or load/offload it according to actual usage. Preserve the teacher architecture and student objective; removing model structure to game parameter-count checks is not a valid repair. CPU placement can preserve all parameters while avoiding GPU residency. Initialization uses the same ordered CPU RNG stream regardless of final placement so a placement-only repair can preserve the student's initial weights and synthetic data.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Flags: `--batch`, `--steps` (20), `--device`, `--tiny`, `--seed`. Tiny mode retains the unused second model. JSON Lines report teacher bytes, total parameters, losses, timing and CUDA byte metrics (null for CPU GPU-memory fields). OOM is summarized then re-raised with traceback.
