import {
  ResponsiveContainer,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Line,
  Legend,
  ReferenceDot,
} from "recharts";
import { timelinePoints, rows, numeric, type Dict } from "./data";
import { Empty } from "./components";
import { theme } from "./theme";
export default function MemoryChart({
  before,
  after,
  baselineOnly = false,
}: {
  before: Dict;
  after: Dict;
  baselineOnly?: boolean;
}) {
  const data = timelinePoints(before, baselineOnly ? {} : after);
  const hasBefore = data.some((point) => point.before !== null);
  const hasAfter = data.some((point) => point.after !== null);
  const beforeLabel = baselineOnly ? "Baseline" : "Before";
  const seriesLabel = [
    hasBefore ? beforeLabel : null,
    hasAfter ? "After" : null,
  ]
    .filter(Boolean)
    .join(" and ");
  if (!data.length)
    return (
      <Empty title="No memory trace yet">
        A chart appears when a capture is available. Missing measurements stay
        unknown.
      </Empty>
    );
  const ooms = rows(before.timeline).filter(
    (r) =>
      r.is_oom === true &&
      numeric(r.event_index) !== null &&
      numeric(r.allocated_bytes) !== null,
  );
  return (
    <>
      <div
        className="chart"
        role="img"
        aria-label={`Measured allocated GPU memory: ${seriesLabel}, indexed by allocator event`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 14, right: 22, bottom: 12, left: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 4"
              vertical={false}
              stroke={theme.border}
            />
            <XAxis
              dataKey="event"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 11, fill: theme.muted }}
              tickLine={false}
              axisLine={false}
              minTickGap={45}
            />
            <YAxis
              unit=" GB"
              width={64}
              tick={{ fontSize: 11, fill: theme.muted }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              formatter={(value: unknown) =>
                typeof value === "number" ? `${value.toFixed(3)} GB` : "Unknown"
              }
              labelFormatter={(label) => `Allocator event ${label}`}
              contentStyle={{
                borderRadius: 12,
                borderColor: theme.border,
                fontSize: 12,
              }}
            />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
            {hasBefore && (
              <Line
                dataKey="before"
                name={beforeLabel}
                type="linear"
                stroke={theme.before}
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            )}
            {hasAfter && (
              <Line
                dataKey="after"
                name="After"
                type="linear"
                stroke={theme.after}
                strokeWidth={2.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            )}
            {ooms.map((row) => (
              <ReferenceDot
                key={Number(row.event_index)}
                x={Number(row.event_index)}
                y={Number(row.allocated_bytes) / 1e9}
                r={4}
                fill="#b95340"
                stroke="white"
                label={{
                  value: "OOM",
                  position: "insideTopRight",
                  fontSize: 10,
                  fill: "#b95340",
                }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="caption">
        Allocated memory · sampled allocator events
        {hasBefore && hasAfter
          ? " · independent captures."
          : " · one recorded capture."}
        Lines join recorded points; event indices do not represent elapsed time.
      </p>
    </>
  );
}
