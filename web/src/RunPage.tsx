import { lazy, Suspense, useEffect, useState } from "react";
import { ChevronRight, Download, SquareArrowOutUpRight } from "lucide-react";
import { getJSON, getText } from "./api";
import {
  analysisOf,
  artifactLink,
  configurationLink,
  decimal,
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
  record,
  rows,
  text,
  usd,
  verificationRows,
  type Dict,
  type RunEvent,
} from "./data";
import {
  Badge,
  Empty,
  External,
  Loading,
  Metric,
  Notice,
  Section,
} from "./components";
const MemoryChart = lazy(() => import("./MemoryChart"));
const DiffView = lazy(() => import("./DiffView"));

function confirmedAmount(value: unknown): string {
  const amount = decimal(value);
  return amount === null || amount < 0
    ? "unavailable"
    : amount > 0 && amount < 0.0001
      ? "<$0.0001"
      : usd(value);
}
function confirmedRunCost(value: unknown): string {
  const usage = record(value);
  if (
    usage.complete !== true ||
    ("unknown_cost_calls" in usage && numeric(usage.unknown_cost_calls) !== 0)
  )
    return "unavailable";
  return confirmedAmount(usage.total_cost_usd);
}
function publicText(value: unknown, fallback = "Unknown"): string {
  let output = text(value, fallback);
  if (/^[a-z][a-z0-9_]+$/.test(output)) output = human(output);
  if (
    /unknown[ _-]+(?:charge|cost)|unconfirmed (?:actual )?charge|unresolved (?:charge|cost)/i.test(
      output,
    )
  )
    return "The provider has not supplied a complete usage total.";
  if (
    /budget[ _-]+exceeded|insufficient.*budget|cannot reserve|budget.*reservation/i.test(
      output,
    )
  )
    return "The run reached its model-usage limit.";
  if (/verified provider profile|runtime profile unavailable/i.test(output))
    return "Model access is unavailable.";
  output = output
    .replace(/HTTP 529/gi, "model service unavailable")
    .replace(/conservative upper/gi, "estimated maximum")
    .replace(/\bledger\b/gi, "usage record")
    .replace(/\breservation\b/gi, "estimate")
    .replace(/\bwithdrawn\b/gi, "not selected")
    .replace(/\bacceptance\b/gi, "verification")
    .replace(/\bgate\b/gi, "check")
    .replace(/\bhalt(?:ed)?\b/gi, "stopped")
    .replace(/See report JSON/g, "See the downloaded report");
  return output;
}
function RunStatus({ value }: { value: unknown }) {
  const state = text(value, "unknown");
  const labels: Record<string, string> = {
    completed: "Completed",
    done: "Completed",
    running: "Running",
    queued: "Queued",
    preparing: "Preparing",
    failed: "Failed",
    rejected: "Not run",
    timeout: "Timed out",
    cancelled: "Cancelled",
    needs_human: "Needs attention",
    budget_exceeded: "Stopped",
  };
  const tone = ["completed", "done"].includes(state)
    ? "green"
    : ["failed", "rejected", "timeout"].includes(state)
      ? "red"
      : ["needs_human", "budget_exceeded"].includes(state)
        ? "amber"
        : "neutral";
  return <Badge tone={tone}>{labels[state] ?? "Unknown"}</Badge>;
}
function initialDiagnosisEvidence(value: unknown): Dict | null {
  const envelope = record(value);
  const binding = record(envelope.diagnosis_binding);
  const digestKeys = [
    "evidence_json_sha256",
    "evidence_markdown_sha256",
    "diagnosis_sha256",
    "request_payload_sha256",
    "request_wire_sha256",
  ];
  if (
    binding.round !== 1 ||
    binding.stage !== "baseline" ||
    !digestKeys.every(
      (key) =>
        typeof binding[key] === "string" &&
        /^[a-f0-9]{64}$/.test(binding[key] as string),
    ) ||
    !Array.isArray(record(envelope.diagnosis).root_causes) ||
    !Array.isArray(envelope.stacks)
  )
    return null;
  const stacks = rows(envelope.stacks);
  if (stacks.length !== envelope.stacks.length || stacks.length > 200)
    return null;
  const identifiers = new Set(stacks.map((stack) => stack.id));
  if (
    identifiers.size !== stacks.length ||
    stacks.some(
      (stack) =>
        typeof stack.id !== "string" ||
        !/^stk_[a-f0-9]{16}$/.test(stack.id) ||
        !Array.isArray(stack.frames),
    )
  )
    return null;
  if (
    rows(record(envelope.diagnosis).root_causes).some(
      (cause) =>
        !Array.isArray(cause.evidence_refs) ||
        cause.evidence_refs.some((ref) => !identifiers.has(ref)),
    )
  )
    return null;
  return envelope;
}
function byteLabel(value: unknown): string {
  const bytes = numeric(value);
  return bytes === null || bytes < 0 || !Number.isInteger(bytes)
    ? "unavailable"
    : bytes.toLocaleString("en-US") + " bytes (" + gb(bytes) + ")";
}
function frameText(frames: Dict[]): string {
  return frames
    .map(
      (frame) =>
        text(frame.filename, "?") +
        ":" +
        String(frame.line ?? "?") +
        " in " +
        text(frame.name),
    )
    .join("\n");
}
function StackReference({
  reference,
  evidence,
}: {
  reference: unknown;
  evidence: Dict | null;
}) {
  const [open, setOpen] = useState(false);
  const id = text(reference, "");
  // Only the authenticated, source-bound diagnosis response supplies these stacks.
  const stack = evidence
    ? rows(evidence.stacks).find((entry) => entry.id === id)
    : undefined;
  if (!id) return null;
  if (!id.startsWith("stk_")) return <code>{id}</code>;
  const frames = rows(stack?.frames);
  const sourceFrames = frames.filter((frame) =>
    text(frame.filename, "").startsWith("/source/"),
  );
  return (
    <div
      className="stack-reference"
      style={{ maxWidth: "100%", minWidth: 0, overflowWrap: "anywhere" }}
    >
      <button
        type="button"
        className="text-link"
        style={{
          whiteSpace: "normal",
          overflowWrap: "anywhere",
          textAlign: "left",
        }}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {id}
      </button>
      {open &&
        (stack ? (
          <div className="stack-block">
            <p className="caption">Initial diagnosis · original capture</p>
            <dl className="key-values">
              <div>
                <dt>Live at peak</dt>
                <dd>{byteLabel(stack.peak_live_bytes)}</dd>
              </div>
              <div>
                <dt>Allocated during capture</dt>
                <dd>{byteLabel(stack.lifetime_allocated_bytes)}</dd>
              </div>
            </dl>
            <pre>
              {frameText(sourceFrames.length ? sourceFrames : frames) ||
                "No frames retained."}
            </pre>
            {sourceFrames.length > 0 &&
              sourceFrames.length !== frames.length && (
                <details>
                  <summary>Full call stack ({frames.length} frames)</summary>
                  <pre>{frameText(frames)}</pre>
                </details>
              )}
          </div>
        ) : (
          <p className="caption">
            Stack details unavailable: this report does not identify the capture
            used by this diagnosis.
          </p>
        ))}
    </div>
  );
}

