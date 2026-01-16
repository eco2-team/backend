"""Naver News Search API Client.

네이버 검색 API를 사용한 뉴스 검색 클라이언트.

API 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md

사용량 제한:
- 일일 25,000건
- 요청당 최대 100건

인증:
- X-Naver-Client-Id: 애플리케이션 클라이언트 ID
- X-Naver-Client-Secret: 애플리케이션 클라이언트 Secret
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from info.application.ports.news_source import NewsSourcePort
from info.domain.entities import NewsArticle

logger = logging.getLogger(__name__)

NAVER_SEARCH_API_URL = "https://openapi.naver.com/v1/search/news.json"


class NaverNewsClient(NewsSourcePort):
    """네이버 뉴스 검색 클라이언트.

    네이버 검색 API의 뉴스 검색 기능을 사용합니다.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient,
    ):
        """초기화.

        Args:
            client_id: 네이버 API 클라이언트 ID
            client_secret: 네이버 API 클라이언트 Secret
            http_client: HTTP 클라이언트 (외부 주입)
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = http_client
        self._headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }

    @property
    def source_name(self) -> str:
        """소스 식별자."""
        return "naver"

    async def fetch_news(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[NewsArticle]:
        """뉴스 검색.

        Args:
            query: 검색어
            max_results: 최대 결과 수 (최대 100)

        Returns:
            뉴스 기사 목록
        """
        # 네이버 API는 최대 100개까지 지원
        display = min(max_results, 100)

        try:
            response = await self._client.get(
                NAVER_SEARCH_API_URL,
                params={
                    "query": query,
                    "display": display,
                    "sort": "date",  # 최신순
                },
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()

            articles = []
            for item in data.get("items", []):
                article = self._parse_item(item)
                if article:
                    articles.append(article)

            logger.info(
                "Naver news search completed",
                extra={
                    "query": query,
                    "total": data.get("total", 0),
                    "fetched": len(articles),
                },
            )

            return articles

        except httpx.HTTPStatusError as e:
            logger.error(
                "Naver API HTTP error",
                extra={"status": e.response.status_code, "query": query},
            )
            return []
        except Exception as e:
            logger.error(
                "Naver news search failed",
                extra={"error": str(e), "query": query},
            )
            return []

    def _parse_item(self, item: dict[str, Any]) -> NewsArticle | None:
        """API 응답 아이템을 NewsArticle로 변환.

        Args:
            item: 네이버 API 응답 아이템

        Returns:
            NewsArticle 또는 None (파싱 실패 시)
        """
        try:
            # HTML 태그 제거
            title = self._strip_html(item.get("title", ""))
            description = self._strip_html(item.get("description", ""))
            link = item.get("link", "")
            original_link = item.get("originallink", link)

            # pubDate 파싱 (예: "Tue, 14 Jan 2026 10:30:00 +0900")
            pub_date_str = item.get("pubDate", "")
            published_at = self._parse_date(pub_date_str)

            if not title or not link:
                return None

            # ID 생성 (URL 해시)
            article_id = f"naver_{hashlib.md5(original_link.encode()).hexdigest()[:12]}"

            return NewsArticle(
                id=article_id,
                title=title,
                url=original_link,
                snippet=description,
                source="naver",
                source_name=self._extract_source_name(link),
                published_at=published_at,
                thumbnail_url=None,  # 네이버 뉴스 API는 썸네일 미제공
            )

        except Exception as e:
            logger.warning("Failed to parse Naver news item: %s", e)
            return None

    def _strip_html(self, text: str) -> str:
        """HTML 태그 제거."""
        # <b>, </b> 등 HTML 태그 제거
        clean = re.sub(r"<[^>]+>", "", text)
        # HTML 엔티티 변환
        clean = clean.replace("&quot;", '"')
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = clean.replace("&apos;", "'")
        return clean.strip()

    def _parse_date(self, date_str: str) -> datetime:
        """날짜 문자열 파싱.

        Args:
            date_str: 날짜 문자열 (RFC 2822 형식)

        Returns:
            datetime 객체 (timezone-aware)
        """
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            logger.debug("Failed to parse date: %s, using current time", date_str)
            from datetime import timezone

            return datetime.now(timezone.utc)

    def _extract_source_name(self, url: str) -> str:
        """URL에서 언론사 이름 추출.

        Args:
            url: 기사 URL

        Returns:
            언론사 이름
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")

            # 알려진 언론사 매핑
            source_map = {
                "n.news.naver.com": "네이버뉴스",
                "news.naver.com": "네이버뉴스",
                "hani.co.kr": "한겨레",
                "khan.co.kr": "경향신문",
                "chosun.com": "조선일보",
                "donga.com": "동아일보",
                "joins.com": "중앙일보",
                "mk.co.kr": "매일경제",
                "hankyung.com": "한국경제",
                "yna.co.kr": "연합뉴스",
                "ytn.co.kr": "YTN",
                "sbs.co.kr": "SBS",
                "kbs.co.kr": "KBS",
                "mbc.co.kr": "MBC",
            }

            for pattern, name in source_map.items():
                if pattern in domain:
                    return name

            return domain

        except Exception:
            return "Unknown"

    async def close(self) -> None:
        """리소스 정리 (클라이언트는 외부에서 관리)."""
        pass


