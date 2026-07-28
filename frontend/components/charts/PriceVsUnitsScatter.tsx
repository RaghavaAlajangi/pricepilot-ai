"use client";

import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "@/lib/colors";
import type { WeeklyPoint } from "@/lib/types";
import ChartCard from "./ChartCard";

const AXIS_STYLE = { fontSize: 11, fill: CHART_COLORS.muted };

/** Each dot is one week: does a lower price come with higher sales? */
export default function PriceVsUnitsScatter({ weekly }: { weekly: WeeklyPoint[] }) {
  return (
    <ChartCard
      title="Price vs. demand"
      subtitle="One dot per week — the downward drift is the price-demand relationship"
    >
      <ResponsiveContainer width="100%" height={296}>
        <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={CHART_COLORS.grid} />
          <XAxis
            type="number"
            dataKey="avg_price"
            name="Avg price"
            unit="€"
            domain={["auto", "auto"]}
            tick={AXIS_STYLE}
          />
          <YAxis type="number" dataKey="units" name="Units sold" tick={AXIS_STYLE} width={44} />
          <Tooltip
            cursor={{ strokeDasharray: "4 4" }}
            formatter={(value: number, name: string) =>
              name === "Avg price" ? `${value.toFixed(2)} €` : value
            }
          />
          <Scatter data={weekly} fill={CHART_COLORS.scatter} fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
