import type { PerfStats } from "@/lib/types";

interface PerfStripProps {
  /** Timings reported by the summary endpoint (data fetch + aggregation). */
  summaryPerf: PerfStats | null;
  /** Timings reported by the elasticity endpoint (ML inference). */
  elasticityPerf: PerfStats | null;
  /** Client-measured round-trip for the two dashboard requests. */
  roundTripMs: number | null;
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-surface px-2.5 py-1 text-xs">
      <span className="text-ink-muted">{label}</span>
      <span className="font-medium text-ink-secondary">{value}</span>
    </span>
  );
}

/** Observability strip: where the time goes for the charts on screen. */
export default function PerfStrip({
  summaryPerf,
  elasticityPerf,
  roundTripMs,
}: PerfStripProps) {
  const perf = elasticityPerf ?? summaryPerf;
  if (!perf) return null;
  const dataFetchMs =
    (summaryPerf?.data_fetch_ms ?? 0) + (elasticityPerf?.data_fetch_ms ?? 0);
  return (
    <div className="flex flex-wrap items-center gap-2" title="Server-side timings reported per request">
      <Chip
        label="dataset"
        value={perf.backend === "in-memory" ? "in-memory (no DB)" : "postgres"}
      />
      <Chip label="data fetch" value={`${dataFetchMs.toFixed(1)} ms`} />
      {summaryPerf && (
        <Chip label="aggregation" value={`${summaryPerf.compute_ms.toFixed(1)} ms`} />
      )}
      {elasticityPerf && (
        <Chip
          label="ML inference"
          value={`${elasticityPerf.compute_ms.toFixed(1)} ms`}
        />
      )}
      {roundTripMs !== null && (
        <Chip label="round-trip" value={`${Math.round(roundTripMs)} ms`} />
      )}
    </div>
  );
}
