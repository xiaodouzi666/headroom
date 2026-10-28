import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { RunPage } from "./RunPage";

const id = "a".repeat(32);
const detailPath = `/api/runs/${id}`;
class OfflineEvents {
  static instances: OfflineEvents[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, ((message: MessageEvent) => void)[]>();
  closed = false;
  constructor(public url: string) {
    OfflineEvents.instances.push(this);
  }
  addEventListener(kind: string, listener: (message: MessageEvent) => void) {
    this.listeners.set(kind, [...(this.listeners.get(kind) ?? []), listener]);
  }
  emit(kind: string, data: unknown) {
    for (const listener of this.listeners.get(kind) ?? [])
      listener(new MessageEvent(kind, { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}
function setup() {
  let ended = false;
  const mocked = vi.fn((input: unknown) => {
    if (input === detailPath)
      return Promise.resolve(
        new Response(
          JSON.stringify({
            run_id: id,
            target: "fix-oom",
            status: ended ? "needs_human" : "running",
            reason: ended ? "Verified provider profile unavailable" : null,
            provenance: "offline_fixture",
            artifacts: {},
            usage: {
              calls: 1,
              unknown_cost_calls: 1,
              total_cost_usd: null,
              known_cost_usd: "0",
              complete: false,
            },
          }),
          { status: 200 },
        ),
      );
    return Promise.reject(new Error("Unexpected request in offline run test"));
  });
  window.history.replaceState({}, "", `/runs/${id}`);
  vi.stubGlobal("fetch", mocked);
  OfflineEvents.instances = [];
  vi.stubGlobal("EventSource", OfflineEvents);
  return {
    mocked,
    end: () => {
      ended = true;
    },
  };
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.history.replaceState({}, "", "/");
});
describe("run event lifecycle", () => {
  it("deduplicates events, shows actual call metadata, and closes at needs_human", async () => {
    const test = setup();
    const view = render(<RunPage runId={id} />);
    await waitFor(() => expect(OfflineEvents.instances).toHaveLength(1));
    const source = OfflineEvents.instances[0];
    expect(source.url).toBe(`${detailPath}/events`);
    act(() => source.onopen?.());
    const event = {
      sequence: 2,
      kind: "diagnose.done",
      data: {
        model: "nvidia/actual-model",
        elapsed_seconds: 1.25,
        cost_usd: "0.0123",
      },
    };
    act(() => {
      source.emit("diagnose.done", event);
      source.emit("diagnose.done", event);
      source.emit("run.started", {
        sequence: 1,
        kind: "run.started",
        data: {},
      });
    });
    expect(screen.getAllByText("diagnose · done")).toHaveLength(1);
    expect(screen.getByText("actual-model")).toBeInTheDocument();
    expect(screen.getByText("1.25s")).toBeInTheDocument();
    expect(screen.getByText("Cost $0.0123")).toBeInTheDocument();
    expect(screen.getAllByText(/Offline fixture/).length).toBeGreaterThan(0);
    expect(screen.getByText("No after measurement yet")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    test.end();
    act(() =>
      source.emit("stream.end", {
        status: "needs_human",
        cleanup_verified: true,
      }),
    );
    expect(source.closed).toBe(true);
    expect(
      await screen.findByText("This run needs attention."),
    ).toBeInTheDocument();
    expect(screen.getByText("Event history complete")).toBeInTheDocument();
    const atEnd = test.mocked.mock.calls.length;
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(test.mocked.mock.calls.length).toBe(atEnd);
    view.unmount();
    expect(source.closed).toBe(true);
  });
  it("keeps reconnection visible and releases the stream on navigation", async () => {
    setup();
    const view = render(<RunPage runId={id} />);
    await waitFor(() => expect(OfflineEvents.instances).toHaveLength(1));
    const source = OfflineEvents.instances[0];
    act(() => source.onerror?.());
    expect(screen.getByText("Reconnecting")).toBeInTheDocument();
    view.unmount();
    expect(source.closed).toBe(true);
  });
});

it("renders per-round verification and only downloads complete retained or reverted diffs", async () => {
  window.history.replaceState({}, "", `/runs/${id}`);
  const patch = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-x=1\n+x=2\n";
  const reportPath = detailPath + "/report.json";
  const displayed = {
    peak_before: "10.000 GB",
    peak_after: "8.000 GB",
    reduction_pct: "20.000%",
    step_ms_before: "100.000 ms",
    step_ms_after: "110.000 ms",
    throughput_regression_pct: "10.000%",
    loss_equivalence: "changed",
    numerical_basis: "Observed full backward-loss sequence (original plan)",
    max_loss_delta: "0.500000",
    target_met: false,
    completed: true,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      if (input === detailPath)
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: id,
              status: "needs_human",
              provenance: "offline_fixture",
              usage: {},
              artifacts: { "report.json": reportPath },
            }),
          ),
        );
      if (input === reportPath)
        return Promise.resolve(
          new Response(
            JSON.stringify({
              rounds: [
                {
                  number: 1,
                  decision: "revert",
                  reason: "loss changed",
                  provenance: "offline_fixture",
                  diff_status: "available",
                  diff: patch,
                  diff_summary: "1 file, 1 insertion, 1 deletion",
                  display_verification: displayed,
                  verification: {
                    checks: { loss_tolerance: false },
                    notes: ["Reference differs."],
                  },
                },
                {
                  number: 2,
                  decision: "revert",
                  reason: "patch missing",
                  diff_status: "unavailable",
                  verification: {},
                },
              ],
            }),
          ),
        );
      return Promise.reject(new Error("Unexpected request"));
    }),
  );
  vi.stubGlobal("EventSource", OfflineEvents);
  const nativeURL = URL;
  const create = vi.fn((_blob: Blob) => "blob:offline"),
    revoke = vi.fn();
  vi.stubGlobal(
    "URL",
    Object.assign(class extends nativeURL {}, {
      createObjectURL: create,
      revokeObjectURL: revoke,
    }),
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  render(<RunPage runId={id} />);
  const table = await screen.findByRole("table", {
    name: "Round 1 verification",
  });
  expect(table).toHaveTextContent("20.000%");
  expect(table).toHaveTextContent("changed");
  expect(table).toHaveTextContent("Not passed");
  expect(screen.getByText("Reference differs.")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Download round 2 patch" }),
  ).not.toBeInTheDocument();
  vi.useFakeTimers();
  screen.getByRole("button", { name: "Download round 1 patch" }).click();
  expect(create).toHaveBeenCalledTimes(1);
  expect(create.mock.calls[0][0]).toHaveProperty("size", patch.length);
  expect(click).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1000);
  expect(revoke).toHaveBeenCalledWith("blob:offline");
  click.mockRestore();
});

