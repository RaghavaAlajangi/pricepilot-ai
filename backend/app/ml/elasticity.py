"""Price-elasticity estimation — hybrid model loading + live fallback.

Inference priority (set by the notebook training run):
  Tier 1 — dedicated OLS per SKU/market
           weights/dedicated_{sku}_{mkt}.joblib
  Tier 2 — category Ridge per cat/market
           weights/category_{cat}_{mkt}.joblib
  Tier 3 — live OLS fit on raw data (fallback, always available)

The notebook ``notebooks/eda_and_elasticity_model.ipynb`` trains Tiers 1 & 2
and writes the .joblib files.  In production this would be a scheduled batch
job with MLflow versioning; the notebook documents that roadmap.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

# Overridable via env var so the `train` container and the backend both point
# at the shared docker-compose volume (/app/weights).
# Default matches the baked-in path in the Docker image (data/weights/).
# Override via WEIGHTS_DIR env var for local dev or CI runs.
_default_weights = (
    Path(__file__).parent.parent.parent.parent / "data" / "weights"
)
WEIGHTS_DIR = Path(os.environ.get("WEIGHTS_DIR", str(_default_weights)))

MIN_WEEKS = 8
MIN_DISTINCT_PRICES = 3
GRID_POINTS = 50


@dataclass(frozen=True)
class ElasticityFit:
    """Result of one elasticity estimation, consumed by the API layer."""

    elasticity: float
    r_squared: float
    n_weeks: int
    current_price: float
    unit_cost: float
    min_price: float
    max_price: float
    recommended_price: float
    profit_at_recommended: float
    profit_at_current: float
    confidence: str
    warnings: list[str]
    grid_prices: np.ndarray
    grid_units: np.ndarray
    grid_profit: np.ndarray


class InsufficientDataError(ValueError):
    """Raised when there is not enough price variation to fit a model."""


def weekly_aggregate(daily: pd.DataFrame) -> pd.DataFrame:
    """Collapse daily rows to one row per ISO week."""
    df = daily.copy()
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = (
        df.groupby("week")
        .agg(
            avg_price=("unit_price_eur", "mean"),
            units=("units_sold", "sum"),
            sessions=("web_sessions", "sum"),
            ad_spend=("ad_spend_eur", "sum"),
        )
        .reset_index()
    )
    weekly["revenue"] = weekly["avg_price"] * weekly["units"]
    return weekly


def _design_matrix(weekly: pd.DataFrame) -> np.ndarray:
    """Features: ln(price), ln(ad_spend + 1), 11 month dummies (Dec is
    baseline)."""
    ln_price = np.log(weekly["avg_price"].to_numpy())
    ln_ads = np.log1p(weekly["ad_spend"].to_numpy())
    months = pd.get_dummies(weekly["week"].dt.month, dtype=float)
    months = months.reindex(
        columns=range(1, 12), fill_value=0.0
    )  # drop December
    return np.column_stack([ln_price, ln_ads, months.to_numpy()])


def _load_bundle(path: Path) -> dict | None:
    """Return a joblib weight bundle, or None if the file does not exist."""
    if path.exists():
        return joblib.load(path)
    return None


def _bundle_to_fit(
    bundle: dict,
    current_price: float,
    sku_id: str | None = None,
) -> ElasticityFit:
    """Reconstruct an ElasticityFit from a saved weight bundle.

    Works for both tier-1 (dedicated) and tier-2 (category Ridge) bundles.
    For category bundles pass ``sku_id`` so the correct cost/price range
    is used.
    """
    model = bundle["model"]
    controls = bundle["controls_mean"]

    if bundle["model_tier"] == "dedicated":
        unit_cost = bundle["unit_cost"]
        min_price = bundle["min_price"]
        max_price = bundle["max_price"]
        n_weeks = bundle["n_weeks"]
        grid_X_builder = lambda g: np.column_stack(  # noqa: E731
            [np.log(g), np.tile(controls, (GRID_POINTS, 1))]
        )
    else:
        # Category bundle — look up per-SKU metadata
        fallback_cost = list(bundle["unit_costs"].values())[0]
        unit_cost = bundle["unit_costs"].get(sku_id, fallback_cost)
        min_price, max_price = bundle["price_ranges"].get(
            sku_id, list(bundle["price_ranges"].values())[0]
        )
        n_weeks = bundle["n_samples"]
        n_sku = len(bundle["sku_columns"])
        sku_zeros = np.zeros((GRID_POINTS, n_sku))
        grid_X_builder = lambda g: np.column_stack(  # noqa: E731
            [np.log(g), np.tile(controls, (GRID_POINTS, 1)), sku_zeros]
        )

    grid = np.linspace(min_price, max_price, GRID_POINTS)
    grid_units = np.exp(model.predict(grid_X_builder(grid)))
    grid_profit = (grid - unit_cost) * grid_units
    best = int(np.argmax(grid_profit))
    elasticity = float(bundle["elasticity"])
    r_squared = float(
        bundle.get("r_squared", bundle.get("r_squared_train", 0.0))
    )
    profit_at_current = float(np.interp(current_price, grid, grid_profit))

    warnings: list[str] = []
    if elasticity >= 0:
        warnings.append(
            "Estimated elasticity is non-negative; price signal is unreliable."
        )
    if elasticity > -1:
        warnings.append(
            "Demand looks inelastic (|e| < 1); model pushes toward the top of "
            "the observed price range — treat as an upper bound, not a target."
        )
    if best in (0, GRID_POINTS - 1):
        warnings.append(
            "Optimum sits at the edge of the observed price range."
        )
    if r_squared < 0.3:
        warnings.append("Low model fit (R² < 0.3); interpret with caution.")

    if elasticity < 0 and r_squared >= 0.5:
        confidence = "high"
    elif elasticity < 0 and r_squared >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    return ElasticityFit(
        elasticity=round(elasticity, 3),
        r_squared=round(r_squared, 3),
        n_weeks=n_weeks,
        current_price=current_price,
        unit_cost=unit_cost,
        min_price=round(min_price, 2),
        max_price=round(max_price, 2),
        recommended_price=round(float(grid[best]), 2),
        profit_at_recommended=round(float(grid_profit[best]), 2),
        profit_at_current=round(profit_at_current, 2),
        confidence=confidence,
        warnings=warnings,
        grid_prices=grid,
        grid_units=grid_units,
        grid_profit=grid_profit,
    )


def load_elasticity(
    product_id: str,
    market: str,
    category: str,
    current_price: float,
) -> ElasticityFit | None:
    """Try to return an ElasticityFit from saved weights (Tier 1 then Tier 2).

    Returns None if no weight file exists for this SKU/category+market,
    signalling the caller to fall back to live fitting.
    """
    # Tier 1 — dedicated model for this exact SKU/market
    tier1_path = WEIGHTS_DIR / f"dedicated_{product_id}_{market}.joblib"
    bundle = _load_bundle(tier1_path)
    if bundle is not None:
        return _bundle_to_fit(bundle, current_price)

    # Tier 2 — category model for this market
    cat_slug = category.replace(" ", "_")
    tier2_path = WEIGHTS_DIR / f"category_{cat_slug}_{market}.joblib"
    bundle = _load_bundle(tier2_path)
    if bundle is not None:
        return _bundle_to_fit(bundle, current_price, sku_id=product_id)

    return None


def fit_elasticity(daily: pd.DataFrame, unit_cost: float) -> ElasticityFit:
    """Estimate elasticity and derive the profit-maximising price.

    Raises ``InsufficientDataError`` if the series is too short or the
    price never changed (elasticity is then unidentifiable).
    """
    weekly = weekly_aggregate(daily)
    weekly = weekly[
        weekly["units"] > 0
    ]  # ln(0) undefined; zero weeks are rare after aggregation
    if (
        len(weekly) < MIN_WEEKS
        or weekly["avg_price"].round(2).nunique() < MIN_DISTINCT_PRICES
    ):
        raise InsufficientDataError(
            "Not enough weeks or price variation to estimate elasticity."
        )

    X = _design_matrix(weekly)
    y = np.log(weekly["units"].to_numpy())
    model = LinearRegression().fit(X, y)
    elasticity = float(model.coef_[0])
    r_squared = float(model.score(X, y))

    # Predict demand on a price grid, holding controls at their mean
    # (an "average week"), strictly within the observed price range.
    min_price = float(weekly["avg_price"].min())
    max_price = float(weekly["avg_price"].max())
    current_price = float(daily.sort_values("date")["unit_price_eur"].iloc[-1])
    grid = np.linspace(min_price, max_price, GRID_POINTS)
    controls = X[:, 1:].mean(axis=0)
    grid_X = np.column_stack(
        [np.log(grid), np.tile(controls, (GRID_POINTS, 1))]
    )
    grid_units = np.exp(model.predict(grid_X))
    grid_profit = (grid - unit_cost) * grid_units

    best = int(np.argmax(grid_profit))
    recommended = float(grid[best])
    profit_at_current = float(np.interp(current_price, grid, grid_profit))

    warnings: list[str] = []
    if elasticity >= 0:
        warnings.append(
            "Estimated elasticity is non-negative; price signal is unreliable."
        )
    if elasticity > -1:
        warnings.append(
            "Demand looks inelastic (|e| < 1); the model pushes towards the "
            "top of the observed price range — treat as an upper bound, not "
            "a target."
        )
    if best in (0, GRID_POINTS - 1):
        warnings.append(
            "Optimum sits at the edge of the observed price range (possibly "
            "beyond it)."
        )
    if r_squared < 0.3:
        warnings.append("Low model fit (R² < 0.3); interpret with caution.")

    if elasticity < 0 and r_squared >= 0.5:
        confidence = "high"
    elif elasticity < 0 and r_squared >= 0.3:
        confidence = "medium"
    else:
        confidence = "low"

    return ElasticityFit(
        elasticity=round(elasticity, 3),
        r_squared=round(r_squared, 3),
        n_weeks=len(weekly),
        current_price=current_price,
        unit_cost=unit_cost,
        min_price=round(min_price, 2),
        max_price=round(max_price, 2),
        recommended_price=round(recommended, 2),
        profit_at_recommended=round(float(grid_profit[best]), 2),
        profit_at_current=round(profit_at_current, 2),
        confidence=confidence,
        warnings=warnings,
        grid_prices=grid,
        grid_units=grid_units,
        grid_profit=grid_profit,
    )
