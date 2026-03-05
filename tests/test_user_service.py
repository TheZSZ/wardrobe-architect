"""
Integration tests for user_service.py - user CRUD, auth, sessions, API keys, OAuth.

These tests require the test-db container to be running.
Run with: make test
"""
import pytest
import os
from uuid import UUID

import psycopg2

from app.config import Settings
from app.services.user_service import UserService
from app.models.user import UserCreate, UserUpdate, APIKeyCreate, OAuthLinkCreate


# Use the test database
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://wardrobe:wardrobe@test-db:5432/wardrobe_test"
)


def db_available():
    """Check if database is available."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
        return True
    except Exception:
        return False


# Skip all tests if database not available
pytestmark = pytest.mark.skipif(
    not db_available(),
    reason="PostgreSQL database not available"
)


@pytest.fixture
def test_settings():
    """Settings for test database."""
    return Settings(
        api_key="test-key",
        google_sheets_credentials_json="{}",
        google_sheet_id="test",
        database_url=DATABASE_URL,
        dummy_mode=True,
        dev_mode=False,
    )


@pytest.fixture
def user_service(test_settings):
    """User service connected to test database."""
    # Reset singletons to ensure we use test settings
    import app.services.database as db_module
    import app.services.user_service as user_module
    db_module._db_service = None
    user_module._user_service = None

    service = UserService(test_settings)

    # Clean up user-related tables before each test
    try:
        with service.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM oauth_links")
            cursor.execute("DELETE FROM api_keys")
            cursor.execute("DELETE FROM user_sessions")
            cursor.execute("DELETE FROM users")
    except Exception:
        pass  # Tables might not exist yet

    yield service

    # Reset singletons after test
    db_module._db_service = None
    user_module._user_service = None


@pytest.fixture
def sample_user_create():
    """Sample user creation data."""
    return UserCreate(
        email="test@example.com",
        passcode="testpasscode123",
        display_name="Test User",
    )


class TestUserCRUD:
    """Test user CRUD operations."""

    def test_create_user(self, user_service, sample_user_create):
        """Create a new user."""
        user = user_service.create_user(sample_user_create)

        assert user is not None
        assert isinstance(user.id, UUID)
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"
        assert user.is_active is True
        assert user.google_sheet_id is None

    def test_create_user_duplicate_email_fails(self, user_service, sample_user_create):
        """Creating user with duplicate email should fail."""
        user_service.create_user(sample_user_create)

        with pytest.raises(Exception):  # psycopg2.errors.UniqueViolation
            user_service.create_user(sample_user_create)

    def test_get_user_by_id(self, user_service, sample_user_create):
        """Get user by ID."""
        created = user_service.create_user(sample_user_create)
        retrieved = user_service.get_user_by_id(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.email == created.email

    def test_get_user_by_id_not_found(self, user_service):
        """Get non-existent user returns None."""
        from uuid import uuid4
        user = user_service.get_user_by_id(uuid4())
        assert user is None

    def test_get_user_by_email(self, user_service, sample_user_create):
        """Get user by email."""
        created = user_service.create_user(sample_user_create)
        retrieved = user_service.get_user_by_email("test@example.com")

        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_user_by_email_case_insensitive(self, user_service, sample_user_create):
        """Email lookup should be case-insensitive."""
        user_service.create_user(sample_user_create)

        retrieved = user_service.get_user_by_email("TEST@EXAMPLE.COM")
        assert retrieved is not None
        assert retrieved.email == "test@example.com"

    def test_get_user_by_email_not_found(self, user_service):
        """Get non-existent user by email returns None."""
        user = user_service.get_user_by_email("nonexistent@example.com")
        assert user is None

    def test_get_all_users(self, user_service):
        """Get all users."""
        user_service.create_user(UserCreate(
            email="user1@example.com",
            passcode="password123",
            display_name="User 1",
        ))
        user_service.create_user(UserCreate(
            email="user2@example.com",
            passcode="password456",
            display_name="User 2",
        ))

        users = user_service.get_all_users()
        assert len(users) == 2

    def test_update_user_display_name(self, user_service, sample_user_create):
        """Update user display name."""
        created = user_service.create_user(sample_user_create)

        updated = user_service.update_user(
            created.id,
            UserUpdate(display_name="New Name")
        )

        assert updated is not None
        assert updated.display_name == "New Name"

    def test_update_user_google_sheet_id(self, user_service, sample_user_create):
        """Update user's Google Sheet ID."""
        created = user_service.create_user(sample_user_create)

        updated = user_service.update_user(
            created.id,
            UserUpdate(google_sheet_id="sheet-123")
        )

        assert updated is not None
        assert updated.google_sheet_id == "sheet-123"

    def test_update_user_is_active(self, user_service, sample_user_create):
        """Deactivate a user."""
        created = user_service.create_user(sample_user_create)

        updated = user_service.update_user(
            created.id,
            UserUpdate(is_active=False)
        )

        assert updated is not None
        assert updated.is_active is False

    def test_update_user_no_changes(self, user_service, sample_user_create):
        """Update with empty changes returns existing user."""
        created = user_service.create_user(sample_user_create)

        updated = user_service.update_user(created.id, UserUpdate())

        assert updated is not None
        assert updated.id == created.id

    def test_reset_passcode(self, user_service, sample_user_create):
        """Reset user passcode."""
        created = user_service.create_user(sample_user_create)

        result = user_service.reset_passcode(created.id, "newpasscode")
        assert result is True

        # Verify new passcode works
        user = user_service.authenticate_user("test@example.com", "newpasscode")
        assert user is not None

    def test_delete_user(self, user_service, sample_user_create):
        """Delete a user."""
        created = user_service.create_user(sample_user_create)

        result = user_service.delete_user(created.id)
        assert result is True

        # Verify user is gone
        user = user_service.get_user_by_id(created.id)
        assert user is None

    def test_delete_user_not_found(self, user_service):
        """Delete non-existent user returns False."""
        from uuid import uuid4
        result = user_service.delete_user(uuid4())
        assert result is False


