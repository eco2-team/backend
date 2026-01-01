# ============================================================================
# Auth Relay Worker Dockerfile
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY apps/auth_relay/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================================
# Runtime
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local
COPY apps/auth_relay /app/apps/auth_relay

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER appuser

# Relay Worker 시작
CMD ["python", "-m", "apps.auth_relay.main"]
