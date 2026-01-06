# apps/users_worker/Dockerfile
# Users Worker - Celery Worker (독립적, 도메인 의존성 없음)
# 처리 큐: users.save_character (유저 캐릭터 DB 동기화)
# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/users_worker/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치 (gcc 제외)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# Worker 코드만 복사 (apps.users_worker 경로 유지)
COPY apps/users_worker /app/apps/users_worker

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 보안: non-root 사용자로 실행
USER appuser

# Celery Worker 실행
CMD ["celery", "-A", "apps.users_worker.main", "worker", "-E", "--loglevel=info", "-Q", "users.save_character", "-c", "2"]
