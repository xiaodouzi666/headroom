# Devpost draft — not ready to submit

Working title: **Headroom — autoresearch for GPU memory**

One line: Give Headroom a PyTorch workload and a memory target; it captures allocator evidence, proposes a focused patch, and checks the tradeoff on real hardware.

## Inspiration

An out-of-memory traceback tells an engineer where an allocation failed, but not which combination of activations, optimizer state, temporary buffers and retained graphs made the workload run out of room. Headroom is designed to turn that investigation into a repeatable, inspectable loop.

## What it does

Headroom packages memory history and relevant source, routes diagnosis to NVIDIA Nemotron 3 Ultra on Nebius Token Factory, uses Super for bounded patches and Nano for stack labels, and retrieves version-specific documentation through Tavily. Candidates are run in an isolated GPU Lab. Their memory, numerical behavior, parameter count and timing checks determine whether the search keeps or reverts them.

## How we built it

Python, PyTorch allocator traces, Docker, SQLite, FastAPI/SSE, React/TypeScript, Tailwind, Recharts and diff2html. Every run records evidence, usage and intermediate decisions. Local accounting reserves spend before each model attempt and preserves unknown charges.

## Verified so far

RESULTS records real GPU baselines, sandbox checks, Tavily search/extract/cache reuse, all 60 prescribed T0.4 probe outcomes and the T1.3 client gate. Ultra handled 500,029 measured input tokens and a separate 268,920-token authentic evidence request. The former is a tested lower bound, not the exact maximum or proof of the advertised 1M context; the 900k/429 outcome retains its unknown charge conservatively. The three-scenario Docker-contained independent subprocess comparison passed with 0% peak differences. The development app's existing replays remain clearly labeled baselines.

Final MVP v7 measured 1/9 target success (s8) and 6/9 raw first causes (4 valid, 3 failed, 2 unknown). Its patch kept an unused teacher on CPU: 20 updates, 96.071422% lower GPU peak, identical observed scalar losses and unchanged parameter count. Full workload pairing remains unknown, so this is the original scalar gate, not proof of full mathematical equivalence. Earlier v6 s3 evidence is separately preserved. Overall MVP and main/ablation acceptance remain failed or pending; the three additional iterations are exhausted.

## Challenges and learning

Allocator categories are heuristics with recorded coverage. A large reserved-minus-allocated gap alone does not prove harmful fragmentation. An unknown numerical comparison or API charge must remain unknown. Source preservation and partial reports make failure useful evidence.

## What's next

Review the completed v7 audit and choose the next bounded scope under the original PLAN section0.6 stop rule; see reports/final-decision-20261025-v7.md. Main/ablation campaigns, qualifying repair replays, public deployment and the demo video remain subject to their original acceptance gates; no outcome is promised.

## Submission checklist

- Track: Coding and Agentic Engineering, to be verified against the current form.
- Repository: https://github.com/xiaodouzi666/headroom
- Public demo: pending approved domain/deployment.
- Public video: one verified repair is available; owner recording pending.
- Insert only measured RESULTS and actual provider feedback.
- Owner review, terms acknowledgment, draft save and final submission remain separate actions. Nothing has been saved or submitted to Devpost by this draft.


## Latest measured readiness — 2026-10-25

Final MVP v7: 1/9 targets, 6/9 raw first causes (4 valid), 3/8 synthetic scenes applied and compiled. Source-span and literal CLI evidence are complete, but overall target and all-zero CLI gates fail. Backend 2,218 tests passed. Required Nano/Sources, full UI repair flow, main evaluation, qualifying replays, public demo and video remain incomplete. Draft only: no public submission or deployment has occurred.
