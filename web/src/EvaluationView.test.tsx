import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import App from "./App";
const response = (data: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(data), { status }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
function setup(document: unknown = null, fail = false) {
  window.history.replaceState({}, "", "/results");
  vi.stubGlobal(
    "fetch",
    vi.fn((input: unknown) => {
      if (input === "/api/health") return response({});
      if (input === "/api/runs") return response({ runs: [] });
      if (input === "/api/usage") return response({});
      if (input === "/api/replays") return response({ replays: [] });
      if (input === "/api/evaluations")
        return fail
          ? response(
              { detail: "Published evaluation evidence is unavailable" },
              503,
            )
          : response({
              evaluations: document
                ? [{ id: "reviewed", title: "Reviewed campaign" }]
                : [],
            });
      if (input === "/api/evaluations/reviewed") return response(document);
      return Promise.reject(new Error("Unexpected request"));
    }),
  );
}
function fixture(provenance = "offline_fixture") {
  return {
    provenance,
    status: "finished",
    rows: [
      {
        scenario_id: "s1",
        condition: "full_ultra",
        policy_name: "strict",
        provenance,
        status: "completed",
        ground_truth: "activations",
        first_cause_matches: true,
        target_met: false,
        peak_before_bytes: 10e9,
        peak_after_bytes: 8e9,
        peak_reduction_pct: "20.125",
        throughput_change_pct: null,
        step_time_change_pct: "12.25",
        loss_equivalence: "within_tol",
        numerical_basis: "original_plan_full_backward_scalar_series",
        acceptance_scope: "standard",
        rounds: 2,
        cost_usd: null,
        wall_seconds: 45,
        run_id: "a".repeat(32),
      },
    ],
    summary: {
      status: "pending",
      attempted_live_runs: 0,
      target_met_count: 0,
      target_met_rate: null,
      target_measured_denominator: 0,
      target_unknown_runs: 0,
      first_cause_correct: 0,
      first_cause_accuracy: null,
      first_cause_scored_denominator: 0,
      first_cause_unknown_runs: 0,
      known_cost_usd: "0",
      total_cost_usd: null,
      offline_fixture_rows_excluded: 1,
      measured_metrics: {
        numerical_equivalence: {
          equivalent: 0,
          comparable_count: 0,
          not_comparable_or_unknown: 0,
          rate_among_comparable: null,
        },
      },
    },
    ablation: {
      paired_scored_count: 0,
      accuracy: {},
      pairs: [],
      excluded: [],
      aggregation_scope: "scenario-policy pairs",
    },
    conclusions: [
      "No live evaluation scores are available; offline fixtures are excluded from live scores.",
    ],
  };
}
describe("published evaluation results", () => {
  it("shows the no-reference exception beside n/a without claiming equivalence", async () => {
    const document = fixture();
    document.rows[0].loss_equivalence = "n/a";
    document.rows[0].numerical_basis = "repository_no_reference_exception";
    document.rows[0].acceptance_scope = "repository";
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    expect(within(table).getByText("n/a")).toBeInTheDocument();
    expect(
      within(table).getByText(
        "Repository without reference; numerical equivalence unverified",
      ),
    ).toHaveAttribute("title", "Acceptance scope: repository");
  });

  it("keeps unpublished evaluation pending without claiming a benchmark", async () => {
    setup();
    render(<App />);
    expect(
      await screen.findByText("Evaluation publication pending"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Main evaluation results" }),
    ).not.toBeInTheDocument();
  });
  it("shows complete columns, unknown metrics and fixture exclusion", async () => {
    setup(fixture());
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    for (const heading of [
      "Authored cause",
      "First cause matches",
      "Reduction %",
      "Throughput change %",
      "Step-time change %",
      "Numerics",
      "Rounds",
      "Cost USD",
      "Wall seconds",
    ])
      expect(
        within(table).getByRole("columnheader", { name: heading }),
      ).toBeInTheDocument();
    expect(within(table).getByText("10.00 GB")).toBeInTheDocument();
    expect(within(table).getByText("20.125")).toBeInTheDocument();
    expect(within(table).getByText("12.25")).toBeInTheDocument();
    expect(within(table).getByText("Summary (live only)")).toBeInTheDocument();
    expect(
      screen.getByText("Offline fixture · excluded from live scores"),
    ).toBeInTheDocument();
    expect(screen.getByText(/No live evaluation scores/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Download published evaluation/ }),
    ).toHaveAttribute("href", "/api/evaluations/reviewed");
    expect(
      screen.getByText("No comparable three-condition pairs."),
    ).toBeInTheDocument();
  });
  it("shows paired conditions and exclusions without hiding unscored groups", async () => {
    const document = fixture("live");
    document.ablation = {
      paired_scored_count: 1,
      accuracy: { full_ultra: 1, traceback_ultra: 0, full_super: 1 },
      pairs: [
        {
          scenario_id: "s1",
          policy_name: "strict",
          correct: {
            full_ultra: true,
            traceback_ultra: false,
            full_super: true,
          },
        },
      ] as never[],
      excluded: [
        {
          scenario_id: "s2",
          policy_name: "strict",
          reason: "source_hash_not_comparable",
        },
      ] as never[],
      aggregation_scope: "scenario-policy pairs",
    };
    document.conclusions = [
      "Only one comparable pair is recorded; these observations do not establish statistical significance.",
    ];
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Paired ablation summary",
    });
    expect(within(table).getAllByText("100.00%")).toHaveLength(2);
    expect(within(table).getByText("0.00%")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Excluded ablation groups" }),
    ).toHaveTextContent("source hash not comparable");
  });
  it("keeps a publication failure distinct from a pending empty catalog", async () => {
    setup(null, true);
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("unavailable");
  });
});
