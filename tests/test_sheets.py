import pytest
from unittest.mock import MagicMock
from app.services.sheets import SheetsService, COLUMNS
from app.models.item import WardrobeItemCreate, WardrobeItemUpdate
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
        api_key="test-key",
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-sheet-id",
        images_dir="/fake/images",
    )


@pytest.fixture
def mock_worksheet():
    """Create a mock gspread worksheet."""
    worksheet = MagicMock()
    return worksheet


@pytest.fixture
def sheets_service(settings, mock_worksheet):
    """Create SheetsService with mocked gspread."""
    service = SheetsService(settings)
    service._sheet = mock_worksheet
    service._client = MagicMock()
    return service


class TestRowToItem:
    def test_valid_row(self, sheets_service):
        row = ["1", "Navy Shirt", "Tops", "Navy", "Slim", "All", "Notes here"]
        item = sheets_service._row_to_item(row, 2)

        assert item is not None
        assert item.id == "1"
        assert item.item == "Navy Shirt"
        assert item.category == "Tops"
        assert item.color == "Navy"
        assert item.fit == "Slim"
        assert item.season == "All"
        assert item.notes == "Notes here"

    def test_row_without_notes(self, sheets_service):
        row = ["2", "White Tee", "Tops", "White", "Regular", "Summer"]
        item = sheets_service._row_to_item(row, 2)

        assert item is not None
        assert item.notes is None

    def test_row_with_empty_notes(self, sheets_service):
        row = ["3", "Item", "Cat", "Color", "Fit", "Season", ""]
        item = sheets_service._row_to_item(row, 2)

        assert item is not None
        assert item.notes is None

    def test_empty_row(self, sheets_service):
        row = []
        item = sheets_service._row_to_item(row, 2)
        assert item is None

    def test_row_with_empty_id(self, sheets_service):
        row = ["", "Item", "Cat", "Color", "Fit", "Season"]
        item = sheets_service._row_to_item(row, 2)
        assert item is None

    def test_row_too_short(self, sheets_service):
        row = ["1", "Item", "Cat"]
        item = sheets_service._row_to_item(row, 2)
        assert item is None


class TestGetAllItems:
    def test_returns_all_items(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["2", "Pants", "Bottoms", "Black", "Regular", "All", "Favorite"],
        ]

        items = sheets_service.get_all_items()

        assert len(items) == 2
        assert items[0].id == "1"
        assert items[1].id == "2"

    def test_filter_by_category(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["2", "Pants", "Bottoms", "Black", "Regular", "All", ""],
            ["3", "Jacket", "Tops", "Navy", "Slim", "Winter", ""],
        ]

        items = sheets_service.get_all_items(category="Tops")

        assert len(items) == 2
        assert all(item.category == "Tops" for item in items)

    def test_filter_by_color(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["2", "Pants", "Bottoms", "Blue", "Regular", "All", ""],
            ["3", "Jacket", "Tops", "Navy", "Slim", "Winter", ""],
        ]

        items = sheets_service.get_all_items(color="Blue")

        assert len(items) == 2

    def test_filter_by_season(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "Summer", ""],
            ["2", "Pants", "Bottoms", "Black", "Regular", "Winter", ""],
        ]

        items = sheets_service.get_all_items(season="Winter")

        assert len(items) == 1
        assert items[0].season == "Winter"

    def test_filter_case_insensitive(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "TOPS", "Blue", "Slim", "All", ""],
        ]

        items = sheets_service.get_all_items(category="tops")
        assert len(items) == 1

    def test_empty_sheet(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
        ]

        items = sheets_service.get_all_items()
        assert len(items) == 0


class TestGetItemById:
    def test_found(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["2", "Pants", "Bottoms", "Black", "Regular", "All", ""],
        ]

        item = sheets_service.get_item_by_id("2")

        assert item is not None
        assert item.id == "2"
        assert item.item == "Pants"

    def test_not_found(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]

        item = sheets_service.get_item_by_id("999")
        assert item is None


class TestGenerateNextId:
    def test_increments_max_id(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["5", "Pants", "Bottoms", "Black", "Regular", "All", ""],
            ["3", "Jacket", "Tops", "Navy", "Slim", "Winter", ""],
        ]

        next_id = sheets_service._generate_next_id()
        assert next_id == "6"

    def test_empty_sheet(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
        ]

        next_id = sheets_service._generate_next_id()
        assert next_id == "1"


class TestCreateItem:
    def test_creates_item(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]

        item_data = WardrobeItemCreate(
            item="New Jacket",
            category="Outerwear",
            color="Black",
            fit="Regular",
            season="Winter",
            notes="Brand new",
        )

        result = sheets_service.create_item(item_data)

        assert result.id == "2"
        assert result.item == "New Jacket"
        mock_worksheet.append_row.assert_called_once()


class TestUpdateItem:
    def test_updates_item(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]
        mock_worksheet.row_values.return_value = ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""]

        update_data = WardrobeItemUpdate(color="Red")
        sheets_service.update_item("1", update_data)

        mock_worksheet.update_cell.assert_called_with(2, COLUMNS["color"], "Red")

    def test_update_not_found(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
        ]

        update_data = WardrobeItemUpdate(color="Red")
        result = sheets_service.update_item("999", update_data)

        assert result is None


class TestDeleteItem:
    def test_deletes_item(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]

        result = sheets_service.delete_item("1")

        assert result is True
        mock_worksheet.delete_rows.assert_called_once_with(2)

    def test_delete_not_found(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
        ]

        result = sheets_service.delete_item("999")

        assert result is False
        mock_worksheet.delete_rows.assert_not_called()


class TestRenameItemId:
    def test_rename_success(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["old_id", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]

        result = sheets_service.rename_item_id("old_id", "new_id")

        assert result is True
        mock_worksheet.update_cell.assert_called_once_with(2, COLUMNS["id"], "new_id")

    def test_rename_old_id_not_found(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["1", "Shirt", "Tops", "Blue", "Slim", "All", ""],
        ]

        result = sheets_service.rename_item_id("nonexistent", "new_id")

        assert result is False
        mock_worksheet.update_cell.assert_not_called()

    def test_rename_new_id_already_exists(self, sheets_service, mock_worksheet):
        mock_worksheet.get_all_values.return_value = [
            ["ID", "Item", "Category", "Color", "Fit", "Season", "Notes"],
            ["old_id", "Shirt", "Tops", "Blue", "Slim", "All", ""],
            ["new_id", "Pants", "Bottoms", "Black", "Regular", "All", ""],
        ]

        result = sheets_service.rename_item_id("old_id", "new_id")

        assert result is False
        mock_worksheet.update_cell.assert_not_called()
