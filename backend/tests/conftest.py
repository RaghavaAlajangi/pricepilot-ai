"""Shared fixtures: a small synthetic dataset and an API test client."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def make_synthetic_daily(
    elasticity: float = -2.0,
    n_days: int = 364,
    unit_cost: float = 40.0,
    seed: int = 7,
) -> pd.DataFrame:
    """Daily sales generated from a known constant-elasticity demand curve.

    units ~ Poisson(A * price^elasticity), price cycles through 4 levels,
    so the fitted model should recover ``elasticity`` closely.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    price_levels = np.array([69.95, 79.95, 89.95, 99.95])
    prices = price_levels[(np.arange(n_days) // 28) % len(price_levels)]
    demand = 40_000.0 * prices**elasticity
    units = rng.poisson(demand)
    return pd.DataFrame(
        {
            "date": dates,
            "product_id": "SKU-1000",
            "product_name": "Pendant Light 'Test'",
            "category": "Pendant Lights",
            "brand": "Casaluce",
            "market": "DE",
            "unit_price_eur": prices,
            "unit_cost_eur": unit_cost,
            "units_sold": units,
            "web_sessions": rng.integers(20, 120, n_days),
            "ad_spend_eur": rng.uniform(0, 10, n_days).round(2),
        }
    )


@pytest.fixture
def synthetic_daily() -> pd.DataFrame:
    return make_synthetic_daily()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient backed by the CSV data source and a tiny synthetic file."""
    csv_path = tmp_path / "mini.csv"
    make_synthetic_daily().to_csv(csv_path, index=False)
    monkeypatch.setenv("DATASET_PATH", str(csv_path))
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    from app.config import get_settings
    from app.data_source import get_data_source
    from app.main import app
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    get_data_source.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_data_source.cache_clear()
