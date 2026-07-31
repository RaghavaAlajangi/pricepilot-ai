"""Orchestrates one agent analysis: cache -> ML payload -> LangGraph ->
guardrails.

Every run emits a structured compliance log entry (input hash, model,
latency, validation status) — the payload itself is derived from
non-sensitive aggregate sales data, but we still log a hash, not raw text.
"""

import hashlib
import json
import time

from ..agents.graph import run_workflow
from ..cache import cache_get, cache_set
from ..config import get_settings
from ..data_source import DataSource
from ..guardrails import validate_recommendation
from ..logging_conf import get_logger
from ..schemas import AgentAnalysisResponse, GuardrailReport
from . import pricing

log = get_logger(__name__)


def analyze(source: DataSource, product_id: str, market: str) -> AgentAnalysisResponse:
    """Run (or fetch from cache) the three-agent analysis for one
    product/market."""
    settings = get_settings()
    cache_key = f"agents:{settings.openai_model}:{product_id}:{market}"
    if cached := cache_get(cache_key):
        return AgentAnalysisResponse(**{**cached, "cached": True})

    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta["product_name"], meta["category"]
    )

    started = time.perf_counter()
    state = run_workflow(payload)
    latency_ms = round((time.perf_counter() - started) * 1000)

    analyst, strategist, reviewer = (
        state["analyst"],
        state["strategist"],
        state["reviewer"],
    )
    assert analyst is not None and strategist is not None and reviewer is not None

    violations = validate_recommendation(
        strategist,
        unit_cost=result.unit_cost,
        current_price=result.current_price,
        min_observed=result.min_observed_price,
        max_observed=result.max_observed_price,
    )
    response = AgentAnalysisResponse(
        product_id=product_id,
        market=market,
        analyst=analyst,
        strategist=strategist,
        reviewer=reviewer,
        guardrail=GuardrailReport(passed=not violations, violations=violations),
        model=settings.openai_model,
        cached=False,
    )
    log.info(
        "agent_analysis_completed",
        product_id=product_id,
        market=market,
        model=settings.openai_model,
        input_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16],
        latency_ms=latency_ms,
        guardrail_passed=response.guardrail.passed,
        reviewer_verdict=reviewer.verdict,
    )
    cache_set(cache_key, response.model_dump())
    return response
