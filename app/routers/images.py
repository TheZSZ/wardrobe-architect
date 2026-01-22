from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import FileResponse
from app.auth import verify_api_key
from app.config import Settings, get_settings
from app.models.item import ImageInfo
from app.services.storage import StorageService, get_storage_service
from app.services.sheets import SheetsService, get_sheets_service

router = APIRouter(tags=["Images"])


def get_storage(settings: Settings = Depends(get_settings)) -> StorageService:
    return get_storage_service(settings)


def get_sheets(settings: Settings = Depends(get_settings)) -> SheetsService:
    return get_sheets_service(settings)


def get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


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
    _: str = Depends(verify_api_key),
):
    """Upload an image for a wardrobe item."""
    # Verify the item exists
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    # Validate file type
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )

    base_url = get_base_url(request)
    image_info = await storage.save_image(item_id, file, base_url)
    return image_info


@router.get("/items/{item_id}/images", response_model=list[ImageInfo])
async def list_images_for_item(
    item_id: str,
    request: Request,
    storage: StorageService = Depends(get_storage),
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
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
    return storage.list_images_for_item(item_id, base_url)


@router.get("/images/{image_id}")
async def get_image(
    image_id: str,
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key),
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
