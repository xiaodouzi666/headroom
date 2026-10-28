import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import AblationView from "./AblationView";
import study from "./ablation-data.json";

afterEach(cleanup);

describe("published diagnosis comparison", () => {
  it("keeps the published measurements and source fingerprint intact", () => {
    const bytes = readFileSync(
      resolve(process.cwd(), "../reports/ablation-20261028/ablation.json"),
    );
    const source = JSON.parse(bytes.toString());
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      study.source_sha256,
    );
    expect(source.completed_all_requests).toBe(true);
    expect(study.executed_requests).toBe(source.executed_requests);
    expect(study.total_cost_usd).toBe(source.total_cost_usd);
    expect(study.conditions).toHaveLength(3);
    for (const row of study.conditions) {
      const original = source.conditions.find(
        (value: { condition: string }) => value.condition === row.condition,
      );
      for (const [field, value] of Object.entries(row)) {
        expect(original[field]).toEqual(value);
      }
      expect(row.denominator).toBe(9);
      expect(row.attempted).toBe(9);
      expect(row.unscored_truths).toBe(2);
    }
  });

  it("shows category matches separately from complete valid diagnoses", () => {
    render(<AblationView />);
    const table = screen.getByRole("table", {
      name: "Diagnosis evidence comparison",
    });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      ["9 / 9", "6 / 9", "4 / 9", "46,496", "$0.46426", "8.5 s"],
      ["9 / 9", "2 / 9", "2 / 9", "11,009", "$0.09866092", "4.69 s"],
      ["9 / 9", "6 / 9", "4 / 9", "46,496", "$0.1308225", "5.68 s"],
    ]);
    expect(screen.getByText(/does not measure repairs/)).toBeInTheDocument();
    expect(screen.getByText(/Two unscored scenarios/)).toHaveTextContent(
      /stay in every denominator of nine/,
    );
    expect(screen.getByText(/Elapsed means/)).toHaveTextContent(
      /local validation, rather than time to first token/,
    );
    expect(screen.getByText(/Total model cost/)).toHaveTextContent(
      "$0.69374342",
    );
    expect(
      screen.getByRole("link", { name: /Read the experiment report/ }),
    ).toHaveAttribute(
      "href",
      "https://github.com/xiaodouzi666/headroom/blob/main/reports/ablation-20261028/README.md",
    );
    expect(
      screen.getByRole("link", { name: /Inspect the measured data/ }),
    ).toHaveAttribute(
      "href",
      "https://github.com/xiaodouzi666/headroom/blob/main/reports/ablation-20261028/ablation.json",
    );
  });
});
