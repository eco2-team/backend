# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/character_worker/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치 (gcc 제외)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# 공유 모듈 복사 (domains/_shared)
COPY domains/_shared /app/domains/_shared

# 애플리케이션 코드 복사
COPY apps/character /app/apps/character
COPY apps/character_worker /app/apps/character_worker

# PYTHONPATH 설정
ENV PYTHONPATH=/app

# 보안: non-root 사용자로 실행
USER appuser

# Celery Worker 시작
CMD ["celery", "-A", "apps.character_worker.main:app", "worker", \
     "--loglevel=info", \
     "--queues=character.match,character.reward,character.grant_default", \
     "--concurrency=4", \
     "--pool=prefork"]
