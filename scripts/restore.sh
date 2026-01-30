#!/bin/bash
#
# Restore script for Wardrobe Architect
# Restores database and images from backup archive
#
# Usage: ./scripts/restore.sh backups/wardrobe-backup-YYYYMMDD-HHMMSS.tar.gz
#

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -la backups/*.tar.gz 2>/dev/null || echo "  No backups found in ./backups/"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Restoring from: $BACKUP_FILE"
echo ""

# Create temp directory for extraction
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Extract archive
echo "Extracting archive..."
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Find the backup directory (first directory in temp)
BACKUP_DIR=$(find "$TEMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)

if [ -z "$BACKUP_DIR" ]; then
    echo "Error: Invalid backup archive (no directory found)"
    exit 1
fi

echo "  Found backup: $(basename "$BACKUP_DIR")"

# Check manifest
if [ -f "$BACKUP_DIR/manifest.json" ]; then
    echo "  Manifest:"
    cat "$BACKUP_DIR/manifest.json" | sed 's/^/    /'
fi

echo ""

# Confirm before proceeding
read -p "This will overwrite existing data. Continue? (y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Restore database
if [ -f "$BACKUP_DIR/db_dump.sql" ]; then
    echo "Restoring database..."
    # Drop and recreate tables
    docker compose exec -T db psql -U wardrobe wardrobe -c "DROP TABLE IF EXISTS image_metadata CASCADE; DROP TABLE IF EXISTS wardrobe_items CASCADE; DROP TABLE IF EXISTS sync_log CASCADE;"
    # Restore from dump
    docker compose exec -T db psql -U wardrobe wardrobe < "$BACKUP_DIR/db_dump.sql"
    echo "  Database restored"
else
    echo "Warning: No database dump found in backup"
fi

# Restore images
if [ -d "$BACKUP_DIR/images" ]; then
    echo "Restoring images..."
    # Remove existing images
    rm -rf images/*
    # Copy from backup
    cp -r "$BACKUP_DIR/images/"* images/ 2>/dev/null || true
    IMAGE_COUNT=$(find images -type f 2>/dev/null | wc -l)
    echo "  Restored $IMAGE_COUNT image files"
else
    echo "Warning: No images directory found in backup"
fi

echo ""
echo "Restore complete!"
echo "Restart the API to apply changes: docker compose restart wardrobe-api"
