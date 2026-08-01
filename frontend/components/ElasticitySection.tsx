import { formatEur } from "@/lib/format";
import type { ElasticityResult } from "@/lib/types";
import ProfitCurveChart from "./charts/ProfitCurveChart";

const CONFIDENCE_STYLE: Record<ElasticityResult["confidence"], string> = {
  high: "bg-status-good/15 text-green-400",
  medium: "bg-status-warning/15 text-amber-300",
  low: "bg-status-critical/15 text-red-400",
};

interface StatProps {
  label: string;
  value: string;
  hint?: string;
}

function Stat({ label, value, hint }: StatProps) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="text-lg font-semibold text-ink">{value}</p>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

/** ML results: elasticity stats on the left, profit curve on the right. */
export default function ElasticitySection({ result }: { result: ElasticityResult }) {
  const profitLift = result.profit_at_recommended - result.profit_at_current;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-xl border border-white/10 bg-surface p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Price-demand model</h2>
          <div className="flex items-center gap-2">
            {result.perf && (
              <span
                className="rounded-full border border-white/10 px-2 py-0.5 text-xs text-ink-muted"
                title="Server-side model inference time for this request"
              >
                inference {result.perf.compute_ms.toFixed(1)} ms
              </span>
            )}
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${CONFIDENCE_STYLE[result.confidence]}`}
            >
              {result.confidence} confidence
            </span>
          </div>
        </div>
        <p className="mb-4 mt-1 text-xs text-ink-muted">
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
          <ul className="mt-4 space-y-1 rounded-md border border-status-warning/30 bg-status-warning/10 p-3 text-xs text-amber-200">
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
