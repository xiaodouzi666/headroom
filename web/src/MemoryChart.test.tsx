import { cloneElement, type ReactElement } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import MemoryChart from "./MemoryChart";

vi.mock("recharts", async (original) => ({
  ...(await original<typeof import("recharts")>()),
  ResponsiveContainer: ({ children }: { children: ReactElement }) =>
    cloneElement(children, { width: 640, height: 280 } as object),
}));
afterEach(cleanup);
const measured = {
  timeline: [
    { event_index: 1, allocated_bytes: 1e9 },
    { event_index: 2, allocated_bytes: 2e9 },
  ],
};
it("baseline record cannot present an After series even with stray after data", () => {
  render(<MemoryChart before={measured} after={measured} baselineOnly />);
  expect(screen.getByText("Baseline")).toBeInTheDocument();
  expect(screen.queryByText("After")).not.toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAccessibleName(/memory: Baseline,/);
});
it("a single unverified capture does not advertise an After series", () => {
  render(<MemoryChart before={measured} after={{}} />);
  expect(screen.getByText("Before")).toBeInTheDocument();
  expect(screen.queryByText("After")).not.toBeInTheDocument();
});
it("two measured captures retain both series", () => {
  render(<MemoryChart before={measured} after={measured} />);
  expect(screen.getByText("Before")).toBeInTheDocument();
  expect(screen.getByText("After")).toBeInTheDocument();
});
