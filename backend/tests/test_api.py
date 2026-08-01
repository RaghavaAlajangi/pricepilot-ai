"""API integration tests against the CSV-backed test client."""

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
