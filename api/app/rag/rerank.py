"""Cross-encoder reranking (fastembed, ONNX on CPU). Scores become 0–1 relevance via a sigmoid."""

import math
import threading
from typing import Protocol

from app.config import get_settings

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class Reranker(Protocol):
    def scores(self, query: str, texts: list[str]) -> list[float]:
        """Raw relevance logits, one per text (higher = more relevant)."""
        ...


class FastReranker:
    def __init__(self, model_name: str = RERANK_MODEL) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        settings = get_settings()
        settings.models_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextCrossEncoder(model_name=model_name, cache_dir=str(settings.models_dir))
        self._lock = threading.Lock()

    def scores(self, query: str, texts: list[str]) -> list[float]:
        with self._lock:
            return [float(s) for s in self._model.rerank(query, texts, batch_size=16)]


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


# Calibration for ms-marco-MiniLM-L-6-v2, measured on real documents (contracts, a résumé):
# unrelated question/passage pairs score about -11; passages that answer the question score
# -0.2 to +6.6 even when worded differently ("study" vs "Education"). A plain sigmoid put a
# correct answer at 0.44 ("low confidence"). Centre at -5 and soften: -11 -> 0.08, -5 -> 0.50,
# -0.2 -> 0.87, +3 -> 0.96. Thresholds stay as specified: skip the LLM below 0.35, high >= 0.75.
CENTER, SCALE = -5.0, 2.5


def relevance(logit: float) -> float:
    """Cross-encoder logit -> 0-1 relevance shown in the UI and used for confidence."""
    return sigmoid((logit - CENTER) / SCALE)


_reranker: Reranker | None = None
_lock = threading.Lock()


def get_reranker() -> Reranker:
    global _reranker
    with _lock:
        if _reranker is None:
            _reranker = FastReranker()
        return _reranker


def set_reranker(r: Reranker | None) -> None:
    """Swap the reranker (tests use a fake)."""
    global _reranker
    with _lock:
        _reranker = r
