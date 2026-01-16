# apps/chat/Dockerfile
# Chat API - Clean Architecture (Intent-Routed Workflow with Subagent)
# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/chat/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# API 코드 복사
COPY apps/chat /app/chat

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 보안: non-root 사용자로 실행
USER appuser

# 헬스체크
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# FastAPI 서버 실행
CMD ["python", "-m", "uvicorn", "chat.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
