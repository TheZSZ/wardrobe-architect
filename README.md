# Wardrobe Architect API

A Python/FastAPI backend for managing wardrobe items, designed to work with a custom ChatGPT GPT via GPT Actions. Uses Google Sheets as a database and local filesystem for image storage.

## Features

- CRUD operations for wardrobe items
- Multiple images per item with drag-and-drop reordering
- Custom thumbnail cropping per image
- Google Sheets as database (easy to edit manually)
- Filtering by category, color, season
- API key authentication with timing-attack protection
- Rate limiting to prevent abuse
- File upload validation (size limits, magic byte verification)
- Web UI for managing items and images
- Dummy mode for testing without Google Sheets
- OpenAPI spec for GPT Actions integration

## Prerequisites

- Docker and Docker Compose
- Google Cloud service account with Sheets API access (for production)
- Your Google Sheet shared with the service account

## Quick Start

```bash
# Build
make build

# Run tests
make test

# Run linter
make lint

# Run in dummy mode (no Google Sheets needed, in-memory storage)
make run-dummy
# Access at http://localhost:8000

# Run with real Google Sheets
API_KEY=your-key \
GOOGLE_SHEET_ID=your-sheet-id \
GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account",...}' \
make run

# Stop
make stop

# Full cleanup (removes containers, volumes, images)
make clean

# Create portable archive for deployment
make archive
```

## Setup

### 1. Google Cloud Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Sheets API
4. Go to "IAM & Admin" > "Service Accounts"
5. Create a new service account
6. Create a JSON key and download it
7. You'll pass the contents of this JSON as an environment variable

### 2. Google Sheet Setup

1. Open your existing Google Sheet (or create a new one)
2. Ensure the first row has headers: `ID`, `Item`, `Category`, `Color`, `Fit`, `Season`, `Notes`
3. Share the sheet with your service account email (found in the JSON file, looks like `xxx@xxx.iam.gserviceaccount.com`)
4. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit`

### 3. Environment Variables

All credentials are passed as environment variables (no files stored in repo):

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Your secret API key for authentication | *required* |
| `GOOGLE_SHEET_ID` | The ID from your Google Sheet URL | *required for production* |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | The full JSON content of your service account key | `{}` |
| `DUMMY_MODE` | Use in-memory storage instead of Google Sheets | `false` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins | `` (same-origin only) |
| `MAX_UPLOAD_SIZE_MB` | Maximum file upload size in MB | `10` |
| `IMAGES_DIR` | Directory for storing images | `/app/images` |
| `HOST` | Host to bind to | `0.0.0.0` |
| `PORT` | Port to bind to | `8000` |

Generate a secure API key:
```bash
openssl rand -hex 32
```

### 4. Run with Docker

```bash
API_KEY=your-key \
GOOGLE_SHEET_ID=your-sheet-id \
GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account","project_id":"..."}' \
make run
```

The API will be available at `http://localhost:8000`

## Web UI

The application includes a web interface for managing your wardrobe:

- **Login page**: `http://localhost:8000/` - Enter your API key
- **Wardrobe page**: `http://localhost:8000/wardrobe` - View, add, edit, and delete items
- **Coverage report**: `http://localhost:8000/coverage` - View test coverage (after running `make test`)

### Web UI Features

- View all items in a responsive grid
- Filter by category, color, or season
- Add new items with the "Add Item" button
- Edit item details (name, category, color, fit, season, notes)
- Rename item IDs (useful for fixing inconsistent IDs from ChatGPT)
- Upload multiple images per item
- Click on item images to manage them:
  - Drag and drop to reorder
  - Delete individual images
  - Adjust thumbnail crop region
- Items are sorted by the numeric portion of their ID

## API Endpoints

### Items
- `GET /items` - List all items (optional filters: `?category=Tops&color=Blue&season=Summer`)
- `GET /items/{id}` - Get item by ID
- `POST /items` - Create new item
- `PUT /items/{id}` - Update item
- `PUT /items/{id}/rename` - Rename item ID (also renames image folder)
- `DELETE /items/{id}` - Delete item and its images

### Images
- `POST /items/{id}/images` - Upload image for an item
- `GET /items/{id}/images` - List all images for an item
- `PUT /items/{id}/images/order` - Reorder images
- `GET /images/{image_id}` - Retrieve image (supports `?api_key=` query param)
- `PUT /images/{image_id}/crop` - Set thumbnail crop region
- `DELETE /images/{image_id}` - Delete image

