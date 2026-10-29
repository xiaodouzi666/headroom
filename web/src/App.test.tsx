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
  window.history.replaceState({}, "", "/run");
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      if (input === "/api/config")
        return response({
          public_demo: false,
          verified_runs_enabled: false,
          judge_scripts_available: false,
          run_submissions: { enabled: true },
        });
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
    expect(
      screen.getByText("Live analysis is not enabled yet."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/verified repair succeeded/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Saved replay|Explore saved runs/),
    ).not.toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/replays"),
    ).toBe(false);
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
      "Service availability could not be loaded",
    );
    expect(
      screen.queryByRole("button", { name: /Start analysis/ }),
    ).not.toBeInTheDocument();
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
describe("paused public workspace", () => {
  it("explains the pause, links to evaluations, and rejects form submission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: unknown) => {
        if (input === "/api/config")
          return response({
            public_demo: true,
            verified_runs_enabled: false,
            judge_scripts_available: false,
            run_submissions: { enabled: true },
          });
        if (input === "/api/health")
          return response({
            run_submissions: {
              enabled: false,
              reason: "Model budget is currently unavailable.",
            },
          });
        if (input === "/api/examples") return response({ examples: [] });
        return Promise.reject(new Error("Paused UI must not submit work"));
      }),
    );
    const { container } = render(<App />);
    expect(
      await screen.findByText("Live analysis temporarily paused."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Model budget is currently unavailable/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Paste a script" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Run budget in USD"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /browse published evaluation results/ }),
    ).toHaveAttribute("href", "/results");
    expect(
      screen.getByRole("button", { name: /Start analysis/ }),
    ).toBeDisabled();
    fireEvent.submit(container.querySelector("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Live analysis temporarily paused.",
    );
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
    ).toBe(false);
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/replays"),
    ).toBe(false);
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

describe("availability guidance", () => {
  it.each([
    [{ gpu: { status: "busy", busy: true, stale: false } }, "The GPU is busy."],
    [
      {
        local_budget: {
          scope: "local_application_authorization",
          status: "pending_charge",
        },
      },
      "Live analysis temporarily paused.",
    ],
    [
      {
        local_budget: {
          scope: "local_application_authorization",
          status: "exhausted",
        },
      },
      "Live analysis temporarily paused.",
    ],
    [
      {
        local_budget: {
          scope: "local_application_authorization",
          status: "billing_review_required",
        },
      },
      "Live analysis temporarily paused.",
    ],
  ])(
    "explains the blocker and prevents a blocked start",
    async (observed, message) => {
      vi.stubGlobal(
        "fetch",
        vi.fn((input: unknown) => {
          if (input === "/api/config")
            return response({
              public_demo: false,
              verified_runs_enabled: false,
              judge_scripts_available: false,
              run_submissions: { enabled: true },
            });
          if (input === "/api/health")
            return response({
              ...observed,
              token_factory: { configured: true },
              queue: {},
            });
          if (input === "/api/examples") return response({ examples: [] });
          return Promise.reject(new Error("Unexpected request"));
        }),
      );
      render(<App />);
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: /Explore saved evidence/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Start analysis/ }),
      ).toBeDisabled();
      expect(
        screen.queryByText(/verified repair succeeded/i),
      ).not.toBeInTheDocument();
    },
  );
  it("keeps automatic availability guidance without a replay endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: unknown) => {
        if (input === "/api/config")
          return response({
            public_demo: false,
            verified_runs_enabled: false,
            judge_scripts_available: false,
            run_submissions: { enabled: true },
          });
        if (input === "/api/health")
          return response({ gpu: { status: "busy", busy: true } });
        if (input === "/api/examples") return response({ examples: [] });
        return Promise.reject(new Error("Unexpected request"));
      }),
    );
    render(<App />);
    expect(await screen.findByText("The GPU is busy.")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Explore saved evidence/ }),
    ).not.toBeInTheDocument();
  });
});

it.each(["until_target", "bounded_pareto"])(
  "submits explicit search mode %s without expanding precision policy",
  async (mode) => {
    const existing = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((input, init) =>
      input === "/api/runs"
        ? Promise.resolve(
            new Response(
              JSON.stringify({ detail: "Offline submission captured" }),
              { status: 400 },
            ),
          )
        : existing(input, init),
    );
    render(<App />);
    const example = await screen.findByRole("button", {
      name: /Activation memory/,
    });
    fireEvent.click(example);
    const select = screen.getByRole("combobox", { name: "Search mode" });
    expect(select).toHaveValue("until_target");
    fireEvent.change(select, { target: { value: mode } });
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    await screen.findByText(
      "The request could not be processed. Check the supplied inputs.",
    );
    const posted = vi
      .mocked(fetch)
      .mock.calls.find(([path]) => path === "/api/runs")!;
    const body = JSON.parse(String(posted[1]?.body));
    expect(body.search_mode).toBe(mode);
    expect(body.policy.allow_numerics_change).toBe(false);
    expect(body.budget).toBe("0.60");
  },
);

