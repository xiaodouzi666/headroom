import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  Download,
  Layers3,
  Play,
  Terminal,
  FileCode2,
  Check,
  Cpu,
  ShieldCheck,
  SquareArrowOutUpRight,
} from "lucide-react";
import { getJSON, getText, submitRun } from "./api";
import EvaluationView from "./EvaluationView";
import {
  analysisOf,
  availabilityBlocks,
  artifactLink,
  costTotal,
  costUpperBound,
  configurationLink,
  displayMetric,
  EVENT_KINDS,
  externalLink,
  gb,
  human,
  measurement,
  mergeEvents,
  numeric,
  parseEvent,
  provenanceLabel,
  queueAtCapacity,
  record,
  rows,
  text,
  usd,
  validateSubmission,
  searchModeLabel,
  type SearchMode,
  verificationRows,
  type Dict,
  type RunEvent,
  type Submission,
} from "./data";
import {
  Badge,
  Empty,
  External,
  Loading,
  Metric,
  Notice,
  Section,
  Status,
} from "./components";
const MemoryChart = lazy(() => import("./MemoryChart"));
const DiffView = lazy(() => import("./DiffView"));
const hrefRun = (id: unknown, replay = false) =>
  `/runs/${encodeURIComponent(text(id, ""))}${replay ? "?replay=1" : ""}`;
function Brand() {
  return (
    <a href="/" className="brand" aria-label="Headroom home">
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      headroom<span className="brand-beta">LAB</span>
    </a>
  );
}
function Navigation() {
  const path = window.location.pathname;
  return (
    <header className="site-header">
      <div className="nav-shell">
        <Brand />
        <nav aria-label="Main navigation">
          <a href="/" aria-current={path === "/" ? "page" : undefined}>
            Workspace
          </a>
          <a
            href="/results"
            aria-current={path === "/results" ? "page" : undefined}
          >
            Results
          </a>
          <a
            href="/about"
            aria-current={path === "/about" ? "page" : undefined}
          >
            About
          </a>
        </nav>
        <span className="nav-note">
          <span className="status-dot" />
          Evidence first
        </span>
      </div>
    </header>
  );
}
function Footer() {
  return (
    <footer className="site-footer">
      <span>Headroom · GPU memory, made visible.</span>
      <a href="/about">
        How it works <ArrowUpRight size={13} />
      </a>
    </footer>
  );
}
function ProviderBadge() {
  return (
    <div className="provider-badge">
      <Cpu size={14} />
      <span>Powered by NVIDIA Nemotron 3 on Nebius Token Factory</span>
      <span className="provider-separator">/</span>
      <span>Research by Tavily</span>
    </div>
  );
}

