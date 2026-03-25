from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class WashCare(BaseModel):
    """Laundry care settings to group compatible items. Use the user's specific washer/dryer settings. Ask the user what temperature settings their washer has if unknown."""
    wash_temp: Optional[str] = Field(None, description="Wash temperature setting from user's washer. Common options: 'tap cold', 'cold', 'warm', 'warm hot', 'hot'. Use exact setting names from user's machine.")
    dry_method: Optional[str] = Field(None, description="Drying method. Examples: 'tumble low', 'tumble medium', 'tumble high', 'hang dry', 'lay flat', 'dry clean only'")
    color_group: Optional[str] = Field(None, description="Color grouping for sorting laundry. Examples: 'whites', 'lights', 'darks', 'colors', 'brights', 'delicates'")
    delicate: Optional[bool] = Field(None, description="True if item requires gentle/delicate cycle")
    separate: Optional[bool] = Field(None, description="True if item must be washed alone (e.g., new dark jeans that bleed dye)")
    notes: Optional[str] = Field(None, description="Specific care instructions (e.g., 'Use delicate cycle', 'Inside out', 'Mesh bag')")


class WardrobeItemBase(BaseModel):
    item: str = Field(..., description="Name/description of the clothing item")
    category: str = Field(..., description="Category (e.g., Tops, Bottoms, Outerwear)")
    color: str = Field(..., description="Primary color of the item")
    fit: str = Field(..., description="Fit style (e.g., Slim, Regular, Relaxed)")
    season: str = Field(..., description="Seasonal appropriateness (e.g., All, Summer, Winter)")
    notes: Optional[str] = Field(None, description="Additional notes about the item")
    wash_care: Optional[WashCare] = Field(None, description="Laundry settings to group items that can be washed together. Set based on garment care labels and user's washer settings.")


class WardrobeItemCreate(WardrobeItemBase):
    pass


class WardrobeItemUpdate(BaseModel):
    item: Optional[str] = Field(None, description="Name/description of the clothing item")
    category: Optional[str] = Field(None, description="Category")
    color: Optional[str] = Field(None, description="Primary color")
    fit: Optional[str] = Field(None, description="Fit style")
    season: Optional[str] = Field(None, description="Seasonal appropriateness")
    notes: Optional[str] = Field(None, description="Additional notes")
    wash_care: Optional[WashCare] = Field(None, description="Laundry settings. Set to null to clear existing wash care.")


class WardrobeItem(WardrobeItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique identifier for the item")


class CropRegion(BaseModel):
    x: float = Field(..., description="X position as percentage (0-100)")
    y: float = Field(..., description="Y position as percentage (0-100)")
    size: float = Field(..., description="Size of square crop as percentage (0-100)")


class ImageInfo(BaseModel):
    image_id: str = Field(..., description="Unique identifier for the image")
    item_id: str = Field(..., description="ID of the wardrobe item this image belongs to")
    filename: str = Field(..., description="Original filename")
    url: str = Field(..., description="URL to retrieve the image")
    crop_region: Optional[CropRegion] = Field(None, description="Crop region for square thumbnail")
