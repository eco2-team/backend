"""Logging configuration."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """애플리케이션 로깅을 설정합니다."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # SQLAlchemy 로깅 레벨 조정
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
