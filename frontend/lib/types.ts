/** TypeScript mirrors of the backend Pydantic schemas. */

export type Market = "DE" | "FR" | "CH";

export interface ProductInfo {
  product_id: string;
  product_name: string;
  category: string;
  brand: string;
  markets: string[];
}

export interface WeeklyPoint {
  week: string;
  avg_price: number;
  units: number;
  revenue: number;
  sessions: number;
}

export interface ProductSummary {
  product_id: string;
  product_name: string;
  category: string;
  brand: string;
  market: Market;
  current_price: number;
  unit_cost: number;
  total_units: number;
  total_revenue: number;
  avg_weekly_units: number;
  weekly: WeeklyPoint[];
}

export interface CurvePoint {
  price: number;
  predicted_weekly_units: number;
  predicted_weekly_profit: number;
}

export interface ElasticityResult {
  product_id: string;
  market: Market;
  elasticity: number;
  r_squared: number;
  n_weeks: number;
  current_price: number;
  unit_cost: number;
  min_observed_price: number;
  max_observed_price: number;
  recommended_price: number;
  profit_at_recommended: number;
  profit_at_current: number;
  confidence: "high" | "medium" | "low";
  warnings: string[];
  curve: CurvePoint[];
}

export interface AnalystFindings {
  summary: string;
  findings: string[];
  data_quality_notes: string[];
}

export interface StrategistRecommendation {
  recommended_price_eur: number;
  rationale: string;
  expected_impact: string;
  risks: string[];
}

export interface ReviewerVerdict {
  verdict: "approve" | "revise" | "reject";
  checks_performed: string[];
  concerns: string[];
}

export interface GuardrailReport {
  passed: boolean;
  violations: string[];
}

export interface AgentAnalysisResponse {
  product_id: string;
  market: Market;
  analyst: AnalystFindings;
  strategist: StrategistRecommendation;
  reviewer: ReviewerVerdict;
  guardrail: GuardrailReport;
  model: string;
  cached: boolean;
}
