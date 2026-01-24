import secrets
from fastapi import Header, HTTPException, status, Depends, Query
from typing import Optional
from app.config import Settings, get_settings


def _secure_compare(provided: str, expected: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return secrets.compare_digest(provided.encode(), expected.encode())


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, description="API key for authentication"),
    settings: Settings = Depends(get_settings),
) -> str:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if not _secure_compare(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key


async def verify_api_key_or_query(
    x_api_key: Optional[str] = Header(None, description="API key for authentication"),
    api_key: Optional[str] = Query(None, description="API key as query parameter"),
    settings: Settings = Depends(get_settings),
) -> str:
    """Verify API key from header or query parameter (for image loading in browser)."""
    key = x_api_key or api_key
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    if not _secure_compare(key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return key
