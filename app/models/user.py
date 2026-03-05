from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """User model for authenticated users."""

    id: UUID
    email: EmailStr
    display_name: Optional[str] = None
    google_sheet_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None


class UserCreate(BaseModel):
    """Model for creating a new user (admin only)."""

    email: EmailStr
    passcode: str = Field(..., min_length=8)
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    """Model for updating user info."""

    display_name: Optional[str] = None
    google_sheet_id: Optional[str] = None
    is_active: Optional[bool] = None


class PasscodeChange(BaseModel):
    """Model for changing passcode."""

    current_passcode: str
    new_passcode: str = Field(..., min_length=8)


class PasscodeReset(BaseModel):
    """Model for admin resetting a user's passcode."""

    new_passcode: str = Field(..., min_length=8)


class OAuthLink(BaseModel):
    """OAuth provider link for a user."""

    id: UUID
    user_id: UUID
    provider: str  # 'google' or 'apple'
    provider_user_id: str
    provider_email: Optional[str] = None
    linked_at: datetime


class OAuthLinkCreate(BaseModel):
    """Model for creating an OAuth link."""

    provider: str
    provider_user_id: str
    provider_email: Optional[str] = None


class APIKey(BaseModel):
    """API key model (without the actual key)."""

    id: UUID
    user_id: UUID
    key_prefix: str  # First 8 chars for identification
    name: Optional[str] = None
    created_at: datetime
    last_used: Optional[datetime] = None
    is_active: bool = True


class APIKeyCreate(BaseModel):
    """Model for creating an API key."""

    name: Optional[str] = None


class APIKeyResponse(BaseModel):
    """Response when creating an API key (includes full key, shown only once)."""

    key: str  # Full key (wrd_xxxxxxxxxxxx)
    id: UUID
    name: Optional[str] = None


class Session(BaseModel):
    """User session model."""

    id: UUID
    user_id: UUID
    session_token: str
    created_at: datetime
    expires_at: datetime


class LoginRequest(BaseModel):
    """Email + passcode login request."""

    email: EmailStr
    passcode: str
