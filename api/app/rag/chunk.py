"""Split parsed blocks into overlapping, token-sized chunks along sentence boundaries.

Rules:
- A chunk never exceeds `chunk_size` tokens (only a single over-long sentence is split mid-sentence).
- Chunks break at paragraph/sentence boundaries, never mid-sentence if avoidable.
- A new section always starts a new chunk, so a citation's "§" label is accurate.
- A page change starts a new chunk once the current one is reasonably full, so page labels stay accurate.
- Consecutive chunks share up to `overlap` tokens of whole trailing sentences.
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache

from app.rag.parse import Block


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    if "TIKTOKEN_CACHE_DIR" not in os.environ:
        from app.config import get_settings

        cache = get_settings().models_dir / "tiktoken"
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


def context_header(filename: str, section: str | None) -> str:
    """A short line naming the document and section, prepended to a chunk for embedding, keyword
    search and reranking (not for display). "Acme_MSA_2024.pdf" + "§11.2 Termination" ->
    "Acme MSA 2024 › §11.2 Termination". Helps passages that never repeat their subject ("he", "it")."""
    stem = filename.rsplit(".", 1)[0]
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    return f"{stem} › {section}" if section else stem


def with_context(filename: str, section: str | None, text: str) -> str:
    return f"{context_header(filename, section)}\n{text}"


@dataclass
class ChunkDraft:
    text: str
    page: int | None
    section: str | None
    token_count: int


@dataclass
class _Unit:
    text: str
    tokens: int
    page: int | None
    section: str | None
    para_start: bool  # first sentence of a paragraph: join with a blank line


# Sentence end: . ! ? (optionally followed by quotes/brackets), whitespace, then an uppercase/digit/quote start.
_SENT_SPLIT = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9§])")
# A piece ending in one of these is not a sentence end ("Dr. Smith", "e.g. Acme", "J. Doe", "No. 5").
_ABBREV_END = re.compile(
    r"(?:\b(?:Mr|Ms|Mrs|Dr|Prof|Inc|Ltd|Co|vs|etc|e\.g|i\.e|No|Sec|Art|Fig|St|Jr|Sr|p|pp|approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)|\b[A-Z])\.$"
)


def split_sentences(paragraph: str) -> list[str]:
    out: list[str] = []
    for line_group in re.split(r"\n(?=\s*(?:[-*•]|\d+[.)])\s)", paragraph):  # list items stay separate
        pieces = [s.strip() for s in _SENT_SPLIT.split(line_group) if s.strip()]
        merged: list[str] = []
        for p in pieces:
            if merged and _ABBREV_END.search(merged[-1]):
                merged[-1] += " " + p
            else:
                merged.append(p)
        out += merged
    return out


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Split one over-long sentence by words so each piece fits."""
    enc = _encoding()
    pieces, cur = [], []
    for word in text.split(" "):
        candidate = " ".join([*cur, word])
        if cur and len(enc.encode(candidate, disallowed_special=())) > max_tokens:
            pieces.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        pieces.append(" ".join(cur))
    # A single "word" longer than max_tokens (e.g. a base64 blob): split by tokens.
    out = []
    for p in pieces:
        ids = enc.encode(p, disallowed_special=())
        if len(ids) <= max_tokens:
            out.append(p)
        else:
            out += [enc.decode(ids[i : i + max_tokens]) for i in range(0, len(ids), max_tokens)]
    return out


def _units(blocks: list[Block], chunk_size: int) -> list[_Unit]:
    units: list[_Unit] = []
    for b in blocks:
        for para in re.split(r"\n\s*\n", b.text):
            first = True
            for sent in split_sentences(para):
                n = count_tokens(sent)
                pieces = [sent] if n <= chunk_size else _hard_split(sent, chunk_size)
                for piece in pieces:
                    units.append(_Unit(piece, count_tokens(piece), b.page, b.section, first))
                    first = False
    return units


def _join(units: list[_Unit]) -> str:
    out = ""
    for i, u in enumerate(units):
        if i == 0:
            out = u.text
        else:
            out += ("\n\n" if u.para_start else " ") + u.text
    return out


def chunk_blocks(blocks: list[Block], chunk_size: int = 800, overlap: int = 120) -> list[ChunkDraft]:
    if chunk_size < 20:
        raise ValueError("chunk_size too small")
    overlap = max(0, min(overlap, chunk_size // 2))
    units = _units(blocks, chunk_size)
    chunks: list[ChunkDraft] = []
    cur: list[_Unit] = []
    cur_tokens = 0
    fresh = 0  # units in `cur` that are not overlap carried from the previous chunk

    def emit() -> None:
        nonlocal cur, cur_tokens, fresh
        if fresh == 0:
            return
        text = _join(cur)
        chunks.append(ChunkDraft(text, cur[0].page, cur[0].section, count_tokens(text)))
        # Carry whole trailing sentences (same section) as overlap into the next chunk.
        carry: list[_Unit] = []
        total = 0
        for u in reversed(cur):
            if total + u.tokens > overlap:
                break
            carry.insert(0, u)
            total += u.tokens
        cur, cur_tokens, fresh = carry, total, 0

    for u in units:
        section_change = bool(cur) and u.section != cur[-1].section
        page_change = bool(cur) and u.page != cur[-1].page and cur_tokens >= chunk_size // 3
        if (section_change or page_change) and fresh:
            emit()
            cur, cur_tokens = [], 0  # no overlap across a section or page break
        elif section_change:
            cur, cur_tokens = [], 0
        # +1 approximates the joining space/newline.
        if fresh and cur_tokens + u.tokens + 1 > chunk_size:
            emit()
        while cur and cur_tokens + u.tokens + 1 > chunk_size:  # overlap alone too big for this unit
            cur_tokens -= cur.pop(0).tokens
        cur.append(u)
        cur_tokens += u.tokens + (1 if len(cur) > 1 else 0)
        fresh += 1
    emit()
    return chunks
