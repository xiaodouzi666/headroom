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

**Do not turn the following into past-tense achievements yet:** accepted automated scenario repairs, benchmark success rates or ablation gains. Diagnosis v5 matched 7/8 first causes but did not pass full policy/plan acceptance. A generic Super docstring patch applied and compiled after bounded repair; it contributes zero memory-repair benchmark successes. MVP v1/v2/v3 failures are preserved. The final permitted MVP v4 iteration is finished: 0/9 targets and 7/9 first-cause matches. Original repair iterations are exhausted; further repair work awaits the owner's decision under PLAN section0.6.

## Challenges and learning

Allocator categories are heuristics with recorded coverage. A large reserved-minus-allocated gap alone does not prove harmful fragmentation. An unknown numerical comparison or API charge must remain unknown. Source preservation and partial reports make failure useful evidence.

## What's next

Review the completed failed MVP audit and obtain the owner's decision on any extra repair iteration under the original PLAN section0.6 stop rule. Main/ablation campaigns, qualifying repair replays, public deployment and the demo video remain subject to their original acceptance gates; no outcome is promised.

## Submission checklist

- Track: Coding and Agentic Engineering, to be verified against the current form.
- Repository: https://github.com/xiaodouzi666/headroom
- Public demo: pending approved domain/deployment.
- Public video: pending verified repair and owner recording.
- Insert only measured RESULTS and actual provider feedback.
- Owner review, terms acknowledgment, draft save and final submission remain separate actions. Nothing has been saved or submitted to Devpost by this draft.


## Latest measured readiness — 2026-10-25

The final original MVP iteration executed all nine scenarios: 0/9 targets met, 7/9 first causes matched, 2/8 synthetic scenes applied and compiled. One retained candidate completed20 steps and reduced peak3.556%, below20%; this is not a successful target repair. Full coverage/accuracy of Nano labels and the two required Tavily Sources gates remain incomplete despite genuine service calls/cache. Backend2026 tests and baseline HomeLighthouse99 do not replace real repair acceptance. Draft only: no public submission or deployment has occurred.