describe("confirmed run cost", () => {
  it.each([true, false])(
    "shows one actual total, or unavailable (known=%s)",
    async (known) => {
      const usage = {
        calls: 1,
        admission_counts: { local_estimate: 1 },
        reservation_usd: "0.3456",
        total_cost_usd: known ? "0.0213" : null,
        known_cost_usd: known ? "0.0213" : "0",
        unknown_cost_calls: known ? 0 : 1,
        complete: known,
      };
      mountRun({ usage });
      const line = await screen.findByText(/Token Factory cost of this run:/);
      expect(line).toHaveTextContent(known ? "$0.0213" : "unavailable");
      expect(
        screen.getAllByText(/Token Factory cost of this run:/),
      ).toHaveLength(1);
      expect(screen.queryByText("$0.3456")).not.toBeInTheDocument();
      expect(screen.queryByText("Model usage")).not.toBeInTheDocument();
      expect(
        screen.queryByText(/known subtotal|local estimates|unresolved charge/i),
      ).not.toBeInTheDocument();
    },
  );
  it.each([
    { complete: false, total_cost_usd: "0" },
    { complete: true, unknown_cost_calls: 1, total_cost_usd: "0" },
    { complete: true, unknown_cost_calls: "1", total_cost_usd: "0" },
    { total_cost_usd: "0.1" },
    { complete: true, total_cost_usd: "-0.1" },
    { complete: true, total_cost_usd: "NaN" },
  ])(
    "never turns incomplete or invalid usage into a price: %j",
    async (usage) => {
      mountRun({ usage });
      expect(
        await screen.findByText(/Token Factory cost of this run:/),
      ).toHaveTextContent("unavailable");
    },
  );
  it("keeps an explicitly confirmed zero as zero", async () => {
    mountRun({
      usage: { complete: true, unknown_cost_calls: 0, total_cost_usd: "0" },
    });
    expect(
      await screen.findByText(/Token Factory cost of this run:/),
    ).toHaveTextContent("$0.0000");
  });
});

