"""Application configuration, read from environment variables (and `.env`)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_secret: str = "change-me-in-production"
    data_dir: Path = Path("./data")
    database_url: str = ""  # defaults to sqlite in data_dir
    allow_signup: bool = False
    public_url: str = "http://localhost:8000"
    project_url: str = "https://github.com/aiwithrc/aiwithrc-rag"
    auto_model_preference: str = "claude-sonnet*,gpt-4.1*,qwen3.5*,qwen2.5*,llama3.1*,gemma*"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    max_upload_mb: int = 50
    session_days: int = 30
    cookie_secure: bool = False
    web_dist: Path = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
    # Where fastembed models are cached. Defaults to DATA_DIR/models; the Docker image bakes the
    # default model into /app/models so the first upload doesn't wait for a download.
    model_cache_dir: Path | None = None
    # The background job worker. Tests turn it off and drive jobs by hand.
    start_worker: bool = True

    @field_validator("public_url", "project_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def public_host(self) -> str:
        return self.public_url.split("://", 1)[-1]

    @property
    def auto_models(self) -> list[str]:
        return [p.strip() for p in self.auto_model_preference.split(",") if p.strip()]

    @property
    def models_dir(self) -> Path:
        return self.model_cache_dir or (self.data_dir / "models")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for sub in ("", "uploads", "chroma", "models"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
