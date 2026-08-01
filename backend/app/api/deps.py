"""Shared FastAPI dependencies."""

from fastapi import Header, HTTPException

from ..config import get_settings


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject requests whose X-API-Key header does not match APP_API_KEY.

    If APP_API_KEY is not configured the check is skipped so local dev works
    without any extra setup.
    """
    expected = get_settings().app_api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