it("shows a retained target success separately from exhausted exploration", async () => {
  window.history.replaceState({}, "", `/runs/${id}`);
  const reportPath = detailPath + "/report.json";
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      const value =
        input === detailPath
          ? {
              run_id: id,
              status: "budget_exceeded",
              target: "fit:22GB",
              artifacts: {
                "report.json": reportPath,
                "patch.diff": detailPath + "/patch.diff",
              },
              usage: {},
            }
          : input === reportPath
            ? {
                summary: { target_met: true },
                search: {
                  mode: "bounded_pareto",
                  stop_reason: "budget_exceeded",
                  rounds_executed: 3,
                  first_target_met_round: 1,
                },
              }
            : null;
      if (input === detailPath + "/patch.diff")
        return Promise.resolve(new Response("retained patch"));
      if (value) return Promise.resolve(new Response(JSON.stringify(value)));
      return Promise.reject(new Error("Unexpected request"));
    }),
  );
  vi.stubGlobal("EventSource", OfflineEvents);
  render(<RunPage runId={id} />);
  await screen.findByText(/The selected repair meets the target/);
  expect(screen.getByText("Stopped")).toBeInTheDocument();
  expect(
    screen.getByText(/The run reached its model-usage limit/),
  ).toBeInTheDocument();
  expect(screen.getByText("Yes — verifier reported")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "patch.diff" })).toHaveAttribute(
    "href",
    detailPath + "/patch.diff",
  );
});

it("does not present historical baseline completion as successful exploration", async () => {
  window.history.replaceState({}, "", `/runs/${id}`);
  const reportPath = detailPath + "/report.json";
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      if (input === detailPath)
        return Promise.resolve(
          new Response(
            JSON.stringify({
              run_id: id,
              status: "completed",
              provenance: "recorded_baseline",
              usage: {},
              artifacts: { "report.json": reportPath },
            }),
          ),
        );
      if (input === reportPath)
        return Promise.resolve(
          new Response(
            JSON.stringify({
              summary: { target_met: false },
              rounds: [],
            }),
          ),
        );
      return Promise.reject(new Error("Unexpected request"));
    }),
  );
  vi.stubGlobal("EventSource", OfflineEvents);
  render(<RunPage runId={id} />);
  await screen.findByText(/Recorded GPU baseline/);
  expect(await screen.findByText("N/A — baseline only")).toBeInTheDocument();
  expect(
    screen.queryByText(/The selected repair meets the target/),
  ).not.toBeInTheDocument();
});

