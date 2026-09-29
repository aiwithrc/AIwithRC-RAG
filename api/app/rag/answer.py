"""Answer a question from a knowledge base: rewrite (chat memory) → retrieve → stream answer →
citations, confidence, follow-ups. Yields events for the SSE stream; the router persists the result.
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.providers.base import ProviderError
from app.providers.chat import THINKING, ChatTarget, complete, stream_chat
from app.rag import cite
from app.rag.retrieve import Passage, retrieve

log = logging.getLogger("aiwithrc.answer")

SYSTEM = """You answer questions using only the numbered passages you are given.

Rules:
- Use only facts stated in the passages. Never add outside knowledge or guess.
- After each sentence that states a fact, cite the passage number(s) it came from in square brackets, like [1] or [2][3]. Only cite numbers that appear in the passages.
- Put the single most important fact in **bold**.
- Keep it short: 1–4 sentences, or a brief bulleted list if the question asks for several items.
- If the passages don't contain the answer, say so plainly in one sentence and don't cite anything.
- Answer in the language of the question. No preamble or headings, and don't say "according to the passages"."""

MAX_INSTRUCTIONS = 4000


def system_prompt(instructions: str = "") -> str:
    """Built-in rules, plus the workspace's own instructions (Prompt screen) when set.
    The built-in rules come first and win on conflict: citations and the source panel depend on them."""
    extra = (instructions or "").strip()[:MAX_INSTRUCTIONS]
    if not extra:
        return SYSTEM
    return (
        f"{SYSTEM}\n\nAdditional instructions from this workspace (follow them unless they conflict with the rules "
        f"above; always keep citing passages as [n]):\n{extra}"
    )


REWRITE_SYSTEM = """Rewrite the user's latest question as one standalone question that can be understood without the conversation. Replace pronouns like "he", "it" or "that" with what they refer to. If it is already standalone, return it unchanged. Reply with the question only."""

FOLLOWUP_SYSTEM = """Suggest follow-up questions a reader might ask next, answerable from the passages. Reply with only a JSON array of 3 short questions (under 12 words each), and nothing else."""

NOT_FOUND = (
    "I couldn't find a passage that answers this directly. The closest match is below [1], but it only partly "
    "covers the question. Try rephrasing, or search a different knowledge base."
)


@dataclass
class Settings:
    top_k: int = 5
    hybrid: bool = True
    rerank: bool = True
    embedding_model: str | None = None
    instructions: str = ""


@dataclass
class Result:
    content: str
    confidence: str | None
    citations: list[dict] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    standalone: str = ""


def format_passages(passages: list[Passage]) -> str:
    out = []
    for i, p in enumerate(passages, start=1):
        loc = p.location()
        out.append(f"[{i}] {p.filename}{' — ' + loc if loc else ''}\n{p.text}")
    return "\n\n".join(out)


def parse_followups(text: str, question: str) -> list[str]:
    m = re.search(r"\[.*\]", text, re.S)
    items: list = []
    if m:
        try:
            items = json.loads(m.group(0))
        except ValueError:
            items = []
    if not items:  # fall back to one-per-line lists
        items = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in text.splitlines()]
    seen, out = {question.strip().lower()}, []
    for q in items:
        if not isinstance(q, str):
            continue
        q = q.strip().strip('"').strip()
        if 3 < len(q) <= 120 and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q if q.endswith("?") else q + "?")
    return out[:3]


_REFERS_BACK = re.compile(
    r"\b(he|him|his|she|her|hers|it|its|they|them|their|this|that|these|those|there|then|same|above|former|latter|"
    r"previous|earlier|else|more|also|too|what about|how about)\b",
    re.I,
)


def needs_rewrite(question: str) -> bool:
    """Only follow-ups that point back at the conversation need an extra model call."""
    return len(question.split()) <= 4 or bool(_REFERS_BACK.search(question))


async def rewrite(target: ChatTarget, history: list[dict], question: str) -> str:
    """Turn a follow-up into a standalone question using the last few messages."""
    if not history or not needs_rewrite(question):
        return question
    convo = "\n".join(f"{m['role'].title()}: {m['content'][:600]}" for m in history[-4:])
    try:
        out = await complete(
            target, REWRITE_SYSTEM,
            [{"role": "user", "content": f"Conversation:\n{convo}\n\nLatest question: {question}"}],
            max_tokens=80,
        )
    except ProviderError:
        return question
    out = cite.strip_think(out).strip().strip('"').splitlines()[0].strip() if out.strip() else ""
    return out if 3 < len(out) <= 300 else question


async def suggest_followups(target: ChatTarget, passages: list[Passage], question: str) -> list[str]:
    try:
        text = await complete(
            target, FOLLOWUP_SYSTEM,
            [{"role": "user", "content": f"Passages:\n\n{format_passages(passages[:3])}\n\nAlready asked: {question}"}],
            max_tokens=120,
        )
    except ProviderError:
        return []
    return parse_followups(cite.strip_think(text), question)


def _retrieve(kb_id: str, question: str, s: Settings) -> list[Passage]:
    with SessionLocal() as db:
        return retrieve(
            db, kb_id, question, top_k=s.top_k, hybrid=s.hybrid, rerank=s.rerank, embedding_model=s.embedding_model
        )


async def run(
    target: ChatTarget, kb_id: str, kb_name: str, question: str, history: list[dict], s: Settings
) -> AsyncIterator[tuple[str, object]]:
    """Yields ("status", dict), ("token", str), ("result", Result), then maybe ("followups", list[str]).
    Raises ProviderError."""
    yield "status", {"stage": "searching"}
    standalone = await rewrite(target, history, question)
    passages = await run_in_threadpool(_retrieve, kb_id, standalone, s)

    if not passages:
        yield "result", Result(
            content=f"There are no indexed documents in {kb_name} yet. Upload a file on the knowledge base page, "
            "then ask again.",
            confidence=None, standalone=standalone,
        )
        return

    best = max(p.score for p in passages)
    if best < cite.MIN_RELEVANCE:
        # Nothing relevant enough: don't ask the model, show the closest passage instead.
        yield "result", Result(
            content=NOT_FOUND, confidence="low",
            citations=[cite.closest_citation(passages[0], standalone).dict()], standalone=standalone,
        )
        return

    yield "status", {"stage": "answering", "passages": len(passages)}
    user = f"Passages:\n\n{format_passages(passages)}\n\nQuestion: {standalone}"
    raw = ""
    # Generous budget: some models reason before answering even when asked not to.
    system = system_prompt(s.instructions)
    async for piece in stream_chat(target, system, [{"role": "user", "content": user}], max_tokens=3000):
        if piece is THINKING:
            yield "status", {"stage": "thinking"}
            continue
        raw += piece
        yield "token", piece

    content, citations = cite.build_citations(raw, passages)
    if not content:
        raise ProviderError("The model returned an empty answer. Try again, or pick a different model.")
    yield "result", Result(
        content=content, confidence=cite.confidence(passages, citations),
        citations=[c.dict() for c in citations], standalone=standalone,
    )
    # Follow-ups come after the answer is saved and shown, so they never delay it.
    if citations:
        yield "followups", await suggest_followups(target, passages, standalone)
