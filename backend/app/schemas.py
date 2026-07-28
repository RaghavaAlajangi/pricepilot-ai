"""All Pydantic models: API request/response shapes and agent output
schemas."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Market = Literal["DE", "FR", "CH"]


# catalogue -------------------------------------------------------------------
class ProductInfo(BaseModel):
    product_id: str
    product_name: str
    category: str
    brand: str
    markets: list[str]


# summary / charts ------------------------------------------------------------
class WeeklyPoint(BaseModel):
    """One week of sales for a product in a market (chart-ready)."""

    week: date
    avg_price: float
    units: int
    revenue: float
    sessions: int


class ProductSummary(BaseModel):
    product_id: str
    product_name: str
    category: str
    brand: str
    market: Market
    current_price: float
    unit_cost: float
    total_units: int
    total_revenue: float
    avg_weekly_units: float
    weekly: list[WeeklyPoint]


# ML result ------------------------------------------------------------------
class CurvePoint(BaseModel):
    """Model prediction at one candidate price."""

    price: float
    predicted_weekly_units: float
    predicted_weekly_profit: float


class ElasticityResult(BaseModel):
    product_id: str
    market: Market
    elasticity: float = Field(
        description="% change in demand per 1% price change"
    )
    r_squared: float
    n_weeks: int
    current_price: float
    unit_cost: float
    min_observed_price: float
    max_observed_price: float
    recommended_price: float
    profit_at_recommended: float
    profit_at_current: float
    confidence: Literal["high", "medium", "low"]
    warnings: list[str]
    curve: list[CurvePoint]


# agents ----------------------------------------------------------------------
class AgentAnalysisRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=20, pattern=r"^SKU-\d+$")
    market: Market


class AnalystFindings(BaseModel):
    """Output of the Data Analyst agent."""

    summary: str = Field(description="2-3 sentence plain-language summary")
    findings: list[str] = Field(
        description="3-5 bullet findings, each citing numbers from the input"
    )
    data_quality_notes: list[str] = Field(
        description="Caveats about model fit or data coverage"
    )


class StrategistRecommendation(BaseModel):
    """Output of the Pricing Strategist agent."""

    recommended_price_eur: float = Field(gt=0)
    rationale: str
    expected_impact: str
    risks: list[str]


class ReviewerVerdict(BaseModel):
    """Output of the Risk Reviewer agent."""

    verdict: Literal["approve", "revise", "reject"]
    checks_performed: list[str] = Field(
        description=(
            "List of individual checks performed, one string per check."
        )
    )
    concerns: list[str] = Field(
        description="List of specific concerns found. Empty list if none."
    )


class GuardrailReport(BaseModel):
    """Code-level validation of the strategist's recommendation."""

    passed: bool
    violations: list[str]


class AgentAnalysisResponse(BaseModel):
    product_id: str
    market: Market
    analyst: AnalystFindings
    strategist: StrategistRecommendation
    reviewer: ReviewerVerdict
    guardrail: GuardrailReport
    model: str
    cached: bool


# misc ------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
