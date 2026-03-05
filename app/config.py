from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_key: str = "dummy"  # Default for dummy mode, should be overridden in production
    google_sheets_credentials_json: str = "{}"  # JSON string of service account credentials
    google_sheet_id: str = ""
    images_dir: str = "/app/images"
    host: str = "0.0.0.0"
    port: int = 8000
    dummy_mode: bool = False  # Use DB but skip Google Sheets (for local dev)
    cors_origins: str = ""  # Comma-separated list of allowed origins (empty = same-origin only)
    max_upload_size_mb: int = 10  # Maximum file upload size in MB

    # Database settings
    database_url: str = "postgresql://wardrobe:wardrobe@db:5432/wardrobe"
    sync_on_startup: bool = False  # Sync from Sheets on app start

    # Logging settings
    log_file: str = "/var/log/wardrobe-api.log"

    # Admin settings
    admin_password: str = ""  # Required for admin panel access

    # OAuth settings
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    # Security
    session_secret_key: str = ""  # For signing session cookies

    # ClamAV virus scanning
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_enabled: bool = True  # Set to False to skip virus scanning

    # Development mode
    dev_mode: bool = False  # If True: short sessions, clear OAuth links on startup


@lru_cache
def get_settings() -> Settings:
    return Settings()
