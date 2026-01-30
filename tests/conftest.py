import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings, get_settings
from app.auth import verify_api_key, verify_api_key_or_query
from app.services.sheets import SheetsService
from app.services.storage import StorageService
from app.routers.items import get_sheets as items_get_sheets, get_storage as items_get_storage
from app.routers.images import get_sheets as images_get_sheets, get_storage as images_get_storage


TEST_API_KEY = "test-api-key-12345"


@pytest.fixture
def test_settings(tmp_path):
    """Create test settings with temporary directories.

    Uses an invalid database URL to ensure unit tests don't connect
    to any real database - they should use file-based fallbacks.
    """
    return Settings(
        api_key=TEST_API_KEY,
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-sheet-id",
        images_dir=str(tmp_path / "images"),
        host="0.0.0.0",
        port=8000,
        database_url="postgresql://invalid:invalid@localhost:9999/invalid",
    )


@pytest.fixture
def storage_service(test_settings):
    """Create a StorageService with temporary directory."""
    return StorageService(test_settings)


@pytest.fixture
def mock_sheets_service():
    """Create a mock SheetsService."""
    mock = Mock(spec=SheetsService)
    return mock


@pytest.fixture
def client(test_settings, mock_sheets_service, storage_service):
    """Create a test client with mocked dependencies."""

    def override_settings():
        return test_settings

    def override_api_key():
        return TEST_API_KEY

    def override_sheets():
        return mock_sheets_service

    def override_storage():
        return storage_service

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[verify_api_key] = override_api_key
    app.dependency_overrides[verify_api_key_or_query] = override_api_key
    # Override router-level dependencies
    app.dependency_overrides[items_get_sheets] = override_sheets
    app.dependency_overrides[items_get_storage] = override_storage
    app.dependency_overrides[images_get_sheets] = override_sheets
    app.dependency_overrides[images_get_storage] = override_storage

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def client_no_auth(test_settings, mock_sheets_service, storage_service):
    """Create a test client without API key override (for auth testing)."""

    def override_settings():
        return test_settings

    def override_sheets():
        return mock_sheets_service

    def override_storage():
        return storage_service

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[items_get_sheets] = override_sheets
    app.dependency_overrides[items_get_storage] = override_storage
    app.dependency_overrides[images_get_sheets] = override_sheets
    app.dependency_overrides[images_get_storage] = override_storage

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_wardrobe_item():
    """Sample wardrobe item data."""
    return {
        "id": "1",
        "item": "Navy Blue Oxford Shirt",
        "category": "Tops",
        "color": "Navy Blue",
        "fit": "Slim",
        "season": "All",
        "notes": "Favorite work shirt",
    }


@pytest.fixture
def sample_item_create():
    """Sample data for creating an item."""
    return {
        "item": "White T-Shirt",
        "category": "Tops",
        "color": "White",
        "fit": "Regular",
        "season": "Summer",
        "notes": None,
    }


@pytest.fixture
def sample_image_bytes():
    """Sample image data (1x1 red PNG)."""
    # Minimal valid PNG file
    return (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
        b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
        b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
