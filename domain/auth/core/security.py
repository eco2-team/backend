import base64
import hashlib
import secrets
from datetime import datetime, timezone
from enum import Enum


def _urlsafe_b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    # RFC 7636 recommends 43-128 chars.
    return secrets.token_urlsafe(64)


def generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _urlsafe_b64(digest)


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def compute_ttl_seconds(expires_at: datetime) -> int:
    delta = expires_at - now_utc()
    return max(int(delta.total_seconds()), 0)


def to_unix_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())
