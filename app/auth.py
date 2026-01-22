from fastapi import Header, HTTPException, status, Depends
from app.config import Settings, get_settings


async def verify_api_key(
    x_api_key: str = Header(..., description="API key for authentication"),
    settings: Settings = Depends(get_settings),
) -> str:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
