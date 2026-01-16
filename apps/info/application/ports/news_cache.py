"""News Cache Port.

뉴스 캐시 추상화 인터페이스.
Redis 등 다양한 캐시 저장소 어댑터 구현 가능.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle


class NewsCachePort(ABC):
    """뉴스 캐시 포트.

    뉴스 기사 캐싱을 위한 인터페이스.
    Cursor 기반 페이지네이션 지원.
    """

    @abstractmethod
    async def get_articles(
        self,
        category: str,
        cursor: int | None,
        limit: int,
    ) -> tuple[list[NewsArticle], int | None, bool]:
        """캐시에서 기사 조회.

        Args:
            category: 카테고리 ("all", "environment", "energy", "ai")
            cursor: 페이지네이션 커서 (Unix timestamp ms, None이면 최신부터)
            limit: 조회할 기사 수

        Returns:
            (기사 목록, 다음 커서, 더 있는지 여부)
        """
        pass

    @abstractmethod
    async def set_articles(
        self,
        category: str,
        articles: list[NewsArticle],
        ttl: int = 3600,
    ) -> None:
        """캐시에 기사 저장.

        Args:
            category: 카테고리
            articles: 저장할 기사 목록
            ttl: TTL (초)
        """
        pass

    @abstractmethod
    async def is_fresh(self, category: str) -> bool:
        """캐시가 유효한지 확인.

        Args:
            category: 카테고리

        Returns:
            캐시가 유효하면 True
        """
        pass

    @abstractmethod
    async def get_total_count(self, category: str) -> int:
        """캐시된 기사 총 개수.

        Args:
            category: 카테고리

        Returns:
            기사 개수
        """
        pass

    @abstractmethod
    async def get_ttl(self, category: str) -> int:
        """캐시 남은 TTL.

        Args:
            category: 카테고리

        Returns:
            남은 TTL (초), 없으면 0
        """
        pass

    async def acquire_refresh_lock(
        self,
        category: str,
        lock_ttl: int = 30,
    ) -> bool:
        """캐시 갱신 락 획득.

        Cache Stampede 방지를 위한 분산 락.
        동시에 여러 요청이 캐시를 갱신하는 것을 방지.

        Args:
            category: 카테고리
            lock_ttl: 락 TTL (초), 기본 30초

        Returns:
            락 획득 성공 여부
        """
        return True  # 기본 구현은 항상 성공

    async def release_refresh_lock(self, category: str) -> None:
        """캐시 갱신 락 해제.

        Args:
            category: 카테고리
        """
        pass  # 기본 구현은 아무것도 안함

    async def close(self) -> None:
        """리소스 정리 (optional)."""
        pass
