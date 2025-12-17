"""
Service Constants (Single Source of Truth)

정적 상수 정의 - 빌드 타임에 결정되며 환경변수로 변경되지 않음
"""

# Service Identity
SERVICE_NAME = "location-api"
SERVICE_VERSION = "1.0.7"

# Logging Constants (12-Factor App Compliance)
ENV_KEY_ENVIRONMENT = "ENVIRONMENT"
ENV_KEY_LOG_LEVEL = "LOG_LEVEL"
ENV_KEY_LOG_FORMAT = "LOG_FORMAT"

DEFAULT_ENVIRONMENT = "dev"
DEFAULT_LOG_LEVEL = "DEBUG"
DEFAULT_LOG_FORMAT = "json"

ECS_VERSION = "8.11.0"

EXCLUDED_LOG_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "created",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "exc_info",
        "exc_text",
        "thread",
        "threadName",
        "taskName",
        "message",
    }
)

# PII Masking Configuration (OWASP compliant, codebase-specific)
SENSITIVE_FIELD_PATTERNS = frozenset({"password", "secret", "token", "api_key", "authorization"})
MASK_PLACEHOLDER = "***REDACTED***"
MASK_PRESERVE_PREFIX = 4
MASK_PRESERVE_SUFFIX = 4
MASK_MIN_LENGTH = 10
