from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter(tags=["Web"])

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    return (TEMPLATES_DIR / "login.html").read_text()


@router.get("/wardrobe", response_class=HTMLResponse)
async def wardrobe_page(request: Request):
    """Serve the main wardrobe page."""
    return (TEMPLATES_DIR / "wardrobe.html").read_text()
