"""Redis Cache Layer.

캐릭터 카탈로그 등 자주 조회되는 데이터를 캐싱합니다.

Cache Strategy:
    - Cache-aside pattern (Lazy loading)
    - TTL 기반 만료 (default: 5분)
    - Graceful degradation (Redis 실패 시 DB 직접 조회)

Usage:
    from domains.character.core.cache import get_cached, set_cached, invalidate_cache

    # 조회
    data = await get_cached("character:catalog")

    # 저장
    await set_cached("character:catalog", catalog_data, ttl=300)

    # 무효화
    await invalidate_cache("character:catalog")
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from domains.character.core.config import get_settings

if TYPE_CHECKING:
    from domains.character.core.config import Settings
    from domains.character.models.character import Character
    from domains.character.schemas.catalog import CharacterProfile

logger = logging.getLogger(__name__)

# Lazy-loaded Redis client
_redis_client = None

# Cache key prefixes
CACHE_PREFIX = "character:"
CATALOG_KEY = f"{CACHE_PREFIX}catalog"


async def _get_redis():
    """Lazy initialization of Redis client."""
    global _redis_client

    settings = get_settings()
    if not settings.cache_enabled:
        return None

    if _redis_client is None:
        try:
            import redis.asyncio as redis

            _redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Connection test
            await _redis_client.ping()
            logger.info(
                "Redis cache connected",
                extra={"url": settings.redis_url.split("@")[-1]},  # 비밀번호 제거
            )
        except Exception as e:
            logger.warning(
                "Redis cache unavailable, falling back to no-cache",
                extra={"error": str(e)},
            )
            _redis_client = None

    return _redis_client


async def get_cached(key: str) -> Any | None:
    """캐시에서 값 조회.

    Args:
        key: 캐시 키

    Returns:
        캐시된 값 또는 None (미스 또는 에러)
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return None

        data = await redis.get(key)
        if data is not None:
            logger.debug("Cache hit", extra={"key": key})
            return json.loads(data)

        logger.debug("Cache miss", extra={"key": key})
        return None

    except Exception as e:
        logger.warning("Cache get error", extra={"key": key, "error": str(e)})
        return None


async def set_cached(key: str, value: Any, ttl: int | None = None) -> bool:
    """캐시에 값 저장.

    Args:
        key: 캐시 키
        value: 저장할 값 (JSON 직렬화 가능해야 함)
        ttl: TTL 초 (None이면 설정의 기본값 사용)

    Returns:
        저장 성공 여부
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return False

        settings = get_settings()
        ttl = ttl or settings.cache_ttl_seconds

        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        logger.debug("Cache set", extra={"key": key, "ttl": ttl})
        return True

    except Exception as e:
        logger.warning("Cache set error", extra={"key": key, "error": str(e)})
        return False


async def invalidate_cache(key: str) -> bool:
    """캐시 무효화.

    Args:
        key: 캐시 키

    Returns:
        삭제 성공 여부
    """
    try:
        redis = await _get_redis()
        if redis is None:
            return False

        await redis.delete(key)
        logger.info("Cache invalidated", extra={"key": key})
        return True

    except Exception as e:
        logger.warning("Cache invalidate error", extra={"key": key, "error": str(e)})
        return False


async def invalidate_catalog_cache() -> bool:
    """카탈로그 캐시 무효화 (헬퍼 함수)."""
    return await invalidate_cache(CATALOG_KEY)


def _character_to_profile(char: "Character") -> "CharacterProfile":
    """Character 모델을 CharacterProfile로 변환."""
    from domains.character.schemas.catalog import CharacterProfile

    return CharacterProfile(
        name=char.name,
        type=str(char.type_label or "").strip(),
        dialog=str(char.dialog or char.description or "").strip(),
        match=str(char.match_label or "").strip() or None,
    )


async def _load_and_cache_catalog(settings: "Settings") -> bool:
    """DB에서 카탈로그를 로드하고 캐시에 저장."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from domains.character.repositories import CharacterRepository

    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            characters = await CharacterRepository(session).list_all()
            if not characters:
                logger.warning("Cache warmup: no characters found in database")
                return False

            profiles = [_character_to_profile(c) for c in characters]
            success = await set_cached(CATALOG_KEY, [p.model_dump() for p in profiles])

            if success:
                logger.info("Cache warmup completed", extra={"catalog_size": len(profiles)})
            else:
                logger.warning("Cache warmup: failed to set cache")
            return success
    finally:
        await engine.dispose()


async def warmup_catalog_cache() -> bool:
    """서버 시작 시 카탈로그 캐시 워밍업.

    Returns:
        워밍업 성공 여부

    Note:
        DB 연결 실패 시에도 서버 시작을 차단하지 않습니다.
    """
    settings = get_settings()
    if not settings.cache_enabled:
        logger.info("Cache warmup skipped (cache disabled)")
        return False

    try:
        return await _load_and_cache_catalog(settings)
    except Exception as e:
        logger.warning("Cache warmup failed (non-blocking)", extra={"error": str(e)})
        return False


async def close_cache() -> None:
    """Redis 연결 종료 (graceful shutdown)."""
    global _redis_client

    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            logger.info("Redis cache connection closed")
        except Exception as e:
            logger.warning("Error closing Redis connection", extra={"error": str(e)})
        finally:
            _redis_client = None


def reset_cache_client() -> None:
    """캐시 클라이언트 리셋 (테스트용).

    테스트 간 상태 격리를 위해 글로벌 클라이언트를 초기화합니다.
    프로덕션 코드에서는 사용하지 마세요.

    Usage:
        @pytest.fixture(autouse=True)
        def reset_cache():
            reset_cache_client()
            yield
            reset_cache_client()
    """
    global _redis_client
    _redis_client = None


def set_cache_client(client) -> None:
    """캐시 클라이언트 주입 (테스트용).

    테스트에서 mock Redis 클라이언트를 주입할 때 사용합니다.

    Args:
        client: Redis 클라이언트 또는 Mock 객체
    """
    global _redis_client
    _redis_client = client
