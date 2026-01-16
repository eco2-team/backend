# apps/info/Dockerfile
# Clean Architecture Info API (뉴스 정보 서비스)
# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY apps/info/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# 런타임 의존성만 설치 (gcc 제외)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Builder에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

# 앱 코드만 복사 (완전 독립)
COPY apps/info /app/info

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 보안: non-root 사용자로 실행
USER appuser

EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/info/health || exit 1

# 실행
CMD ["uvicorn", "info.main:app", "--host", "0.0.0.0", "--port", "8000"]
