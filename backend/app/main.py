"""FastAPI entrypoint: logging, CORS, startup checks and route registration."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .data_source import get_data_source
from .logging_conf import configure_logging, get_logger
from .schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate configuration and warm the data source before serving."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    if not settings.database_url and not Path(settings.dataset_path).exists():
        raise RuntimeError(
            f"No DATABASE_URL set and dataset file '{settings.dataset_path}' "
            f"not found. Set DATABASE_URL or DATASET_PATH in your environment "
            f"(see .env.example)."
        )
    get_data_source()  # loads CSV / seeds Postgres once, at startup
    log.info(
        "startup_complete",
        db="postgres" if settings.database_url else "csv",
        cache=f"memory(ttl={settings.cache_ttl_seconds}s,"
        f" max={settings.cache_max_size})",
        llm_configured=bool(settings.openai_api_key),
    )
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in get_settings().frontend_origins.split(",") if o.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe for Docker/Cloud Run health checks."""
    return HealthResponse(status="ok", app=get_settings().app_name)
