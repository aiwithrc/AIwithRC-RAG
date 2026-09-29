"""Model "Auto": the first available chat model matching the preference list."""

from fnmatch import fnmatch

from app.config import get_settings
from app.providers.base import is_chat_model


def _names(model_id: str) -> tuple[str, str]:
    m = model_id.lower()
    return m, m.rsplit("/", 1)[-1]  # "qwen/qwen3.5-9b" also matches "qwen3.5*"


def pick_auto(models: list[str], preference: list[str] | None = None) -> str | None:
    chat = [m for m in models if is_chat_model(m)]
    for pattern in preference if preference is not None else get_settings().auto_models:
        p = pattern.lower()
        for m in chat:
            if any(fnmatch(n, p) for n in _names(m)):
                return m
    return chat[0] if chat else (models[0] if models else None)


def resolve_model(selected: str, models: list[str]) -> str | None:
    """The model a connection actually answers with."""
    if selected and selected != "auto":
        return selected
    return pick_auto(models)
