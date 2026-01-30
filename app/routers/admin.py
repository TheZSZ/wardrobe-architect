import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Form, Cookie
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.services.database import get_database_service
from app.services.sheets import get_sheets_service, SheetsService

HTMLCOV_DIR = Path(__file__).parent.parent.parent / "htmlcov"

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)

templates = Jinja2Templates(directory="app/templates")


def verify_admin_session(
    request: Request,
    admin_token: Optional[str] = Cookie(None),
    settings: Settings = Depends(get_settings),
) -> bool:
    """Verify admin session from cookie."""
    if not admin_token:
        return False
    return admin_token == settings.api_key


def get_sheets(settings: Settings = Depends(get_settings)) -> SheetsService:
    return get_sheets_service(settings)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    next: Optional[str] = Query(None, alias="next"),
):
    """Render login page."""
    return templates.TemplateResponse(
        request, "admin_login.html", {"error": error, "next": next or ""}
    )


@router.post("/login")
async def login(
    request: Request,
    api_key: str = Form(...),
    next: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
):
    """Process login form."""
    if api_key == settings.api_key:
        # Redirect to next URL or default to /admin
        redirect_url = next if next and next.startswith("/admin") else "/admin"
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(
            key="admin_token",
            value=api_key,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="strict",
        )
        return response
    else:
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {"error": "Invalid API key", "next": next or ""},
            status_code=401,
        )


@router.get("/logout")
async def logout():
    """Log out and clear session."""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Render admin dashboard page."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    db = get_database_service(settings)

    # Get stats
    try:
        item_count = db.get_item_count()
        image_count = db.get_image_count()
        last_sync = db.get_last_sync()
        db_connected = db.is_connected()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        item_count = 0
        image_count = 0
        last_sync = None
        db_connected = False

    # Get disk usage
    images_dir = Path(settings.images_dir)
    if images_dir.exists():
        disk_used = sum(f.stat().st_size for f in images_dir.rglob('*') if f.is_file())
        disk_used_mb = disk_used / (1024 * 1024)
    else:
        disk_used_mb = 0

    # Get recent logs
    recent_logs = []
    log_file = Path(settings.log_file)
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_logs = [line.strip() for line in reversed(lines[-50:])]
        except Exception as e:
            logger.error(f"Error reading logs: {e}")

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "item_count": item_count,
            "image_count": image_count,
            "disk_used_mb": round(disk_used_mb, 2),
            "last_sync": last_sync,
            "db_connected": db_connected,
            "recent_logs": recent_logs,
            "dummy_mode": settings.dummy_mode,
        },
    )