it("hands off CLI-only wrapper repairs with safe selected arguments and complete downloads", async () => {
  window.history.replaceState({}, "", "/runs/" + id);
  const reportPath = detailPath + "/report.json";
  const injected =
    "</pre><script>alert(1)</script><img src=x onerror=alert(1)>";
  const artifacts = Object.fromEntries(
    [
      "report.json",
      "patch.diff",
      "env.sh",
      "cli.json",
      "configuration.json",
    ].map((name) => [name, detailPath + "/" + name]),
  );
  const selected = {
    round: 1,
    original: {
      execution_argv: ["/bin/sh", "launch.sh", injected],
      script_args: ["--batch=8"],
    },
    effective: {
      execution_argv: ["/bin/sh", "launch.sh", injected],
      script_args: ["--batch=1"],
    },
    wrapper_replay: { kind: "captured_wrapper", source_relative: "train.py" },
  };
  const mocked = vi.fn((input: unknown) => {
    if (input === detailPath)
      return Promise.resolve(
        new Response(
          JSON.stringify({
            run_id: id,
            status: "budget_exceeded",
            artifacts,
            usage: {},
          }),
        ),
      );
    if (input === reportPath)
      return Promise.resolve(
        new Response(
          JSON.stringify({
            selected_configuration: selected,
            pareto: {
              frontier: [
                {
                  round: 1,
                  artifacts: {
                    manifest: "configurations/round-01/manifest.json",
                  },
                },
              ],
            },
          }),
        ),
      );
    if (input === detailPath + "/patch.diff")
      return Promise.resolve(new Response(""));
    return Promise.reject(new Error("Unexpected offline request"));
  });
  vi.stubGlobal("fetch", mocked);
  vi.stubGlobal("EventSource", OfflineEvents);
  const view = render(<RunPage runId={id} />);
  await screen.findByText("Use this repair");
  for (const name of ["cli.json", "configuration.json"])
    expect(await screen.findByRole("link", { name })).toHaveAttribute(
      "href",
      detailPath + "/" + name,
    );
  expect(screen.getByRole("link", { name: "manifest" })).toHaveAttribute(
    "href",
    detailPath + "/configurations/round-01/manifest.json",
  );
  expect(view.container.querySelector("pre.code-block")).toBeNull();
  expect(view.container.textContent).not.toContain(injected);
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector('img[src="x"]')).toBeNull();
  expect(
    screen.getByText(/Some repairs change these settings/),
  ).toBeInTheDocument();
  expect(screen.getByText(/This run used a launcher/)).toBeInTheDocument();
  expect(
    mocked.mock.calls.every(([url]) =>
      [detailPath, reportPath, detailPath + "/patch.diff"].includes(
        String(url),
      ),
    ),
  ).toBe(true);
});

it("shows a bound Nano opinion separately from the unchanged heuristic category", async () => {
  const reportPath = detailPath + "/report.json";
  const report = {
    run: {
      annotations: {
        status: "completed",
        evidence_fingerprint: "a".repeat(64),
        annotations: [{ stack_id: "stk_a", label: "Stale unbound label" }],
      },
    },
    peak_composition: [{ category: "activations", bytes: 100, gb: "0.000 GB" }],
    evidence: {
      before: {
        analysis: {
          category_bytes: { activations: 100 },
          peak_composition: [
            {
              stack_id: "stk_a",
              category: "activations",
              bytes: 100,
              frames: [],
              model_annotation: {
                kind: "model_interpretation",
                is_measurement: false,
                category: "optimizer_state",
                label: "Bound Nano hypothesis",
                provenance: "offline_fixture",
              },
            },
          ],
        },
      },
    },
  };
  window.history.replaceState({}, "", `/runs/${id}`);
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            input === detailPath
              ? {
                  run_id: id,
                  status: "completed",
                  target: "reclaim",
                  provenance: "offline_fixture",
                  artifacts: { "report.json": reportPath },
                  usage: {},
                }
              : input === reportPath
                ? report
                : {},
          ),
          { status: 200 },
        ),
      ),
    ),
  );
  OfflineEvents.instances = [];
  vi.stubGlobal("EventSource", OfflineEvents);
  render(<RunPage runId={id} />);
  expect(await screen.findByText(/Bound Nano hypothesis/)).toBeInTheDocument();
  expect(
    screen.getByText(/Model category: optimizer state/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Separate from the heuristic category and measured bytes/),
  ).toBeInTheDocument();
  expect(screen.getByText("activations")).toBeInTheDocument();
  expect(screen.queryByText("Stale unbound label")).not.toBeInTheDocument();
});

