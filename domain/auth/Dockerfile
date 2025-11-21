FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY domain/auth/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 공유 모듈 복사
COPY domain/_shared /app/domain/_shared

# Auth 서비스 코드 복사
COPY domain/auth /app/domain/auth

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

EXPOSE 8000

# 애플리케이션 서버 시작
CMD ["uvicorn", "domain.auth.main:app", "--host", "0.0.0.0", "--port", "8000"]
