# apps/scan_worker/Dockerfile
# Scan Worker - Clean Architecture

FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements 먼저 복사 (캐시 활용)
COPY apps/scan_worker/requirements.txt /app/apps/scan_worker/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/scan_worker/requirements.txt

# 공유 모듈 복사
COPY domains/_shared /app/domains/_shared

# apps/scan (도메인 공유)
COPY apps/scan/domain /app/apps/scan/domain

# Worker 코드 복사
COPY apps/scan_worker /app/apps/scan_worker

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Celery Worker 실행
CMD ["celery", "-A", "apps.scan_worker.main", "worker", \
     "--pool=gevent", "--concurrency=100", \
     "-Q", "scan.vision,scan.rule,scan.answer,scan.reward", \
     "--loglevel=INFO"]

# Scan Worker - Clean Architecture

FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements 먼저 복사 (캐시 활용)
COPY apps/scan_worker/requirements.txt /app/apps/scan_worker/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/scan_worker/requirements.txt

# 공유 모듈 복사
COPY domains/_shared /app/domains/_shared

# apps/scan (도메인 공유)
COPY apps/scan/domain /app/apps/scan/domain

# Worker 코드 복사
COPY apps/scan_worker /app/apps/scan_worker

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Celery Worker 실행
CMD ["celery", "-A", "apps.scan_worker.main", "worker", \
     "--pool=gevent", "--concurrency=100", \
     "-Q", "scan.vision,scan.rule,scan.answer,scan.reward", \
     "--loglevel=INFO"]
