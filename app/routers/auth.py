import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, get_current_user_optional
from app.config import Settings, get_settings
from app.models.user import OAuthLinkCreate, User
from app.services.user_service import get_user_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

templates = Jinja2Templates(directory="app/templates")


# ==================== Login Routes ====================


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    next: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user_optional),
):
    """Show login page with OAuth and email options."""
    # If already logged in, redirect to post-login setup
    if user:
        return RedirectResponse(url="/post-login", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error, "next": next or "/"},
    )


@router.post("/login")
async def login_with_passcode(
    request: Request,
    email: str = Form(...),
    passcode: str = Form(...),
    next: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
):
    """Process email + passcode login."""
    user_service = get_user_service(settings)
    user = user_service.authenticate_user(email, passcode)

    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid email or passcode", "next": next or "/"},
            status_code=401,
        )

    # Create session
    session_token = user_service.create_session(user.id)

    # Redirect to post-login setup (or next URL if specified)
    redirect_url = next if next and next.startswith("/") else "/post-login"
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=86400 if not settings.dev_mode else 300,  # 24h or 5min in dev
        samesite="strict",
    )

    logger.info(f"User logged in: {user.email}")
    return response


@router.get("/logout")
async def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Log out and clear session."""
    session_token = request.cookies.get("session_token")

    if session_token:
        user_service = get_user_service(settings)
        user_service.delete_session(session_token)

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response


@router.get("/post-login", response_class=HTMLResponse)
async def post_login_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Post-login page that sets up API key in localStorage."""
    return templates.TemplateResponse(request, "post_login.html", {})


@router.post("/api/keys/ensure")
async def ensure_api_key(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Get existing API key or create a new one for the current user."""
    from app.models.user import APIKeyCreate

    user_service = get_user_service(settings)

    # Check if user already has an active API key
    existing_keys = user_service.get_api_keys_for_user(user.id)
    active_keys = [k for k in existing_keys if k.is_active]

    if active_keys:
        # User has existing keys, but we can't retrieve the full key
        # We need to create a new one and return it
        pass

    # Create a new API key for web access
    key_response = user_service.create_api_key(
        user.id,
        APIKeyCreate(name="Web Access (auto-generated)")
    )

    return {"key": key_response.key}


# ==================== OAuth Login Routes ====================


@router.get("/login/google")
async def google_login(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Redirect to Google OAuth for login."""
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured",
        )

    # Build OAuth URL
    from urllib.parse import urlencode

    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": str(request.url_for("google_login_callback")),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }

    # In dev mode, force consent screen
    if settings.dev_mode:
        params["prompt"] = "consent"

    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=oauth_url, status_code=303)


@router.get("/login/google/callback")
async def google_login_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    settings: Settings = Depends(get_settings),
):
    """Handle Google OAuth callback for login."""
    if error:
        return RedirectResponse(url=f"/login?error={error}", status_code=303)

    if not code:
        return RedirectResponse(url="/login?error=No+authorization+code", status_code=303)

    try:
        # Exchange code for tokens
        import httpx

        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": str(request.url_for("google_login_callback")),
                "grant_type": "authorization_code",
            },
        )
        token_data = token_response.json()

        if "error" in token_data:
            logger.error(f"Google OAuth token error: {token_data}")
            err_msg = token_data.get('error_description', token_data['error'])
            return RedirectResponse(
                url=f"/login?error=OAuth+failed:+{err_msg}",
                status_code=303,
            )

        # Get user info
        access_token = token_data["access_token"]
        userinfo_response = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo = userinfo_response.json()

        provider_user_id = userinfo["id"]

        # Look up user by OAuth link
        user_service = get_user_service(settings)
        user = user_service.get_user_by_oauth("google", provider_user_id)

        if not user:
            return RedirectResponse(
                url="/login?error=No+account+linked+to+this+Google+account",
                status_code=303,
            )

        # Create session
        session_token = user_service.create_session(user.id)

        response = RedirectResponse(url="/post-login", status_code=303)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            max_age=86400 if not settings.dev_mode else 300,
            samesite="strict",
        )

        logger.info(f"User logged in via Google: {user.email}")
        return response

    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(
            url="/login?error=OAuth+failed",
            status_code=303,
        )


# ==================== OAuth Linking Routes ====================


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Show user settings page with OAuth linking options."""
    user_service = get_user_service(settings)
    oauth_links = user_service.get_oauth_links_for_user(user.id)
    api_keys = user_service.get_api_keys_for_user(user.id)

    # Check which providers are linked
    linked_providers = {link.provider for link in oauth_links}

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "oauth_links": oauth_links,
            "api_keys": api_keys,
            "google_linked": "google" in linked_providers,
            "google_available": bool(settings.google_oauth_client_id),
        },
    )


@router.get("/settings/link/google")
async def link_google(
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Redirect to Google OAuth for linking."""
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    from urllib.parse import urlencode

    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": str(request.url_for("link_google_callback")),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",  # Always show consent for linking
    }

    oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=oauth_url, status_code=303)


@router.get("/settings/link/google/callback")
async def link_google_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Handle Google OAuth callback for linking."""
    if error:
        return RedirectResponse(url=f"/settings?error={error}", status_code=303)

    if not code:
        return RedirectResponse(url="/settings?error=No+authorization+code", status_code=303)

    try:
        import httpx

        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": str(request.url_for("link_google_callback")),
                "grant_type": "authorization_code",
            },
        )
        token_data = token_response.json()

        if "error" in token_data:
            return RedirectResponse(
                url="/settings?error=OAuth+failed",
                status_code=303,
            )

        access_token = token_data["access_token"]
        userinfo_response = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo = userinfo_response.json()

        # Create OAuth link
        user_service = get_user_service(settings)
        user_service.create_oauth_link(
            user.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id=userinfo["id"],
                provider_email=userinfo.get("email"),
            ),
        )

        logger.info(f"User {user.email} linked Google account")
        return RedirectResponse(url="/settings?success=Google+linked", status_code=303)

    except Exception as e:
        logger.error(f"Google link error: {e}")
        return RedirectResponse(url="/settings?error=Link+failed", status_code=303)


@router.post("/settings/unlink/{provider}")
async def unlink_oauth(
    provider: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Unlink an OAuth provider."""
    if provider != "google":
        raise HTTPException(status_code=400, detail="Invalid provider")

    user_service = get_user_service(settings)
    success = user_service.delete_oauth_link(user.id, provider)

    if success:
        logger.info(f"User {user.email} unlinked {provider}")

    return RedirectResponse(url="/settings", status_code=303)
