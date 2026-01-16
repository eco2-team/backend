"""LLM Ports - LLM 관련 인터페이스.

분리 이유:
- LLMClient: 순수 API 호출 (generate, generate_stream)
- LLMPolicy: 프롬프트 템플릿, 모델 선택, 리트라이 정책

LLMPort가 커지면 비대해지기 쉬움:
- 프롬프트 템플릿
- 모델 라우팅
- 레이트리밋
- 리트라이
- 로깅

이를 분리해서 단일 책임 원칙 준수.
"""

from .llm_client import LLMClientPort
from .llm_policy import LLMPolicyPort

__all__ = [
    "LLMClientPort",
    "LLMPolicyPort",
]
