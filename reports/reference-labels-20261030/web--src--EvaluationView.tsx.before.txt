import { useEffect, useState } from "react";
import { getJSON, productMessage } from "./api";
import {
  record,
  rows,
  text,
  decimal,
  gb,
  human,
  searchModeLabel,
  type Dict,
} from "./data";
import { Badge, Empty, Loading, Notice, Section } from "./components";

const conditions = ["full_ultra", "traceback_ultra", "full_super"];
const columns: [string, string][] = [
  ["scenario_id", "Scenario"],
  ["condition", "Condition"],
  ["policy_name", "Policy"],
  ["provenance", "Evidence"],
  ["status", "State"],
  ["diagnosis_attempt_recorded", "Diagnosis attempt recorded"],
  ["patch_attempt_recorded", "Patch attempt recorded"],
  ["ground_truth", "Authored cause"],
  ["first_cause_matches", "First cause matches"],
  ["target_met", "Target met"],
  ["patch_applied", "Any patch/config applied"],
  ["selected_round", "Selected round"],
  ["selected_patch_applied", "Selected patch/config applied"],
  ["selected_completed", "Selected completed"],
  ["peak_before_bytes", "Peak before"],
  ["peak_after_bytes", "Peak after"],
  ["peak_reduction_pct", "Reduction %"],
  ["throughput_change_pct", "Throughput change %"],
  ["step_time_change_pct", "Step-time change %"],
  ["loss_equivalence", "Numerics"],
  ["rounds", "Rounds"],
  ["cost_usd", "Actual cost USD"],
  ["wall_seconds", "Wall seconds"],
  ["run_id", "Source run"],
];
const value = (v: unknown) =>
  typeof v === "boolean"
    ? v
      ? "Yes"
      : "No"
    : v == null
      ? "Unknown"
      : String(v);
const percent = (v: unknown) =>
  decimal(v) === null ? "Unknown" : (decimal(v)! * 100).toFixed(2) + "%";
const number = (v: unknown, digits = 2) => {
  const n = decimal(v);
  return n === null
    ? "Unknown"
    : n.toLocaleString("en-US", { maximumFractionDigits: digits });
};
const cost = (v: unknown) => {
  const n = decimal(v);
  if (n === null || n < 0) return "Unknown";
  if (n > 0 && n < 0.0001) return "<$0.0001";
  return "$" + n.toFixed(n > 0 && n < 0.01 ? 4 : 2);
};
const scenarioName = (v: unknown) =>
  (
    ({
      s1_batch_too_big: "Large training batch",
      s2_capacity_v2: "Model and optimizer memory",
      s3_eval_no_grad_missing: "Evaluation loop",
      s4_loss_accumulation_graph: "Accumulated loss graph",
      s5_fragmentation_varlen: "Variable-length batches",
      s6_full_vocab_logits_fp32: "Full-vocabulary logits",
      s7_frozen_params_optimizer_state: "Frozen parameters",
      s8_two_models_resident: "Two resident models",
      nanogpt: "nanoGPT",
    }) as Record<string, string>
  )[String(v)] ?? value(v);
const conditionName = (v: unknown) =>
  (
    ({
      full_ultra: "Full evidence + Ultra",
      traceback_ultra: "Traceback + Ultra",
      full_super: "Full evidence + Super",
    }) as Record<string, string>
  )[String(v)] ?? value(v);
const campaignName = (item: Dict) =>
  (
    ({
      "r7-20261029": "October 29, 2026 · 1 of 9 memory targets met",
      "r6-20261027": "October 27, 2026 · 2 of 9 memory targets met",
      "r5-20261027": "October 27, 2026 · 3 of 9 memory targets met",
    }) as Record<string, string>
  )[String(item.id)] ?? text(item.title);
const stopReason = (v: unknown) =>
  (
    ({
      completed: "Completed",
      done: "Completed",
      failed: "Failed",
      error: "Failed",
      rejected: "Not run",
      timeout: "Timed out",
      cancelled: "Cancelled",
      needs_human: "Needs attention",
      budget_exceeded: "Stopped",
      running: "Running",
    }) as Record<string, string>
  )[String(v)] ?? productMessage(v, "Unknown");
