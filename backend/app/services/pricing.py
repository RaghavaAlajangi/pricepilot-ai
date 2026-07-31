"""Business logic: catalogue, summaries, ML results and the agent payload."""

import pandas as pd

from ..data_source import DataSource
from ..ml.elasticity import fit_elasticity, load_elasticity, weekly_aggregate
from ..schemas import (
    CurvePoint,
    ElasticityResult,
    ProductInfo,
    ProductSummary,
    WeeklyPoint,
)


class ProductNotFoundError(LookupError):
    """Raised when a product/market combination has no rows."""


def list_products(source: DataSource) -> list[ProductInfo]:
    """Catalogue of products with the markets they are sold in."""
    rows = source.list_products()
    products = []
    for (pid, name, cat, brand), grp in rows.groupby(
        ["product_id", "product_name", "category", "brand"], sort=True
    ):
        products.append(
            ProductInfo(
                product_id=pid,
                product_name=name,
                category=cat,
                brand=brand,
                markets=sorted(grp["market"].tolist()),
            )
        )
    return products


def _series_or_raise(
    source: DataSource, product_id: str, market: str
) -> pd.DataFrame:
    daily = source.product_series(product_id, market)
    if daily.empty:
        raise ProductNotFoundError(
            f"No data for {product_id} in market {market}."
        )
    return daily


def get_summary(
    source: DataSource, product_id: str, market: str
) -> ProductSummary:
    """KPIs plus the weekly series that feeds the dashboard charts."""
    daily = _series_or_raise(source, product_id, market)
    meta = source.list_products()
    meta = meta[meta["product_id"] == product_id].iloc[0]
    weekly = weekly_aggregate(daily)
    return ProductSummary(
        product_id=product_id,
        product_name=meta["product_name"],
        category=meta["category"],
        brand=meta["brand"],
        market=market,
        current_price=float(daily["unit_price_eur"].iloc[-1]),
        unit_cost=float(daily["unit_cost_eur"].iloc[0]),
        total_units=int(weekly["units"].sum()),
        total_revenue=round(float(weekly["revenue"].sum()), 2),
        avg_weekly_units=round(float(weekly["units"].mean()), 1),
        weekly=[
            WeeklyPoint(
                week=row.week.date(),
                avg_price=round(row.avg_price, 2),
                units=int(row.units),
                revenue=round(row.revenue, 2),
                sessions=int(row.sessions),
            )
            for row in weekly.itertuples()
        ],
    )


def get_elasticity(
    source: DataSource, product_id: str, market: str
) -> ElasticityResult:
    """Return an elasticity result, preferring saved weights over live fitting.

    Priority: Tier 1 (dedicated) → Tier 2 (category Ridge) → Tier 3 (live OLS).
    """
    daily = _series_or_raise(source, product_id, market)
    meta = source.list_products()
    category = str(
        meta[meta["product_id"] == product_id]["category"].iloc[0]
    )
    current_price = float(
        daily.sort_values("date")["unit_price_eur"].iloc[-1]
    )
    fit = load_elasticity(product_id, market, category, current_price)
    if fit is None:
        fit = fit_elasticity(
            daily, unit_cost=float(daily["unit_cost_eur"].iloc[0])
        )
    curve = [
        CurvePoint(
            price=round(float(p), 2),
            predicted_weekly_units=round(float(u), 1),
            predicted_weekly_profit=round(float(pr), 2),
        )
        for p, u, pr in zip(fit.grid_prices, fit.grid_units, fit.grid_profit)
    ]
    return ElasticityResult(
        product_id=product_id,
        market=market,
        elasticity=fit.elasticity,
        r_squared=fit.r_squared,
        n_weeks=fit.n_weeks,
        current_price=fit.current_price,
        unit_cost=fit.unit_cost,
        min_observed_price=fit.min_price,
        max_observed_price=fit.max_price,
        recommended_price=fit.recommended_price,
        profit_at_recommended=fit.profit_at_recommended,
        profit_at_current=fit.profit_at_current,
        confidence=fit.confidence,
        warnings=fit.warnings,
        curve=curve,
    )


def build_agent_payload(
    result: ElasticityResult, product_name: str, category: str
) -> dict:
    """Compact, numbers-only payload the agents reason over.

    The full curve is excluded on purpose: it would inflate token cost
    without adding decision-relevant information.
    """
    return {
        "product_id": result.product_id,
        "product_name": product_name,
        "category": category,
        "market": result.market,
        "current_price_eur": result.current_price,
        "unit_cost_eur": result.unit_cost,
        "elasticity": result.elasticity,
        "r_squared": result.r_squared,
        "n_weeks": result.n_weeks,
        "min_observed_price_eur": result.min_observed_price,
        "max_observed_price_eur": result.max_observed_price,
        "model_recommended_price_eur": result.recommended_price,
        "predicted_weekly_profit_at_recommended_eur": result.profit_at_recommended,
        "predicted_weekly_profit_at_current_eur": result.profit_at_current,
        "model_confidence": result.confidence,
        "model_warnings": result.warnings,
    }
