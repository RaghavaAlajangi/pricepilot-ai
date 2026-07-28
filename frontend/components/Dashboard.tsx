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
import PriceVsUnitsScatter from "./charts/PriceVsUnitsScatter";
import TrendCharts from "./charts/TrendCharts";

const MARKETS: Market[] = ["DE", "FR", "CH"];

export default function Dashboard() {
  const [products, setProducts] = useState<ProductInfo[]>([]);
  const [productId, setProductId] = useState<string>("");
  const [market, setMarket] = useState<Market>("DE");
  const [summary, setSummary] = useState<ProductSummary | null>(null);
  const [elasticity, setElasticity] = useState<ElasticityResult | null>(null);
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
    try {
      const [summaryData, elasticityData] = await Promise.all([
        fetchSummary(productId, market),
        fetchElasticity(productId, market),
      ]);
      setSummary(summaryData);
      setElasticity(elasticityData);
    } catch (e) {
      setError((e as Error).message);
      setSummary(null);
      setElasticity(null);
    } finally {
      setLoading(false);
    }
  }, [productId, market]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col text-sm font-medium">
          Product
          <select
            className="mt-1 w-80 rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
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
        <label className="flex flex-col text-sm font-medium">
          Market
          <select
            className="mt-1 w-24 rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
          >
            {MARKETS.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        {loading && <span className="pb-2 text-sm text-stone-400">Loading…</span>}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
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
