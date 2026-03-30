import json
import logging
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional

from app.config import Settings
from app.models.item import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate, WashCare
from app.services.database import DatabaseService, get_database_service

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column mapping (1-indexed for gspread)
COLUMNS = {
    "id": 1,
    "item": 2,
    "category": 3,
    "color": 4,
    "fit": 5,
    "season": 6,
    "notes": 7,
    # Wash care columns
    "fabric": 8,
    "wash_temp": 9,
    "dry_method": 10,
    "color_group": 11,
    "delicate": 12,
    "separate": 13,
    "care_notes": 14,
}


class SheetsService:
    """Google Sheets service with dual-write to PostgreSQL."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Worksheet] = None
        self._db: Optional[DatabaseService] = None

    @property
    def db(self) -> DatabaseService:
        """Lazy load database service."""
        if self._db is None:
            self._db = get_database_service(self.settings)
        return self._db

    def _get_client(self) -> gspread.Client:
        if self._client is None:
            credentials_info = json.loads(self.settings.google_sheets_credentials_json)
            credentials = Credentials.from_service_account_info(
                credentials_info,
                scopes=SCOPES,
            )
            self._client = gspread.authorize(credentials)
        return self._client

    def _get_sheet(self) -> gspread.Worksheet:
        if self._sheet is None:
            client = self._get_client()
            spreadsheet = client.open_by_key(self.settings.google_sheet_id)
            self._sheet = spreadsheet.sheet1
        return self._sheet

    def _parse_bool(self, value: str) -> Optional[bool]:
        """Parse boolean from Sheets cell (TRUE/FALSE or Yes/No)."""
        if not value:
            return None
        v = value.strip().upper()
        if v in ('TRUE', 'YES', '1'):
            return True
        if v in ('FALSE', 'NO', '0'):
            return False
        return None

    def _parse_wash_care(self, row: list) -> Optional[WashCare]:
        """Parse wash care fields from row columns 8-14."""
        # Check if any wash care data exists (0-indexed: col 8 = index 7)
        fabric = str(row[7]).strip() if len(row) > 7 and row[7] else None
        wash_temp = str(row[8]).strip() if len(row) > 8 and row[8] else None
        dry_method = str(row[9]).strip() if len(row) > 9 and row[9] else None
        color_group = str(row[10]).strip() if len(row) > 10 and row[10] else None
        delicate = self._parse_bool(str(row[11])) if len(row) > 11 else None
        separate = self._parse_bool(str(row[12])) if len(row) > 12 else None
        care_notes = str(row[13]).strip() if len(row) > 13 and row[13] else None

        # Only create WashCare if at least one field has data
        if any([fabric, wash_temp, dry_method, color_group,
                delicate is not None, separate is not None, care_notes]):
            return WashCare(
                fabric=fabric,
                wash_temp=wash_temp,
                dry_method=dry_method,
                color_group=color_group,
                delicate=delicate,
                separate=separate,
                notes=care_notes,
            )
        return None

    def _row_to_item(self, row: list, row_index: int) -> Optional[WardrobeItem]:
        if len(row) < 6 or not row[0]:
            return None

        wash_care = self._parse_wash_care(row)

        return WardrobeItem(
            id=str(row[0]),
            item=str(row[1]) if len(row) > 1 else "",
            category=str(row[2]) if len(row) > 2 else "",
            color=str(row[3]) if len(row) > 3 else "",
            fit=str(row[4]) if len(row) > 4 else "",
            season=str(row[5]) if len(row) > 5 else "",
            notes=str(row[6]) if len(row) > 6 and row[6] else None,
            wash_care=wash_care,
        )

    def _row_to_dict(self, row: list) -> Optional[dict]:
        """Convert row to dict for DB sync."""
        if len(row) < 6 or not row[0]:
            return None

        wash_care = self._parse_wash_care(row)

        return {
            'id': str(row[0]),
            'item': str(row[1]) if len(row) > 1 else "",
            'category': str(row[2]) if len(row) > 2 else "",
            'color': str(row[3]) if len(row) > 3 else "",
            'fit': str(row[4]) if len(row) > 4 else "",
            'season': str(row[5]) if len(row) > 5 else "",
            'notes': str(row[6]) if len(row) > 6 and row[6] else None,
            'wash_care': wash_care.model_dump() if wash_care else None,
        }

    def get_all_items(
        self,
        category: Optional[str] = None,
        color: Optional[str] = None,
        season: Optional[str] = None,
    ) -> list[WardrobeItem]:
        """Get items - reads from database for speed."""
        return self.db.get_all_items(category=category, color=color, season=season)

    def get_all_items_from_sheets(self) -> list[dict]:
        """Get all items directly from Sheets (for sync)."""
        sheet = self._get_sheet()
        all_rows = sheet.get_all_values()

        items = []
        for row in all_rows[1:]:  # Skip header row
            item_dict = self._row_to_dict(row)
            if item_dict:
                items.append(item_dict)

        return items

    def get_item_by_id(self, item_id: str) -> Optional[WardrobeItem]:
        """Get item by ID - reads from database."""
        return self.db.get_item_by_id(item_id)

    def _find_row_by_id(self, item_id: str) -> Optional[int]:
        sheet = self._get_sheet()
        all_rows = sheet.get_all_values()

        for i, row in enumerate(all_rows[1:], start=2):
            if row and str(row[0]) == item_id:
                return i

        return None

    def _generate_next_id(self) -> str:
        sheet = self._get_sheet()
        all_rows = sheet.get_all_values()

        max_id = 0
        for row in all_rows[1:]:
            if row and row[0]:
                try:
                    current_id = int(row[0])
                    max_id = max(max_id, current_id)
                except ValueError:
                    continue

        return str(max_id + 1)

    def _bool_to_sheets(self, value: Optional[bool]) -> str:
        """Convert boolean to Sheets-friendly string."""
        if value is None:
            return ""
        return "TRUE" if value else "FALSE"

    def create_item(self, item_data: WardrobeItemCreate) -> WardrobeItem:
        """Create item - writes to Sheets first, then DB."""
        sheet = self._get_sheet()
        new_id = self._generate_next_id()

        # Build wash care columns
        wc = item_data.wash_care
        wash_care_cols = [
            wc.fabric or "" if wc else "",
            wc.wash_temp or "" if wc else "",
            wc.dry_method or "" if wc else "",
            wc.color_group or "" if wc else "",
            self._bool_to_sheets(wc.delicate) if wc else "",
            self._bool_to_sheets(wc.separate) if wc else "",
            wc.notes or "" if wc else "",
        ]

        new_row = [
            new_id,
            item_data.item,
            item_data.category,
            item_data.color,
            item_data.fit,
            item_data.season,
            item_data.notes or "",
        ] + wash_care_cols

        # Write to Sheets first (source of truth)
        sheet.append_row(new_row)
        logger.info(f"Created item {new_id} in Sheets")

        # Then write to DB
        item = self.db.create_item(new_id, item_data)
        logger.info(f"Created item {new_id} in DB")

        return item

    def update_item(
        self, item_id: str, item_data: WardrobeItemUpdate
    ) -> Optional[WardrobeItem]:
        """Update item - writes to Sheets first, then DB."""
        row_index = self._find_row_by_id(item_id)
        if row_index is None:
            return None

        sheet = self._get_sheet()

        # Update only fields that are provided
        update_data = item_data.model_dump(exclude_unset=True)

        # Write to Sheets first
        if "item" in update_data:
            sheet.update_cell(row_index, COLUMNS["item"], update_data["item"])
        if "category" in update_data:
            sheet.update_cell(row_index, COLUMNS["category"], update_data["category"])
        if "color" in update_data:
            sheet.update_cell(row_index, COLUMNS["color"], update_data["color"])
        if "fit" in update_data:
            sheet.update_cell(row_index, COLUMNS["fit"], update_data["fit"])
        if "season" in update_data:
            sheet.update_cell(row_index, COLUMNS["season"], update_data["season"])
        if "notes" in update_data:
            sheet.update_cell(row_index, COLUMNS["notes"], update_data["notes"] or "")

        # Handle wash_care updates
        if "wash_care" in update_data:
            wc = update_data["wash_care"]
            if wc is None:
                # Clear all wash care columns
                sheet.update_cell(row_index, COLUMNS["fabric"], "")
                sheet.update_cell(row_index, COLUMNS["wash_temp"], "")
                sheet.update_cell(row_index, COLUMNS["dry_method"], "")
                sheet.update_cell(row_index, COLUMNS["color_group"], "")
                sheet.update_cell(row_index, COLUMNS["delicate"], "")
                sheet.update_cell(row_index, COLUMNS["separate"], "")
                sheet.update_cell(row_index, COLUMNS["care_notes"], "")
            else:
                # Update wash care fields
                if "fabric" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["fabric"], wc["fabric"] or ""
                    )
                if "wash_temp" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["wash_temp"], wc["wash_temp"] or ""
                    )
                if "dry_method" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["dry_method"], wc["dry_method"] or ""
                    )
                if "color_group" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["color_group"], wc["color_group"] or ""
                    )
                if "delicate" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["delicate"],
                        self._bool_to_sheets(wc["delicate"])
                    )
                if "separate" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["separate"],
                        self._bool_to_sheets(wc["separate"])
                    )
                if "notes" in wc:
                    sheet.update_cell(
                        row_index, COLUMNS["care_notes"], wc["notes"] or ""
                    )

        logger.info(f"Updated item {item_id} in Sheets")

        # Then update DB
        item = self.db.update_item(item_id, item_data)
        logger.info(f"Updated item {item_id} in DB")

        return item

    def delete_item(self, item_id: str) -> bool:
        """Delete item - deletes from Sheets first, then DB."""
        row_index = self._find_row_by_id(item_id)
        if row_index is None:
            return False

        sheet = self._get_sheet()
        sheet.delete_rows(row_index)
        logger.info(f"Deleted item {item_id} from Sheets")

        # Then delete from DB
        self.db.delete_item(item_id)
        logger.info(f"Deleted item {item_id} from DB")

        return True

    def rename_item_id(self, old_id: str, new_id: str) -> bool:
        """Rename item ID - updates Sheets first, then DB."""
        # Check if new_id already exists
        if self.get_item_by_id(new_id) is not None:
            return False

        row_index = self._find_row_by_id(old_id)
        if row_index is None:
            return False

        sheet = self._get_sheet()
        sheet.update_cell(row_index, COLUMNS["id"], new_id)
        logger.info(f"Renamed item {old_id} -> {new_id} in Sheets")

        # Then rename in DB
        self.db.rename_item_id(old_id, new_id)
        # Also update image metadata
        self.db.rename_item_images(old_id, new_id)
        logger.info(f"Renamed item {old_id} -> {new_id} in DB")

        return True

    def sync_to_db(self) -> int:
        """Sync all data from Sheets to DB."""
        items = self.get_all_items_from_sheets()
        count = self.db.sync_from_sheets(items)
        logger.info(f"Synced {count} items from Sheets to DB")
        return count


SAMPLE_ITEMS = [
    {"item": "Navy Oxford Shirt", "category": "Tops", "color": "Navy Blue", "fit": "Slim", "season": "All", "notes": "Classic work shirt"},
    {"item": "White T-Shirt", "category": "Tops", "color": "White", "fit": "Regular", "season": "Summer", "notes": "Basic essential"},
    {"item": "Black Jeans", "category": "Bottoms", "color": "Black", "fit": "Slim", "season": "All", "notes": None},
    {"item": "Khaki Chinos", "category": "Bottoms", "color": "Khaki", "fit": "Regular", "season": "All", "notes": "Business casual"},
    {"item": "Grey Wool Sweater", "category": "Tops", "color": "Grey", "fit": "Regular", "season": "Winter", "notes": "Merino wool"},
    {"item": "Leather Jacket", "category": "Outerwear", "color": "Brown", "fit": "Regular", "season": "Fall", "notes": "Vintage style"},
    {"item": "Running Shoes", "category": "Shoes", "color": "Black", "fit": "Regular", "season": "All", "notes": "Nike Air Max"},
    {"item": "Dress Shoes", "category": "Shoes", "color": "Brown", "fit": "Regular", "season": "All", "notes": "Oxford style"},
    {"item": "Denim Jacket", "category": "Outerwear", "color": "Blue", "fit": "Regular", "season": "Spring", "notes": "Light wash"},
    {"item": "Wool Coat", "category": "Outerwear", "color": "Charcoal", "fit": "Regular", "season": "Winter", "notes": "Long overcoat"},
]


class DummyModeService:
    """
    DB-backed service for dummy mode (no Google Sheets connection).
    Uses PostgreSQL but skips Sheets operations.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._db: Optional[DatabaseService] = None

    @property
    def db(self) -> DatabaseService:
        """Lazy load database service."""
        if self._db is None:
            self._db = get_database_service(self.settings)
        return self._db

    def seed_sample_data(self) -> int:
        """Populate with sample clothing items. Returns count of items added."""
        if self.db.get_item_count() > 0:
            return 0  # Don't seed if items already exist

        for item_data in SAMPLE_ITEMS:
            item_create = WardrobeItemCreate(**item_data)
            # Generate ID
            count = self.db.get_item_count()
            new_id = str(count + 1)
            self.db.create_item(new_id, item_create)

        logger.info(f"Seeded {len(SAMPLE_ITEMS)} sample items")
        return len(SAMPLE_ITEMS)

    def get_all_items(
        self,
        category: Optional[str] = None,
        color: Optional[str] = None,
        season: Optional[str] = None,
    ) -> list[WardrobeItem]:
        return self.db.get_all_items(category=category, color=color, season=season)

    def get_item_by_id(self, item_id: str) -> Optional[WardrobeItem]:
        return self.db.get_item_by_id(item_id)

    def create_item(self, item_data: WardrobeItemCreate) -> WardrobeItem:
        # Generate next ID
        count = self.db.get_item_count()
        new_id = str(count + 1)
        return self.db.create_item(new_id, item_data)

    def update_item(
        self, item_id: str, item_data: WardrobeItemUpdate
    ) -> Optional[WardrobeItem]:
        return self.db.update_item(item_id, item_data)

    def delete_item(self, item_id: str) -> bool:
        # Also delete images
        self.db.delete_images_for_item(item_id)
        return self.db.delete_item(item_id)

    def rename_item_id(self, old_id: str, new_id: str) -> bool:
        if self.db.get_item_by_id(new_id) is not None:
            return False
        if not self.db.rename_item_id(old_id, new_id):
            return False
        self.db.rename_item_images(old_id, new_id)
        return True


_sheets_service: Optional[SheetsService] = None
_dummy_service: Optional[DummyModeService] = None


def get_sheets_service(settings: Settings) -> SheetsService | DummyModeService:
    global _sheets_service, _dummy_service

    if settings.dummy_mode:
        if _dummy_service is None:
            _dummy_service = DummyModeService(settings)
        return _dummy_service

    if _sheets_service is None:
        _sheets_service = SheetsService(settings)
    return _sheets_service
