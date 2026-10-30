import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Badge, Empty, Loading, Notice, Section } from "./components";
import {
  decimal,
  gb,
  human,
  numeric,
  record,
  rows,
  text,
  type Dict,
} from "./data";
import {
  fetchSnapshot,
  SNAPSHOT_ACTIVE,
  SnapshotAPIError,
  snapshotArtifactURL,
  submitSnapshot,
  validateSnapshotFiles,
  type SnapshotArtifactKind,
  type SnapshotFiles,
  type SnapshotJob,
  type SnapshotStatus,
} from "./snapshotApi";
const DiffView = lazy(() => import("./DiffView"));
const NOT_RUN = "Not run — bring the patch to your GPU";
const labels: Record<SnapshotStatus, string> = {
  receiving: "Receiving upload",
  preparing: "Preparing evidence",
  queued: "Queued",
  running: "Analyzing snapshot",
  completed: "Analysis complete",
  needs_human: "More information needed",
  budget_exceeded: "Analysis stopped",
  failed: "Analysis failed",
  timeout: "Analysis timed out",
  cancelled: "Analysis cancelled",
  expired: "Snapshot expired",
};
function bytes(value: unknown): string {
  const amount = numeric(value);
  return amount === null || amount < 0
    ? "Unknown"
    : `${amount.toLocaleString("en-US")} bytes (${gb(amount)})`;
}
function amount(value: unknown): string {
  const number = decimal(value);
  return number === null || number < 0
    ? "Unavailable"
    : number > 0 && number < 0.0001
      ? "<$0.0001"
      : `$${number.toFixed(4)}`;
}
function date(value?: string): string {
  const parsed = value ? new Date(value) : null;
  return parsed && !Number.isNaN(parsed.getTime())
    ? parsed.toLocaleString()
    : "Time unavailable";
}
function boundStacks(evidence: Dict): Dict[] | null {
  const binding = record(evidence.diagnosis_binding);
  const digests = [
    "snapshot_sha256",
    "evidence_json_sha256",
    "diagnosis_sha256",
  ];
  if (
    evidence.source !== "uploaded_snapshot" ||
    !digests.every(
      (key) =>
        typeof binding[key] === "string" &&
        /^[a-f0-9]{64}$/.test(binding[key] as string),
    ) ||
    binding.snapshot_sha256 !== evidence.snapshot_sha256 ||
    !Array.isArray(evidence.stacks) ||
    evidence.stacks.length > 200
  )
    return null;
  const stacks = rows(evidence.stacks);
  const ids = new Set(stacks.map((stack) => stack.id));
  if (
    stacks.length !== evidence.stacks.length ||
    ids.size !== stacks.length ||
    stacks.some(
      (stack) =>
        typeof stack.id !== "string" ||
        !/^stk_(?:[a-f0-9]{16}|[a-f0-9]{64})$/.test(stack.id) ||
        !Array.isArray(stack.frames),
    )
  )
    return null;
  return stacks;
}
function StackCitation({
  reference,
  stacks,
}: {
  reference: unknown;
  stacks: Dict[] | null;
}) {
  const [open, setOpen] = useState(false);
  const id = text(reference, "");
  const stack = stacks?.find((entry) => entry.id === id);
  if (!id) return null;
  if (!stack || rows(stack.frames).length === 0)
    return (
      <span className="caption" style={{ overflowWrap: "anywhere" }}>
        {id} · bound stack unavailable
      </span>
    );
  return (
    <div
      className="stack-reference"
      style={{ minWidth: 0, overflowWrap: "anywhere" }}
    >
      <button
        className="text-link"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{ whiteSpace: "normal", overflowWrap: "anywhere" }}
      >
        {id}
      </button>
      {open && (
        <div className="stack-block">
          <p className="caption">Uploaded snapshot · cited allocation stack</p>
          <dl className="key-values">
            <div>
              <dt>Live at recorded peak</dt>
              <dd>{bytes(stack.peak_live_bytes)}</dd>
            </div>
            <div>
              <dt>Allocated during capture</dt>
              <dd>{bytes(stack.lifetime_allocated_bytes)}</dd>
            </div>
          </dl>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {rows(stack.frames)
              .map(
                (frame) =>
                  `${text(frame.filename, "?")}:${frame.line ?? "?"} in ${text(frame.name)}`,
              )
              .join("\n") || "No frames retained."}
          </pre>
        </div>
      )}
    </div>
  );
}
function SnapshotResult({ job }: { job: SnapshotJob }) {
  const result = job.result!;
  const diagnosis = record(result.diagnosis),
    evidence = record(result.evidence);
  const analysis = record(evidence.analysis),
    patch = record(result.patch);
  const stacks = boundStacks(evidence);
  const peak = numeric(analysis.peak_allocated_bytes);
  const categories = Object.entries(record(analysis.category_bytes));
  const downloads: [SnapshotArtifactKind, string][] = [
    ["diagnosis_json", "Download diagnosis JSON"],
    ["diagnosis_markdown", "Download diagnosis Markdown"],
    ["patch", "Download unverified patch"],
  ];
  return (
    <div style={{ marginTop: 24 }}>
      {result.provenance === "offline_fixture" ? (
        <Notice>
          Offline test fixture — synthetic data, not a real model diagnosis.
        </Notice>
      ) : result.provenance !== "live_model" ? (
        <Notice>Diagnosis provenance is unavailable.</Notice>
      ) : null}
      <Notice>
        {NOT_RUN}. This analysis uses an uploaded capture. No workload or
        generated patch was executed.
      </Notice>
      <Section title="Uploaded snapshot" kicker="Captured evidence">
        <div className="metric-grid three">
          <div className="metric">
            <span>Recorded allocated peak</span>
            <strong>
              {peak === null
                ? "Unknown"
                : `${analysis.peak_is_exact === false ? "≥ " : ""}${gb(peak)}`}
            </strong>
            <small>
              {analysis.peak_is_exact === true
                ? "Reconstructed from the supplied capture"
                : "Capture completeness is limited or unknown"}
            </small>
          </div>
          <div className="metric">
            <span>Hardware verification</span>
            <strong>Not run</strong>
          </div>
          <div className="metric">
            <span>Reported analysis cost</span>
            <strong>{amount(result.cost_usd)}</strong>
          </div>
        </div>
        {categories.length ? (
          <div className="table-wrap">
            <table aria-label="Snapshot peak composition">
              <thead>
                <tr>
                  <th>Allocation origin</th>
                  <th>Live bytes at recorded peak</th>
                </tr>
              </thead>
              <tbody>
                {categories.map(([category, size]) => (
                  <tr key={category}>
                    <td>{human(category)}</td>
                    <td>{bytes(size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Peak composition unavailable" />
        )}
        <p className="caption">
          Allocation-origin categories are heuristics, not proof of the cause.
          Unknown measurements remain unknown.
        </p>
        {Array.isArray(analysis.warnings) && analysis.warnings.length > 0 && (
          <ul>
            {analysis.warnings.map((warning, index) => (
              <li key={index}>{text(warning)}</li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Snapshot diagnosis" kicker="Model hypotheses">
        <div className="diagnosis-cards">
          {rows(diagnosis.root_causes).length ? (
            rows(diagnosis.root_causes).map((cause, index) => (
              <article key={index}>
                <div className="diagnosis-index">
                  {String(index + 1).padStart(2, "0")}
                </div>
                <h3>{text(cause.title)}</h3>
                <p>{human(cause.category)}</p>
                <div className="diagnosis-stat">
                  <span>Estimated size</span>
                  <strong>
                    {numeric(cause.bytes_gb) === null
                      ? "Unknown"
                      : `${Number(cause.bytes_gb).toFixed(2)} GB`}
                  </strong>
                </div>
                <p className="caption">
                  Model hypothesis · confidence{" "}
                  {numeric(cause.confidence) === null
                    ? "unknown"
                    : `${(Number(cause.confidence) * 100).toFixed(0)}%`}
                </p>
                <div className="stack-refs">
                  {Array.isArray(cause.evidence_refs) &&
                    cause.evidence_refs.map((reference, i) => (
                      <StackCitation
                        key={i}
                        reference={reference}
                        stacks={stacks}
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
                  : "No diagnosis available"
              }
            />
          )}
        </div>
        {Array.isArray(diagnosis.notes) && diagnosis.notes.length > 0 && (
          <ul>
            {diagnosis.notes.map((note, index) => (
              <li key={index}>{text(note)}</li>
            ))}
          </ul>
        )}
      </Section>
      {rows(diagnosis.plan).length > 0 && (
        <Section title="Suggested fixes" kicker="Unverified plan">
          {rows(diagnosis.plan).map((step, index) => (
            <article className="round-note" key={index}>
              <h3>{text(step.title)}</h3>
              <p>{text(step.description)}</p>
              <p className="caption">
                Risk: {text(step.risk, "Not specified")}. Numerical impact:{" "}
                {human(step.numerics_impact)}.
              </p>
            </article>
          ))}
        </Section>
      )}
      <Section title="Patch draft" kicker="Hardware verification not run">
        {patch.status === "unverified" &&
        typeof patch.diff === "string" &&
        patch.diff.trim() ? (
          <>
            <Badge tone="amber">Unverified patch</Badge>
            <details>
              <summary>Inspect patch draft</summary>
              <Suspense fallback={<Loading />}>
                <DiffView diff={patch.diff} recorded />
              </Suspense>
            </details>
          </>
        ) : (
          <p>
            No patch draft is available. The diagnosis may need more source or
            runtime information.
          </p>
        )}
        <p className="caption">{NOT_RUN}.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          {downloads.map(([kind, label]) => {
            const url = snapshotArtifactURL(job, kind);
            return url &&
              (kind !== "patch" || patch.status === "unverified") ? (
              <a className="text-link" key={kind} href={url}>
                {label}
              </a>
            ) : null;
          })}
        </div>
      </Section>
    </div>
  );
}
export default function SnapshotDiagnosisPanel({
  enabled,
  requiresJudgeToken = false,
}: {
  enabled: boolean;
  requiresJudgeToken?: boolean;
}) {
  const [files, setFiles] = useState<SnapshotFiles>({
    snapshot: null,
    traceback: null,
    source: null,
  });
  const [token, setToken] = useState(""),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [job, setJob] = useState<SnapshotJob | null>(null);
  const [refresh, setRefresh] = useState(0),
    [pollError, setPollError] = useState("");
  const upload = useRef<AbortController | null>(null);
  useEffect(() => () => upload.current?.abort(), []);
  useEffect(() => {
    if (!enabled) setToken("");
  }, [enabled]);
  const runId = job?.run_id;
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await fetchSnapshot(runId, controller.signal);
        if (controller.signal.aborted) return;
        setJob(next);
        setPollError("");
        if (SNAPSHOT_ACTIVE.has(next.status)) timer = setTimeout(poll, 2000);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setPollError(
          reason instanceof Error
            ? reason.message
            : "Snapshot status is unavailable.",
        );
        if (
          reason instanceof SnapshotAPIError &&
          [404, 410].includes(reason.status)
        )
          setJob((previous) =>
            previous
              ? { ...previous, status: "expired", result: null, artifacts: {} }
              : null,
          );
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [runId, refresh]);
  const active = busy || (job !== null && SNAPSHOT_ACTIVE.has(job.status));
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || active) return;
    const invalid = validateSnapshotFiles(files);
    if (invalid) {
      setError(invalid);
      return;
    }
    if (requiresJudgeToken && !token.trim()) {
      setError("Enter your judge access token to upload a snapshot.");
      return;
    }
    const controller = new AbortController();
    upload.current = controller;
    setBusy(true);
    setError("");
    setPollError("");
    try {
      const next = await submitSnapshot(files, token, controller.signal);
      if (!controller.signal.aborted) setJob(next);
    } catch (reason) {
      if (!controller.signal.aborted)
        setError(
          reason instanceof Error
            ? reason.message
            : "The snapshot could not be uploaded.",
        );
    } finally {
      setToken("");
      setBusy(false);
    }
  }
  return (
    <div style={{ padding: "20px 0" }}>
      <p>
        Upload a PyTorch memory snapshot to get a diagnosis with cited
        allocation stacks and an unverified patch draft. Your script is not run.
      </p>
      <p className="caption">
        Uploads and generated artifacts are deleted after 24 hours. Keep a local
        copy of anything you need.
      </p>
      {!enabled ? (
        <Notice>Snapshot analysis is temporarily paused.</Notice>
      ) : (
        <form onSubmit={submit} aria-label="Diagnose my snapshot">
          <fieldset
            disabled={active}
            style={{ border: 0, padding: 0, minWidth: 0 }}
          >
            <div className="field">
              <label htmlFor="snapshot-file">
                Memory snapshot (.pickle or .pkl, up to 50 MiB)
              </label>
              <input
                id="snapshot-file"
                type="file"
                accept=".pickle,.pkl"
                onChange={(event) =>
                  setFiles((previous) => ({
                    ...previous,
                    snapshot: event.target.files?.[0] ?? null,
                  }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="snapshot-traceback">
                Traceback (optional, up to 256 KiB)
              </label>
              <input
                id="snapshot-traceback"
                type="file"
                accept=".txt,.log"
                onChange={(event) =>
                  setFiles((previous) => ({
                    ...previous,
                    traceback: event.target.files?.[0] ?? null,
                  }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="snapshot-source">
                Source code (optional, up to 1 MiB)
              </label>
              <input
                id="snapshot-source"
                type="file"
                accept=".py,.txt"
                onChange={(event) =>
                  setFiles((previous) => ({
                    ...previous,
                    source: event.target.files?.[0] ?? null,
                  }))
                }
              />
            </div>
            <div className="field">
              <label htmlFor="snapshot-token">
                {requiresJudgeToken
                  ? "Judge access token"
                  : "Judge token (optional)"}
              </label>
              <input
                id="snapshot-token"
                type="password"
                value={token}
                autoComplete="off"
                onChange={(event) => setToken(event.target.value)}
              />
              <small>
                {requiresJudgeToken
                  ? "An access token is required for private snapshot uploads. No hourly upload limit applies to authenticated judges."
                  : "Leave blank for anonymous access: up to two uploads per IP per hour."}{" "}
                The token is used only for this upload and is not saved.
              </small>
            </div>
            <button className="button button-primary" type="submit">
              {busy ? "Uploading…" : "Analyze snapshot"}
            </button>
          </fieldset>
        </form>
      )}
      {error && <Notice tone="red">{error}</Notice>}
      {job && (
        <div style={{ marginTop: 20 }}>
          <Badge
            tone={
              ["failed", "timeout", "expired"].includes(job.status)
                ? "amber"
                : "neutral"
            }
          >
            {labels[job.status]}
          </Badge>
          {job.expires_at && (
            <p className="caption">
              Expires: {date(job.expires_at)}. Files and results are retained
              for 24 hours.
            </p>
          )}
          {SNAPSHOT_ACTIVE.has(job.status) && (
            <Loading>
              Analyzing the capture. No GPU workload will be run.
            </Loading>
          )}
          {pollError && (
            <Notice tone="red">
              {pollError}{" "}
              {job.status !== "expired" && (
                <button
                  type="button"
                  className="text-link"
                  onClick={() => setRefresh((value) => value + 1)}
                >
                  Refresh status
                </button>
              )}
            </Notice>
          )}
          {job.result && job.status !== "expired" ? (
            <SnapshotResult job={job} />
          ) : !SNAPSHOT_ACTIVE.has(job.status) && job.status !== "expired" ? (
            <Empty title="No diagnosis result available">{NOT_RUN}.</Empty>
          ) : null}
        </div>
      )}
    </div>
  );
}
