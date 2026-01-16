"""Open Graph Image Extractor.

기사 URL에서 og:image 메타태그를 추출하여 썸네일을 가져오는 유틸리티.
이미지가 없는 뉴스 소스(네이버 등)에서 사용.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from info.domain.entities import NewsArticle

logger = logging.getLogger(__name__)

# OG 이미지 추출 정규식
OG_IMAGE_PATTERN = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?property=["\']og:image["\']\s+(?:[^>]*?\s+)?content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
OG_IMAGE_PATTERN_ALT = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?content=["\']([^"\']+)["\']\s+(?:[^>]*?\s+)?property=["\']og:image["\']',
    re.IGNORECASE,
)


class OGImageExtractor:
    """Open Graph 이미지 추출기.

    기사 URL에서 og:image 메타태그를 추출합니다.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        timeout: float = 5.0,
        max_concurrent: int = 10,
    ):
        """초기화.

        Args:
            http_client: HTTP 클라이언트
            timeout: 요청 타임아웃 (초)
            max_concurrent: 동시 요청 수 제한
        """
        self._client = http_client
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_image_url(self, url: str) -> str | None:
        """URL에서 og:image 추출.

        Args:
            url: 기사 URL

        Returns:
            og:image URL 또는 None
        """
        async with self._semaphore:
            try:
                response = await self._client.get(
                    url,
                    timeout=self._timeout,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; Eco2Bot/1.0)",
                    },
                )

                if response.status_code != 200:
                    return None

                # HTML 앞부분만 파싱 (head 태그 내 메타태그)
                html = response.text[:10000]

                # og:image 추출
                match = OG_IMAGE_PATTERN.search(html)
                if not match:
                    match = OG_IMAGE_PATTERN_ALT.search(html)

                if match:
                    image_url = match.group(1)
                    # 상대 경로 처리
                    if image_url.startswith("//"):
                        image_url = f"https:{image_url}"
                    elif image_url.startswith("/"):
                        from urllib.parse import urlparse

                        parsed = urlparse(url)
                        image_url = f"{parsed.scheme}://{parsed.netloc}{image_url}"

                    logger.debug("Extracted og:image", extra={"url": url, "image": image_url})
                    return image_url

                return None

            except httpx.TimeoutException:
                logger.debug("Timeout extracting og:image", extra={"url": url})
                return None
            except Exception as e:
                logger.debug("Failed to extract og:image: %s", e, extra={"url": url})
                return None

    async def enrich_articles_with_images(
        self,
        articles: list[NewsArticle],
    ) -> list[NewsArticle]:
        """이미지가 없는 기사들에 og:image 추가.

        Args:
            articles: 뉴스 기사 목록

        Returns:
            이미지가 보강된 기사 목록
        """
        from dataclasses import replace

        # 이미지가 없는 기사만 추출
        articles_without_image = [(i, a) for i, a in enumerate(articles) if not a.thumbnail_url]

        if not articles_without_image:
            return articles

        logger.info(
            "Enriching articles with og:image",
            extra={"count": len(articles_without_image)},
        )

        # 병렬로 og:image 추출
        tasks = [self.extract_image_url(article.url) for _, article in articles_without_image]
        results = await asyncio.gather(*tasks)

        # 결과 병합
        enriched = list(articles)
        enriched_count = 0

        for (idx, article), image_url in zip(articles_without_image, results):
            if image_url:
                enriched[idx] = replace(article, thumbnail_url=image_url)
                enriched_count += 1

        logger.info(
            "Enriched articles with og:image",
            extra={
                "total": len(articles_without_image),
                "enriched": enriched_count,
            },
        )

        return enriched
