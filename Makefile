.PHONY: build test lint clean run run-dummy stop logs archive sync backup restore check-db migrate

# Dummy values for commands that don't need real credentials
DUMMY_ENV = API_KEY=dummy GOOGLE_SHEET_ID=dummy GOOGLE_SHEETS_CREDENTIALS_JSON='{}'

# Build all Docker images
build:
	@$(DUMMY_ENV) docker compose build

# Run tests with coverage (--user ensures htmlcov is owned by you, not root)
test:
	@mkdir -p htmlcov
	@$(DUMMY_ENV) docker compose run --rm --user $$(id -u):$$(id -g) test

# Run flake8 linter
lint:
	@$(DUMMY_ENV) docker compose run --rm lint && echo "✓ Lint passed"

# Run the API server
# Option 1: Use .env file (docker compose reads it automatically)
# Option 2: Pass env vars: API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{}' make run
run:
	@if [ -z "$(API_KEY)" ] && [ ! -f .env ]; then \
		echo "Error: No .env file found and API_KEY is not set"; \
		echo "Either create a .env file or run:"; \
		echo "  API_KEY=xxx GOOGLE_SHEET_ID=xxx GOOGLE_SHEETS_CREDENTIALS_JSON='{...}' make run"; \
		exit 1; \
	fi
	@docker compose up -d nginx
	@echo "Services started (HTTP:80, HTTPS:443). Following logs..."
	@echo "Ctrl+C to detach, 'make stop' to stop all containers."
	@docker compose logs --tail=50 -f

# Run the API server in dummy mode (in-memory storage, no Google Sheets)
# Starts detached, then follows logs. Ctrl+C stops log viewing (containers keep running).
# Use 'make stop' to stop all containers.
# For HTTPS: edit nginx/server.conf with your domain, then run certbot
run-dummy:
	API_KEY=dummy DUMMY_MODE=true docker compose up -d nginx
	@echo "Services started (HTTP:80, HTTPS:443). Following logs..."
	@echo "Ctrl+C to detach, 'make stop' to stop all containers."
	@docker compose logs --tail=50 -f

# Follow logs from all running containers (for attaching to a screen session)
logs:
	@docker compose logs --tail=50 -f

# Stop all containers (including test/lint profiles)
stop:
	@$(DUMMY_ENV) docker compose --profile test --profile lint down

# Full cleanup: stop containers, remove volumes and images
# WARNING: This deletes ALL data including the database!
clean:
	@echo ""
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@echo "║  WARNING: This will PERMANENTLY DELETE all data including:    ║"
	@echo "║    • PostgreSQL database (all wardrobe items)                 ║"
	@echo "║    • All Docker volumes                                       ║"
	@echo "║    • All wardrobe Docker images                               ║"
	@echo "║                                                               ║"
	@echo "║  This action CANNOT be undone. Run 'make backup' first!       ║"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@read -p "Type 'DELETE' to confirm: " confirm && [ "$$confirm" = "DELETE" ] || (echo "Aborted." && exit 1)
	@read -p "Are you REALLY sure? Type 'YES' to proceed: " confirm2 && [ "$$confirm2" = "YES" ] || (echo "Aborted." && exit 1)
	@echo ""
	@echo "Removing containers and volumes..."
	@$(DUMMY_ENV) docker compose --profile test --profile lint down -v
	@echo "Removing images..."
	@docker images --filter "reference=wardrobe-*" -q | xargs docker rmi 2>/dev/null || true
	@echo ""
	@echo "Clean complete. All data has been deleted."

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

# Run database migrations (safe to run multiple times)
migrate:
	@./scripts/migrate.sh

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
