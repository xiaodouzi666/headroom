import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

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
    const view = render(<App />);
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
    const view = render(<App />);
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
  render(<App />);
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

describe("estimated admission disclosure", () => {
  it.each([true, false])(
    "keeps reported cost independent of reservations (known=%s)",
    async (known) => {
      window.history.replaceState({}, "", `/runs/${id}`);
      const reportPath = detailPath + "/report.json";
      const usage = {
        calls: 1,
        admission_counts: {
          verified_provider_bound: 0,
          local_estimate: 1,
          unknown: 0,
        },
        reservation_usd: "0.3456",
        total_cost_usd: known ? "0.0213" : null,
        known_cost_usd: known ? "0.0213" : "0",
        unknown_cost_calls: known ? 0 : 1,
        complete: known,
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
                  usage,
                  artifacts: { "report.json": reportPath },
                }),
              ),
            );
          if (input === reportPath)
            return Promise.resolve(
              new Response(JSON.stringify({ usage, rounds: [] })),
            );
          return Promise.reject(new Error("Unexpected offline request"));
        }),
      );
      vi.stubGlobal("EventSource", OfflineEvents);
      render(<App />);
      const total = await screen.findByText("Total recorded cost");
      expect(total.parentElement).toHaveTextContent(
        known ? "$0.0213" : "Unknown",
      );
      expect(await screen.findByRole("note")).toHaveTextContent(
        "1 call used local estimates",
      );
      expect(screen.getByRole("note")).toHaveTextContent(
        "a call can exceed its estimate",
      );
      expect(screen.queryByText("$0.3456")).not.toBeInTheDocument();
      if (!known)
        expect(screen.getByText(/unresolved charge/)).toBeInTheDocument();
    },
  );
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
  render(<App />);
  await screen.findByText("Explore more configurations");
  const target = screen.getByText("Selected configuration meets target");
  expect(target.nextElementSibling).toHaveTextContent("Yes");
  expect(
    screen.getByText("First verified target round").nextElementSibling,
  ).toHaveTextContent("1");
  expect(
    screen.getByText("Exploration status").nextElementSibling,
  ).toHaveTextContent("budget exceeded");
  expect(
    screen.getByText("Stopped because").nextElementSibling,
  ).toHaveTextContent("budget exceeded");
  expect(screen.getByRole("link", { name: "patch.diff" })).toHaveAttribute(
    "href",
    detailPath + "/patch.diff",
  );
});

it("does not present historical baseline completion as successful exploration", async () => {
  window.history.replaceState({}, "", `/runs/${id}?replay=1`);
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
  render(<App />);
  await screen.findByText("Search outcome");
  expect(
    screen.getByText("Exploration status").nextElementSibling,
  ).toHaveTextContent("Not recorded");
  expect(
    screen.getByText("Selected configuration meets target").nextElementSibling,
  ).toHaveTextContent("N/A — baseline only");
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
  const view = render(<App />);
  await screen.findByText("Reproduce the selected configuration");
  for (const name of ["cli.json", "configuration.json"])
    expect(await screen.findByRole("link", { name })).toHaveAttribute(
      "href",
      detailPath + "/" + name,
    );
  expect(screen.getByRole("link", { name: "manifest" })).toHaveAttribute(
    "href",
    detailPath + "/configurations/round-01/manifest.json",
  );
  const preview = view.container.querySelector("pre.code-block");
  expect(preview).toHaveTextContent("--batch=8");
  expect(preview).toHaveTextContent("--batch=1");
  expect(preview).toHaveTextContent(injected);
  expect(view.container.querySelector("script")).toBeNull();
  expect(view.container.querySelector('img[src="x"]')).toBeNull();
  expect(
    screen.getByText(/An empty diff can represent a CLI-only/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/An ordinary shell does not apply it/),
  ).toBeInTheDocument();
  expect(
    mocked.mock.calls.every(([url]) =>
      [detailPath, reportPath, detailPath + "/patch.diff"].includes(
        String(url),
      ),
    ),
  ).toBe(true);
});
