# apps/scan/Dockerfile
# Clean Architecture Scan API

FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements 먼저 복사 (캐시 활용)
COPY apps/scan/requirements.txt /app/apps/scan/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/scan/requirements.txt

# 공유 모듈 복사
COPY domains/_shared /app/domains/_shared

# 앱 코드 복사
COPY apps/scan /app/apps/scan

# 환경 변수
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 포트
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 실행
CMD ["uvicorn", "apps.scan.main:app", "--host", "0.0.0.0", "--port", "8000"]
