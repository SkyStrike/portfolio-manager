"""
core/migrations.py

Programmatic Alembic migration runner.

Called at application startup (before init_db) to apply any pending
schema migrations. Handles the first-deploy scenario where an existing
production database has no alembic_version table.
"""
import logging
import os
import sqlite3

from alembic.config import Config
from alembic import command

logger = logging.getLogger(__name__)


# The revision that represents the full current schema as it exists
# in production databases that predate Alembic tracking.
BASELINE_REVISION = '001'


def _get_alembic_config() -> Config:
    """Build an Alembic Config object pointing to the project alembic.ini."""
    # Resolve path to alembic.ini relative to this file's location
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(project_root, 'alembic.ini')

    cfg = Config(ini_path)

    # Override DB URL from environment variable (same as core/database.py)
    db_file = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")

    return cfg


def _is_alembic_tracked(db_file: str) -> bool:
    """Check whether the database already has an alembic_version table."""
    if not os.path.exists(db_file):
        return False  # Fresh database — will be created and tracked normally
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception:
        return False


def run_migrations() -> None:
    """
    Apply all pending Alembic migrations to the configured SQLite database.

    First-deploy strategy for existing untracked production databases:
      1. Detect that alembic_version table is missing.
      2. Stamp the database at the baseline revision (001) — inserts the
         alembic_version row WITHOUT running any SQL migrations.
      3. Call upgrade head — no-op since we're already at head.

    For fresh databases (first ever run):
      - upgrade head runs all migrations from 001 onward, creating tables.

    For subsequent deploys with new migrations (002, 003, ...):
      - upgrade head runs only the new unapplied migrations.
    """
    db_file = os.getenv("PORTFOLIO_DB_FILE", "data/portfolio.db")
    cfg = _get_alembic_config()

    try:
        if not _is_alembic_tracked(db_file):
            if os.path.exists(db_file):
                # Production database exists but was never tracked by Alembic.
                # Stamp it at the baseline revision so that future migrations
                # apply cleanly without re-running the schema creation.
                logger.info("Untracked database detected at %s.", db_file)
                logger.info("Stamping at Alembic baseline revision '%s'...", BASELINE_REVISION)
                command.stamp(cfg, BASELINE_REVISION)
                logger.info("Database stamped successfully. No schema changes were made.")
            # If the DB doesn't exist yet, upgrade head will create it from scratch.

        # Apply any pending migrations (no-op if already at head)
        logger.info("Running Alembic migrations...")
        command.upgrade(cfg, "head")
        logger.info("Database migrations are up to date.")

    except Exception as e:
        logger.error("Error running database migrations: %s", e)
        raise