it("distinguishes an explicitly empty patch from missing patch evidence", () => {
  const view = render(<DiffView diff="" recorded />);
  expect(
    screen.getByText("No source changes in this patch"),
  ).toBeInTheDocument();
  expect(screen.queryByText("No patch produced")).not.toBeInTheDocument();
  view.rerender(<DiffView diff="" />);
  expect(screen.getByText("No patch produced")).toBeInTheDocument();
  expect(
    screen.queryByText("No source changes in this patch"),
  ).not.toBeInTheDocument();
});

describe("example target presets", () => {
  function examplesWithPresets() {
    const existing = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((input, init) => {
      if (input === "/api/examples")
        return response({
          examples: [
            {
              id: "s2_fp32_adamw_1b",
              title: "Legacy optimizer example",
              expected_mode: "reclaim",
              baseline_verified: true,
              recommended: { target: "reclaim", allocator_conf: null },
              baseline_note: "Baseline already fits 22 GB.",
            },
            {
              id: "s2_capacity_v2",
              title: "Capacity repair",
              expected_mode: "fit",
              baseline_verified: true,
              recommended: {
                target: "fit:22GB",
                allocator_conf: "expandable_segments:True",
              },
              baseline_note:
                "Capacity baseline measured; not a verified model repair.",
            },
          ],
        });
      if (input === "/api/runs")
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Offline preset captured" }), {
            status: 400,
          }),
        );
      return existing(input, init);
    });
  }
  async function chooseCapacity() {
    fireEvent.click(
      await screen.findByRole("button", { name: /Capacity repair/ }),
    );
  }
  async function posted() {
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    await screen.findByText(
      "The request could not be processed. Check the supplied inputs.",
    );
    const call = vi
      .mocked(fetch)
      .mock.calls.filter(([path]) => path === "/api/runs")
      .at(-1)!;
    return JSON.parse(String(call[1]?.body));
  }
  it("uses old reclaim and new fit22 recommendations and sends the capacity environment", async () => {
    examplesWithPresets();
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Legacy optimizer example/ }),
    );
    expect(
      screen.getByRole("radio", { name: /Reclaim headroom/ }),
    ).toBeChecked();
    await chooseCapacity();
    expect(
      screen.getByRole("radio", { name: /Fit a memory budget/ }),
    ).toBeChecked();
    expect(screen.getByLabelText("Target memory in GB")).toHaveValue(22);
    expect(
      screen.getByText(/Example environment: expandable_segments:True/),
    ).toBeInTheDocument();
    const body = await posted();
    expect(body.example_id).toBe("s2_capacity_v2");
    expect(body.target).toBe("fit:22GB");
    expect(body.allocator_conf).toBe("expandable_segments:True");
    expect(body.policy.allow_numerics_change).toBe(false);
  });
  it("preserves a manually edited fit limit across cards and supports an explicit reset", async () => {
    examplesWithPresets();
    render(<App />);
    await chooseCapacity();
    fireEvent.change(screen.getByLabelText("Target memory in GB"), {
      target: { value: "18" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Legacy optimizer example/ }),
    );
    expect(screen.getByLabelText("Target memory in GB")).toHaveValue(18);
    expect(screen.getByText(/Your custom target is kept/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Use recommended target" }),
    );
    expect(
      screen.getByRole("radio", { name: /Reclaim headroom/ }),
    ).toBeChecked();
    expect((await posted()).allocator_conf).toBeNull();
  });
  it("preserves an explicitly chosen fix-oom target even when it matches the initial default", async () => {
    examplesWithPresets();
    render(<App />);
    await chooseCapacity();
    fireEvent.click(screen.getByRole("radio", { name: /Fix out of memory/ }));
    fireEvent.click(
      screen.getByRole("button", { name: /Legacy optimizer example/ }),
    );
    await chooseCapacity();
    expect(
      screen.getByRole("radio", { name: /Fix out of memory/ }),
    ).toBeChecked();
    expect((await posted()).target).toBe("fix-oom");
  });
  it.each([false, true])(
    "does not leak the capacity environment into pasted source (manual=%s)",
    async (manual) => {
      examplesWithPresets();
      render(<App />);
      await chooseCapacity();
      if (manual)
        fireEvent.change(screen.getByLabelText("Target memory in GB"), {
          target: { value: "18" },
        });
      fireEvent.click(screen.getByRole("button", { name: "Paste a script" }));
      fireEvent.change(screen.getByLabelText("Python training script"), {
        target: { value: "print('offline')" },
      });
      const body = await posted();
      expect(body.example_id).toBeUndefined();
      expect(body.script_text).toBe("print('offline')");
      expect(body.allocator_conf).toBeNull();
      expect(body.target).toBe(manual ? "fit:18GB" : "fix-oom");
      fireEvent.click(screen.getByRole("button", { name: "Use an example" }));
      expect(screen.getByLabelText("Target memory in GB")).toHaveValue(
        manual ? 18 : 22,
      );
    },
  );
});

