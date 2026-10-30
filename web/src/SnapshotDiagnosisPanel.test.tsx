/** Synthetic offline UI fixtures only. These are not real diagnoses or GPU runs. */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import App from "./App";
import SnapshotDiagnosisPanel from "./SnapshotDiagnosisPanel";
import {
  fetchSnapshot,
  SNAPSHOT_LIMITS,
  snapshotArtifactURL,
  submitSnapshot,
  validateSnapshotFiles,
  type SnapshotFiles,
} from "./snapshotApi";
const ID = "a".repeat(32),
  STACK = "stk_" + "b".repeat(16),
  HASH = "c".repeat(64);
const reply = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));
function file(name: string, size = 4) {
  const value = new File(["mock"], name);
  Object.defineProperty(value, "size", { value: size });
  return value;
}
function files(): SnapshotFiles {
  return { snapshot: file("snapshot.pickle"), traceback: null, source: null };
}
function completed() {
  return {
    run_id: ID,
    status: "completed",
    created_at: "2026-10-29T00:00:00+00:00",
    expires_at: "2026-10-30T00:00:00+00:00",
    result: {
      kind: "snapshot_diagnosis",
      provenance: "offline_fixture",
      cost_usd: null,
      diagnosis: {
        root_causes: [
          {
            id: "c1",
            title: "Offline UI fixture — activation hypothesis",
            category: "activations",
            bytes_gb: 2.5,
            confidence: 0.8,
            evidence_refs: [STACK],
          },
        ],
        plan: [
          {
            fix_id: "f1",
            title: "Inspect activation lifetime",
            description: "Synthetic unverified suggestion.",
            risk: "Hardware checks required",
            numerics_impact: "none",
          },
        ],
        needs_more_info: false,
        notes: ["Offline UI fixture; no real model or GPU call."],
      },
      evidence: {
        source: "uploaded_snapshot",
        snapshot_sha256: HASH,
        diagnosis_binding: {
          snapshot_sha256: HASH,
          evidence_json_sha256: "d".repeat(64),
          diagnosis_sha256: "e".repeat(64),
        },
        analysis: {
          peak_allocated_bytes: 4_000_000_000,
          peak_is_exact: false,
          category_bytes: { activations: 3_000_000_000, unknown: null },
          warnings: ["Incomplete capture history."],
        },
        stacks: [
          {
            id: STACK,
            peak_live_bytes: null,
            lifetime_allocated_bytes: 123456,
            frames: [
              { filename: "/uploaded/train.py", line: 14, name: "forward" },
            ],
          },
        ],
      },
      patch: {
        status: "unverified",
        diff: "--- a/train.py\\n+++ b/train.py\\n@@ -1 +1 @@\\n-x = 1\\n+x = 2\\n",
      },
      verification: {
        status: "not_run",
        message: "Not run — bring the patch to your GPU",
      },
    },
    artifacts: {
      diagnosis_json: { url: `/api/snapshots/${ID}/download/diagnosis_json` },
      diagnosis_markdown: {
        url: `/api/snapshots/${ID}/download/diagnosis_markdown`,
      },
      patch: { url: `/api/snapshots/${ID}/download/patch` },
    },
  };
}
function mockJob(document = completed()) {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: unknown, init?: RequestInit) => {
      if (path === "/api/snapshots" && init?.method === "POST")
        return reply({ run_id: ID, status: "queued" }, 202);
      if (path === `/api/snapshots/${ID}`) return reply(document);
      throw new Error("Unexpected request in offline snapshot UI test");
    }),
  );
}
function selectSnapshot(value = file("snapshot.pickle")) {
  fireEvent.change(screen.getByLabelText(/Memory snapshot/), {
    target: { files: [value] },
  });
}
beforeEach(() => {
  window.history.replaceState({}, "", "/");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("keeps the Home panel paused when config is absent or false despite a forged query", async () => {
  window.history.replaceState({}, "", "/?snapshot_submissions_enabled=true");
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      reply({
        snapshot_submissions_enabled: true,
        snapshot_submissions: { enabled: false },
      }),
    ),
  );
  render(<App />);
  fireEvent.click(screen.getByText("Diagnose my snapshot"));
  expect(
    await screen.findByText("Snapshot analysis is temporarily paused."),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("form", { name: "Diagnose my snapshot" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Diagnose my snapshot" }),
  ).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.map(([path]) => path)).toEqual([
    "/api/config",
  ]);
});
it("does not submit while paused even if a file had been selected before disabling", async () => {
  mockJob();
  const view = render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  view.rerender(<SnapshotDiagnosisPanel enabled={false} />);
  expect(
    screen.queryByRole("button", { name: "Analyze snapshot" }),
  ).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
it("rejects missing or empty required input without a network request", () => {
  vi.stubGlobal("fetch", vi.fn());
  render(<SnapshotDiagnosisPanel enabled />);
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Choose a PyTorch memory snapshot",
  );
  selectSnapshot(file("empty.pickle", 0));
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(screen.getByRole("alert")).toHaveTextContent("snapshot file is empty");
  expect(fetch).not.toHaveBeenCalled();
});
it.each(["snapshot", "traceback", "source"] as const)(
  "enforces the %s byte boundary before POST",
  async (kind) => {
    vi.stubGlobal("fetch", vi.fn());
    const input = files();
    input[kind] = file(kind, SNAPSHOT_LIMITS[kind] + 1);
    await expect(submitSnapshot(input, "")).rejects.toThrow("exceeds");
    expect(fetch).not.toHaveBeenCalled();
    input[kind] = file(kind, SNAPSHOT_LIMITS[kind]);
    expect(validateSnapshotFiles(input)).toBeNull();
  },
);
it("sends multipart fields and the ephemeral judge token only in the POST header", async () => {
  mockJob();
  const local = vi.spyOn(Storage.prototype, "setItem");
  const cookieBefore = document.cookie;
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.change(screen.getByLabelText(/Traceback/), {
    target: { files: [file("oom.txt")] },
  });
  fireEvent.change(screen.getByLabelText(/Source code/), {
    target: { files: [file("train.py")] },
  });
  fireEvent.change(screen.getByLabelText("Judge token (optional)"), {
    target: { value: "offline-ui-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Analysis complete")).toBeInTheDocument();
  const post = vi
    .mocked(fetch)
    .mock.calls.find(([path]) => path === "/api/snapshots")!;
  expect(post[1]?.headers).toEqual({
    Authorization: "Bearer offline-ui-token",
  });
  expect(post[1]?.credentials).toBe("same-origin");
  const form = post[1]?.body as FormData;
  expect([...form.keys()]).toEqual(["snapshot", "traceback", "source"]);
  expect(form.get("token")).toBeNull();
  const get = vi
    .mocked(fetch)
    .mock.calls.find(([path]) => path === `/api/snapshots/${ID}`)!;
  expect(get[1]?.headers).toBeUndefined();
  expect(screen.getByLabelText("Judge token (optional)")).toHaveValue("");
  expect(local).not.toHaveBeenCalled();
  expect(document.cookie).toBe(cookieBefore);
  expect(window.location.href).not.toContain("offline-ui-token");
});
it("supports anonymous submission without Authorization and keeps limit errors visible", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      reply({ detail: "Two snapshot uploads per hour are allowed" }, 429),
    ),
  );
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Two snapshot uploads per hour",
  );
  expect(vi.mocked(fetch).mock.calls[0][1]?.headers).toBeUndefined();
  expect(screen.queryByText("Analysis complete")).not.toBeInTheDocument();
});
it("shows diagnosis, measured evidence and unverified status without inventing repair gains", async () => {
  mockJob();
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(
    await screen.findByRole("heading", { name: "Snapshot diagnosis" }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByText(/Not run — bring the patch to your GPU/).length,
  ).toBeGreaterThan(0);
  expect(screen.getByText("≥ 4.00 GB")).toBeInTheDocument();
  expect(screen.getByText(/Offline test fixture/)).toBeInTheDocument();
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("table", { name: "Snapshot peak composition" }),
  ).toHaveTextContent("Unknown");
  expect(screen.getByText(/Expires:/)).toHaveTextContent(
    "retained for 24 hours",
  );
  expect(
    screen.queryByText(
      /Peak after|Memory reduction|Repair succeeded|Target met/i,
    ),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: STACK }));
  expect(
    screen.getByText("/uploaded/train.py:14 in forward"),
  ).toBeInTheDocument();
  const stack = screen
    .getByText("Uploaded snapshot · cited allocation stack")
    .closest<HTMLElement>(".stack-block")!;
  expect(
    within(stack).getByText("Live at reconstructed peak").closest("div"),
  ).toHaveTextContent("Unknown");
  expect(
    within(stack).getByText("Allocated during capture").closest("div"),
  ).toHaveTextContent("123,456 bytes");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(
    screen.getByRole("link", { name: "Download unverified patch" }),
  ).toHaveAttribute("href", `/api/snapshots/${ID}/download/patch`);
});
it.each(["missing", "mismatched", "duplicate", "empty_frames"] as const)(
  "does not link stacks with %s binding information",
  async (mode) => {
    const document = completed();
    if (mode === "missing")
      document.result.evidence.diagnosis_binding.diagnosis_sha256 = "";
    if (mode === "mismatched")
      document.result.evidence.snapshot_sha256 = "f".repeat(64);
    if (mode === "empty_frames") document.result.evidence.stacks[0].frames = [];
    if (mode === "duplicate")
      document.result.evidence.stacks.push(document.result.evidence.stacks[0]);
    mockJob(document);
    render(<SnapshotDiagnosisPanel enabled />);
    selectSnapshot();
    fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
    await screen.findByRole("heading", { name: "Snapshot diagnosis" });
    expect(
      screen.queryByRole("button", { name: STACK }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/bound stack unavailable/)).toBeInTheDocument();
  },
);
it("allows only this snapshot's API-supplied download URLs and hides unavailable patch assets", async () => {
  const document = completed();
  document.artifacts.diagnosis_json.url = "https://example.org/private.json";
  document.artifacts.diagnosis_markdown.url = `/api/snapshots/${"f".repeat(32)}/download/diagnosis_markdown`;
  document.result.patch.status = "unavailable";
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  await screen.findByRole("heading", { name: "Snapshot diagnosis" });
  expect(
    screen.queryByRole("link", { name: /Download/ }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Inspect patch draft")).not.toBeInTheDocument();
  const job = await fetchSnapshot(ID);
  expect(
    snapshotArtifactURL(
      { ...job, artifacts: { diagnosis_json: { path: "diagnosis.json" } } },
      "diagnosis_json",
    ),
  ).toBeNull();
});
it("keeps a positive tiny reported cost visible instead of rounding it to zero", async () => {
  const document = completed();
  Object.assign(document.result, { cost_usd: "0.00001" });
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("<$0.0001")).toBeInTheDocument();
});
it("keeps completed-without-result distinct from a verified GPU repair", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      reply({ run_id: ID, status: "completed", result: null, artifacts: {} }),
    ),
  );
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(
    await screen.findByText("No diagnosis result available"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Hardware verification was not run."),
  ).toBeInTheDocument();
});
it("removes result downloads when the server reports the upload unavailable or expired", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: unknown) =>
      path === "/api/snapshots"
        ? reply({ run_id: ID, status: "queued" }, 202)
        : reply({}, 404),
    ),
  );
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Snapshot expired")).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /Download/ }),
  ).not.toBeInTheDocument();
});
it("cancels status polling on unmount", async () => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => reply({ run_id: ID, status: "running" })),
  );
  const view = render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" })),
  );
  expect(fetch).toHaveBeenCalledTimes(2);
  const signal = vi.mocked(fetch).mock.calls[1][1]?.signal;
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => vi.advanceTimersByTime(10000));
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("rejects a mismatched owner response identifier", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => reply({ run_id: "f".repeat(32), status: "completed" })),
  );
  await expect(fetchSnapshot(ID)).rejects.toThrow("did not match this upload");
});

