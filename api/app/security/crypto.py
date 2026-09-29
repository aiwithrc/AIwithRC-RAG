"""Encryption of secrets at rest (provider API keys) with a key derived from APP_SECRET."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings


def _fernet(secret: str | None = None) -> Fernet:
    raw = (secret if secret is not None else get_settings().app_secret).encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"aiwithrc-rag", info=b"secrets-at-rest").derive(raw)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str, secret: str | None = None) -> str:
    """Decrypt with APP_SECRET, or with `secret` (re-encrypting keys after APP_SECRET changed)."""
    try:
        return _fernet(secret).decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt secret. Did APP_SECRET change?") from e


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def mask_key(key: str) -> str:
    """`sk-ant-api03-…4f1c` → `sk-ant-…4f1c`. Never reveals more than prefix + last 4."""
    if len(key) <= 8:
        return "••••••••"
    prefix = key[:7] if key.startswith(("sk-", "sk_")) else key[:3]
    return f"{prefix}…{key[-4:]}"
