import { describe, expect, it } from "vitest";
import {
  analysisOf,
  availabilityBlocks,
  artifactLink,
  costTotal,
  configurationLink,
  displayMetric,
  externalLink,
  gb,
  mergeEvents,
  parseEvent,
  provenanceLabel,
  queueAtCapacity,
  timelinePoints,
  validateSubmission,
  verificationRows,
  type Submission,
} from "./data";
const id = "a".repeat(32);
describe("measurement and charge honesty", () => {
  it("keeps absent and nonfinite measurements unknown", () => {
    expect(gb(null)).toBe("Unknown");
    expect(gb(undefined)).toBe("Unknown");
    expect(gb(NaN)).toBe("Unknown");
    expect(gb(0)).toBe("0.00 GB");
    expect(displayMetric({}, "peak_after")).toBe("Unknown");
  });
  it("does not turn an unknown charge into a zero total", () => {
    expect(costTotal({ total_cost_usd: "0", unknown_cost_calls: 1 })).toBe(
      "Unknown",
    );
    expect(costTotal({ total_cost_usd: "0", complete: false })).toBe("Unknown");
    expect(costTotal({ total_cost_usd: "0", complete: true, calls: 0 })).toBe(
      "$0.0000",
    );
    expect(costTotal({})).toBe("Unknown");
  });
  it("uses display values from actual report JSON", () => {
    expect(
      displayMetric({ display: { peak_before: "21.553 GB" } }, "peak_before"),
    ).toBe("21.553 GB");
    expect(
      displayMetric({ display: { peak_after: "unknown" } }, "peak_after", 0),
    ).toBe("Unknown");
  });
  it("does not infer verification from a generated patch", () => {
    const values = verificationRows({ rounds: [{ status: "applied" }] });
    expect(values.find((r) => r.label === "Target met")?.value).toBe("Unknown");
  });
  it("labels fixture and historical provenance prominently", () => {
    expect(provenanceLabel({ provenance: "offline-fixture" }, true)).toMatch(
      /not a verified repair/,
    );
    expect(provenanceLabel({ provenance: "live" }, true)).toMatch(/historical/);
    expect(provenanceLabel({ provenance: "live" })).toBeNull();
  });
});
describe("SSE ordering and input validation", () => {
  it("deduplicates reconnect events and sorts out-of-order delivery", () => {
    const a = parseEvent({ sequence: 2, kind: "run.started", data: {} })!;
    const b = parseEvent({ sequence: 1, kind: "run.queued", data: {} })!;
    const state = mergeEvents(mergeEvents([], a), b);
    expect(state.map((e) => e.sequence)).toEqual([1, 2]);
    expect(mergeEvents(state, a)).toBe(state);
  });
  it("rejects malformed event envelopes", () => {
    expect(parseEvent({ sequence: 0, kind: "x" })).toBeNull();
    expect(parseEvent({ sequence: "1", kind: "x" })).toBeNull();
    expect(parseEvent({ sequence: 1 })).toBeNull();
  });
  const valid: Submission = {
    example_id: "s1_batch_too_big",
    target: "fit:22GB",
    budget: "0.60",
    policy: {
      allow_numerics_change: false,
      allow_model_change: false,
      allow_batch_grad_accum: true,
      max_throughput_regression_pct: 25,
    },
  };
  it("keeps budget as a string and accepts exactly one source", () => {
    expect(validateSubmission(valid)).toBeNull();
    expect(typeof valid.budget).toBe("string");
    expect(validateSubmission({ ...valid, script_text: "x=1" })).toMatch(
      /Choose/,
    );
    expect(validateSubmission({ ...valid, example_id: undefined })).toMatch(
      /Choose/,
    );
  });
  it("rejects invalid budgets and memory targets", () => {
    for (const budget of ["0", "NaN", "-1", "5.01"])
      expect(validateSubmission({ ...valid, budget })).toMatch(/budget/);
    expect(validateSubmission({ ...valid, target: "fit:0GB" })).toMatch(
      /greater/,
    );
  });
});
describe("real evidence shapes and safe links", () => {
  it("adapts native allocator event points without adding missing after values", () => {
    const before = {
      timeline: [
        { event_index: 0, allocated_bytes: 0 },
        { event_index: 246, allocated_bytes: 4095410176 },
        { event_index: 247, allocated_bytes: null },
      ],
    };
    const points = timelinePoints(before, {});
    expect(points).toEqual([
      { event: 0, before: 0, after: null },
      { event: 246, before: 4.095410176, after: null },
    ]);
  });
  it("reads the original evidence bundle and paired report shapes", () => {
    const header = { peak_allocated_bytes: 21553250816, peak_is_exact: true };
    expect(
      analysisOf({ evidence: { analysis: { header } } }, "before").header,
    ).toEqual(header);
    expect(
      analysisOf({ evidence: { before: { analysis: { header } } } }, "before")
        .header,
    ).toEqual(header);
    expect(analysisOf({}, "after")).toEqual({});
  });
  it("only exposes declared same-run artifacts", () => {
    const good = `/api/runs/${id}/patch.diff`;
    expect(artifactLink(id, "patch.diff", { "patch.diff": good })).toBe(good);
    expect(artifactLink(id, "patch.diff", {})).toBeNull();
    expect(
      artifactLink(id, "patch.diff", {
        "patch.diff": "https://attacker.invalid/x",
      }),
    ).toBeNull();
    expect(
      artifactLink(id, "patch.diff", {
        "patch.diff": `/api/runs/${"b".repeat(32)}/patch.diff`,
      }),
    ).toBeNull();
  });
  it("rejects active-content and credential source URLs", () => {
    expect(externalLink("javascript:alert(1)")).toBeNull();
    expect(externalLink("https://user:key@example.com/a")).toBeNull();
    expect(
      externalLink("https://docs.pytorch.org/docs/2.5/checkpoint.html"),
    ).toContain("/2.5/");
  });
});

