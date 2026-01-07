"""Users Worker Entry Point.

Celery Worker를 시작합니다.

Usage:
    celery -A users_worker.main worker -Q users.save_character -c 2 --loglevel=info
"""

from users_worker.setup.celery import celery_app
from users_worker.setup.logging import setup_logging

# 로깅 설정
setup_logging()

# Celery 앱 내보내기 (celery CLI에서 사용)
app = celery_app

if __name__ == "__main__":
    celery_app.start()
