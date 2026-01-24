from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_key: str
    google_sheets_credentials_json: str = "{}"  # JSON string of service account credentials
    google_sheet_id: str = ""
    images_dir: str = "/app/images"
    host: str = "0.0.0.0"
    port: int = 8000
    dummy_mode: bool = False  # Use in-memory storage instead of Google Sheets
    cors_origins: str = ""  # Comma-separated list of allowed origins (empty = same-origin only)
    max_upload_size_mb: int = 10  # Maximum file upload size in MB


@lru_cache
def get_settings() -> Settings:
    return Settings()