it("enables Home snapshot uploads only from the nested server submission flag", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      reply({
        snapshot_submissions: { enabled: true },
        judge_scripts_available: false,
      }),
    ),
  );
  render(<App />);
  fireEvent.click(screen.getByText("Diagnose my snapshot"));
  expect(
    await screen.findByRole("form", { name: "Diagnose my snapshot" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Analyze snapshot" }),
  ).toBeEnabled();
});

it("requires the server-declared judge token before a private upload", async () => {
  mockJob();
  render(<SnapshotDiagnosisPanel enabled requiresJudgeToken />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Enter your judge access token",
  );
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Judge access token"), {
    target: { value: "offline-ui-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Analysis complete")).toBeInTheDocument();
  const post = vi
    .mocked(fetch)
    .mock.calls.find(([path]) => path === "/api/snapshots")!;
  expect(post[1]?.headers).toEqual({
    Authorization: "Bearer offline-ui-token",
  });
  expect(screen.getByLabelText("Judge access token")).toHaveValue("");
});

it("uses the server's private snapshot flag on Home", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      reply({
        snapshot_submissions: { enabled: true, requires_judge_token: true },
      }),
    ),
  );
  render(<App />);
  fireEvent.click(screen.getByText("Diagnose my snapshot"));
  expect(
    await screen.findByLabelText("Judge access token"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/Leave blank for anonymous access/),
  ).not.toBeInTheDocument();
});

