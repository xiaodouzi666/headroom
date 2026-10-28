import { lazy, Suspense, useEffect, useState } from "react";
import { getJSON, getText } from "./api";
import {
  decimal,
  externalLink,
  gb,
  numeric,
  record,
  rows,
  text,
  type Dict,
} from "./data";
import { Badge, Empty, External, Loading, Notice } from "./components";

const DiffView = lazy(() => import("./DiffView"));
const boolean = (value: unknown) =>
  value === true ? "Passed" : value === false ? "Not passed" : "Unknown";
const count = (value: unknown) =>
  numeric(value) === null ? "Unknown" : Number(value).toLocaleString("en-US");
const numerics = (value: unknown) =>
  (
    ({
      identical: "Identical",
      within_tol: "Within tolerance",
      changed: "Changed",
      "n/a": "Not compared",
    }) as Record<string, string>
  )[String(value)] ?? "Unknown";
const percent = (value: unknown) =>
  decimal(value) === null ? "Unknown" : Number(value).toFixed(2) + "%";
const peak = (measurement: Dict) =>
  (measurement.peak_is_exact === false ? "≥ " : "") +
  gb(measurement.peak_allocated_bytes);
function candidateReason(value: unknown): string {
  const reason = text(value, "The reason was not recorded.").trim();
  if (reason === "verification_hard_constraints_unmet")
    return "The candidate did not pass the required verification.";
  const readable = reason.replace(/_/g, " ");
  return readable.charAt(0).toUpperCase() + readable.slice(1);
}
const bindingKeys = [
  "evidence_json_sha256",
  "evidence_markdown_sha256",
  "diagnosis_sha256",
  "request_payload_sha256",
  "request_wire_sha256",
];
function boundDiagnosis(run: Dict) {
  const binding = record(run.diagnosis_binding);
  return (
    binding.round === 1 &&
    binding.stage === "baseline" &&
    bindingKeys.every(
      (key) =>
        typeof binding[key] === "string" &&
        /^[a-f0-9]{64}$/.test(String(binding[key])),
    )
  );
}
function assetURL(run: Dict, kind: string): string | null {
  const url = record(record(run.downloads)[kind]).url;
  if (typeof url !== "string") return null;
  const match =
    /^\/api\/verified\/([a-f0-9]{32})\/download\/(patch|report_json|report_markdown)$/.exec(
      url,
    );
  return match && match[1] === run.run_id && match[2] === kind ? url : null;
}
function StackCitation({ run, reference }: { run: Dict; reference: string }) {
  const [open, setOpen] = useState(false);
  const matches = boundDiagnosis(run)
    ? rows(run.stacks).filter((stack) => stack.id === reference)
    : [];
  const stack = matches.length === 1 ? matches[0] : null;
  if (!stack)
    return (
      <span className="caption">{reference} · bound evidence unavailable</span>
    );
  return (
    <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
      <button
        type="button"
        className="text-link"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{ whiteSpace: "normal", overflowWrap: "anywhere" }}
      >
        {reference}
      </button>
      {open && (
        <div className="stack-block">
          <p>Initial diagnosis · baseline capture</p>
          <p>
            Live bytes at recorded peak:{" "}
            {numeric(stack.peak_live_bytes) === null
              ? "Unknown"
              : `${count(stack.peak_live_bytes)} bytes (${gb(stack.peak_live_bytes)})`}
          </p>
          <p>
            Total bytes allocated over the capture:{" "}
            {numeric(stack.lifetime_allocated_bytes) === null
              ? "Unknown"
              : `${count(stack.lifetime_allocated_bytes)} bytes`}
          </p>
          <pre>
            {rows(stack.frames)
              .map(
                (frame) =>
                  `${text(frame.filename)}:${count(frame.line)} in ${text(frame.name)}`,
              )
              .join("\n") || "Frames unavailable."}
          </pre>
        </div>
      )}
    </div>
  );
}
function Patch({ url, kept }: { url: string; kept: boolean }) {
  const [expanded, setExpanded] = useState(false),
    [diff, setDiff] = useState<string | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!expanded || diff !== null) return;
    const controller = new AbortController();
    getText(url, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setDiff(value);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError("The patch could not be loaded.");
      });
    return () => controller.abort();
  }, [url, expanded, diff]);
  return (
    <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>
        {kept
          ? "Inspect the selected patch"
          : "Inspect the reverted candidate patch"}
      </summary>
      {error ? (
        <Notice tone="red">{error}</Notice>
      ) : diff === null ? (
        <Loading>Loading patch…</Loading>
      ) : (
        <Suspense fallback={<Loading />}>
          <DiffView diff={diff} recorded />
        </Suspense>
      )}
    </details>
  );
}
function Verification({ data, updates }: { data: Dict; updates: unknown }) {
  const checks = record(data.checks);
  return (
    <div className="table-wrap">
      <table aria-label="Recorded verification">
        <tbody>
          <tr>
            <th>Loss comparison</th>
            <td>{numerics(data.loss_equivalence)}</td>
          </tr>
          <tr>
            <th>Loss samples compared</th>
            <td>{count(data.compared_loss_count)}</td>
          </tr>
          <tr>
            <th>Optimizer updates completed</th>
            <td>{count(updates)}</td>
          </tr>
          <tr>
            <th>Parameters before / after</th>
            <td>
              {count(data.parameter_count_before)} /{" "}
              {count(data.parameter_count_after)}
            </td>
          </tr>
          <tr>
            <th>Parameter count unchanged</th>
            <td>{boolean(checks.parameter_count_unchanged)}</td>
          </tr>
          <tr>
            <th>Same inputs</th>
            <td>{boolean(checks.same_inputs)}</td>
          </tr>
          <tr>
            <th>Same effective batch</th>
            <td>{boolean(checks.same_effective_batch)}</td>
          </tr>
          <tr>
            <th>Same objective</th>
            <td>{boolean(checks.same_objective)}</td>
          </tr>
        </tbody>
      </table>
      <p className="caption">
        {text(data.note, "Comparison details unavailable.")}
      </p>
    </div>
  );
}
function VerifiedCard({ run }: { run: Dict }) {
  const successful = run.outcome === "target_met";
  const before = record(run.before),
    after = record(run.after),
    verification = record(run.verification);
  const attempt = record(run.last_attempt),
    candidate = record(attempt.candidate);
  const diagnosis = record(run.diagnosis),
    patch = assetURL(run, "patch");
  return (
    <article
      className="panel"
      id={`verified-${String(run.run_id)}`}
      style={{ padding: 24, marginBottom: 24 }}
    >
      <Badge tone={successful ? "green" : "amber"}>
        {successful ? "Recorded repair" : "Not solved — here is why"}
      </Badge>
      <h2>{text(run.title)}</h2>
      <p>{text(run.description)}</p>
      <div className="metric-grid three">
        <div className="metric">
          <span>Peak before</span>
          <strong>{peak(before)}</strong>
        </div>
        <div className="metric">
          <span>
            {successful ? "Peak after selected repair" : "Selected repair"}
          </span>
          <strong>{successful ? peak(after) : "None"}</strong>
        </div>
        <div className="metric">
          <span>Recorded peak reduction</span>
          <strong>
            {successful ? percent(run.peak_reduction_pct) : "Not solved"}
          </strong>
        </div>
      </div>
      {successful ? (
        <Verification data={verification} updates={after.optimizer_updates} />
      ) : (
        <>
          <p>No candidate was retained as a successful repair.</p>
          {Object.keys(attempt).length > 0 && (
            <div>
              <h3>Last candidate · reverted</h3>
              <p>{candidateReason(attempt.reason)}</p>
              <p>
                Candidate peak: {peak(candidate)}. This is not the result of a
                retained repair.
              </p>
              <Verification
                data={record(attempt.verification)}
                updates={candidate.optimizer_updates}
              />
            </div>
          )}
        </>
      )}
      <h3>Initial diagnosis</h3>
      <p className="caption">
        Round 1, before any patch. Later planning may differ.
      </p>
      {rows(diagnosis.root_causes).map((cause, index) => (
        <div key={index} className="diagnosis-cards">
          <h4>{text(cause.title)}</h4>
          <p>{text(cause.category)}</p>
          <div>
            {(Array.isArray(cause.evidence_refs) ? cause.evidence_refs : [])
              .filter((ref): ref is string => typeof ref === "string")
              .map((ref) => (
                <StackCitation key={ref} run={run} reference={ref} />
              ))}
          </div>
        </div>
      ))}
      {!boundDiagnosis(run) && (
        <p className="caption">
          The initial diagnosis capture could not be verified; stack references
          are unavailable.
        </p>
      )}
      {patch && <Patch url={patch} kept={successful} />}
      <div
        style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 16 }}
      >
        {(
          [
            ["patch", "Download patch"],
            ["report_json", "Download report data"],
            ["report_markdown", "Download report"],
          ] as const
        ).map(([kind, label]) => {
          const url = assetURL(run, kind);
          return url ? (
            <a key={kind} href={url} download className="text-link">
              {label}
            </a>
          ) : null;
        })}
      </div>
      <h3>Sources</h3>
      {rows(run.sources).length ? (
        <ul className="plain-list">
          {rows(run.sources).map((source, index) => {
            const url = externalLink(source.url);
            return url ? (
              <li key={index}>
                <External href={url}>{text(source.title)}</External> · Tavily
                {source.version_match !== true && (
                  <small className="table-note">
                    Version match not established.
                  </small>
                )}
              </li>
            ) : null;
          })}
        </ul>
      ) : (
        <p>No research sources were recorded for this run.</p>
      )}
      <h3>Limitations</h3>
      <ul className="plain-list">
        {(Array.isArray(run.limitations) ? run.limitations : []).map(
          (line, index) => (
            <li key={index}>{String(line)}</li>
          ),
        )}
      </ul>
    </article>
  );
}
export default function VerifiedPage({
  enabled,
  loading = false,
}: {
  enabled: boolean;
  loading?: boolean;
}) {
  const [catalog, setCatalog] = useState<Dict>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) {
      setCatalog({});
      return;
    }
    const controller = new AbortController();
    setBusy(true);
    setError("");
    getJSON("/api/verified", controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          if (data.publication_status !== "published")
            throw new Error("Verified runs are not open yet.");
          setCatalog(data);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Verified runs could not be loaded.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [enabled]);
  return (
    <main className="page">
      <div className="page-intro">
        <p className="eyebrow">Recorded on real hardware</p>
        <h1>Verified runs.</h1>
        <p>
          Inspect selected repairs and unresolved workloads, with the original
          diagnosis, patch, and measurements.
        </p>
      </div>
      {loading ? (
        <Loading>Checking gallery availability…</Loading>
      ) : !enabled ? (
        <Empty title="Verified runs are not open yet">
          <a href="/results">Browse published evaluation results</a>
        </Empty>
      ) : error ? (
        <Notice tone="red">{error}</Notice>
      ) : busy ? (
        <Loading>Loading recorded runs…</Loading>
      ) : (
        <>
          <p className="caption">
            These examples come from separate historical evaluations. They are
            not a combined success score.{" "}
            <a href="/results">Compare complete evaluations.</a>
          </p>
          {rows(catalog.runs)
            .filter((run) => /^[a-f0-9]{32}$/.test(String(run.run_id)))
            .map((run) => (
              <VerifiedCard key={String(run.run_id)} run={run} />
            ))}
        </>
      )}
    </main>
  );
}