function mountRun(
  run: Record<string, unknown> = {},
  report: Record<string, unknown> = {},
) {
  const reportPath = detailPath + "/report.json";
  const mocked = vi.fn((input: unknown) => {
    if (input === detailPath)
      return Promise.resolve(
        new Response(
          JSON.stringify({
            run_id: id,
            status: "completed",
            artifacts: { "report.json": reportPath },
            ...run,
          }),
        ),
      );
    if (input === reportPath)
      return Promise.resolve(new Response(JSON.stringify(report)));
    return Promise.reject(
      new Error("Unexpected request in offline Run fixture"),
    );
  });
  vi.stubGlobal("fetch", mocked);
  OfflineEvents.instances = [];
  vi.stubGlobal("EventSource", OfflineEvents);
  return { ...render(<RunPage runId={id} />), mocked };
}
it("does not reuse baseline stack IDs as unbound diagnosis evidence", async () => {
  const report = {
    diagnosis: {
      root_causes: [
        { title: "Retained activations", evidence_refs: ["stk_shared"] },
      ],
    },
    evidence: {
      before: {
        analysis: {
          peak_composition: [
            {
              stack_id: "stk_shared",
              bytes: 500,
              frames: [{ filename: "baseline.py", line: 5, name: "old_step" }],
            },
          ],
        },
      },
    },
  };
  mountRun({}, report);
  const reference = await screen.findByRole("button", { name: "stk_shared" });
  act(() => reference.click());
  const panel = reference.closest(".stack-reference")!;
  expect(
    within(panel as HTMLElement).getByText(/Stack details unavailable/),
  ).toBeInTheDocument();
  expect(panel).not.toHaveTextContent("500 bytes");
  expect(panel).not.toHaveTextContent("baseline.py");
});
it("renders actual failure and missing metrics in plain language without debug views", async () => {
  mountRun(
    { status: "needs_human", reason: "loss_tolerance_gate_failed" },
    {
      summary: { target_met: false, loss_equivalence: "changed" },
      verification: { checks: { loss_tolerance: false } },
      warnings: [
        "The provider ledger has an unknown charge; halt at reservation gate.",
      ],
      selected_configuration: { private_debug: "do not preview this object" },
    },
  );
  await screen.findByText("loss tolerance check failed");
  expect(screen.getByText("changed")).toBeInTheDocument();
  expect(screen.getByText("Not passed")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Limitations" }),
  ).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(
    /ledger|unknown charge|\bhalt\b|\bgate\b|reservation|withdrawn|acceptance/i,
  );
  expect(document.body.textContent).not.toContain("do not preview this object");
});
it("never substitutes a nested zero for an explicitly unavailable event cost", async () => {
  mountRun();
  await waitFor(() => expect(OfflineEvents.instances).toHaveLength(1));
  act(() =>
    OfflineEvents.instances[0].emit("diagnose.done", {
      sequence: 1,
      kind: "diagnose.done",
      data: {
        model: "nvidia/actual-model",
        elapsed_seconds: 2,
        cost_usd: null,
        cost: { usd: 0 },
      },
    }),
  );
  expect(screen.getByText("Cost unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Cost $0.0000")).not.toBeInTheDocument();
});

it("does not round a confirmed positive run or event cost to zero", async () => {
  mountRun({
    usage: {
      complete: true,
      unknown_cost_calls: 0,
      total_cost_usd: "0.000001",
    },
  });
  expect(
    await screen.findByText(/Token Factory cost of this run:/),
  ).toHaveTextContent("<$0.0001");
  await waitFor(() => expect(OfflineEvents.instances).toHaveLength(1));
  act(() =>
    OfflineEvents.instances[0].emit("diagnose.done", {
      sequence: 1,
      kind: "diagnose.done",
      data: { cost_usd: "0.000001" },
    }),
  );
  expect(screen.getByText("Cost <$0.0001")).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("$0.0000");
});

