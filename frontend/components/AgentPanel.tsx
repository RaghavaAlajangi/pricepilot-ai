"use client";

import { useEffect, useState } from "react";
import { runAgentAnalysis } from "@/lib/api";
import { formatEur } from "@/lib/format";
import type { AgentAnalysisResponse, Market } from "@/lib/types";

const VERDICT_STYLE: Record<string, string> = {
  approve: "bg-green-100 text-green-800",
  revise: "bg-amber-100 text-amber-800",
  reject: "bg-red-100 text-red-800",
};

interface AgentCardProps {
  role: string;
  children: React.ReactNode;
}

function AgentCard({ role, children }: AgentCardProps) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold">{role}</h3>
      <div className="space-y-2 text-sm text-stone-700">{children}</div>
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-xs">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

/** Runs the analyst → strategist → reviewer workflow and renders each role. */
export default function AgentPanel({
  productId,
  market,
}: {
  productId: string;
  market: Market;
}) {
  const [result, setResult] = useState<AgentAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // A new product/market selection invalidates the previous analysis.
  useEffect(() => {
    setResult(null);
    setError("");
  }, [productId, market]);

  async function handleRun() {
    setLoading(true);
    setError("");
    try {
      setResult(await runAgentAnalysis(productId, market));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold">AI agent analysis</h2>
        <button
          type="button"
          onClick={handleRun}
          disabled={loading}
          className="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-50"
        >
          {loading ? "Agents working…" : "Run AI analysis"}
        </button>
        {result?.cached && (
          <span className="text-xs text-stone-400">cached result</span>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {result && (
        <>
          {!result.guardrail.passed && (
            <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
              <p className="font-semibold">
                &#9888; Guardrail check failed — do not act on this recommendation
              </p>
              <BulletList items={result.guardrail.violations} />
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-3">
            <AgentCard role="1 · Data Analyst">
              <p>{result.analyst.summary}</p>
              <BulletList items={result.analyst.findings} />
              {result.analyst.data_quality_notes.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-stone-500">Data quality</p>
                  <BulletList items={result.analyst.data_quality_notes} />
                </div>
              )}
            </AgentCard>
            <AgentCard role="2 · Pricing Strategist">
              <p className="text-lg font-semibold">
                {formatEur(result.strategist.recommended_price_eur)}
              </p>
              <p>{result.strategist.rationale}</p>
              <p className="text-xs text-stone-500">{result.strategist.expected_impact}</p>
              <div>
                <p className="text-xs font-medium text-stone-500">Risks</p>
                <BulletList items={result.strategist.risks} />
              </div>
            </AgentCard>
            <AgentCard role="3 · Risk Reviewer">
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_STYLE[result.reviewer.verdict]}`}
              >
                {result.reviewer.verdict}
              </span>
              <div>
                <p className="text-xs font-medium text-stone-500">Checks performed</p>
                <BulletList items={result.reviewer.checks_performed} />
              </div>
              {result.reviewer.concerns.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-stone-500">Concerns</p>
                  <BulletList items={result.reviewer.concerns} />
                </div>
              )}
            </AgentCard>
          </div>
        </>
      )}
    </section>
  );
}
