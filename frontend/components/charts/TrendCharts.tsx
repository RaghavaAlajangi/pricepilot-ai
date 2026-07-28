"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "@/lib/colors";
import type { WeeklyPoint } from "@/lib/types";
import ChartCard from "./ChartCard";

const AXIS_STYLE = { fontSize: 11, fill: CHART_COLORS.muted };

function formatWeek(week: string): string {
  return week.slice(0, 7); // YYYY-MM
}

/**
 * Price and demand over time as two stacked single-axis charts
 * (deliberately not one dual-axis chart — different units don't share a scale).
 */
export default function TrendCharts({ weekly }: { weekly: WeeklyPoint[] }) {
  return (
    <ChartCard
      title="Weekly price & demand over time"
      subtitle="Average selling price (top) and units sold (bottom) per week"
    >
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={weekly} syncId="trend">
          <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
          <XAxis dataKey="week" tickFormatter={formatWeek} tick={AXIS_STYLE} minTickGap={40} />
          <YAxis tick={AXIS_STYLE} width={44} domain={["auto", "auto"]} unit="€" />
          <Tooltip formatter={(v: number) => `${v.toFixed(2)} €`} />
          <Line
            type="monotone"
            dataKey="avg_price"
            name="Avg price"
            stroke={CHART_COLORS.price}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={weekly} syncId="trend">
          <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
          <XAxis dataKey="week" tickFormatter={formatWeek} tick={AXIS_STYLE} minTickGap={40} />
          <YAxis tick={AXIS_STYLE} width={44} />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="units"
            name="Units sold"
            stroke={CHART_COLORS.units}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