it("keeps About limitations clear without internal financial or review terminology", async () => {
  window.history.replaceState({}, "", "/about");
  const { container } = render(<App />);
  expect(
    screen.getByRole("heading", { name: "Limitations" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Numerical comparisons cover the recorded loss samples/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Missing measurements and costs remain Unknown/),
  ).toBeInTheDocument();
  expect(container.textContent).toContain("Limitations");
});

describe("separate home and public submission", () => {
  function publicAPI(judgeScripts = true, enabled = true) {
    vi.stubGlobal(
      "fetch",
      vi.fn((path: unknown) => {
        if (path === "/api/config")
          return response({
            public_demo: true,
            verified_runs_enabled: false,
            judge_scripts_available: judgeScripts,
            run_submissions: { enabled },
          });
        if (path === "/api/health")
          return response({ token_factory: { configured: true }, queue: {} });
        if (path === "/api/examples")
          return response({
            examples: [{ id: "s1_batch_too_big", title: "Activation memory" }],
          });
        if (path === "/api/runs")
          return Promise.resolve(
            new Response(
              JSON.stringify({ detail: "Offline submission captured" }),
              { status: 400 },
            ),
          );
        return Promise.reject(new Error("Unexpected request"));
      }),
    );
  }
  it("shows three home actions while the server-controlled gallery stays closed", async () => {
    window.history.replaceState({}, "", "/");
    publicAPI(false, false);
    render(<App />);
    expect(
      await screen.findByText(/Live analysis temporarily paused/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Verified runs.*Coming soon/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("link", { name: "Run an example" }),
    ).toHaveAttribute("href", "/run");
    expect(screen.getAllByRole("link", { name: "Results" })).toHaveLength(2);
    expect(
      screen.queryByRole("button", { name: /Start analysis/ }),
    ).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.map(([path]) => path)).toEqual([
      "/api/config",
    ]);
  });
  it("requires an ephemeral judge token for public scripts and sends it only in Authorization", async () => {
    publicAPI();
    render(<App />);
    await screen.findByRole("button", { name: /Activation memory/ });
    fireEvent.click(screen.getByRole("button", { name: "Paste a script" }));
    fireEvent.change(screen.getByLabelText("Python training script"), {
      target: { value: "print(1)" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter your judge access token",
    );
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
    ).toBe(false);
    fireEvent.change(screen.getByLabelText("Judge access token"), {
      target: { value: "test-token" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Start analysis/ }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    await screen.findByText(
      "The request could not be processed. Check the supplied inputs.",
    );
    const request = vi
      .mocked(fetch)
      .mock.calls.find(([path]) => path === "/api/runs")!;
    expect(recordHeaders(request[1]?.headers).Authorization).toBe(
      "Bearer test-token",
    );
    expect(String(request[1]?.body)).not.toContain("test-token");
    expect(JSON.parse(String(request[1]?.body)).budget).toBe("0.30");
    expect(screen.getByLabelText("Judge access token")).toHaveValue("");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(window.location.href).not.toContain("test-token");
    expect(document.cookie).not.toContain("test-token");
    expect(
      screen.queryByLabelText("Run budget in USD"),
    ).not.toBeInTheDocument();
  });
  it("uses the entered judge token when switching from a script to an example", async () => {
    publicAPI();
    render(<App />);
    await screen.findByRole("button", { name: /Activation memory/ });
    fireEvent.click(screen.getByRole("button", { name: "Paste a script" }));
    fireEvent.change(screen.getByLabelText("Judge access token"), {
      target: { value: "test-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Use an example" }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Activation memory/ }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Start analysis/ }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    await screen.findByText(
      "The request could not be processed. Check the supplied inputs.",
    );
    const request = vi
      .mocked(fetch)
      .mock.calls.find(([path]) => path === "/api/runs")!;
    expect(recordHeaders(request[1]?.headers).Authorization).toBe(
      "Bearer test-token",
    );
  });
  it("does not let a query string enable the script form", async () => {
    window.history.replaceState({}, "", "/run?judge_scripts_available=true");
    publicAPI(false);
    render(<App />);
    await screen.findByRole("button", { name: /Activation memory/ });
    expect(
      screen.queryByRole("button", { name: "Paste a script" }),
    ).not.toBeInTheDocument();
  });
});
function recordHeaders(value: HeadersInit | undefined): Record<string, string> {
  return value as Record<string, string>;
}

it("never flashes public script or budget controls before configuration arrives", () => {
  window.history.replaceState({}, "", "/run");
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  render(<App />);
  expect(
    screen.getByText("Checking service availability…"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Paste a script" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Run budget in USD")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Judge access token")).not.toBeInTheDocument();
});

describe("judge access with an exhausted anonymous allowance", () => {
  function dualPoolFetch({ gpuBusy = false, queueFull = false } = {}) {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: unknown, init?: RequestInit) => {
        const auth = new Headers(init?.headers).get("Authorization");
        if (input === "/api/config")
          return response({
            public_demo: true,
            judge_scripts_available: true,
            run_submissions: { enabled: false },
          });
        if (input === "/api/health") {
          if (auth && auth !== "Bearer offline-judge-token")
            return Promise.resolve(new Response("{}", { status: 401 }));
          const enabled = auth === "Bearer offline-judge-token";
          return response({
            run_submissions: { enabled },
            local_budget: { status: enabled ? "available" : "unavailable" },
            token_factory: { configured: true },
            gpu: {
              status: gpuBusy ? "busy" : "available",
              available: !gpuBusy,
              busy: gpuBusy,
            },
            queue: {
              running: queueFull,
              pending: queueFull ? 2 : 0,
              capacity: 3,
            },
            limits: {
              hourly_limit_applies: !enabled,
              runs_per_ip_per_hour: enabled ? null : 1,
              max_waiting_runs: 2,
              deadline_seconds: 480,
            },
          });
        }
        if (input === "/api/examples")
          return response({
            examples: [
              {
                id: "s1_batch_too_big",
                title: "Activation memory",
                expected_mode: "oom",
                baseline_verified: true,
              },
            ],
          });
        if (input === "/api/runs")
          return Promise.resolve(new Response("{}", { status: 400 }));
        return Promise.reject(new Error("Unexpected offline UI request"));
      }),
    );
  }

  it("checks the entered token server-side and sends it for an example", async () => {
    dualPoolFetch();
    render(<App />);
    const token = await screen.findByLabelText("Judge access token");
    expect(
      screen.getByRole("button", { name: /Start analysis/ }),
    ).toBeDisabled();
    fireEvent.change(token, { target: { value: "offline-judge-token" } });
    fireEvent.click(
      await screen.findByRole("button", { name: /Activation memory/ }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Start analysis/ }),
      ).toBeEnabled(),
    );
    expect(
      screen.getByText(/No hourly run-count limit for this token/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/per-run spending limits still apply/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
      ).toBe(true),
    );
    const post = vi
      .mocked(fetch)
      .mock.calls.find(([path]) => path === "/api/runs")!;
    expect(new Headers(post[1]?.headers).get("Authorization")).toBe(
      "Bearer offline-judge-token",
    );
    expect(JSON.parse(String(post[1]?.body)).example_id).toBe(
      "s1_batch_too_big",
    );
    await waitFor(() => expect(token).toHaveValue(""));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(window.location.search).toBe("");
  });

  it("keeps invalid tokens blocked without falling back to anonymous submission", async () => {
    dualPoolFetch();
    render(<App />);
    const token = await screen.findByLabelText("Judge access token");
    fireEvent.change(token, { target: { value: "wrong-token" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The judge access token was not accepted.",
    );
    expect(
      screen.getByRole("button", { name: /Start analysis/ }),
    ).toBeDisabled();
    expect(
      vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
    ).toBe(false);
    expect(token).toHaveValue("wrong-token");
    expect(
      screen.queryByText(/No hourly run-count limit/),
    ).not.toBeInTheDocument();
  });

  it.each([
    ["busy GPU", { gpuBusy: true }],
    ["full queue", { queueFull: true }],
  ] as const)(
    "keeps %s protection with an unlimited hourly token",
    async (_label, state) => {
      dualPoolFetch(state);
      render(<App />);
      const token = await screen.findByLabelText("Judge access token");
      fireEvent.change(token, { target: { value: "offline-judge-token" } });
      fireEvent.click(
        await screen.findByRole("button", { name: /Activation memory/ }),
      );
      expect(
        await screen.findByText(/No hourly run-count limit for this token/),
      ).toBeInTheDocument();
      if ("gpuBusy" in state) {
        expect(screen.getByText("The GPU is busy.")).toBeInTheDocument();
      } else {
        expect(
          screen.getByText(/The run queue is currently unavailable/),
        ).toBeInTheDocument();
      }
      expect(
        screen.getByRole("button", { name: /Start analysis/ }),
      ).toBeDisabled();
      fireEvent.click(screen.getByRole("button", { name: /Start analysis/ }));
      expect(
        vi.mocked(fetch).mock.calls.some(([path]) => path === "/api/runs"),
      ).toBe(false);
    },
  );
});
