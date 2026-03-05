import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings, get_settings
from app.services.sheets import SheetsService
from app.routers.items import get_sheets as items_get_sheets


# Note: Multi-user API keys are in wrd_xxxxxxxxxxxx format and stored in DB
# Unit tests can only test format validation; full auth requires integration tests
TEST_API_KEY_INVALID_FORMAT = "test-api-key-12345"
TEST_API_KEY_VALID_FORMAT = "wrd_testkey123"


@pytest.fixture
def test_settings(tmp_path):
    """Settings with invalid database URL to prevent DB connections in unit tests."""
    return Settings(
        api_key="dummy-key-for-testing",  # Not used in multi-user mode
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-sheet-id",
        images_dir=str(tmp_path / "images"),
        database_url="postgresql://invalid:invalid@localhost:9999/invalid",
    )


@pytest.fixture
def mock_sheets():
    mock = Mock(spec=SheetsService)
    mock.get_all_items.return_value = []
    return mock


@pytest.fixture
def mock_user_service():
    """Mock user service that returns None for all lookups."""
    mock = Mock()
    mock.get_user_by_api_key.return_value = None
    mock.get_user_by_session.return_value = None
    return mock


@pytest.fixture
def auth_client(test_settings, mock_sheets, mock_user_service):
    """Client that uses real auth (no override for verify_api_key)."""

    def override_settings():
        return test_settings

    def override_sheets():
        return mock_sheets

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[items_get_sheets] = override_sheets

    # Patch user service to avoid DB connections
    with patch('app.auth._get_user_service', return_value=mock_user_service):
        with TestClient(app) as client:
            yield client

    app.dependency_overrides.clear()


class TestAPIKeyAuthentication:
    def test_health_endpoint_no_auth_required(self, auth_client):
        response = auth_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data
        assert "disk" in data

    def test_api_key_wrong_format_rejected(self, auth_client):
        """API keys must be in wrd_xxxx format."""
        response = auth_client.get(
            "/items",
            headers={"X-API-Key": TEST_API_KEY_INVALID_FORMAT},
        )
        assert response.status_code == 401
        assert "Invalid API key format" in response.json()["detail"]

    def test_api_key_valid_format_but_not_in_db(self, auth_client):
        """Valid format but key not in database still returns 401."""
        response = auth_client.get(
            "/items",
            headers={"X-API-Key": TEST_API_KEY_VALID_FORMAT},
        )
        # Key has right format but is not in the database
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_missing_api_key(self, auth_client):
        response = auth_client.get("/items")
        assert response.status_code == 401  # Missing API key returns 401
        assert "Missing API key" in response.json()["detail"]


class TestAPIKeyQueryParameter:
    """Test API key authentication via query parameter (for images)."""

    def test_api_key_in_query_param_wrong_format(self, auth_client):
        """Query param API key with wrong format rejected."""
        response = auth_client.get(
            "/images/test-image-id",
            params={"api_key": TEST_API_KEY_INVALID_FORMAT},
        )
        assert response.status_code == 401
        assert "Invalid API key format" in response.json()["detail"]

    def test_api_key_in_query_param_valid_format_not_in_db(self, auth_client):
        """Query param API key with valid format but not in DB."""
        response = auth_client.get(
            "/images/test-image-id",
            params={"api_key": TEST_API_KEY_VALID_FORMAT},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_api_key_missing_from_query_and_header(self, auth_client):
        """No API key in header or query param returns 401."""
        response = auth_client.get("/images/test-image-id")
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]

    def test_header_takes_precedence_over_query(self, auth_client):
        """Header API key is checked even when query param is also provided."""
        response = auth_client.get(
            "/images/test-image-id",
            headers={"X-API-Key": TEST_API_KEY_INVALID_FORMAT},
            params={"api_key": TEST_API_KEY_VALID_FORMAT},
        )
        # Header is checked first, which has invalid format
        assert response.status_code == 401
        assert "Invalid API key format" in response.json()["detail"]


