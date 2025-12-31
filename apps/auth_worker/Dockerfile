# Auth Worker Dockerfile
# 블랙리스트 이벤트를 Redis에 저장하는 워커

FROM python:3.12-slim AS base

# 환경 변수
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────
# Builder stage
# ─────────────────────────────────────────────────────────────
FROM base AS builder

# pip 업그레이드
RUN pip install --no-cache-dir --upgrade pip

# 의존성 설치
COPY apps/auth_worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ─────────────────────────────────────────────────────────────
# Runtime stage
# ─────────────────────────────────────────────────────────────
FROM base AS runtime

# 비루트 사용자
RUN useradd --create-home --shell /bin/bash worker
USER worker

# Python 패키지 복사
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 애플리케이션 코드
COPY --chown=worker:worker apps/auth_worker /app/apps/auth_worker

# 헬스체크 (프로세스 존재 여부)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python -m apps.auth_worker.main" || exit 1

# 엔트리포인트
CMD ["python", "-m", "apps.auth_worker.main"]
