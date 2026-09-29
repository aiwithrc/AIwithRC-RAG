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
from app.providers.chat import THINKING, ChatTarget, complete, context_window, stream_chat
from app.rag import cite
from app.rag.retrieve import Passage, coverage, retrieve

log = logging.getLogger("aiwithrc.answer")

# Fixed: answers stay grounded, and the [n] citations and source panel depend on these.
GROUNDING = """You are an expert analyst answering questions about the user's documents. You are given numbered passages from those documents.

Grounding rules (always apply):
- Use only facts stated in the passages. Never add outside knowledge or guess. You may connect and compare facts from different passages.
- After each sentence or bullet that states a fact, cite the passage number(s) it came from in square brackets, like [1] or [2][3]. Only cite numbers that appear in the passages.
- If the passages don't contain the answer, say so plainly in one sentence and don't cite anything. If they answer only part of it, answer that part and say clearly what's missing.
- Answer in the language of the question. Don't say "according to the passages" or mention passage numbers other than as citations."""

# Default style: the workspace's own instructions (Prompt screen) take priority over this.
STYLE = """Answer style:
- Start with the direct answer in the first sentence, and put the single most important fact in **bold**.
- Match the length to the question. A simple fact needs 1–3 sentences. Explanations, comparisons, processes, summaries or questions with several parts deserve a complete, well-organised answer: short paragraphs, bullet or numbered lists, and a Markdown table when comparing several items.
- Be specific: keep exact names, numbers, dates and amounts as written.
- Use "##" headings only for long answers with several distinct parts. No preamble, and don't repeat the question."""

SYSTEM = f"{GROUNDING}\n\n{STYLE}"

MAX_INSTRUCTIONS = 8000


def system_prompt(instructions: str = "") -> str:
    """Grounding rules, default style, then the workspace's own instructions (Prompt screen) when set.
    Workspace instructions override the style (length, tone, format) but never the grounding and citation rules."""
    extra = (instructions or "").strip()[:MAX_INSTRUCTIONS]
    if not extra:
        return SYSTEM
    return (
        f"{SYSTEM}\n\nWorkspace instructions (these take priority over the answer style above; the grounding rules "
        f"and [n] citations still always apply):\n{extra}"
    )


REWRITE_SYSTEM = """Rewrite the user's latest question as one standalone question that can be understood without the conversation. Replace pronouns like "he", "it" or "that" with what they refer to. If it is already standalone, return it unchanged. Reply with the question only."""

FOLLOWUP_SYSTEM = """Suggest follow-up questions a reader might ask next, answerable from the passages. Reply with only a JSON array of 3 short questions (under 12 words each), and nothing else."""

NOT_FOUND = (
    "I couldn't find a passage that answers this directly. The closest match is below [1], but it only partly "
    "covers the question. Try rephrasing, or search a different knowledge base."
)


@dataclass
class Settings:
    top_k: int = 8
    hybrid: bool = True
    rerank: bool = True
    embedding_model: str | None = None
    instructions: str = ""
    context_tokens: int = 8000


# Room kept free in the model's context window for the prompt, earlier turns and the answer itself.
RESERVED_TOKENS = 3000
MIN_CONTEXT_TOKENS = 1200
HISTORY_TURNS = 3  # earlier question/answer pairs the model sees
HISTORY_CHARS = 1500

_OVERVIEW = re.compile(
    r"\b(summar(y|ise|ize|ies)|overview|outline|tl;?dr|gist|key (points|takeaways|findings|themes)|"
    r"main (points|ideas|topics|themes)|what('s| is) (this|the) (document|doc|file|pdf|report|paper) about|"
    r"table of contents|walk me through)\b",
    re.I,
)


def is_overview(question: str) -> bool:
    """Questions about a whole document need coverage of all of it, not the few most similar chunks."""
    return bool(_OVERVIEW.search(question))


def budget_for(window: int | None, context_tokens: int) -> int:
    """Passage tokens for one question: the workspace setting, capped by what the model can actually hold."""
    budget = context_tokens
    if window:
        budget = min(budget, window - RESERVED_TOKENS)
    return max(MIN_CONTEXT_TOKENS, budget)


