# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSE Gateway - Central Consumer + Memory Fan-out
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# workers=1, Pod 스케일링 전략
# 참조: docs/blogs/async/31-sse-fanout-optimization.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 루트에서 빌드 시 경로: domains/sse-gateway/requirements.txt
COPY domains/sse-gateway/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# 환경 변수
# PYTHONPATH: sse-gateway 폴더 우선 (상대 import 지원) + /app (domains._shared 지원)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/domains/sse-gateway:/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

# 애플리케이션 코드 복사
# - _shared/events: Redis Streams 클라이언트
COPY domains/_shared /app/domains/_shared
COPY domains/sse-gateway /app/domains/sse-gateway

# 비루트 사용자
RUN chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 포트
EXPOSE 8000

# 실행 (workers=1 필수 - 단일 Consumer 유지)
# main:app - PYTHONPATH에 sse-gateway 폴더가 포함되어 있어 상대 import 가능
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
