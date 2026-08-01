"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchElasticity, fetchProducts, fetchSummary } from "@/lib/api";
import type {
  ElasticityResult,
  Market,
  ProductInfo,
  ProductSummary,
} from "@/lib/types";
import AgentPanel from "./AgentPanel";
import ElasticitySection from "./ElasticitySection";
import KpiCards from "./KpiCards";
import PerfStrip from "./PerfStrip";
import PriceVsUnitsScatter from "./charts/PriceVsUnitsScatter";
import TrendCharts from "./charts/TrendCharts";

const MARKETS: Market[] = ["DE", "FR", "CH"];

export default function Dashboard() {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [productId, setProductId] = useState<string>("");
  const [market, setMarket] = useState<Market>("DE");
  const [summary, setSummary] = useState<ProductSummary | null>(null);
  const [elasticity, setElasticity] = useState<ElasticityResult | null>(null);
  const [roundTripMs, setRoundTripMs] = useState<number | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchProducts()
      .then((list) => {
        setProducts(list);
        if (list.length > 0) setProductId(list[0].product_id);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const loadData = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    setError("");
    const started = performance.now();
    try {
      const [summaryData, elasticityData] = await Promise.all([
        fetchSummary(productId, market),
        fetchElasticity(productId, market),
      ]);
      setSummary(summaryData);
      setElasticity(elasticityData);
      setRoundTripMs(performance.now() - started);
    } catch (e) {
      setError((e as Error).message);
      setSummary(null);
      setElasticity(null);
      setRoundTripMs(null);
    } finally {
      setLoading(false);
    }
  }, [productId, market]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="relative space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-xl border border-white/10 bg-surface p-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-sm font-medium text-ink-secondary">
            Product
            <select
              className="mt-1 w-80 rounded-md border border-white/10 bg-raised px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
            >
              {products.map((p) => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_name} ({p.category})
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-col text-sm font-medium text-ink-secondary">
            Market
            <div className="mt-1 inline-flex overflow-hidden rounded-md border border-white/10">
              {MARKETS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMarket(m)}
                  className={`px-4 py-2 text-sm font-medium transition-colors ${
                    market === m
                      ? "bg-accent text-white"
                      : "bg-raised text-ink-secondary hover:text-ink"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          {loading && (
            <span className="flex items-center gap-2 pb-2 text-sm text-ink-muted">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/20 border-t-accent" />
              Loading…
            </span>
          )}
        </div>
        <PerfStrip
          summaryPerf={summary?.perf ?? null}
          elasticityPerf={elasticity?.perf ?? null}
          roundTripMs={roundTripMs}
        />
      </div>

      {error && (
        <div className="rounded-md border border-status-critical/40 bg-status-critical/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {summary && (
        <>
          <KpiCards summary={summary} />
          <div className="grid gap-6 lg:grid-cols-2">
            <TrendCharts weekly={summary.weekly} />
            <PriceVsUnitsScatter weekly={summary.weekly} />
          </div>
        </>
      )}

      {elasticity && <ElasticitySection result={elasticity} />}

      {productId && <AgentPanel productId={productId} market={market} />}
    </div>
  );
}
