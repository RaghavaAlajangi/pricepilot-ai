import { formatEur } from "@/lib/format";
import type { ElasticityResult } from "@/lib/types";
import ProfitCurveChart from "./charts/ProfitCurveChart";

const CONFIDENCE_STYLE: Record<ElasticityResult["confidence"], string> = {
  high: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-red-100 text-red-800",
};

interface StatProps {
  label: string;
  value: string;
  hint?: string;
}

function Stat({ label, value, hint }: StatProps) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-stone-500">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
      {hint && <p className="text-xs text-stone-500">{hint}</p>}
    </div>
  );
}

/** ML results: elasticity stats on the left, profit curve on the right. */
export default function ElasticitySection({ result }: { result: ElasticityResult }) {
  const profitLift = result.profit_at_recommended - result.profit_at_current;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-lg border border-stone-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Price-demand model</h2>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONFIDENCE_STYLE[result.confidence]}`}
          >
            {result.confidence} confidence
          </span>
        </div>
        <p className="mb-4 mt-1 text-xs text-stone-500">
          Log-log regression on {result.n_weeks} weeks of sales
        </p>
        <div className="grid grid-cols-2 gap-4">
          <Stat
            label="Price elasticity"
            value={result.elasticity.toFixed(2)}
            hint={`a 1% price increase changes sales by ~${result.elasticity.toFixed(1)}%`}
          />
          <Stat label="Model fit (R²)" value={result.r_squared.toFixed(2)} />
          <Stat
            label="Recommended price"
            value={formatEur(result.recommended_price)}
            hint={`current: ${formatEur(result.current_price)}`}
          />
          <Stat
            label="Est. weekly profit lift"
            value={`${profitLift >= 0 ? "+" : ""}${formatEur(profitLift)}`}
            hint="vs. staying at the current price"
          />
        </div>
        {result.warnings.length > 0 && (
          <ul className="mt-4 space-y-1 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            {result.warnings.map((warning) => (
              <li key={warning}>&#9888; {warning}</li>
            ))}
          </ul>
        )}
      </section>
      <ProfitCurveChart result={result} />
    </div>
  );
}
