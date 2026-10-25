export type Dict = Record<string, unknown>;
export const record = (value: unknown): Dict =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Dict)
    : {};
export const rows = (value: unknown): Dict[] =>
  Array.isArray(value)
    ? value
        .filter((v) => v && typeof v === "object" && !Array.isArray(v))
        .map(record)
    : [];
export const text = (value: unknown, fallback = "Unknown"): string =>
  typeof value === "string" && value.length > 0 ? value : fallback;
export const numeric = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
export function decimal(value: unknown): number | null {
  if (typeof value === "number") return numeric(value);
  if (
    typeof value !== "string" ||
    !/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)
  )
    return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
export const gb = (value: unknown) =>
  numeric(value) === null
    ? "Unknown"
    : `${(Number(value) / 1e9).toFixed(2)} GB`;
export const usd = (value: unknown) =>
  decimal(value) === null ? "Unknown" : `$${decimal(value)!.toFixed(4)}`;
// Preserve the exact decimal for an upper bound: rounding down would weaken it.
export function usdUpper(value: unknown): string {
  const amount = decimal(value);
  return amount === null || amount < 0 ? "Unknown" : "$" + String(value);
}
export function costUpperBound(usage: unknown): string {
  const u = record(usage);
  return u.billing_complete === true
    ? usdUpper(u.conservative_total_usd)
    : "Unknown";
}
export function costTotal(usage: unknown): string {
  const u = record(usage);
  if (u.complete === false || (numeric(u.unknown_cost_calls) ?? 0) > 0)
    return "Unknown";
  return usd(u.total_cost_usd);
}
export const human = (value: unknown) =>
  text(value, "unknown").replaceAll("_", " ").replaceAll(".", " · ");
export const TERMINAL = new Set([
  "completed",
  "done",
  "failed",
  "needs_human",
  "budget_exceeded",
  "cancelled",
  "rejected",
  "timeout",
]);
export function provenanceLabel(run: Dict, replay = false): string | null {
  const source = text(run.provenance, "").toLowerCase();
  if (
    source.includes("fixture") ||
    source.includes("mock") ||
    source.includes("offline")
  )
    return "Offline fixture · not a verified repair";
  if (source === "recorded_baseline")
    return "Recorded GPU baseline · no repair performed";
  if (replay || source.includes("replay"))
    return "Saved replay · historical evidence";
  return null;
}
export interface RunEvent {
  sequence: number;
  kind: string;
  data: Dict;
  created_at?: string;
}
export function parseEvent(value: unknown): RunEvent | null {
  const d = record(value);
  const sequence = numeric(d.sequence);
  if (
    sequence === null ||
    !Number.isInteger(sequence) ||
    sequence < 1 ||
    typeof d.kind !== "string"
  )
    return null;
  return {
    sequence,
    kind: d.kind,
    data: record(d.data),
    created_at: typeof d.created_at === "string" ? d.created_at : undefined,
  };
}
export function mergeEvents(
  existing: RunEvent[],
  incoming: RunEvent,
): RunEvent[] {
  if (existing.some((e) => e.sequence === incoming.sequence)) return existing;
  return [...existing, incoming].sort((a, b) => a.sequence - b.sequence);
}
const ARTIFACTS = new Set([
  "cli.json",
  "configuration.json",
  "pareto.json",
  "pareto.md",
  "annotations.json",
  "report.md",
  "report.json",
  "patch.diff",
  "env.sh",
  "evidence.json",
  "evidence.md",
  "timeline-before.png",
  "timeline-after.png",
]);
export function artifactLink(
  runId: string,
  name: string,
  artifacts: unknown,
): string | null {
  if (!/^[a-f0-9]{32}$/.test(runId) || !ARTIFACTS.has(name)) return null;
  const expected = `/api/runs/${runId}/${name}`;
  return record(artifacts)[name] === expected ? expected : null;
}
export function externalLink(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) &&
      !u.username &&
      !u.password
      ? u.href
      : null;
  } catch {
    return null;
  }
}
export function analysisOf(
  report: Dict,
  side: "before" | "after",
  evidence?: Dict,
): Dict {
  const e = record(report.evidence);
  const bundle = side === "before" ? record(e.before ?? e) : record(e.after);
  const analysis = record(
    bundle.analysis ?? (bundle.header ? bundle : undefined),
  );
  if (Object.keys(analysis).length) return analysis;
  return side === "before" ? record(evidence?.analysis ?? evidence) : {};
}
export interface TimelinePoint {
  event: number;
  before: number | null;
  after: number | null;
}
export function timelinePoints(before: Dict, after: Dict): TimelinePoint[] {
  const merged = new Map<number, TimelinePoint>();
  for (const [side, data] of [
    ["before", before],
    ["after", after],
  ] as const) {
    for (const row of rows(data.timeline)) {
      const index = numeric(row.event_index),
        amount = numeric(row.allocated_bytes);
      if (index === null || amount === null || amount < 0) continue;
      const point = merged.get(index) ?? {
        event: index,
        before: null,
        after: null,
      };
      point[side] = amount / 1e9;
      merged.set(index, point);
    }
  }
  return [...merged.values()].sort((a, b) => a.event - b.event);
}
export function measurement(
  report: Dict,
  side: "before" | "after",
  key: string,
): unknown {
  return record(record(report.measurements)[side])[key];
}
export function displayMetric(
  report: Dict,
  key: string,
  fallback?: unknown,
): string {
  const value = record(report.display)[key];
  if (typeof value === "string") return value === "unknown" ? "Unknown" : value;
  return fallback === undefined ? "Unknown" : gb(fallback);
}
export function verificationRows(
  report: Dict,
): { label: string; value: string }[] {
  const verification = record(report.verification);
  const summary = record(report.summary);
  const checks = record(verification.checks);
  return [
    {
      label: "Target met",
      value:
        record(report.run).provenance === "recorded_baseline"
          ? "N/A — baseline only"
          : summary.target_met === true
            ? "Yes — verifier reported"
            : summary.target_met === false
              ? "No"
              : "Unknown",
    },
    {
      label: "Peak allocated before",
      value: displayMetric(report, "peak_before"),
    },
    {
      label: "Peak allocated after",
      value: displayMetric(report, "peak_after"),
    },
    { label: "Peak reduction", value: displayMetric(report, "peak_reduction") },
    { label: "Step time before", value: displayMetric(report, "step_before") },
    { label: "Step time after", value: displayMetric(report, "step_after") },
    {
      label: "Step-time change",
      value: displayMetric(report, "step_time_change"),
    },
    { label: "Numerical equivalence", value: text(summary.loss_equivalence) },
    ...Object.entries(checks).map(([label, value]) => ({
      label: human(label),
      value:
        typeof value === "boolean"
          ? value
            ? "Passed"
            : "Not passed"
          : typeof value === "string"
            ? value
            : "See report JSON",
    })),
  ];
}
export type SearchMode = "until_target" | "bounded_pareto";
export const searchModeLabel = (value: unknown) =>
  value === "until_target"
    ? "Stop when target is met"
    : value === "bounded_pareto"
      ? "Explore more configurations"
      : "Not recorded";
