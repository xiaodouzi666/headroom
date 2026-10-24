import { record, text, type Dict, type Submission } from "./data";
export async function getJSON(
  path: string,
  signal?: AbortSignal,
): Promise<Dict> {
  const response = await fetch(path, { credentials: "same-origin", signal });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response.");
  }
  if (!response.ok)
    throw new Error(
      text(record(body).detail, `Request failed (${response.status}).`),
    );
  return record(body);
}
export async function submitRun(data: Submission): Promise<Dict> {
  const response = await fetch("/api/runs", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const body = record(await response.json());
  if (!response.ok)
    throw new Error(
      text(body.detail, `Could not start the run (${response.status}).`),
    );
  if (typeof body.run_id !== "string" || !/^[a-f0-9]{32}$/.test(body.run_id))
    throw new Error("The server returned an invalid run identifier.");
  return body;
}
export async function getText(
  path: string,
  signal?: AbortSignal,
): Promise<string> {
  const response = await fetch(path, { credentials: "same-origin", signal });
  if (!response.ok)
    throw new Error(`Artifact unavailable (${response.status}).`);
  return response.text();
}
