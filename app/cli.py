#!/usr/bin/env python3
"""
CLI commands for wardrobe-architect.

Usage:
    python -m app.cli sync     # Sync from Sheets to DB
    python -m app.cli seed     # Seed sample data (dummy mode only)
"""
import argparse
import logging
import sys

from app.config import get_settings
from app.logging_config import setup_logging
from app.services.database import get_database_service
from app.services.sheets import get_sheets_service

logger = logging.getLogger(__name__)


def sync_command():
    """Sync data from Google Sheets to PostgreSQL."""
    settings = get_settings()

    if settings.dummy_mode:
        print("Error: Sync not available in dummy mode (no Sheets connection)")
        sys.exit(1)

    print("Starting sync from Google Sheets to PostgreSQL...")

    try:
        sheets_service = get_sheets_service(settings)
        count = sheets_service.sync_to_db()
        print(f"Successfully synced {count} items")
    except Exception as e:
        print(f"Error: Sync failed - {e}")
        logger.exception("Sync failed")
        sys.exit(1)


def seed_command():
    """Seed sample data (dummy mode only)."""
    settings = get_settings()

    if not settings.dummy_mode:
        print("Error: Seed only works in dummy mode")
        print("Set DUMMY_MODE=true to use this command")
        sys.exit(1)

    print("Seeding sample data...")

    try:
        sheets_service = get_sheets_service(settings)
        count = sheets_service.seed_sample_data()
        if count > 0:
            print(f"Successfully seeded {count} sample items")
        else:
            print("No items seeded (database already has data)")
    except Exception as e:
        print(f"Error: Seed failed - {e}")
        logger.exception("Seed failed")
        sys.exit(1)


def check_db_command():
    """Check database connection."""
    settings = get_settings()

    print("Checking database connection...")
    db_host = settings.database_url.split('@')[1] if '@' in settings.database_url else 'N/A'
    print(f"Database URL: {db_host}")

    try:
        db = get_database_service(settings)
        if db.is_connected():
            print("Database connection: OK")
            print(f"Items in database: {db.get_item_count()}")
            print(f"Images in database: {db.get_image_count()}")
        else:
            print("Database connection: FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"Database connection: FAILED - {e}")
        sys.exit(1)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Wardrobe Architect CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # sync command
    subparsers.add_parser("sync", help="Sync from Google Sheets to PostgreSQL")

    # seed command
    subparsers.add_parser("seed", help="Seed sample data (dummy mode only)")

    # check-db command
    subparsers.add_parser("check-db", help="Check database connection")

    args = parser.parse_args()

    if args.command == "sync":
        sync_command()
    elif args.command == "seed":
        seed_command()
    elif args.command == "check-db":
        check_db_command()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