export interface Submission {
  search_mode?: SearchMode;
  script_text?: string;
  example_id?: string;
  allocator_conf?: string | null;
  target: string;
  budget: string;
  policy: {
    allow_numerics_change: boolean;
    allow_model_change: boolean;
    allow_batch_grad_accum: boolean;
    max_throughput_regression_pct: number;
  };
}
export function validateSubmission(input: Submission): string | null {
  if (Boolean(input.example_id) === Boolean(input.script_text?.trim()))
    return "Choose an example or paste a Python script.";
  if (
    input.script_text &&
    new TextEncoder().encode(input.script_text).length > 1024 * 1024
  )
    return "The script must be smaller than 1 MiB.";
  if (
    input.search_mode !== undefined &&
    !["until_target", "bounded_pareto"].includes(input.search_mode)
  )
    return "Choose a valid search mode.";
  const budget = decimal(input.budget);
  if (budget === null || budget <= 0 || budget > 5)
    return "Enter a run budget greater than $0 and at most $5.";
  if (
    input.target !== "fix-oom" &&
    input.target !== "reclaim" &&
    !/^fit:[0-9]+(?:\.[0-9]+)?GB$/.test(input.target)
  )
    return "Enter a valid memory target.";
  if (input.target.startsWith("fit:") && Number(input.target.slice(4, -2)) <= 0)
    return "Memory target must be greater than zero.";
  return null;
}
export const EVENT_KINDS = [
  "run.started",
  "baseline.started",
  "baseline.oom",
  "baseline.completed",
  "evidence.built",
  "annotate.done",
  "diagnose.started",
  "diagnose.done",
  "research.called",
  "research.done",
  "patch.written",
  "patch.applied",
  "patch.failed",
  "verify.started",
  "verify.done",
  "round.done",
  "target.met",
  "budget.exceeded",
  "run.done",
  "run.failed",
  "needs_human",
  "run.preflight",
  "run.queued",
  "evidence.started",
  "patch.started",
  "report.started",
  "report.written",
  "verify.reference",
  "budget.reserved",
];

export function configurationLink(
  runId: string,
  relative: unknown,
): string | null {
  if (
    !/^[a-f0-9]{32}$/.test(runId) ||
    typeof relative !== "string" ||
    !/^configurations\/round-0[1-6]\/(patch\.diff|env\.sh|cli\.json|manifest\.json)$/.test(
      relative,
    )
  )
    return null;
  return `/api/runs/${runId}/${relative}`;
}

export function queueAtCapacity(queue: Dict): boolean {
  if (queue.halted === true || queue.closing === true) return true;
  const capacity = numeric(queue.capacity);
  if (capacity === null) return false;
  const running =
    typeof queue.running === "string" && queue.running.length > 0 ? 1 : 0;
  return (
    (numeric(queue.pending) ?? 0) + (numeric(queue.preparing) ?? 0) + running >=
    capacity
  );
}

export function availabilityBlocks(health: Dict): {
  gpuBusy: boolean;
  budgetBlocked: boolean;
  budgetReason:
    "exhausted" | "billing_review_required" | "pending_charge" | null;
} {
  const gpu = record(health.gpu),
    budget = record(health.local_budget);
  const reason =
    budget.scope === "local_application_authorization" &&
    (budget.status === "exhausted" ||
      budget.status === "billing_review_required" ||
      budget.status === "pending_charge")
      ? budget.status
      : null;
  return {
    gpuBusy: gpu.status === "busy" && gpu.busy === true && gpu.stale !== true,
    budgetBlocked: reason !== null,
    budgetReason: reason,
  };
}
