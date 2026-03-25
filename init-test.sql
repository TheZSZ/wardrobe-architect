-- Create test database
SELECT 'CREATE DATABASE wardrobe_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wardrobe_test')\gexec

-- Connect to test database and create schema
\c wardrobe_test

-- Main items table with JSONB for flexible schema
CREATE TABLE IF NOT EXISTS wardrobe_items (
    id VARCHAR(255) PRIMARY KEY,
    data JSONB NOT NULL,
    synced_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    wash_care JSONB
);

-- Image metadata table
CREATE TABLE IF NOT EXISTS image_metadata (
    image_id VARCHAR(255) PRIMARY KEY,
    item_id VARCHAR(255) NOT NULL,
    filename VARCHAR(255),
    crop_region JSONB,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_item
        FOREIGN KEY (item_id)
        REFERENCES wardrobe_items(id)
        ON DELETE CASCADE
);

-- Sync log for tracking sync history
CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    synced_at TIMESTAMP DEFAULT NOW(),
    items_synced INTEGER,
    source VARCHAR(50),
    status VARCHAR(20) DEFAULT 'success',
    error_message TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_items_category ON wardrobe_items ((data->>'category'));
CREATE INDEX IF NOT EXISTS idx_items_color ON wardrobe_items ((data->>'color'));
CREATE INDEX IF NOT EXISTS idx_items_season ON wardrobe_items ((data->>'season'));
CREATE INDEX IF NOT EXISTS idx_items_wash_care ON wardrobe_items USING GIN (wash_care);
CREATE INDEX IF NOT EXISTS idx_images_item_id ON image_metadata (item_id);
CREATE INDEX IF NOT EXISTS idx_images_display_order ON image_metadata (item_id, display_order);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS update_wardrobe_items_updated_at ON wardrobe_items;
CREATE TRIGGER update_wardrobe_items_updated_at
    BEFORE UPDATE ON wardrobe_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
