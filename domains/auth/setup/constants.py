"""
Service Constants (Single Source of Truth)

정적 상수 정의 - 빌드 타임에 결정되며 환경변수로 변경되지 않음
"""

# =============================================================================
# Service Identity
# =============================================================================
SERVICE_NAME = "auth-api"
SERVICE_VERSION = "1.0.7"

# =============================================================================
# Logging Constants (12-Factor App Compliance)
# =============================================================================
# Environment variable keys
ENV_KEY_ENVIRONMENT = "ENVIRONMENT"
ENV_KEY_LOG_LEVEL = "LOG_LEVEL"
ENV_KEY_LOG_FORMAT = "LOG_FORMAT"

# Default values (DEBUG for development phase)
DEFAULT_ENVIRONMENT = "dev"
DEFAULT_LOG_LEVEL = "DEBUG"
DEFAULT_LOG_FORMAT = "json"

# ECS (Elastic Common Schema) version
ECS_VERSION = "8.11.0"

# LogRecord attributes to exclude from extra fields
# Reference: https://docs.python.org/3/library/logging.html#logrecord-attributes
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

# =============================================================================
# PII Masking Configuration
# =============================================================================
# Sensitive field names (case-insensitive substring matching)
# Only include patterns actually used in this codebase
# Reference: OWASP Logging Cheat Sheet
SENSITIVE_FIELD_PATTERNS = frozenset(
    {
        "password",  # Key loading, user credentials
        "secret",  # jwt_secret_key, client_secret
        "token",  # JWT, OAuth tokens (covers access_token, refresh_token)
        "api_key",  # External API keys (OpenAI, etc.)
        "authorization",  # HTTP Authorization header
    }
)

# Masking placeholder
MASK_PLACEHOLDER = "***REDACTED***"

# Partial masking settings
MASK_PRESERVE_PREFIX = 4  # Show first N characters for tokens
MASK_PRESERVE_SUFFIX = 4  # Show last N characters for tokens
MASK_MIN_LENGTH = 10  # Minimum length to apply partial masking
