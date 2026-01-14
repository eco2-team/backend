# apps/chat_worker/Dockerfile
# Chat Worker - Taskiq based LangGraph Pipeline Executor
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

COPY apps/chat_worker/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# chat 패키지 복사 (domain, application 재사용)
COPY apps/chat /app/chat

# Worker 코드 복사
COPY apps/chat_worker /app/chat_worker

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 보안: non-root 사용자로 실행
USER appuser

# Taskiq Worker 실행
CMD ["taskiq", "worker", "chat_worker.main:broker", \
     "--workers", "4", \
     "--max-async-tasks", "10"]