const resultLabel = (row: Dict) =>
  row.target_met === true
    ? "Repaired"
    : row.status === "budget_exceeded" &&
        row.diagnosis_attempt_recorded === false &&
        row.patch_attempt_recorded === false
      ? "Stopped before diagnosis"
      : row.target_met === false
        ? "Not solved"
        : ["failed", "error", "rejected", "timeout"].includes(
              String(row.status),
            )
          ? "Run failed · result unknown"
          : row.status === "needs_human"
            ? "Needs review · result unknown"
            : row.status === "budget_exceeded"
              ? "Analysis paused · result unknown"
              : "Unknown";
const numericalResult = (v: unknown) =>
  (
    ({
      identical: "Identical",
      within_tol: "Within tolerance",
      changed: "Changed",
      "n/a": "Not compared",
    }) as Record<string, string>
  )[String(v)] ?? "Unknown";
const numericalBasis = (basis: unknown) =>
  (
    ({
      original_plan_first_five_backward_scalars:
        "First five recorded backward losses",
      original_plan_full_backward_scalar_series:
        "Full recorded backward-loss sequence",
      original_workload_offload_first_five_backward_scalars:
        "Observed first five backward losses with original-workload offload reference",
      repository_no_reference_exception:
        "Repository without reference; numerical equivalence unverified",
      unavailable: "Comparison unavailable",
    }) as Record<string, string>
  )[String(basis)] ?? "Comparison basis not recorded";
const outcomeKeys = new Set([
  "patch_applied",
  "selected_patch_applied",
  "selected_completed",
]);
const outcomeValue = (v: unknown) =>
  typeof v === "boolean" ? value(v) : "Unknown";
const roundValue = (v: unknown) =>
  typeof v === "number" && Number.isInteger(v) && v >= 1 && v <= 6
    ? String(v)
    : "Unknown";
const outcomeSummary = (v: unknown) => {
  const counts = record(v);
  if (
    !["true_count", "false_count", "unknown_count", "known_count"].every(
      (key) =>
        typeof counts[key] === "number" &&
        Number.isInteger(counts[key]) &&
        Number(counts[key]) >= 0,
    )
  )
    return "Unknown";
  return `${counts.true_count} Yes / ${counts.false_count} No; ${counts.unknown_count} Unknown`;
};
const metric = (key: string, v: unknown) =>
  outcomeKeys.has(key)
    ? outcomeValue(v)
    : key === "selected_round"
      ? roundValue(v)
      : key.endsWith("_bytes")
        ? gb(v)
        : key === "cost_usd"
          ? cost(v)
          : key.endsWith("_pct")
            ? number(v)
            : key === "wall_seconds" || key === "rounds"
              ? number(v, 1)
              : key === "scenario_id"
                ? scenarioName(v)
                : key === "condition"
                  ? conditionName(v)
                  : key === "status"
                    ? stopReason(v)
                    : value(v);

function RoundOutcomes({ row }: { row: Dict }) {
  const outcomes = rows(row.round_outcomes);
  return (
    <details className="evaluation-round-attempts">
      <summary>Round attempts</summary>
      {outcomes.length ? (
        <ul className="plain-list">
          {outcomes.map((attempt, index) => (
            <li key={index}>
              Round {roundValue(attempt.round)}: patch/config applied{" "}
              {outcomeValue(attempt.patch_applied)}; candidate completed{" "}
              {outcomeValue(attempt.candidate_completed)}; decision{" "}
              {attempt.decision === "keep"
                ? "Keep"
                : attempt.decision === "revert"
                  ? "Revert"
                  : "Unknown"}
              .
            </li>
          ))}
        </ul>
      ) : (
        <p className="caption">Round attempts: Unknown.</p>
      )}
      <p className="caption">
        Candidate completion describes that round only. It does not change the
        selected configuration or the measurements shown.
      </p>
    </details>
  );
}

