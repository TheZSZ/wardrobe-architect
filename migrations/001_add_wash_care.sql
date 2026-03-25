-- Migration: 001_add_wash_care
-- Description: Add wash_care JSONB column for laundry instructions
-- Example values:
--   {"tumble": "low", "temperature": "tap cold", "dry_clean": false}
--   {"tumble": "none", "temperature": "warm", "dry_clean": true, "iron": "low"}

-- Add wash_care column to wardrobe_items
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS wash_care JSONB;

-- Index for querying by wash care properties (e.g., find all "dry clean only" items)
CREATE INDEX IF NOT EXISTS idx_items_wash_care ON wardrobe_items USING GIN (wash_care);
