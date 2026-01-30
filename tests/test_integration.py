"""
Integration tests that run against a dedicated test PostgreSQL database.

These tests require the test-db container to be running.
Run with: make test (uses docker compose test service with test-db)

The test database is completely separate from the production database,
so these tests can safely truncate tables without affecting real data.
"""
import pytest
import os

import psycopg2

from app.config import Settings
from app.services.database import DatabaseService
from app.models.item import WardrobeItemCreate


# Use the test database (test-db container with wardrobe_test database)
# This is completely separate from the production database
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
def db_settings():
    """Settings for test database."""
    return Settings(
        api_key="test-key",
        google_sheets_credentials_json="{}",
        google_sheet_id="test",
        database_url=DATABASE_URL,
        dummy_mode=True,
    )


@pytest.fixture
def db_service(db_settings):
    """Database service connected to test database."""
    service = DatabaseService(db_settings)
    # Clean up tables before each test
    try:
        with service.get_cursor() as cursor:
            cursor.execute("DELETE FROM image_metadata")
            cursor.execute("DELETE FROM wardrobe_items")
            cursor.execute("DELETE FROM sync_log")
    except Exception:
        pass  # Tables might not exist yet
    return service


@pytest.fixture
def sample_item():
    """Sample item for testing."""
    return WardrobeItemCreate(
        item="Test Jacket",
        category="Outerwear",
        color="Blue",
        fit="Regular",
        season="Winter",
        notes="Test notes",
    )


class TestDatabaseConnection:
    """Test database connectivity."""

    def test_is_connected(self, db_service):
        assert db_service.is_connected() is True

    def test_get_item_count_empty(self, db_service):
        count = db_service.get_item_count()
        assert count == 0

    def test_get_image_count_empty(self, db_service):
        count = db_service.get_image_count()
        assert count == 0


class TestDatabaseCRUD:
    """Test CRUD operations on database."""

    def test_upsert_and_get_item(self, db_service, sample_item):
        # Create item
        item_id = "test-1"
        db_service.upsert_item(item_id, sample_item.model_dump())

        # Retrieve it
        item = db_service.get_item_by_id(item_id)
        assert item is not None
        assert item.id == item_id
        assert item.item == "Test Jacket"
        assert item.category == "Outerwear"
        assert item.color == "Blue"

    def test_get_all_items(self, db_service, sample_item):
        # Create multiple items
        db_service.upsert_item("item-1", {
            "item": "Shirt 1",
            "category": "Shirts",
            "color": "Red",
            "fit": "Slim",
            "season": "Summer",
        })
        db_service.upsert_item("item-2", {
            "item": "Shirt 2",
            "category": "Shirts",
            "color": "Blue",
            "fit": "Regular",
            "season": "Winter",
        })

        items = db_service.get_all_items()
        assert len(items) == 2

    def test_filter_by_category(self, db_service):
        db_service.upsert_item("jacket-1", {
            "item": "Jacket",
            "category": "Outerwear",
            "color": "Black",
            "fit": "Regular",
            "season": "Winter",
        })
        db_service.upsert_item("shirt-1", {
            "item": "Shirt",
            "category": "Shirts",
            "color": "White",
            "fit": "Slim",
            "season": "Summer",
        })

        items = db_service.get_all_items(category="Outerwear")
        assert len(items) == 1
        assert items[0].category == "Outerwear"

    def test_filter_by_color(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Item 1",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.upsert_item("item-2", {
            "item": "Item 2",
            "category": "Cat",
            "color": "Red",
            "fit": "Fit",
            "season": "Season",
        })

        items = db_service.get_all_items(color="Blue")
        assert len(items) == 1
        assert items[0].color == "Blue"

    def test_filter_case_insensitive(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Item",
            "category": "Shirts",
            "color": "Blue",
            "fit": "Fit",
            "season": "Summer",
        })

        # Test case-insensitive matching
        items = db_service.get_all_items(category="shirts")
        assert len(items) == 1

        items = db_service.get_all_items(color="BLUE")
        assert len(items) == 1

    def test_update_item(self, db_service):
        # Create item
        db_service.upsert_item("item-1", {
            "item": "Original",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })

        # Update it
        db_service.upsert_item("item-1", {
            "item": "Updated",
            "category": "Cat",
            "color": "Red",
            "fit": "Fit",
            "season": "Season",
        })

        item = db_service.get_item_by_id("item-1")
        assert item.item == "Updated"
        assert item.color == "Red"

    def test_delete_item(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "To Delete",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })

        result = db_service.delete_item("item-1")
        assert result is True

        item = db_service.get_item_by_id("item-1")
        assert item is None

    def test_delete_nonexistent_item(self, db_service):
        result = db_service.delete_item("nonexistent")
        assert result is False


