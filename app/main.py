from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.routers import items, images, web
from app.config import Settings, get_settings

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Wardrobe Architect API",
    description="API for managing wardrobe items and images, designed for GPT Actions integration",
    version="1.0.0",
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - configured via CORS_ORIGINS environment variable
# For personal use, leave CORS_ORIGINS empty (same-origin only)
# For ChatGPT Actions, set CORS_ORIGINS=https://chat.openai.com
settings = get_settings()
cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,  # Don't allow credentials with specific origins for API
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

# Include routers
app.include_router(web.router)
app.include_router(items.router)
app.include_router(images.router)

# Mount coverage report if available
HTMLCOV_DIR = Path(__file__).parent.parent / "htmlcov"
if HTMLCOV_DIR.exists():
    app.mount("/coverage", StaticFiles(directory=HTMLCOV_DIR, html=True), name="coverage")


@app.get("/health", tags=["Utility"])
async def health_check():
    """Health check endpoint - no authentication required."""
    return {"status": "healthy"}


@app.get("/config", tags=["Utility"])
async def get_config(settings: Settings = Depends(get_settings)):
    """Get public configuration - no authentication required."""
    return {"dummy_mode": settings.dummy_mode}


if __name__ == "__main__":
    import uvicorn
    from app.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
