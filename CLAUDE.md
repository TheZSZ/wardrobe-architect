# Wardrobe Architect - Claude Code Reference

## Project Overview

A FastAPI backend for managing wardrobe items with image storage. Designed for integration with ChatGPT GPT Actions. Uses PostgreSQL for data storage, Google Sheets for optional syncing, and local filesystem for images.

## Quick Commands

```bash
make build          # Build Docker images
make test           # Run tests with coverage (238 tests, 71% coverage)
make lint           # Run flake8 linter
make run-dummy      # Run in dummy mode (starts full stack with nginx)
make stop           # Stop all containers
make clean          # Full cleanup (containers, volumes, images)
```

## Architecture

### Services (Docker Compose)
- **nginx**: Reverse proxy (port 80) - entry point, image caching
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
- `/admin/health` - Live system metrics with charts
- `/admin/db` - Database browser
- `/admin/logs` - Docker container logs
- `/admin/users` - User management
- `/admin/docs` - OpenAPI docs

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
docker compose logs -f wardrobe-api
```

## Notes

- All endpoints except `/health` and `/config` require authentication
- Images require `?api_key=` query param for direct browser access
- File uploads validated by magic bytes (not just content-type)
- Rate limiting enabled via slowapi
- Port 8000 is localhost-only; all external traffic goes through nginx (port 80)
