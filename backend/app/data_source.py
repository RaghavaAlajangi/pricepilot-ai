"""Data access layer with two interchangeable backends.

- ``PostgresDataSource``: used when DATABASE_URL is set (docker compose).
  The ``sales`` table is seeded once from the CSV at startup.
- ``CsvDataSource``: loads the CSV into memory when no database is
  configured (e.g. a standalone Cloud Run container). 131k rows ~ 15 MB.

Both return pandas DataFrames with identical columns, so everything
above this module is backend-agnostic.
"""

from functools import lru_cache
from typing import Protocol

import pandas as pd
from sqlalchemy import Engine, create_engine, inspect, text

from .config import get_settings
from .logging_conf import get_logger

log = get_logger(__name__)

SALES_TABLE = "sales"
CSV_DTYPES = {
    "product_id": "string",
    "product_name": "string",
    "category": "string",
    "brand": "string",
    "market": "string",
}
SERIES_COLUMNS = [
    "date",
    "unit_price_eur",
    "unit_cost_eur",
    "units_sold",
    "web_sessions",
    "ad_spend_eur",
]


class DataSource(Protocol):
    """Minimal read interface the API and ML layers depend on."""

    def list_products(self) -> pd.DataFrame:
        """Distinct (product_id, product_name, category, brand, market) rows"""
        ...

    def product_series(self, product_id: str, market: str) -> pd.DataFrame:
        """Daily rows (SERIES_COLUMNS) for one product in one market."""
        ...


def _read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"], dtype=CSV_DTYPES)
    df["ad_spend_eur"] = df["ad_spend_eur"].fillna(0.0)
    return df


class CsvDataSource:
    """In-memory dataset loaded once from the CSV file."""

    def __init__(self, path: str) -> None:
        self._df = _read_csv(path)
        log.info("csv_loaded", path=path, rows=len(self._df))

    def list_products(self) -> pd.DataFrame:
        cols = ["product_id", "product_name", "category", "brand", "market"]
        return self._df[cols].drop_duplicates()

    def product_series(self, product_id: str, market: str) -> pd.DataFrame:
        mask = (self._df["product_id"] == product_id) & (self._df["market"] == market)
        return (
            self._df.loc[mask, SERIES_COLUMNS]
            .sort_values("date")
            .reset_index(drop=True)
        )


class PostgresDataSource:
    """Reads from the ``sales`` table; seeds it from the CSV if empty."""

    def __init__(self, database_url: str, dataset_path: str) -> None:
        self._engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self._seed_if_empty(dataset_path)

    def _seed_if_empty(self, dataset_path: str) -> None:
        if inspect(self._engine).has_table(SALES_TABLE):
            with self._engine.connect() as conn:
                count = conn.execute(
                    text(f"SELECT count(*) FROM {SALES_TABLE}")
                ).scalar()
            if count:
                log.info("db_already_seeded", rows=count)
                return
        df = _read_csv(dataset_path)
        df.to_sql(
            SALES_TABLE,
            self._engine,
            if_exists="replace",
            index=False,
            chunksize=10_000,
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE INDEX idx_sales_pm ON {SALES_TABLE} (product_id, "
                    f"market)"
                )
            )
        log.info("db_seeded", rows=len(df))

    def list_products(self) -> pd.DataFrame:
        query = text(
            f"SELECT DISTINCT product_id, product_name, category, brand, "
            f"market FROM {SALES_TABLE}"
        )
        return pd.read_sql(query, self._engine)

    def product_series(self, product_id: str, market: str) -> pd.DataFrame:
        query = text(
            f"SELECT {', '.join(SERIES_COLUMNS)} FROM {SALES_TABLE} "
            "WHERE product_id = :p AND market = :m ORDER BY date"
        )
        df = pd.read_sql(query, self._engine, params={"p": product_id, "m": market})
        df["date"] = pd.to_datetime(df["date"])
        return df


@lru_cache
def get_data_source() -> DataSource:
    """Singleton data source chosen from configuration."""
    settings = get_settings()
    if settings.database_url:
        log.info("data_source", backend="postgres")
        return PostgresDataSource(settings.database_url, settings.dataset_path)
    log.info("data_source", backend="csv")
    return CsvDataSource(settings.dataset_path)
