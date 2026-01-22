import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile

from app.services.storage import StorageService
from app.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        api_key="test-key",
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-id",
        images_dir=str(tmp_path / "images"),
    )


@pytest.fixture
def storage(settings):
    return StorageService(settings)


@pytest.fixture
def sample_png():
    """Minimal valid PNG."""
    return (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
        b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
        b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )


class TestStorageServiceInit:
    def test_creates_images_directory(self, settings):
        StorageService(settings)
        assert Path(settings.images_dir).exists()


class TestSaveImage:
    @pytest.mark.asyncio
    async def test_save_image_creates_file(self, storage, sample_png):
        # Create mock UploadFile
        file = MagicMock(spec=UploadFile)
        file.filename = "test_image.png"
        file.read = AsyncMock(return_value=sample_png)

        result = await storage.save_image("item_1", file, "http://localhost")

        assert result.item_id == "item_1"
        assert result.filename == "test_image.png"
        assert "http://localhost/images/" in result.url

        # Verify file exists on disk
        item_dir = storage.images_dir / "item_1"
        assert item_dir.exists()
        files = list(item_dir.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".png"

    @pytest.mark.asyncio
    async def test_save_image_default_extension(self, storage, sample_png):
        file = MagicMock(spec=UploadFile)
        file.filename = None
        file.read = AsyncMock(return_value=sample_png)

        result = await storage.save_image("item_2", file, "http://example.com")

        assert result.filename == "image.jpg"

    @pytest.mark.asyncio
    async def test_save_multiple_images_for_item(self, storage, sample_png):
        for i in range(3):
            file = MagicMock(spec=UploadFile)
            file.filename = f"image_{i}.png"
            file.read = AsyncMock(return_value=sample_png)
            await storage.save_image("item_3", file, "http://localhost")

        images = storage.list_images_for_item("item_3", "http://localhost")
        assert len(images) == 3


class TestGetImagePath:
    @pytest.mark.asyncio
    async def test_get_image_path_finds_image(self, storage, sample_png):
        file = MagicMock(spec=UploadFile)
        file.filename = "test.png"
        file.read = AsyncMock(return_value=sample_png)

        result = await storage.save_image("item_1", file, "http://localhost")
        image_id = result.image_id

        found = storage.get_image_path(image_id)
        assert found is not None
        path, item_id = found
        assert path.exists()
        assert item_id == "item_1"

    def test_get_image_path_not_found(self, storage):
        result = storage.get_image_path("nonexistent")
        assert result is None


class TestListImagesForItem:
    @pytest.mark.asyncio
    async def test_list_images_returns_all(self, storage, sample_png):
        for i in range(2):
            file = MagicMock(spec=UploadFile)
            file.filename = f"img_{i}.jpg"
            file.read = AsyncMock(return_value=sample_png)
            await storage.save_image("item_1", file, "http://localhost")

        images = storage.list_images_for_item("item_1", "http://localhost")
        assert len(images) == 2
        for img in images:
            assert img.item_id == "item_1"
            assert "http://localhost/images/" in img.url

    def test_list_images_empty_for_nonexistent_item(self, storage):
        images = storage.list_images_for_item("nonexistent", "http://localhost")
        assert images == []


class TestDeleteImage:
    @pytest.mark.asyncio
    async def test_delete_image_removes_file(self, storage, sample_png):
        file = MagicMock(spec=UploadFile)
        file.filename = "to_delete.png"
        file.read = AsyncMock(return_value=sample_png)

        result = await storage.save_image("item_1", file, "http://localhost")
        image_id = result.image_id

        # Verify file exists
        assert storage.get_image_path(image_id) is not None

        # Delete
        deleted = storage.delete_image(image_id)
        assert deleted is True

        # Verify file is gone
        assert storage.get_image_path(image_id) is None

    def test_delete_nonexistent_image(self, storage):
        deleted = storage.delete_image("nonexistent")
        assert deleted is False


class TestDeleteAllImagesForItem:
    @pytest.mark.asyncio
    async def test_delete_all_images(self, storage, sample_png):
        for i in range(3):
            file = MagicMock(spec=UploadFile)
            file.filename = f"img_{i}.png"
            file.read = AsyncMock(return_value=sample_png)
            await storage.save_image("item_1", file, "http://localhost")

        count = storage.delete_all_images_for_item("item_1")
        assert count == 3

        # Directory should be removed
        item_dir = storage.images_dir / "item_1"
        assert not item_dir.exists()

    def test_delete_all_for_nonexistent_item(self, storage):
        count = storage.delete_all_images_for_item("nonexistent")
        assert count == 0
