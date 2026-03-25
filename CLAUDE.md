# Wardrobe Architect - Claude Code Reference

## Project Overview

A FastAPI backend for managing wardrobe items with image storage. Designed for integration with ChatGPT GPT Actions. Uses PostgreSQL for data storage, Google Sheets for optional syncing, and local filesystem for images.

## Quick Commands

```bash
make build          # Build Docker images
make test           # Run tests with coverage (250 tests, 71% coverage)
make lint           # Run flake8 linter
make run-dummy      # Run in dummy mode (HTTP:80, HTTPS:443)
make stop           # Stop all containers (data persists)
make clean          # Full cleanup (containers, volumes, images) - DATA LOSS
make logs           # Follow logs from all containers
make migrate        # Run database schema migrations
```

## Architecture

### Services (Docker Compose)
- **nginx**: Reverse proxy (ports 80+443) - HTTP/HTTPS, image caching
- **wardrobe-api**: FastAPI application (port 8000, localhost only)
- **db**: PostgreSQL 16 (port 5433)
- **clamav**: Virus scanning for uploads

### Code Structure
```
app/
├── main.py              # FastAPI app, middleware, health endpoint
├── config.py            # Pydantic settings from environment
├── auth.py              # API key authentication (timing-safe)
├── logging_config.py    # Logging setup with rotation
├── routers/
│   ├── admin.py         # Admin dashboard, user management, logs
│   ├── auth.py          # OAuth, session management
│   ├── items.py         # Item CRUD endpoints
│   ├── images.py        # Image upload, crop, reorder
│   └── web.py           # HTML page serving
├── services/
│   ├── database.py      # PostgreSQL operations
│   ├── sheets.py        # Google Sheets sync
│   ├── storage.py       # Image filesystem operations
│   ├── user_service.py  # User/API key management
│   ├── auth_service.py  # Session handling
│   └── clamav_service.py # Virus scanning
├── models/
│   ├── item.py          # Item, ImageInfo models
│   └── user.py          # User, APIKey models
└── templates/           # Jinja2 HTML templates
```

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | App entry, middleware, `/health` endpoint |
| `app/config.py` | All environment variables |
| `app/routers/admin.py` | Admin panel routes |
| `docker-compose.yml` | All service definitions |
| `Makefile` | Build/test/run commands |
| `init.sql` | Database schema |

## Environment Variables

Essential:
- `API_KEY` - API authentication key
- `ADMIN_PASSWORD` - Admin panel password
- `DATABASE_URL` - PostgreSQL connection string

Optional:
- `DUMMY_MODE=true` - Skip Google Sheets, use DB only
- `DEV_MODE=true` - Short sessions, clear OAuth on startup
- `CLAMAV_ENABLED=false` - Disable virus scanning
- `SYNC_ON_STARTUP=true` - Sync from Sheets on start

## Testing

```bash
make test                    # Run all 238 tests with coverage
docker compose logs test     # View test output
```

Tests run in a separate `test-db` container. Coverage report generated in `htmlcov/`.

### Test Structure
```
tests/
├── conftest.py              # Shared fixtures, test client setup
├── test_auth.py             # API key and session authentication
├── test_auth_service.py     # Passcode hashing, token generation
├── test_user_service.py     # User CRUD, sessions, API keys, OAuth
├── test_admin.py            # Admin panel routes
├── test_items_router.py     # Item CRUD endpoints
├── test_images_router.py    # Image upload/management
├── test_integration.py      # Database integration tests
├── test_storage.py          # Image storage operations
├── test_sheets.py           # Google Sheets sync
└── test_models.py           # Pydantic model validation
```

### Coverage by Area
- **auth_service.py**: 100% - Passcode hashing, API key generation
- **user_service.py**: 98% - User management, sessions, OAuth
- **auth.py**: 73% - Request authentication middleware
- **admin.py**: 53% - Admin dashboard routes
- **database.py**: 76% - PostgreSQL operations

## Admin Panel

Access at `/admin` (requires `ADMIN_PASSWORD`):
- Dashboard: Stats, sync status, recent logs
- `/admin/health` - Live system metrics with charts (includes container stats)
- `/admin/db` - Database browser
- `/admin/logs` - Docker container logs and nginx logs
- `/admin/users` - User management
- `/admin/docs` - OpenAPI docs

## ChatGPT GPT Actions

ChatGPT GPT Actions has a 30-action limit. Use the filtered OpenAPI spec (requires admin auth):

