"""NewsData.io API Client.

NewsData.io API를 사용한 글로벌 뉴스 검색 클라이언트.

API 문서: https://newsdata.io/documentation

사용량 제한 (무료):
- 일일 200 크레딧
- 요청당 최대 10개 결과

인증:
- apikey: API 키 (쿼리 파라미터)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

import httpx

from info.application.ports.news_source import NewsSourcePort
from info.domain.entities import NewsArticle

logger = logging.getLogger(__name__)

NEWSDATA_API_URL = "https://newsdata.io/api/1/latest"


class NewsDataClient(NewsSourcePort):
    """NewsData.io 뉴스 검색 클라이언트.

    206개국, 89개 언어 지원.
    환경/에너지/AI 관련 글로벌 뉴스 검색에 사용.
    """

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
    ):
        """초기화.

        Args:
            api_key: NewsData.io API 키
            http_client: HTTP 클라이언트 (외부 주입)
        """
        self._api_key = api_key
        self._client = http_client

    @property
    def source_name(self) -> str:
        """소스 식별자."""
        return "newsdata"

    async def fetch_news(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[NewsArticle]:
        """뉴스 검색.

        Args:
            query: 검색어
            max_results: 최대 결과 수

        Returns:
            뉴스 기사 목록
        """
        # NewsData.io는 무료 플랜에서 한 번에 최대 10개
        # 여러 번 호출해서 max_results까지 수집
        all_articles: list[NewsArticle] = []
        next_page: str | None = None

        try:
            while len(all_articles) < max_results:
                params: dict[str, Any] = {
                    "apikey": self._api_key,
                    "q": query,
                    # language 필터 제거: NewsData.io는 한국어 기사가 적음
                    # country=kr로 한국 소스 기사를 영어로 가져옴
                }

                if next_page:
                    params["page"] = next_page

                response = await self._client.get(NEWSDATA_API_URL, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    logger.warning(
                        "NewsData API returned non-success status",
                        extra={"status": data.get("status")},
                    )
                    break

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    article = self._parse_item(item)
                    if article:
                        all_articles.append(article)

                # 다음 페이지
                next_page = data.get("nextPage")
                if not next_page:
                    break

                # 무료 플랜 크레딧 절약을 위해 1회만 호출
                break

            logger.info(
                "NewsData.io search completed",
                extra={
                    "query": query,
                    "fetched": len(all_articles),
                },
            )

            return all_articles[:max_results]

        except httpx.HTTPStatusError as e:
            logger.error(
                "NewsData API HTTP error",
                extra={"status": e.response.status_code, "query": query},
            )
            return []
        except Exception as e:
            logger.error(
                "NewsData.io search failed",
                extra={"error": str(e), "query": query},
            )
            return []

    def _parse_item(self, item: dict[str, Any]) -> NewsArticle | None:
        """API 응답 아이템을 NewsArticle로 변환.

        Args:
            item: NewsData.io API 응답 아이템

        Returns:
            NewsArticle 또는 None (파싱 실패 시)
        """
        try:
            title = item.get("title", "")
            link = item.get("link", "")
            description = item.get("description") or item.get("content") or ""
            source_name = item.get("source_name") or item.get("source_id", "Unknown")

            # 이미지 및 미디어 필드
            image_url = item.get("image_url")
            source_icon_url = item.get("source_icon")
            video_url = item.get("video_url")

            # AI 분석 필드
            keywords = item.get("keywords")  # list or None
            ai_tag = item.get("ai_tag")
            category = item.get("category")  # NewsData 자체 카테고리

            # pubDate 파싱 (ISO 형식: "2026-01-16 10:30:00")
            pub_date_str = item.get("pubDate", "")
            published_at = self._parse_date(pub_date_str)

            if not title or not link:
                return None

            # ID 생성 (article_id 또는 URL 해시)
            article_id = item.get("article_id")
            if not article_id:
                article_id = f"newsdata_{hashlib.md5(link.encode()).hexdigest()[:12]}"

            # description 길이 제한
            if len(description) > 500:
                description = description[:497] + "..."

            # keywords를 tuple로 변환 (frozen dataclass 호환)
            keywords_tuple = tuple(keywords) if keywords else None

            return NewsArticle(
                id=article_id,
                title=title,
                url=link,
                snippet=description,
                source="newsdata",
                source_name=source_name,
                published_at=published_at,
                thumbnail_url=image_url,
                source_icon_url=source_icon_url,
                video_url=video_url,
                keywords=keywords_tuple,
                ai_tag=ai_tag,
                category=category,  # NewsData 자체 카테고리 우선 사용
            )

        except Exception as e:
            logger.warning("Failed to parse NewsData.io item: %s", e)
            return None

    def _parse_date(self, date_str: str) -> datetime:
        """날짜 문자열 파싱.

        Args:
            date_str: 날짜 문자열 (ISO 형식)

        Returns:
            datetime 객체 (timezone-aware)
        """
        from datetime import timezone

        try:
            # "2026-01-16 10:30:00" 형식
            dt = datetime.fromisoformat(date_str.replace(" ", "T"))
            # naive datetime이면 UTC로 설정
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            try:
                # ISO 8601 형식
                dt = datetime.fromisoformat(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                logger.debug("Failed to parse date: %s, using current time", date_str)
                return datetime.now(timezone.utc)

    async def close(self) -> None:
        """리소스 정리 (클라이언트는 외부에서 관리)."""
        pass
