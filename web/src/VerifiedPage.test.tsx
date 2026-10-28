/** Offline rendering of the prepared records; this does not activate the gallery. */
import preparedCatalog from "../../public-evidence/verified-runs.json";
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import App from "./App";
import VerifiedPage from "./VerifiedPage";
const prepared = JSON.parse(JSON.stringify(preparedCatalog));

function published() {
  const document = structuredClone(prepared);
  document.publication_status = "published";
  for (const run of document.runs)
    for (const [kind, asset] of Object.entries(run.downloads))
      Object.assign(asset as object, {
        url: `/api/verified/${run.run_id}/download/${kind}`,
      });
  return document;
}
const response = (data: unknown) =>
  Promise.resolve(new Response(JSON.stringify(data), { status: 200 }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
function mockCatalog(document = published()) {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: unknown) =>
      path === "/api/verified"
        ? response(document)
        : Promise.reject(
            new Error("No other network calls in this offline test"),
          ),
    ),
  );
}
it("keeps the gallery closed and never requests records when the server flag is false", async () => {
  window.history.replaceState({}, "", "/verified?verified_runs_enabled=true");
  vi.stubGlobal(
    "fetch",
    vi.fn((path: unknown) =>
      path === "/api/config"
        ? response({ verified_runs_enabled: false, public_demo: true })
        : Promise.reject(new Error("Gallery must stay closed")),
    ),
  );
  render(<App />);
  expect(
    await screen.findByText("Verified runs are not open yet"),
  ).toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.map(([path]) => path)).toEqual([
    "/api/config",
  ]);
  expect(
    screen.queryByRole("link", { name: "Verified runs" }),
  ).not.toBeInTheDocument();
});
it("shows four recorded repairs and two unresolved examples without combining their score", async () => {
  mockCatalog();
  render(<VerifiedPage enabled />);
  expect(await screen.findAllByText("Recorded repair")).toHaveLength(4);
  expect(screen.getAllByText("Not solved — here is why")).toHaveLength(2);
  expect(
    screen.getAllByRole("heading", { name: "Initial diagnosis" }),
  ).toHaveLength(6);
  expect(screen.getByText(/not a combined success score/)).toBeInTheDocument();
  for (const id of ["s1_batch_too_big", "nanogpt"]) {
    const run = prepared.runs.find(
      (item: { scenario_id: string }) => item.scenario_id === id,
    );
    const card = screen
      .getByRole("heading", { name: run.title })
      .closest("article")!;
    expect(within(card).getByText("None")).toBeInTheDocument();
    expect(
      within(card).getByText("Last candidate · reverted"),
    ).toBeInTheDocument();
    expect(
      within(card).getByText(/not the result of a retained repair/),
    ).toBeInTheDocument();
  }
});
it("preserves tolerance and unknown pairing for s2 and only five compared samples for s4", async () => {
  mockCatalog();
  render(<VerifiedPage enabled />);
  const s2 = prepared.runs.find(
    (item: { scenario_id: string }) => item.scenario_id === "s2_capacity_v2",
  );
  const s4 = prepared.runs.find(
    (item: { scenario_id: string }) =>
      item.scenario_id === "s4_loss_accumulation_graph",
  );
  const two = (await screen.findByRole("heading", { name: s2.title })).closest(
    "article",
  )!;
  const twoTable = within(two).getByRole("table", {
    name: "Recorded verification",
  });
  expect(within(twoTable).getByText("Within tolerance")).toBeInTheDocument();
  expect(within(twoTable).queryByText("Identical")).not.toBeInTheDocument();
  for (const label of ["Same inputs", "Same effective batch", "Same objective"])
    expect(within(twoTable).getByText(label).closest("tr")).toHaveTextContent(
      "Unknown",
    );
  const four = screen
    .getByRole("heading", { name: s4.title })
    .closest("article")!;
  expect(
    within(four).getByText("Loss samples compared").closest("tr"),
  ).toHaveTextContent("5");
  expect(
    within(four).getByText("Optimizer updates completed").closest("tr"),
  ).toHaveTextContent("20");
  expect(
    within(four).getByText(/not all 20 candidate updates/),
  ).toBeInTheDocument();
});
it("opens only the initial diagnosis bound stack and distinguishes live peak from cumulative allocation", async () => {
  const document = published(),
    run = document.runs[0];
  const reference = run.diagnosis.root_causes[0].evidence_refs[0];
  const stack = run.stacks.find(
    (item: { id: string }) => item.id === reference,
  );
  stack.peak_live_bytes = null;
  stack.lifetime_allocated_bytes = 123456;
  mockCatalog(document);
  render(<VerifiedPage enabled />);
  const card = (
    await screen.findByRole("heading", { name: run.title })
  ).closest("article")!;
  fireEvent.click(within(card).getAllByRole("button", { name: reference })[0]);
  expect(
    within(card).getByText("Live bytes at recorded peak: Unknown"),
  ).toBeInTheDocument();
  expect(
    within(card).getByText(
      "Total bytes allocated over the capture: 123,456 bytes",
    ),
  ).toBeInTheDocument();
  expect(
    within(card).getByText("Initial diagnosis · baseline capture"),
  ).toBeInTheDocument();
  expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
});
it("does not infer downloadable URLs or trust an unbound diagnosis", async () => {
  const document = published(),
    run = document.runs[0];
  const reference = run.diagnosis.root_causes[0].evidence_refs[0];
  run.diagnosis_binding.round = 2;
  for (const asset of Object.values(run.downloads))
    delete (asset as { url?: string }).url;
  mockCatalog(document);
  render(<VerifiedPage enabled />);
  const card = (
    await screen.findByRole("heading", { name: run.title })
  ).closest("article")!;
  expect(
    within(card).queryByRole("button", { name: reference }),
  ).not.toBeInTheDocument();
  expect(
    within(card).queryByRole("link", { name: /Download/ }),
  ).not.toBeInTheDocument();
  expect(
    within(card).getByText(/capture could not be verified/),
  ).toBeInTheDocument();
});
it("rejects a prepared catalog even when the client was told the gallery is enabled", async () => {
  mockCatalog(structuredClone(prepared));
  render(<VerifiedPage enabled />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Verified runs are not open yet",
  );
  expect(screen.queryByText("Recorded repair")).not.toBeInTheDocument();
});

it("explains a failed verification and preserves an unfamiliar reason in readable form", async () => {
  const document = published();
  const failed = document.runs.filter(
    (run: { outcome: string }) => run.outcome !== "target_met",
  );
  failed[0].last_attempt.reason = "verification_hard_constraints_unmet";
  failed[1].last_attempt.reason = "candidate_optimizer_state_mismatch";
  mockCatalog(document);
  render(<VerifiedPage enabled />);
  expect(
    await screen.findByText(
      "The candidate did not pass the required verification.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Candidate optimizer state mismatch"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("verification_hard_constraints_unmet"),
  ).not.toBeInTheDocument();
});
