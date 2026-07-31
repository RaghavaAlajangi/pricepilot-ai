"""Model training entry-point.

Runs at image-build time (or as a one-shot container before the backend starts)
and writes .joblib weight files to WEIGHTS_DIR so the backend can load them.

Production evolution (out of scope for this challenge):
  - This script would be the heart of an Airflow / Prefect DAG.
  - Weight files would go to S3 (or GCS) instead of a local volume.
  - MLflow would log every run: metrics, params, artefacts.
  - A model registry (MLflow / SageMaker) would gate promotion to production.
  - The backend would pull weights from the registry on startup, not from disk.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge, RidgeCV
from sklearn.model_selection import cross_val_score

# ---------------------------------------------------------------------------
# Paths — all overridable via env vars so the Docker image is portable.
# ---------------------------------------------------------------------------
DATASET_PATH = Path(os.environ.get("DATASET_PATH", "/app/data/dataset.csv"))
WEIGHTS_DIR = Path(os.environ.get("WEIGHTS_DIR", "/app/weights"))
HIGH_VOLUME_REVENUE_THRESHOLD = float(
    os.environ.get("HIGH_VOLUME_REVENUE_THRESHOLD", "50.0")
)  # % of total revenue

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","event":"%(message)s"}',
    level=logging.INFO,
)
log = logging.getLogger("train")


# ---------------------------------------------------------------------------
# Feature engineering — mirrors backend/app/ml/elasticity.py exactly.
# Kept here explicitly so train/ has zero dependency on the backend package.
# ---------------------------------------------------------------------------


def weekly_aggregate(daily: pd.DataFrame) -> pd.DataFrame:
    """Collapse daily rows to one row per ISO week."""
    df = daily.copy()
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    weekly = (
        df.groupby("week")
        .agg(
            avg_price=("unit_price_eur", "mean"),
            units=("units_sold", "sum"),
            ad_spend=("ad_spend_eur", "sum"),
        )
        .reset_index()
    )
    return weekly


def design_matrix(weekly: pd.DataFrame) -> np.ndarray:
    """Features: ln(price), ln(ad_spend + 1), 11 month dummies (Dec is
    baseline)."""
    ln_price = np.log(weekly["avg_price"].to_numpy())
    ln_ads = np.log1p(weekly["ad_spend"].to_numpy())
    months = pd.get_dummies(weekly["week"].dt.month, dtype=float)
    months = months.reindex(columns=range(1, 12), fill_value=0.0)
    return np.column_stack([ln_price, ln_ads, months.to_numpy()])


# ---------------------------------------------------------------------------
# Tier 1: dedicated OLS per high-volume SKU + market
# ---------------------------------------------------------------------------


def train_dedicated(daily: pd.DataFrame, unit_cost: float) -> dict:
    """OLS on one SKU/market. Raises ValueError if data is insufficient."""
    weekly = weekly_aggregate(daily)
    weekly = weekly[weekly["units"] > 0]

    if len(weekly) < 8 or weekly["avg_price"].round(2).nunique() < 3:
        raise ValueError("Insufficient data for dedicated model.")

    X = design_matrix(weekly)
    y = np.log(weekly["units"].to_numpy())
    model = LinearRegression().fit(X, y)

    return {
        "model": model,
        "controls_mean": X[:, 1:].mean(axis=0),
        "min_price": float(weekly["avg_price"].min()),
        "max_price": float(weekly["avg_price"].max()),
        "unit_cost": unit_cost,
        "elasticity": float(model.coef_[0]),
        "r_squared": float(model.score(X, y)),
        "n_weeks": len(weekly),
        "model_tier": "dedicated",
    }


# ---------------------------------------------------------------------------
# Tier 2: category Ridge pooling mid-volume SKUs
# ---------------------------------------------------------------------------


def build_category_dataset(
    df: pd.DataFrame, skus: set[str], category: str, market: str
) -> dict | None:
    """Stack weekly rows for all mid-volume SKUs in one category/market."""
    frames = []
    for pid in sorted(skus):
        grp = df[
            (df["product_id"] == pid)
            & (df["market"] == market)
            & (df["category"] == category)
        ].copy()
        if grp.empty:
            continue
        w = weekly_aggregate(grp)
        w = w[w["units"] > 0]
        if len(w) < 4:
            continue
        w["product_id"] = pid
        w["unit_cost"] = float(grp["unit_cost_eur"].iloc[0])
        frames.append(w)

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    X_base = design_matrix(combined)
    sku_dummies = pd.get_dummies(
        combined["product_id"], dtype=float, drop_first=True
    )
    X = np.column_stack([X_base, sku_dummies.to_numpy()])
    y = np.log(combined["units"].to_numpy())

    return {
        "X": X,
        "y": y,
        "price_ranges": {
            pid: (float(g["avg_price"].min()), float(g["avg_price"].max()))
            for pid, g in combined.groupby("product_id")
        },
        "unit_costs": combined.groupby("product_id")["unit_cost"]
        .first()
        .to_dict(),
        "controls_mean": X_base[:, 1:].mean(axis=0),
        "sku_columns": list(sku_dummies.columns),
        "n_base_features": X_base.shape[1],
    }


def train_category(data: dict, category: str, market: str) -> dict:
    ridge = Ridge(alpha=1.0).fit(data["X"], data["y"])
    cv_r2 = cross_val_score(
        Ridge(alpha=1.0),
        data["X"],
        data["y"],
        cv=min(5, len(data["y"]) // 4),
        scoring="r2",
    )
    return {
        "model": ridge,
        "controls_mean": data["controls_mean"],
        "price_ranges": data["price_ranges"],
        "unit_costs": data["unit_costs"],
        "sku_columns": data["sku_columns"],
        "n_base_features": data["n_base_features"],
        "elasticity": float(ridge.coef_[0]),
        "r_squared_train": float(ridge.score(data["X"], data["y"])),
        "r_squared_cv": float(cv_r2.mean()),
        "n_samples": len(data["y"]),
        "model_tier": "category",
        "category": category,
        "market": market,
    }


# ---------------------------------------------------------------------------
# Tier 3: global Ridge across all SKUs, markets, categories
# ---------------------------------------------------------------------------


def build_global_dataset(df: pd.DataFrame) -> dict:
    """Pool every SKU × market × category into one training table."""
    frames = []
    for (pid, mkt, cat), grp in df.groupby(
        ["product_id", "market", "category"]
    ):
        w = weekly_aggregate(grp.copy())
        w = w[w["units"] > 0]
        if len(w) < 4:
            continue
        w["product_id"] = pid
        w["market"] = mkt
        w["category"] = cat
        w["unit_cost"] = float(grp["unit_cost_eur"].iloc[0])
        frames.append(w)

    combined = pd.concat(frames, ignore_index=True)
    X_base = design_matrix(combined)
    prod_dummies = pd.get_dummies(
        combined["product_id"], dtype=float, drop_first=True
    )
    mkt_dummies = pd.get_dummies(
        combined["market"], dtype=float, drop_first=True
    )
    cat_dummies = pd.get_dummies(
        combined["category"], dtype=float, drop_first=True
    )

    X = np.column_stack(
        [
            X_base,
            prod_dummies.to_numpy(),
            mkt_dummies.to_numpy(),
            cat_dummies.to_numpy(),
        ]
    )
    y = np.log(combined["units"].to_numpy())

    return {
        "X": X,
        "y": y,
        "X_base_n_features": X_base.shape[1],
        "controls_mean": X_base[:, 1:].mean(axis=0),
        "prod_columns": list(prod_dummies.columns),
        "mkt_columns": list(mkt_dummies.columns),
        "cat_columns": list(cat_dummies.columns),
    }


def train_global(data: dict) -> dict:
    alphas = np.logspace(-2, 4, 50)
    model = RidgeCV(alphas=alphas, cv=5, scoring="r2").fit(
        data["X"], data["y"]
    )
    cv_r2 = cross_val_score(
        Ridge(alpha=float(model.alpha_)),
        data["X"],
        data["y"],
        cv=5,
        scoring="r2",
    )
    return {
        "model": model,
        "elasticity": float(model.coef_[0]),
        "r_squared_train": float(model.score(data["X"], data["y"])),
        "r_squared_cv": float(cv_r2.mean()),
        "alpha": float(model.alpha_),
        "controls_mean": data["controls_mean"],
        "prod_columns": data["prod_columns"],
        "mkt_columns": data["mkt_columns"],
        "cat_columns": data["cat_columns"],
        "n_base_features": data["X_base_n_features"],
        "n_samples": len(data["y"]),
        "model_tier": "global",
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run(dataset_path: Path, weights_dir: Path) -> None:
    t0 = time.perf_counter()
    weights_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading dataset from %s", dataset_path)
    df = pd.read_csv(dataset_path, parse_dates=["date"])
    log.info("Loaded %d rows, %d SKUs", len(df), df["product_id"].nunique())

    df["revenue"] = df["unit_price_eur"] * df["units_sold"]
    sku_revenue = (
        df.groupby("product_id")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    sku_revenue["cum_pct"] = (
        sku_revenue["revenue"].cumsum() / sku_revenue["revenue"].sum() * 100
    )

    high_volume = set(
        sku_revenue[sku_revenue["cum_pct"] <= HIGH_VOLUME_REVENUE_THRESHOLD][
            "product_id"
        ]
    )
    high_volume.add(
        sku_revenue.iloc[0]["product_id"]
    )  # always include top SKU
    mid_volume = set(sku_revenue["product_id"]) - high_volume
    markets = sorted(df["market"].unique())

    saved = {"dedicated": 0, "category": 0, "global": 0, "skipped": 0}

    # ---- Tier 1: dedicated OLS ----------------------------------------------
    log.info(
        "Training Tier 1: dedicated OLS for %d high-volume SKUs × %d markets",
        len(high_volume),
        len(markets),
    )
    for pid in sorted(high_volume):
        for mkt in markets:
            daily = df[
                (df["product_id"] == pid) & (df["market"] == mkt)
            ].copy()
            cost = float(daily["unit_cost_eur"].iloc[0])
            try:
                bundle = train_dedicated(daily, cost)
                path = weights_dir / f"dedicated_{pid}_{mkt}.joblib"
                joblib.dump(bundle, path)
                saved["dedicated"] += 1
                log.info(
                    "dedicated/%s/%s  e=%.3f  R²=%.3f  n=%d",
                    pid,
                    mkt,
                    bundle["elasticity"],
                    bundle["r_squared"],
                    bundle["n_weeks"],
                )
            except ValueError as exc:
                saved["skipped"] += 1
                log.warning("SKIP dedicated/%s/%s  reason=%s", pid, mkt, exc)

    # ---- Tier 2: category Ridge ---------------------------------------------
    log.info(
        "Training Tier 2: category Ridge for %d mid-volume SKUs",
        len(mid_volume),
    )
    for cat in sorted(df["category"].unique()):
        for mkt in markets:
            data = build_category_dataset(df, mid_volume, cat, mkt)
            if data is None or len(data["y"]) < 10:
                continue
            bundle = train_category(data, cat, mkt)
            slug = cat.replace(" ", "_")
            path = weights_dir / f"category_{slug}_{mkt}.joblib"
            joblib.dump(bundle, path)
            saved["category"] += 1
            log.info(
                "category/%s/%s  e=%.3f  R²_cv=%.3f  n=%d",
                cat,
                mkt,
                bundle["elasticity"],
                bundle["r_squared_cv"],
                bundle["n_samples"],
            )

    # ---- Tier 3: global Ridge -----------------------------------------------
    log.info("Training Tier 3: global Ridge across all data")
    global_data = build_global_dataset(df)
    bundle = train_global(global_data)
    path = weights_dir / "global_ridge.joblib"
    joblib.dump(bundle, path)
    saved["global"] += 1
    log.info(
        "global  e=%.3f  R²_cv=%.3f  n=%d  alpha=%.4f",
        bundle["elasticity"],
        bundle["r_squared_cv"],
        bundle["n_samples"],
        bundle["alpha"],
    )

    elapsed = time.perf_counter() - t0
    total = saved["dedicated"] + saved["category"] + saved["global"]
    log.info(
        "Training complete in %.1fs — %d files saved "
        "(dedicated=%d  category=%d  global=%d  skipped=%d)",
        elapsed,
        total,
        saved["dedicated"],
        saved["category"],
        saved["global"],
        saved["skipped"],
    )

    all_files = sorted(weights_dir.glob("*.joblib"))
    log.info("Weights directory: %s  (%d files)", weights_dir, len(all_files))


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PricePilot model training")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--weights-dir", type=Path, default=WEIGHTS_DIR)
    args = parser.parse_args()

    if not args.dataset.exists():
        log.error("Dataset not found: %s", args.dataset)
        sys.exit(1)

    run(args.dataset, args.weights_dir)
