import asyncio
import io
from typing import Optional, Tuple
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Body
from fastapi.responses import FileResponse
from app.auth import verify_api_key, verify_api_key_or_query
from app.config import Settings, get_settings
from app.models.item import (
    ImageInfo, ImageOrderRequest, ImageFromUrlRequest,
    ImageFromUrlsRequest, ImageUploadResult, ImageUploadResults
)
from app.services.storage import StorageService, get_storage_service
from app.services.sheets import SheetsService, get_sheets_service

router = APIRouter(tags=["Images"])

# Image magic bytes for validation
IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpeg',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'RIFF': 'webp',  # WebP starts with RIFF....WEBP
}


def validate_image_content(content: bytes) -> bool:
    """Validate image by checking magic bytes."""
    for signature in IMAGE_SIGNATURES:
        if content.startswith(signature):
            return True
    # Additional check for WebP (RIFF....WEBP format)
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return True
    return False


def get_storage(settings: Settings = Depends(get_settings)) -> StorageService:
    return get_storage_service(settings)


def get_sheets(settings: Settings = Depends(get_settings)) -> SheetsService:
    return get_sheets_service(settings)


def get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


async def download_and_validate_image(
    url: str, max_size: int
) -> Tuple[Optional[bytes], Optional[str], Optional[str], Optional[str]]:
    """
    Download and validate an image from a URL.

    Returns: (content, content_type, filename, error)
    On success: (bytes, str, str, None)
    On failure: (None, None, None, error_message)
    """
    # Validate URL scheme
    if not url.startswith(('http://', 'https://')):
        return None, None, None, "URL must start with http:// or https://"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Check content length if provided
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > max_size:
                return None, None, None, "Image too large"

            content = response.content

            # Check actual size
            if len(content) > max_size:
                return None, None, None, "Image too large"

    except httpx.TimeoutException:
        return None, None, None, "Timeout downloading image"
    except httpx.HTTPStatusError as e:
        return None, None, None, f"HTTP {e.response.status_code}"
    except httpx.RequestError as e:
        return None, None, None, f"Download failed: {str(e)}"

    # Validate content type
    content_type = response.headers.get('content-type', '')
    if not content_type.startswith('image/'):
        return None, None, None, "URL does not point to an image"

    # Validate by magic bytes
    if not validate_image_content(content):
        return None, None, None, "Invalid image format"

    # Extract filename
    url_path = url.split('?')[0]
    filename = url_path.split('/')[-1] or "image.jpg"
    if '.' not in filename:
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        ext = ext_map.get(content_type.split(';')[0], '.jpg')
        filename = f"image{ext}"

    return content, content_type, filename, None


@router.post(
    "/items/{item_id}/images",
    response_model=ImageInfo,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    item_id: str,
    request: Request,
    file: UploadFile = File(..., description="Image file to upload"),
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    settings: Settings = Depends(get_settings),
    api_key: str = Depends(verify_api_key),
):
    """Upload an image for a wardrobe item."""
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    # Validate file type by Content-Type header
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )

    # Read file content for validation
    content = await file.read()

    # Check file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB",
        )

    # Validate by magic bytes (prevents fake content-type)
    if not validate_image_content(content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: PNG, JPEG, GIF, WebP",
        )

    # Reset file position for storage service
    await file.seek(0)

    base_url = get_base_url(request)
    try:
        image_info = await storage.save_image(item_id, file, base_url, api_key=api_key)
    except ValueError as e:
        # Virus detected or other validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return image_info


@router.post(
    "/items/{item_id}/images/from-url",
    response_model=ImageInfo,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image_from_url(
    item_id: str,
    request: Request,
    body: ImageFromUrlRequest,
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    settings: Settings = Depends(get_settings),
    api_key: str = Depends(verify_api_key),
):
    """
    Upload an image from a URL.

    Downloads the image from the provided URL and saves it to the item.
    Useful for ChatGPT Actions which cannot upload files directly.
    """
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    max_size = settings.max_upload_size_mb * 1024 * 1024
    content, content_type, filename, error = await download_and_validate_image(
        body.url, max_size
    )

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error,
        )

    # Create an UploadFile-like object for storage service
    file = UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers={"content-type": content_type},
    )

    base_url = get_base_url(request)
    try:
        image_info = await storage.save_image(item_id, file, base_url, api_key=api_key)
    except ValueError as e:
        # Virus detected or other validation error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return image_info


