"""Versioned REST API. Every route has explicit Pydantic request/response
models."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.graph import AgentError
from app.config import get_settings
from app.data_source import DataSource, get_data_source
from app.logging_conf import get_logger
from app.ml.elasticity import InsufficientDataError
from app.schemas import (
    AgentAnalysisRequest,
    AgentAnalysisResponse,
    ElasticityResult,
    Market,
    ProductInfo,
    ProductSummary,
)
from app.services import agent_analysis, pricing
from app.services.pricing import ProductNotFoundError

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

MarketQuery = Query(description="Sales market", pattern="^(DE|FR|CH)$")


@router.get("/products", response_model=list[ProductInfo])
async def get_products(
    source: DataSource = Depends(get_data_source),
) -> list[ProductInfo]:
    """Product catalogue for the dashboard selectors."""
    return pricing.list_products(source)


@router.get("/products/{product_id}/summary", response_model=ProductSummary)
async def get_summary(
    product_id: str,
    market: Market = MarketQuery,
    source: DataSource = Depends(get_data_source),
) -> ProductSummary:
    """KPIs and weekly time series for one product in one market."""
    try:
        return pricing.get_summary(source, product_id, market)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/products/{product_id}/elasticity", response_model=ElasticityResult
)
async def get_elasticity(
    product_id: str,
    market: Market = MarketQuery,
    source: DataSource = Depends(get_data_source),
) -> ElasticityResult:
    """Price-elasticity model results incl. profit curve and recommended
    price."""
    try:
        return pricing.get_elasticity(source, product_id, market)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/agents/analyze", response_model=AgentAnalysisResponse)
async def analyze_with_agents(
    request: AgentAnalysisRequest,  # guardrail: SKU pattern + market enum
    source: DataSource = Depends(get_data_source),
) -> AgentAnalysisResponse:
    """Run the analyst -> strategist -> reviewer agent workflow."""
    if not get_settings().openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Missing OPENAI_API_KEY; agent analysis is unavailable.",
        )
    try:
        return agent_analysis.analyze(
            source, request.product_id, request.market
        )
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AgentError as exc:
        log.error("agent_workflow_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="The AI analysis could not be completed. Please try again "
            "shortly.",
        ) from exc
