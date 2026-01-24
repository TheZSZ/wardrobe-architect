import json
import re
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

    def _sanitize_item_id(self, item_id: str) -> str:
        """Sanitize item_id to prevent path traversal attacks."""
        # Reject path traversal attempts
        if '..' in item_id or '/' in item_id or '\\' in item_id:
            raise ValueError(f"Invalid item_id: {item_id}")
        # Reject empty or whitespace-only IDs
        if not item_id or not item_id.strip():
            raise ValueError("Item ID cannot be empty")
        # Reject IDs with problematic characters
        if re.search(r'[<>:"|?*\x00-\x1f]', item_id):
            raise ValueError(f"Invalid characters in item_id: {item_id}")
        return item_id.strip()

    def _get_item_dir(self, item_id: str) -> Path:
        safe_id = self._sanitize_item_id(item_id)
        item_dir = self.images_dir / safe_id
        # Verify the resulting path is still under images_dir (defense in depth)
        if not item_dir.resolve().is_relative_to(self.images_dir.resolve()):
            raise ValueError(f"Invalid item_id: {item_id}")
        item_dir.mkdir(parents=True, exist_ok=True)
        return item_dir

    def _get_order_file(self, item_id: str) -> Path:
        return self._get_item_dir(item_id) / ".order.json"

    def _load_order(self, item_id: str) -> list[str]:
        order_file = self._get_order_file(item_id)
        if order_file.exists():
            try:
                return json.loads(order_file.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_order(self, item_id: str, order: list[str]) -> None:
        order_file = self._get_order_file(item_id)
        order_file.write_text(json.dumps(order))

    def _get_metadata_file(self, item_id: str) -> Path:
        return self._get_item_dir(item_id) / ".metadata.json"

    def _load_metadata(self, item_id: str) -> dict:
        metadata_file = self._get_metadata_file(item_id)
        if metadata_file.exists():
            try:
                return json.loads(metadata_file.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_metadata(self, item_id: str, metadata: dict) -> None:
        metadata_file = self._get_metadata_file(item_id)
        metadata_file.write_text(json.dumps(metadata))

    def set_crop_region(self, item_id: str, image_id: str, region: dict) -> bool:
        """Set crop region for an image (x, y, size as percentages 0-100)."""
        # Validate region has required fields
        if not all(k in region for k in ("x", "y", "size")):
            return False
        # Validate values are in valid range
        x, y, size = region["x"], region["y"], region["size"]
        if not (0 <= x <= 100 and 0 <= y <= 100 and 0 < size <= 100):
            return False
        # Ensure crop box stays within image bounds
        if x + size > 100 or y + size > 100:
            return False

        metadata = self._load_metadata(item_id)
        if "crop_regions" not in metadata:
            metadata["crop_regions"] = {}
        metadata["crop_regions"][image_id] = {"x": x, "y": y, "size": size}
        self._save_metadata(item_id, metadata)
        return True

    def get_crop_region(self, item_id: str, image_id: str) -> dict | None:
        """Get crop region for an image. Returns None if not set."""
        metadata = self._load_metadata(item_id)
        return metadata.get("crop_regions", {}).get(image_id)

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

        # Add to order list
        order = self._load_order(item_id)
        order.append(image_id)
        self._save_order(item_id, order)

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

        # Build a dict of all images
        images_by_id: dict[str, ImageInfo] = {}
        for file in item_dir.iterdir():
            if file.is_file() and not file.name.startswith('.'):
                images_by_id[file.stem] = ImageInfo(
                    image_id=file.stem,
                    item_id=item_id,
                    filename=file.name,
                    url=f"{base_url}/images/{file.stem}",
                    crop_region=self.get_crop_region(item_id, file.stem),
                )

        # Sort by saved order, with any new images at the end
        order = self._load_order(item_id)
        result = []
        for image_id in order:
            if image_id in images_by_id:
                result.append(images_by_id.pop(image_id))

        # Add any remaining images not in order (e.g., legacy images)
        result.extend(images_by_id.values())

        return result

    def delete_image(self, image_id: str) -> bool:
        result = self.get_image_path(image_id)
        if result is None:
            return False

        file_path, item_id = result
        file_path.unlink()

        # Remove from order list
        order = self._load_order(item_id)
        if image_id in order:
            order.remove(image_id)
            self._save_order(item_id, order)

        return True

    def reorder_images(self, item_id: str, image_ids: list[str]) -> bool:
        """Set the order of images for an item."""
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return False

        # Verify all image_ids exist
        existing_ids = {f.stem for f in item_dir.iterdir() if f.is_file() and not f.name.startswith('.')}
        if not all(img_id in existing_ids for img_id in image_ids):
            return False

        self._save_order(item_id, image_ids)
        return True

    def delete_all_images_for_item(self, item_id: str) -> int:
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return 0

        count = 0
        for file in item_dir.iterdir():
            if file.is_file():
                file.unlink()
                # Don't count hidden files (like .order.json)
                if not file.name.startswith('.'):
                    count += 1

        # Remove empty directory
        if item_dir.exists() and not any(item_dir.iterdir()):
            item_dir.rmdir()

        return count

    def rename_item_folder(self, old_id: str, new_id: str) -> bool:
        """Rename an item's image folder from old_id to new_id."""
        old_dir = self.images_dir / old_id
        new_dir = self.images_dir / new_id

        # If new folder already exists, fail
        if new_dir.exists():
            return False

        # If old folder doesn't exist, that's OK (no images yet)
        if not old_dir.exists():
            return True

        # Rename the folder
        old_dir.rename(new_dir)
        return True


_storage_service: Optional[StorageService] = None


def get_storage_service(settings: Settings) -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService(settings)
    return _storage_service
