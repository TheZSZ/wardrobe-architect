from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional
from app.auth import verify_api_key
from app.config import Settings, get_settings
from app.models.item import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate
from app.services.sheets import SheetsService, get_sheets_service
from app.services.storage import StorageService, get_storage_service

router = APIRouter(prefix="/items", tags=["Items"])


def get_sheets(settings: Settings = Depends(get_settings)) -> SheetsService:
    return get_sheets_service(settings)


def get_storage(settings: Settings = Depends(get_settings)) -> StorageService:
    return get_storage_service(settings)


@router.get("", response_model=list[WardrobeItem])
async def list_items(
    category: Optional[str] = Query(None, description="Filter by category"),
    color: Optional[str] = Query(None, description="Filter by color"),
    season: Optional[str] = Query(None, description="Filter by season"),
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """List all wardrobe items with optional filters."""
    return sheets.get_all_items(category=category, color=color, season=season)


@router.get("/{item_id}", response_model=WardrobeItem)
async def get_item(
    item_id: str,
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """Get a specific wardrobe item by ID."""
    item = sheets.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )
    return item


@router.post("", response_model=WardrobeItem, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: WardrobeItemCreate,
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """Create a new wardrobe item."""
    return sheets.create_item(item_data)


@router.put("/{item_id}", response_model=WardrobeItem)
async def update_item(
    item_id: str,
    item_data: WardrobeItemUpdate,
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """Update an existing wardrobe item."""
    item = sheets.update_item(item_id, item_data)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    sheets: SheetsService = Depends(get_sheets),
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key),
):
    """Delete a wardrobe item and its associated images."""
    deleted = sheets.delete_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    # Also delete associated images
    storage.delete_all_images_for_item(item_id)
    return None
