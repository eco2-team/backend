"""Grant Default Character Task.

신규 사용자에게 기본 캐릭터(이코)를 지급합니다.
users API에서 캐릭터 목록이 빈 경우 이 태스크가 호출됩니다.

Flow:
    1. users API: 빈 리스트 감지 → character.grant_default 발행
    2. character_worker: 기본 캐릭터 정보 조회 (DB)
    3. character_worker: users.user_characters에 저장 (Eventual Consistency)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from domains.character.celery_app import celery_app
from domains.character.core.constants import DEFAULT_CHARACTER_NAME
from domains.character.database.session import get_db_engine

logger = logging.getLogger(__name__)

# 기본 캐릭터 소스
DEFAULT_CHARACTER_SOURCE = "default-onboard"


@celery_app.task(
    name="character.grant_default",
    bind=True,
    queue="character.grant_default",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def grant_default_character_task(self, user_id: str) -> dict[str, Any]:
    """기본 캐릭터(이코)를 사용자에게 지급합니다.

    Args:
        user_id: 사용자 ID (string)

    Returns:
        처리 결과
    """
    log_ctx = {
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "character.grant_default",
    }
    logger.info("Grant default character task started", extra=log_ctx)

    try:
        # 1. 기본 캐릭터 정보 조회 (character DB)
        default_char = _get_default_character()

        if default_char is None:
            logger.error("Default character not found", extra=log_ctx)
            return {"success": False, "error": "default_character_not_found"}

        # 2. users.user_characters에 저장
        result = _save_to_users_db(
            user_id=UUID(user_id),
            character_id=default_char["id"],
            character_code=default_char["code"],
            character_name=default_char["name"],
            character_type=default_char["type"],
            character_dialog=default_char["dialog"],
        )

        logger.info(
            "Grant default character completed",
            extra={
                **log_ctx,
                "character_name": default_char["name"],
                **result,
            },
        )
        return {"success": True, **result}

    except Exception:
        logger.exception("Grant default character failed", extra=log_ctx)
        raise


def _get_default_character() -> dict[str, Any] | None:
    """DB에서 기본 캐릭터를 조회합니다."""
    engine = get_db_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT id, code, name, type_label, dialog
                FROM character.characters
                WHERE name = :name
                LIMIT 1
            """
            ),
            {"name": DEFAULT_CHARACTER_NAME},
        )
        row = result.fetchone()

        if row is None:
            return None

        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "type": row.type_label,
            "dialog": row.dialog,
        }


def _save_to_users_db(
    user_id: UUID,
    character_id: UUID,
    character_code: str,
    character_name: str,
    character_type: str,
    character_dialog: str,
) -> dict[str, Any]:
    """users.user_characters 테이블에 저장합니다.

    동일 PostgreSQL 서버의 users DB에 접근합니다.
    ON CONFLICT DO NOTHING으로 중복 지급을 방지합니다.
    """
    import os

    from sqlalchemy import create_engine

    # character DB URL에서 users DB URL 생성
    # POSTGRES_HOST 환경변수 사용
    postgres_host = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_user = os.getenv("USERS_POSTGRES_USER", "users")
    postgres_password = os.getenv("USERS_POSTGRES_PASSWORD", "users")
    postgres_db = os.getenv("USERS_POSTGRES_DB", "users")

    users_db_url = (
        f"postgresql://{postgres_user}:{postgres_password}"
        f"@{postgres_host}:{postgres_port}/{postgres_db}"
    )

    engine = create_engine(users_db_url, pool_size=5, max_overflow=10)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO users.user_characters
                        (id, user_id, character_id, character_code, character_name,
                         character_type, character_dialog, source, status, acquired_at, updated_at)
                    VALUES
                        (:id, :user_id, :character_id, :character_code, :character_name,
                         :character_type, :character_dialog, :source, 'owned', NOW(), NOW())
                    ON CONFLICT (user_id, character_code) DO NOTHING
                """
                ),
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "character_id": character_id,
                    "character_code": character_code,
                    "character_name": character_name,
                    "character_type": character_type,
                    "character_dialog": character_dialog,
                    "source": DEFAULT_CHARACTER_SOURCE,
                },
            )
            conn.commit()

            inserted = result.rowcount > 0
            return {"inserted": inserted, "skipped": not inserted}
    finally:
        engine.dispose()