@router.post(
    "/items/{item_id}/images/from-urls",
    response_model=ImageUploadResults,
    status_code=status.HTTP_200_OK,
)
async def upload_images_from_urls(
    item_id: str,
    request: Request,
    body: ImageFromUrlsRequest,
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    settings: Settings = Depends(get_settings),
    api_key: str = Depends(verify_api_key),
):
    """
    Upload multiple images from URLs in a single request.

    Downloads images from all provided URLs concurrently and saves them.
    Returns results for each URL (success or failure).
    Maximum 10 URLs per request.
    """
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    max_size = settings.max_upload_size_mb * 1024 * 1024
    base_url = get_base_url(request)

    # Download all images concurrently
    download_tasks = [
        download_and_validate_image(url, max_size) for url in body.urls
    ]
    download_results = await asyncio.gather(*download_tasks)

    # Process results and save images
    results = []
    succeeded = 0
    failed = 0

    for url, (content, content_type, filename, error) in zip(
        body.urls, download_results
    ):
        if error:
            results.append(ImageUploadResult(
                url=url,
                success=False,
                error=error,
            ))
            failed += 1
            continue

        # Create UploadFile and save
        file = UploadFile(
            file=io.BytesIO(content),
            filename=filename,
            headers={"content-type": content_type},
        )

        try:
            image_info = await storage.save_image(
                item_id, file, base_url, api_key=api_key
            )
            results.append(ImageUploadResult(
                url=url,
                success=True,
                image=image_info,
            ))
            succeeded += 1
        except ValueError as e:
            results.append(ImageUploadResult(
                url=url,
                success=False,
                error=str(e),
            ))
            failed += 1

    return ImageUploadResults(
        results=results,
        succeeded=succeeded,
        failed=failed,
    )


@router.get("/items/{item_id}/images", response_model=list[ImageInfo])
async def list_images_for_item(
    item_id: str,
    request: Request,
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    api_key: str = Depends(verify_api_key),
):
    """List all images for a wardrobe item."""
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    base_url = get_base_url(request)
    return storage.list_images_for_item(item_id, base_url, api_key=api_key)


@router.get("/images/{image_id}")
async def get_image(
    image_id: str,
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key_or_query),
):
    """Retrieve an image by its ID."""
    result = storage.get_image_path(image_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with ID '{image_id}' not found",
        )

    file_path, _ = result
    return FileResponse(
        path=file_path,
        media_type=f"image/{file_path.suffix.lstrip('.')}",
        filename=file_path.name,
        headers={
            "Cache-Control": "public, max-age=604800",  # 7 days
            "ETag": f'"{image_id}"',
        },
    )


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: str,
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key),
):
    """Delete an image by its ID."""
    deleted = storage.delete_image(image_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with ID '{image_id}' not found",
        )
    return None


@router.put("/items/{item_id}/images/order")
async def reorder_images(
    item_id: str,
    body: ImageOrderRequest,
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """Set the display order of images for an item."""
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    success = storage.reorder_images(item_id, body.image_ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image IDs provided",
        )

    return {"message": "Image order updated"}


@router.put("/images/{image_id}/crop")
async def set_crop_region(
    image_id: str,
    x: float = Body(..., description="X position as percentage (0-100)"),
    y: float = Body(..., description="Y position as percentage (0-100)"),
    size: float = Body(..., description="Size of crop square as percentage (0-100)"),
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key),
):
    """Set the crop region for an image thumbnail."""
    # Find the image to get item_id
    result = storage.get_image_path(image_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with ID '{image_id}' not found",
        )

    _, item_id = result
    success = storage.set_crop_region(item_id, image_id, {"x": x, "y": y, "size": size})
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid crop region. Values must be 0-100 and fit within bounds.",
        )

    return {"message": "Crop region updated"}
