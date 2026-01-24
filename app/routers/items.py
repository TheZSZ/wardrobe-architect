import re
from fastapi import APIRouter, Body, Depends, HTTPException, status, Query
from typing import Optional
from app.auth import verify_api_key
from app.config import Settings, get_settings
from app.models.item import WardrobeItem, WardrobeItemCreate, WardrobeItemUpdate
from app.services.sheets import SheetsService, MockSheetsService, get_sheets_service
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


@router.put("/{item_id}/rename", response_model=WardrobeItem)
async def rename_item_id(
    item_id: str,
    new_id: str = Body(..., embed=True, description="New ID for the item"),
    sheets: SheetsService = Depends(get_sheets),
    storage: StorageService = Depends(get_storage),
    _: str = Depends(verify_api_key),
):
    """Rename an item's ID, updating both the sheet and image folder."""
    # Validate new_id
    if not new_id or not new_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New ID cannot be empty",
        )

    new_id = new_id.strip()

    # Check for invalid characters in folder names
    if re.search(r'[/\\<>:"|?*]', new_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New ID contains invalid characters (/, \\, <, >, :, \", |, ?, *)",
        )

    # Check if old item exists
    old_item = sheets.get_item_by_id(item_id)
    if old_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with ID '{item_id}' not found",
        )

    # Try to rename in sheets (will fail if new_id already exists)
    renamed = sheets.rename_item_id(item_id, new_id)
    if not renamed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rename: ID '{new_id}' already exists",
        )

    # Rename image folder
    folder_renamed = storage.rename_item_folder(item_id, new_id)
    if not folder_renamed:
        # Rollback the sheet rename
        sheets.rename_item_id(new_id, item_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rename image folder",
        )

    # Return the updated item
    return sheets.get_item_by_id(new_id)


@router.post("/seed", tags=["Utility"])
async def seed_sample_data(
    sheets: SheetsService = Depends(get_sheets),
    _: str = Depends(verify_api_key),
):
    """Seed sample clothing items (dummy mode only)."""
    if not isinstance(sheets, MockSheetsService):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seeding is only available in dummy mode",
        )
    count = sheets.seed_sample_data()
    if count == 0:
        return {"message": "Items already exist, no seeding performed"}
    return {"message": f"Added {count} sample items"}
