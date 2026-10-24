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
      "Any patch/config applied",
      "Selected round",
      "Selected patch/config applied",
      "Selected completed",
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

it("keeps historical campaign search mode unrecorded", async () => {
  setup(fixture());
  render(<App />);
  expect(
    await screen.findByText(/Search mode: Not recorded/),
  ).toBeInTheDocument();
});

function outcomeCell(table: HTMLElement, heading: string, rowIndex = 1) {
  const headings = within(table).getAllByRole("columnheader");
  const index = headings.findIndex((cell) => cell.textContent === heading);
  expect(index).toBeGreaterThanOrEqual(0);
  const row = within(table).getAllByRole("row")[rowIndex];
  return row.children[index] as HTMLElement;
}
function displayedOutcome(table: HTMLElement, heading: string) {
  return outcomeCell(table, heading).firstChild?.textContent;
}

describe("recorded patch and completion outcomes", () => {
  it.each(["completed", "budget_exceeded", "error"])(
    "keeps selected evidence apart from a later reverted candidate when search is %s",
    async (status) => {
      const document = fixture("live");
      Object.assign(document.rows[0], {
        status,
        target_met: true,
        patch_applied: true,
        patch_applied_rounds: [1, 2],
        selected_round: 1,
        selected_patch_applied: true,
        selected_completed: true,
        outcome_basis: "recorded_round_artifacts_v1",
        round_outcomes: [
          {
            round: 1,
            decision: "keep",
            patch_applied: true,
            candidate_completed: true,
          },
          {
            round: 2,
            decision: "revert",
            patch_applied: true,
            candidate_completed: false,
          },
        ],
      });
      setup(document);
      render(<App />);
      const table = await screen.findByRole("table", {
        name: "Main evaluation results",
      });
      expect(displayedOutcome(table, "Any patch/config applied")).toBe("Yes");
      expect(displayedOutcome(table, "Selected round")).toBe("1");
      expect(displayedOutcome(table, "Selected patch/config applied")).toBe(
        "Yes",
      );
      expect(displayedOutcome(table, "Selected completed")).toBe("Yes");
      expect(outcomeCell(table, "Peak after")).toHaveTextContent("8.00 GB");
      const details = outcomeCell(
        table,
        "Any patch/config applied",
      ).querySelector("details")!;
      expect(details).not.toHaveAttribute("open");
      expect(details).toHaveTextContent(
        "Round 2: patch/config applied Yes; candidate completed No; decision Revert.",
      );
      expect(screen.getByText(/Selected fields describe/)).toHaveTextContent(
        "Peak before is the baseline; peak after, reductions and timing changes compare that baseline with the final selected configuration.",
      );
    },
  );

  it("preserves an applied and completed attempt without presenting it as selected", async () => {
    const document = fixture("live");
    Object.assign(document.rows[0], {
      status: "completed",
      patch_applied: true,
      selected_round: null,
      selected_patch_applied: false,
      selected_completed: null,
      round_outcomes: [
        {
          round: 1,
          decision: "revert",
          patch_applied: true,
          candidate_completed: true,
        },
      ],
    });
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    expect(displayedOutcome(table, "Any patch/config applied")).toBe("Yes");
    expect(displayedOutcome(table, "Selected round")).toBe("Unknown");
    expect(displayedOutcome(table, "Selected patch/config applied")).toBe("No");
    expect(displayedOutcome(table, "Selected completed")).toBe("Unknown");
    expect(outcomeCell(table, "Any patch/config applied")).toHaveTextContent(
      "candidate completed Yes; decision Revert.",
    );
  });

  it("uses recorded facts for a CLI-only application with an empty diff", async () => {
    const document = fixture("live");
    Object.assign(document.rows[0], {
      patch_diff: "",
      patch_applied: true,
      selected_round: 1,
      selected_patch_applied: true,
      selected_completed: true,
    });
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    expect(displayedOutcome(table, "Any patch/config applied")).toBe("Yes");
    expect(displayedOutcome(table, "Selected completed")).toBe("Yes");
  });

  it.each([undefined, null, "true", "false", 1, 0, {}])(
    "keeps missing or malformed outcomes Unknown instead of deriving them from success (%j)",
    async (outcome) => {
      const document = fixture("live");
      Object.assign(document.rows[0], {
        status: "completed",
        target_met: true,
        patch_applied: outcome,
        selected_patch_applied: outcome,
        selected_completed: outcome,
        round_outcomes: [
          {
            round: 1,
            decision: "keep",
            patch_applied: true,
            candidate_completed: true,
          },
        ],
      });
      setup(document);
      render(<App />);
      const table = await screen.findByRole("table", {
        name: "Main evaluation results",
      });
      for (const heading of [
        "Any patch/config applied",
        "Selected patch/config applied",
        "Selected completed",
      ]) {
        expect(displayedOutcome(table, heading)).toBe("Unknown");
      }
      expect(displayedOutcome(table, "Selected round")).toBe("Unknown");
    },
  );

  it("shows recorded No and Unknown separately in round attempts", async () => {
    const document = fixture("live");
    Object.assign(document.rows[0], {
      patch_applied: false,
      selected_patch_applied: false,
      selected_completed: false,
      round_outcomes: [
        {
          round: 1,
          decision: "revert",
          patch_applied: false,
          candidate_completed: null,
        },
        {
          round: "2",
          decision: "invented",
          patch_applied: "false",
          candidate_completed: 1,
        },
      ],
    });
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    expect(displayedOutcome(table, "Any patch/config applied")).toBe("No");
    expect(displayedOutcome(table, "Selected completed")).toBe("No");
    expect(outcomeCell(table, "Any patch/config applied")).toHaveTextContent(
      "Round 1: patch/config applied No; candidate completed Unknown; decision Revert.",
    );
    expect(outcomeCell(table, "Any patch/config applied")).toHaveTextContent(
      "Round Unknown: patch/config applied Unknown; candidate completed Unknown; decision Unknown.",
    );
  });

  it("aligns live-only outcome totals with their columns and keeps the wide table in its scroll region", async () => {
    const document = fixture("live");
    Object.assign(document.summary, {
      outcomes: {
        patch_applied: {
          true_count: 2,
          false_count: 1,
          unknown_count: 3,
          known_count: 3,
        },
        selected_patch_applied: {
          true_count: 1,
          false_count: 2,
          unknown_count: 3,
          known_count: 3,
        },
        selected_completed: {
          true_count: 1,
          false_count: 0,
          unknown_count: 5,
          known_count: 1,
        },
      },
    });
    setup(document);
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    const allRows = within(table).getAllByRole("row");
    const columnCount = within(table).getAllByRole("columnheader").length;
    expect(columnCount).toBe(22);
    for (const row of allRows) expect(row.children).toHaveLength(columnCount);
    expect(outcomeCell(table, "Any patch/config applied", 2)).toHaveTextContent(
      "2 Yes / 1 No; 3 Unknown",
    );
    expect(outcomeCell(table, "Selected round", 2)).toHaveTextContent("—");
    expect(
      outcomeCell(table, "Selected patch/config applied", 2),
    ).toHaveTextContent("1 Yes / 2 No; 3 Unknown");
    expect(outcomeCell(table, "Selected completed", 2)).toHaveTextContent(
      "1 Yes / 0 No; 5 Unknown",
    );
    expect(outcomeCell(table, "Peak after", 2)).toHaveTextContent("—");
    const region = screen.getByRole("region", {
      name: "Scrollable evaluation results",
    });
    expect(region).toHaveClass("table-wrap");
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region).toContainElement(table);
    expect(table).toHaveClass("evaluation-main-table");
    expect(outcomeCell(table, "State")).toHaveClass("evaluation-column-status");
    expect(outcomeCell(table, "Any patch/config applied")).toHaveClass(
      "evaluation-column-patch_applied",
    );
    expect(
      outcomeCell(table, "Any patch/config applied").querySelector("details"),
    ).toHaveClass("evaluation-round-attempts");
  });

  it("keeps historical missing summary outcomes and round details unknown", async () => {
    setup(fixture("live"));
    render(<App />);
    const table = await screen.findByRole("table", {
      name: "Main evaluation results",
    });
    for (const heading of [
      "Any patch/config applied",
      "Selected patch/config applied",
      "Selected completed",
    ]) {
      expect(outcomeCell(table, heading, 2)).toHaveTextContent(/^Unknown$/);
    }
    expect(outcomeCell(table, "Any patch/config applied")).toHaveTextContent(
      "Round attempts: Unknown.",
    );
  });
});