```
GET /admin/openapi-chatgpt.json
```

This returns only the 12 core API actions needed for ChatGPT:
- **Items**: GET/POST /items, GET/PUT/DELETE /items/{id}
- **Images**: POST/GET /items/{id}/images, GET/DELETE /images/{id}, PUT order/crop
- **Utility**: GET /health

The full OpenAPI spec (`/openapi.json`) includes all 49 endpoints including admin panel and OAuth routes.

## Request Logging

Custom middleware logs requests as JSON:
```json
{"method": "GET", "path": "/items", "status": 200, "duration_ms": 1.84}
```
- Sensitive params (api_key, token, password) are redacted
- `/health` and `/favicon.ico` are not logged

## Image Storage

- Images stored in `/app/images/{user_id}/{item_id}/`
- Metadata in PostgreSQL `image_metadata` table
- Virus scanning via ClamAV before save
- Crop regions stored per-image

## Nginx Caching

Images are cached by nginx for 7 days:
- Cache stored in `/var/cache/nginx/images` (Docker volume)
- Cache key ignores `api_key` query param (shared cache across users)
- Cache locking prevents stampedes (concurrent requests wait for first)
- Errors (401/403/404) are never cached
- Check `X-Cache-Status` header: MISS (first request) → HIT (cached)

## SSL/HTTPS Setup

Nginx listens on both port 80 (HTTP) and 443 (HTTPS). To enable HTTPS:

**1. Set your domain in `nginx/server.conf`:**
```
SERVER_NAME=wardrobe.example.com
```

**2. Get Let's Encrypt certificate:**
```bash
# Stop nginx first if running
make stop

# Get certificate
sudo certbot certonly --standalone -d wardrobe.example.com
```

**3. Start nginx:**
```bash
make run-dummy   # HTTP works immediately, HTTPS after certs exist
```

**Files:**
| File | Purpose |
|------|---------|
| `nginx/server.conf` | Domain name (SERVER_NAME=) |
| `nginx/nginx.conf.template` | Nginx config template |
| `/etc/letsencrypt/live/{domain}/` | Let's Encrypt certificates |

**Certificate renewal:**
```bash
sudo certbot renew
docker compose restart nginx
```

## Common Tasks

### Add a new endpoint
1. Create route in appropriate router (`app/routers/`)
2. Add any models to `app/models/`
3. Add tests in `tests/`
4. Run `make test` and `make lint`

### Add environment variable
1. Add to `app/config.py` in `Settings` class
2. Add to `docker-compose.yml` environment section
3. Document in README.md

### Debug database issues
```bash
docker compose exec wardrobe-db psql -U wardrobe -d wardrobe
```

### View live logs
```bash
make logs                           # All containers
docker compose logs -f wardrobe-api # Just the API
```

### Database Migrations

Migrations are numbered SQL files in `migrations/` that are tracked in the `schema_migrations` table for auditing.

**Run migrations:**
```bash
make migrate
```

**Output:**
```
=== Database Migration ===
Applying base schema (init.sql)...
✓ Base schema applied

Checking migrations...
  ⏭  001_add_wash_care.sql (already applied)
  ▶  Applying 002_add_tags.sql...
  ✓  002_add_tags.sql applied

=== Migration Complete ===
Applied: 1 | Skipped: 1
```

**Creating a new migration:**
1. Create file: `migrations/NNN_description.sql` (e.g., `002_add_tags.sql`)
2. Use `IF NOT EXISTS` for safety
3. Run `make migrate`

**Example migration file:**
```sql
-- Migration: 002_add_tags
-- Description: Add tags array column

ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS tags TEXT[];
CREATE INDEX IF NOT EXISTS idx_items_tags ON wardrobe_items USING GIN (tags);
```

**View migration history:**
```bash
docker compose exec db psql -U wardrobe -d wardrobe -c "SELECT * FROM schema_migrations;"
```

**Data persistence:**
- `make stop` - stops containers, data persists in Docker volumes
- `make clean` - removes volumes, **DATA LOSS**
- Database volume: `wardrobe-db` (persists across restarts)

## Notes

- All endpoints except `/health` and `/config` require authentication
- Images require `?api_key=` query param for direct browser access
- File uploads validated by magic bytes (not just content-type)
- Rate limiting enabled via slowapi
- Port 8000 is localhost-only; all external traffic goes through nginx (port 80)
