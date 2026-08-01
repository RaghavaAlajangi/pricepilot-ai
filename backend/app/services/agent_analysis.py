"""Orchestrates one agent analysis: cache -> ML payload -> LangGraph ->
guardrails.

Every run emits a structured compliance log entry (input hash, model,
latency, validation status) — the payload itself is derived from
non-sensitive aggregate sales data, but we still log a hash, not raw text.

Two entry points share the same pipeline:

- :func:`analyze` — blocking, returns the final response (used by tests
  and non-streaming clients).
- :func:`analyze_stream` — generator of SSE-ready event dicts so the UI
  can render each agent step (latency + token usage) as it completes.
"""

import hashlib
import json
import time
from typing import Iterator

from ..agents.graph import AGENT_SEQUENCE, AgentState, run_workflow, stream_workflow
from ..cache import cache_get, cache_set
from ..config import get_settings
from ..data_source import DataSource
from ..guardrails import validate_recommendation
from ..logging_conf import get_logger
from ..schemas import AgentAnalysisResponse, ElasticityResult, GuardrailReport
from . import pricing

log = get_logger(__name__)


def _cache_key(product_id: str, market: str) -> str:
    return f"agents:{get_settings().openai_model}:{product_id}:{market}"


def _build_payload(
    source: DataSource, product_id: str, market: str
) -> tuple[ElasticityResult, dict]:
    """ML result + the compact numbers-only payload the agents reason over."""
    result = pricing.get_elasticity(source, product_id, market)
    meta = source.list_products()
    meta = meta[meta["product_id"] == product_id].iloc[0]
    payload = pricing.build_agent_payload(
        result, meta["product_name"], meta["category"]
    )
    return result, payload


def _finalize(
    state: AgentState,
    result: ElasticityResult,
    product_id: str,
    market: str,
    payload: dict,
    total_latency_ms: int,
) -> AgentAnalysisResponse:
    """Guardrails, compliance log and cache write for one completed run."""
    settings = get_settings()
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
    steps = state["steps"]
    response = AgentAnalysisResponse(
        product_id=product_id,
        market=market,
        analyst=analyst,
        strategist=strategist,
        reviewer=reviewer,
        guardrail=GuardrailReport(passed=not violations, violations=violations),
        model=settings.openai_model,
        cached=False,
        steps=steps,
        total_latency_ms=total_latency_ms,
        total_tokens=sum(s.input_tokens + s.output_tokens for s in steps),
    )
    log.info(
        "agent_analysis_completed",
        product_id=product_id,
        market=market,
        model=settings.openai_model,
        input_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16],
        latency_ms=total_latency_ms,
        total_tokens=response.total_tokens,
        guardrail_passed=response.guardrail.passed,
        reviewer_verdict=reviewer.verdict,
    )
    cache_set(_cache_key(product_id, market), response.model_dump())
    return response


def analyze(source: DataSource, product_id: str, market: str) -> AgentAnalysisResponse:
    """Run (or fetch from cache) the three-agent analysis for one
    product/market."""
    if cached := cache_get(_cache_key(product_id, market)):
        return AgentAnalysisResponse(**{**cached, "cached": True})

    result, payload = _build_payload(source, product_id, market)
    started = time.perf_counter()
    state = run_workflow(payload)
    total_latency_ms = round((time.perf_counter() - started) * 1000)
    return _finalize(state, result, product_id, market, payload, total_latency_ms)


def analyze_stream(source: DataSource, product_id: str, market: str) -> Iterator[dict]:
    """Yield progress events for one analysis run (SSE-ready dicts).

    Event shapes:
      {"event": "step_started",   "agent": "analyst"}
      {"event": "step_completed", "agent": "analyst", "latency_ms": ...,
       "input_tokens": ..., "output_tokens": ...}
      {"event": "result", "data": <AgentAnalysisResponse>}
    """
    if cached := cache_get(_cache_key(product_id, market)):
        response = AgentAnalysisResponse(**{**cached, "cached": True})
        yield {"event": "result", "data": response.model_dump(mode="json")}
        return

    result, payload = _build_payload(source, product_id, market)
    started = time.perf_counter()
    yield {"event": "step_started", "agent": AGENT_SEQUENCE[0]}

    final_state: AgentState | None = None
    for index, (agent, state) in enumerate(stream_workflow(payload)):
        final_state = state
        step = state["steps"][-1]
        yield {"event": "step_completed", **step.model_dump()}
        if index + 1 < len(AGENT_SEQUENCE):
            yield {"event": "step_started", "agent": AGENT_SEQUENCE[index + 1]}

    assert final_state is not None  # the graph always runs all three nodes
    total_latency_ms = round((time.perf_counter() - started) * 1000)
    response = _finalize(
        final_state, result, product_id, market, payload, total_latency_ms
    )
    yield {"event": "result", "data": response.model_dump(mode="json")}
