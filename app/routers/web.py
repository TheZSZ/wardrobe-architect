from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path

router = APIRouter(tags=["Web"])

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@router.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    """Redirect root to login page."""
    return RedirectResponse(url="/login", status_code=303)


@router.get("/wardrobe", response_class=HTMLResponse)
async def wardrobe_page(request: Request):
    """Serve the main wardrobe page."""
    return (TEMPLATES_DIR / "wardrobe.html").read_text()
