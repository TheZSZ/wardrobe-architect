import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_file: str = "/var/log/wardrobe-api.log") -> logging.Logger:
    """Configure logging with file rotation and console output."""

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler (for Docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation (only if path is writable)
    file_handler = None
    try:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB per file
            backupCount=5                # Keep 5 backup files
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        root_logger.info(f"File logging enabled: {log_file}")
    except (PermissionError, OSError) as e:
        root_logger.warning(f"Could not set up file logging to {log_file}: {e}")

    # Configure uvicorn.error logger to write to our file (startup/shutdown messages)
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.handlers.clear()
    uvicorn_error.setLevel(logging.INFO)
    uvicorn_error.propagate = False
    uvicorn_error.addHandler(console_handler)
    if file_handler:
        uvicorn_error.addHandler(file_handler)

    # Disable uvicorn.access logging - we use our own middleware for cleaner logs
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.setLevel(logging.WARNING)  # Only log warnings/errors
    uvicorn_access.propagate = False

    return root_logger
