import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Layers3,
  Terminal,
  FileCode2,
  Check,
  Cpu,
  ShieldCheck,
} from "lucide-react";
import { getJSON, submitRun, requestError } from "./api";
import EvaluationView from "./EvaluationView";
import AblationView from "./AblationView";
import { RunPage } from "./RunPage";
import VerifiedPage from "./VerifiedPage";
import SnapshotDiagnosisPanel from "./SnapshotDiagnosisPanel";
import {
  availabilityBlocks,
  artifactLink,
  displayMetric,
  human,
  provenanceLabel,
  queueAtCapacity,
  record,
  rows,
  text,
  validateSubmission,
  type SearchMode,
  type Dict,
  type Submission,
} from "./data";
import {
  Badge,
  Empty,
  External,
  Loading,
  Notice,
  Section,
  Status,
} from "./components";
const hrefRun = (id: unknown) => `/runs/${encodeURIComponent(text(id, ""))}`;
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
function Navigation({ config }: { config: Dict }) {
  const path = window.location.pathname;
  return (
    <header className="site-header">
      <div className="nav-shell">
        <Brand />
        <nav aria-label="Main navigation">
          <a href="/" aria-current={path === "/" ? "page" : undefined}>
            Home
          </a>
          {config.verified_runs_enabled === true ? (
            <a
              href="/verified"
              aria-current={path === "/verified" ? "page" : undefined}
            >
              Verified runs
            </a>
          ) : (
            <span aria-disabled="true" title="Not open yet">
              Verified runs
            </span>
          )}
          <a
            href="/run"
            aria-current={
              path === "/run" || /^\/runs?\//.test(path) ? "page" : undefined
            }
          >
            Run
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
      <span>
        Powered by NVIDIA Nemotron 3 Ultra · Super · Nano on Nebius Token
        Factory
      </span>
      <span className="provider-separator">/</span>
      <span>Research by Tavily</span>
    </div>
  );
}

function Home({ config }: { config: Dict }) {
  return (
    <main className="page home-page">
      <div className="hero">
        <div>
          <p className="eyebrow">
            <span className="small-line" />A little room goes a long way
          </p>
          <h1>
            From CUDA OOM
            <br />
            <span>to a verified patch.</span>
          </h1>
          <p className="hero-description">
            Headroom turns a CUDA out-of-memory crash into a verified patch: it
            diagnoses the memory problem, proposes a change, and tests it on the
            GPU.
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
      <div
        style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 28 }}
      >
        {config.verified_runs_enabled === true ? (
          <a className="button button-primary" href="/verified">
            Verified runs <ArrowRight size={16} />
          </a>
        ) : (
          <button
            className="button button-primary"
            disabled
            title="Not open yet"
          >
            Verified runs · Coming soon
          </button>
        )}
        <a className="button button-secondary" href="/run">
          Run an example
        </a>
        <a className="button button-secondary" href="/results">
          Results
        </a>
      </div>
      {record(config.run_submissions).enabled === false && (
        <Notice>
          Live analysis temporarily paused. Recorded evaluation results remain
          available.
        </Notice>
      )}
      <details className="panel" style={{ padding: 24, marginBottom: 28 }}>
        <summary>Diagnose my snapshot</summary>
        <SnapshotDiagnosisPanel
          enabled={record(config.snapshot_submissions).enabled === true}
        />
      </details>
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
      </section>{" "}
    </main>
  );
}

