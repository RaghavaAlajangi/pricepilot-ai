import { formatEur, formatInt } from "@/lib/format";
import type { ProductSummary } from "@/lib/types";

interface KpiProps {
  label: string;
  value: string;
}

function Kpi({ label, value }: KpiProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
    </div>
  );
}

export default function KpiCards({ summary }: { summary: ProductSummary }) {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
      <Kpi label="Current price" value={formatEur(summary.current_price)} />
      <Kpi label="Unit cost" value={formatEur(summary.unit_cost)} />
      <Kpi label="Units sold (2y)" value={formatInt(summary.total_units)} />
      <Kpi label="Revenue (2y)" value={formatEur(summary.total_revenue)} />
      <Kpi label="Avg units / week" value={formatInt(summary.avg_weekly_units)} />
    </div>
  );
}
