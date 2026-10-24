# Web interface

The frontend is a Vite + React + TypeScript application with Tailwind CSS, Recharts, and diff2html. All package files, dependencies, build output, and any later screenshots remain on azuki. The web interface reports recorded backend results; rendering a report does not establish a successful repair.

## Build and local development

The verified official Node.js v24.22.1 installation is under the ignored project directory `.tools/node-web/current`. Use an already compatible Node installation or add that directory to PATH:

```sh
cd /home/xiaodouzi/workspace/headroom/web
export PATH=/home/xiaodouzi/workspace/headroom/.tools/node-web/current/bin:$PATH
npm ci --no-audit --no-fund
npm run typecheck
npm test
npm run build
```

`web/dist` is generated and ignored. The Python API can serve that build and its SPA paths from the same origin. The preferred acceptance deployment is this single-origin arrangement. For development only, `npm run dev` binds 127.0.0.1 and proxies `/api` to `http://127.0.0.1:8000`; set `HEADROOM_API_PROXY` to another loopback API URL when needed. The proxy deliberately retains `changeOrigin: false` so that browser Origin and forwarded Host match the API's same-origin protection.

`npm run preview` serves only the static build on loopback and is not a replacement for the API. No frontend command configures a public listener, uploads a project, or requests a provider API key.

## Pages and backend contract

- **Workspace / Home**: fetches the actual example catalog and curated replay list. Users can choose one example or paste one Python script, then select Fix OOM, Fit in a decimal GB target, or Reclaim headroom. Policy controls map directly to the request policy. The per-run budget remains a JSON string. There is no key entry or payment UI.
- **Run**: consumes persisted SSE events, deduplicates by sequence, shows reconnect state, refreshes run artifacts, and closes the stream on `stream.end`. A five-second detail refresh is a fallback until the terminal event. Event model, time, and charge are shown only when recorded. Run-level and per-model usage are separate from per-event metadata.
- **Results**: lists real session runs and their supplied report measurements. It is explicitly a saved-run view, not a claim that the planned evaluation campaign is complete. Report details are fetched for at most the first 50 runs in groups of four; other rows keep unknown measurements.
- **About**: describes capture, model reasoning, proposed patches, measured verification, provider roles, established related techniques, and current limits.

Requests use same-origin credentials. The UI first obtains `/api/health` before Home/Results fan-out to avoid racing initial session-cookie creation. It submits:

```json
{
  "example_id": "s1_batch_too_big",
  "target": "fit:22GB",
  "policy": {
    "allow_numerics_change": false,
    "allow_model_change": false,
    "allow_batch_grad_accum": true,
    "max_throughput_regression_pct": 25
  },
  "budget": "0.60"
}
```

`script_text` replaces `example_id` for pasted input. A queued run redirects to its returned 32-hex run ID. Fetch errors and backend rejection reasons remain visible. If the health response says Token Factory is unconfigured, Home explains that runs may end in `needs_human`; it never announces provider readiness from a key-presence indicator.

SSE uses the API's named event kinds and envelope `{sequence, kind, data, created_at}`. Browser EventSource handles its built-in Last-Event-ID reconnection. `stream.end` signifies the end of the persisted event history; it does not imply target success. Status, report verification, and API cleanup fields remain independent evidence.

## Evidence and measurement semantics

The interface adapts the actual report schema from `headroom/report.py`:

- Header/verification measurements use `report.display` strings and `report.summary`. A missing value is **Unknown**, not zero. A generated patch alone does not imply numerical equivalence or target completion.
- Charts read real `evidence.before/after.analysis.timeline` allocator points. The x-axis is allocator event index, not elapsed time. Before/after are independent captures; lines join recorded points. No synthetic curve appears while evidence is missing. Original timeline PNGs are expandable only if the API declares them.
- Composition categories use the report's byte totals and shares. Expandable stack details come from retained peak-composition evidence. Categories remain explicitly heuristic.
- Diagnostic root causes, confidence, evidence references, and expected savings are labeled model hypotheses or estimates. Reserved-minus-allocated memory is not labeled proven fragmentation.
- Unknown or pending charges keep the total **Unknown**, even if the known subtotal is zero. Known subtotal and unknown-call count are shown separately.
- Offline fixtures and historical replays have persistent visible provenance labels. An empty replay endpoint stays empty; no fabricated demo results fill the gap.

Sources are rendered as escaped React text with HTTP(S) links only and no URL credentials. Artifact links must be declared same-run API paths from a fixed allowlist. Patch text is parsed with diff2html and rendered as React text nodes; the frontend never injects the parser's generated HTML. No raw Markdown or source-page HTML is executed.

The layout uses a desktop workspace grid, responsive run columns, and a narrow-screen single column. Code and tables scroll inside their containers. It includes labeled inputs, keyboard focus treatment, a skip link, semantic headings/tables, and reduced-motion support. Interactive Chrome verification on 2026-10-24 checked Home, partial Run, baseline Replay, Results and About at 390 × 844 without page-level horizontal overflow. This does not establish a live model repair or a complete accessibility audit.

## Offline verification and acceptance boundary

The tests use injected fetch/EventSource fakes and no model, Tavily, or GPU calls. They cover measurement and fee unknowns, report adaptation, provenance, safe links, request validation, missing-provider UI, API errors, patch HTML escaping, SSE ordering/reconnect/terminal cleanup, and terminal needs-human behavior.

Local checks completed on azuki:

- TypeScript strict typecheck.
- Vitest adapter and rendered-component tests.
- Production build with lazy chart/diff chunks.

These checks do **not** complete the model-driven T3.2 acceptance. Interactive Chrome submitted a real example to the API, received a `needs_human` partial report with zero model calls, and inspected five baseline replays; see `reports/browser-validation-20261024.json`. Real repaired-run SSE and final success remain pending authenticated model access. T3.3's required repaired replays and later public-deployment gates remain unchanged.

Performance investigation retained the first failing Home Lighthouse scores, 65/66/66. The build now lets Vite split chart/diff modules at dynamic imports without eagerly preloading shared chart code on Home. The API compresses text/JSON assets with gzip while Starlette excludes `text/event-stream`; regression checks preserve immediate SSE and identical decoded content. A favicon removes the prior missing-icon request. Post-change Lighthouse results are recorded separately and do not replace the old failures.

Final performance check: `reports/lighthouse-20261024.json` records Home90/90/90 and real baseline Run89/98/89 across three fresh mobile-profile runs each (390×844,DPR2). All six exceed the original70 threshold. The same final build passed27 frontend tests, strict typecheck and production build. Eight actual desktop/mobile screenshots plus hashes are in `docs/media/ui-20261024T025659Z-baseline-only/`. The baseline chart shows only Baseline; absent after-captures never gain a legend/series.

Measured caveats remain visible in the report: accessibility96 includes contrast findings; Home Speed Index remains around33seconds despite FCP/LCP below2seconds, and that discrepancy was not explained here. A passing aggregate Performance score does not establish every performance/accessibility metric or the real model repair flow.