function RunForm({ config }: { config: Dict }) {
  const publicDemo = config.public_demo !== false;
  const judgeScriptsAvailable = config.judge_scripts_available === true;
  const canPasteScript = !publicDemo || judgeScriptsAvailable;
  const [judgeToken, setJudgeToken] = useState("");
  const [examples, setExamples] = useState<Dict[]>([]),
    [health, setHealth] = useState<Dict>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const [mode, setMode] = useState<"example" | "script">("example"),
    [example, setExample] = useState(""),
    [script, setScript] = useState(""),
    [target, setTarget] = useState("fix-oom"),
    [manualTarget, setManualTarget] = useState(false),
    [fit, setFit] = useState("22"),
    [budget, setBudget] = useState(publicDemo ? "0.30" : "0.60"),
    [searchMode, setSearchMode] = useState<SearchMode>("until_target"),
    [precision, setPrecision] = useState(false),
    [batch, setBatch] = useState(true),
    [slowdown, setSlowdown] = useState("25"),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    async function loadHealth() {
      const response = await fetch("/api/health", {
        credentials: "same-origin",
        signal: controller.signal,
        headers: {
          "X-Headroom-View": "product-v1",
          ...(judgeToken.trim()
            ? { Authorization: "Bearer " + judgeToken.trim() }
            : {}),
        },
      });
      if (!response.ok)
        throw new Error(
          response.status === 401
            ? "The judge access token was not accepted."
            : requestError(response.status),
        );
      return record(await response.json());
    }
    (async () => {
      try {
        const h = await loadHealth();
        setHealth(h);
        const e = await getJSON("/api/examples", controller.signal);
        setExamples(rows(e.examples));
      } catch (e) {
        if (!controller.signal.aborted) {
          setHealth({ run_submissions: { enabled: false } });
          setError(e instanceof Error ? e.message : "Could not reach the API.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    const refresh = window.setInterval(async () => {
      try {
        setHealth(await loadHealth());
      } catch {
        if (!controller.signal.aborted)
          setHealth((previous) => ({
            ...previous,
            run_submissions: { enabled: false },
            limits: {},
            gpu: { status: "unknown", available: null, busy: null },
            local_budget: { status: "unknown", remaining_usd: null },
          }));
      }
    }, 15000);
    return () => {
      controller.abort();
      window.clearInterval(refresh);
    };
  }, [judgeToken]);
  const queue = record(health.queue),
    provider = record(health.token_factory);
  const submissions = record(health.run_submissions);
  const requestLimits = record(health.limits);
  const submissionsPaused =
    (typeof submissions.enabled === "boolean"
      ? submissions.enabled
      : record(config.run_submissions).enabled) !== true;
  const submissionPauseReason = "Live analysis temporarily paused.";
  const queueFull = queueAtCapacity(queue);
  const availability = availabilityBlocks(health);
  const selectedExample =
    mode === "example" ? examples.find((row) => row.id === example) : undefined;
  const recommended = record(selectedExample?.recommended);
  function applyRecommended(row?: Dict) {
    const value = text(record(row?.recommended).target, "fix-oom");
    const match = /^fit:([0-9]+(?:\.[0-9]+)?)GB$/.exec(value);
    setTarget(match ? "fit" : value === "reclaim" ? "reclaim" : "fix-oom");
    if (match) setFit(match[1]);
    setManualTarget(false);
  }
  function selectExample(row: Dict) {
    setExample(text(row.id, ""));
    if (!manualTarget) applyRecommended(row);
  }
  function selectMode(next: "example" | "script") {
    setMode(next);
    if (!manualTarget)
      applyRecommended(
        next === "example"
          ? examples.find((row) => row.id === example)
          : undefined,
      );
  }
  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    if (submissionsPaused) {
      setError(submissionPauseReason);
      return;
    }
    const payload: Submission = {
      ...(mode === "example"
        ? { example_id: example }
        : { script_text: script }),
      target: target === "fit" ? `fit:${fit}GB` : target,
      allocator_conf:
        typeof recommended.allocator_conf === "string"
          ? recommended.allocator_conf
          : null,
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
    if (
      mode === "script" &&
      publicDemo &&
      (!judgeScriptsAvailable || !judgeToken.trim())
    ) {
      setError("Enter your judge access token to submit a script.");
      return;
    }
    setBusy(true);
    try {
      let run: Dict;
      if (publicDemo && judgeToken.trim()) {
        const response = await fetch("/api/runs", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${judgeToken.trim()}`,
          },
          body: JSON.stringify(payload),
        });
        const body = record(await response.json());
        if (!response.ok) throw new Error(requestError(response.status));
        if (
          typeof body.run_id !== "string" ||
          !/^[a-f0-9]{32}$/.test(body.run_id)
        )
          throw new Error("The server returned an invalid run identifier.");
        run = body;
      } else {
        run = await submitRun(payload);
      }
      window.location.assign(hrefRun(run.run_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
      setBusy(false);
    } finally {
      setJudgeToken("");
    }
  }
  return (
    <main className="page home-page">
      <div className="page-intro">
        <p className="eyebrow">Run on the GPU</p>
        <h1>Start an analysis.</h1>
        <p>
          Choose a prepared workload and define the memory target. Each run
          records its diagnosis, changes, and measured result.
        </p>
      </div>
      {error && <Notice tone="red">{error}</Notice>}
      {submissionsPaused && (
        <Notice>
          <strong>{submissionPauseReason}</strong> You can still{" "}
          <a href="/results">browse published evaluation results</a>.
        </Notice>
      )}
      {!submissionsPaused && !loading && provider.configured === false && (
        <Notice>
          <strong>Live analysis is not enabled yet.</strong> Runs may pause
          while model readiness checks are completed.
        </Notice>
      )}
      {queueFull && (
        <Notice>
          The run queue is currently unavailable. Availability will refresh
          automatically.
        </Notice>
      )}
      {availability.gpuBusy && (
        <Notice>
          <strong>The GPU is busy.</strong> A compute workload is active.
          Availability will refresh automatically.
        </Notice>
      )}
      {!submissionsPaused && availability.budgetBlocked && (
        <Notice>
          <strong>Live analysis temporarily paused.</strong> You can still
          browse the recorded results while new analysis is unavailable.
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
          {publicDemo && judgeScriptsAvailable && (
            <label className="field">
              Judge access token (optional for examples)
              <input
                type="password"
                autoComplete="off"
                value={judgeToken}
                onChange={(event) => {
                  setError("");
                  setHealth({ run_submissions: { enabled: false } });
                  setJudgeToken(event.target.value);
                }}
                aria-label="Judge access token"
              />
              <span className="caption">
                Use a token for an example or your own script. It stays only on
                this page and is cleared after submission.
              </span>
            </label>
          )}
          {publicDemo && requestLimits.hourly_limit_applies === false && (
            <p className="caption" role="status">
              No hourly run-count limit for this token. Queue capacity, runtime
              and per-run spending limits still apply.
            </p>
          )}
          {publicDemo &&
            requestLimits.hourly_limit_applies === true &&
            typeof requestLimits.runs_per_ip_per_hour === "number" && (
              <p className="caption" role="status">
                Anonymous access: {requestLimits.runs_per_ip_per_hour} run
                attempt per IP per hour.
              </p>
            )}
          <div className="segmented" role="group" aria-label="Source type">
            <button
              type="button"
              aria-pressed={mode === "example"}
              onClick={() => selectMode("example")}
            >
              Use an example
            </button>
            {!submissionsPaused && canPasteScript && (
              <button
                type="button"
                aria-pressed={mode === "script"}
                onClick={() => selectMode("script")}
              >
                Paste a script
              </button>
            )}
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
                    onClick={() => selectExample(row)}
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
                    {typeof row.baseline_note === "string" && (
                      <p className="caption">{row.baseline_note}</p>
                    )}
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
                  onChange={() => {
                    setTarget(value);
                    setManualTarget(true);
                  }}
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
                  onChange={(e) => {
                    setFit(e.target.value);
                    setManualTarget(true);
                  }}
                />
                <span>GB</span>
              </span>
            </label>
          )}
          {typeof recommended.target === "string" && (
            <div className="caption">
              <p>Recommended target: {recommended.target}.</p>
              {manualTarget && (
                <>
                  <p>Your custom target is kept when switching examples.</p>
                  <button
                    type="button"
                    onClick={() => applyRecommended(selectedExample)}
                  >
                    Use recommended target
                  </button>
                </>
              )}
              {typeof recommended.allocator_conf === "string" && (
                <p>Example environment: {recommended.allocator_conf}.</p>
              )}
            </div>
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
          </div>
          {!publicDemo && (
            <label className="field">
              Run budget
              <input
                aria-label="Run budget in USD"
                type="number"
                min="0.01"
                max="5"
                step="0.01"
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
              />
            </label>
          )}
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
            within the same time and policy limits. Verified results are kept if
            a later attempt stops.
          </p>
          <p className="caption">
            Model structure stays unchanged. Each result includes the measured
            memory use and numerical comparison.
          </p>
          <button
            className="button button-primary start-button"
            type="submit"
            disabled={
              busy ||
              loading ||
              submissionsPaused ||
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
    </main>
  );
}

function Results() {
  const [items, setItems] = useState<Dict[]>([]),
    [reports, setReports] = useState<Record<string, Dict>>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        await getJSON("/api/health", controller.signal);
        const r = await getJSON("/api/runs", controller.signal);
        const list = rows(r.runs);
        setItems(list);
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
          Explore real GPU measurements, the repairs that worked, and the
          workloads that still need work.
        </p>
      </div>
      {error && <Notice tone="red">{error}</Notice>}
      <EvaluationView />
      <AblationView />
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
                        <Status
                          value={
                            row.status === "budget_exceeded"
                              ? "analysis_paused"
                              : row.status
                          }
                        />
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
          Your browser session keeps its own run history. Missing measurements
          are shown as Unknown.
        </p>
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
          Headroom analyzes GPU memory in single-GPU PyTorch workloads, proposes
          a focused change, and checks what happened when the workload runs
          again.
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
                Adds compact labels to captured allocation stacks. Each report
                records the models used.
              </p>
            </div>
            <div>
              <Badge>Tavily</Badge>
              <h3>Version-aware research</h3>
              <p>
                Finds version-specific PyTorch documentation and known issues to
                inform repair suggestions.
              </p>
            </div>
          </div>
        </Section>
        <Section title="Limitations" kicker="Understanding the results">
          <ul className="plain-list">
            <li>
              Headroom currently supports single-GPU PyTorch workloads it can
              run again. It does not yet support distributed training.
            </li>
            <li>
              A suggested patch can fail or leave the memory problem unsolved.
              Each result shows what ran, what changed, and whether the repair
              worked.
            </li>
            <li>
              Numerical comparisons cover the recorded loss samples, not an
              entire training run. The comparison basis is shown beside each
              result, and precision changes require an explicit policy.
            </li>
            <li>
              Missing measurements and costs remain Unknown. Offline examples
              are labelled separately from real GPU results.
            </li>
            <li>
              A snapshot describes recorded allocations. Unused reserved memory
              alone does not establish harmful fragmentation.
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
  const run = /^\/runs?\/([a-f0-9]{32})\/?$/.exec(path);
  const [config, setConfig] = useState<Dict>({});
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getJSON("/api/config", controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setConfig(value);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setConfigError(
            "Service availability could not be loaded. Please try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setConfigLoading(false);
      });
    return () => controller.abort();
  }, []);
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation config={config} />
      <div id="main-content">
        {path === "/" ? (
          <Home config={config} />
        ) : path === "/run" ? (
          configLoading ? (
            <main className="page">
              <Loading>Checking service availability…</Loading>
            </main>
          ) : configError ? (
            <main className="page">
              <Notice tone="red">{configError}</Notice>
            </main>
          ) : (
            <RunForm config={config} />
          )
        ) : path === "/verified" ? (
          <VerifiedPage
            enabled={config.verified_runs_enabled === true}
            loading={configLoading}
          />
        ) : path === "/results" ? (
          <Results />
        ) : path === "/about" ? (
          <About />
        ) : run ? (
          <RunPage runId={run[1]} />
        ) : (
          <main className="page">
            <Empty title="Page not found">
              <a href="/">Return to the home page</a>
            </Empty>
          </main>
        )}
      </div>
      <Footer />
    </>
  );
}
