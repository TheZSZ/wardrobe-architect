#!/bin/bash
#
# Backup script for Wardrobe Architect
# Creates a tar.gz archive with database dump, images, and manifest
#
# Usage: ./scripts/backup.sh
#

set -e

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="backups/wardrobe-backup-$TIMESTAMP"

echo "Creating backup: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Dump database
echo "Dumping database..."
docker compose exec -T db pg_dump -U wardrobe wardrobe > "$BACKUP_DIR/db_dump.sql"
echo "  Database dump complete: $(wc -l < "$BACKUP_DIR/db_dump.sql") lines"

# Copy images
echo "Copying images..."
if [ -d "images" ]; then
    cp -r images "$BACKUP_DIR/images"
    IMAGE_COUNT=$(find "$BACKUP_DIR/images" -type f | wc -l)
    echo "  Copied $IMAGE_COUNT image files"
else
    mkdir -p "$BACKUP_DIR/images"
    echo "  No images directory found (empty backup)"
fi

# Create manifest
echo "Creating manifest..."
cat > "$BACKUP_DIR/manifest.json" << EOF
{
    "timestamp": "$TIMESTAMP",
    "version": "1.0",
    "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

# Create archive
echo "Creating archive..."
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czvf "$BACKUP_DIR.tar.gz" -C backups "wardrobe-backup-$TIMESTAMP"

# Remove temp directory
rm -rf "$BACKUP_DIR"

# Show result
BACKUP_SIZE=$(ls -lh "$BACKUP_DIR.tar.gz" | awk '{print $5}')
echo ""
echo "Backup complete!"
echo "  File: $BACKUP_DIR.tar.gz"
echo "  Size: $BACKUP_SIZE"
