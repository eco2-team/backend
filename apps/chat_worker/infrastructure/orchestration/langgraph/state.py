"""LangGraph State Schema.

멀티턴 대화를 위한 상태 정의.
LangGraph 1.0+ 컨텍스트 압축 지원.

아키텍처:
```
ChatState
├── messages        # 전체 대화 히스토리 (영구)
├── summary         # 압축된 이전 대화 요약
├── context         # 현재 턴 컨텍스트 (LLM 입력용)
├── query           # 현재 사용자 질문
├── intent          # 분류된 의도
├── evidence        # RAG 검색 결과
├── character       # Character Subagent 결과
├── location        # Location Subagent 결과
├── web_results     # Web Search 결과
├── answer          # 최종 응답
├── feedback        # RAG 품질 평가 결과
└── ...             # 기타 중간 상태
```

컨텍스트 압축 전략:
1. messages가 임계값 초과 시 이전 대화 요약
2. summary + recent_messages로 context 구성
3. LLM은 context만 참조 (토큰 절약)
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage


def add_messages(
    existing: list[AnyMessage] | None,
    new: list[AnyMessage] | AnyMessage,
) -> list[AnyMessage]:
    """메시지 리스트 병합 Reducer.

    Args:
        existing: 기존 메시지 리스트
        new: 추가할 메시지 (단일 또는 리스트)

    Returns:
        병합된 메시지 리스트
    """
    if existing is None:
        existing = []

    if isinstance(new, list):
        return existing + new
    return existing + [new]


class ChatState(TypedDict, total=False):
    """Chat 파이프라인 상태.

    LangGraph 1.0+ 컨텍스트 압축 지원.
    멀티턴 대화에서 토큰 효율성 확보.

    Attributes:
        messages: 전체 대화 히스토리 (Annotated Reducer로 누적)
        summary: 압축된 이전 대화 요약 (컨텍스트 압축 시 사용)
        context: 현재 턴 LLM 입력 컨텍스트 (summary + recent)
        query: 현재 사용자 질문
        intent: 분류된 의도 (waste, character, location, web_search, general)
        intent_history: 이전 intent 히스토리 (Chain-of-Intent)
        evidence: RAG 검색 결과 리스트
        character: Character Subagent 응답
        location: Location Subagent 응답
        web_results: Web Search 결과 리스트
        classification_result: Vision 분류 결과 (이미지 분석)
        answer: 최종 생성된 응답
        feedback: RAG 품질 평가 결과
        fallback_reason: Fallback 발생 사유
        job_id: 작업 ID (이벤트 추적용)
        user_id: 사용자 ID (SSE 라우팅용)
        image_url: 이미지 URL (Vision 분석용)
        thread_id: 대화 스레드 ID (멀티턴 컨텍스트)
    """

    # 대화 히스토리 (Reducer로 누적)
    messages: Annotated[list[AnyMessage], add_messages]

    # 컨텍스트 압축
    summary: str  # 이전 대화 요약
    context: dict[str, Any]  # LLM 입력용 컨텍스트

    # 현재 턴 입력
    query: str
    image_url: str | None

    # 파이프라인 중간 결과
    intent: str
    intent_history: list[str]  # Chain-of-Intent: 이전 intent 히스토리
    evidence: list[dict[str, Any]]
    character: dict[str, Any] | None
    location: dict[str, Any] | None
    web_results: list[dict[str, Any]]
    classification_result: str | None

    # 품질 평가
    feedback: dict[str, Any]
    fallback_reason: str | None

    # 최종 출력
    answer: str

    # 메타데이터
    job_id: str
    user_id: str
    thread_id: str


class LLMInputState(TypedDict):
    """LLM 입력용 압축된 상태.

    컨텍스트 압축 후 LLM에 전달되는 상태.
    전체 messages 대신 압축된 context 사용.
    """

    summarized_messages: list[AnyMessage]
    context: dict[str, Any]
    query: str
    evidence: list[dict[str, Any]]


# 토큰 임계값 상수는 summarization.py에서 정의
# from .summarization import (
#     DEFAULT_MAX_TOKENS,
#     DEFAULT_MAX_TOKENS_BEFORE_SUMMARY,
#     DEFAULT_MAX_SUMMARY_TOKENS,
# )
