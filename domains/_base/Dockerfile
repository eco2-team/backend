# ============================================================================
# Base Image for ECO2 Services
# API와 Worker가 공통으로 사용하는 의존성만 포함
# ============================================================================
FROM python:3.11-slim AS base

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 공통 패키지 설치
COPY domains/_base/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 사용자 생성
RUN useradd --create-home --shell /bin/bash appuser

# 런타임 이미지
FROM python:3.11-slim AS runtime

WORKDIR /app

# 런타임 의존성만 포함
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# 빌드된 패키지 복사
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

USER appuser
