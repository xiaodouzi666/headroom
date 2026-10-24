import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import DiffView from "./DiffView";
import { Status } from "./components";
const response = (body: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
beforeEach(() => {
  window.history.replaceState({}, "", "/");
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      if (input === "/api/health")
        return response({
          token_factory: { configured: false },
          queue: { pending: 0, capacity: 3 },
        });
      if (input === "/api/examples")
        return response({
          examples: [
            {
              id: "s1_batch_too_big",
              title: "Activation memory",
              root_cause: "Retained activations",
              expected_mode: "oom",
              baseline_verified: true,
            },
          ],
        });
      if (input === "/api/replays") return response({ replays: [] });
      return Promise.reject(new Error("Unexpected request in offline UI test"));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("workspace state", () => {
  it("shows real API examples and the missing-model-access state", async () => {
    render(<App />);
    expect(
      await screen.findByRole("button", { name: /Activation memory/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Model access needs setup.")).toBeInTheDocument();
    expect(
      screen.queryByText(/verified repair succeeded/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/No curated replays are available yet/),
    ).toBeInTheDocument();
  });
  it("validates source selection before submitting", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Activation memory/ });
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose an example",
    );
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
    ).toBe(false);
  });
  it("keeps server failure visible without inventing an empty success state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("API unavailable"))),
    );
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "API unavailable",
    );
    await waitFor(() =>
      expect(screen.getByText("No examples available")).toBeInTheDocument(),
    );
  });
  it("exposes script entry and the actual request policy controls", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Activation memory/ });
    fireEvent.click(screen.getByRole("button", { name: "Paste a script" }));
    expect(screen.getByLabelText("Python training script")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Allow precision changes/ }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Allow batch/ })).toBeChecked();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
  });
});
describe("safe evidence rendering", () => {
  it("renders patch HTML as text rather than executable markup", () => {
    const diff =
      '--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-x=1\n+x="<img src=x onerror=alert(1)>"\n';
    const { container } = render(<DiffView diff={diff} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
  it("renders needs_human as a visible state", () => {
    render(<Status value="needs_human" />);
    expect(screen.getByText("needs human")).toBeInTheDocument();
  });
});
