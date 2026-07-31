"""ML sanity: the model recovers a known elasticity from synthetic data."""

import pandas as pd
import pytest

from app.ml.elasticity import (
    InsufficientDataError,
    fit_elasticity,
    weekly_aggregate,
)


def test_recovers_known_elasticity(synthetic_daily: pd.DataFrame) -> None:
    fit = fit_elasticity(synthetic_daily, unit_cost=40.0)
    # data was generated with elasticity = -2.0
    assert -2.4 < fit.elasticity < -1.6
    assert fit.r_squared > 0.5
    assert fit.confidence == "high"


def test_recommended_price_is_sane(synthetic_daily: pd.DataFrame) -> None:
    fit = fit_elasticity(synthetic_daily, unit_cost=40.0)
    assert fit.min_price <= fit.recommended_price <= fit.max_price
    assert fit.recommended_price > fit.unit_cost
    assert fit.profit_at_recommended >= fit.profit_at_current
    # elasticity -2 with cost 40 => theoretical optimum c*e/(1+e) = 80 EUR
    assert 70.0 < fit.recommended_price < 92.0


def test_constant_price_raises(synthetic_daily: pd.DataFrame) -> None:
    flat = synthetic_daily.copy()
    flat["unit_price_eur"] = 89.95  # no variation -> unidentifiable
    with pytest.raises(InsufficientDataError):
        fit_elasticity(flat, unit_cost=40.0)


def test_short_series_raises(synthetic_daily: pd.DataFrame) -> None:
    with pytest.raises(InsufficientDataError):
        fit_elasticity(synthetic_daily.head(20), unit_cost=40.0)


def test_weekly_aggregate_sums_units(synthetic_daily: pd.DataFrame) -> None:
    weekly = weekly_aggregate(synthetic_daily)
    assert weekly["units"].sum() == synthetic_daily["units_sold"].sum()
    assert 50 <= len(weekly) <= 54  # ~52 weeks
