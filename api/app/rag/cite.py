"""Citations: clean up the model's [n] markers, keep only valid ones, renumber them 1..m in order of
first use, and find the sentence(s) in each passage that best support the claims citing it.
Also decides answer confidence.
"""

import re
from dataclasses import asdict, dataclass

from app.rag.chunk import split_sentences
from app.rag.retrieve import Passage

HIGH_CONFIDENCE = 0.75
MIN_RELEVANCE = 0.35
CONTEXT_CHARS = 360  # text kept before/after the highlighted span

# [1] [1, 2] [1][2] 【1】 [^1] [1-3] … inside the answer text.
_MARKER = re.compile(r"[\[【]\^?\s*(\d+(?:\s*[,–-]\s*\d+)*)\s*[\]】]")
_THINK = re.compile(r"<think>.*?</think>", re.S)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an the and or of to in on at by for with from as is are was were be been being this that these those it its "
    "their there they them he she his her we you your our i not no can may shall will would should could must does "
    "do did has have had than then so such any all each which who whom what when where how per also into about".split()
)


@dataclass
class Citation:
    n: int
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    location: str
    score: float
    chunk: int  # 1-based ordinal within the document
    total: int
    before: str
    hit: str
    after: str

    def dict(self) -> dict:
        return asdict(self)


def strip_think(text: str) -> str:
    """Remove reasoning blocks from reasoning models (Qwen3, DeepSeek-R1, …)."""
    text = _THINK.sub("", text)
    if "</think>" in text:  # opening tag was in the prompt template; drop everything before the close
        text = text.split("</think>", 1)[1]
    return text.replace("<think>", "").strip()


def strip_markers(text: str) -> str:
    """Answer text without [n] citation markers."""
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", _MARKER.sub("", text)).strip()


def _expand(group: str) -> list[int]:
    nums: list[int] = []
    for part in re.split(r"\s*,\s*", group):
        m = re.match(r"(\d+)\s*[–-]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a < 10:
                nums += list(range(a, b + 1))
                continue
        if part.strip().isdigit():
            nums.append(int(part))
    return nums


def renumber(text: str, n_passages: int) -> tuple[str, list[int]]:
    """Rewrite markers to [1]..[m] in order of first use. Returns (text, original passage numbers used)."""
    order: list[int] = []

    def sub(m: re.Match) -> str:
        out = ""
        for n in _expand(m.group(1)):
            if not 1 <= n <= n_passages:
                continue  # drop citations to passages that don't exist
            if n not in order:
                order.append(n)
            marker = f"[{order.index(n) + 1}]"
            if marker not in out:
                out += marker
        return out

    text = _MARKER.sub(sub, text)
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)  # "claim [9]." -> "claim." after dropping [9]
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip(), order


def _terms(text: str) -> set[str]:
    return {w[:6] for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}  # crude stemming


def _claims_for(text: str, n: int) -> str:
    """Sentences of the answer that cite [n]."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return " ".join(p for p in parts if f"[{n}]" in p) or text


def highlight(chunk_text: str, claim: str) -> tuple[str, str, str]:
    """Split the chunk into (before, hit, after) where hit is the sentence(s) overlapping most with the claim."""
    # Line breaks are boundaries too, so a heading line without a full stop isn't glued to the next sentence.
    sentences = [s for line in chunk_text.split("\n") for s in split_sentences(line.strip()) if s]
    if not sentences:
        return "", chunk_text, ""
    claim_terms = _terms(_MARKER.sub("", claim))
    scores = []
    for s in sentences:
        st = _terms(s)
        scores.append(len(st & claim_terms) / (len(claim_terms) ** 0.5 * max(1, len(st)) ** 0.5) if st else 0.0)
    best = max(range(len(sentences)), key=lambda i: scores[i])
    lo = hi = best
    # Extend to an adjacent sentence that also supports the claim.
    if best + 1 < len(sentences) and scores[best + 1] >= 0.6 * scores[best] > 0:
        hi = best + 1
    elif best > 0 and scores[best - 1] >= 0.6 * scores[best] > 0:
        lo = best - 1
    before = " ".join(sentences[:lo])
    hit = " ".join(sentences[lo : hi + 1])
    after = " ".join(sentences[hi + 1 :])
    if len(before) > CONTEXT_CHARS:
        before = "…" + before[-CONTEXT_CHARS:].split(" ", 1)[-1]
    if len(after) > CONTEXT_CHARS:
        after = after[:CONTEXT_CHARS].rsplit(" ", 1)[0] + "…"
    return (before + " ") if before else "", hit, (" " + after) if after else ""


def build_citations(raw_answer: str, passages: list[Passage]) -> tuple[str, list[Citation]]:
    text, used = renumber(strip_think(raw_answer), len(passages))
    cites = []
    for new_n, old_n in enumerate(used, start=1):
        p = passages[old_n - 1]
        before, hit, after = highlight(p.text, _claims_for(text, new_n))
        cites.append(
            Citation(
                n=new_n, chunk_id=p.chunk_id, document_id=p.document_id, filename=p.filename, page=p.page,
                section=p.section, location=p.location(), score=p.score, chunk=p.ordinal + 1, total=p.doc_chunks,
                before=before, hit=hit, after=after,
            )
        )
    return text, cites


def closest_citation(p: Passage, question: str) -> Citation:
    before, hit, after = highlight(p.text, question)
    return Citation(
        n=1, chunk_id=p.chunk_id, document_id=p.document_id, filename=p.filename, page=p.page, section=p.section,
        location=p.location(), score=p.score, chunk=p.ordinal + 1, total=p.doc_chunks,
        before=before, hit=hit, after=after,
    )


CLEAR_WINNER = 0.55  # a passage this relevant that stands out from the rest…
CLEAR_MARGIN = 0.2  # …by this much is also strong evidence (long mixed-topic chunks rarely reach 0.75)


def confidence(passages: list[Passage], citations: list[Citation]) -> str:
    if not citations:
        return "low"
    scores = sorted((p.score for p in passages), reverse=True)
    best = scores[0] if scores else 0.0
    cited_best = max(c.score for c in citations)
    if best >= HIGH_CONFIDENCE:
        return "high"
    runner_up = scores[1] if len(scores) > 1 else 0.0
    if cited_best == best and best >= CLEAR_WINNER and best - runner_up >= CLEAR_MARGIN:
        return "high"
    return "low"
