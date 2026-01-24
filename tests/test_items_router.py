from app.models.item import WardrobeItem


class TestListItems:
    def test_list_items_returns_all(self, client, mock_sheets_service):
        mock_sheets_service.get_all_items.return_value = [
            WardrobeItem(
                id="1",
                item="Shirt",
                category="Tops",
                color="Blue",
                fit="Slim",
                season="All",
            ),
            WardrobeItem(
                id="2",
                item="Pants",
                category="Bottoms",
                color="Black",
                fit="Regular",
                season="All",
            ),
        ]

        response = client.get("/items")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "1"
        assert data[1]["id"] == "2"

    def test_list_items_with_category_filter(self, client, mock_sheets_service):
        mock_sheets_service.get_all_items.return_value = [
            WardrobeItem(
                id="1",
                item="Shirt",
                category="Tops",
                color="Blue",
                fit="Slim",
                season="All",
            ),
        ]

        response = client.get("/items?category=Tops")

        assert response.status_code == 200
        mock_sheets_service.get_all_items.assert_called_with(
            category="Tops", color=None, season=None
        )

    def test_list_items_with_multiple_filters(self, client, mock_sheets_service):
        mock_sheets_service.get_all_items.return_value = []

        response = client.get("/items?category=Tops&color=Blue&season=Summer")

        assert response.status_code == 200
        mock_sheets_service.get_all_items.assert_called_with(
            category="Tops", color="Blue", season="Summer"
        )

    def test_list_items_empty(self, client, mock_sheets_service):
        mock_sheets_service.get_all_items.return_value = []

        response = client.get("/items")

        assert response.status_code == 200
        assert response.json() == []


class TestGetItem:
    def test_get_item_found(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Navy Shirt",
            category="Tops",
            color="Navy",
            fit="Slim",
            season="All",
            notes="Favorite",
        )

        response = client.get("/items/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "1"
        assert data["item"] == "Navy Shirt"
        assert data["notes"] == "Favorite"

    def test_get_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.get("/items/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestCreateItem:
    def test_create_item_success(self, client, mock_sheets_service, sample_item_create):
        mock_sheets_service.create_item.return_value = WardrobeItem(
            id="1", **sample_item_create
        )

        response = client.post("/items", json=sample_item_create)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "1"
        assert data["item"] == sample_item_create["item"]

    def test_create_item_validation_error(self, client, mock_sheets_service):
        invalid_data = {"item": "Test"}  # Missing required fields

        response = client.post("/items", json=invalid_data)

        assert response.status_code == 422


class TestUpdateItem:
    def test_update_item_success(self, client, mock_sheets_service):
        mock_sheets_service.update_item.return_value = WardrobeItem(
            id="1",
            item="Updated Shirt",
            category="Tops",
            color="Red",
            fit="Slim",
            season="All",
        )

        response = client.put("/items/1", json={"color": "Red"})

        assert response.status_code == 200
        assert response.json()["color"] == "Red"

    def test_update_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.update_item.return_value = None

        response = client.put("/items/999", json={"color": "Red"})

        assert response.status_code == 404

    def test_update_item_multiple_fields(self, client, mock_sheets_service):
        mock_sheets_service.update_item.return_value = WardrobeItem(
            id="1",
            item="New Name",
            category="Bottoms",
            color="Blue",
            fit="Regular",
            season="Winter",
            notes="Updated notes",
        )

        response = client.put(
            "/items/1",
            json={
                "item": "New Name",
                "category": "Bottoms",
                "notes": "Updated notes",
            },
        )

        assert response.status_code == 200


class TestDeleteItem:
    def test_delete_item_success(self, client, mock_sheets_service, storage_service):
        mock_sheets_service.delete_item.return_value = True

        response = client.delete("/items/1")

        assert response.status_code == 204
        mock_sheets_service.delete_item.assert_called_with("1")

    def test_delete_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.delete_item.return_value = False

        response = client.delete("/items/999")

        assert response.status_code == 404


class TestRenameItemId:
    def test_rename_item_success(self, client, mock_sheets_service, storage_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="old_id",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )
        mock_sheets_service.rename_item_id.return_value = True
        storage_service.rename_item_folder = lambda old, new: True

        # After rename, get_item_by_id should return the updated item
        def get_item_side_effect(item_id):
            if item_id == "new_id":
                return WardrobeItem(
                    id="new_id",
                    item="Shirt",
                    category="Tops",
                    color="Blue",
                    fit="Slim",
                    season="All",
                )
            return WardrobeItem(
                id="old_id",
                item="Shirt",
                category="Tops",
                color="Blue",
                fit="Slim",
                season="All",
            )

        mock_sheets_service.get_item_by_id.side_effect = get_item_side_effect

        response = client.put("/items/old_id/rename", json={"new_id": "new_id"})

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "new_id"

    def test_rename_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.put("/items/nonexistent/rename", json={"new_id": "new_id"})

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_rename_item_empty_new_id(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="old_id",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.put("/items/old_id/rename", json={"new_id": ""})

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_rename_item_invalid_characters(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="old_id",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.put("/items/old_id/rename", json={"new_id": "bad/id"})

        assert response.status_code == 400
        assert "invalid characters" in response.json()["detail"].lower()

    def test_rename_item_new_id_exists(self, client, mock_sheets_service, storage_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="old_id",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )
        # rename_item_id returns False when new_id already exists
        mock_sheets_service.rename_item_id.return_value = False

        response = client.put("/items/old_id/rename", json={"new_id": "existing_id"})

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()
