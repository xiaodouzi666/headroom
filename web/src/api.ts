import { record, type Dict, type Submission } from "./data";
export async function getJSON(
  path: string,
  signal?: AbortSignal,
): Promise<Dict> {
  const response = await fetch(path, {
    credentials: "same-origin",
    signal,
    headers: { "X-Headroom-View": "product-v1" },
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error("The server returned an unreadable response.");
  }
  if (!response.ok) throw new Error(requestError(response.status));
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
  if (!response.ok) throw new Error(requestError(response.status));
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

const messages = new Set([
  "Additional details are available in the downloaded report.",
  "The provider has not supplied a complete usage total.",
  "The run reached its model-usage limit.",
  "Model access is unavailable.",
  "The numerical comparison did not pass.",
  "The numerical reference differs.",
  "A complete patch was not produced.",
  "The run reached its time limit.",
  "The requested memory target was reached.",
  "The model service is unavailable.",
  "Analysis stopped.",
  "A completed run has not verified the repair.",
  "Some captured measurements are incomplete or inconsistent. Inspect the downloaded report.",
  "Some output files are unavailable. Inspect the downloaded report.",
]);
export function productMessage(
  value: unknown,
  fallback = "Additional details are available in the downloaded report.",
): string {
  return typeof value === "string" && messages.has(value) ? value : fallback;
}
export function requestError(status: number): string {
  return (
    (
      {
        400: "The request could not be processed. Check the supplied inputs.",
        401: "This request needs a valid session.",
        403: "This action is unavailable for this session.",
        404: "The requested result is unavailable for this session.",
        409: "The service is busy. Please try again shortly.",
        413: "The uploaded file is too large.",
        422: "The supplied inputs are invalid.",
        429: "Too many requests. Please try again later.",
        503: "The service is temporarily unavailable. Please try again later.",
      } as Record<number, string>
    )[status] ?? "The request could not be completed. Please try again."
  );
}
