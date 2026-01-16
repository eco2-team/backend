"""Answer Result DTO - 답변 생성 결과.

Answer Generation에 사용되는 데이터 전송 객체들.

- AnswerContext: 답변 생성에 필요한 컨텍스트
- AnswerResult: 답변 생성 결과
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnswerContext:
    """답변 생성 컨텍스트 DTO.

    각 파이프라인 단계에서 수집된 정보를 모아서
    최종 답변 생성에 사용합니다.
    """

    classification: dict[str, Any] | None = None
    disposal_rules: dict[str, Any] | None = None
    character_context: dict[str, Any] | None = None
    location_context: dict[str, Any] | None = None
    web_search_results: str | None = None
    recyclable_price_context: str | None = None  # 재활용자원 시세 컨텍스트
    bulk_waste_context: str | None = None  # 대형폐기물 정보 컨텍스트
    weather_context: str | None = None  # 날씨 기반 분리배출 팁
    collection_point_context: str | None = None  # 수거함 위치 정보
    user_input: str = ""
    # Multi-turn 대화 컨텍스트
    conversation_history: list[dict[str, str]] | None = None  # 최근 대화 히스토리
    conversation_summary: str | None = None  # 압축된 이전 대화 요약

    def to_prompt_context(self) -> str:
        """프롬프트용 컨텍스트 문자열 생성."""
        parts = []

        # Multi-turn: 대화 요약이 있으면 먼저 추가
        if self.conversation_summary:
            parts.append(f"## Previous Conversation Summary\n{self.conversation_summary}")

        # Multi-turn: 최근 대화 히스토리
        if self.conversation_history:
            history_lines = []
            for msg in self.conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                role_label = "User" if role == "user" else "Assistant"
                history_lines.append(f"- {role_label}: {content}")
            if history_lines:
                parts.append("## Recent Conversation\n" + "\n".join(history_lines))

        if self.classification:
            parts.append(
                f"## Classification\n```json\n"
                f"{json.dumps(self.classification, ensure_ascii=False, indent=2)}\n```"
            )

        if self.disposal_rules:
            parts.append(
                f"## Disposal Rules\n```json\n"
                f"{json.dumps(self.disposal_rules, ensure_ascii=False, indent=2)}\n```"
            )

        if self.character_context:
            char_json = json.dumps(self.character_context, ensure_ascii=False, indent=2)
            parts.append(f"## Character Info\n```json\n{char_json}\n```")

        if self.location_context:
            loc_json = json.dumps(self.location_context, ensure_ascii=False, indent=2)
            parts.append(f"## Location Info\n```json\n{loc_json}\n```")

        if self.web_search_results:
            parts.append(f"## Web Search Results\n{self.web_search_results}")

        if self.recyclable_price_context:
            parts.append(f"## Recyclable Price Info\n{self.recyclable_price_context}")

        if self.bulk_waste_context:
            parts.append(f"## Bulk Waste Info\n{self.bulk_waste_context}")

        if self.weather_context:
            parts.append(f"## Weather Info\n{self.weather_context}")

        if self.collection_point_context:
            parts.append(f"## Collection Point Info\n{self.collection_point_context}")

        if self.user_input:
            parts.append(f"## User Question\n{self.user_input}")

        return "\n\n".join(parts)

    def has_context(self) -> bool:
        """컨텍스트가 하나라도 있는지 확인."""
        return any(
            [
                self.classification,
                self.disposal_rules,
                self.character_context,
                self.location_context,
                self.web_search_results,
                self.recyclable_price_context,
                self.bulk_waste_context,
                self.weather_context,
                self.collection_point_context,
                self.conversation_history,
                self.conversation_summary,
            ]
        )


@dataclass
class AnswerResult:
    """답변 생성 결과 DTO.

    Attributes:
        answer: 생성된 답변 텍스트
        token_count: 사용된 토큰 수 (input + output)
        model: 사용된 모델 이름
        context_used: 사용된 컨텍스트 요약
        is_streamed: 스트리밍 생성 여부
    """

    answer: str
    token_count: int = 0
    model: str = ""
    context_used: list[str] = field(default_factory=list)
    is_streamed: bool = False

    @classmethod
    def from_stream(
        cls,
        chunks: list[str],
        model: str = "",
        context_used: list[str] | None = None,
    ) -> "AnswerResult":
        """스트리밍 청크들에서 결과 생성."""
        return cls(
            answer="".join(chunks),
            model=model,
            context_used=context_used or [],
            is_streamed=True,
        )

    def to_dict(self) -> dict:
        """직렬화용 딕셔너리 변환."""
        return {
            "answer": self.answer,
            "token_count": self.token_count,
            "model": self.model,
            "context_used": self.context_used,
            "is_streamed": self.is_streamed,
        }
