import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.config import Settings
from app.models.item import ImageInfo, CropRegion
from app.services.database import DatabaseService, get_database_service

logger = logging.getLogger(__name__)


class StorageService:
    """
    Storage service for images.
    Uses filesystem for image files, PostgreSQL for metadata.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.images_dir = Path(settings.images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._db: Optional[DatabaseService] = None

    @property
    def db(self) -> DatabaseService:
        """Lazy load database service."""
        if self._db is None:
            self._db = get_database_service(self.settings)
        return self._db

    def _sanitize_item_id(self, item_id: str) -> str:
        """Sanitize item_id to prevent path traversal attacks."""
        if '..' in item_id or '/' in item_id or '\\' in item_id:
            raise ValueError(f"Invalid item_id: {item_id}")
        if not item_id or not item_id.strip():
            raise ValueError("Item ID cannot be empty")
        if re.search(r'[<>:"|?*\x00-\x1f]', item_id):
            raise ValueError(f"Invalid characters in item_id: {item_id}")
        return item_id.strip()

    def _get_item_dir(self, item_id: str) -> Path:
        safe_id = self._sanitize_item_id(item_id)
        item_dir = self.images_dir / safe_id
        if not item_dir.resolve().is_relative_to(self.images_dir.resolve()):
            raise ValueError(f"Invalid item_id: {item_id}")
        item_dir.mkdir(parents=True, exist_ok=True)
        return item_dir

    # Legacy file-based methods for backward compatibility during migration
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
        if not all(k in region for k in ("x", "y", "size")):
            return False
        x, y, size = region["x"], region["y"], region["size"]
        if not (0 <= x <= 100 and 0 <= y <= 100 and 0 < size <= 100):
            return False
        if x + size > 100 or y + size > 100:
            return False

        # Try DB first
        try:
            if self.db.is_connected():
                result = self.db.set_crop_region(image_id, {"x": x, "y": y, "size": size})
                if result:
                    return True
        except Exception as e:
            logger.warning(
                f"DB crop region failed for image {image_id} "
                f"(item '{item_id}'), using file: {e}"
            )

        # Fallback to file-based storage
        metadata = self._load_metadata(item_id)
        if "crop_regions" not in metadata:
            metadata["crop_regions"] = {}
        metadata["crop_regions"][image_id] = {"x": x, "y": y, "size": size}
        self._save_metadata(item_id, metadata)
        return True

    def _get_crop_region_from_file(self, item_id: str, image_id: str) -> Optional[CropRegion]:
        """Get crop region from file-based storage only."""
        metadata = self._load_metadata(item_id)
        crop = metadata.get("crop_regions", {}).get(image_id)
        if crop:
            return CropRegion(x=crop['x'], y=crop['y'], size=crop['size'])
        return None

    def get_crop_region(self, item_id: str, image_id: str) -> Optional[CropRegion]:
        """Get crop region for an image. Returns None if not set."""
        # Try DB first
        try:
            if self.db.is_connected():
                meta = self.db.get_image_metadata(image_id)
                if meta and meta.get('crop_region'):
                    cr = meta['crop_region']
                    return CropRegion(x=cr['x'], y=cr['y'], size=cr['size'])
                # If meta exists but no crop_region, or meta doesn't exist,
                # check file fallback (image might not be in DB)
        except Exception as e:
            logger.warning(
                f"DB get crop failed for image {image_id} "
                f"(item '{item_id}'), using file: {e}"
            )

        # Fallback to file-based storage
        return self._get_crop_region_from_file(item_id, image_id)

    def _get_image_path(self, item_id: str, image_id: str) -> Optional[Path]:
        item_dir = self.images_dir / item_id
        if not item_dir.exists():
            return None

        for file in item_dir.iterdir():
            if file.stem == image_id:
                return file

        return None

    async def save_image(
        self, item_id: str, file: UploadFile, base_url: str
    ) -> ImageInfo:
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

        # Get current order/count for display_order
        try:
            if self.db.is_connected():
                existing_images = self.db.get_images_for_item(item_id)
                display_order = len(existing_images)

                # Save to DB
                self.db.save_image_metadata(
                    image_id=image_id,
                    item_id=item_id,
                    filename=original_filename,
                    display_order=display_order,
                )
                file_size_kb = len(content) / 1024
                logger.info(
                    f"Saved image {image_id} for item '{item_id}': "
                    f"{original_filename} ({file_size_kb:.1f} KB)"
                )
        except Exception as e:
            logger.warning(
                f"DB save image failed for {image_id} "
                f"(item '{item_id}'), using file: {e}"
            )
            # Fallback to file-based order
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
        """Search all item directories for the image."""
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

        # Build a dict of all images on disk
        images_on_disk: dict[str, tuple[str, Path]] = {}
        for file in item_dir.iterdir():
            if file.is_file() and not file.name.startswith('.'):
                images_on_disk[file.stem] = (file.name, file)

        if not images_on_disk:
            return []

        result = []

        # Try to get order and crop from DB
        try:
            if self.db.is_connected():
                db_images = self.db.get_images_for_item(item_id)

                # Add images in DB order
                for db_img in db_images:
                    img_id = db_img['image_id']
                    if img_id in images_on_disk:
                        filename, _ = images_on_disk.pop(img_id)
                        crop = None
                        if db_img.get('crop_region'):
                            cr = db_img['crop_region']
                            crop = CropRegion(x=cr['x'], y=cr['y'], size=cr['size'])

                        result.append(ImageInfo(
                            image_id=img_id,
                            item_id=item_id,
                            filename=filename,
                            url=f"{base_url}/images/{img_id}",
                            crop_region=crop,
                        ))

                # Add any remaining disk images not in DB (check file fallback for crop)
                for img_id, (filename, _) in images_on_disk.items():
                    result.append(ImageInfo(
                        image_id=img_id,
                        item_id=item_id,
                        filename=filename,
                        url=f"{base_url}/images/{img_id}",
                        crop_region=self._get_crop_region_from_file(item_id, img_id),
                    ))

                return result
        except Exception as e:
            logger.warning(
                f"DB list images failed for item '{item_id}', using file: {e}"
            )

        # Fallback to file-based order
        order = self._load_order(item_id)

        for img_id in order:
            if img_id in images_on_disk:
                filename, _ = images_on_disk.pop(img_id)
                result.append(ImageInfo(
                    image_id=img_id,
                    item_id=item_id,
                    filename=filename,
                    url=f"{base_url}/images/{img_id}",
                    crop_region=self.get_crop_region(item_id, img_id),
                ))

        # Add remaining images not in order
        for img_id, (filename, _) in images_on_disk.items():
            result.append(ImageInfo(
                image_id=img_id,
                item_id=item_id,
                filename=filename,
                url=f"{base_url}/images/{img_id}",
                crop_region=self.get_crop_region(item_id, img_id),
            ))

        return result

    def delete_image(self, image_id: str) -> bool:
        result = self.get_image_path(image_id)
        if result is None:
            return False

        file_path, item_id = result
        file_path.unlink()

        # Delete from DB
        try:
            if self.db.is_connected():
                self.db.delete_image_metadata(image_id)
                logger.info(f"Deleted image {image_id} from item '{item_id}'")
        except Exception as e:
            logger.warning(
                f"DB delete image failed for {image_id} "
                f"(item '{item_id}'): {e}"
            )

        # Also remove from file-based order (for backward compat)
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
        existing = {f.stem for f in item_dir.iterdir() if f.is_file() and not f.name.startswith('.')}
        if not all(img_id in existing for img_id in image_ids):
            return False

        # Update DB order
        try:
            if self.db.is_connected():
                self.db.update_image_order(item_id, image_ids)
                logger.info(
                    f"Reordered {len(image_ids)} images for item '{item_id}'"
                )
        except Exception as e:
            logger.warning(
                f"DB reorder failed for item '{item_id}' "
                f"({len(image_ids)} images): {e}"
            )

        # Also update file-based order
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
                if not file.name.startswith('.'):
                    count += 1

        # Remove empty directory
        if item_dir.exists() and not any(item_dir.iterdir()):
            item_dir.rmdir()

        # Delete from DB
        try:
            if self.db.is_connected():
                self.db.delete_images_for_item(item_id)
                logger.info(
                    f"Deleted all {count} images for item '{item_id}'"
                )
        except Exception as e:
            logger.warning(
                f"DB delete images failed for item '{item_id}': {e}"
            )

        return count

    def rename_item_folder(self, old_id: str, new_id: str) -> bool:
        """Rename an item's image folder from old_id to new_id."""
        old_dir = self.images_dir / old_id
        new_dir = self.images_dir / new_id

        if new_dir.exists():
            return False

        if not old_dir.exists():
            return True

        old_dir.rename(new_dir)

        # Update DB - this is done in sheets service
        return True


_storage_service: Optional[StorageService] = None


def get_storage_service(settings: Settings) -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService(settings)
    return _storage_service
