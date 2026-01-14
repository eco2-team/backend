"""Intent Classifier Service - 의도 분류 비즈니스 로직.

순수 비즈니스 로직만 포함. LangGraph 의존성 없음.
Domain Layer의 Intent, QueryComplexity, ChatIntent 사용.

Clean Architecture:
- Service: 비즈니스 로직 (이 파일)
- Port: LLMClientPort (generate만 사용)
- Domain: Intent, ChatIntent (결과 VO)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_worker.domain import ChatIntent, Intent, QueryComplexity

if TYPE_CHECKING:
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

INTENT_CLASSIFIER_PROMPT = """당신은 사용자 메시지의 의도를 분류하는 분류기입니다.

## 가능한 의도:
- waste: 분리배출, 폐기물 처리 방법 질문
- character: 캐릭터 정보, 획득 조건 질문
- location: 주변 재활용 센터, 제로웨이스트샵 검색
- general: 기타 일반적인 대화, 환경 관련 지식

## 규칙:
1. 반드시 위 4가지 중 하나만 출력
2. 소문자로 출력
3. 추가 설명 없이 의도 단어만 출력
"""

COMPLEX_KEYWORDS = frozenset(["그리고", "또한", "차이", "비교", "여러", "같이"])


class IntentClassifier:
    """의도 분류 서비스.

    책임:
    - 메시지 분석 → 의도 분류 (Domain: Intent)
    - 복잡도 판단 (Domain: QueryComplexity)
    - 결과 반환 (Domain: ChatIntent Value Object)

    LangGraph 노드에서 호출되며,
    노드는 이 서비스의 결과를 state에 반영하는 역할만 수행.
    """

    def __init__(self, llm: "LLMClientPort"):
        self._llm = llm

    async def classify(self, message: str) -> ChatIntent:
        """메시지의 의도를 분류.

        Args:
            message: 사용자 메시지

        Returns:
            ChatIntent: 불변 Value Object (Domain Layer)
        """
        try:
            # LLMClientPort.generate() 직접 호출
            intent_str = await self._llm.generate(
                prompt=message,
                system_prompt=INTENT_CLASSIFIER_PROMPT,
                max_tokens=20,
                temperature=0.1,
            )

            # 정규화
            intent_str = intent_str.strip().lower()

            # Domain Enum으로 변환
            intent = Intent.from_string(intent_str)

            # 복잡도 판단
            is_complex = self._is_complex_query(message)
            complexity = QueryComplexity.from_bool(is_complex)

            logger.info(
                "Intent classified",
                extra={
                    "intent": intent.value,
                    "complexity": complexity.value,
                },
            )

            return ChatIntent(
                intent=intent,
                complexity=complexity,
                confidence=1.0,
            )

        except Exception as e:
            logger.error("Intent classification failed: %s", e)
            return ChatIntent.simple_general(confidence=0.0)

    def _is_complex_query(self, message: str) -> bool:
        """복잡도 판단."""
        for keyword in COMPLEX_KEYWORDS:
            if keyword in message:
                return True
        return len(message) > 100
