"""Logging Configuration.

ECS 호환 JSON 로깅 설정입니다.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import ecs_logging

from apps.auth_worker.setup.config import get_settings


def setup_logging() -> None:
    """로깅 설정."""
    settings = get_settings()

    # ECS JSON 포맷터
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ecs_logging.StdlibFormatter())

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # 서비스 메타데이터 추가
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **kwargs)
        record.service = {
            "name": settings.service_name,
            "version": settings.service_version,
            "environment": settings.environment,
        }
        return record

    logging.setLogRecordFactory(record_factory)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)