### Utility
- `GET /health` - Health check (no auth required)
- `GET /config` - Get public config like dummy_mode (no auth required)
- `GET /openapi.json` - OpenAPI specification
- `POST /items/seed` - Load sample data (dummy mode only)

## Authentication

All endpoints (except `/health`, `/config`, and web pages) require an `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/items
```

For image retrieval in browsers, you can also use a query parameter:
```
http://localhost:8000/images/{image_id}?api_key=your-api-key
```

## Security Features

- **Rate limiting**: Prevents brute force and DoS attacks
- **Timing-attack safe auth**: Uses constant-time comparison for API keys
- **File upload validation**:
  - Size limit (configurable, default 10MB)
  - Magic byte verification (only real PNG, JPEG, GIF, WebP accepted)
- **Path traversal protection**: Item IDs are sanitized to prevent directory escape
- **CORS configuration**: Restrictive by default, configurable for specific origins

## GPT Actions Setup

1. In ChatGPT, go to your custom GPT settings
2. Add a new Action
3. Import from URL: `https://your-domain.com/openapi.json`
4. Set authentication to "API Key" with header name `X-API-Key`
5. Enter your API key
6. For CORS, set `CORS_ORIGINS=https://chat.openai.com` in your environment

## Exposing to Internet (for GPT Actions)

Since you're self-hosting on Ubuntu with port forwarding + DDNS:

1. **Port Forward**: Configure your router to forward port 443 to your Ubuntu machine's port 8000
2. **DDNS**: Set up a DDNS service (DuckDNS, No-IP, etc.) to handle dynamic IP
3. **SSL/HTTPS**: Use a reverse proxy (nginx or Caddy) with Let's Encrypt for HTTPS

Example Caddy configuration:
```
your-domain.duckdns.org {
    reverse_proxy localhost:8000
}
```

## Deployment to Ubuntu

1. Create the archive on your Mac:
   ```bash
   make archive
   ```

2. Copy to your Ubuntu server:
   ```bash
   scp ../wardrobe-architect.tar.gz user@your-server:~
   ```

3. On Ubuntu, extract and run:
   ```bash
   tar -xzvf wardrobe-architect.tar.gz
   cd wardrobe-architect
   make build

   # Run in dummy mode for testing
   make run-dummy

   # Or run with real credentials
   API_KEY=your-key \
   GOOGLE_SHEET_ID=your-sheet-id \
   GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account",...}' \
   make run
   ```

## Development

### Running Tests

```bash
make test
```

Tests run with coverage reporting. View the HTML report at `http://localhost:8000/coverage` after starting the server, or open `htmlcov/index.html` directly.

### Running Linter

```bash
make lint
```

### Project Structure

```
wardrobe-architect/
├── app/
│   ├── main.py           # FastAPI app with rate limiting, CORS
│   ├── config.py         # Settings from environment
│   ├── auth.py           # API key auth with timing protection
│   ├── routers/
│   │   ├── items.py      # Item CRUD + rename endpoints
│   │   ├── images.py     # Image upload, crop, reorder endpoints
│   │   └── web.py        # HTML page serving
│   ├── services/
│   │   ├── sheets.py     # Google Sheets + Mock service
│   │   └── storage.py    # Image storage with path sanitization
│   ├── models/
│   │   └── item.py       # Pydantic models
│   └── templates/
│       ├── login.html    # Login page
│       └── wardrobe.html # Main wardrobe UI
├── tests/                # 91 tests, 78% coverage
├── images/               # Image storage (mounted volume)
├── htmlcov/              # Coverage report (generated)
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── pytest.ini
└── README.md
```

## Troubleshooting

### "Invalid API key" error
- Ensure the `X-API-Key` header matches your `API_KEY` environment variable exactly
- Check for trailing whitespace or newlines

### Images not loading in browser
- Images require authentication. The web UI passes `?api_key=` automatically
- If accessing directly, append `?api_key=your-key` to the image URL

### Google Sheets connection fails
- Verify the service account email has access to the sheet
- Check that `GOOGLE_SHEETS_CREDENTIALS_JSON` is valid JSON
- Ensure the Google Sheets API is enabled in your GCP project

### CORS errors with GPT Actions
- Set `CORS_ORIGINS=https://chat.openai.com` in your environment
- Restart the container after changing environment variables

### File upload fails
- Check file size (default limit: 10MB)
- Ensure the file is a real image (PNG, JPEG, GIF, or WebP)
- Fake content-types are rejected via magic byte validation