class TestUserAuthentication:
    """Test user authentication."""

    def test_authenticate_user_success(self, user_service, sample_user_create):
        """Authenticate with correct credentials."""
        user_service.create_user(sample_user_create)

        user = user_service.authenticate_user("test@example.com", "testpasscode123")
        assert user is not None
        assert user.email == "test@example.com"

    def test_authenticate_user_wrong_passcode(self, user_service, sample_user_create):
        """Authenticate with wrong passcode fails."""
        user_service.create_user(sample_user_create)

        user = user_service.authenticate_user("test@example.com", "wrongpasscode")
        assert user is None

    def test_authenticate_user_wrong_email(self, user_service, sample_user_create):
        """Authenticate with wrong email fails."""
        user_service.create_user(sample_user_create)

        user = user_service.authenticate_user("wrong@example.com", "testpasscode123")
        assert user is None

    def test_authenticate_user_inactive(self, user_service, sample_user_create):
        """Authenticate inactive user fails."""
        created = user_service.create_user(sample_user_create)
        user_service.update_user(created.id, UserUpdate(is_active=False))

        user = user_service.authenticate_user("test@example.com", "testpasscode123")
        assert user is None

    def test_authenticate_user_case_insensitive_email(self, user_service, sample_user_create):
        """Email should be case-insensitive for auth."""
        user_service.create_user(sample_user_create)

        user = user_service.authenticate_user("TEST@EXAMPLE.COM", "testpasscode123")
        assert user is not None


class TestUserSessions:
    """Test session management."""

    def test_create_session(self, user_service, sample_user_create):
        """Create a session for user."""
        created = user_service.create_user(sample_user_create)

        token = user_service.create_session(created.id)
        assert isinstance(token, str)
        assert len(token) > 32

    def test_get_user_by_session(self, user_service, sample_user_create):
        """Get user by session token."""
        created = user_service.create_user(sample_user_create)
        token = user_service.create_session(created.id)

        user = user_service.get_user_by_session(token)
        assert user is not None
        assert user.id == created.id

    def test_get_user_by_session_invalid(self, user_service):
        """Invalid session token returns None."""
        user = user_service.get_user_by_session("invalid-token")
        assert user is None

    def test_get_user_by_session_inactive_user(self, user_service, sample_user_create):
        """Session for inactive user returns None."""
        created = user_service.create_user(sample_user_create)
        token = user_service.create_session(created.id)

        # Deactivate user
        user_service.update_user(created.id, UserUpdate(is_active=False))

        user = user_service.get_user_by_session(token)
        assert user is None

    def test_delete_session(self, user_service, sample_user_create):
        """Delete a session (logout)."""
        created = user_service.create_user(sample_user_create)
        token = user_service.create_session(created.id)

        result = user_service.delete_session(token)
        assert result is True

        # Session should no longer be valid
        user = user_service.get_user_by_session(token)
        assert user is None

    def test_delete_session_invalid(self, user_service):
        """Delete invalid session returns False."""
        result = user_service.delete_session("invalid-token")
        assert result is False

    def test_cleanup_expired_sessions(self, user_service, sample_user_create):
        """Cleanup removes expired sessions."""
        created = user_service.create_user(sample_user_create)

        # Create a session
        user_service.create_session(created.id)

        # Manually expire it
        with user_service.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE user_sessions SET expires_at = NOW() - INTERVAL '1 hour'"
            )

        # Cleanup should remove it
        count = user_service.cleanup_expired_sessions()
        assert count >= 1


