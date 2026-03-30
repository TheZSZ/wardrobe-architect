from io import BytesIO
import httpx
import respx
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


class TestCropRegion:
    def test_set_crop_region_success(
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

        # Set crop region
        response = client.put(
            f"/images/{image_id}/crop",
            json={"x": 10, "y": 20, "size": 50},
        )

        assert response.status_code == 200
        assert "updated" in response.json()["message"].lower()

    def test_set_crop_region_image_not_found(self, client, storage_service):
        response = client.put(
            "/images/nonexistent/crop",
            json={"x": 10, "y": 20, "size": 50},
        )

        assert response.status_code == 404

    def test_set_crop_region_invalid_values(
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

        # Try invalid crop (x + size > 100)
        response = client.put(
            f"/images/{image_id}/crop",
            json={"x": 80, "y": 0, "size": 30},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_crop_region_included_in_list(
        self, client, mock_sheets_service, storage_service, sample_image_bytes
    ):
        # Upload an image
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

        # Set crop region
        client.put(
            f"/images/{image_id}/crop",
            json={"x": 25, "y": 25, "size": 50},
        )

        # List images should include crop region
        list_response = client.get("/items/1/images")
        assert list_response.status_code == 200
        images = list_response.json()
        assert len(images) == 1
        assert images[0]["crop_region"] == {"x": 25, "y": 25, "size": 50}


class TestUploadImageFromUrl:
    """Tests for the single URL upload endpoint."""

    @respx.mock
    def test_upload_from_url_success(
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

        # Mock the external URL
        respx.get("https://example.com/image.png").mock(
            return_value=httpx.Response(
                200,
                content=sample_image_bytes,
                headers={"content-type": "image/png"},
            )
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "https://example.com/image.png"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["item_id"] == "1"
        assert "image_id" in data
        assert "url" in data

    @respx.mock
    def test_upload_from_url_item_not_found(
        self, client, mock_sheets_service, sample_image_bytes
    ):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.post(
            "/items/999/images/from-url",
            json={"url": "https://example.com/image.png"},
        )

        assert response.status_code == 404

    def test_upload_from_url_invalid_scheme(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "ftp://example.com/image.png"},
        )

        assert response.status_code == 400
        assert "http" in response.json()["detail"].lower()

    @respx.mock
    def test_upload_from_url_not_an_image(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        # Mock response with non-image content type
        respx.get("https://example.com/file.txt").mock(
            return_value=httpx.Response(
                200,
                content=b"not an image",
                headers={"content-type": "text/plain"},
            )
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "https://example.com/file.txt"},
        )

        assert response.status_code == 400
        assert "image" in response.json()["detail"].lower()

    @respx.mock
    def test_upload_from_url_invalid_image_bytes(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        # Mock response claims to be image but bytes are invalid
        respx.get("https://example.com/fake.png").mock(
            return_value=httpx.Response(
                200,
                content=b"not valid image bytes",
                headers={"content-type": "image/png"},
            )
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "https://example.com/fake.png"},
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    @respx.mock
    def test_upload_from_url_http_error(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        respx.get("https://example.com/notfound.png").mock(
            return_value=httpx.Response(404)
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "https://example.com/notfound.png"},
        )

        assert response.status_code == 400
        assert "404" in response.json()["detail"]

    @respx.mock
    def test_upload_from_url_timeout(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        respx.get("https://example.com/slow.png").mock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )

        response = client.post(
            "/items/1/images/from-url",
            json={"url": "https://example.com/slow.png"},
        )

        assert response.status_code == 400
        assert "timeout" in response.json()["detail"].lower()


class TestUploadImagesFromUrls:
    """Tests for the batch URL upload endpoint."""

    @respx.mock
    def test_batch_upload_all_success(
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

        # Mock multiple URLs
        for i in range(3):
            respx.get(f"https://example.com/image{i}.png").mock(
                return_value=httpx.Response(
                    200,
                    content=sample_image_bytes,
                    headers={"content-type": "image/png"},
                )
            )

        response = client.post(
            "/items/1/images/from-urls",
            json={
                "urls": [
                    "https://example.com/image0.png",
                    "https://example.com/image1.png",
                    "https://example.com/image2.png",
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] == 3
        assert data["failed"] == 0
        assert len(data["results"]) == 3
        for result in data["results"]:
            assert result["success"] is True
            assert result["image"] is not None

    @respx.mock
    def test_batch_upload_partial_success(
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

        # First URL succeeds
        respx.get("https://example.com/good.png").mock(
            return_value=httpx.Response(
                200,
                content=sample_image_bytes,
                headers={"content-type": "image/png"},
            )
        )
        # Second URL fails (404)
        respx.get("https://example.com/notfound.png").mock(
            return_value=httpx.Response(404)
        )
        # Third URL fails (timeout)
        respx.get("https://example.com/slow.png").mock(
            side_effect=httpx.TimeoutException("timeout")
        )

        response = client.post(
            "/items/1/images/from-urls",
            json={
                "urls": [
                    "https://example.com/good.png",
                    "https://example.com/notfound.png",
                    "https://example.com/slow.png",
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 2

        # Check individual results
        results = {r["url"]: r for r in data["results"]}
        assert results["https://example.com/good.png"]["success"] is True
        assert results["https://example.com/notfound.png"]["success"] is False
        assert results["https://example.com/slow.png"]["success"] is False

    @respx.mock
    def test_batch_upload_all_fail(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        respx.get("https://example.com/bad1.png").mock(
            return_value=httpx.Response(500)
        )
        respx.get("https://example.com/bad2.png").mock(
            return_value=httpx.Response(500)
        )

        response = client.post(
            "/items/1/images/from-urls",
            json={
                "urls": [
                    "https://example.com/bad1.png",
                    "https://example.com/bad2.png",
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 2

    def test_batch_upload_item_not_found(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = None

        response = client.post(
            "/items/999/images/from-urls",
            json={"urls": ["https://example.com/image.png"]},
        )

        assert response.status_code == 404

    def test_batch_upload_empty_urls(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.post(
            "/items/1/images/from-urls",
            json={"urls": []},
        )

        # Should fail validation (min_length=1)
        assert response.status_code == 422

    def test_batch_upload_too_many_urls(self, client, mock_sheets_service):
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        response = client.post(
            "/items/1/images/from-urls",
            json={"urls": [f"https://example.com/{i}.png" for i in range(11)]},
        )

        # Should fail validation (max_length=10)
        assert response.status_code == 422

    @respx.mock
    def test_batch_upload_includes_api_key_in_urls(
        self, client, mock_sheets_service, sample_image_bytes
    ):
        """Verify that returned image URLs include the api_key parameter."""
        mock_sheets_service.get_item_by_id.return_value = WardrobeItem(
            id="1",
            item="Shirt",
            category="Tops",
            color="Blue",
            fit="Slim",
            season="All",
        )

        respx.get("https://example.com/image.png").mock(
            return_value=httpx.Response(
                200,
                content=sample_image_bytes,
                headers={"content-type": "image/png"},
            )
        )

        response = client.post(
            "/items/1/images/from-urls",
            json={"urls": ["https://example.com/image.png"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["succeeded"] == 1
        # Check that the returned image URL contains api_key
        image_url = data["results"][0]["image"]["url"]
        assert "api_key=" in image_url
