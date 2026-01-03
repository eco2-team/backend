"""Celery Default Character Publisher Implementation.

character.grant_default 큐로 이벤트를 발행합니다.
character_worker가 이벤트를 수신하여 기본 캐릭터를 지급합니다.
"""

import logging
from uuid import UUID

from celery import Celery

from apps.users.application.character.ports import DefaultCharacterPublisher

logger = logging.getLogger(__name__)


class CeleryDefaultCharacterPublisher(DefaultCharacterPublisher):
    """Celery 기반 기본 캐릭터 발행자.

    character.grant_default 태스크를 호출합니다.
    """

    def __init__(self, celery_app: Celery) -> None:
        """Initialize.

        Args:
            celery_app: Celery 앱 인스턴스
        """
        self._celery_app = celery_app

    def publish(self, user_id: UUID) -> None:
        """기본 캐릭터 지급 이벤트를 발행합니다."""
        try:
            self._celery_app.send_task(
                "character.grant_default",
                kwargs={"user_id": str(user_id)},
                queue="character.grant_default",
            )
            logger.info(
                "Default character grant event published",
                extra={"user_id": str(user_id)},
            )
        except Exception:
            logger.exception(
                "Failed to publish default character grant event",
                extra={"user_id": str(user_id)},
            )
            # Fire-and-forget: 실패해도 예외 전파 안 함
