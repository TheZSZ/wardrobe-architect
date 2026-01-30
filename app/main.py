import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.routers import items, images, web, admin
from app.config import Settings, get_settings
from app.logging_config import setup_logging
from app.services.database import get_database_service

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    settings = get_settings()

    # Log startup mode
    if settings.dummy_mode:
        logger.info("Starting in DUMMY MODE (no Google Sheets connection)")
    else:
        logger.info("Starting in NORMAL MODE (Google Sheets enabled)")

    # Check database connection
    try:
        db = get_database_service(settings)
        if db.is_connected():
            item_count = db.get_item_count()
            image_count = db.get_image_count()
            logger.info(
                f"Database connected: {item_count} items, {image_count} images"
            )
        else:
            logger.error("Database connection FAILED")
    except Exception as e:
        logger.error(f"Database connection error: {e}")

    # Check Google Sheets connection (only in normal mode)
    if not settings.dummy_mode:
        try:
            from app.services.sheets import get_sheets_service
            sheets = get_sheets_service(settings)
            # Try to access the sheet to verify connection
            sheets._get_sheet()
            logger.info(
                f"Google Sheets connected: sheet ID {settings.google_sheet_id[:8]}..."
            )

            # Sync on startup if configured
            if settings.sync_on_startup:
                count = sheets.sync_to_db()
                logger.info(f"Startup sync completed: {count} items synced")
        except Exception as e:
            logger.error(f"Google Sheets connection FAILED: {e}")

    yield  # Application runs here

    # Shutdown
    logger.info("Application shutting down")


app = FastAPI(
    title="Wardrobe Architect API",
    description="API for managing wardrobe items and images, designed for GPT Actions integration",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # Disable default docs, served via /admin/docs
    redoc_url=None,  # Disable default redoc, served via /admin/redoc
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
app.include_router(admin.router)

# Coverage report is served through admin router (requires auth)


# Redirect /docs and /redoc to admin-protected versions
@app.get("/docs", include_in_schema=False)
async def docs_redirect():
    """Redirect to admin-protected docs."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/docs", status_code=303)


@app.get("/redoc", include_in_schema=False)
async def redoc_redirect():
    """Redirect to admin-protected redoc."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/redoc", status_code=303)


@app.get("/health", tags=["Utility"])
async def health_check(settings: Settings = Depends(get_settings)):
    """Health check endpoint with system stats - no authentication required."""
    import psutil
    from pathlib import Path

    # Basic status
    health = {
        "status": "healthy",
        "mode": "dummy" if settings.dummy_mode else "normal",
    }

    # Database status
    try:
        db = get_database_service(settings)
        db_connected = db.is_connected()
        health["database"] = {
            "connected": db_connected,
            "items": db.get_item_count() if db_connected else 0,
            "images": db.get_image_count() if db_connected else 0,
        }
        if not db_connected:
            health["status"] = "degraded"
    except Exception as e:
        health["database"] = {"connected": False, "error": str(e)}
        health["status"] = "degraded"

    # Disk usage
    try:
        images_dir = Path(settings.images_dir)
        if images_dir.exists():
            images_size = sum(
                f.stat().st_size for f in images_dir.rglob('*') if f.is_file()
            )
            images_size_mb = round(images_size / (1024 * 1024), 2)
        else:
            images_size_mb = 0

        disk = psutil.disk_usage('/')
        health["disk"] = {
            "total_gb": round(disk.total / (1024 ** 3), 2),
            "used_gb": round(disk.used / (1024 ** 3), 2),
            "free_gb": round(disk.free / (1024 ** 3), 2),
            "percent_used": disk.percent,
            "images_mb": images_size_mb,
        }
    except Exception as e:
        health["disk"] = {"error": str(e)}

    # Memory usage
    try:
        mem = psutil.virtual_memory()
        health["memory"] = {
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "used_gb": round(mem.used / (1024 ** 3), 2),
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "percent_used": mem.percent,
        }
    except Exception as e:
        health["memory"] = {"error": str(e)}

    # CPU usage
    try:
        health["cpu"] = {
            "percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count(),
        }
    except Exception as e:
        health["cpu"] = {"error": str(e)}

    # Process info
    try:
        proc = psutil.Process()
        health["process"] = {
            "memory_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
            "cpu_percent": proc.cpu_percent(),
            "threads": proc.num_threads(),
            "uptime_seconds": round(
                (psutil.time.time() - proc.create_time()), 0
            ),
        }
    except Exception as e:
        health["process"] = {"error": str(e)}

    return health


@app.get("/config", tags=["Utility"])
async def get_config(settings: Settings = Depends(get_settings)):
    """Get public configuration - no authentication required."""
    return {"dummy_mode": settings.dummy_mode}


if __name__ == "__main__":
    import uvicorn
    from app.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
