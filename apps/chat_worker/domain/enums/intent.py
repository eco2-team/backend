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

    제로웨이스트샵, 재활용센터 등 일반 장소 검색.

    - 근처 재활용센터 어디야?
    - 제로웨이스트샵 찾아줘
    """

    BULK_WASTE = "bulk_waste"
    """대형폐기물 처리 (행정안전부 API).

    대형폐기물 배출 방법, 신청 절차, 수수료 안내.

    - 소파 버리려면 어떻게 해?
    - 대형폐기물 신청 방법
    - 냉장고 수수료 얼마야?
    """

    RECYCLABLE_PRICE = "recyclable_price"
    """재활용자원 시세 (한국환경공단 API).

    재활용품 매입 가격, 시세 정보.

    - 고철 시세 얼마야?
    - 폐지 가격 알려줘
    - 페트병 kg당 얼마?
    """

    COLLECTION_POINT = "collection_point"
    """수거함 위치 검색 (한국환경공단 KECO API).

    의류수거함, 폐건전지, 폐형광등 수거함 위치.

    - 근처 의류수거함 어디야?
    - 폐건전지 수거함 위치
    - 폐형광등 어디서 버려?
    """

    WEATHER = "weather"
    """날씨 정보 조회 (기상청 KMA API).

    현재 날씨, 기온, 강수 확률 등 날씨 정보.

    - 오늘 날씨 어때?
    - 지금 비 와?
    - 강남역 날씨 알려줘
    - 우산 챙겨야 해?
    """

    IMAGE_GENERATION = "image_generation"
    """이미지 생성 요청.

    - 분리배출 방법 이미지로 만들어줘
    - 페트병 버리는 법 그림으로 보여줘
    - 인포그래픽 생성해줘
    - 이미지로 설명해줘

    Responses API의 네이티브 image_generation tool 사용.
    """

    GENERAL = "general"
    """일반 대화 및 웹 검색이 필요한 질문.

    - 안녕
    - 환경 보호에 대해 알려줘
    - 분리배출 왜 해야 해?
    - 최신 분리배출 정책은?
    - 플라스틱 규제 뉴스 알려줘

    Note:
        네이티브 web_search tool (OpenAI Responses API)을
        사용하여 실시간 정보 검색 지원.
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
