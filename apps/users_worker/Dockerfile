# ============================================================================
# Users Worker Dockerfile
# Celery Worker 전용 이미지
# 처리 큐: users.character (유저 캐릭터 DB 동기화)
# ============================================================================
FROM docker.io/mng990/eco2:base-dev-latest

WORKDIR /app

# 애플리케이션 코드 복사
COPY apps/users_worker /app/apps/users_worker

USER appuser

# Health check용 procps 설치 (pgrep)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends procps && \
    rm -rf /var/lib/apt/lists/*
USER appuser

# Celery Worker 실행
CMD ["celery", "-A", "apps.users_worker.main", "worker", "-E", "--loglevel=info", "-Q", "users.character", "-c", "2"]
