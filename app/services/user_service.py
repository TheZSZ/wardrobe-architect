import hashlib
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.config import Settings
from app.models.user import (
    APIKey,
    APIKeyCreate,
    APIKeyResponse,
    OAuthLink,
    OAuthLinkCreate,
    User,
    UserCreate,
    UserUpdate,
)
from app.services.auth_service import (
    generate_api_key,
    generate_session_token,
    get_session_expiry,
    hash_passcode,
    verify_passcode,
)
from app.services.database import get_database_service

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._db = None

    @property
    def db(self):
        """Lazy load database service."""
        if self._db is None:
            self._db = get_database_service(self.settings)
        return self._db

    # ==================== User CRUD ====================

    def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        passcode_hash = hash_passcode(user_data.passcode)

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (email, passcode_hash, display_name)
                VALUES (%s, %s, %s)
                RETURNING id, email, display_name, google_sheet_id,
                          is_active, created_at, last_login
                """,
                (user_data.email, passcode_hash, user_data.display_name),
            )
            row = cursor.fetchone()

        logger.info(f"Created user: {user_data.email}")
        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get a user by ID."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, google_sheet_id, is_active, created_at, last_login
                FROM users WHERE id = %s
                """,
                (str(user_id),),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, google_sheet_id, is_active, created_at, last_login
                FROM users WHERE LOWER(email) = LOWER(%s)
                """,
                (email,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def get_all_users(self) -> list[User]:
        """Get all users."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, display_name, google_sheet_id, is_active, created_at, last_login
                FROM users ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()

        return [
            User(
                id=row["id"],
                email=row["email"],
                display_name=row["display_name"],
                google_sheet_id=row["google_sheet_id"],
                is_active=row["is_active"],
                created_at=row["created_at"],
                last_login=row["last_login"],
            )
            for row in rows
        ]

    def update_user(self, user_id: UUID, user_data: UserUpdate) -> Optional[User]:
        """Update a user."""
        updates = []
        params = []

        if user_data.display_name is not None:
            updates.append("display_name = %s")
            params.append(user_data.display_name)
        if user_data.google_sheet_id is not None:
            updates.append("google_sheet_id = %s")
            params.append(user_data.google_sheet_id)
        if user_data.is_active is not None:
            updates.append("is_active = %s")
            params.append(user_data.is_active)

        if not updates:
            return self.get_user_by_id(user_id)

        params.append(str(user_id))

        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE users SET {', '.join(updates)}
                WHERE id = %s
                RETURNING id, email, display_name, google_sheet_id,
                          is_active, created_at, last_login
                """,
                params,
            )
            row = cursor.fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def reset_passcode(self, user_id: UUID, new_passcode: str) -> bool:
        """Reset a user's passcode (admin function)."""
        passcode_hash = hash_passcode(new_passcode)

        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET passcode_hash = %s WHERE id = %s RETURNING id",
                (passcode_hash, str(user_id)),
            )
            result = cursor.fetchone()

        return result is not None

    def delete_user(self, user_id: UUID) -> bool:
        """Delete a user and all associated data."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM users WHERE id = %s RETURNING id",
                (str(user_id),),
            )
            result = cursor.fetchone()

        if result:
            logger.info(f"Deleted user: {user_id}")
        return result is not None

    # ==================== Authentication ====================

    def authenticate_user(self, email: str, passcode: str) -> Optional[User]:
        """Authenticate a user with email and passcode."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, passcode_hash, display_name, google_sheet_id,
                       is_active, created_at, last_login
                FROM users WHERE LOWER(email) = LOWER(%s)
                """,
                (email,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        if not row["is_active"]:
            return None

        if not verify_passcode(passcode, row["passcode_hash"]):
            return None

        # Update last login
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET last_login = NOW() WHERE id = %s",
                (str(row["id"]),),
            )

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=datetime.now(),
        )

    def create_session(self, user_id: UUID) -> str:
        """Create a new session for a user."""
        token = generate_session_token()
        expires_at = get_session_expiry(self.settings)

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_sessions (user_id, session_token, expires_at)
                VALUES (%s, %s, %s)
                """,
                (str(user_id), token, expires_at),
            )

        return token

    def get_user_by_session(self, session_token: str) -> Optional[User]:
        """Get a user by session token."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.display_name, u.google_sheet_id,
                       u.is_active, u.created_at, u.last_login
                FROM users u
                JOIN user_sessions s ON u.id = s.user_id
                WHERE s.session_token = %s AND s.expires_at > NOW() AND u.is_active = TRUE
                """,
                (session_token,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def delete_session(self, session_token: str) -> bool:
        """Delete a session (logout)."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_sessions WHERE session_token = %s RETURNING id",
                (session_token,),
            )
            result = cursor.fetchone()

        return result is not None

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_sessions WHERE expires_at < NOW()"
            )
            return cursor.rowcount

    # ==================== API Keys ====================

    def create_api_key(self, user_id: UUID, key_data: APIKeyCreate) -> APIKeyResponse:
        """Create a new API key for a user."""
        full_key, key_hash, key_prefix = generate_api_key()

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_keys (user_id, key_hash, key_prefix, name)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (str(user_id), key_hash, key_prefix, key_data.name),
            )
            row = cursor.fetchone()

        logger.info(f"Created API key for user {user_id}: {key_prefix}...")
        return APIKeyResponse(key=full_key, id=row["id"], name=key_data.name)

    def get_api_keys_for_user(self, user_id: UUID) -> list[APIKey]:
        """Get all API keys for a user (without the actual key)."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, key_prefix, name, created_at, last_used, is_active
                FROM api_keys WHERE user_id = %s ORDER BY created_at DESC
                """,
                (str(user_id),),
            )
            rows = cursor.fetchall()

        return [
            APIKey(
                id=row["id"],
                user_id=row["user_id"],
                key_prefix=row["key_prefix"],
                name=row["name"],
                created_at=row["created_at"],
                last_used=row["last_used"],
                is_active=row["is_active"],
            )
            for row in rows
        ]

    def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get the user associated with an API key."""
        if not api_key.startswith("wrd_"):
            return None

        key_prefix = api_key[:8]
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.display_name, u.google_sheet_id,
                       u.is_active, u.created_at, u.last_login, ak.id as key_id
                FROM users u
                JOIN api_keys ak ON u.id = ak.user_id
                WHERE ak.key_prefix = %s AND ak.key_hash = %s
                      AND ak.is_active = TRUE AND u.is_active = TRUE
                """,
                (key_prefix, key_hash),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Update last_used timestamp
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE api_keys SET last_used = NOW() WHERE id = %s",
                (str(row["key_id"]),),
            )

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    def revoke_api_key(self, key_id: UUID) -> bool:
        """Revoke an API key."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE api_keys SET is_active = FALSE WHERE id = %s RETURNING id",
                (str(key_id),),
            )
            result = cursor.fetchone()

        return result is not None

    def delete_api_key(self, key_id: UUID) -> bool:
        """Permanently delete an API key."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM api_keys WHERE id = %s RETURNING id",
                (str(key_id),),
            )
            result = cursor.fetchone()

        return result is not None

    # ==================== OAuth Links ====================

    def create_oauth_link(self, user_id: UUID, link_data: OAuthLinkCreate) -> OAuthLink:
        """Create an OAuth link for a user."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO oauth_links (user_id, provider, provider_user_id, provider_email)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, provider, provider_user_id, provider_email, linked_at
                """,
                (
                    str(user_id),
                    link_data.provider,
                    link_data.provider_user_id,
                    link_data.provider_email,
                ),
            )
            row = cursor.fetchone()

        logger.info(f"Linked {link_data.provider} OAuth for user {user_id}")
        return OAuthLink(
            id=row["id"],
            user_id=row["user_id"],
            provider=row["provider"],
            provider_user_id=row["provider_user_id"],
            provider_email=row["provider_email"],
            linked_at=row["linked_at"],
        )

    def get_oauth_links_for_user(self, user_id: UUID) -> list[OAuthLink]:
        """Get all OAuth links for a user."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, provider, provider_user_id, provider_email, linked_at
                FROM oauth_links WHERE user_id = %s ORDER BY linked_at DESC
                """,
                (str(user_id),),
            )
            rows = cursor.fetchall()

        return [
            OAuthLink(
                id=row["id"],
                user_id=row["user_id"],
                provider=row["provider"],
                provider_user_id=row["provider_user_id"],
                provider_email=row["provider_email"],
                linked_at=row["linked_at"],
            )
            for row in rows
        ]

    def get_user_by_oauth(self, provider: str, provider_user_id: str) -> Optional[User]:
        """Get a user by OAuth provider and provider user ID."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, u.display_name, u.google_sheet_id,
                       u.is_active, u.created_at, u.last_login
                FROM users u
                JOIN oauth_links ol ON u.id = ol.user_id
                WHERE ol.provider = %s AND ol.provider_user_id = %s AND u.is_active = TRUE
                """,
                (provider, provider_user_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Update last login
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET last_login = NOW() WHERE id = %s",
                (str(row["id"]),),
            )

        return User(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            google_sheet_id=row["google_sheet_id"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=datetime.now(),
        )

    def delete_oauth_link(self, user_id: UUID, provider: str) -> bool:
        """Delete an OAuth link for a user."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM oauth_links WHERE user_id = %s AND provider = %s RETURNING id",
                (str(user_id), provider),
            )
            result = cursor.fetchone()

        return result is not None

    def clear_all_oauth_links(self) -> int:
        """Clear all OAuth links (for dev mode startup)."""
        with self.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM oauth_links")
            return cursor.rowcount


# Singleton instance
_user_service: Optional[UserService] = None


def get_user_service(settings: Settings) -> UserService:
    """Get or create the user service singleton."""
    global _user_service
    if _user_service is None:
        _user_service = UserService(settings)
    return _user_service
