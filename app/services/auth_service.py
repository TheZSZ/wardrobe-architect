import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import Settings


# Argon2 password hasher with secure defaults
_ph = PasswordHasher()


def hash_passcode(passcode: str) -> str:
    """Hash a passcode using Argon2id."""
    return _ph.hash(passcode)


def verify_passcode(passcode: str, passcode_hash: str) -> bool:
    """Verify a passcode against its hash."""
    try:
        _ph.verify(passcode_hash, passcode)
        return True
    except VerifyMismatchError:
        return False


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        tuple: (full_key, key_hash, key_prefix)
        - full_key: The complete key to show to user once (wrd_xxxxxxxxxxxx)
        - key_hash: SHA-256 hash to store in database
        - key_prefix: First 8 chars for identification (wrd_xxxx)
    """
    # Generate 12 random chars (base62-ish from urlsafe base64)
    random_part = secrets.token_urlsafe(9)[:12]
    full_key = f"wrd_{random_part}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:8]  # "wrd_xxxx"
    return full_key, key_hash, key_prefix


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Verify an API key against its stored hash."""
    provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
    return secrets.compare_digest(provided_hash, stored_hash)


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(48)


def get_session_expiry(settings: Settings) -> datetime:
    """Get session expiry time based on dev mode."""
    if settings.dev_mode:
        # 5 minutes in dev mode
        return datetime.now() + timedelta(minutes=5)
    else:
        # 24 hours in production
        return datetime.now() + timedelta(hours=24)


class AuthService:
    """Service for authentication operations."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def hash_passcode(self, passcode: str) -> str:
        """Hash a passcode."""
        return hash_passcode(passcode)

    def verify_passcode(self, passcode: str, passcode_hash: str) -> bool:
        """Verify a passcode."""
        return verify_passcode(passcode, passcode_hash)

    def generate_api_key(self) -> tuple[str, str, str]:
        """Generate a new API key."""
        return generate_api_key()

    def verify_api_key(self, provided_key: str, stored_hash: str) -> bool:
        """Verify an API key."""
        return verify_api_key(provided_key, stored_hash)

    def generate_session_token(self) -> str:
        """Generate a session token."""
        return generate_session_token()

    def get_session_expiry(self) -> datetime:
        """Get session expiry time."""
        return get_session_expiry(self.settings)


# Singleton instance
_auth_service: Optional[AuthService] = None


def get_auth_service(settings: Settings) -> AuthService:
    """Get or create the auth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService(settings)
    return _auth_service
