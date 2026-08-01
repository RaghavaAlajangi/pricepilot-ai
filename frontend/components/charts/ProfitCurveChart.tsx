"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, TOOLTIP_STYLE } from "@/lib/colors";
import type { ElasticityResult } from "@/lib/types";
import ChartCard from "./ChartCard";

const AXIS_STYLE = { fontSize: 11, fill: CHART_COLORS.muted };

/** Model-predicted weekly profit at each candidate price. */
export default function ProfitCurveChart({ result }: { result: ElasticityResult }) {
  return (
    <ChartCard
      title="Where profit peaks"
      subtitle="Predicted weekly profit at each price (within the range we actually tested)"
    >
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={result.curve} margin={{ top: 24, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
          <XAxis
            type="number"
            dataKey="price"
            unit="€"
            domain={[result.min_observed_price, result.max_observed_price]}
            tick={AXIS_STYLE}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <YAxis tick={AXIS_STYLE} width={56} tickFormatter={(v: number) => v.toFixed(0)} unit="€" />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(value: number) => [`${value.toFixed(2)} €`, "Weekly profit"]}
            labelFormatter={(price: number) => `Price ${price.toFixed(2)} €`}
          />
          <ReferenceLine
            x={result.current_price}
            stroke={CHART_COLORS.muted}
            strokeDasharray="4 4"
            label={{ value: "current", position: "top", fontSize: 11, fill: CHART_COLORS.muted }}
          />
          <ReferenceLine
            x={result.recommended_price}
            stroke={CHART_COLORS.good}
            label={{ value: "recommended", position: "top", fontSize: 11, fill: CHART_COLORS.good }}
          />
          <Line
            type="monotone"
            dataKey="predicted_weekly_profit"
            stroke={CHART_COLORS.price}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
