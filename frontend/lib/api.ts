/** Typed API client — the only place the frontend talks to the backend. */
import type {
  AgentAnalysisResponse,
  AgentStreamEvent,
  ElasticityResult,
  Market,
  ProductInfo,
  ProductSummary,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const APP_API_KEY = process.env.NEXT_PUBLIC_APP_API_KEY || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", headers.get("Content-Type") ?? "application/json");
  if (APP_API_KEY) headers.set("X-API-Key", APP_API_KEY);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function fetchProducts(): Promise<ProductInfo[]> {
  return request<ProductInfo[]>("/api/v1/products");
}

export function fetchSummary(
  productId: string,
  market: Market,
): Promise<ProductSummary> {
  return request<ProductSummary>(
    `/api/v1/products/${productId}/summary?market=${market}`,
  );
}

export function fetchElasticity(
  productId: string,
  market: Market,
): Promise<ElasticityResult> {
  return request<ElasticityResult>(
    `/api/v1/products/${productId}/elasticity?market=${market}`,
  );
}

export function runAgentAnalysis(
  productId: string,
  market: Market,
): Promise<AgentAnalysisResponse> {
  return request<AgentAnalysisResponse>("/api/v1/agents/analyze", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, market }),
  });
}

/**
 * Streaming variant of {@link runAgentAnalysis}: parses the SSE stream,
 * invokes `onEvent` per step event and resolves with the final result.
 * Falls back to the non-streaming endpoint if the transport yields no
 * usable stream (e.g. a buffering proxy).
 */
export async function runAgentAnalysisStream(
  productId: string,
  market: Market,
  onEvent: (event: AgentStreamEvent) => void,
): Promise<AgentAnalysisResponse> {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (APP_API_KEY) (headers as Record<string, string>)["X-API-Key"] = APP_API_KEY;
  const response = await fetch(`${API_BASE}/api/v1/agents/analyze/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ product_id: productId, market }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  if (!response.body) {
    return runAgentAnalysis(productId, market);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AgentAnalysisResponse | null = null;

  const handleChunk = (chunk: string): void => {
    const line = chunk.split("\n").find((l) => l.startsWith("data: "));
    if (!line) return;
    const event = JSON.parse(line.slice(6)) as AgentStreamEvent;
    if (event.event === "error") throw new Error(event.detail);
    if (event.event === "result") result = event.data;
    onEvent(event);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      handleChunk(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
  if (!result) {
    throw new Error("The analysis stream ended without a result.");
  }
  return result;
}
