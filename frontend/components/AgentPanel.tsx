"use client";

import { useEffect, useState } from "react";
import { runAgentAnalysisStream } from "@/lib/api";
import { formatEur, formatInt } from "@/lib/format";
import type {
  AgentAnalysisResponse,
  AgentName,
  AgentStepStats,
  Market,
} from "@/lib/types";

const VERDICT_STYLE: Record<string, string> = {
  approve: "bg-status-good/15 text-green-400",
  revise: "bg-status-warning/15 text-amber-300",
  reject: "bg-status-critical/15 text-red-400",
};

const AGENTS: { name: AgentName; role: string; task: string }[] = [
  { name: "analyst", role: "Data Analyst", task: "reads the model output" },
  { name: "strategist", role: "Pricing Strategist", task: "proposes a price" },
  { name: "reviewer", role: "Risk Reviewer", task: "audits the proposal" },
];

type StepStatus = "pending" | "running" | "done";

interface StepState {
  status: StepStatus;
  stats: AgentStepStats | null;
}

const IDLE_STEPS: Record<AgentName, StepState> = {
  analyst: { status: "pending", stats: null },
  strategist: { status: "pending", stats: null },
  reviewer: { status: "pending", stats: null },
};

function StepBadge({ status, index }: { status: StepStatus; index: number }) {
  if (status === "done") {
    return (
      <span className="flex h-8 w-8 items-center justify-center rounded-full border border-status-good/50 bg-status-good/15 text-sm text-green-400">
        &#10003;
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="relative flex h-8 w-8 items-center justify-center rounded-full border border-accent bg-accent/10 text-sm font-medium text-accent">
        <span className="absolute inset-0 animate-ping rounded-full border border-accent/40" />
        {index + 1}
      </span>
    );
  }
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 text-sm text-ink-muted">
      {index + 1}
    </span>
  );
}

/** Live pipeline view: one entry per agent with latency + token usage. */
function StepTimeline({ steps }: { steps: Record<AgentName, StepState> }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-3">
      {AGENTS.map(({ name, role, task }, index) => {
        const { status, stats } = steps[name];
        return (
          <li
            key={name}
            className={`flex items-center gap-3 rounded-xl border p-3 transition-colors ${
              status === "running"
                ? "border-accent/50 bg-accent/5"
                : "border-white/10 bg-surface"
            }`}
          >
            <StepBadge status={status} index={index} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">{role}</p>
              <p className="truncate text-xs text-ink-muted">
                {status === "running" && "thinking…"}
                {status === "pending" && task}
                {status === "done" &&
                  stats &&
                  `${(stats.latency_ms / 1000).toFixed(1)} s · ${formatInt(
                    stats.input_tokens + stats.output_tokens,
                  )} tokens`}
                {status === "done" && !stats && "done"}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function TelemetryChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-surface px-2.5 py-1 text-xs">
      <span className="text-ink-muted">{label}</span>
      <span className="font-medium text-ink-secondary">{value}</span>
    </span>
  );
}

interface AgentCardProps {
  role: string;
  children: React.ReactNode;
}

function AgentCard({ role, children }: AgentCardProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-surface p-4">
      <h3 className="mb-2 text-sm font-semibold text-ink">{role}</h3>
      <div className="space-y-2 text-sm text-ink-secondary">{children}</div>
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

/** Runs the analyst → strategist → reviewer workflow with live progress. */
export default function AgentPanel({
  productId,
  market,
}: {
  productId: string;
  market: Market;
}) {
  const [result, setResult] = useState<AgentAnalysisResponse | null>(null);
  const [steps, setSteps] = useState<Record<AgentName, StepState>>(IDLE_STEPS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // A new product/market selection invalidates the previous analysis.
  useEffect(() => {
    setResult(null);
    setSteps(IDLE_STEPS);
    setError("");
  }, [productId, market]);

  async function handleRun() {
    setLoading(true);
    setError("");
    setResult(null);
    setSteps(IDLE_STEPS);
    try {
      const final = await runAgentAnalysisStream(productId, market, (event) => {
        if (event.event === "step_started") {
          setSteps((prev) => ({
            ...prev,
            [event.agent]: { status: "running", stats: null },
          }));
        } else if (event.event === "step_completed") {
          const stats: AgentStepStats = {
            agent: event.agent,
            latency_ms: event.latency_ms,
            input_tokens: event.input_tokens,
            output_tokens: event.output_tokens,
          };
          setSteps((prev) => ({
            ...prev,
            [stats.agent]: { status: "done", stats },
          }));
        }
      });
      setResult(final);
      // cached responses skip step events — backfill the timeline from the
      // stored telemetry so the panel always shows per-step numbers
      setSteps(() => {
        const done = { ...IDLE_STEPS };
        for (const stats of final.steps) {
          done[stats.agent] = { status: "done", stats };
        }
        return done;
      });
    } catch (e) {
      setError((e as Error).message);
      setSteps(IDLE_STEPS);
    } finally {
      setLoading(false);
    }
  }

  const showTimeline = loading || result !== null;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-ink">AI agent analysis</h2>
        <button
          type="button"
          onClick={handleRun}
          disabled={loading}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-deep disabled:opacity-50"
        >
          {loading ? "Agents working…" : "Run AI analysis"}
        </button>
        {result && (
          <div className="flex flex-wrap items-center gap-2">
            <TelemetryChip label="model" value={result.model} />
            <TelemetryChip
              label="total"
              value={`${(result.total_latency_ms / 1000).toFixed(1)} s`}
            />
            <TelemetryChip
              label="tokens"
              value={formatInt(result.total_tokens)}
            />
            {result.cached && <TelemetryChip label="served from" value="cache" />}
          </div>
        )}
      </div>

      {showTimeline && <StepTimeline steps={steps} />}

      {error && (
        <div className="rounded-md border border-status-critical/40 bg-status-critical/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {result && (
        <>
          {!result.guardrail.passed && (
            <div className="rounded-md border border-status-critical/40 bg-status-critical/10 p-3 text-sm text-red-300">
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
                  <p className="text-xs font-medium text-ink-muted">Data quality</p>
                  <BulletList items={result.analyst.data_quality_notes} />
                </div>
              )}
            </AgentCard>
            <AgentCard role="2 · Pricing Strategist">
              <p className="text-lg font-semibold text-ink">
                {formatEur(result.strategist.recommended_price_eur)}
              </p>
              <p>{result.strategist.rationale}</p>
              <p className="text-xs text-ink-muted">
                {result.strategist.expected_impact}
              </p>
              <div>
                <p className="text-xs font-medium text-ink-muted">Risks</p>
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
                <p className="text-xs font-medium text-ink-muted">
                  Checks performed
                </p>
                <BulletList items={result.reviewer.checks_performed} />
              </div>
              {result.reviewer.concerns.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-ink-muted">Concerns</p>
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
