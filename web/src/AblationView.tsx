import study from "./ablation-data.json";
import { Badge, Section } from "./components";

const labels: Record<string, { evidence: string; model: string }> = {
  full_ultra: { evidence: "Full evidence", model: "Nemotron 3 Ultra" },
  traceback_ultra: {
    evidence: "Traceback + memory summary",
    model: "Nemotron 3 Ultra",
  },
  full_super: { evidence: "Full evidence", model: "Nemotron 3 Super" },
};

const number = (value: number | null, digits: number) =>
  value === null
    ? "Not recorded"
    : value.toLocaleString("en-US", { maximumFractionDigits: digits });
const cost = (value: string) =>
  "$" +
  Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 8,
  });

export default function AblationView() {
  return (
    <Section
      id="diagnosis-comparison"
      title="Diagnosis with different evidence"
      kicker="One comparison, three conditions"
      action={<Badge>{study.executed_requests} model requests</Badge>}
    >
      <p className="small-copy">
        One request for each of nine workloads in each condition, using saved
        captures. This comparison measures diagnosis; it does not measure
        repairs.
      </p>
      <div className="table-wrap">
        <table
          className="ablation-table"
          aria-label="Diagnosis evidence comparison"
          aria-describedby="ablation-definitions ablation-limits"
        >
          <thead>
            <tr>
              <th scope="col">Evidence / model</th>
              <th scope="col">Requests</th>
              <th scope="col">First-cause matches</th>
              <th scope="col">Valid + correct</th>
              <th scope="col">Mean input tokens</th>
              <th scope="col">Model cost (USD)</th>
              <th scope="col">Mean elapsed</th>
            </tr>
          </thead>
          <tbody>
            {study.conditions.map((row) => (
              <tr key={row.condition}>
                <th scope="row">
                  <strong>{labels[row.condition].evidence}</strong>
                  <small className="table-note">
                    {labels[row.condition].model}
                  </small>
                </th>
                <td>
                  {row.attempted} / {row.denominator}
                </td>
                <td>
                  {row.first_cause_matches} / {row.denominator}
                </td>
                <td>
                  {row.valid_correct_first_causes} / {row.denominator}
                </td>
                <td>{number(row.mean_provider_input_tokens, 0)}</td>
                <td>{cost(row.total_cost_usd)}</td>
                <td>{number(row.mean_latency_seconds, 2)} s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p id="ablation-definitions" className="small-copy ablation-note">
        <strong>First-cause matches</strong> compare the first category parsed
        from strict JSON with the reference cause.{" "}
        <strong>Valid + correct</strong> also requires the complete diagnosis,
        evidence references and policy checks to pass.
      </p>
      <p id="ablation-limits" className="small-copy">
        Two unscored scenarios—variable-length batches and nanoGPT—stay in every
        denominator of nine because their reference causes are unconfirmed. This
        is one pass without repeated trials. The two full-evidence conditions
        used the same input.
      </p>
      <p className="caption">
        Input means include all nine provider-reported token counts, including
        cached tokens. Elapsed means include the model-router call and local
        validation, rather than time to first token. Displayed means are
        rounded. Costs use the observed token usage and configured prices,
        including cache discounts; tax is excluded. Total model cost:{" "}
        {cost(study.total_cost_usd)}.
      </p>
      <div className="ablation-sources">
        <a
          className="text-link"
          href={study.report_url}
          target="_blank"
          rel="noreferrer"
        >
          Read the experiment report ↗
        </a>
        <a
          className="text-link"
          href={study.data_url}
          target="_blank"
          rel="noreferrer"
        >
          Inspect the measured data ↗
        </a>
      </div>
    </Section>
  );
}