class TestAPIKeys:
    """Test API key management."""

    def test_create_api_key(self, user_service, sample_user_create):
        """Create an API key for user."""
        created = user_service.create_user(sample_user_create)

        response = user_service.create_api_key(
            created.id,
            APIKeyCreate(name="Test Key")
        )

        assert response.key.startswith("wrd_")
        assert response.name == "Test Key"
        assert response.id is not None

    def test_get_api_keys_for_user(self, user_service, sample_user_create):
        """Get all API keys for user."""
        created = user_service.create_user(sample_user_create)

        user_service.create_api_key(created.id, APIKeyCreate(name="Key 1"))
        user_service.create_api_key(created.id, APIKeyCreate(name="Key 2"))

        keys = user_service.get_api_keys_for_user(created.id)
        assert len(keys) == 2
        # Keys should not contain the full key, just prefix
        assert all(k.key_prefix.startswith("wrd_") for k in keys)

    def test_get_user_by_api_key(self, user_service, sample_user_create):
        """Get user by API key."""
        created = user_service.create_user(sample_user_create)

        response = user_service.create_api_key(
            created.id,
            APIKeyCreate(name="Test Key")
        )

        user = user_service.get_user_by_api_key(response.key)
        assert user is not None
        assert user.id == created.id

    def test_get_user_by_api_key_invalid_format(self, user_service):
        """API key with wrong format returns None."""
        user = user_service.get_user_by_api_key("invalid-key-format")
        assert user is None

    def test_get_user_by_api_key_not_found(self, user_service):
        """Non-existent API key returns None."""
        user = user_service.get_user_by_api_key("wrd_notfound123")
        assert user is None

    def test_get_user_by_api_key_inactive_user(self, user_service, sample_user_create):
        """API key for inactive user returns None."""
        created = user_service.create_user(sample_user_create)
        response = user_service.create_api_key(
            created.id,
            APIKeyCreate(name="Test Key")
        )

        # Deactivate user
        user_service.update_user(created.id, UserUpdate(is_active=False))

        user = user_service.get_user_by_api_key(response.key)
        assert user is None

    def test_revoke_api_key(self, user_service, sample_user_create):
        """Revoke an API key."""
        created = user_service.create_user(sample_user_create)
        response = user_service.create_api_key(
            created.id,
            APIKeyCreate(name="Test Key")
        )

        result = user_service.revoke_api_key(response.id)
        assert result is True

        # Key should no longer work
        user = user_service.get_user_by_api_key(response.key)
        assert user is None

    def test_delete_api_key(self, user_service, sample_user_create):
        """Delete an API key."""
        created = user_service.create_user(sample_user_create)
        response = user_service.create_api_key(
            created.id,
            APIKeyCreate(name="Test Key")
        )

        result = user_service.delete_api_key(response.id)
        assert result is True

        # Key should be gone
        keys = user_service.get_api_keys_for_user(created.id)
        assert len(keys) == 0


class TestOAuthLinks:
    """Test OAuth link management."""

    def test_create_oauth_link(self, user_service, sample_user_create):
        """Create OAuth link for user."""
        created = user_service.create_user(sample_user_create)

        link = user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
                provider_email="test@gmail.com",
            )
        )

        assert link is not None
        assert link.provider == "google"
        assert link.provider_user_id == "google-123"
        assert link.provider_email == "test@gmail.com"

    def test_get_oauth_links_for_user(self, user_service, sample_user_create):
        """Get all OAuth links for user."""
        created = user_service.create_user(sample_user_create)

        user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
                provider_email="test@gmail.com",
            )
        )

        links = user_service.get_oauth_links_for_user(created.id)
        assert len(links) == 1
        assert links[0].provider == "google"

    def test_get_user_by_oauth(self, user_service, sample_user_create):
        """Get user by OAuth provider and ID."""
        created = user_service.create_user(sample_user_create)
        user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
            )
        )

        user = user_service.get_user_by_oauth("google", "google-123")
        assert user is not None
        assert user.id == created.id

    def test_get_user_by_oauth_not_found(self, user_service):
        """Non-existent OAuth link returns None."""
        user = user_service.get_user_by_oauth("google", "nonexistent")
        assert user is None

    def test_get_user_by_oauth_inactive_user(self, user_service, sample_user_create):
        """OAuth link for inactive user returns None."""
        created = user_service.create_user(sample_user_create)
        user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
            )
        )

        # Deactivate user
        user_service.update_user(created.id, UserUpdate(is_active=False))

        user = user_service.get_user_by_oauth("google", "google-123")
        assert user is None

    def test_delete_oauth_link(self, user_service, sample_user_create):
        """Delete OAuth link."""
        created = user_service.create_user(sample_user_create)
        user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
            )
        )

        result = user_service.delete_oauth_link(created.id, "google")
        assert result is True

        # Link should be gone
        links = user_service.get_oauth_links_for_user(created.id)
        assert len(links) == 0

    def test_delete_oauth_link_not_found(self, user_service, sample_user_create):
        """Delete non-existent OAuth link returns False."""
        created = user_service.create_user(sample_user_create)

        result = user_service.delete_oauth_link(created.id, "google")
        assert result is False

    def test_clear_all_oauth_links(self, user_service, sample_user_create):
        """Clear all OAuth links (dev mode feature)."""
        created = user_service.create_user(sample_user_create)
        user_service.create_oauth_link(
            created.id,
            OAuthLinkCreate(
                provider="google",
                provider_user_id="google-123",
            )
        )

        count = user_service.clear_all_oauth_links()
        assert count >= 1

        links = user_service.get_oauth_links_for_user(created.id)
        assert len(links) == 0
