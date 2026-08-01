"""Versioned REST API. Every route has explicit Pydantic request/response
models."""

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..agents.llm_client import AgentError
from ..config import get_settings
from ..data_source import DataSource, get_data_source
from ..logging_conf import get_logger
from ..ml.elasticity import InsufficientDataError
from ..schemas import (
    AgentAnalysisRequest,
    AgentAnalysisResponse,
    ElasticityResult,
    Market,
    ProductInfo,
    ProductSummary,
)
from ..services import agent_analysis, pricing
from ..services.pricing import ProductNotFoundError
from .deps import verify_api_key

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


@router.get("/products/{product_id}/elasticity", response_model=ElasticityResult)
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


def _require_llm_configured() -> None:
    if not get_settings().openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Missing OPENAI_API_KEY; agent analysis is unavailable.",
        )


@router.post("/agents/analyze", response_model=AgentAnalysisResponse)
async def analyze_with_agents(
    request: AgentAnalysisRequest,  # guardrail: SKU pattern + market enum
    source: DataSource = Depends(get_data_source),
    _: None = Depends(verify_api_key),
) -> AgentAnalysisResponse:
    """Run the analyst -> strategist -> reviewer agent workflow."""
    _require_llm_configured()
    try:
        return agent_analysis.analyze(source, request.product_id, request.market)
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


@router.post("/agents/analyze/stream")
async def analyze_with_agents_stream(
    request: AgentAnalysisRequest,  # guardrail: SKU pattern + market enum
    source: DataSource = Depends(get_data_source),
    _: None = Depends(verify_api_key),
) -> StreamingResponse:
    """Same workflow as ``/agents/analyze`` but as Server-Sent Events.

    Emits ``step_started`` / ``step_completed`` per agent (with latency and
    token usage) and a final ``result`` event. Errors after the stream has
    started cannot change the HTTP status, so they arrive as an ``error``
    event with a client-safe message.
    """
    _require_llm_configured()

    def event_source() -> Iterator[str]:
        try:
            for event in agent_analysis.analyze_stream(
                source, request.product_id, request.market
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except (ProductNotFoundError, InsufficientDataError) as exc:
            yield f"data: {json.dumps({'event': 'error', 'detail': str(exc)})}\n\n"
        except AgentError as exc:
            log.error("agent_workflow_failed", error=str(exc))
            detail = "The AI analysis could not be completed. Please try again shortly."
            yield f"data: {json.dumps({'event': 'error', 'detail': detail})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
