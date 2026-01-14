"""LLM Policy Port - 프롬프트/정책/리트라이.

책임:
- 프롬프트 템플릿 관리
- 모델 선택/라우팅
- 리트라이 정책
- 레이트리밋

vs LLMClient:
- LLMClient: 순수 API 호출
- LLMPolicy: 호출 전/후 로직

사용 예:
```python
policy = LLMPolicy(client)
prompt = policy.format_intent_prompt(message)
result = await policy.execute_with_retry(
    lambda: client.generate(prompt),
    max_retries=3,
)
```
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class ModelTier(str, Enum):
    """모델 티어 (비용/성능 트레이드오프)."""

    FAST = "fast"  # 빠르고 저렴 (gpt-4o-mini, gemini-flash)
    STANDARD = "standard"  # 균형 (gpt-4o, gemini-pro)
    PREMIUM = "premium"  # 최고 성능 (gpt-4-turbo, claude-opus)


class TaskType(str, Enum):
    """작업 타입 (모델 선택 기준)."""

    INTENT_CLASSIFICATION = "intent"
    ANSWER_GENERATION = "answer"
    SUMMARIZATION = "summarization"


class LLMPolicyPort(ABC):
    """LLM 정책 포트.

    프롬프트 템플릿, 모델 선택, 리트라이 정책 관리.
    """

    @abstractmethod
    def select_model(
        self,
        task_type: TaskType,
        preferred_tier: ModelTier = ModelTier.STANDARD,
    ) -> str:
        """작업 타입에 따른 모델 선택.

        Args:
            task_type: 작업 타입
            preferred_tier: 선호 티어

        Returns:
            모델 이름 (e.g., "gpt-4o", "gemini-pro")
        """
        pass

    @abstractmethod
    def format_prompt(
        self,
        template_name: str,
        **kwargs: Any,
    ) -> str:
        """프롬프트 템플릿 포매팅.

        Args:
            template_name: 템플릿 이름
            **kwargs: 템플릿 변수

        Returns:
            포매팅된 프롬프트
        """
        pass

    @abstractmethod
    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> T:
        """리트라이 정책 적용.

        Args:
            operation: 실행할 작업
            max_retries: 최대 재시도 횟수
            backoff_factor: 백오프 배수

        Returns:
            작업 결과
        """
        pass

    @abstractmethod
    async def check_rate_limit(
        self,
        model: str,
    ) -> bool:
        """레이트리밋 확인.

        Args:
            model: 모델 이름

        Returns:
            사용 가능 여부
        """
        pass
