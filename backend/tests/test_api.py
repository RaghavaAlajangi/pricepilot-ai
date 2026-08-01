"""API integration tests against the CSV-backed test client."""

import json

import pytest
from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_products(client: TestClient) -> None:
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    products = response.json()
    assert products[0]["product_id"] == "SKU-1000"
    assert products[0]["markets"] == ["DE"]


def test_summary_returns_weekly_series(client: TestClient) -> None:
    response = client.get("/api/v1/products/SKU-1000/summary", params={"market": "DE"})
    assert response.status_code == 200
    body = response.json()
    assert body["unit_cost"] == 40.0
    assert len(body["weekly"]) > 40


def test_elasticity_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force live fitting so saved weights don't override the synthetic dataset.
    import app.services.pricing as pricing_mod

    monkeypatch.setattr(pricing_mod, "load_elasticity", lambda *_: None)

    response = client.get(
        "/api/v1/products/SKU-1000/elasticity", params={"market": "DE"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["elasticity"] < -1
    assert len(body["curve"]) == 50


def test_unknown_product_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/products/SKU-9999/summary", params={"market": "DE"})
    assert response.status_code == 404


def test_agents_endpoint_without_key_is_503(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agents/analyze",
        json={"product_id": "SKU-1000", "market": "DE"},
    )
    assert response.status_code == 503


def test_agents_endpoint_rejects_malformed_sku(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agents/analyze",
        json={"product_id": "'; DROP TABLE sales;--", "market": "DE"},
    )
    assert response.status_code == 422


def test_summary_and_elasticity_report_perf_stats(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.services.pricing as pricing_mod

    monkeypatch.setattr(pricing_mod, "load_elasticity", lambda *_: None)

    summary = client.get(
        "/api/v1/products/SKU-1000/summary", params={"market": "DE"}
    ).json()
    elasticity = client.get(
        "/api/v1/products/SKU-1000/elasticity", params={"market": "DE"}
    ).json()
    for body in (summary, elasticity):
        assert body["perf"]["backend"] == "in-memory"
        assert body["perf"]["data_fetch_ms"] >= 0
        assert body["perf"]["compute_ms"] >= 0


def test_agents_stream_endpoint_emits_step_events(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SSE endpoint yields step events per agent and a final result."""
    import app.services.agent_analysis as analysis_mod
    import app.services.pricing as pricing_mod
    from app.config import get_settings
    from app.schemas import (
        AgentStepStats,
        AnalystFindings,
        ReviewerVerdict,
        StrategistRecommendation,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(pricing_mod, "load_elasticity", lambda *_: None)

    outputs = {
        "analyst": AnalystFindings(
            summary="Demand is price-sensitive.",
            findings=["Elasticity is -2.0"],
            data_quality_notes=[],
        ),
        "strategist": StrategistRecommendation(
            recommended_price_eur=84.5,
            rationale="Near the optimum.",
            expected_impact="Higher profit.",
            risks=[],
        ),
        "reviewer": ReviewerVerdict(
            verdict="approve", checks_performed=["above cost"], concerns=[]
        ),
    }

    def fake_stream(payload: dict, llm=None):
        state = {
            "payload": payload,
            "analyst": None,
            "strategist": None,
            "reviewer": None,
            "steps": [],
        }
        for agent in ("analyst", "strategist", "reviewer"):
            step = AgentStepStats(
                agent=agent, latency_ms=10, input_tokens=500, output_tokens=100
            )
            state = {**state, agent: outputs[agent], "steps": state["steps"] + [step]}
            yield agent, state

    monkeypatch.setattr(analysis_mod, "stream_workflow", fake_stream)

    response = client.post(
        "/api/v1/agents/analyze/stream",
        json={"product_id": "SKU-1000", "market": "DE"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    kinds = [(e["event"], e.get("agent")) for e in events]
    assert kinds == [
        ("step_started", "analyst"),
        ("step_completed", "analyst"),
        ("step_started", "strategist"),
        ("step_completed", "strategist"),
        ("step_started", "reviewer"),
        ("step_completed", "reviewer"),
        ("result", None),
    ]
    result = events[-1]["data"]
    assert result["guardrail"]["passed"] is True
    assert result["total_tokens"] == 1800
    assert len(result["steps"]) == 3
