# apps/info_worker/Dockerfile
# Info Worker - Celery Beat 기반 뉴스 수집 Worker
# info 패키지에 의존 (NewsAggregatorService, NaverNewsClient 등)
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

# info + info_worker 의존성 모두 설치
COPY apps/info/requirements.txt ./info-requirements.txt
COPY apps/info_worker/requirements.txt ./info-worker-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
    -r info-requirements.txt \
    -r info-worker-requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치 (gcc 제외)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# info 패키지 복사 (info_worker가 의존)
COPY apps/info /app/info

# info_worker 코드 복사
COPY apps/info_worker /app/info_worker

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 보안: non-root 사용자로 실행
USER appuser

# Celery Worker 실행 (gevent pool)
CMD ["celery", "-A", "info_worker.setup.celery:celery_app", "worker", \
     "--pool=gevent", "--concurrency=100", \
     "-Q", "info.collect_news", \
     "--loglevel=INFO"]
