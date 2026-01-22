from io import BytesIO
from app.models.item import WardrobeItem


class TestUploadImage:
    def test_upload_image_success(
        self, client, mock_sheets_service, sample_image_bytes
    ):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.post(
            "/items/1/images",
            files={"file": ("test.png", BytesIO(sample_image_bytes), "image/png")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["item_id"] == "1"
        assert "image_id" in data
        assert "url" in data

    def test_upload_image_item_not_found(
        self, client, mock_sheets_service, sample_image_bytes
    ):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.post(
            "/items/999/images",
            files={"file": ("test.png", BytesIO(sample_image_bytes), "image/png")},
        )

        assert response.status_code == 404

    def test_upload_non_image_rejected(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.post(
            "/items/1/images",
            files={"file": ("test.txt", BytesIO(b"not an image"), "text/plain")},
        )

        assert response.status_code == 400
        assert "must be an image" in response.json()["detail"]


class TestListImagesForItem:
    def test_list_images_success(self, client, mock_sheets_service, storage_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.get("/items/1/images")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_images_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.get("/items/999/images")

        assert response.status_code == 404


class TestGetImage:
    def test_get_image_success(
        self, client, mock_sheets_service, storage_service, sample_image_bytes
    ):
        # First upload an image
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        upload_response = client.post(
            "/items/1/images",
            files={"file": ("test.png", BytesIO(sample_image_bytes), "image/png")},
        )
        image_id = upload_response.json()["image_id"]

        # Now retrieve it
        response = client.get(f"/images/{image_id}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")

    def test_get_image_not_found(self, client, storage_service):
        response = client.get("/images/nonexistent")

        assert response.status_code == 404


class TestDeleteImage:
    def test_delete_image_success(
        self, client, mock_sheets_service, storage_service, sample_image_bytes
    ):
        # First upload an image
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        upload_response = client.post(
            "/items/1/images",
            files={"file": ("test.png", BytesIO(sample_image_bytes), "image/png")},
        )
        image_id = upload_response.json()["image_id"]

        # Now delete it
        response = client.delete(f"/images/{image_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = client.get(f"/images/{image_id}")
        assert get_response.status_code == 404

    def test_delete_image_not_found(self, client, storage_service):
        response = client.delete("/images/nonexistent")

        assert response.status_code == 404


class TestMultipleImages:
    def test_upload_multiple_images_for_item(
        self, client, mock_sheets_service, sample_image_bytes
    ):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        # Upload 3 images
        image_ids = []
        for i in range(3):
            response = client.post(
                "/items/1/images",
                files={
                    "file": (f"image_{i}.png", BytesIO(sample_image_bytes), "image/png")
                },
            )
            assert response.status_code == 201
            image_ids.append(response.json()["image_id"])

        # List should show all 3
        list_response = client.get("/items/1/images")
        assert response.status_code == 201
        assert len(list_response.json()) == 3
