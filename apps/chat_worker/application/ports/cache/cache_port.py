"""Cache Port - 캐싱 인터페이스 정의.

Clean Architecture 원칙:
- Application Layer는 Infrastructure(Redis)를 직접 의존하지 않음
- 이 Port를 통해 캐싱 기능을 추상화
- 테스트 시 Mock/InMemory 구현체로 교체 가능
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CachePort(ABC):
    """캐시 Port.

    기본 캐시 연산을 정의합니다.
    Redis, Memcached, InMemory 등 다양한 구현체로 교체 가능.

    사용 예시:
    - Intent 분류 결과 캐싱
    - RAG 검색 결과 캐싱
    - 사용자 프로필 캐싱
    """

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """캐시 조회.

        Args:
            key: 캐시 키

        Returns:
            캐시된 값 (없으면 None)
        """
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """캐시 저장.

        Args:
            key: 캐시 키
            value: 저장할 값
            ttl: TTL 초 (None이면 무기한)

        Returns:
            저장 성공 여부
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """캐시 삭제.

        Args:
            key: 캐시 키

        Returns:
            삭제 성공 여부
        """
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """캐시 존재 여부 확인.

        Args:
            key: 캐시 키

        Returns:
            존재 여부
        """
        raise NotImplementedError

    # === 선택적 메서드 (기본 구현 제공) ===

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """JSON 형태로 캐시 조회.

        Args:
            key: 캐시 키

        Returns:
            파싱된 dict (없거나 파싱 실패 시 None)
        """
        import json

        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None

    async def set_json(self, key: str, value: dict[str, Any], ttl: int | None = None) -> bool:
        """JSON 형태로 캐시 저장.

        Args:
            key: 캐시 키
            value: 저장할 dict
            ttl: TTL 초

        Returns:
            저장 성공 여부
        """
        import json

        try:
            json_str = json.dumps(value, ensure_ascii=False)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError):
            return False
