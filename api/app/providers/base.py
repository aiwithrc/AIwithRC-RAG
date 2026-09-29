"""Facts about a provider connection derived from its API Base: kind, display name, local vs cloud."""

import ipaddress
from typing import Literal
from urllib.parse import urlsplit

Kind = Literal["openai_compat", "anthropic"]
Runtime = Literal["local", "cloud"]


class ProviderError(Exception):
    """A connection problem worth showing to the user as-is."""


def normalize_base(api_base: str) -> str:
    base = api_base.strip().rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ProviderError("API Base must start with http:// or https://")
    if parts.query or parts.fragment:
        raise ProviderError("API Base shouldn't include ?query or #fragment.")
    return base


def host_of(api_base: str) -> str:
    return (urlsplit(api_base).hostname or "").lower()


def port_of(api_base: str) -> int | None:
    try:
        return urlsplit(api_base).port
    except ValueError:
        return None


def kind_for(api_base: str) -> Kind:
    return "anthropic" if host_of(api_base).endswith("anthropic.com") else "openai_compat"


def display_name(api_base: str) -> str:
    host, port = host_of(api_base), port_of(api_base)
    base = api_base.lower()
    if port == 11434 or "ollama" in base:
        return "Ollama"
    if port == 1234 or "lmstudio" in base or "lm-studio" in base:
        return "LM Studio"
    if host.endswith("anthropic.com"):
        return "Anthropic"
    if host.endswith("openai.com"):
        return "OpenAI"
    if host.endswith("openrouter.ai"):
        return "OpenRouter"
    if host.endswith("groq.com"):
        return "Groq"
    if host.endswith("mistral.ai"):
        return "Mistral"
    if host.endswith("together.xyz") or host.endswith("together.ai"):
        return "Together"
    if port == 8000 and _is_local_host(host):
        return "vLLM"
    return urlsplit(api_base).netloc or "Custom endpoint"


def _is_local_host(host: str) -> bool:
    if host in ("localhost", "host.docker.internal", "gateway.docker.internal") or host.endswith(
        (".local", ".internal", ".lan", ".localhost")
    ):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def runtime_for(api_base: str) -> Runtime:
    """Local = the model runs on this machine or network, so passages never leave it."""
    return "local" if _is_local_host(host_of(api_base)) else "cloud"


def is_chat_model(model_id: str) -> bool:
    m = model_id.lower()
    return not any(s in m for s in ("embed", "embedding", "rerank", "whisper", "tts", "dall-e", "moderation"))
