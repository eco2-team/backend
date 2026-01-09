"""
Structured Logging Configuration (ECS-based)

Log Collection Protocol:
- Fluent Bit → Elasticsearch: HTTP (9200)
- OpenTelemetry → Jaeger: gRPC OTLP (4317)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from images.core.constants import (
    DEFAULT_ENVIRONMENT,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    ECS_VERSION,
    ENV_KEY_ENVIRONMENT,
    ENV_KEY_LOG_FORMAT,
    ENV_KEY_LOG_LEVEL,
    EXCLUDED_LOG_RECORD_ATTRS,
    MASK_MIN_LENGTH,
    MASK_PLACEHOLDER,
    MASK_PRESERVE_PREFIX,
    MASK_PRESERVE_SUFFIX,
    SENSITIVE_FIELD_PATTERNS,
    SERVICE_NAME,
    SERVICE_VERSION,
)

try:
    from opentelemetry import trace

    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_FIELD_PATTERNS)


def _mask_value(value: Any) -> str:
    if value is None:
        return MASK_PLACEHOLDER
    str_value = str(value)
    if len(str_value) <= MASK_MIN_LENGTH:
        return MASK_PLACEHOLDER
    return f"{str_value[:MASK_PRESERVE_PREFIX]}...{str_value[-MASK_PRESERVE_SUFFIX:]}"


def mask_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data
    result = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            result[key] = _mask_value(value)
        elif isinstance(value, dict):
            result[key] = mask_sensitive_data(value)
        elif isinstance(value, list):
            result[key] = [
                mask_sensitive_data(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            result[key] = value
    return result


class ECSJsonFormatter(logging.Formatter):
    """Elastic Common Schema (ECS) 기반 JSON 포매터"""

    def __init__(
        self,
        service_name: str = SERVICE_NAME,
        service_version: str = SERVICE_VERSION,
        environment: str = DEFAULT_ENVIRONMENT,
    ):
        super().__init__()
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "@timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "message": record.getMessage(),
            "log.level": record.levelname.lower(),
            "log.logger": record.name,
            "ecs.version": ECS_VERSION,
            "service.name": self.service_name,
            "service.version": self.service_version,
            "service.environment": self.environment,
        }

        if HAS_OPENTELEMETRY:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                log_obj["trace.id"] = format(ctx.trace_id, "032x")
                log_obj["span.id"] = format(ctx.span_id, "016x")

        if record.exc_info:
            log_obj["error.type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            log_obj["error.message"] = str(record.exc_info[1]) if record.exc_info[1] else None
            log_obj["error.stack_trace"] = self.formatException(record.exc_info)

        extra_fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in EXCLUDED_LOG_RECORD_ATTRS
        }
        if extra_fields:
            log_obj["labels"] = mask_sensitive_data(extra_fields)

        return json.dumps(log_obj, ensure_ascii=False, default=str)


def configure_logging(
    service_name: str = SERVICE_NAME,
    service_version: str = SERVICE_VERSION,
    log_level: str | None = None,
    json_format: bool | None = None,
) -> None:
    """애플리케이션 로깅 설정"""
    environment = os.getenv(ENV_KEY_ENVIRONMENT, DEFAULT_ENVIRONMENT)
    level = log_level or os.getenv(ENV_KEY_LOG_LEVEL, DEFAULT_LOG_LEVEL)
    use_json = (
        json_format
        if json_format is not None
        else os.getenv(ENV_KEY_LOG_FORMAT, DEFAULT_LOG_FORMAT) == "json"
    )

    numeric_level = getattr(logging, level.upper(), logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if use_json:
        handler.setFormatter(
            ECSJsonFormatter(
                service_name=service_name,
                service_version=service_version,
                environment=environment,
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    for logger_name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "asyncio",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