export default function EvaluationView() {
  const [catalog, setCatalog] = useState<Dict[]>([]);
  const [selected, setSelected] = useState("");
  const [document, setDocument] = useState<Dict>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getJSON("/api/evaluations", controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const items = rows(data.evaluations).filter(
          (row) =>
            typeof row.id === "string" &&
            /^[a-z0-9][a-z0-9_-]{0,63}$/.test(row.id),
        );
        setCatalog(items);
        setSelected(items.length ? String(items[0].id) : "");
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Published evaluations are unavailable.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setLoading(true);
    setDocument({});
    setError("");
    getJSON(
      "/api/evaluations/" + encodeURIComponent(selected),
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setDocument(data);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Evaluation evidence is unavailable.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [selected]);
  const summary = record(document.summary),
    ablation = record(document.ablation);
  const measured = record(summary.measured_metrics),
    comparable = record(measured.numerical_equivalence);
  const outcomeCounts = record(summary.outcomes);
  const suite_result = record(document.suite_result);
  const summaryCells: Record<string, string> = {
    scenario_id: "Summary (live only)",
    condition: "all",
    policy_name: "all",
    provenance: "live",
    status: value(summary.status),
    ground_truth: "—",
    first_cause_matches: `${value(summary.first_cause_correct)}/${value(summary.first_cause_scored_denominator)} scored; ${value(summary.first_cause_unknown_runs)} unknown`,
    target_met: `${value(summary.target_met_count)}/${value(summary.target_measured_denominator)} known; ${value(summary.target_unknown_runs)} unknown`,
    patch_applied: outcomeSummary(outcomeCounts.patch_applied),
    selected_round: "—",
    selected_patch_applied: outcomeSummary(
      outcomeCounts.selected_patch_applied,
    ),
    selected_completed: outcomeSummary(outcomeCounts.selected_completed),
    peak_before_bytes: "—",
    peak_after_bytes: "—",
    ...Object.fromEntries(
      [
        "peak_reduction_pct",
        "throughput_change_pct",
        "step_time_change_pct",
      ].map((key) => [key, number(record(measured[key]).mean)]),
    ),
    loss_equivalence: `${value(comparable.equivalent)}/${value(comparable.comparable_count)} comparable`,
    rounds: number(record(measured.rounds).mean, 1),
    cost_usd: cost(summary.total_cost_usd),
    wall_seconds: number(record(measured.wall_seconds).mean, 1),
    run_id: "—",
  };
  const pairs = rows(ablation.pairs),
    excluded = rows(ablation.excluded);
  const summaryRows = [
    [
      "Target success",
      percent(summary.target_met_rate),
      summary.target_measured_denominator,
      summary.target_unknown_runs,
    ],
    [
      "First-cause accuracy",
      percent(summary.first_cause_accuracy),
      summary.first_cause_scored_denominator,
      summary.first_cause_unknown_runs,
    ],
    ...[
      "peak_reduction_pct",
      "throughput_change_pct",
      "step_time_change_pct",
      "rounds",
      "wall_seconds",
      "cost_usd",
    ].map((key) => {
      const m = record(measured[key]);
      return [
        (
          {
            peak_reduction_pct: "Average memory reduction (%)",
            throughput_change_pct: "Average throughput change (%)",
            step_time_change_pct: "Average step-time change (%)",
            rounds: "Average repair attempts",
            wall_seconds: "Average runtime (seconds)",
            cost_usd: "Average Token Factory cost",
          } as Record<string, string>
        )[key],
        metric(key, m.mean),
        m.measured_count,
        m.unknown_count,
      ];
    }),
    [
      "Numerical equivalence",
      percent(comparable.rate_among_comparable),
      comparable.comparable_count,
      comparable.not_comparable_or_unknown,
    ],
  ];
  return (
    <Section
      title="Published evaluations"
      kicker="Repairs, measurements, and unfinished work"
    >
      {error && <Notice tone="red">{error}</Notice>}
      {catalog.length > 0 && (
        <label className="evaluation-campaign-picker">
          Evaluation campaign{" "}
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            {catalog.map((item) => (
              <option key={String(item.id)} value={String(item.id)}>
                {campaignName(item)}
              </option>
            ))}
          </select>
        </label>
      )}
      {loading ? (
        <Loading>Loading published evaluation evidence…</Loading>
      ) : !catalog.length ? (
        error ? null : (
          <Empty title="Evaluation publication pending">
            The recorded evaluation results will appear here when available.
          </Empty>
        )
      ) : !Object.keys(document).length ? null : (
        <>
          <p>
            <Badge>
              {document.provenance === "offline_fixture"
                ? "Offline fixture · excluded from live scores"
                : "Recorded live campaign"}
            </Badge>{" "}
            <Badge>{human(document.status)}</Badge>
          </p>
          {selected === "r7-20261029" && (
            <Notice>
              <strong>1 of 9 workloads met the memory target.</strong> For this
              evaluation, “First category matches” and “First-cause accuracy” show
              raw category matching, before full diagnosis validation. Raw
              category matches: 7/9; valid correct diagnoses: 5/9. Two workloads
              lack authored ground truth and remain in the fixed nine; the
              detailed accuracy percentage uses the seven scored workloads.
            </Notice>
          )}
          {suite_result.basis === "independent_fixed_suite_review_v1" && (
            <Notice>
              <strong>
                {value(suite_result.target_met_count)}/
                {value(suite_result.fixed_denominator)} workloads repaired
                automatically.
              </strong>{" "}
              Each evaluation stands on its own; earlier successes are not added
              to this result.
              {Number(suite_result.stopped_before_diagnosis_and_patch) > 0 && (
                <>
                  {" "}
                  {value(suite_result.stopped_before_diagnosis_and_patch)}{" "}
                  workloads stopped before diagnosis or patch generation. Their
                  baseline and Nano annotation ran; these workloads remain among
                  the nine and are not counted as repairs.
                </>
              )}
            </Notice>
          )}
          <div
            className="table-wrap"
            role="region"
            aria-label="Evaluation overview"
            tabIndex={0}
          >
            <table aria-label="Workload results">
              <thead>
                <tr>
                  {[
                    "Workload",
                    "Result",
                    "First category matches",
                    "Peak before",
                    "Peak after",
                    "Memory reduction",
                    "Numerics",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows(document.rows).map((row, index) => (
                  <tr key={index}>
                    <th scope="row">{scenarioName(row.scenario_id)}</th>
                    <td>{resultLabel(row)}</td>
                    <td>{value(row.first_cause_matches)}</td>
                    <td>{gb(row.peak_before_bytes)}</td>
                    <td>{gb(row.peak_after_bytes)}</td>
                    <td>
                      {decimal(row.peak_reduction_pct) === null
                        ? "Unknown"
                        : number(row.peak_reduction_pct) + "%"}
                    </td>
                    <td>
                      {numericalResult(row.loss_equivalence)}
                      <small className="table-note">
                        {numericalBasis(row.numerical_basis)}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="caption">
            Token Factory cost of this evaluation:{" "}
            {cost(summary.total_cost_usd)}.
          </p>
          <details className="evaluation-details">
            <summary>Detailed measurements</summary>
            <p className="caption">
              Search mode: {searchModeLabel(document.search_mode)}. Only
              explicitly published evidence appears here. Unknown outcomes
              remain unknown. Throughput is a separate measurement, not inferred
              from step time. Any patch/config applied records a successful
              application attempt, including one later reverted. Selected fields
              describe the final retained configuration. Peak before is the
              baseline; peak after, reductions and timing changes compare that
              baseline with the final selected configuration.
            </p>
            <a
              className="text-link"
              href={"/api/evaluations/" + encodeURIComponent(selected)}
              download
            >
              Download full evaluation data
            </a>
            <div
              className="table-wrap"
              role="region"
              aria-label="Scrollable evaluation results"
              tabIndex={0}
            >
              <table
                className="evaluation-main-table"
                aria-label="Main evaluation results"
              >
                <thead>
                  <tr>
                    {columns.map(([key, label]) => (
                      <th key={key} className={"evaluation-column-" + key}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows(document.rows).map((row, index) => (
                    <tr key={index}>
                      {columns.map(([key]) => (
                        <td key={key} className={"evaluation-column-" + key}>
                          {metric(key, row[key])}
                          {key === "patch_applied" && (
                            <RoundOutcomes row={row} />
                          )}
                          {key === "status" && (
                            <small className="table-note">
                              {searchModeLabel(row.search_mode)} · Stop:{" "}
                              {stopReason(row.search_stop_reason)}
                            </small>
                          )}
                          {key === "loss_equivalence" && (
                            <>
                              <br />
                              <small
                                className="caption"
                                title={
                                  "Comparison scope: " +
                                  value(row.comparison_scope)
                                }
                              >
                                {numericalBasis(row.numerical_basis)}
                              </small>
                            </>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr>
                    {columns.map(([key]) =>
                      key === "scenario_id" ? (
                        <th
                          key={key}
                          scope="row"
                          className={"evaluation-column-" + key}
                        >
                          {summaryCells[key]}
                        </th>
                      ) : (
                        <td key={key} className={"evaluation-column-" + key}>
                          {summaryCells[key] ?? "Unknown"}
                        </td>
                      ),
                    )}
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="caption">
              Averages use the available GPU measurements. Runs that did not
              finish and unknown measurements remain in the table. Offline
              examples excluded from measured results:{" "}
              {value(summary.offline_fixture_rows_excluded)}.
            </p>
            <div className="table-wrap">
              <table aria-label="Evaluation summary">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Measured / comparable</th>
                    <th>Unknown / not comparable</th>
                  </tr>
                </thead>
                <tbody>
                  {summaryRows.map(([label, result, count, unknown]) => (
                    <tr key={String(label)}>
                      <th>{String(label)}</th>
                      <td>{String(result)}</td>
                      <td>{value(count)}</td>
                      <td>{value(unknown)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>Paired diagnosis ablation</h3>
            <p className="caption">
              {text(ablation.aggregation_scope)}. Only matching source hashes,
              effective policies, authored truth and complete three-condition
              groups are compared.
            </p>
            <div className="table-wrap">
              <table aria-label="Paired ablation summary">
                <thead>
                  <tr>
                    <th>Condition</th>
                    <th>Correct first causes</th>
                    <th>Comparable pairs</th>
                    <th>Accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {conditions.map((condition) => (
                    <tr key={condition}>
                      <th>{conditionName(condition)}</th>
                      <td>
                        {
                          pairs.filter(
                            (pair) => record(pair.correct)[condition] === true,
                          ).length
                        }
                      </td>
                      <td>{value(ablation.paired_scored_count)}</td>
                      <td>{percent(record(ablation.accuracy)[condition])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-wrap">
              <table aria-label="Paired ablation evidence">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Policy</th>
                    {conditions.map((condition) => (
                      <th key={condition}>{conditionName(condition)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pairs.length ? (
                    pairs.map((pair, index) => (
                      <tr key={index}>
                        <th>{value(pair.scenario_id)}</th>
                        <td>{value(pair.policy_name)}</td>
                        {conditions.map((condition) => (
                          <td key={condition}>
                            {value(record(pair.correct)[condition])}
                          </td>
                        ))}
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5}>No comparable three-condition pairs.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {excluded.length > 0 && (
              <div className="table-wrap">
                <table aria-label="Excluded ablation groups">
                  <thead>
                    <tr>
                      <th>Scenario</th>
                      <th>Policy</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {excluded.map((row, index) => (
                      <tr key={index}>
                        <td>{value(row.scenario_id)}</td>
                        <td>{value(row.policy_name)}</td>
                        <td>{human(row.reason)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
          <h3>Limitations</h3>
          <p className="small-copy">
            A completed attempt can still leave the workload unsolved. Memory
            and timing measurements describe the final selected configuration;
            earlier attempts, including reverted changes, remain in the details.
            Numerical comparisons cover the recorded loss samples shown for each
            workload, not a full training run. Missing results and costs stay
            Unknown.
          </p>
          <p className="small-copy">
            {document.provenance === "offline_fixture"
              ? "This is an offline example; it does not contribute to measured repair results."
              : "The recorded evaluations use a single GPU. They do not establish performance on other hardware or distributed training."}{" "}
            {pairs.length
              ? "Diagnosis comparisons include only matched workloads with comparable evidence and a known cause."
              : "Diagnosis-only measurements are reported separately."}
          </p>
        </>
      )}
    </Section>
  );
}
