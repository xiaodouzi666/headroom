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

MVP v6 verified one automated repair: s3 completed 20 updates with 73.378694% lower peak memory, identical recorded losses and unchanged parameter count. All nine cases ran; the overall score remains 1/9, below the original 6/9 gate. Raw first-cause agreement is 7/9 (six valid, one invalid, two unknown). Do not present the project as having passed MVP, main benchmarks or ablations. The final authorized v7 extension is undergoing regression; its live result is still pending.

## Challenges and learning

Allocator categories are heuristics with recorded coverage. A large reserved-minus-allocated gap alone does not prove harmful fragmentation. An unknown numerical comparison or API charge must remain unknown. Source preservation and partial reports make failure useful evidence.

## What's next

Finish the final authorized v7 campaign and audit; if it still fails, return the concrete results for the owner's decision under the original PLAN section0.6 stop rule. Main/ablation campaigns, qualifying repair replays, public deployment and the demo video remain subject to their original acceptance gates; no outcome is promised.

## Submission checklist

- Track: Coding and Agentic Engineering, to be verified against the current form.
- Repository: https://github.com/xiaodouzi666/headroom
- Public demo: pending approved domain/deployment.
- Public video: one verified repair is available; owner recording pending.
- Insert only measured RESULTS and actual provider feedback.
- Owner review, terms acknowledgment, draft save and final submission remain separate actions. Nothing has been saved or submitted to Devpost by this draft.


## Latest measured readiness — 2026-10-25

Latest completed MVP v6: 1/9 targets, 7/9 raw first causes (six valid), 3/8 synthetic scenes applied and compiled. The s3 repair passes its original target and independent >=30% reduction gate. Full Nano coverage/accuracy, required Tavily Sources, main evaluation, qualifying replay set and public delivery remain incomplete. Final v7 is pending. Draft only: no public submission or deployment has occurred.
