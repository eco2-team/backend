"""Intent Enum.

사용자 질문의 의도를 분류합니다.
"""

from enum import Enum


class Intent(str, Enum):
    """사용자 질문 의도.

    LangGraph의 Intent Node에서 분류되어
    라우팅 결정에 사용됩니다.
    """

    WASTE = "waste"
    """분리배출 질문.

    - 이 쓰레기 어떻게 버려?
    - 플라스틱 분리배출 방법
    - (이미지 첨부) 이거 뭐야?
    """

    CHARACTER = "character"
    """캐릭터 관련 질문.

    - 이 쓰레기로 어떤 캐릭터 얻어?
    - 플라스틱 버리면 누가 나와?
    """

    LOCATION = "location"
    """위치 기반 장소 검색 (카카오맵 API).

    제로웨이스트샵, 재활용센터, 대형폐기물 처리장 등 검색.

    - 근처 재활용센터 어디야?
    - 제로웨이스트샵 찾아줘
    - 대형폐기물 어디서 버려?
    """

    WEB_SEARCH = "web_search"
    """웹 검색이 필요한 질문.

    - 최신 분리배출 정책은?
    - 플라스틱 규제 뉴스 알려줘
    - 환경부 재활용 공지사항
    """

    GENERAL = "general"
    """일반 대화 (그 외).

    - 안녕
    - 환경 보호에 대해 알려줘
    - 분리배출 왜 해야 해?
    """

    @classmethod
    def from_string(cls, value: str) -> "Intent":
        """문자열에서 Intent 생성.

        Args:
            value: 의도 문자열 (case-insensitive)

        Returns:
            매칭된 Intent, 없으면 GENERAL
        """
        try:
            return cls(value.lower())
        except ValueError:
            return cls.GENERAL
