"""Base classes for Reward Evaluators.

Strategy Pattern을 위한 추상 인터페이스 정의.

Note:
    Evaluator는 순수한 평가/매칭 로직만 담당합니다.
    DB 조회, 지급 등의 부수 효과는 Service 레이어에서 처리합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from domains.character.models import Character
    from domains.character.schemas.reward import CharacterRewardRequest


@dataclass
class EvaluationResult:
    """평가 결과.

    Attributes:
        should_evaluate: 평가 조건 충족 여부
        matches: 매칭된 캐릭터 목록
        source_label: 리워드 소스 식별자 (예: "scan-reward")
        match_reason: 매칭 사유 문자열
    """

    should_evaluate: bool = False
    matches: list["Character"] = field(default_factory=list)
    source_label: str = ""
    match_reason: str | None = None


class RewardEvaluator(ABC):
    """리워드 평가 추상 클래스 (Strategy Interface).

    Evaluator는 순수한 평가 로직만 담당합니다:
    - should_evaluate(): 평가 조건 확인 (순수 함수)
    - match_characters(): 주어진 캐릭터 목록에서 매칭 (순수 함수)
    - build_match_reason(): 매칭 사유 생성 (순수 함수)

    DB 조회는 Service에서 수행 후 결과를 Evaluator에 전달합니다.

    Example:
        class QuestRewardEvaluator(RewardEvaluator):
            @property
            def source_label(self) -> str:
                return "quest-reward"

            def should_evaluate(self, payload) -> bool:
                return payload.quest_completed

            def match_characters(self, payload, characters):
                return [c for c in characters if c.quest_id == payload.quest_id]
    """

    @property
    @abstractmethod
    def source_label(self) -> str:
        """리워드 소스 식별자 (DB 저장용).

        Returns:
            예: "scan-reward", "quest-reward"
        """
        ...

    @abstractmethod
    def should_evaluate(self, payload: "CharacterRewardRequest") -> bool:
        """평가 조건을 충족하는지 확인.

        Args:
            payload: 리워드 요청

        Returns:
            bool: 평가를 진행할지 여부

        Note:
            순수 함수여야 합니다 (부수 효과 없음).
        """
        ...

    @abstractmethod
    def match_characters(
        self,
        payload: "CharacterRewardRequest",
        characters: Sequence["Character"],
    ) -> list["Character"]:
        """주어진 캐릭터 목록에서 조건에 맞는 캐릭터 매칭.

        Args:
            payload: 리워드 요청
            characters: 매칭 대상 캐릭터 목록 (Service에서 조회)

        Returns:
            매칭된 캐릭터 목록 (우선순위 순)

        Note:
            순수 함수여야 합니다 (부수 효과 없음).
        """
        ...

    @abstractmethod
    def build_match_reason(self, payload: "CharacterRewardRequest") -> str:
        """매칭 사유 문자열 생성.

        Args:
            payload: 리워드 요청

        Returns:
            사람이 읽을 수 있는 매칭 사유
        """
        ...

    def evaluate(
        self,
        payload: "CharacterRewardRequest",
        characters: Sequence["Character"],
    ) -> EvaluationResult:
        """평가 실행 (Template Method).

        1. should_evaluate()로 평가 조건 확인
        2. match_characters()로 캐릭터 매칭
        3. 결과 반환 (실제 지급은 상위 레이어에서 처리)

        Args:
            payload: 리워드 요청
            characters: 매칭 대상 캐릭터 목록

        Returns:
            평가 결과
        """
        if not self.should_evaluate(payload):
            return EvaluationResult(should_evaluate=False, source_label=self.source_label)

        match_reason = self.build_match_reason(payload)
        matches = self.match_characters(payload, characters)

        return EvaluationResult(
            should_evaluate=True,
            matches=list(matches),
            source_label=self.source_label,
            match_reason=match_reason,
        )