export function RunPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<Dict>({}),
    [report, setReport] = useState<Dict>({}),
    [evidence, setEvidence] = useState<Dict>({}),
    [events, setEvents] = useState<RunEvent[]>([]),
    [diff, setDiff] = useState<string | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [stream, setStream] = useState("Connecting");
  useEffect(() => {
    setRun({});
    setReport({});
    setEvidence({});
    setEvents([]);
    setDiff(null);
    setError("");
    setLoading(true);
    setStream("Connecting");
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
  const boundDiagnosis =
    run.run_id === runId
      ? initialDiagnosisEvidence(run.diagnosis_evidence)
      : null;
  const label = provenanceLabel(run),
    usage = Object.keys(record(run.usage)).length
      ? record(run.usage)
      : record(report.usage),
    before = analysisOf(report, "before", evidence),
    after = analysisOf(report, "after"),
    diagnosis = record(boundDiagnosis?.diagnosis ?? report.diagnosis),
    causes = rows(diagnosis.root_causes),
    allocator = record(report.allocator),
    summary = record(report.summary);
  const limitations = [
    ...(Array.isArray(report.warnings) ? report.warnings : []),
    ...(allocator.note ? [allocator.note] : []),
  ];
  const downloads = [
    "patch.diff",
    "cli.json",
    "configuration.json",
    "report.md",
    "report.json",
    "env.sh",
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
            <RunStatus value={run.status} />
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
      {error && <Notice tone="red">{publicText(error)}</Notice>}
      {run.status === "needs_human" && (
        <Notice>
          <strong>This run needs attention.</strong>{" "}
          {publicText(
            run.reason,
            "A required condition is unavailable. Inspect the report before continuing.",
          )}
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
          </div>
          <p className="caption run-cost">
            Token Factory cost of this run: {confirmedRunCost(usage)}
          </p>
          {summary.target_met === true &&
            run.provenance !== "recorded_baseline" && (
              <Notice tone="neutral">
                The selected repair meets the target. Its patch and settings are
                available below.
              </Notice>
            )}
          {run.status === "budget_exceeded" && (
            <Notice>
              The run reached its model-usage limit. Any verified repair remains
              available below.
            </Notice>
          )}
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
                        <div className="event-title">
                          {publicText(human(event.kind))}
                        </div>
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
                        </div>
                        {typeof event.data.model === "string" && (
                          <Badge>{event.data.model.split("/").pop()}</Badge>
                        )}
                        {typeof event.data.reason === "string" && (
                          <p>{publicText(event.data.reason)}</p>
                        )}
                        {numeric(event.data.elapsed_seconds) !== null && (
                          <small>
                            {Number(event.data.elapsed_seconds).toFixed(2)}s
                          </small>
                        )}
                        {("cost_usd" in event.data || "cost" in event.data) && (
                          <small>
                            Cost{" "}
                            {confirmedAmount(
                              "cost_usd" in event.data
                                ? event.data.cost_usd
                                : record(event.data.cost).usd,
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
              {rows(record(report.pareto).frontier).length > 0 && (
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
                    Only comparable, verified configurations establish a
                    tradeoff. Unknown or shared timing does not establish a
                    speed advantage.
                  </p>
                </Section>
              )}
              {Object.keys(record(report.selected_configuration)).length >
                0 && (
                <Section title="Use this repair">
                  <p className="small-copy">
                    Apply the patch together with the downloaded command
                    arguments and environment settings. Some repairs change
                    these settings without changing the source file.
                  </p>
                  {record(report.selected_configuration).wrapper_replay !=
                    null && (
                    <p className="caption">
                      This run used a launcher. Update that launcher with the
                      downloaded settings before running the script yourself.
                    </p>
                  )}
                </Section>
              )}
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
                      {verificationRows({
                        ...report,
                        run: {
                          ...record(report.run),
                          provenance:
                            run.provenance ?? record(report.run).provenance,
                        },
                      }).map((row, i) => (
                        <tr key={i}>
                          <td>{publicText(row.label)}</td>
                          <td>{publicText(row.value)}</td>
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
              <Section
                title={boundDiagnosis ? "Initial diagnosis" : "The diagnosis"}
                kicker="NVIDIA Nemotron"
              >
                <div className="diagnosis-cards">
                  {causes.length ? (
                    causes.map((cause, index) => (
                      <article key={index}>
                        <div className="diagnosis-index">
                          {String(index + 1).padStart(2, "0")}
                        </div>
                        <h3>{publicText(cause.title)}</h3>
                        <p>{publicText(human(cause.category))}</p>
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
                              <StackReference
                                key={i}
                                reference={ref}
                                evidence={boundDiagnosis}
                              />
                            ))}
                        </div>
                      </article>
                    ))
                  ) : (
                    <Empty
                      title={
                        diagnosis.needs_more_info === true
                          ? "More information needed"
                          : "No diagnosis yet"
                      }
                    >
                      {diagnosis.needs_more_info === true
                        ? Array.isArray(diagnosis.notes)
                          ? diagnosis.notes
                              .map((note) => publicText(note))
                              .join(" ")
                          : "The model needs more information to identify the cause."
                        : "Root causes appear after the evidence is analyzed."}
                    </Empty>
                  )}
                </div>
              </Section>
              {rows(diagnosis.plan).length > 0 && (
                <Section title="Suggested fixes" kicker="Model estimates">
                  {rows(diagnosis.plan).map((item, index) => (
                    <article className="round-note" key={index}>
                      <h3>{publicText(item.title)}</h3>
                      <p>
                        {publicText(item.description, "No rationale recorded.")}
                      </p>
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
              <Section title="Sources" kicker="Research by Tavily">
                <Sources sources={rows(report.sources)} />
              </Section>
            </aside>
          </div>
          {limitations.length > 0 && (
            <Section title="Limitations">
              {limitations.map((warning, index) => (
                <p className="small-copy" key={index}>
                  {publicText(warning)}
                </p>
              ))}
            </Section>
          )}
        </>
      )}
    </main>
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
        : publicText(value);
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
      <strong>{publicText(human(row.decision ?? row.status))}</strong>
      <p>{publicText(row.reason, "No decision reason recorded.")}</p>
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
                  <th>{publicText(human(name))}</th>
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
            {publicText(note)}
          </p>
        ))}
    </article>
  );
}
