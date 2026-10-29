# F5 environment recovery — independent live check

**The environment problem is resolved, and the clean checkout executed its GPU and model workflow. It did not produce a successful repair.**

| Observation | Result |
| --- | --- |
| Recovery run | bd5bc2173ef1452aaabebcd5fd76bfb3 |
| Source revision | 254b92eee53458894d50db1c924b1d2797810a35 |
| Original preserved run | 01b872b7d4e24bd9a1109827777e4529 |
| Clean checkout | Own installed CLI and package, 127 bound files matched; Git status clean |
| GPU baseline | CUDA, completed 20 updates, capture and cleanup verified |
| Baseline peak | 2,435,717,632 bytes (2.435717632 decimal GB) |
| Model calls | 3: Nano annotation ×1, Ultra diagnosis ×2 |
| Final result | needs_human; diagnosis requests additional information; target_met=false |
| Patch / after-run | None / none |
| Wall time | 44.3630433769431 seconds, within the 480-second limit |
| Actual net model cost | $0.075498372, known and settled |
| Both F5 attempts combined | $0.075498372, within the $0.30 cap |

The original attempt remains a zero-call, zero-cost environment failure. Its claim, parent and child rows exactly match the preserved proposal snapshot; its budget has no attempts and remains closed without a halt. All original report-artifact hashes still match. The recovery uses a distinct run and once record in the same pool, profile and daily limit. Its queued request and workload hashes equal the original; only the explicitly reviewed source revision/pins changed.

The recovery invoked the clean checkout's own installed console. Its CUDA baseline completed 20 updates and **already satisfied fix-oom**. This does not count as a new repair achievement. No candidate was generated or retained, and there is no after-run or numerical comparison.

The first Ultra response was truncated, with a retained finish_reason of length. The existing diagnosis flow made one supplementary request. Its final diagnosis was valid but not ready for a patch: it requested missing optimizer-input/effective-batch observations and clarification of the cited source. The workflow therefore stopped as needs_human instead of changing the workload without adequate evidence.

Cleanup and settlement are verified. This establishes that the private-file prerequisite no longer blocks the clean CLI → GPU capture → model/report chain; it does not establish successful repair or retroactively change the original result. No further retry was performed by this audit.

[recovery-receipt.json](recovery-receipt.json) records the exact metadata and source hashes. The earlier [live.md](live.md) and live-receipt.json are unchanged. This inspection did not read credential values or modify the runtime, controller, proposal, clean checkout or ledger.
