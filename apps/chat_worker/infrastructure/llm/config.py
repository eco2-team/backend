"""LLM 공통 설정."""

import httpx

HTTP_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=60.0,
    write=10.0,
    pool=5.0,
)

HTTP_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

MAX_RETRIES = 2

MODEL_CONTEXT_WINDOWS = {
    "gpt-5.2": 256_000,
    "gpt-5.2-pro": 256_000,
    "gpt-5.2-instant": 128_000,
    "gpt-5-mini": 128_000,
    "gemini-3-flash-preview": 1_000_000,
    "gemini-3-pro-preview": 2_000_000,
}
