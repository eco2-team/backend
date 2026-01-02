"""Database schema and table constants.

PostgreSQL 스키마 및 테이블 관련 상수들을 정의합니다.
"""

# =============================================================================
# Schema Names
# =============================================================================
USERS_SCHEMA = "users"
AUTH_SCHEMA = "auth"  # auth 도메인 테이블 읽기용 (cross-schema query)

# =============================================================================
# Table Names (users schema)
# =============================================================================
ACCOUNTS_TABLE = "accounts"
SOCIAL_ACCOUNTS_TABLE = "social_accounts"
USER_CHARACTERS_TABLE = "user_characters"

# =============================================================================
# Table Names (auth schema - read-only)
# =============================================================================
AUTH_USER_SOCIAL_ACCOUNTS_TABLE = "user_social_accounts"
