from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, status

from app.config import Settings, get_settings
from app.models.user import User


def _get_user_service(settings: Settings):
    """Lazy import to avoid circular dependency."""
    from app.services.user_service import get_user_service
    return get_user_service(settings)


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, description="API key for authentication"),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Verify API key and return the associated user.

    API keys must be in the format: wrd_xxxxxxxxxxxx (16 chars total)
    """
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    # Check for multi-user API key (wrd_xxxx format)
    if not x_api_key.startswith("wrd_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    user_service = _get_user_service(settings)
    user = user_service.get_user_by_api_key(x_api_key)
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def verify_api_key_or_query(
    x_api_key: Optional[str] = Header(None, description="API key for authentication"),
    api_key: Optional[str] = Query(None, description="API key as query parameter"),
    settings: Settings = Depends(get_settings),
) -> User:
    """Verify API key from header or query parameter (for image loading in browser)."""
    key = x_api_key or api_key
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    if not key.startswith("wrd_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    user_service = _get_user_service(settings)
    user = user_service.get_user_by_api_key(key)
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="session_token"),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Get the current authenticated user from session cookie.

    Used for web UI authentication (not API).
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_service = _get_user_service(settings)
    user = user_service.get_user_by_session(session_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    return user


async def get_current_user_optional(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias="session_token"),
    settings: Settings = Depends(get_settings),
) -> Optional[User]:
    """
    Get the current user if authenticated, otherwise return None.

    Used for pages that work with or without authentication.
    """
    if not session_token:
        return None

    user_service = _get_user_service(settings)
    return user_service.get_user_by_session(session_token)
