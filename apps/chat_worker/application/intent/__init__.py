"""Intent Classification - 의도 분류 단계.

사용자 메시지의 의도를 분류.

의도 타입:
- waste: 분리배출, 폐기물 처리 방법
- character: 캐릭터 정보, 획득 조건
- location: 주변 재활용 센터, 제로웨이스트샵
- general: 기타 일반 대화
"""

from .dto import IntentResult
from .services import IntentClassifier

__all__ = [
    "IntentClassifier",
    "IntentResult",
]
