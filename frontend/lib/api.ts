/** Typed API client — the only place the frontend talks to the backend. */
import type {
  AgentAnalysisResponse,
  ElasticityResult,
  Market,
  ProductInfo,
  ProductSummary,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId, market }),
  });
}