@router.get("/db", response_class=HTMLResponse)
async def database_browser(
    request: Request,
    search: Optional[str] = None,
    category: Optional[str] = None,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """View database contents (read-only)."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    db = get_database_service(settings)

    try:
        items = db.get_all_items(category=category)
        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            items = [
                item for item in items
                if search_lower in item.item.lower()
                or search_lower in item.id.lower()
                or search_lower in (item.notes or "").lower()
            ]

        # Get all images for each item
        items_with_images = []
        for item in items:
            images = db.get_images_for_item(item.id)
            items_with_images.append({
                "item": item,
                "images": images,
            })

        # Get unique categories for filter dropdown
        all_items = db.get_all_items()
        categories = sorted(set(i.category for i in all_items if i.category))

        # Get sync history
        sync_history = db.get_sync_history(limit=10)

    except Exception as e:
        logger.error(f"Error fetching database: {e}")
        items_with_images = []
        categories = []
        sync_history = []

    return templates.TemplateResponse(
        request,
        "admin_db.html",
        {
            "items": items_with_images,
            "categories": categories,
            "search": search or "",
            "selected_category": category or "",
            "sync_history": sync_history,
            "total_items": len(items_with_images),
        },
    )


@router.get("/stats")
async def get_stats(
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Get system statistics as JSON."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    db = get_database_service(settings)

    try:
        item_count = db.get_item_count()
        image_count = db.get_image_count()
        last_sync = db.get_last_sync()
        db_connected = db.is_connected()
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        item_count = 0
        image_count = 0
        last_sync = None
        db_connected = False

    # Disk usage for images
    images_dir = Path(settings.images_dir)
    if images_dir.exists():
        disk_used = sum(f.stat().st_size for f in images_dir.rglob('*') if f.is_file())
        disk_used_gb = disk_used / (1024 * 1024 * 1024)
    else:
        disk_used_gb = 0

    # System stats
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()

    return {
        "items": item_count,
        "images": image_count,
        "disk_used_gb": round(disk_used_gb, 2),
        "last_sync": last_sync,
        "db_connected": db_connected,
        "dummy_mode": settings.dummy_mode,
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024 ** 3), 2),
        },
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    lines: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """View log file with optional search."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    log_file = Path(settings.log_file)
    log_lines = []

    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()

            # Filter by search term if provided
            if search:
                all_lines = [line for line in all_lines if search.lower() in line.lower()]

            # Get last N lines, strip whitespace, newest first
            log_lines = [line.strip() for line in reversed(all_lines[-lines:])]
        except Exception as e:
            logger.error(f"Error reading logs: {e}")

    return templates.TemplateResponse(
        request,
        "admin_logs.html",
        {
            "log_lines": log_lines,
            "lines": lines,
            "search": search or "",
            "total_lines": len(log_lines),
        },
    )


@router.get("/logs/download")
async def download_logs(
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Download the full log file."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    log_file = Path(settings.log_file)

    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        path=log_file,
        filename=f"wardrobe-api-{datetime.now().strftime('%Y%m%d')}.log",
        media_type="text/plain",
    )


@router.post("/sync")
async def trigger_sync(
    settings: Settings = Depends(get_settings),
    sheets: SheetsService = Depends(get_sheets),
    authenticated: bool = Depends(verify_admin_session),
):
    """Trigger sync from Google Sheets to database."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if settings.dummy_mode:
        raise HTTPException(
            status_code=400,
            detail="Sync not available in dummy mode (no Sheets connection)",
        )

    try:
        # Call sync method on SheetsService
        count = sheets.sync_to_db()
        logger.info(f"Admin triggered sync: {count} items synced")
        return {
            "message": f"Successfully synced {count} items from Google Sheets",
            "items_synced": count,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/logs/api")
async def get_logs_json(
    lines: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Get log lines as JSON (for AJAX refresh)."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    log_file = Path(settings.log_file)
    log_lines = []

    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()

            if search:
                all_lines = [line for line in all_lines if search.lower() in line.lower()]

            log_lines = [line.strip() for line in reversed(all_lines[-lines:])]
        except Exception as e:
            logger.error(f"Error reading logs: {e}")

    return {"lines": log_lines, "count": len(log_lines)}


NGINX_LOG_DIR = Path("/var/log/nginx")


@router.get("/logs/nginx", response_class=HTMLResponse)
async def view_nginx_logs(
    request: Request,
    log_type: str = Query("access", pattern="^(access|error)$"),
    lines: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    authenticated: bool = Depends(verify_admin_session),
):
    """View nginx access or error logs."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    log_file = NGINX_LOG_DIR / f"{log_type}.log"
    log_lines = []

    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()

            if search:
                all_lines = [line for line in all_lines if search.lower() in line.lower()]

            log_lines = [line.strip() for line in reversed(all_lines[-lines:])]
        except Exception as e:
            logger.error(f"Error reading nginx logs: {e}")

    return templates.TemplateResponse(
        request,
        "admin_logs_nginx.html",
        {
            "log_lines": log_lines,
            "lines": lines,
            "search": search or "",
            "total_lines": len(log_lines),
            "log_type": log_type,
        },
    )


@router.get("/logs/nginx/download")
async def download_nginx_logs(
    log_type: str = Query("access", pattern="^(access|error)$"),
    authenticated: bool = Depends(verify_admin_session),
):
    """Download nginx log file."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    log_file = NGINX_LOG_DIR / f"{log_type}.log"

    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"Nginx {log_type} log not found")

    return FileResponse(
        path=log_file,
        filename=f"nginx-{log_type}-{datetime.now().strftime('%Y%m%d')}.log",
        media_type="text/plain",
    )


@router.get("/coverage")
async def coverage_index(
    authenticated: bool = Depends(verify_admin_session),
):
    """Redirect to coverage index.html."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)
    return RedirectResponse(url="/admin/coverage/index.html", status_code=303)


@router.get("/coverage/{path:path}")
async def coverage_files(
    path: str,
    authenticated: bool = Depends(verify_admin_session),
):
    """Serve coverage report files (requires admin auth)."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not HTMLCOV_DIR.exists():
        raise HTTPException(status_code=404, detail="Coverage report not found")

    file_path = HTMLCOV_DIR / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: ensure path doesn't escape htmlcov directory
    try:
        file_path.resolve().relative_to(HTMLCOV_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    return Response(
        content=file_path.read_bytes(),
        media_type=mime_type or "application/octet-stream",
    )


@router.get("/docs", response_class=HTMLResponse)
async def admin_docs(
    request: Request,
    authenticated: bool = Depends(verify_admin_session),
):
    """Serve Swagger UI docs (requires admin auth)."""
    if not authenticated:
        return RedirectResponse(url="/admin/login?next=/admin/docs", status_code=303)

    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Wardrobe Architect API - Docs",
    )


@router.get("/redoc", response_class=HTMLResponse)
async def admin_redoc(
    request: Request,
    authenticated: bool = Depends(verify_admin_session),
):
    """Serve ReDoc docs (requires admin auth)."""
    if not authenticated:
        return RedirectResponse(url="/admin/login?next=/admin/redoc", status_code=303)

    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="Wardrobe Architect API - ReDoc",
    )
