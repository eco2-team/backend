"""Logging Setup.

구조화된 JSON 로깅을 설정합니다.
"""

from __future__ import annotations

import logging
import sys

from apps.users_worker.setup.config import get_settings


def setup_logging() -> None:
    """로깅 설정."""
    settings = get_settings()

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))

    # 핸들러가 이미 있으면 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 새 핸들러 추가
    handler = logging.StreamHandler(sys.stdout)

    if settings.log_format == "json":
        try:
            import ecs_logging

            handler.setFormatter(ecs_logging.StdlibFormatter())
        except ImportError:
            # ecs_logging이 없으면 기본 포맷 사용
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root_logger.addHandler(handler)

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("kombu").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # 서비스 메타데이터 추가
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = settings.service_name
        record.environment = settings.environment
        return record

    logging.setLogRecordFactory(record_factory)