it("marks baseline replays separately from verified repairs", () => {
  expect(provenanceLabel({ provenance: "recorded_baseline" })).toContain(
    "no repair performed",
  );
  expect(
    verificationRows({
      run: { provenance: "recorded_baseline" },
      summary: { target_met: true },
    })[0].value,
  ).toBe("N/A — baseline only");
});
it("only links fixed configuration files inside a run", () => {
  expect(configurationLink(id, "configurations/round-01/patch.diff")).toBe(
    `/api/runs/${id}/configurations/round-01/patch.diff`,
  );
  for (const path of [
    "../.env",
    "configurations/round-01/../../.env",
    "configurations/round-07/patch.diff",
    "https://example.com/patch.diff",
  ])
    expect(configurationLink(id, path)).toBeNull();
});

it("counts repository preparation and the active worker against capacity", () => {
  expect(
    queueAtCapacity({ capacity: 3, pending: 1, preparing: 1, running: id }),
  ).toBe(true);
  expect(
    queueAtCapacity({ capacity: 3, pending: 1, preparing: 0, running: id }),
  ).toBe(false);
  expect(queueAtCapacity({ halted: true })).toBe(true);
});

describe("availability evidence", () => {
  it("uses fresh explicit GPU busy evidence and keeps unknown or stale data unblocked", () => {
    expect(
      availabilityBlocks({ gpu: { status: "busy", busy: true, stale: false } })
        .gpuBusy,
    ).toBe(true);
    expect(
      availabilityBlocks({ gpu: { status: "busy", busy: true, stale: true } })
        .gpuBusy,
    ).toBe(false);
    expect(
      availabilityBlocks({ gpu: { status: "unknown", busy: null } }).gpuBusy,
    ).toBe(false);
    expect(
      availabilityBlocks({ gpu: { status: "busy", busy: false } }).gpuBusy,
    ).toBe(false);
  });
  it("never confuses an account balance or unknown budget with an exhausted local limit", () => {
    expect(
      availabilityBlocks({
        local_budget: {
          status: "exhausted",
          scope: "local_application_authorization",
        },
      }).budgetBlocked,
    ).toBe(true);
    expect(
      availabilityBlocks({
        local_budget: {
          status: "billing_review_required",
          scope: "local_application_authorization",
        },
      }).budgetReason,
    ).toBe("billing_review_required");
    expect(
      availabilityBlocks({
        local_budget: {
          status: "pending_charge",
          scope: "local_application_authorization",
        },
      }).budgetReason,
    ).toBe("pending_charge");
    expect(
      availabilityBlocks({
        local_budget: { status: "unknown", remaining_usd: null },
      }).budgetBlocked,
    ).toBe(false);
    expect(
      availabilityBlocks({
        local_budget: { status: "exhausted", scope: "provider_account" },
      }).budgetBlocked,
    ).toBe(false);
  });
});