it("labels host-derived quantities without claiming causal savings", async () => {
  const document = completed();
  Object.assign(document.result.evidence.diagnosis_binding, {
    quantity_source: "cited_peak_stack_sum_v1",
  });
  Object.assign(document.result.evidence.stacks[0], {
    peak_live_bytes: 2_500_000_000,
  });
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Cited peak allocation")).toBeInTheDocument();
  expect(screen.queryByText("Estimated size")).not.toBeInTheDocument();
  expect(screen.getByText(/They do not establish causal contribution or savings/)).toBeInTheDocument();
  expect(screen.getByText("Reconstructed allocated peak")).toBeInTheDocument();
});

it("retains the estimate label for older results", async () => {
  mockJob();
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Estimated size")).toBeInTheDocument();
  expect(screen.queryByText("Cited peak allocation")).not.toBeInTheDocument();
});


it("distinguishes a rejected model response from missing information and does not suggest a nonexistent patch", async () => {
  const document = completed();
  Object.assign(document, { status: "needs_human" });
  Object.assign(document.result, {
    provenance: "live_model",
    diagnosis: null,
    error: "diagnosis_unavailable",
    patch: { status: "unavailable", diff: null },
  });
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Model response rejected")).toBeInTheDocument();
  expect(screen.getByText(/No reliable diagnosis is available for this upload/)).toBeInTheDocument();
  expect(screen.getByText("No validated diagnosis available")).toBeInTheDocument();
  expect(screen.queryByText("More information needed")).not.toBeInTheDocument();
  expect(screen.queryByText(/bring the patch to your GPU/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Download unverified patch" })).not.toBeInTheDocument();
  expect(screen.getByText("No patch draft was generated because the model response did not pass validation.")).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Snapshot peak composition" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download diagnosis JSON" })).toBeInTheDocument();
});

