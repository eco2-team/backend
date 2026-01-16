"""Redis News Cache Implementation.

Redis Sorted Set을 사용한 뉴스 캐시 구현.

데이터 구조:
- news:feed:{category} → Sorted Set (score=timestamp, member=article_id)
- news:article:{article_id} → Hash (기사 상세)
"""

from __future__ import annotations

import logging
from datetime import datetime

from redis.asyncio import Redis

from info.application.ports.news_cache import NewsCachePort
from info.domain.entities import NewsArticle

logger = logging.getLogger(__name__)

# Redis 키 프리픽스
FEED_KEY_PREFIX = "news:feed:"
ARTICLE_KEY_PREFIX = "news:article:"
LOCK_KEY_PREFIX = "news:lock:"


class RedisNewsCache(NewsCachePort):
    """Redis 뉴스 캐시.

    Sorted Set을 사용하여 시간순 정렬 및 Cursor 페이지네이션 지원.
    """

    def __init__(self, redis: Redis, ttl: int = 3600):
        """초기화.

        Args:
            redis: Redis 클라이언트
            ttl: 기본 캐시 TTL (초)
        """
        self._redis = redis
        self._default_ttl = ttl

    def _feed_key(self, category: str) -> str:
        """피드 키 생성."""
        return f"{FEED_KEY_PREFIX}{category}"

    def _article_key(self, article_id: str) -> str:
        """기사 키 생성."""
        return f"{ARTICLE_KEY_PREFIX}{article_id}"

    def _lock_key(self, category: str) -> str:
        """락 키 생성."""
        return f"{LOCK_KEY_PREFIX}{category}"

    async def get_articles(
        self,
        category: str,
        cursor: int | None,
        limit: int,
    ) -> tuple[list[NewsArticle], int | None, bool]:
        """캐시에서 기사 조회.

        ZREVRANGEBYSCORE를 사용하여 cursor 이전의 기사들을 조회.

        Args:
            category: 카테고리
            cursor: 페이지네이션 커서 (Unix timestamp ms, None이면 최신부터)
            limit: 조회할 기사 수

        Returns:
            (기사 목록, 다음 커서, 더 있는지 여부)
        """
        feed_key = self._feed_key(category)

        # cursor가 None이면 +inf (최신부터)
        max_score = cursor - 1 if cursor else "+inf"

        # limit + 1로 조회해서 has_more 판단
        article_ids = await self._redis.zrevrangebyscore(
            feed_key,
            max=max_score,
            min="-inf",
            start=0,
            num=limit + 1,
        )

        if not article_ids:
            return [], None, False

        # has_more 판단
        has_more = len(article_ids) > limit
        if has_more:
            article_ids = article_ids[:limit]

        # 기사 상세 조회 (Pipeline으로 N+1 방지)
        articles: list[NewsArticle] = []
        if article_ids:
            pipe = self._redis.pipeline()
            for article_id in article_ids:
                pipe.hgetall(self._article_key(article_id))
            results = await pipe.execute()

            for article_data in results:
                if article_data:
                    article = self._deserialize_article(article_data)
                    if article:
                        articles.append(article)

        # 다음 커서 계산
        next_cursor = None
        if articles and has_more:
            next_cursor = articles[-1].published_at_ms

        return articles, next_cursor, has_more

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
        if not articles:
            return

        feed_key = self._feed_key(category)

        # Pipeline으로 일괄 저장
        pipe = self._redis.pipeline()

        # 기존 피드 삭제 (전체 교체)
        pipe.delete(feed_key)

        # Sorted Set에 추가
        feed_data = {article.id: article.published_at_ms for article in articles}
        if feed_data:
            pipe.zadd(feed_key, feed_data)
            pipe.expire(feed_key, ttl)

        # 기사 상세 저장
        for article in articles:
            article_key = self._article_key(article.id)
            article_data = self._serialize_article(article)
            pipe.hset(article_key, mapping=article_data)
            pipe.expire(article_key, ttl)

        await pipe.execute()

        logger.info(
            "Cached news articles",
            extra={"category": category, "count": len(articles), "ttl": ttl},
        )

    async def is_fresh(self, category: str) -> bool:
        """캐시가 유효한지 확인.

        Args:
            category: 카테고리

        Returns:
            캐시가 유효하면 True
        """
        feed_key = self._feed_key(category)
        ttl = await self._redis.ttl(feed_key)
        return ttl > 0

    async def get_total_count(self, category: str) -> int:
        """캐시된 기사 총 개수.

        Args:
            category: 카테고리

        Returns:
            기사 개수
        """
        feed_key = self._feed_key(category)
        return await self._redis.zcard(feed_key)

    async def get_ttl(self, category: str) -> int:
        """캐시 남은 TTL.

        Args:
            category: 카테고리

        Returns:
            남은 TTL (초), 없으면 0
        """
        feed_key = self._feed_key(category)
        ttl = await self._redis.ttl(feed_key)
        return max(0, ttl)

    def _serialize_article(self, article: NewsArticle) -> dict[str, str]:
        """NewsArticle을 Redis Hash로 직렬화."""
        return {
            "id": article.id,
            "title": article.title,
            "url": article.url,
            "snippet": article.snippet,
            "source": article.source,
            "source_name": article.source_name,
            "published_at": article.published_at.isoformat(),
            "thumbnail_url": article.thumbnail_url or "",
            "category": article.category or "",
            "source_icon_url": article.source_icon_url or "",
            "video_url": article.video_url or "",
            "keywords": ",".join(article.keywords) if article.keywords else "",
            "ai_tag": article.ai_tag or "",
        }

    def _deserialize_article(self, data: dict[str, str]) -> NewsArticle | None:
        """Redis Hash에서 NewsArticle로 역직렬화."""
        required_fields = ("id", "title", "url", "snippet", "source", "source_name", "published_at")

        # 필수 필드 확인
        missing = [f for f in required_fields if not data.get(f)]
        if missing:
            logger.warning("Missing required fields in cached article: %s", missing)
            return None

        try:
            # keywords 역직렬화
            keywords_str = data.get("keywords", "")
            keywords = tuple(keywords_str.split(",")) if keywords_str else None

            return NewsArticle(
                id=data["id"],
                title=data["title"],
                url=data["url"],
                snippet=data["snippet"],
                source=data["source"],
                source_name=data["source_name"],
                published_at=datetime.fromisoformat(data["published_at"]),
                thumbnail_url=data.get("thumbnail_url") or None,
                category=data.get("category") or None,
                source_icon_url=data.get("source_icon_url") or None,
                video_url=data.get("video_url") or None,
                keywords=keywords,
                ai_tag=data.get("ai_tag") or None,
            )
        except (ValueError, KeyError) as e:
            logger.warning("Failed to deserialize article: %s", e)
            return None

    async def acquire_refresh_lock(
        self,
        category: str,
        lock_ttl: int = 30,
    ) -> bool:
        """캐시 갱신 락 획득 (SETNX).

        Cache Stampede 방지를 위한 분산 락.
        동시에 여러 요청이 캐시를 갱신하는 것을 방지.

        Args:
            category: 카테고리
            lock_ttl: 락 TTL (초), 기본 30초

        Returns:
            락 획득 성공 여부
        """
        lock_key = self._lock_key(category)

        # SETNX + EXPIRE를 원자적으로 수행
        acquired = await self._redis.set(
            lock_key,
            "1",
            nx=True,  # SET if Not eXists
            ex=lock_ttl,  # Expire in seconds
        )

        if acquired:
            logger.debug("Acquired refresh lock", extra={"category": category})
        else:
            logger.debug("Failed to acquire refresh lock", extra={"category": category})

        return bool(acquired)

    async def release_refresh_lock(self, category: str) -> None:
        """캐시 갱신 락 해제.

        Args:
            category: 카테고리
        """
        lock_key = self._lock_key(category)
        await self._redis.delete(lock_key)
        logger.debug("Released refresh lock", extra={"category": category})

    async def close(self) -> None:
        """리소스 정리."""
        # Redis 클라이언트는 외부에서 관리
        pass
