import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from app.config import Settings
from app.models.item import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate

logger = logging.getLogger(__name__)


class DatabaseService:
    """PostgreSQL database service using JSONB for dynamic schema."""

    def __init__(self, settings: Settings):
        self.conn_string = settings.database_url
        self._conn = None

    @contextmanager
    def get_cursor(self):
        """Get a database cursor with automatic connection management."""
        conn = None
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            yield cursor
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_all_items(
        self,
        category: Optional[str] = None,
        color: Optional[str] = None,
        season: Optional[str] = None,
    ) -> list[WardrobeItem]:
        """Get all items with optional filters."""
        query = "SELECT id, data FROM wardrobe_items WHERE 1=1"
        params = []

        if category:
            query += " AND LOWER(data->>'category') = LOWER(%s)"
            params.append(category)
        if color:
            query += " AND LOWER(data->>'color') = LOWER(%s)"
            params.append(color)
        if season:
            query += " AND LOWER(data->>'season') = LOWER(%s)"
            params.append(season)

        query += " ORDER BY id"

        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        items = []
        for row in rows:
            data = row['data']
            items.append(WardrobeItem(
                id=row['id'],
                item=data.get('item', ''),
                category=data.get('category', ''),
                color=data.get('color', ''),
                fit=data.get('fit', ''),
                season=data.get('season', ''),
                notes=data.get('notes'),
            ))
        return items

    def get_item_by_id(self, item_id: str) -> Optional[WardrobeItem]:
        """Get a single item by ID."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT id, data FROM wardrobe_items WHERE id = %s",
                (item_id,)
            )
            row = cursor.fetchone()

        if not row:
            return None

        data = row['data']
        return WardrobeItem(
            id=row['id'],
            item=data.get('item', ''),
            category=data.get('category', ''),
            color=data.get('color', ''),
            fit=data.get('fit', ''),
            season=data.get('season', ''),
            notes=data.get('notes'),
        )

    def create_item(self, item_id: str, item_data: WardrobeItemCreate) -> WardrobeItem:
        """Create a new item."""
        data = item_data.model_dump()

        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO wardrobe_items (id, data, synced_at)
                VALUES (%s, %s, %s)
                """,
                (item_id, Json(data), datetime.now())
            )

        return WardrobeItem(id=item_id, **data)

    def update_item(
        self, item_id: str, item_data: WardrobeItemUpdate
    ) -> Optional[WardrobeItem]:
        """Update an existing item."""
        # Get current data
        current = self.get_item_by_id(item_id)
        if not current:
            return None

        # Merge updates
        current_data = {
            'item': current.item,
            'category': current.category,
            'color': current.color,
            'fit': current.fit,
            'season': current.season,
            'notes': current.notes,
        }
        update_data = item_data.model_dump(exclude_unset=True)
        current_data.update(update_data)

        with self.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE wardrobe_items
                SET data = %s, updated_at = %s
                WHERE id = %s
                """,
                (Json(current_data), datetime.now(), item_id)
            )

        return self.get_item_by_id(item_id)

    def delete_item(self, item_id: str) -> bool:
        """Delete an item."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM wardrobe_items WHERE id = %s RETURNING id",
                (item_id,)
            )
            result = cursor.fetchone()

        return result is not None

    def rename_item_id(self, old_id: str, new_id: str) -> bool:
        """Rename an item's ID."""
        # Check if new_id already exists
        if self.get_item_by_id(new_id):
            return False

        with self.get_cursor() as cursor:
            cursor.execute(
                "UPDATE wardrobe_items SET id = %s WHERE id = %s RETURNING id",
                (new_id, old_id)
            )
            result = cursor.fetchone()

        return result is not None

    def upsert_item(self, item_id: str, data: dict) -> None:
        """Insert or update an item (used for sync)."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO wardrobe_items (id, data, synced_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at
                """,
                (item_id, Json(data), datetime.now())
            )

    def sync_from_sheets(self, items: list[dict]) -> int:
        """
        Bulk sync from Sheets: upsert all items and remove items not in Sheets.
        Returns count of items synced.
        """
        if not items:
            return 0

        sheet_ids = set()

        with self.get_cursor() as cursor:
            for item in items:
                item_id = item.get('id')
                if not item_id:
                    continue

                sheet_ids.add(item_id)
                data = {k: v for k, v in item.items() if k != 'id'}

                cursor.execute(
                    """
                    INSERT INTO wardrobe_items (id, data, synced_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET data = EXCLUDED.data, synced_at = EXCLUDED.synced_at
                    """,
                    (item_id, Json(data), datetime.now())
                )

            # Remove items not in Sheets
            if sheet_ids:
                cursor.execute(
                    "DELETE FROM wardrobe_items WHERE id != ALL(%s)",
                    (list(sheet_ids),)
                )

            # Log sync
            cursor.execute(
                """
                INSERT INTO sync_log (items_synced, source, status)
                VALUES (%s, %s, %s)
                """,
                (len(items), 'sheets', 'success')
            )

        logger.info(f"Synced {len(items)} items from Sheets")
        return len(items)

    def get_last_sync(self) -> Optional[dict]:
        """Get the last sync log entry."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT synced_at, items_synced, source, status
                FROM sync_log
                ORDER BY synced_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()

        if row:
            return {
                'synced_at': row['synced_at'].isoformat() if row['synced_at'] else None,
                'items_synced': row['items_synced'],
                'source': row['source'],
                'status': row['status'],
            }
        return None

    def get_item_count(self) -> int:
        """Get total number of items."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM wardrobe_items")
            row = cursor.fetchone()
        return row['count'] if row else 0

    def get_image_count(self) -> int:
        """Get total number of images."""
        with self.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM image_metadata")
            row = cursor.fetchone()
        return row['count'] if row else 0

    # Image metadata methods
    def get_image_metadata(self, image_id: str) -> Optional[dict]:
        """Get metadata for a single image."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM image_metadata WHERE image_id = %s",
                (image_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_images_for_item(self, item_id: str) -> list[dict]:
        """Get all image metadata for an item, ordered by display_order."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM image_metadata
                WHERE item_id = %s
                ORDER BY display_order, created_at
                """,
                (item_id,)
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def save_image_metadata(
        self,
        image_id: str,
        item_id: str,
        filename: str,
        display_order: int = 0,
        crop_region: Optional[dict] = None,
    ) -> None:
        """Save or update image metadata."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO image_metadata (image_id, item_id, filename, display_order, crop_region)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (image_id) DO UPDATE
                SET filename = EXCLUDED.filename,
                    display_order = EXCLUDED.display_order,
                    crop_region = EXCLUDED.crop_region
                """,
                (
                    image_id, item_id, filename, display_order,
                    Json(crop_region) if crop_region else None
                )
            )

    def delete_image_metadata(self, image_id: str) -> bool:
        """Delete image metadata."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM image_metadata WHERE image_id = %s RETURNING image_id",
                (image_id,)
            )
            result = cursor.fetchone()
        return result is not None

    def delete_images_for_item(self, item_id: str) -> int:
        """Delete all image metadata for an item."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM image_metadata WHERE item_id = %s",
                (item_id,)
            )
            return cursor.rowcount

    def update_image_order(self, item_id: str, image_ids: list[str]) -> bool:
        """Update display order for images."""
        with self.get_cursor() as cursor:
            for order, image_id in enumerate(image_ids):
                cursor.execute(
                    """
                    UPDATE image_metadata
                    SET display_order = %s
                    WHERE image_id = %s AND item_id = %s
                    """,
                    (order, image_id, item_id)
                )
        return True

    def set_crop_region(self, image_id: str, crop_region: dict) -> bool:
        """Set crop region for an image."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE image_metadata
                SET crop_region = %s
                WHERE image_id = %s
                RETURNING image_id
                """,
                (Json(crop_region), image_id)
            )
            result = cursor.fetchone()
        return result is not None

    def rename_item_images(self, old_item_id: str, new_item_id: str) -> int:
        """Update item_id for all images when an item is renamed."""
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE image_metadata
                SET item_id = %s
                WHERE item_id = %s
                """,
                (new_item_id, old_item_id)
            )
            return cursor.rowcount

    def is_connected(self) -> bool:
        """Check if database is accessible."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False

    def get_sync_history(self, limit: int = 10) -> list[dict]:
        """Get recent sync history."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, synced_at, items_synced, source, status, error_message
                    FROM sync_log
                    ORDER BY synced_at DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"Failed to get sync history: {e}")
            return []


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_database_service(settings: Settings) -> DatabaseService:
    """Get or create the database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService(settings)
    return _db_service
