"""Character Worker Main Entry Point.

Celery Worker 실행 진입점입니다.
"""

import logging

from character_worker.setup.celery import celery_app
from character_worker.setup.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# OpenTelemetry 설정
if settings.otel_enabled:
    from character_worker.infrastructure.observability import setup_tracing

    setup_tracing(settings.service_name)

# Celery 앱 내보내기
app = celery_app

if __name__ == "__main__":
    celery_app.start()
