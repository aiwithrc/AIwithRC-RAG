"""Where uploaded files live: DATA_DIR/uploads/{kb_id}/{sha256}. Never under the web root."""

import shutil
from pathlib import Path

from app.config import get_settings


def kb_dir(kb_id: str) -> Path:
    return get_settings().data_dir / "uploads" / kb_id


def upload_path(kb_id: str, sha256: str) -> Path:
    return kb_dir(kb_id) / sha256


def delete_kb_files(kb_id: str) -> None:
    shutil.rmtree(kb_dir(kb_id), ignore_errors=True)


def human_size(n: float) -> str:
    """1234 -> "1 KB", 2_200_000 -> "2.1 MB" (matches the prototype's size column)."""
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit != "MB" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
