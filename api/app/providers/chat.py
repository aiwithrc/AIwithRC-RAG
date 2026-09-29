"""Chat completions: streaming and one-shot, for OpenAI-compatible APIs and Anthropic.

Reasoning models (Qwen3, DeepSeek-R1, …) may wrap their thinking in <think>…</think>; `ThinkFilter`
hides it from the stream so only the answer reaches the user.
"""

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from app.providers.base import ProviderError, display_name, host_of
from app.providers.catalog import ANTHROPIC_VERSION, anthropic_base

# Local models can take a while to load and to produce the first token.
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)

# Tests swap this for httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


@dataclass
class ChatTarget:
    api_base: str
    api_key: str
    kind: str  # openai_compat | anthropic
    model: str
    local: bool = False  # LM Studio / Ollama / vLLM on this machine or network


class _Thinking(str):
    """Yielded once by `stream_chat` when the model starts reasoning on a separate channel."""


THINKING = _Thinking("")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, transport=transport)


def _wants_no_think(model: str) -> bool:
    """Qwen3-family models honour a /no_think switch; answering from passages doesn't need long reasoning."""
    m = model.lower()
    return "qwen3" in m or "qwq" in m


class ThinkFilter:
    """Streaming filter that drops <think>…</think> spans, even when tags are split across chunks."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.buf = ""
        self.inside = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = ""
        while self.buf:
            tag = self.CLOSE if self.inside else self.OPEN
            i = self.buf.find(tag)
            if i >= 0:
                if not self.inside:
                    out += self.buf[:i]
                self.buf = self.buf[i + len(tag) :]
                self.inside = not self.inside
                continue
            # Keep a possible partial tag at the end for the next chunk.
            keep = next((k for k in range(len(tag) - 1, 0, -1) if self.buf.endswith(tag[:k])), 0)
            if not self.inside:
                out += self.buf[: len(self.buf) - keep]
            self.buf = self.buf[len(self.buf) - keep :] if keep else ""
            break
        return out

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest


def _error_from(r_text: str, status: int) -> str:
    try:
        body = json.loads(r_text)
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except (ValueError, AttributeError):
        msg = r_text[:200]
    return f"The model server answered with an error ({status}): {msg}" if msg else f"The model server answered {status}."


def _prepare(
    target: ChatTarget, system: str, messages: list[dict], max_tokens: int, stream: bool, no_reasoning: bool = True
) -> tuple[str, dict, dict]:
    if _wants_no_think(target.model):
        system = system + "\n/no_think"
    if target.kind == "anthropic":
        url = anthropic_base(target.api_base) + "/messages"
        headers = {"x-api-key": target.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        body = {"model": target.model, "system": system, "messages": messages, "max_tokens": max_tokens, "stream": stream}
    else:
        url = target.api_base.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        body = {
            "model": target.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": stream,
        }
        if target.local and no_reasoning:
            # Local reasoning models (e.g. Qwen3.5 in LM Studio) otherwise spend hundreds of tokens thinking
            # before answering. Answering from given passages doesn't need it. OpenAI's API rejects "none"
            # for non-reasoning models, so this is only sent to local servers (and retried without on 400).
            body["reasoning_effort"] = "none"
    return url, headers, body


def _connect_error(target: ChatTarget) -> ProviderError:
    return ProviderError(
        f"Couldn't reach {display_name(target.api_base)} at {host_of(target.api_base)}. Check that it's running."
    )


async def stream_chat(target: ChatTarget, system: str, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
    """Yield answer text as it arrives (thinking removed). Yields THINKING once if the model reasons first."""
    think = ThinkFilter()
    reasoning_seen = False
    try:
        async with _client() as c:
            for attempt in (0, 1):
                url, headers, body = _prepare(target, system, messages, max_tokens, stream=True, no_reasoning=attempt == 0)
                async with c.stream("POST", url, headers=headers, json=body) as r:
                    if r.status_code >= 400:
                        text = (await r.aread()).decode(errors="replace")
                        if attempt == 0 and "reasoning_effort" in body and r.status_code in (400, 422):
                            continue  # server doesn't know reasoning_effort: retry without it
                        msg = _error_from(text, r.status_code)
                        raise ProviderError(context_error(msg) or msg)
                    async for piece in _read_stream(r, target, think):
                        if piece is THINKING:
                            if not reasoning_seen:
                                reasoning_seen = True
                                yield THINKING
                            continue
                        yield piece
                    if tail := think.flush():
                        yield tail
                    return
    except httpx.ConnectError as e:
        raise _connect_error(target) from e
    except httpx.TimeoutException as e:
        raise ProviderError("The model took too long to respond. It may still be loading; try again.") from e
    except httpx.HTTPError as e:
        raise ProviderError(f"Lost the connection to the model server ({e.__class__.__name__}).") from e


async def _read_stream(r: httpx.Response, target: ChatTarget, think: ThinkFilter) -> AsyncIterator[str]:
    """Parse one SSE response into answer text; yields THINKING for reasoning-channel chunks."""
    async for line in r.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            evt = json.loads(data)
        except ValueError:
            continue
        if target.kind == "anthropic":
            if evt.get("type") == "error":
                raise ProviderError(evt.get("error", {}).get("message", "The model returned an error."))
            delta = evt.get("delta", {}) if evt.get("type") == "content_block_delta" else {}
            if delta.get("type") == "thinking_delta":
                yield THINKING
                continue
            piece = delta.get("text", "")
        else:
            if "error" in evt:
                err = evt["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                raise ProviderError(context_error(msg) or msg)
            delta = (evt.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("reasoning_content") or delta.get("reasoning"):
                yield THINKING  # separate reasoning channel (LM Studio, vLLM, DeepSeek): never shown
            piece = delta.get("content") or ""
        if piece and (out := think.feed(piece)):
            yield out


async def complete(target: ChatTarget, system: str, messages: list[dict], max_tokens: int = 200) -> str:
    """One-shot completion (thinking removed)."""
    parts = [p async for p in stream_chat(target, system, messages, max_tokens) if p is not THINKING]
    return "".join(parts).strip()


_CONTEXT_WORDS = ("context length", "context window", "context_length", "maximum context", "n_ctx", "too many tokens",
                  "prompt is too long", "exceeds the context", "context size")


def context_error(message: str) -> str | None:
    """A friendlier message when the prompt didn't fit the model's context window."""
    low = message.lower()
    if any(w in low for w in _CONTEXT_WORDS):
        return (
            "The question plus the retrieved passages didn't fit the model's context window. In LM Studio, reload the "
            "model with a larger Context Length (16384 or more), or lower \"Context per answer\" in Settings."
        )
    return None


_ctx_cache: dict[tuple[str, str], tuple[float, int | None]] = {}


async def context_window(target: ChatTarget) -> int | None:
    """Context length the model is loaded with, when the server says (LM Studio's /api/v0). Cached for a minute.
    None means unknown: cloud models and Ollama are assumed to be large enough."""
    if not target.local or target.kind != "openai_compat":
        return None
    key = (target.api_base, target.model)
    now = time.monotonic()
    if key in _ctx_cache and now - _ctx_cache[key][0] < 60:
        return _ctx_cache[key][1]
    root = target.api_base.rstrip("/").removesuffix("/v1")
    ctx: int | None = None
    try:
        async with httpx.AsyncClient(timeout=3.0, transport=transport) as c:
            r = await c.get(f"{root}/api/v0/models/{target.model}")
            if r.status_code == 200:
                # Absent when the model isn't loaded yet (LM Studio loads it on first use).
                ctx = r.json().get("loaded_context_length") or None
    except (httpx.HTTPError, ValueError):
        ctx = None
    _ctx_cache[key] = (now, ctx)
    return ctx
