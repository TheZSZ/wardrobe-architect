# Wardrobe Architect API

A Python/FastAPI backend for managing wardrobe items, designed to work with a custom ChatGPT GPT via GPT Actions. Uses Google Sheets as a database and local filesystem for image storage.

## Features

- CRUD operations for wardrobe items
- Multiple images per item
- Google Sheets as database (easy to edit manually)
- Filtering by category, color, season
- API key authentication
- OpenAPI spec for GPT Actions integration

## Prerequisites

- Docker and Docker Compose
- Google Cloud service account with Sheets API access
- Your Google Sheet shared with the service account

## Quick Start

```bash
# Build
make build

# Run tests
make test

# Run linter
make lint

# Run the API (with credentials)
API_KEY=your-key \
GOOGLE_SHEET_ID=your-sheet-id \
GOOGLE_SHEETS_CREDENTIALS_JSON='{"type":"service_account",...}' \
make run

# Stop
make stop

# Full cleanup
make clean
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

| Variable | Description |
|----------|-------------|
| `API_KEY` | Your secret API key for authentication |
| `GOOGLE_SHEET_ID` | The ID from your Google Sheet URL |
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | The full JSON content of your service account key |

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

## API Endpoints

### Items
- `GET /items` - List all items (optional filters: `?category=Tops&color=Blue&season=Summer`)
- `GET /items/{id}` - Get item by ID
- `POST /items` - Create new item
- `PUT /items/{id}` - Update item
- `DELETE /items/{id}` - Delete item and its images

### Images
- `POST /items/{id}/images` - Upload image for an item
- `GET /items/{id}/images` - List all images for an item
- `GET /images/{image_id}` - Retrieve image
- `DELETE /images/{image_id}` - Delete image

### Utility
- `GET /health` - Health check (no auth required)
- `GET /openapi.json` - OpenAPI specification

## Authentication

All endpoints (except `/health`) require an `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/items
```

## GPT Actions Setup

1. In ChatGPT, go to your custom GPT settings
2. Add a new Action
3. Import from URL: `https://your-domain.com/openapi.json`
4. Set authentication to "API Key" with header name `X-API-Key`
5. Enter your API key

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

## Project Structure

```
wardrobe-architect/
├── app/
│   ├── main.py           # FastAPI app
│   ├── config.py         # Settings
│   ├── auth.py           # API key auth
│   ├── routers/
│   │   ├── items.py      # Item endpoints
│   │   └── images.py     # Image endpoints
│   ├── services/
│   │   ├── sheets.py     # Google Sheets service
│   │   └── storage.py    # Image storage service
│   └── models/
│       └── item.py       # Pydantic models
├── tests/                # Test suite (70 tests, 89% coverage)
├── images/               # Image storage (mounted volume)
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── requirements.txt
```