class TestAPIKeyWithValidUser:
    """Test API key auth when user is found in database."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        from app.models.user import User
        from datetime import datetime
        from uuid import uuid4
        return User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            is_active=True,
            created_at=datetime.now(),
        )

    @pytest.fixture
    def mock_user_service_with_user(self, mock_user):
        """Mock user service that returns a valid user."""
        mock = Mock()
        mock.get_user_by_api_key.return_value = mock_user
        mock.get_user_by_session.return_value = None
        return mock

    @pytest.fixture
    def auth_client_with_user(self, test_settings, mock_sheets, mock_user_service_with_user):
        """Client where API key lookups succeed."""
        def override_settings():
            return test_settings

        def override_sheets():
            return mock_sheets

        app.dependency_overrides[get_settings] = override_settings
        app.dependency_overrides[items_get_sheets] = override_sheets

        with patch('app.auth._get_user_service', return_value=mock_user_service_with_user):
            with TestClient(app) as client:
                yield client

        app.dependency_overrides.clear()

    def test_valid_api_key_returns_items(self, auth_client_with_user, mock_sheets):
        """Valid API key allows access to items endpoint."""
        mock_sheets.get_all_items.return_value = []
        response = auth_client_with_user.get(
            "/items",
            headers={"X-API-Key": TEST_API_KEY_VALID_FORMAT},
        )
        assert response.status_code == 200

    def test_valid_api_key_in_query_param(self, auth_client_with_user):
        """Valid API key in query param allows image access."""
        response = auth_client_with_user.get(
            "/images/nonexistent-image",
            params={"api_key": TEST_API_KEY_VALID_FORMAT},
        )
        # Will get 404 since image doesn't exist, but auth passed
        assert response.status_code == 404


class TestSessionAuthentication:
    """Test session-based authentication for web UI."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        from app.models.user import User
        from datetime import datetime
        from uuid import uuid4
        return User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            is_active=True,
            created_at=datetime.now(),
        )

    @pytest.fixture
    def mock_user_service_with_session(self, mock_user):
        """Mock user service that returns a user for session lookups."""
        mock = Mock()
        mock.get_user_by_api_key.return_value = None
        mock.get_user_by_session.return_value = mock_user
        return mock

    @pytest.fixture
    def session_client(self, test_settings, mock_user_service_with_session):
        """Client for session-based auth testing."""
        def override_settings():
            return test_settings

        app.dependency_overrides[get_settings] = override_settings

        with patch('app.auth._get_user_service', return_value=mock_user_service_with_session):
            with TestClient(app) as client:
                yield client

        app.dependency_overrides.clear()

    def test_settings_page_without_session_redirects(self, auth_client):
        """Settings page without session redirects to login."""
        response = auth_client.get("/settings", follow_redirects=False)
        assert response.status_code == 401

    def test_post_login_page_without_session_fails(self, auth_client):
        """Post-login page without session returns 401."""
        response = auth_client.get("/post-login")
        assert response.status_code == 401

    def test_valid_session_allows_access(self, session_client):
        """Valid session cookie allows access to protected pages."""
        session_client.cookies.set("session_token", "valid-session-token")
        response = session_client.get("/post-login")
        # post-login is a simple page that just requires authentication
        assert response.status_code == 200

    def test_invalid_session_rejected(self, auth_client):
        """Invalid session token is rejected."""
        auth_client.cookies.set("session_token", "invalid-token")
        response = auth_client.get("/settings")
        assert response.status_code == 401
        assert "Invalid or expired session" in response.json()["detail"]


class TestOptionalAuthentication:
    """Test get_current_user_optional - returns None if not authenticated."""

    def test_login_page_accessible_without_auth(self, auth_client):
        """Login page is accessible without authentication."""
        response = auth_client.get("/login")
        assert response.status_code == 200
        assert "login" in response.text.lower()
