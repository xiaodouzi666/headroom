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
