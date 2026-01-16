"""Domain Constants.

도메인 레이어의 상수 정의.
"""

# 카테고리별 검색 키워드
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "environment": [
        "환경",
        "분리배출",
        "재활용",
        "쓰레기",
        "폐기물",
        "기후변화",
        "온실가스",
        "탄소",
        "생태계",
        "environment",
        "recycling",
        "waste",
        "climate",
        "pollution",
    ],
    "energy": [
        "에너지",
        "신재생",
        "태양광",
        "풍력",
        "전기차",
        "배터리",
        "수소",
        "탄소중립",
        "energy",
        "solar",
        "renewable",
        "EV",
        "battery",
    ],
    "ai": [
        "인공지능",
        "AI",
        "머신러닝",
        "딥러닝",
        "챗봇",
        "GPT",
        "LLM",
        "자동화",
        "artificial intelligence",
        "machine learning",
        "automation",
    ],
}

# 유효한 카테고리 목록
VALID_CATEGORIES = ["all", "environment", "energy", "ai"]

# 뉴스 카테고리 (all 제외)
CATEGORIES = frozenset({"environment", "energy", "ai"})

# 유효한 뉴스 소스 목록
VALID_SOURCES = ["all", "naver", "newsdata"]
