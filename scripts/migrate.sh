#!/bin/bash
# Database migration script
# Runs numbered migrations from migrations/ directory
# Tracks applied migrations in schema_migrations table for auditing

set -euo pipefail

echo "=== Database Migration ==="

# Wait for database to be ready
echo "Waiting for database..."
until docker compose exec -T db pg_isready -U wardrobe -d wardrobe > /dev/null 2>&1; do
    sleep 2
done
echo "Database is ready."

# Run base schema first (creates tables including schema_migrations)
echo "Applying base schema (init.sql)..."
docker compose exec -T db psql -U wardrobe -d wardrobe < init.sql > /dev/null 2>&1
echo "✓ Base schema applied"

# Check if migrations directory exists and has files
if [ ! -d "migrations" ] || [ -z "$(ls -A migrations/*.sql 2>/dev/null)" ]; then
    echo "No migrations found in migrations/"
    exit 0
fi

# Process each migration file in order
echo ""
echo "Checking migrations..."
APPLIED=0
SKIPPED=0

for migration in migrations/*.sql; do
    filename=$(basename "$migration")

    # Check if already applied
    already_applied=$(docker compose exec -T db psql -U wardrobe -d wardrobe -t -c \
        "SELECT COUNT(*) FROM schema_migrations WHERE filename = '$filename';" | tr -d ' ')

    if [ "$already_applied" -gt 0 ]; then
        echo "  ⏭  $filename (already applied)"
        ((SKIPPED++))
    else
        echo "  ▶  Applying $filename..."

        # Calculate checksum
        checksum=$(sha256sum "$migration" | cut -d' ' -f1)

        # Apply migration
        if docker compose exec -T db psql -U wardrobe -d wardrobe < "$migration"; then
            # Record in schema_migrations
            docker compose exec -T db psql -U wardrobe -d wardrobe -c \
                "INSERT INTO schema_migrations (filename, checksum) VALUES ('$filename', '$checksum');" > /dev/null
            echo "  ✓  $filename applied"
            ((APPLIED++))
        else
            echo "  ✗  $filename FAILED"
            exit 1
        fi
    fi
done

echo ""
echo "=== Migration Complete ==="
echo "Applied: $APPLIED | Skipped: $SKIPPED"
