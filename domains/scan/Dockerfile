# ============================================================================
# Stage 1: Builder - 의존성 설치
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY domains/scan/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Stage 2: Runtime - 최소 이미지
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

# 애플리케이션 코드 복사
# - _shared: waste_pipeline 때문에 필요
# - character: gRPC proto 스펙 때문에 필요
COPY domains/_shared /app/domains/_shared
COPY domains/character /app/domains/character
COPY domains/scan /app/domains/scan

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["opentelemetry-instrument", "uvicorn", "domains.scan.main:app", "--host", "0.0.0.0", "--port", "8000"]
