import json
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional
from app.config import Settings
from app.models.item import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate


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
}


class SheetsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Optional[gspread.Client] = None
        self._sheet: Optional[gspread.Worksheet] = None

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

    def _row_to_item(self, row: list, row_index: int) -> Optional[WardrobeItem]:
        if len(row) < 6 or not row[0]:
            return None
        return WardrobeItem(
            id=str(row[0]),
            item=str(row[1]) if len(row) > 1 else "",
            category=str(row[2]) if len(row) > 2 else "",
            color=str(row[3]) if len(row) > 3 else "",
            fit=str(row[4]) if len(row) > 4 else "",
            season=str(row[5]) if len(row) > 5 else "",
            notes=str(row[6]) if len(row) > 6 and row[6] else None,
        )

    def get_all_items(
        self,
        category: Optional[str] = None,
        color: Optional[str] = None,
        season: Optional[str] = None,
    ) -> list[WardrobeItem]:
        sheet = self._get_sheet()
        all_rows = sheet.get_all_values()

        items = []
        for i, row in enumerate(all_rows[1:], start=2):  # Skip header row
            item = self._row_to_item(row, i)
            if item is None:
                continue

            # Apply filters
            if category and item.category.lower() != category.lower():
                continue
            if color and item.color.lower() != color.lower():
                continue
            if season and item.season.lower() != season.lower():
                continue

            items.append(item)

        return items

    def get_item_by_id(self, item_id: str) -> Optional[WardrobeItem]:
        sheet = self._get_sheet()
        all_rows = sheet.get_all_values()

        for i, row in enumerate(all_rows[1:], start=2):
            if row and str(row[0]) == item_id:
                return self._row_to_item(row, i)

        return None

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

    def create_item(self, item_data: WardrobeItemCreate) -> WardrobeItem:
        sheet = self._get_sheet()
        new_id = self._generate_next_id()

        new_row = [
            new_id,
            item_data.item,
            item_data.category,
            item_data.color,
            item_data.fit,
            item_data.season,
            item_data.notes or "",
        ]

        sheet.append_row(new_row)

        return WardrobeItem(id=new_id, **item_data.model_dump())

    def update_item(self, item_id: str, item_data: WardrobeItemUpdate) -> Optional[WardrobeItem]:
        row_index = self._find_row_by_id(item_id)
        if row_index is None:
            return None

        sheet = self._get_sheet()

        # Update only fields that are provided
        update_data = item_data.model_dump(exclude_unset=True)

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

        return self.get_item_by_id(item_id)

    def delete_item(self, item_id: str) -> bool:
        row_index = self._find_row_by_id(item_id)
        if row_index is None:
            return False

        sheet = self._get_sheet()
        sheet.delete_rows(row_index)
        return True

    def rename_item_id(self, old_id: str, new_id: str) -> bool:
        """Rename an item's ID. Returns False if old_id not found or new_id exists."""
        # Check if new_id already exists
        if self.get_item_by_id(new_id) is not None:
            return False

        row_index = self._find_row_by_id(old_id)
        if row_index is None:
            return False

        sheet = self._get_sheet()
        sheet.update_cell(row_index, COLUMNS["id"], new_id)
        return True


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


class MockSheetsService:
    """In-memory mock service for dummy mode testing."""

    def __init__(self):
        self._items: dict[str, dict] = {}
        self._next_id = 1

    def seed_sample_data(self) -> int:
        """Populate with sample clothing items. Returns count of items added."""
        if self._items:
            return 0  # Don't seed if items already exist
        for item_data in SAMPLE_ITEMS:
            self.create_item(WardrobeItemCreate(**item_data))
        return len(SAMPLE_ITEMS)

    def get_all_items(
        self,
        category: Optional[str] = None,
        color: Optional[str] = None,
        season: Optional[str] = None,
    ) -> list[WardrobeItem]:
        items = []
        for item_data in self._items.values():
            item = WardrobeItem(**item_data)
            if category and item.category.lower() != category.lower():
                continue
            if color and item.color.lower() != color.lower():
                continue
            if season and item.season.lower() != season.lower():
                continue
            items.append(item)
        return items

    def get_item_by_id(self, item_id: str) -> Optional[WardrobeItem]:
        item_data = self._items.get(item_id)
        if item_data:
            return WardrobeItem(**item_data)
        return None

    def create_item(self, item_data: WardrobeItemCreate) -> WardrobeItem:
        new_id = str(self._next_id)
        self._next_id += 1
        item_dict = {"id": new_id, **item_data.model_dump()}
        self._items[new_id] = item_dict
        return WardrobeItem(**item_dict)

    def update_item(self, item_id: str, item_data: WardrobeItemUpdate) -> Optional[WardrobeItem]:
        if item_id not in self._items:
            return None
        update_data = item_data.model_dump(exclude_unset=True)
        self._items[item_id].update(update_data)
        return WardrobeItem(**self._items[item_id])

    def delete_item(self, item_id: str) -> bool:
        if item_id not in self._items:
            return False
        del self._items[item_id]
        return True

    def rename_item_id(self, old_id: str, new_id: str) -> bool:
        """Rename an item's ID. Returns False if old_id not found or new_id exists."""
        if new_id in self._items:
            return False
        if old_id not in self._items:
            return False

        # Move item data to new key
        item_data = self._items.pop(old_id)
        item_data["id"] = new_id
        self._items[new_id] = item_data
        return True


_sheets_service: Optional[SheetsService] = None
_mock_service: Optional[MockSheetsService] = None


def get_sheets_service(settings: Settings) -> SheetsService | MockSheetsService:
    global _sheets_service, _mock_service

    if settings.dummy_mode:
        if _mock_service is None:
            _mock_service = MockSheetsService()
        return _mock_service

    if _sheets_service is None:
        _sheets_service = SheetsService(settings)
    return _sheets_service
