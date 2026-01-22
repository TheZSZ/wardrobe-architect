import pytest
from pydantic import ValidationError
from app.models.item import (
    WardrobeItem,
    WardrobeItemCreate,
    WardrobeItemUpdate,
    ImageInfo,
)


class TestWardrobeItemCreate:
    def test_create_valid_item(self):
        item = WardrobeItemCreate(
            item="Navy Blue Oxford Shirt",
            category="Tops",
            color="Navy Blue",
            fit="Slim",
            season="All",
            notes="Favorite work shirt",
        )
        assert item.item == "Navy Blue Oxford Shirt"
        assert item.category == "Tops"
        assert item.color == "Navy Blue"
        assert item.fit == "Slim"
        assert item.season == "All"
        assert item.notes == "Favorite work shirt"

    def test_create_item_without_notes(self):
        item = WardrobeItemCreate(
            item="White T-Shirt",
            category="Tops",
            color="White",
            fit="Regular",
            season="Summer",
        )
        assert item.notes is None

    def test_create_item_missing_required_field(self):
        with pytest.raises(ValidationError):
            WardrobeItemCreate(
                item="Test Item",
                category="Tops",
                # missing color, fit, season
            )


class TestWardrobeItemUpdate:
    def test_update_partial_fields(self):
        update = WardrobeItemUpdate(color="Red")
        assert update.color == "Red"
        assert update.item is None
        assert update.category is None

    def test_update_all_fields(self):
        update = WardrobeItemUpdate(
            item="Updated Name",
            category="Bottoms",
            color="Black",
            fit="Relaxed",
            season="Winter",
            notes="Updated notes",
        )
        assert update.item == "Updated Name"
        assert update.category == "Bottoms"
        assert update.notes == "Updated notes"

    def test_update_empty_is_valid(self):
        update = WardrobeItemUpdate()
        assert update.model_dump(exclude_unset=True) == {}


class TestWardrobeItem:
    def test_wardrobe_item_with_id(self):
        item = WardrobeItem(
            id="123",
            item="Test Item",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )
        assert item.id == "123"
        assert item.item == "Test Item"

    def test_wardrobe_item_serialization(self):
        item = WardrobeItem(
            id="1",
            item="Test Item",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
            notes="Test notes",
        )
        data = item.model_dump()
        assert data["id"] == "1"
        assert data["item"] == "Test Item"
        assert data["notes"] == "Test notes"


class TestImageInfo:
    def test_image_info_creation(self):
        info = ImageInfo(
            image_id="abc123",
            item_id="1",
            filename="photo.jpg",
            url="http://localhost/images/abc123",
        )
        assert info.image_id == "abc123"
        assert info.item_id == "1"
        assert info.filename == "photo.jpg"
        assert info.url == "http://localhost/images/abc123"

    def test_image_info_serialization(self):
        info = ImageInfo(
            image_id="xyz789",
            item_id="2",
            filename="image.png",
            url="http://example.com/images/xyz789",
        )
        data = info.model_dump()
        assert data["image_id"] == "xyz789"
        assert data["item_id"] == "2"
