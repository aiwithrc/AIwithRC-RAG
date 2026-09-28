"""Run Alembic migrations programmatically (on startup, from the CLI and in tests)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

API_DIR = Path(__file__).resolve().parent.parent


def alembic_config(db_url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def upgrade_to_head(db_url: str) -> None:
    command.upgrade(alembic_config(db_url), "head")