it("keeps a valid needs-human diagnosis distinct from validation rejection without claiming a patch exists", async () => {
  const document = completed();
  Object.assign(document, { status: "needs_human" });
  Object.assign(document.result.diagnosis, { needs_more_info: true });
  Object.assign(document.result, { patch: { status: "unavailable", diff: null } });
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("More information needed")).toBeInTheDocument();
  expect(screen.getByText("Offline UI fixture — activation hypothesis")).toBeInTheDocument();
  expect(screen.queryByText("Model response rejected")).not.toBeInTheDocument();
  expect(screen.queryByText(/bring the patch to your GPU/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Download unverified patch" })).not.toBeInTheDocument();
});

it("does not label unrelated unavailable results as model validation rejection", async () => {
  const document = completed();
  Object.assign(document, { status: "failed" });
  Object.assign(document.result, {
    diagnosis: null,
    error: "runtime_unavailable",
    patch: { status: "unavailable", diff: null },
  });
  mockJob(document);
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByText("Analysis failed")).toBeInTheDocument();
  expect(screen.queryByText("Model response rejected")).not.toBeInTheDocument();
  expect(screen.queryByText(/bring the patch to your GPU/)).not.toBeInTheDocument();
});


it("explains an upload timeout without suggesting that a model diagnosis ran", async () => {
  vi.stubGlobal("fetch", vi.fn(() => reply({ detail: "Snapshot upload deadline exceeded" }, 408)));
  render(<SnapshotDiagnosisPanel enabled />);
  selectSnapshot();
  fireEvent.click(screen.getByRole("button", { name: "Analyze snapshot" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The snapshot upload exceeded its time limit. Analysis did not start.",
  );
  expect(screen.queryByText("Analysis complete")).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls).toHaveLength(1);
});
