"""Dependency Injection Container.

애플리케이션 의존성을 관리합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.users_worker.setup.config import get_settings

if TYPE_CHECKING:
    from apps.users_worker.application.character.commands.save import (
        SaveCharactersCommand,
    )
    from apps.users_worker.infrastructure.persistence_postgres.character_store_sqla import (
        SqlaCharacterStore,
    )

logger = logging.getLogger(__name__)


class Container:
    """의존성 컨테이너.

    애플리케이션 의존성의 생명주기를 관리합니다.
    """

    def __init__(self) -> None:
        """Initialize."""
        self._engine = None
        self._session_factory = None
        self._session: AsyncSession | None = None
        self._character_store: "SqlaCharacterStore | None" = None
        self._save_characters_command: "SaveCharactersCommand | None" = None

    async def init(self) -> None:
        """컨테이너 초기화.

        DB 연결 등 리소스를 초기화합니다.
        """
        settings = get_settings()

        # DB 엔진 생성
        self._engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            echo=False,
        )

        # 세션 팩토리 생성
        self._session_factory = sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # 세션 생성
        self._session = self._session_factory()

        # 저장소 생성
        from apps.users_worker.infrastructure.persistence_postgres.character_store_sqla import (
            SqlaCharacterStore,
        )

        self._character_store = SqlaCharacterStore(self._session)

        # Command 생성
        from apps.users_worker.application.character.commands.save import (
            SaveCharactersCommand,
        )

        self._save_characters_command = SaveCharactersCommand(self._character_store)

        logger.debug("Container initialized")

    async def close(self) -> None:
        """컨테이너 종료.

        리소스를 정리합니다.
        """
        if self._session:
            await self._session.close()
            self._session = None

        if self._engine:
            await self._engine.dispose()
            self._engine = None

        logger.debug("Container closed")

    @property
    def character_store(self) -> "SqlaCharacterStore":
        """캐릭터 저장소."""
        if self._character_store is None:
            raise RuntimeError("Container not initialized")
        return self._character_store

    @property
    def save_characters_command(self) -> "SaveCharactersCommand":
        """캐릭터 저장 Command."""
        if self._save_characters_command is None:
            raise RuntimeError("Container not initialized")
        return self._save_characters_command
