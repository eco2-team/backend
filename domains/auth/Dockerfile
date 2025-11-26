FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY domains/auth/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 공유 모듈 복사
COPY domains/_shared /app/domains/_shared

# Auth 서비스 코드 복사
COPY domains/auth /app/domains/auth

EXPOSE 8000

# 애플리케이션 서버 시작
CMD ["uvicorn", "domains.auth.main:app", "--host", "0.0.0.0", "--port", "8000"]
