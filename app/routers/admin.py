import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
    """Verify admin session from cookie.

    Uses ADMIN_PASSWORD for admin panel access.
    Falls back to api_key for backwards compatibility if admin_password not set.
    """
    if not admin_token:
        return False

    # Use admin_password if set, otherwise fall back to api_key
    expected_password = settings.admin_password or settings.api_key
    if not expected_password:
        return False

    return admin_token == expected_password


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
    password: str = Form(..., alias="api_key"),  # Keep form field name for backwards compat
    next: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
):
    """Process admin login form."""
    expected_password = settings.admin_password or settings.api_key
    if expected_password and password == expected_password:
        # Redirect to next URL or default to /admin
        redirect_url = next if next and next.startswith("/admin") else "/admin"
        response = RedirectResponse(url=redirect_url, status_code=303)
        response.set_cookie(
            key="admin_token",
            value=password,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax",  # "strict" breaks POST->redirect->GET flow
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

    from app.services.storage import get_storage_service

    db = get_database_service(settings)
    storage = get_storage_service(settings)

    # Get stats
    try:
        item_count = db.get_item_count()
        image_count = storage.count_images_on_disk()
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


@router.get("/health", response_class=HTMLResponse)
async def health_dashboard(
    request: Request,
    authenticated: bool = Depends(verify_admin_session),
):
    """Render health monitoring dashboard."""
    if not authenticated:
        return RedirectResponse(url="/admin/login?next=/admin/health", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_health.html",
        {},
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


# Log source definitions
LOG_SOURCES = {
    # Docker containers
    "wardrobe-api": {"type": "docker", "label": "API Container", "group": "Docker"},
    "wardrobe-db": {"type": "docker", "label": "Database Container", "group": "Docker"},
    "wardrobe-clamav": {"type": "docker", "label": "ClamAV Container", "group": "Docker"},
    "wardrobe-nginx": {"type": "docker", "label": "Nginx Container", "group": "Docker"},
    # Nginx log files
    "nginx-access": {"type": "file", "path": "/var/log/nginx/access.log", "label": "Nginx Access", "group": "Nginx"},
    "nginx-error": {"type": "file", "path": "/var/log/nginx/error.log", "label": "Nginx Errors", "group": "Nginx"},
    "nginx-blocked": {"type": "file", "path": "/var/log/nginx/blocked.log", "label": "Nginx Blocked", "group": "Nginx"},
}


def _read_docker_logs(
    container: str, lines: int, search: Optional[str]
) -> tuple[list[str], Optional[str]]:
    """Read logs from a Docker container."""
    import subprocess

    try:
        # Use 2>&1 to merge stderr into stdout so we get all logs together
        result = subprocess.run(
            f"docker logs --tail {lines} {container} 2>&1",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout
        all_lines = output.strip().split("\n") if output.strip() else []
        all_lines.reverse()

        if search:
            all_lines = [line for line in all_lines if search.lower() in line.lower()]

        return all_lines, None

    except subprocess.TimeoutExpired:
        return [], "Timeout reading Docker logs"
    except FileNotFoundError:
        return [], "Docker CLI not available"
    except Exception as e:
        logger.error(f"Docker logs error: {e}")
        return [], f"Error reading Docker logs: {e}"


def _read_file_logs(
    filepath: str, lines: int, search: Optional[str]
) -> tuple[list[str], Optional[str]]:
    """Read logs from a file (tail -n style)."""
    from collections import deque

    try:
        log_path = Path(filepath)
        if not log_path.exists():
            return [], f"Log file not found: {filepath}"

        # Read last N lines efficiently
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = deque(f, maxlen=lines)

        result = list(all_lines)
        result = [line.rstrip() for line in result]
        result.reverse()  # Newest first

        if search:
            result = [line for line in result if search.lower() in line.lower()]

        return result, None

    except PermissionError:
        return [], f"Permission denied: {filepath}"
    except Exception as e:
        logger.error(f"File logs error: {e}")
        return [], f"Error reading log file: {e}"


@router.get("/logs", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    source: str = Query("wardrobe-api"),
    lines: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    authenticated: bool = Depends(verify_admin_session),
):
    """View logs from Docker containers or log files."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    # Validate source
    if source not in LOG_SOURCES:
        source = "wardrobe-api"  # Default

    source_info = LOG_SOURCES[source]

    # Read logs based on source type
    if source_info["type"] == "docker":
        log_lines, error_message = _read_docker_logs(source, lines, search)
    elif source_info["type"] == "file":
        log_lines, error_message = _read_file_logs(source_info["path"], lines, search)
    else:
        log_lines, error_message = [], f"Unknown source type: {source_info['type']}"

    return templates.TemplateResponse(
        request,
        "admin_logs.html",
        {
            "log_lines": log_lines,
            "lines": lines,
            "search": search or "",
            "total_lines": len(log_lines),
            "source": source,
            "sources": LOG_SOURCES,
            "source_label": source_info["label"],
            "error_message": error_message,
        },
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


@router.get("/openapi-chatgpt.json", include_in_schema=False)
async def get_chatgpt_openapi(
    request: Request,
    authenticated: bool = Depends(verify_admin_session),
):
    """
    Get OpenAPI spec filtered for ChatGPT GPT Actions.

    Includes only the core wardrobe API endpoints (items, images),
    excluding admin panel, web UI, and OAuth routes.
    ChatGPT Actions has a limit of 30 actions - this returns 12.
    """
    if not authenticated:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Admin authentication required")

    from fastapi.openapi.utils import get_openapi

    # Get the full OpenAPI spec - need to access the app
    app = request.app
    openapi_schema = get_openapi(
        title="Wardrobe Architect API",
        version="1.0.0",
        description="API for managing wardrobe items and images. For ChatGPT GPT Actions.",
        routes=app.routes,
    )

    # Paths to INCLUDE (ChatGPT-relevant endpoints only)
    chatgpt_paths = {
        # Item operations
        "/items": ["get", "post"],
        "/items/{item_id}": ["get", "put", "delete"],
        # Image operations
        "/items/{item_id}/images": ["get", "post"],
        "/items/{item_id}/images/from-url": ["post"],  # Single URL upload
        "/items/{item_id}/images/from-urls": ["post"],  # Batch URL upload
        "/items/{item_id}/images/order": ["put"],
        "/images/{image_id}": ["get", "delete"],
        "/images/{image_id}/crop": ["put"],
        # Utility
        "/health": ["get"],
    }

    # Simple operation IDs for ChatGPT
    operation_ids = {
        ("/items", "get"): "listItems",
        ("/items", "post"): "createItem",
        ("/items/{item_id}", "get"): "getItem",
        ("/items/{item_id}", "put"): "updateItem",
        ("/items/{item_id}", "delete"): "deleteItem",
        ("/items/{item_id}/images", "get"): "listImages",
        ("/items/{item_id}/images", "post"): "uploadImage",
        ("/items/{item_id}/images/from-url", "post"): "uploadImageFromUrl",
        ("/items/{item_id}/images/from-urls", "post"): "uploadImagesFromUrls",
        ("/items/{item_id}/images/order", "put"): "reorderImages",
        ("/images/{image_id}", "get"): "getImage",
        ("/images/{image_id}", "delete"): "deleteImage",
        ("/images/{image_id}/crop", "put"): "setCrop",
        ("/health", "get"): "healthCheck",
    }

    # Filter paths
    filtered_paths = {}
    for path, methods in chatgpt_paths.items():
        if path in openapi_schema.get("paths", {}):
            filtered_paths[path] = {
                method: openapi_schema["paths"][path][method]
                for method in methods
                if method in openapi_schema["paths"][path]
            }

    openapi_schema["paths"] = filtered_paths

    # Update info for ChatGPT
    openapi_schema["info"]["title"] = "Wardrobe Architect"
    openapi_schema["info"]["description"] = (
        "Manage your wardrobe items and images. "
        "Create, update, delete clothing items and upload photos."
    )

    # Add server URL (derived from request)
    scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    host = request.headers.get("X-Forwarded-Host", request.headers.get("Host", request.url.netloc))
    openapi_schema["servers"] = [{"url": f"{scheme}://{host}"}]

    # Add security scheme
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }

    # Apply security, simple operation IDs, and remove x-api-key parameter
    for path, methods in openapi_schema["paths"].items():
        for method in methods:
            if method in ["get", "post", "put", "delete", "patch"]:
                # Set simple operation ID
                if (path, method) in operation_ids:
                    openapi_schema["paths"][path][method]["operationId"] = operation_ids[(path, method)]
                # Remove x-api-key parameter if present
                if "parameters" in openapi_schema["paths"][path][method]:
                    openapi_schema["paths"][path][method]["parameters"] = [
                        p for p in openapi_schema["paths"][path][method]["parameters"]
                        if p.get("name") != "x-api-key"
                    ]
                # Add security requirement (except /health)
                if path != "/health":
                    openapi_schema["paths"][path][method]["security"] = [{"ApiKeyAuth": []}]

    # Remove unnecessary tags
    chatgpt_tags = {"Items", "Images", "Utility"}
    if "tags" in openapi_schema:
        openapi_schema["tags"] = [
            tag for tag in openapi_schema["tags"]
            if tag.get("name") in chatgpt_tags
        ]

    return openapi_schema


# ==================== User Management ====================


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """List all users."""
    if not authenticated:
        return RedirectResponse(url="/admin/login?next=/admin/users", status_code=303)

    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)
    users = user_service.get_all_users()

    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {"users": users, "total_users": len(users)},
    )


@router.get("/users/new", response_class=HTMLResponse)
async def new_user_form(
    request: Request,
    error: Optional[str] = None,
    authenticated: bool = Depends(verify_admin_session),
):
    """Show form to create new user."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin_user_new.html",
        {"error": error},
    )


@router.post("/users/new")
async def create_user(
    request: Request,
    email: str = Form(...),
    passcode: str = Form(...),
    display_name: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Create a new user."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if len(passcode) < 8:
        return templates.TemplateResponse(
            request,
            "admin_user_new.html",
            {"error": "Passcode must be at least 8 characters"},
            status_code=400,
        )

    from app.models.user import UserCreate
    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        user = user_service.create_user(
            UserCreate(email=email, passcode=passcode, display_name=display_name)
        )
        logger.info(f"Admin created user: {email}")
        return RedirectResponse(
            url=f"/admin/users/{user.id}?success=User+created",
            status_code=303,
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return templates.TemplateResponse(
            request,
            "admin_user_new.html",
            {"error": str(e)},
            status_code=400,
        )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    request: Request,
    user_id: str,
    success: Optional[str] = None,
    error: Optional[str] = None,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """View user details and API keys."""
    if not authenticated:
        return RedirectResponse(url="/admin/login", status_code=303)

    from uuid import UUID

    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        user = user_service.get_user_by_id(UUID(user_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    api_keys = user_service.get_api_keys_for_user(user.id)
    oauth_links = user_service.get_oauth_links_for_user(user.id)

    return templates.TemplateResponse(
        request,
        "admin_user_detail.html",
        {
            "user": user,
            "api_keys": api_keys,
            "oauth_links": oauth_links,
            "success": success,
            "error": error,
        },
    )


@router.post("/users/{user_id}/api-key")
async def create_api_key_for_user(
    request: Request,
    user_id: str,
    name: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Generate a new API key for a user."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from uuid import UUID

    from app.models.user import APIKeyCreate
    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    key_response = user_service.create_api_key(uid, APIKeyCreate(name=name))
    logger.info(f"Admin created API key for user {user_id}: {key_response.key[:8]}...")

    # Return the key in a template that shows it once
    return templates.TemplateResponse(
        request,
        "admin_api_key_created.html",
        {"api_key": key_response.key, "user_id": user_id},
    )


@router.post("/users/{user_id}/api-key/{key_id}/revoke")
async def revoke_api_key(
    user_id: str,
    key_id: str,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Revoke an API key."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from uuid import UUID

    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        user_service.revoke_api_key(UUID(key_id))
        logger.info(f"Admin revoked API key {key_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error revoking API key: {e}")

    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=API+key+revoked",
        status_code=303,
    )


@router.post("/users/{user_id}/reset-passcode")
async def reset_user_passcode(
    request: Request,
    user_id: str,
    new_passcode: str = Form(...),
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Reset a user's passcode."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if len(new_passcode) < 8:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=Passcode+must+be+8+characters",
            status_code=303,
        )

    from uuid import UUID

    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        user_service.reset_passcode(UUID(user_id), new_passcode)
        logger.info(f"Admin reset passcode for user {user_id}")
    except Exception as e:
        logger.error(f"Error resetting passcode: {e}")
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=Failed+to+reset+passcode",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=Passcode+reset",
        status_code=303,
    )


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    settings: Settings = Depends(get_settings),
    authenticated: bool = Depends(verify_admin_session),
):
    """Enable or disable a user."""
    if not authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from uuid import UUID

    from app.models.user import UserUpdate
    from app.services.user_service import get_user_service

    user_service = get_user_service(settings)

    try:
        uid = UUID(user_id)
        user = user_service.get_user_by_id(uid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Toggle active status
        user_service.update_user(uid, UserUpdate(is_active=not user.is_active))
        status = "enabled" if not user.is_active else "disabled"
        logger.info(f"Admin {status} user {user_id}")
    except Exception as e:
        logger.error(f"Error toggling user active: {e}")

    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=User+{status}",
        status_code=303,
    )
