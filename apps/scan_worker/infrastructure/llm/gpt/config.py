"""OpenAI 공통 설정.

타임아웃, 연결 제한, 재시도 설정 등.
"""

import httpx

# ==========================================
# HTTP 타임아웃 설정
# ==========================================

OPENAI_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=30.0,
    write=10.0,
    pool=5.0,
)

# ==========================================
# HTTP 연결 제한 설정
# ==========================================

OPENAI_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)

# ==========================================
# OpenAI 클라이언트 공통 설정
# ==========================================

MAX_RETRIES = 2
