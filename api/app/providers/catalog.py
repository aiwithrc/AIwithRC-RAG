"""List a provider's models. Used to validate a connection when it's saved."""

from pathlib import Path

import httpx

from app.providers.base import ProviderError, host_of, kind_for

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
ANTHROPIC_VERSION = "2023-06-01"

# Tests swap this for httpx.MockTransport.
transport: httpx.BaseTransport | None = None


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, transport=transport, follow_redirects=True)


def _in_docker() -> bool:
    return Path("/.dockerenv").exists()


def anthropic_base(api_base: str) -> str:
    return api_base if api_base.rstrip("/").endswith("/v1") else api_base.rstrip("/") + "/v1"


def list_models(api_base: str, api_key: str) -> list[str]:
    """Return model ids, or raise ProviderError with a message for the person setting it up."""
    if kind_for(api_base) == "anthropic":
        url = anthropic_base(api_base) + "/models?limit=1000"
        headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
    else:
        url = api_base.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    host = host_of(api_base)
    try:
        with _client() as c:
            r = c.get(url, headers=headers)
    except httpx.ConnectError as e:
        msg = f"Couldn't reach {host}. Check the address and that the server is running."
        if _in_docker() and host in ("localhost", "127.0.0.1", "::1"):
            msg += " This app runs in Docker, so use host.docker.internal instead of localhost."
        raise ProviderError(msg) from e
    except httpx.TimeoutException as e:
        raise ProviderError(f"{host} didn't answer within 10 seconds.") from e
    except httpx.HTTPError as e:
        raise ProviderError(f"Couldn't connect to {host}: {e.__class__.__name__}.") from e

    if r.status_code in (401, 403):
        raise ProviderError("The server rejected this API key.")
    if r.status_code == 404:
        raise ProviderError(f"No models endpoint at {url.split('?')[0]}. Check the API Base (it usually ends in /v1).")
    if r.status_code >= 400:
        raise ProviderError(f"The server answered with an error ({r.status_code}).")
    try:
        body = r.json()
    except ValueError as e:
        raise ProviderError("The server's answer wasn't JSON. Check the API Base (it usually ends in /v1).") from e

    items = body.get("data") if isinstance(body, dict) else body
    if items is None and isinstance(body, dict):
        items = body.get("models")  # some servers (e.g. Ollama's native API) use "models"
    if not isinstance(items, list):
        raise ProviderError("The server's model list wasn't in the expected format.")
    ids = []
    for m in items:
        mid = (m.get("id") or m.get("name") or m.get("model")) if isinstance(m, dict) else m
        if isinstance(mid, str) and mid and mid not in ids:
            ids.append(mid)
    return ids
