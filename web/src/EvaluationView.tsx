import { useEffect, useState } from "react";
import { getJSON } from "./api";
import {
  record,
  rows,
  text,
  decimal,
  gb,
  usd,
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
  ["cost_usd", "Cost USD"],
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
const numericalBasis = (basis: unknown) =>
  (
    ({
      original_plan_first_five_backward_scalars:
        "Observed first five backward losses (original plan)",
      original_plan_full_backward_scalar_series:
        "Observed full backward-loss sequence (original plan)",
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
          ? usd(v)
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
      ].map((key) => [key, value(record(measured[key]).mean)]),
    ),
    loss_equivalence: `${value(comparable.equivalent)}/${value(comparable.comparable_count)} comparable`,
    rounds: value(record(measured.rounds).mean),
    cost_usd: usd(summary.total_cost_usd),
    wall_seconds: value(record(measured.wall_seconds).mean),
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
        human(key) + " mean",
        value(m.mean),
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
      kicker="Main campaign and paired ablation"
    >
      {error && <Notice tone="red">{error}</Notice>}
      {catalog.length > 0 && (
        <label>
          Evaluation campaign{" "}
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            {catalog.map((item) => (
              <option key={String(item.id)} value={String(item.id)}>
                {text(item.title)}
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
            No campaign has been selected for public display. This does not
            imply a completed repair benchmark.
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
          <p className="caption">
            Search mode: {searchModeLabel(document.search_mode)}. Only
            explicitly published evidence appears here. Unknown outcomes remain
            unknown. Throughput is a separate measurement, not inferred from
            step time. Any patch/config applied records a successful application
            attempt, including one later reverted. Selected fields describe the
            final retained configuration. Peak before is the baseline; peak
            after, reductions and timing changes compare that baseline with the
            final selected configuration.
          </p>
          <a
            className="text-link"
            href={"/api/evaluations/" + encodeURIComponent(selected)}
            download
          >
            Download published evaluation JSON
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
                        {key === "patch_applied" && <RoundOutcomes row={row} />}
                        {key === "status" && (
                          <small className="table-note">
                            {searchModeLabel(row.search_mode)} · Stop:{" "}
                            {human(row.search_stop_reason)}
                          </small>
                        )}
                        {key === "loss_equivalence" && (
                          <>
                            <br />
                            <small
                              className="caption"
                              title={
                                "Acceptance scope: " +
                                value(row.acceptance_scope)
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
            The summary row uses measured live rows only; reductions, timings
            and rounds are means over available measurements. Applied and
            completed counts are recorded facts, not additional acceptance
            rates. Fixture rows excluded:{" "}
            {value(summary.offline_fixture_rows_excluded)}. Known cost subtotal:{" "}
            {usd(summary.known_cost_usd)}; total: {usd(summary.total_cost_usd)}.
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
                    <th>{condition}</th>
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
                    <th key={condition}>{condition}</th>
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
          <h3>What this evidence supports</h3>
          {Array.isArray(document.conclusions) &&
            document.conclusions.map((line, index) => (
              <p key={index} className="small-copy">
                {String(line)}
              </p>
            ))}
        </>
      )}
    </Section>
  );
}
