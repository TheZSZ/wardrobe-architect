-- Wardrobe Architect Database Schema
-- Uses JSONB for dynamic columns from Google Sheets

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table (core user info, email+passcode auth)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    passcode_hash VARCHAR(128) NOT NULL,
    display_name VARCHAR(100),
    google_sheet_id VARCHAR(255),
    google_sheets_credentials_json TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- OAuth links table (supports multiple providers per user)
CREATE TABLE IF NOT EXISTS oauth_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    provider_email VARCHAR(255),
    linked_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(provider, provider_user_id)
);
CREATE INDEX IF NOT EXISTS idx_oauth_links_user ON oauth_links(user_id);

-- API keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

-- User sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);

-- Main items table with JSONB for flexible schema
CREATE TABLE IF NOT EXISTS wardrobe_items (
    id VARCHAR(255) PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
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
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
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

-- Schema migrations tracking (for auditing)
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT NOW(),
    checksum VARCHAR(64)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_items_category ON wardrobe_items ((data->>'category'));
CREATE INDEX IF NOT EXISTS idx_items_color ON wardrobe_items ((data->>'color'));
CREATE INDEX IF NOT EXISTS idx_items_season ON wardrobe_items ((data->>'season'));
CREATE INDEX IF NOT EXISTS idx_items_user_id ON wardrobe_items (user_id);
CREATE INDEX IF NOT EXISTS idx_items_wash_care ON wardrobe_items USING GIN (wash_care);
CREATE INDEX IF NOT EXISTS idx_images_item_id ON image_metadata (item_id);
CREATE INDEX IF NOT EXISTS idx_images_display_order ON image_metadata (item_id, display_order);
CREATE INDEX IF NOT EXISTS idx_images_user_id ON image_metadata (user_id);

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

-- Create test database for integration tests
-- Note: This runs in the wardrobe database context, so we use a separate connection
-- The test profile in docker-compose will handle test database creation