function Home() {
  const [examples, setExamples] = useState<Dict[]>([]),
    [replays, setReplays] = useState<Dict[]>([]),
    [health, setHealth] = useState<Dict>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [mode, setMode] = useState<"example" | "script">("example"),
    [example, setExample] = useState(""),
    [script, setScript] = useState(""),
    [target, setTarget] = useState("fix-oom"),
    [fit, setFit] = useState("22"),
    [budget, setBudget] = useState("0.60"),
    [searchMode, setSearchMode] = useState<SearchMode>("until_target"),
    [precision, setPrecision] = useState(false),
    [batch, setBatch] = useState(true),
    [slowdown, setSlowdown] = useState("25"),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const h = await getJSON("/api/health", controller.signal);
        setHealth(h);
        const [e, r] = await Promise.all([
          getJSON("/api/examples", controller.signal),
          getJSON("/api/replays", controller.signal),
        ]);
        setExamples(rows(e.examples));
        setReplays(rows(r.replays));
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Could not reach the API.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    const refresh = window.setInterval(async () => {
      try {
        setHealth(await getJSON("/api/health", controller.signal));
      } catch {
        if (!controller.signal.aborted)
          setHealth((previous) => ({
            ...previous,
            gpu: { status: "unknown", available: null, busy: null },
            local_budget: { status: "unknown", remaining_usd: null },
          }));
      }
    }, 15000);
    return () => {
      controller.abort();
      window.clearInterval(refresh);
    };
  }, []);
  const queue = record(health.queue),
    provider = record(health.token_factory);
  const queueFull = queueAtCapacity(queue);
  const availability = availabilityBlocks(health);
  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const payload: Submission = {
      ...(mode === "example"
        ? { example_id: example }
        : { script_text: script }),
      target: target === "fit" ? `fit:${fit}GB` : target,
      budget,
      search_mode: searchMode,
      policy: {
        allow_numerics_change: precision,
        allow_model_change: false,
        allow_batch_grad_accum: batch,
        max_throughput_regression_pct: Number(slowdown),
      },
    };
    const invalid = validateSubmission(payload);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    try {
      const run = await submitRun(payload);
      window.location.assign(hrefRun(run.run_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
      setBusy(false);
    }
  }
  return (
    <main className="page home-page">
      <div className="hero">
        <div>
          <p className="eyebrow">
            <span className="small-line" />A little room goes a long way
          </p>
          <h1>
            Your model fits.
            <br />
            <span>Let’s find the space.</span>
          </h1>
          <p className="hero-description">
            Turn a PyTorch memory problem into a clear diagnosis, a reviewable
            patch, and a measured result.
          </p>
          <ProviderBadge />
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="visual-top">
            <span>MEMORY / UNDERSTOOD</span>
            <Layers3 size={18} />
          </div>
          <div className="memory-blocks">
            <div className="memory-block block-a">parameters</div>
            <div className="memory-block block-b">optimizer</div>
            <div className="memory-block block-c">activations</div>
            <div className="memory-block block-d">
              <span>headroom</span>
              <ArrowUpRight size={24} />
            </div>
          </div>
          <div className="visual-bottom">
            CAPTURE <span>→</span> UNDERSTAND <span>→</span> VERIFY
          </div>
        </div>
      </div>
      {error && <Notice tone="red">{error}</Notice>}
      {!loading && provider.configured === false && (
        <Notice>
          <strong>Live analysis is not enabled yet.</strong> Runs may pause
          while model readiness checks are completed.{" "}
          {replays.length > 0 && (
            <a href="#replays">Explore saved evidence instead →</a>
          )}
        </Notice>
      )}
      {queueFull && (
        <Notice>
          The run queue is currently unavailable. Saved replays remain available
          below.
        </Notice>
      )}
      {availability.gpuBusy && (
        <Notice>
          <strong>The GPU is busy.</strong> A compute workload is active.{" "}
          {replays.length > 0 ? (
            <a href="#replays">Explore saved evidence while you wait →</a>
          ) : (
            "Availability will refresh automatically."
          )}
        </Notice>
      )}
      {availability.budgetBlocked && (
        <Notice>
          <strong>
            {availability.budgetReason === "exhausted"
              ? "The local run budget is exhausted."
              : availability.budgetReason === "pending_charge"
                ? "Waiting for the current model charge."
                : "Model billing needs review."}
          </strong>{" "}
          {availability.budgetReason === "exhausted"
            ? "The application's authorized limit has been reached."
            : availability.budgetReason === "pending_charge"
              ? "Further calls pause until it settles. Availability refreshes automatically."
              : "An earlier call has an unresolved charge or exceeded its budget reservation."}{" "}
          {replays.length > 0 && (
            <a href="#replays">Explore saved evidence instead →</a>
          )}
        </Notice>
      )}
      <form onSubmit={start} className="workspace-grid">
        <section className="panel source-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">01 / Start with your workload</p>
              <h2>What needs more room?</h2>
            </div>
            <FileCode2 size={22} className="muted" />
          </div>
          <div className="segmented" role="group" aria-label="Source type">
            <button
              type="button"
              aria-pressed={mode === "example"}
              onClick={() => setMode("example")}
            >
              Use an example
            </button>
            <button
              type="button"
              aria-pressed={mode === "script"}
              onClick={() => setMode("script")}
            >
              Paste a script
            </button>
          </div>
          {mode === "example" ? (
            loading ? (
              <Loading>Loading available scenarios…</Loading>
            ) : examples.length ? (
              <div className="example-grid">
                {examples.map((row, index) => (
                  <button
                    key={text(row.id)}
                    type="button"
                    className={`example-card ${example === row.id ? "selected" : ""}`}
                    onClick={() => setExample(text(row.id, ""))}
                    aria-pressed={example === row.id}
                  >
                    <div className="example-top">
                      <span className="example-number">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      {example === row.id ? (
                        <Check size={17} />
                      ) : (
                        <ArrowUpRight size={16} />
                      )}
                    </div>
                    <strong>{text(row.title)}</strong>
                    <p>
                      {text(
                        row.root_cause,
                        "Inspect the runtime memory capture for this workload.",
                      )}
                    </p>
                    <span className="example-meta">
                      {human(row.expected_mode)} ·{" "}
                      {row.baseline_verified === true
                        ? "baseline recorded"
                        : "baseline status unknown"}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <Empty title="No examples available">
                Connect the local API to load the actual scenario catalog.
              </Empty>
            )
          ) : (
            <div className="script-field">
              <label htmlFor="script">Python training script</label>
              <textarea
                id="script"
                spellCheck={false}
                value={script}
                onChange={(e) => setScript(e.target.value)}
                placeholder="Paste your PyTorch script here…"
                aria-describedby="script-note"
              />
              <p id="script-note" className="caption">
                Single GPU · Python / PyTorch · maximum 1 MiB. Remove
                credentials before sharing a script.
              </p>
            </div>
          )}
        </section>
        <aside className="panel configure-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">02 / Define the goal</p>
              <h2>Find your headroom</h2>
            </div>
          </div>
          <fieldset className="goal-options">
            <legend className="sr-only">Memory target</legend>
            {[
              [
                "fix-oom",
                "Fix out of memory",
                "Complete the workload successfully.",
              ],
              ["fit", "Fit a memory budget", "Stay within a target peak."],
              [
                "reclaim",
                "Reclaim headroom",
                "Reduce peak usage while preserving behavior.",
              ],
            ].map(([value, title, description]) => (
              <label
                className={`goal ${target === value ? "active" : ""}`}
                key={value}
              >
                <input
                  type="radio"
                  name="target"
                  value={value}
                  checked={target === value}
                  onChange={() => setTarget(value)}
                />
                <span>
                  <strong>{title}</strong>
                  <small>{description}</small>
                </span>
              </label>
            ))}
          </fieldset>
          {target === "fit" && (
            <label className="field">
              Target memory{" "}
              <span className="input-affix">
                <input
                  aria-label="Target memory in GB"
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={fit}
                  onChange={(e) => setFit(e.target.value)}
                />
                <span>GB</span>
              </span>
            </label>
          )}
          <div className="rule" />
          <p className="field-heading">Preserve what matters</p>
          <label className="toggle-row">
            <span>
              Allow precision changes
              <small>Always reported in the result.</small>
            </span>
            <input
              type="checkbox"
              checked={precision}
              onChange={(e) => setPrecision(e.target.checked)}
            />
          </label>
          <label className="toggle-row">
            <span>
              Allow batch / accumulation changes
              <small>Keep samples per update comparable.</small>
            </span>
            <input
              type="checkbox"
              checked={batch}
              onChange={(e) => setBatch(e.target.checked)}
            />
          </label>
          <div className="field-row">
            <label className="field">
              Max. step slowdown
              <span className="input-affix">
                <input
                  type="number"
                  min="0"
                  max="1000"
                  value={slowdown}
                  onChange={(e) => setSlowdown(e.target.value)}
                />
                <span>%</span>
              </span>
            </label>
            <label className="field">
              Run budget
              <span className="input-affix">
                <span>$</span>
                <input
                  aria-label="Run budget in USD"
                  type="number"
                  min="0.01"
                  max="5"
                  step="0.01"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                />
              </span>
            </label>
          </div>
          <label className="field">
            Search mode
            <select
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value as SearchMode)}
              aria-describedby="search-mode-note"
            >
              <option value="until_target">Stop when target is met</option>
              <option value="bounded_pareto">
                Explore more configurations
              </option>
            </select>
          </label>
          <p id="search-mode-note" className="caption">
            Exploration can continue after a successful fix, up to six rounds
            within the same time, budget and policy limits. Verified results are
            kept if a later attempt stops.
          </p>
          <p className="caption">
            Model structure stays unchanged. Costs and any unresolved charges
            appear in the run report.
          </p>
          <button
            className="button button-primary start-button"
            type="submit"
            disabled={
              busy ||
              loading ||
              queueFull ||
              availability.gpuBusy ||
              availability.budgetBlocked
            }
          >
            {busy ? "Starting…" : "Start analysis"}
            <ArrowRight size={18} />
          </button>
        </aside>
      </form>
      <section className="how-strip">
        <div>
          <span>01</span>
          <strong>Capture the evidence</strong>
          <p>Reproduce the workload and record allocator history.</p>
        </div>
        <div>
          <span>02</span>
          <strong>Explain the memory</strong>
          <p>Connect peak allocations to code and propose a focused change.</p>
        </div>
        <div>
          <span>03</span>
          <strong>Verify the tradeoff</strong>
          <p>Compare memory, speed, and numerical behavior on hardware.</p>
        </div>
      </section>
      <section id="replays" className="replay-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Recorded, not simulated</p>
            <h2>Explore saved runs</h2>
          </div>
          <a className="text-link" href="/results">
            All results <ArrowRight size={16} />
          </a>
        </div>
        {replays.length ? (
          <div className="replay-grid">
            {replays.map((run) => (
              <a
                key={text(run.run_id)}
                className="replay-card"
                href={hrefRun(run.run_id, true)}
              >
                <div>
                  <Badge>Saved replay</Badge>
                  <Play size={17} />
                </div>
                <strong>{human(run.target)}</strong>
                <p>
                  {text(
                    run.reason,
                    "Inspect the retained evidence and outcome.",
                  )}
                </p>
                <Status value={run.status} />
              </a>
            ))}
          </div>
        ) : (
          <p className="muted">
            No curated replays are available yet. Completed runs will appear
            when their evidence is ready to share.
          </p>
        )}
      </section>
    </main>
  );
}

function RunPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<Dict>({}),
    [report, setReport] = useState<Dict>({}),
    [evidence, setEvidence] = useState<Dict>({}),
    [events, setEvents] = useState<RunEvent[]>([]),
    [diff, setDiff] = useState<string | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [stream, setStream] = useState("Connecting");
  const replay =
    new URLSearchParams(window.location.search).get("replay") === "1";
  useEffect(() => {
    const controller = new AbortController();
    let source: EventSource | undefined,
      closed = false,
      inflight = false,
      ended = false,
      refreshPending = false,
      timer: ReturnType<typeof setTimeout> | undefined;
    let evidenceLoaded = false;
    async function refresh() {
      if (closed) return;
      if (inflight) {
        refreshPending = true;
        return;
      }
      inflight = true;
      try {
        const current = await getJSON(`/api/runs/${runId}`, controller.signal);
        if (closed) return;
        setRun(current);
        const r = artifactLink(runId, "report.json", current.artifacts),
          p = artifactLink(runId, "patch.diff", current.artifacts),
          e = artifactLink(runId, "evidence.json", current.artifacts);
        const jobs: Promise<void>[] = [];
        if (r)
          jobs.push(
            getJSON(r, controller.signal).then((value) => {
              if (!closed) setReport(value);
            }),
          );
        if (p)
          jobs.push(
            getText(p, controller.signal).then((value) => {
              if (!closed) setDiff(value);
            }),
          );
        if (e && !evidenceLoaded)
          jobs.push(
            getJSON(e, controller.signal).then((value) => {
              evidenceLoaded = true;
              if (!closed) setEvidence(value);
            }),
          );
        await Promise.all(jobs);
        if (!closed) setError("");
      } catch (e) {
        if (!closed)
          setError(e instanceof Error ? e.message : "Could not load this run.");
      } finally {
        inflight = false;
        if (!closed) setLoading(false);
        if (refreshPending && !closed) {
          refreshPending = false;
          void refresh();
        }
      }
    }
    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void refresh(), 250);
    }
    void refresh().then(() => {
      if (closed) return;
      source = new EventSource(`/api/runs/${runId}/events`, {
        withCredentials: true,
      });
      source.onopen = () => setStream("Connected");
      source.onerror = () => {
        if (!closed) setStream("Reconnecting");
      };
      for (const kind of EVENT_KINDS) {
        source.addEventListener(kind, (message) => {
          try {
            const event = parseEvent(
              JSON.parse((message as MessageEvent).data),
            );
            if (event && !closed)
              setEvents((previous) => mergeEvents(previous, event));
            schedule();
          } catch {
            if (!closed) setStream("Invalid event received");
          }
        });
      }
      source.addEventListener("stream.end", () => {
        ended = true;
        setStream("Complete");
        source?.close();
        schedule();
      });
    });
    const poll = setInterval(() => {
      if (!closed && !ended) void refresh();
    }, 5000);
    return () => {
      closed = true;
      controller.abort();
      source?.close();
      clearInterval(poll);
      if (timer) clearTimeout(timer);
    };
  }, [runId]);
  const label = provenanceLabel(run, replay),
    usage = record(run.usage),
    before = analysisOf(report, "before", evidence),
    after = analysisOf(report, "after"),
    diagnosis = record(report.diagnosis),
    causes = rows(diagnosis.root_causes),
    allocator = record(report.allocator),
    search = record(report.search),
    summary = record(report.summary);
  const downloads = [
    "patch.diff",
    "cli.json",
    "configuration.json",
    "report.md",
    "report.json",
    "env.sh",
    "pareto.json",
    "pareto.md",
    "annotations.json",
  ]
    .map((name) => ({ name, url: artifactLink(runId, name, run.artifacts) }))
    .filter((item) => item.url);
  return (
    <main className="page run-page">
      <div className="run-title">
        <div>
          <a href="/" className="back-link">
            Workspace <ChevronRight size={13} />
          </a>
          <p className="eyebrow">Run / {runId.slice(0, 8)}</p>
          <h1>{human(run.target || "Memory analysis")}</h1>
          <div className="run-badges">
            <Status value={run.status} />
            {label && <Badge tone="amber">{label}</Badge>}
            <span className="caption">
              {stream === "Complete" ? "Event history complete" : stream}
            </span>
          </div>
        </div>
        <div className="download-actions">
          {downloads.map((item) => (
            <a
              className="button button-secondary"
              key={item.name}
              href={item.url!}
              download
            >
              <Download size={14} />
              {item.name}
            </a>
          ))}
        </div>
      </div>
      {error && <Notice tone="red">{error}</Notice>}
      {run.status === "needs_human" && (
        <Notice>
          <strong>This run needs attention.</strong>{" "}
          {text(
            run.reason,
            "A required condition is unavailable. Inspect the report before continuing.",
          )}
        </Notice>
      )}
      {label && (
        <Notice tone="neutral">
          {label}. This view does not start a new GPU run or make a new model
          request.
        </Notice>
      )}
      {loading ? (
        <Loading>Loading run evidence…</Loading>
      ) : (
        <>
          <div className="metric-grid">
            <Metric
              label="Peak before"
              value={displayMetric(
                report,
                "peak_before",
                measurement(report, "before", "peak_allocated_bytes") ??
                  record(before.header).peak_allocated_bytes,
              )}
              note={text(
                record(record(report.measurements).before).peak_basis,
                "Capture not yet verified",
              )}
            />
            <Metric
              label="Peak after"
              value={displayMetric(
                report,
                "peak_after",
                measurement(report, "after", "peak_allocated_bytes"),
              )}
              note={text(
                record(record(report.measurements).after).peak_basis,
                "No after measurement yet",
              )}
            />
            <Metric
              label="Peak reduction"
              value={displayMetric(report, "peak_reduction")}
              note="Derived from comparable exact captures"
            />
            <Metric
              label="Model cost"
              value={costTotal(usage)}
              note={`${numeric(usage.calls) ?? "Unknown"} calls · known subtotal ${usd(usage.known_cost_usd)}`}
            />
          </div>
          <Section title="Search outcome">
            <dl className="search-details">
              <div>
                <dt>Mode</dt>
                <dd>{searchModeLabel(search.mode ?? run.search_mode)}</dd>
              </div>
              <div>
                <dt>Baseline already meets target</dt>
                <dd>
                  {search.baseline_target_met === true
                    ? "Yes — before repair"
                    : search.baseline_target_met === false
                      ? "No"
                      : "Unknown"}
                </dd>
              </div>
              <div>
                <dt>Exploration status</dt>
                <dd>{search.mode ? human(run.status) : "Not recorded"}</dd>
              </div>
              <div>
                <dt>Stopped because</dt>
                <dd>{human(search.stop_reason)}</dd>
              </div>
              <div>
                <dt>Rounds executed</dt>
                <dd>{numeric(search.rounds_executed) ?? "Unknown"}</dd>
              </div>
              <div>
                <dt>Selected configuration meets target</dt>
                <dd>
                  {run.provenance === "recorded_baseline"
                    ? "N/A — baseline only"
                    : summary.target_met === true
                      ? "Yes"
                      : summary.target_met === false
                        ? "No"
                        : "Unknown"}
                </dd>
              </div>
              <div>
                <dt>First verified target round</dt>
                <dd>{numeric(search.first_target_met_round) ?? "Unknown"}</dd>
              </div>
            </dl>
            <p className="caption">
              Target success and exploration status are separate. A later stop
              keeps the selected verified configuration and its downloads.
              Historical runs without search metadata remain unknown.
            </p>
          </Section>
          <div className="run-grid">
            <aside className="panel timeline-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Execution log</p>
                  <h2>Every step, visible</h2>
                </div>
              </div>
              {events.length ? (
                <ol className="event-list">
                  {events.map((event, index) => (
                    <li
                      key={event.sequence}
                      className={index === events.length - 1 ? "latest" : ""}
                    >
                      <span className="event-node" />
                      <div>
                        <div className="event-title">{human(event.kind)}</div>
                        <div className="event-meta">
                          <time>
                            {event.created_at
                              ? new Date(event.created_at).toLocaleTimeString(
                                  [],
                                  {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    second: "2-digit",
                                  },
                                )
                              : "Time unknown"}
                          </time>
                          <span>#{event.sequence}</span>
                        </div>
                        {typeof event.data.model === "string" && (
                          <Badge>{event.data.model.split("/").pop()}</Badge>
                        )}
                        {typeof event.data.reason === "string" && (
                          <p>{event.data.reason}</p>
                        )}
                        {numeric(event.data.elapsed_seconds) !== null && (
                          <small>
                            {Number(event.data.elapsed_seconds).toFixed(2)}s
                          </small>
                        )}
                        {("cost_usd" in event.data || "cost" in event.data) && (
                          <small>
                            Cost{" "}
                            {usd(
                              event.data.cost_usd ??
                                record(event.data.cost).usd,
                            )}
                          </small>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <Empty title="Waiting for events">
                  Only recorded events appear here.
                </Empty>
              )}
            </aside>
            <div className="run-center">
              <Section
                title="Memory, over the run"
                kicker="Runtime evidence"
                action={<Badge>Allocator history</Badge>}
              >
                <Suspense fallback={<Loading />}>
                  <MemoryChart
                    before={before}
                    after={after}
                    baselineOnly={run.provenance === "recorded_baseline"}
                  />
                </Suspense>
                <div className="image-links">
                  {[
                    ["timeline-before.png", "Before capture"],
                    ["timeline-after.png", "After capture"],
                  ].map(([name, title]) => {
                    const url = artifactLink(runId, name, run.artifacts);
                    return url ? (
                      <details key={name}>
                        <summary>
                          {title} PNG <SquareArrowOutUpRight size={12} />
                        </summary>
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          <img
                            src={url}
                            alt={`${title} recorded memory timeline`}
                            loading="lazy"
                          />
                        </a>
                      </details>
                    ) : null;
                  })}
                </div>
              </Section>
              <Section
                title="Where the peak comes from"
                kicker="Allocation composition"
              >
                <Composition report={report} analysis={before} />
              </Section>
              <Section
                title="Proposed changes"
                kicker="Reviewable patch"
                action={
                  <Badge>{rows(report.rounds).length} recorded rounds</Badge>
                }
              >
                <Suspense fallback={<Loading />}>
                  <DiffView diff={diff ?? ""} recorded={diff !== null} />
                </Suspense>
                {rows(report.rounds).map((row, index) => (
                  <RoundDetails
                    key={index}
                    row={row}
                    index={index}
                    provenance={run.provenance}
                  />
                ))}
              </Section>
              <Section
                title="Retained configurations"
                kicker="Memory and speed tradeoffs"
              >
                {rows(record(report.pareto).frontier).length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Round</th>
                          <th>Peak</th>
                          <th>Step time</th>
                          <th>Numerics</th>
                          <th>Files</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows(record(report.pareto).frontier).map(
                          (point, index) => (
                            <tr key={index}>
                              <td>{String(point.round ?? index + 1)}</td>
                              <td>{text(point.display_peak)}</td>
                              <td>{text(point.display_step)}</td>
                              <td>{text(point.numerics)}</td>
                              <td>
                                {Object.entries(record(point.artifacts)).map(
                                  ([name, relative]) => {
                                    const url = configurationLink(
                                      runId,
                                      relative,
                                    );
                                    return url ? (
                                      <a
                                        className="text-link"
                                        key={name}
                                        href={url}
                                        download
                                      >
                                        {name}{" "}
                                      </a>
                                    ) : null;
                                  },
                                )}
                              </td>
                            </tr>
                          ),
                        )}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted small-copy">
                    No verified retained configuration yet.
                  </p>
                )}
                <p className="caption">
                  Only comparable, verified configurations establish a tradeoff.
                  Unknown or shared timing does not establish a speed advantage.
                </p>
              </Section>
              <Section
                title="Reproduce the selected configuration"
                kicker="Downloads and execution"
              >
                <p className="caption">
                  The source diff does not include CLI arguments or environment
                  changes. An empty diff can represent a CLI-only or
                  environment-only repair. Apply the patch to the original
                  source, apply env.sh changes, and use the effective target
                  arguments from cli.json. configuration.json contains the
                  selected manifest.
                </p>
                {Object.keys(record(report.selected_configuration)).length ? (
                  <>
                    <p className="caption">
                      Argument arrays preserve token boundaries; they are
                      recorded evidence, not shell commands. Null means not
                      recorded or not applicable.
                    </p>
                    <pre className="code-block">
                      {JSON.stringify(
                        Object.fromEntries(
                          Object.entries(
                            record(report.selected_configuration),
                          ).filter(([key]) => key !== "artifacts"),
                        ),
                        null,
                        2,
                      )}
                    </pre>
                    {record(report.selected_configuration).wrapper_replay !=
                      null && (
                      <p className="caption">
                        Wrapper replay requires the manifest&apos;s
                        execution_entrypoint and execution_argv, the mapped
                        source tree, effective target arguments and recorded
                        environment. Lab applies and verifies the targeted
                        override. An ordinary shell does not apply it: update
                        the launcher or configuration before running outside
                        Lab.
                      </p>
                    )}
                  </>
                ) : (
                  <p className="muted small-copy">
                    No selected configuration recorded; no replay command is
                    inferred.
                  </p>
                )}
              </Section>
              <Section title="Did the change hold up?" kicker="Verification">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>Recorded result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {verificationRows(report).map((row, i) => (
                        <tr key={i}>
                          <td>{row.label}</td>
                          <td>{row.value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="caption">
                  A generated patch is a proposal. Verification and target
                  completion are reported separately.
                </p>
              </Section>
            </div>
            <aside className="run-right">
              <Section title="The diagnosis" kicker="NVIDIA Nemotron">
                <div className="diagnosis-cards">
                  {causes.length ? (
                    causes.map((cause, index) => (
                      <article key={index}>
                        <div className="diagnosis-index">
                          {String(index + 1).padStart(2, "0")}
                        </div>
                        <h3>{text(cause.title)}</h3>
                        <p>{human(cause.category)}</p>
                        <div className="diagnosis-stat">
                          <span>Estimated size</span>
                          <strong>
                            {text(
                              cause.display_estimate,
                              typeof cause.bytes_gb === "number"
                                ? `${cause.bytes_gb} GB`
                                : "Unknown",
                            )}
                          </strong>
                        </div>
                        <p className="caption">
                          Model hypothesis · confidence{" "}
                          {text(
                            cause.display_confidence,
                            typeof cause.confidence === "number"
                              ? `${(cause.confidence * 100).toFixed(0)}%`
                              : "unknown",
                          )}
                        </p>
                        <div className="stack-refs">
                          {Array.isArray(cause.evidence_refs) &&
                            cause.evidence_refs.map((ref, i) => (
                              <code key={i}>{String(ref)}</code>
                            ))}
                        </div>
                      </article>
                    ))
                  ) : (
                    <Empty title="No diagnosis yet">
                      Root causes appear after the evidence is analyzed.
                    </Empty>
                  )}
                </div>
              </Section>
              {rows(diagnosis.plan).length > 0 && (
                <Section title="Suggested fixes" kicker="Model estimates">
                  {rows(diagnosis.plan).map((item, index) => (
                    <article className="round-note" key={index}>
                      <h3>{text(item.title)}</h3>
                      <p>{text(item.description, "No rationale recorded.")}</p>
                      <Badge>
                        Expected saving {text(item.display_expected_saving)}
                      </Badge>
                      <p className="caption">
                        Estimate only · requires measured verification
                      </p>
                    </article>
                  ))}
                </Section>
              )}
              <Section title="Allocator notes">
                <p className="small-copy">
                  {text(
                    allocator.note,
                    "Reserved memory alone does not establish fragmentation.",
                  )}
                </p>
                <dl className="key-values">
                  <div>
                    <dt>Gap indicator</dt>
                    <dd>{text(allocator.fragmentation_indicator)}</dd>
                  </div>
                  <div>
                    <dt>Fragmentation confirmed</dt>
                    <dd>
                      {allocator.fragmentation_confirmed === true
                        ? "Yes"
                        : allocator.fragmentation_confirmed === false
                          ? "No"
                          : "Unknown"}
                    </dd>
                  </div>
                </dl>
              </Section>
              <Section title="Sources" kicker="Research by Tavily">
                <Sources sources={rows(report.sources)} />
              </Section>
              <Section title="Model usage">
                <AdmissionNote usage={usage} />
                <BoundedCostNote usage={usage} />
                <div className="usage-total">
                  <span>Total recorded cost</span>
                  <strong>{costTotal(usage)}</strong>
                </div>
                {rows(usage.by_model).map((model, index) => (
                  <div className="model-row" key={index}>
                    <strong>{text(model.model).split("/").pop()}</strong>
                    <span>
                      {String(model.calls ?? "Unknown")} calls ·{" "}
                      {costTotal(model)}
                    </span>
                    <small>
                      Input {String(model.input_tokens ?? "unknown")} / output{" "}
                      {String(model.output_tokens ?? "unknown")} tokens
                    </small>
                  </div>
                ))}
                {(numeric(usage.unknown_cost_calls) ?? 0) > 0 && (
                  <p className="caption">
                    {String(usage.unknown_cost_calls)} call(s) have an{" "}
                    {(numeric(usage.bounded_cost_calls) ?? 0) > 0
                      ? "unconfirmed actual charge"
                      : "unresolved charge"}
                    . The known subtotal is not the final total.
                  </p>
                )}
              </Section>
            </aside>
          </div>
          {Array.isArray(report.warnings) && report.warnings.length > 0 && (
            <Section title="Evidence limitations">
              {report.warnings.map((warning, index) => (
                <p className="small-copy" key={index}>
                  {String(warning)}
                </p>
              ))}
            </Section>
          )}
        </>
      )}
    </main>
  );
}
function BoundedCostNote({ usage }: { usage: Dict }) {
  if ((numeric(usage.bounded_cost_calls) ?? 0) <= 0) return null;
  return (
    <p className="caption" role="note">
      Actual cost is unconfirmed for {String(usage.bounded_cost_calls)} call(s).
      Verified cost upper bound: {costUpperBound(usage)}. This bound is not a
      confirmed actual charge.
    </p>
  );
}
function AdmissionNote({ usage }: { usage: Dict }) {
  const estimated = numeric(record(usage.admission_counts).local_estimate);
  if (estimated === null || !Number.isInteger(estimated) || estimated <= 0)
    return null;
  return (
    <p className="caption" role="note">
      Budget reservations for {estimated}{" "}
      {estimated === 1 ? "call used" : "calls used"} local estimates. Actual
      cost comes from reported usage; a call can exceed its estimate.
    </p>
  );
}
function Composition({ report, analysis }: { report: Dict; analysis: Dict }) {
  const listed = rows(report.peak_composition);
  const annotationResult = record(record(report.run).annotations);
  // Historical reports lack source binding. New records use only their bound stack metadata.
  const labels = new Map(
    (annotationResult.evidence_fingerprint
      ? []
      : rows(annotationResult.annotations)
    ).map((row) => [row.stack_id, text(row.label)]),
  );
  const categories = listed.length
    ? listed
    : Object.entries(record(analysis.category_bytes)).map(
        ([category, bytes]) => ({
          category,
          bytes,
          gb: gb(bytes),
          percent_of_peak: "Unknown",
        }),
      );
  if (!categories.length)
    return (
      <Empty title="Composition unavailable">
        Allocation categories require a captured snapshot.
      </Empty>
    );
  return (
    <>
      <p className="caption">
        Heuristic allocation-origin categories. Expand a category to inspect its
        retained stacks.
      </p>
      <div className="composition-list">
        {categories.map((category, index) => (
          <details key={index}>
            <summary>
              <span className={`category-dot dot-${index % 5}`} />
              <strong>{human(category.category)}</strong>
              <span>{text(category.gb, gb(category.bytes))}</span>
              <small>{text(category.percent_of_peak)}</small>
              <ChevronRight size={14} />
            </summary>
            <div className="stack-details">
              {rows(analysis.peak_composition)
                .filter((stack) => stack.category === category.category)
                .map((stack, j) => (
                  <div className="stack-block" key={j}>
                    <div>
                      <code>{text(stack.stack_id)}</code>
                      <Badge>{gb(stack.bytes)}</Badge>
                    </div>
                    {record(stack.model_annotation).kind ===
                      "model_interpretation" &&
                    record(stack.model_annotation).is_measurement === false ? (
                      <p>
                        <Badge>Nano interpretation</Badge>{" "}
                        {text(record(stack.model_annotation).label)}
                        <small className="table-note">
                          Model category:{" "}
                          {human(record(stack.model_annotation).category)}.{" "}
                          Separate from the heuristic category and measured
                          bytes. Provenance:{" "}
                          {human(record(stack.model_annotation).provenance)}.
                        </small>
                      </p>
                    ) : labels.has(stack.stack_id) ? (
                      <p>
                        <Badge>Nano interpretation</Badge>{" "}
                        {labels.get(stack.stack_id)}
                        <small className="table-note">
                          Historical label; source binding was not recorded.
                        </small>
                      </p>
                    ) : null}
                    <pre>
                      {text(
                        stack.representative_stack,
                        rows(stack.frames)
                          .slice(-8)
                          .map(
                            (f) =>
                              `${text(f.filename)}:${String(f.line ?? "?")} in ${text(f.name)}`,
                          )
                          .join("\n") || "No frames retained.",
                      )}
                    </pre>
                  </div>
                ))}
            </div>
          </details>
        ))}
      </div>
    </>
  );
}
function Sources({ sources }: { sources: Dict[] }) {
  if (!sources.length)
    return (
      <p className="muted small-copy">No runtime research sources recorded.</p>
    );
  return (
    <ul className="sources-list">
      {sources.map((source, index) => {
        const url = externalLink(source.url);
        return (
          <li key={index}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              {url ? (
                <External href={url}>{text(source.title, url)}</External>
              ) : (
                <strong>{text(source.title, "Source unavailable")}</strong>
              )}
              {url && <small>{new URL(url).hostname}</small>}
              {source.version_match === false && (
                <small>Version applicability unverified</small>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function RoundDetails({
  row,
  index,
  provenance,
}: {
  row: Dict;
  index: number;
  provenance: unknown;
}) {
  const [expanded, setExpanded] = useState(false);
  const number =
    typeof row.number === "number" && row.number >= 1 && row.number <= 6
      ? row.number
      : index + 1;
  const verification = record(row.verification),
    display = record(row.display_verification);
  const completeDiff =
    row.diff_status === "available" && typeof row.diff === "string";
  const fields = [
    ["Completed", "completed"],
    ["Target met", "target_met"],
    ["Peak before", "peak_before"],
    ["Peak after", "peak_after"],
    ["Peak reduction", "reduction_pct"],
    ["Step time before", "step_ms_before"],
    ["Step time after", "step_ms_after"],
    ["Step-time change", "throughput_regression_pct"],
    ["Numerical equivalence", "loss_equivalence"],
    ["Comparison basis", "numerical_basis"],
    ["Comparison precision", "comparison_precision"],
    ["Loss tolerance", "loss_tolerance"],
    ["Observed precision change", "observed_precision_change"],
    ["Maximum loss difference", "max_loss_delta"],
  ];
  const show = (value: unknown) =>
    typeof value === "boolean"
      ? value
        ? "Yes"
        : "No"
      : typeof value === "number" && Number.isFinite(value)
        ? String(value)
        : text(value);
  function download() {
    if (!completeDiff) return;
    const url = URL.createObjectURL(
      new Blob([String(row.diff)], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `round-${String(number).padStart(2, "0")}.patch.diff`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <article className="round-note">
      <Badge>Round {number}</Badge>{" "}
      <strong>{human(row.decision ?? row.status)}</strong>
      <p>{text(row.reason, "No decision reason recorded.")}</p>
      {provenanceLabel({ provenance: row.provenance ?? provenance }) && (
        <p className="caption">
          {provenanceLabel({ provenance: row.provenance ?? provenance })}
        </p>
      )}
      <p className="small-copy">
        {text(row.diff_summary, "Patch summary unavailable.")}
      </p>
      {completeDiff ? (
        <>
          <button
            type="button"
            className="button button-secondary"
            onClick={download}
          >
            Download round {number} patch
          </button>
          <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
            <summary>Inspect round {number} patch</summary>
            {expanded && (
              <Suspense fallback={<Loading />}>
                <DiffView diff={String(row.diff)} recorded />
              </Suspense>
            )}
          </details>
        </>
      ) : (
        <p className="caption">
          Round patch unavailable: {text(row.diff_status)}
        </p>
      )}
      <div className="table-wrap">
        <table aria-label={`Round ${number} verification`}>
          <thead>
            <tr>
              <th>Measurement</th>
              <th>Recorded result</th>
            </tr>
          </thead>
          <tbody>
            {fields.map(([label, key]) => (
              <tr key={key}>
                <th>{label}</th>
                <td>{show(display[key] ?? verification[key])}</td>
              </tr>
            ))}
            {Object.entries(record(verification.checks)).map(
              ([name, result]) => (
                <tr key={name}>
                  <th>{human(name)}</th>
                  <td>
                    {typeof result === "boolean"
                      ? result
                        ? "Passed"
                        : "Not passed"
                      : "Unknown"}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      {Array.isArray(verification.notes) &&
        verification.notes.map((note, i) => (
          <p className="caption" key={i}>
            {String(note)}
          </p>
        ))}
    </article>
  );
}

function Results() {
  const [items, setItems] = useState<Dict[]>([]),
    [reports, setReports] = useState<Record<string, Dict>>({}),
    [usage, setUsage] = useState<Dict>({}),
    [replays, setReplays] = useState<Dict[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        await getJSON("/api/health", controller.signal);
        const [r, u, p] = await Promise.all([
          getJSON("/api/runs", controller.signal),
          getJSON("/api/usage", controller.signal),
          getJSON("/api/replays", controller.signal),
        ]);
        const list = rows(r.runs);
        setItems(list);
        setUsage(u);
        setReplays(rows(p.replays));
        for (let i = 0; i < Math.min(list.length, 50); i += 4) {
          await Promise.all(
            list.slice(i, i + 4).map(async (row) => {
              try {
                const id = text(row.run_id, ""),
                  detail = await getJSON(`/api/runs/${id}`, controller.signal),
                  url = artifactLink(id, "report.json", detail.artifacts);
                if (url) {
                  const report = await getJSON(url, controller.signal);
                  if (!controller.signal.aborted)
                    setReports((prev) => ({ ...prev, [id]: report }));
                }
              } catch {
                /* An unfinished run can have no downloadable report yet. */
              }
            }),
          );
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Could not load results.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, []);
  return (
    <main className="page results-page">
      <div className="page-intro">
        <p className="eyebrow">The record, including the rough edges</p>
        <h1>Results you can inspect.</h1>
        <p>
          Saved outcomes from this browser session. A target miss, unknown cost,
          or incomplete run remains visible.
        </p>
      </div>
      {error && <Notice tone="red">{error}</Notice>}
      <EvaluationView />
      <div className="metric-grid three">
        <Metric label="Saved session runs" value={String(items.length)} />
        <Metric
          label="Recorded model calls"
          value={String(usage.calls ?? "Unknown")}
        />
        <Metric
          label="Session model cost"
          value={costTotal(usage)}
          note={`Known subtotal ${usd(usage.known_cost_usd)}`}
        />
      </div>
      <BoundedCostNote usage={usage} />
      <Section
        title="Your runs"
        action={
          <a className="text-link" href="/">
            New analysis <ArrowRight size={16} />
          </a>
        }
      >
        {loading && !items.length ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Target</th>
                  <th>Status</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>Target met</th>
                  <th>Numerics</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const id = text(row.run_id, ""),
                    report = reports[id] ?? {},
                    summary = record(report.summary),
                    label = provenanceLabel(row);
                  return (
                    <tr key={id}>
                      <td>
                        <a className="run-link" href={hrefRun(id)}>
                          {id.slice(0, 8)}
                          <ArrowUpRight size={13} />
                        </a>
                        {label && <small className="table-note">{label}</small>}
                      </td>
                      <td>{human(row.target)}</td>
                      <td>
                        <Status value={row.status} />
                      </td>
                      <td>{displayMetric(report, "peak_before")}</td>
                      <td>{displayMetric(report, "peak_after")}</td>
                      <td>
                        {row.provenance === "recorded_baseline"
                          ? "N/A — baseline only"
                          : summary.target_met === true
                            ? "Yes"
                            : summary.target_met === false
                              ? "No"
                              : "Unknown"}
                      </td>
                      <td>
                        {text(summary.loss_equivalence)}
                        <small className="table-note">
                          {text(
                            summary.numerical_basis_label,
                            "Comparison basis not recorded",
                          )}
                        </small>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No runs in this session">
            <a className="text-link" href="/">
              Start with an example <ArrowRight size={14} />
            </a>
          </Empty>
        )}
        <p className="caption">
          Figures load from saved report JSON. A missing figure is unknown; this
          table is not a completed benchmark claim.
        </p>
      </Section>
      <Section title="Curated replays" kicker="Historical evidence">
        {replays.length ? (
          <div className="replay-grid">
            {replays.map((row) => (
              <a
                href={hrefRun(row.run_id, true)}
                className="replay-card"
                key={text(row.run_id)}
              >
                <Badge>Saved replay</Badge>
                <strong>{human(row.target)}</strong>
                <Status value={row.status} />
                <span className="text-link">
                  Inspect the evidence <ArrowRight size={15} />
                </span>
              </a>
            ))}
          </div>
        ) : (
          <p className="muted">No curated replays have been published.</p>
        )}
      </Section>
    </main>
  );
}

function About() {
  return (
    <main className="page about-page">
      <div className="page-intro">
        <p className="eyebrow">
          A smaller memory footprint. A clearer explanation.
        </p>
        <h1>
          From an OOM
          <br />
          to an evidence trail.
        </h1>
        <p>
          Headroom investigates GPU memory in single-GPU PyTorch workloads,
          proposes a focused change, and checks what happened when the workload
          runs again.
        </p>
        <ProviderBadge />
      </div>
      <div className="architecture">
        <div>
          <Terminal />
          <span>01 / Lab</span>
          <h2>Capture</h2>
          <p>
            Isolated runs record allocator history, stack traces, peak counters,
            and losses.
          </p>
        </div>
        <ArrowRight className="architecture-arrow" />
        <div>
          <Cpu />
          <span>02 / Reason</span>
          <h2>Diagnose</h2>
          <p>
            Nemotron connects runtime evidence to source code and a constrained
            repair plan.
          </p>
        </div>
        <ArrowRight className="architecture-arrow" />
        <div>
          <FileCode2 />
          <span>03 / Propose</span>
          <h2>Patch</h2>
          <p>
            Changes stay in a separate copy, with policy checks and a readable
            diff.
          </p>
        </div>
        <ArrowRight className="architecture-arrow" />
        <div>
          <ShieldCheck />
          <span>04 / Lab</span>
          <h2>Verify</h2>
          <p>
            Measured memory, timing, loss behavior, and parameter counts
            determine the result.
          </p>
        </div>
      </div>
      <div className="about-grid">
        <Section title="The model roles" kicker="Nebius Token Factory">
          <div className="role-list">
            <div>
              <Badge>Nemotron Ultra</Badge>
              <h3>Diagnosis and planning</h3>
              <p>
                Reads the evidence bundle and proposes causes and repairs with
                evidence references.
              </p>
            </div>
            <div>
              <Badge>Nemotron Super</Badge>
              <h3>Patch generation</h3>
              <p>
                Produces a constrained diff for the selected plan, followed by
                static checks and verification.
              </p>
            </div>
            <div>
              <Badge>Nemotron Nano</Badge>
              <h3>Allocation annotation</h3>
              <p>
                Intended for compact stack labels when that feature is
                available. Its use is recorded per run.
              </p>
            </div>
            <div>
              <Badge>Tavily</Badge>
              <h3>Version-aware research</h3>
              <p>
                Finds official documentation and known issues. Retrieved content
                remains untrusted evidence.
              </p>
            </div>
          </div>
        </Section>
        <Section title="What a report can tell you" kicker="Boundaries matter">
          <ul className="plain-list">
            <li>
              Static checks are guardrails, not a proof that arbitrary Python is
              safe or equivalent.
            </li>
            <li>
              A memory snapshot explains observed allocations. A
              reserved-minus-allocated gap alone does not prove harmful
              fragmentation.
            </li>
            <li>
              A proposed change is not a verified repair. Numerical comparisons
              may be unavailable, and precision changes must be explicit.
            </li>
            <li>
              Missing usage data leaves cost unknown. A known subtotal is never
              represented as the final total.
            </li>
            <li>
              Saved replays are historical records. Offline fixtures are marked
              and do not establish a successful model repair.
            </li>
            <li>
              Current scope is single-GPU PyTorch. Long-context capacity, model
              features, and deployment readiness require their own acceptance
              evidence.
            </li>
          </ul>
        </Section>
      </div>
      <Section title="Built on existing work" kicker="Related tools">
        <p className="small-copy">
          PyTorch memory snapshots and memory_viz provide allocator inspection.
          Activation checkpointing, mixed precision, optimizer changes, and
          allocator configuration are established techniques. Headroom brings
          their investigation, a proposed source change, and measured
          verification into one reviewable workflow.
        </p>
        <div className="related-links">
          <External href="https://docs.pytorch.org/docs/stable/torch_cuda_memory.html">
            PyTorch memory snapshots
          </External>
          <External href="https://docs.pytorch.org/docs/stable/checkpoint.html">
            Activation checkpointing
          </External>
          <External href="https://docs.tokenfactory.nebius.com/quickstart">
            Nebius Token Factory
          </External>
        </div>
      </Section>
    </main>
  );
}

export default function App() {
  const path = window.location.pathname;
  const run = /^\/runs\/([a-f0-9]{32})\/?$/.exec(path);
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation />
      <div id="main-content">
        {path === "/" ? (
          <Home />
        ) : path === "/results" ? (
          <Results />
        ) : path === "/about" ? (
          <About />
        ) : run ? (
          <RunPage runId={run[1]} />
        ) : (
          <main className="page">
            <Empty title="Page not found">
              <a href="/">Return to the workspace</a>
            </Empty>
          </main>
        )}
      </div>
      <Footer />
    </>
  );
}
