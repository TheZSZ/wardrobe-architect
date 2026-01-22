import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
from app.config import Settings
from app.models.item import ImageInfo


class StorageService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.images_dir = Path(settings.images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def _get_item_dir(self, item_id: str) -> Path:
        item_dir = self.images_dir / item_id
        item_dir.mkdir(parents=True, exist_ok=True)
        return item_dir

    def _get_image_path(self, item_id: str, image_id: str) -> Optional[Path]:
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return None

        for file in item_dir.iterdir():
            if file.stem == image_id:
                return file

        return None

    async def save_image(self, item_id: str, file: UploadFile, base_url: str) -> ImageInfo:
        item_dir = self._get_item_dir(item_id)

        # Generate unique image ID
        image_id = str(uuid.uuid4())[:8]

        # Preserve original extension
        original_filename = file.filename or "image.jpg"
        extension = Path(original_filename).suffix or ".jpg"
        filename = f"{image_id}{extension}"

        file_path = item_dir / filename

        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return ImageInfo(
            image_id=image_id,
            item_id=item_id,
            filename=original_filename,
            url=f"{base_url}/images/{image_id}",
        )

    def get_image_path(self, image_id: str) -> Optional[tuple[Path, str]]:
        # Search all item directories for the image
        for item_dir in self.images_dir.iterdir():
            if not item_dir.is_dir():
                continue

            for file in item_dir.iterdir():
                if file.stem == image_id:
                    return file, item_dir.name

        return None

    def list_images_for_item(self, item_id: str, base_url: str) -> list[ImageInfo]:
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return []

        images = []
        for file in item_dir.iterdir():
            if file.is_file():
                images.append(
                    ImageInfo(
                        image_id=file.stem,
                        item_id=item_id,
                        filename=file.name,
                        url=f"{base_url}/images/{file.stem}",
                    )
                )

        return images

    def delete_image(self, image_id: str) -> bool:
        result = self.get_image_path(image_id)
        if result is None:
            return False

        file_path, _ = result
        file_path.unlink()
        return True

    def delete_all_images_for_item(self, item_id: str) -> int:
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return 0

        count = 0
        for file in item_dir.iterdir():
            if file.is_file():
                file.unlink()
                count += 1

        # Remove empty directory
        if item_dir.exists() and not any(item_dir.iterdir()):
            item_dir.rmdir()

        return count


_storage_service: Optional[StorageService] = None


def get_storage_service(settings: Settings) -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService(settings)
    return _storage_service