const citedStack = "stk_1234567890abcdef";
function initialEvidence() {
  return {
    diagnosis: {
      root_causes: [
        {
          title: "Original captured activations",
          category: "activations",
          confidence: 0.9,
          evidence_refs: [citedStack],
        },
      ],
      needs_more_info: false,
      notes: [] as string[],
    },
    diagnosis_binding: {
      round: 1,
      stage: "baseline",
      evidence_json_sha256: "a".repeat(64),
      evidence_markdown_sha256: "b".repeat(64),
      diagnosis_sha256: "c".repeat(64),
      request_payload_sha256: "d".repeat(64),
      request_wire_sha256: "e".repeat(64),
    },
    stacks: [
      {
        id: citedStack,
        peak_live_bytes: 100,
        lifetime_allocated_bytes: 900,
        frames: [
          { filename: "/source/train.py", line: 42, name: "evaluate" },
          { filename: "/runtime/native.cpp", line: 10, name: "allocate" },
        ],
      },
    ],
  };
}
it("opens the initial diagnosis capture and separates peak from lifetime bytes without extra queries", async () => {
  const { mocked } = mountRun(
    { diagnosis_evidence: initialEvidence() },
    {
      diagnosis: {
        root_causes: [
          { title: "Later diagnosis", evidence_refs: [citedStack] },
        ],
      },
      evidence: {
        before: {
          analysis: {
            peak_composition: [
              {
                stack_id: citedStack,
                bytes: 500,
                frames: [{ filename: "different.py", line: 8, name: "other" }],
              },
            ],
          },
        },
      },
    },
  );
  await screen.findByRole("heading", { name: "Initial diagnosis" });
  expect(screen.getByText("Original captured activations")).toBeInTheDocument();
  expect(screen.queryByText("Later diagnosis")).not.toBeInTheDocument();
  const before = mocked.mock.calls.length;
  const button = screen.getByRole("button", { name: citedStack });
  act(() => button.click());
  const panel = button.closest(".stack-reference") as HTMLElement;
  expect(
    within(panel).getByText("Live at peak").nextElementSibling,
  ).toHaveTextContent("100 bytes");
  expect(
    within(panel).getByText("Allocated during capture").nextElementSibling,
  ).toHaveTextContent("900 bytes");
  expect(panel).toHaveTextContent("/source/train.py:42 in evaluate");
  expect(panel).not.toHaveTextContent("different.py");
  expect(
    within(panel).getByText("Full call stack (2 frames)"),
  ).toBeInTheDocument();
  expect(mocked.mock.calls.length).toBe(before);
});
it.each([
  "missing_digest",
  "wrong_round",
  "different_stage",
  "duplicate_stack",
  "unresolved_ref",
])(
  "does not connect stacks from an incomplete diagnosis envelope: %s",
  async (problem) => {
    const envelope = structuredClone(initialEvidence()) as unknown as Record<
      string,
      unknown
    >;
    const binding = envelope.diagnosis_binding as Record<string, unknown>;
    const stacks = envelope.stacks as Record<string, unknown>[];
    const diagnosis = envelope.diagnosis as {
      root_causes: { evidence_refs: string[] }[];
    };
    if (problem === "missing_digest") delete binding.request_wire_sha256;
    if (problem === "wrong_round") binding.round = 2;
    if (problem === "different_stage") binding.stage = "candidate";
    if (problem === "duplicate_stack") stacks.push(stacks[0]);
    if (problem === "unresolved_ref")
      diagnosis.root_causes[0].evidence_refs = ["stk_ffffffffffffffff"];
    mountRun(
      { diagnosis_evidence: envelope },
      {
        diagnosis: {
          root_causes: [
            { title: "Recorded latest diagnosis", evidence_refs: [citedStack] },
          ],
        },
      },
    );
    await screen.findByRole("heading", { name: "The diagnosis" });
    expect(screen.getByText("Recorded latest diagnosis")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: citedStack });
    act(() => button.click());
    expect(
      within(button.closest(".stack-reference") as HTMLElement).getByText(
        /Stack details unavailable/,
      ),
    ).toBeInTheDocument();
  },
);
it("preserves a model request for more information instead of implying it is still loading", async () => {
  const envelope = initialEvidence();
  envelope.diagnosis.root_causes = [];
  envelope.diagnosis.needs_more_info = true;
  envelope.diagnosis.notes = ["The optimizer configuration is needed."];
  envelope.stacks = [];
  mountRun({ status: "needs_human", diagnosis_evidence: envelope });
  expect(
    await screen.findByText("More information needed"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("The optimizer configuration is needed."),
  ).toBeInTheDocument();
  expect(screen.queryByText("No diagnosis yet")).not.toBeInTheDocument();
});
it("escapes source frames while preserving their exact text", async () => {
  const envelope = initialEvidence();
  envelope.stacks[0].frames = [
    {
      filename: "/source/<img src=x onerror=alert(1)>.py",
      line: 1,
      name: "<script>alert(1)</script>",
    },
  ];
  const view = mountRun({ diagnosis_evidence: envelope });
  const button = await screen.findByRole("button", { name: citedStack });
  act(() => button.click());
  expect(button.closest(".stack-reference")).toHaveTextContent(
    "/source/<img src=x onerror=alert(1)>.py:1",
  );
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector('img[src="x"]')).toBeNull();
});
