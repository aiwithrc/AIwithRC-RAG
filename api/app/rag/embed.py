"""Text embeddings. Default: fastembed (ONNX on CPU), so documents are embedded on this server.

Ollama and OpenAI-compatible embedding providers plug in behind the same `Embedder` interface
when the Settings screen lets people pick them (phase 5).
"""

import threading
from typing import Protocol

from app.config import get_settings

BATCH_SIZE = 32


class Embedder(Protocol):
    model_name: str

    @property
    def dim(self) -> int: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        settings = get_settings()
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(settings.models_dir))
        self._dim: int | None = None
        self._lock = threading.Lock()  # onnxruntime sessions are thread-safe, but keep peak RAM predictable

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed_query("dimension probe"))
        return self._dim

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return [v.tolist() for v in self._model.passage_embed(texts, batch_size=BATCH_SIZE)]

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            return next(iter(self._model.query_embed(text))).tolist()


_embedders: dict[str, Embedder] = {}
_lock = threading.Lock()


def get_embedder(model_name: str | None = None) -> Embedder:
    name = model_name or get_settings().embedding_model
    with _lock:
        if name not in _embedders:
            _embedders[name] = FastEmbedder(name)
        return _embedders[name]


def set_embedder(model_name: str, embedder: Embedder) -> None:
    """Register an embedder (used by tests to avoid loading a real model)."""
    with _lock:
        _embedders[model_name] = embedder


def clear_embedders() -> None:
    with _lock:
        _embedders.clear()
