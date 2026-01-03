"""Celery Application Setup."""

import logging

from celery import Celery
from celery.signals import worker_process_init

from apps.character_worker.setup.config import get_settings
from domains._shared.celery.config import CELERY_TASK_ROUTES

logger = logging.getLogger(__name__)
settings = get_settings()

# Celery 앱 생성
celery_app = Celery(
    "character_worker",
    broker=settings.broker_url,
    include=[
        "apps.character_worker.presentation.tasks.match_task",
        "apps.character_worker.presentation.tasks.ownership_task",
        "apps.character_worker.presentation.tasks.grant_default_task",
    ],
)

# Celery 설정
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes=CELERY_TASK_ROUTES,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@worker_process_init.connect
def init_worker_process(**kwargs):
    """Worker 프로세스 초기화.

    캐릭터 캐시를 DB에서 로드합니다.
    HPA 스케일아웃 시 각 Pod마다 실행됩니다.
    """
    logger.info("Initializing character worker process")

    from sqlalchemy import text

    from apps.character.domain.entities import Character
    from apps.character_worker.infrastructure.cache import get_character_cache
    from apps.character_worker.setup.database import sync_session_factory

    cache = get_character_cache()

    if cache.is_loaded():
        logger.info("Character cache already loaded")
        return

    # DB에서 캐릭터 로드
    try:
        with sync_session_factory() as session:
            result = session.execute(
                text("""
                    SELECT id, code, name, type_label, dialog, match_label
                    FROM character.characters
                    WHERE match_label IS NOT NULL
                """)
            )
            rows = result.fetchall()

            characters: dict[str, Character] = {}
            for row in rows:
                char = Character(
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    type_label=row.type_label,
                    dialog=row.dialog,
                    match_label=row.match_label,
                )
                if row.match_label:
                    characters[row.match_label] = char

            cache.load(characters, settings.default_character_code)
            logger.info(
                "Character cache initialized from DB",
                extra={"count": len(characters)},
            )

    except Exception:
        logger.exception("Failed to initialize character cache")
        raise
