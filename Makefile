.PHONY: build test lint clean run run-dummy stop archive sync backup restore check-db

# Dummy values for commands that don't need real credentials
DUMMY_ENV = API_KEY=dummy GOOGLE_SHEET_ID=dummy GOOGLE_SHEETS_CREDENTIALS_JSON='{}'

# Build all Docker images
build:
	@$(DUMMY_ENV) docker compose build

# Run tests with coverage
test:
	@$(DUMMY_ENV) docker compose run --rm test

# Run flake8 linter
lint:
	@$(DUMMY_ENV) docker compose run --rm lint && echo "✓ Lint passed"

# Run the API server
# Usage: API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{}' make run
run:
	@if [ -z "$(API_KEY)" ]; then \
		echo "Error: API_KEY is not set"; \
		echo "Usage: API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{...}' make run"; \
		exit 1; \
	fi
	@if [ -z "$(GOOGLE_SHEET_ID)" ]; then \
		echo "Error: GOOGLE_SHEET_ID is not set"; \
		echo "Usage: API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{...}' make run"; \
		exit 1; \
	fi
	@if [ -z "$(GOOGLE_SHEETS_CREDENTIALS_JSON)" ]; then \
		echo "Error: GOOGLE_SHEETS_CREDENTIALS_JSON is not set"; \
		echo "Usage: API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{...}' make run"; \
		exit 1; \
	fi
	docker compose up -d wardrobe-api

# Run the API server in dummy mode (in-memory storage, no Google Sheets)
run-dummy:
	@API_KEY=dummy DUMMY_MODE=true docker compose up -d wardrobe-api
	@echo "Running in dummy mode at http://localhost:8000"

# Stop all containers (including test/lint profiles)
stop:
	@$(DUMMY_ENV) docker compose --profile test --profile lint down

# Full cleanup: stop containers, remove volumes and images
clean:
	@$(DUMMY_ENV) docker compose --profile test --profile lint down -v
	@docker images --filter "reference=wardrobe-architect-*" -q | xargs docker rmi 2>/dev/null || true

# Create a tar.gz archive of the project (compatible with Linux/Ubuntu)
# --no-mac-metadata and --no-xattrs prevent macOS extended attributes
# COPYFILE_DISABLE=1 prevents macOS from adding ._* resource fork files
archive:
	@cd .. && COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czvf wardrobe-architect.tar.gz \
		--exclude='__pycache__' \
		--exclude='.DS_Store' \
		--exclude='._*' \
		--exclude='*.pyc' \
		--exclude='.git' \
		--exclude='.claude*' \
		--exclude='htmlcov' \
		--exclude='images/*' \
		--exclude='.pytest_cache' \
		--exclude='.coverage' \
		--exclude='*.egg-info' \
		wardrobe-architect
	@echo "Created ../wardrobe-architect.tar.gz"

# Sync data from Google Sheets to PostgreSQL
sync:
	@$(DUMMY_ENV) docker compose exec wardrobe-api python -m app.cli sync

# Check database connection
check-db:
	@$(DUMMY_ENV) docker compose exec wardrobe-api python -m app.cli check-db

# Backup database and images
backup:
	@./scripts/backup.sh

# Restore from backup
# Usage: make restore FILE=backups/wardrobe-backup-YYYYMMDD-HHMMSS.tar.gz
restore:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backups/wardrobe-backup-YYYYMMDD-HHMMSS.tar.gz"; \
		echo ""; \
		echo "Available backups:"; \
		ls -la backups/*.tar.gz 2>/dev/null || echo "  No backups found"; \
		exit 1; \
	fi
	@./scripts/restore.sh $(FILE)
