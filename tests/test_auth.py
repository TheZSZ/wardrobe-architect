import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings, get_settings
from app.services.sheets import SheetsService
from app.routers.items import get_sheets as items_get_sheets


TEST_API_KEY = "test-api-key-12345"


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        api_key=TEST_API_KEY,
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-sheet-id",
        images_dir=str(tmp_path / "images"),
    )


@pytest.fixture
def mock_sheets():
    mock = Mock(spec=SheetsService)
    mock.get_all_items.return_value = []
    return mock


@pytest.fixture
def auth_client(test_settings, mock_sheets):
    """Client that uses real auth (no override for verify_api_key)."""

    def override_settings():
        return test_settings

    def override_sheets():
        return mock_sheets

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[items_get_sheets] = override_sheets

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class TestAPIKeyAuthentication:
    def test_health_endpoint_no_auth_required(self, auth_client):
        response = auth_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_valid_api_key(self, auth_client):
        response = auth_client.get(
            "/items",
            headers={"X-API-Key": TEST_API_KEY},
        )
        # Auth passes, sheets returns empty list
        assert response.status_code == 200
        assert response.json() == []

    def test_invalid_api_key(self, auth_client):
        response = auth_client.get(
            "/items",
            headers={"X-API-Key": "wrong-api-key"},
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_missing_api_key(self, auth_client):
        response = auth_client.get("/items")
        assert response.status_code == 401  # Missing API key returns 401
        assert "Missing API key" in response.json()["detail"]
