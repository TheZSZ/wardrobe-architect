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


_sheets_service: Optional[SheetsService] = None


def get_sheets_service(settings: Settings) -> SheetsService:
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = SheetsService(settings)
    return _sheets_service