def history_messages(history: list[dict]) -> list[dict]:
    """Earlier turns as alternating user/assistant messages (old [n] markers removed: they point at other passages)."""
    pairs: list[dict] = []
    i = 0
    while i + 1 < len(history):
        q, a = history[i], history[i + 1]
        if q["role"] == "user" and a["role"] == "assistant":
            pairs += [
                {"role": "user", "content": q["content"][:HISTORY_CHARS]},
                {"role": "assistant", "content": cite.strip_markers(a["content"])[:HISTORY_CHARS]},
            ]
            i += 2
        else:
            i += 1
    return pairs[-2 * HISTORY_TURNS :]


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


STARTER_SYSTEM = """Suggest questions a new reader would ask about this document, answerable from the passages. Reply with only a JSON array of 3 short, specific questions (under 12 words each), and nothing else."""


async def suggest_starters(target: ChatTarget, passages: list[Passage]) -> list[str]:
    """Questions to try on the empty chat screen, from the start of the latest document."""
    try:
        content = "Passages:\n\n" + format_passages(passages)
        text = await complete(target, STARTER_SYSTEM, [{"role": "user", "content": content}], max_tokens=150)
    except ProviderError:
        return []
    return parse_followups(cite.strip_think(text), "")


def _retrieve(kb_id: str, question: str, s: Settings, budget: int, overview: bool) -> list[Passage]:
    with SessionLocal() as db:
        passages = retrieve(
            db, kb_id, question, top_k=s.top_k, hybrid=s.hybrid, rerank=s.rerank, embedding_model=s.embedding_model,
            token_budget=budget, expand=not overview,
        )
        if overview and passages:
            # The document the question is most about, read across its whole length.
            spread = coverage(db, passages[0].document_id, question, token_budget=budget, rerank=s.rerank)
            if spread:
                return spread
        return passages


async def run(
    target: ChatTarget, kb_id: str, kb_name: str, question: str, history: list[dict], s: Settings
) -> AsyncIterator[tuple[str, object]]:
    """Yields ("status", dict), ("token", str), ("result", Result), then maybe ("followups", list[str]).
    Raises ProviderError."""
    yield "status", {"stage": "searching"}
    standalone = await rewrite(target, history, question)
    overview = is_overview(standalone)
    budget = budget_for(await context_window(target), s.context_tokens)
    passages = await run_in_threadpool(_retrieve, kb_id, standalone, s, budget, overview)

    if not passages:
        yield "result", Result(
            content=f"There are no indexed documents in {kb_name} yet. Upload a file on the knowledge base page, "
            "then ask again.",
            confidence=None, standalone=standalone,
        )
        return

    best = max(p.score for p in passages)
    if best < cite.MIN_RELEVANCE and not overview:
        # Nothing relevant enough: don't ask the model, show the closest passage instead.
        yield "result", Result(
            content=NOT_FOUND, confidence="low",
            citations=[cite.closest_citation(passages[0], standalone).dict()], standalone=standalone,
        )
        return

    yield "status", {"stage": "answering", "passages": len(passages)}
    note = (
        "\n\nThese passages are spread across the whole document, in reading order."
        if overview else ""
    )
    user = (
        f"Passages:{note}\n\n{format_passages(passages)}\n\n"
        f"Question: {standalone}"
    )
    messages = [*history_messages(history), {"role": "user", "content": user}]
    raw = ""
    # Generous budget: long structured answers, and some models reason first even when asked not to.
    system = system_prompt(s.instructions)
    async for piece in stream_chat(target, system, messages, max_tokens=4000):
        if piece is THINKING:
            yield "status", {"stage": "thinking"}
            continue
        raw += piece
        yield "token", piece

    content, citations = cite.build_citations(raw, passages)
    if not content:
        raise ProviderError("The model returned an empty answer. Try again, or pick a different model.")
    conf = "high" if overview and len(citations) >= 2 else cite.confidence(passages, citations)
    yield "result", Result(
        content=content, confidence=conf,
        citations=[c.dict() for c in citations], standalone=standalone,
    )
    # Follow-ups come after the answer is saved and shown, so they never delay it.
    if citations:
        yield "followups", await suggest_followups(target, passages, standalone)
