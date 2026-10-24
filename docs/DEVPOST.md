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

Real synthetic/repository/library GPU baseline work, CPU sandbox checks, real Tavily search/extract and cache reuse, minimal authenticated Nemotron Super/Nano chats, and offline model-client/patch/search integration are recorded in RESULTS. The development app includes clearly labeled baseline replays.

**Do not turn the following into past-tense achievements yet:** successful automated repairs, Ultra or long-input capability, repair-cost benchmarks, benchmark success rates, or ablation gains. Two bounded chat probes establish connectivity and their observed usage only; they do not establish the application's complete provider integration. The full capability and repair evaluations remain pending.

## Challenges and learning

Allocator categories are heuristics with recorded coverage. A large reserved-minus-allocated gap alone does not prove harmful fragmentation. An unknown numerical comparison or API charge must remain unknown. Source preservation and partial reports make failure useful evidence.

## What's next

Complete the reviewed Token Factory probe, execute the main and ablation campaigns, curate successful repair replays, and finish public deployment and the demo video.

## Submission checklist

- Track: Coding and Agentic Engineering, to be verified against the current form.
- Repository: https://github.com/xiaodouzi666/headroom
- Public demo: pending approved domain/deployment.
- Public video: pending verified repair and owner recording.
- Insert only measured RESULTS and actual provider feedback.
- Owner review, terms acknowledgment, draft save and final submission remain separate actions. Nothing has been saved or submitted to Devpost by this draft.