class TestImageMetadata:
    """Test image metadata operations."""

    def test_save_and_get_image_metadata(self, db_service):
        # First create an item
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })

        # Save image metadata
        db_service.save_image_metadata(
            image_id="img-1",
            item_id="item-1",
            filename="photo.jpg",
            display_order=0,
        )

        # Get it back
        meta = db_service.get_image_metadata("img-1")
        assert meta is not None
        assert meta["image_id"] == "img-1"
        assert meta["item_id"] == "item-1"
        assert meta["filename"] == "photo.jpg"

    def test_get_images_for_item(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })

        # Add multiple images
        db_service.save_image_metadata("img-1", "item-1", "photo1.jpg", 0)
        db_service.save_image_metadata("img-2", "item-1", "photo2.jpg", 1)

        images = db_service.get_images_for_item("item-1")
        assert len(images) == 2
        # Should be ordered by display_order
        assert images[0]["image_id"] == "img-1"
        assert images[1]["image_id"] == "img-2"

    def test_set_crop_region(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.save_image_metadata("img-1", "item-1", "photo.jpg", 0)

        # Set crop region
        result = db_service.set_crop_region("img-1", {"x": 10, "y": 20, "size": 50})
        assert result is True

        # Verify it was saved
        meta = db_service.get_image_metadata("img-1")
        assert meta["crop_region"] == {"x": 10, "y": 20, "size": 50}

    def test_delete_image_metadata(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.save_image_metadata("img-1", "item-1", "photo.jpg", 0)

        result = db_service.delete_image_metadata("img-1")
        assert result is True

        meta = db_service.get_image_metadata("img-1")
        assert meta is None

    def test_delete_images_for_item(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.save_image_metadata("img-1", "item-1", "photo1.jpg", 0)
        db_service.save_image_metadata("img-2", "item-1", "photo2.jpg", 1)

        count = db_service.delete_images_for_item("item-1")
        assert count == 2

        images = db_service.get_images_for_item("item-1")
        assert len(images) == 0

    def test_cascade_delete_on_item_delete(self, db_service):
        """Images should be deleted when item is deleted."""
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.save_image_metadata("img-1", "item-1", "photo.jpg", 0)

        # Delete the item
        db_service.delete_item("item-1")

        # Image metadata should be gone (cascade delete)
        meta = db_service.get_image_metadata("img-1")
        assert meta is None


class TestSyncLog:
    """Test sync log operations."""

    def test_sync_from_sheets_logs_sync(self, db_service):
        """Syncing from sheets should create a sync log entry."""
        items = [
            {"id": "item-1", "item": "Shirt", "category": "Shirts",
             "color": "Blue", "fit": "Fit", "season": "Summer"},
            {"id": "item-2", "item": "Pants", "category": "Pants",
             "color": "Black", "fit": "Fit", "season": "Winter"},
        ]
        db_service.sync_from_sheets(items)

        # Check last sync was logged
        last_sync = db_service.get_last_sync()
        assert last_sync is not None
        assert last_sync["items_synced"] == 2
        assert last_sync["source"] == "sheets"
        assert last_sync["status"] == "success"

    def test_get_sync_history(self, db_service):
        """Sync history should return most recent first."""
        # Do two syncs
        db_service.sync_from_sheets([
            {"id": "item-1", "item": "First", "category": "Cat",
             "color": "Blue", "fit": "Fit", "season": "Season"},
        ])
        db_service.sync_from_sheets([
            {"id": "item-1", "item": "Second", "category": "Cat",
             "color": "Blue", "fit": "Fit", "season": "Season"},
            {"id": "item-2", "item": "Third", "category": "Cat",
             "color": "Red", "fit": "Fit", "season": "Season"},
        ])

        history = db_service.get_sync_history(limit=10)
        assert len(history) == 2
        # Most recent first (2 items synced)
        assert history[0]["items_synced"] == 2


class TestItemCounts:
    """Test count operations."""

    def test_get_item_count(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test 1",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.upsert_item("item-2", {
            "item": "Test 2",
            "category": "Cat",
            "color": "Red",
            "fit": "Fit",
            "season": "Season",
        })

        count = db_service.get_item_count()
        assert count == 2

    def test_get_image_count(self, db_service):
        db_service.upsert_item("item-1", {
            "item": "Test",
            "category": "Cat",
            "color": "Blue",
            "fit": "Fit",
            "season": "Season",
        })
        db_service.save_image_metadata("img-1", "item-1", "photo1.jpg", 0)
        db_service.save_image_metadata("img-2", "item-1", "photo2.jpg", 1)

        count = db_service.get_image_count()
        assert count == 2
