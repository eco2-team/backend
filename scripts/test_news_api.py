#!/usr/bin/env python3
"""Info Service API 테스트 스크립트.

로컬에서 뉴스 API를 테스트합니다.
Redis 없이 외부 API만 테스트합니다.

Usage:
    python scripts/test_news_api.py
"""

import asyncio
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx


async def test_naver_api():
    """네이버 뉴스 API 테스트."""
    print("\n" + "=" * 60)
    print("🔍 네이버 뉴스 API 테스트")
    print("=" * 60)

    client_id = os.getenv("INFO_NAVER_CLIENT_ID")
    client_secret = os.getenv("INFO_NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ 네이버 API 키가 설정되지 않았습니다.")
        print("   INFO_NAVER_CLIENT_ID, INFO_NAVER_CLIENT_SECRET 환경변수를 설정하세요.")
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": "환경 분리배출", "display": 5, "sort": "date"},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 성공! 총 {data.get('total', 0)}건 중 {len(data.get('items', []))}건 조회")
            print()

            for i, item in enumerate(data.get("items", [])[:3], 1):
                title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                print(f"  [{i}] {title[:50]}...")
                print(f"      📰 {item.get('originallink', '')[:60]}...")
                print(f"      📅 {item.get('pubDate', '')}")
                print()
        else:
            print(f"❌ 실패: {response.status_code}")
            print(f"   {response.text}")


async def test_newsdata_api():
    """NewsData.io API 테스트."""
    print("\n" + "=" * 60)
    print("🌍 NewsData.io API 테스트")
    print("=" * 60)

    api_key = os.getenv("INFO_NEWSDATA_API_KEY")

    if not api_key:
        print("❌ NewsData API 키가 설정되지 않았습니다.")
        print("   INFO_NEWSDATA_API_KEY 환경변수를 설정하세요.")
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://newsdata.io/api/1/latest",
            params={
                "apikey": api_key,
                "q": "환경 재활용",
                "language": "ko,en",
                "country": "kr",
            },
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("results", [])
                print(f"✅ 성공! {len(results)}건 조회")
                print()

                for i, item in enumerate(results[:3], 1):
                    title = item.get("title", "")[:50]
                    image = "🖼️ 있음" if item.get("image_url") else "❌ 없음"
                    source_icon = "✅" if item.get("source_icon") else "❌"

                    print(f"  [{i}] {title}...")
                    print(f"      이미지: {image}")
                    print(f"      소스아이콘: {source_icon}")
                    print(f"      카테고리: {item.get('category', [])}")
                    print(f"      키워드: {item.get('keywords', [])[:3]}")
                    print()
            else:
                print(f"❌ API 에러: {data}")
        else:
            print(f"❌ 실패: {response.status_code}")
            print(f"   {response.text}")


async def test_og_extraction():
    """OG 이미지 추출 테스트."""
    print("\n" + "=" * 60)
    print("🏷️ OG 이미지 추출 테스트")
    print("=" * 60)

    import re

    OG_IMAGE_PATTERN = re.compile(
        r'<meta\s+(?:[^>]*?\s+)?property=["\']og:image["\']\s+(?:[^>]*?\s+)?content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    OG_IMAGE_PATTERN_ALT = re.compile(
        r'<meta\s+(?:[^>]*?\s+)?content=["\']([^"\']+)["\']\s+(?:[^>]*?\s+)?property=["\']og:image["\']',
        re.IGNORECASE,
    )

    # 테스트 URL (네이버 뉴스)
    test_urls = [
        "https://n.news.naver.com/article/003/0012956789",
        "https://www.hani.co.kr/arti/society/environment/1175000.html",
    ]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in test_urls:
            try:
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Eco2Bot/1.0)"},
                )

                if response.status_code == 200:
                    html = response.text[:10000]
                    match = OG_IMAGE_PATTERN.search(html)
                    if not match:
                        match = OG_IMAGE_PATTERN_ALT.search(html)

                    if match:
                        image_url = match.group(1)
                        print(f"✅ {url[:40]}...")
                        print(f"   og:image: {image_url[:60]}...")
                    else:
                        print(f"⚠️ {url[:40]}...")
                        print(f"   og:image 없음")
                else:
                    print(f"❌ {url[:40]}... - HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ {url[:40]}... - {e}")
            print()


async def main():
    """메인 테스트 실행."""
    print("\n" + "🚀 Info Service API 테스트 시작")
    print("=" * 60)

    # 환경변수 출력
    print("\n📋 환경변수 확인:")
    print(f"  INFO_NAVER_CLIENT_ID: {'✅ 설정됨' if os.getenv('INFO_NAVER_CLIENT_ID') else '❌ 미설정'}")
    print(f"  INFO_NAVER_CLIENT_SECRET: {'✅ 설정됨' if os.getenv('INFO_NAVER_CLIENT_SECRET') else '❌ 미설정'}")
    print(f"  INFO_NEWSDATA_API_KEY: {'✅ 설정됨' if os.getenv('INFO_NEWSDATA_API_KEY') else '❌ 미설정'}")

    await test_naver_api()
    await test_newsdata_api()
    await test_og_extraction()

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
