import { record, text, type Dict } from "./data";

export const SNAPSHOT_LIMITS = {
  snapshot: 50 * 1024 * 1024,
  traceback: 256 * 1024,
  source: 1024 * 1024,
} as const;
export type SnapshotFiles = {
  snapshot: File | null;
  traceback: File | null;
  source: File | null;
};
export type SnapshotStatus =
  | "receiving"
  | "preparing"
  | "queued"
  | "running"
  | "completed"
  | "needs_human"
  | "budget_exceeded"
  | "failed"
  | "timeout"
  | "cancelled"
  | "expired";
export type SnapshotArtifactKind =
  "diagnosis_json" | "diagnosis_markdown" | "patch";
export type SnapshotJob = {
  run_id: string;
  status: SnapshotStatus;
  created_at?: string;
  expires_at?: string;
  result: Dict | null;
  artifacts: Dict;
};
export const SNAPSHOT_ACTIVE = new Set<SnapshotStatus>([
  "receiving",
  "preparing",
  "queued",
  "running",
]);
const statuses = new Set<SnapshotStatus>([
  ...SNAPSHOT_ACTIVE,
  "completed",
  "needs_human",
  "budget_exceeded",
  "failed",
  "timeout",
  "cancelled",
  "expired",
]);
export class SnapshotAPIError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export function validateSnapshotFiles(files: SnapshotFiles): string | null {
  if (!files.snapshot) return "Choose a PyTorch memory snapshot first.";
  for (const [kind, maximum] of Object.entries(SNAPSHOT_LIMITS)) {
    const file = files[kind as keyof SnapshotFiles];
    if (!file) continue;
    if (file.size === 0) return `The ${kind} file is empty.`;
    if (file.size > maximum)
      return `The ${kind} file exceeds its ${kind === "snapshot" ? "50 MiB" : kind === "traceback" ? "256 KiB" : "1 MiB"} limit.`;
  }
  return null;
}
async function responseJSON(response: Response): Promise<Dict> {
  let body: Dict;
  try {
    body = record(await response.json());
  } catch {
    throw new SnapshotAPIError(
      "The server returned an unreadable response.",
      response.status,
    );
  }
  if (!response.ok) {
    const fallback =
      response.status === 404 || response.status === 410
        ? "This snapshot is unavailable or its 24-hour retention has ended."
        : response.status === 401 || response.status === 403
          ? "The judge token or session was not accepted."
          : response.status === 503
            ? "Snapshot analysis is temporarily paused."
            : `Snapshot request failed (${response.status}).`;
    throw new SnapshotAPIError(
      response.status === 429 || response.status === 413
        ? text(body.detail, fallback).slice(0, 300)
        : fallback,
      response.status,
    );
  }
  return body;
}
function parseJob(body: Dict): SnapshotJob {
  if (
    typeof body.run_id !== "string" ||
    !/^[a-f0-9]{32}$/.test(body.run_id) ||
    !statuses.has(body.status as SnapshotStatus)
  )
    throw new Error("The server returned an invalid snapshot response.");
  return {
    run_id: body.run_id,
    status: body.status as SnapshotStatus,
    created_at:
      typeof body.created_at === "string" ? body.created_at : undefined,
    expires_at:
      typeof body.expires_at === "string" ? body.expires_at : undefined,
    result:
      body.result &&
      typeof body.result === "object" &&
      !Array.isArray(body.result)
        ? record(body.result)
        : null,
    artifacts: record(body.artifacts),
  };
}
export async function submitSnapshot(
  files: SnapshotFiles,
  token: string,
  signal?: AbortSignal,
): Promise<SnapshotJob> {
  const invalid = validateSnapshotFiles(files);
  if (invalid) throw new Error(invalid);
  const cleanToken = token.trim();
  if (/[\x00-\x1f\x7f]/.test(cleanToken))
    throw new Error("Enter a valid judge token.");
  const form = new FormData();
  for (const [name, file] of Object.entries(files))
    if (file) form.append(name, file);
  const response = await fetch("/api/snapshots", {
    method: "POST",
    credentials: "same-origin",
    signal,
    headers: cleanToken ? { Authorization: `Bearer ${cleanToken}` } : undefined,
    body: form,
  });
  return parseJob(await responseJSON(response));
}
export async function fetchSnapshot(
  runId: string,
  signal?: AbortSignal,
): Promise<SnapshotJob> {
  if (!/^[a-f0-9]{32}$/.test(runId))
    throw new Error("Invalid snapshot identifier.");
  const response = await fetch(`/api/snapshots/${runId}`, {
    credentials: "same-origin",
    signal,
  });
  const job = parseJob(await responseJSON(response));
  if (job.run_id !== runId)
    throw new Error("The snapshot response did not match this upload.");
  return job;
}
export function snapshotArtifactURL(
  job: SnapshotJob,
  kind: SnapshotArtifactKind,
): string | null {
  const url = record(job.artifacts[kind]).url;
  return typeof url === "string" &&
    url === `/api/snapshots/${job.run_id}/download/${kind}`
    ? url
    : null;
}