# ============================================================
# Sync Version (for gevent/Celery worker)
# ============================================================
class NaverNewsClientSync:
    """네이버 뉴스 검색 클라이언트 (동기 버전).

    gevent 몽키패칭 호환을 위한 동기 HTTP 클라이언트 사용.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http_client: httpx.Client,
    ):
        """초기화."""
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = http_client
        self._headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }

    @property
    def source_name(self) -> str:
        """소스 식별자."""
        return "naver"

    def fetch_news(
        self,
        query: str,
        max_results: int = 50,
    ) -> list[NewsArticle]:
        """뉴스 검색 (동기)."""
        display = min(max_results, 100)

        try:
            response = self._client.get(
                NAVER_SEARCH_API_URL,
                params={
                    "query": query,
                    "display": display,
                    "sort": "date",
                },
                headers=self._headers,
            )
            response.raise_for_status()
            data = response.json()

            articles = []
            for item in data.get("items", []):
                article = self._parse_item(item)
                if article:
                    articles.append(article)

            logger.info(
                "Naver news search completed",
                extra={
                    "query": query,
                    "total": data.get("total", 0),
                    "fetched": len(articles),
                },
            )

            return articles

        except httpx.HTTPStatusError as e:
            logger.error(
                "Naver API HTTP error",
                extra={"status": e.response.status_code, "query": query},
            )
            return []
        except Exception as e:
            logger.error(
                "Naver news search failed",
                extra={"error": str(e), "query": query},
            )
            return []

    def _parse_item(self, item: dict[str, Any]) -> NewsArticle | None:
        """API 응답 아이템을 NewsArticle로 변환."""
        try:
            title = self._strip_html(item.get("title", ""))
            description = self._strip_html(item.get("description", ""))
            link = item.get("link", "")
            original_link = item.get("originallink", link)
            pub_date_str = item.get("pubDate", "")
            published_at = self._parse_date(pub_date_str)

            if not title or not link:
                return None

            article_id = f"naver_{hashlib.md5(original_link.encode()).hexdigest()[:12]}"

            return NewsArticle(
                id=article_id,
                title=title,
                url=original_link,
                snippet=description,
                source="naver",
                source_name=self._extract_source_name(link),
                published_at=published_at,
                thumbnail_url=None,
            )

        except Exception as e:
            logger.warning("Failed to parse Naver news item: %s", e)
            return None

    def _strip_html(self, text: str) -> str:
        """HTML 태그 제거."""
        clean = re.sub(r"<[^>]+>", "", text)
        clean = clean.replace("&quot;", '"')
        clean = clean.replace("&amp;", "&")
        clean = clean.replace("&lt;", "<")
        clean = clean.replace("&gt;", ">")
        clean = clean.replace("&apos;", "'")
        return clean.strip()

    def _parse_date(self, date_str: str) -> datetime:
        """날짜 문자열 파싱."""
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            from datetime import timezone
            return datetime.now(timezone.utc)

    def _extract_source_name(self, url: str) -> str:
        """URL에서 언론사 이름 추출."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            source_map = {
                "n.news.naver.com": "네이버뉴스",
                "news.naver.com": "네이버뉴스",
                "hani.co.kr": "한겨레",
                "khan.co.kr": "경향신문",
                "chosun.com": "조선일보",
                "donga.com": "동아일보",
                "joins.com": "중앙일보",
                "mk.co.kr": "매일경제",
                "hankyung.com": "한국경제",
                "yna.co.kr": "연합뉴스",
            }
            for pattern, name in source_map.items():
                if pattern in domain:
                    return name
            return domain
        except Exception:
            return "Unknown"
