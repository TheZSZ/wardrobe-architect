from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class WardrobeItemBase(BaseModel):
    item: str = Field(..., description="Name/description of the clothing item")
    category: str = Field(..., description="Category (e.g., Tops, Bottoms, Outerwear)")
    color: str = Field(..., description="Primary color of the item")
    fit: str = Field(..., description="Fit style (e.g., Slim, Regular, Relaxed)")
    season: str = Field(..., description="Seasonal appropriateness (e.g., All, Summer, Winter)")
    notes: Optional[str] = Field(None, description="Additional notes about the item")


class WardrobeItemCreate(WardrobeItemBase):
    pass


class WardrobeItemUpdate(BaseModel):
    item: Optional[str] = Field(None, description="Name/description of the clothing item")
    category: Optional[str] = Field(None, description="Category")
    color: Optional[str] = Field(None, description="Primary color")
    fit: Optional[str] = Field(None, description="Fit style")
    season: Optional[str] = Field(None, description="Seasonal appropriateness")
    notes: Optional[str] = Field(None, description="Additional notes")


class WardrobeItem(WardrobeItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique identifier for the item")


class ImageInfo(BaseModel):
    image_id: str = Field(..., description="Unique identifier for the image")
    item_id: str = Field(..., description="ID of the wardrobe item this image belongs to")
    filename: str = Field(..., description="Original filename")
    url: str = Field(..., description="URL to retrieve the image")
