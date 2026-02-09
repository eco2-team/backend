"""BARS Evaluator Port - LLM 기반 BARS 5축 평가 추상화.

Clean Architecture:
- Port: 이 파일 (추상화, Application Layer)
- Adapter: infrastructure/llm/evaluators/ (구현체)

Convention Decision (A.4):
- 신규 포트는 Protocol 사용 (structural subtyping, 테스트 용이)
- 기존 포트(ABC)는 별도 마이그레이션 PR에서 전환 예정

NOTE: rubric 로딩은 인프라 관심사이므로 어댑터가 내부 처리.
      Port 시그니처에서 rubric 파라미터 제거 (see B.6).

사용 위치:
- eval_node의 LLM Grader에서 주입
- EvaluateResponseCommand에서 오케스트레이션

참조: docs/plans/chat-eval-pipeline-plan.md Section 5.1
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from chat_worker.domain.value_objects.axis_score import AxisScore


@runtime_checkable
class BARSEvaluator(Protocol):
    """LLM 기반 BARS 5축 평가 Port.

    Infrastructure에서 구현하며, rubric 로딩은 어댑터 내부에서 처리.
    각 축은 Behaviorally Anchored Rating Scale(1-5점)로 채점.

    평가 축:
    - Faithfulness (사실 충실도): 가중치 0.30
    - Relevance (질문 관련성): 가중치 0.25
    - Completeness (정보 완결성): 가중치 0.20
    - Safety (안전성): 가중치 0.15 (위험물 시 0.25)
    - Communication (소통 품질): 가중치 0.10 (위험물 시 0.05)
    """

    async def evaluate_axis(
        self,
        axis: str,
        query: str,
        context: str,
        answer: str,
    ) -> "AxisScore":
        """단일 축 BARS 평가.

        Self-Consistency 트리거 시 개별 축 독립 호출에 사용.

        Args:
            axis: 평가 축 이름 (faithfulness, relevance, completeness, safety, communication)
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변

        Returns:
            AxisScore: 해당 축의 평가 결과 (score, evidence, reasoning)
        """
        ...

    async def evaluate_all_axes(
        self,
        query: str,
        context: str,
        answer: str,
    ) -> dict[str, "AxisScore"]:
        """전체 5축 BARS 평가 (단일 프롬프트, 비용 절감).

        기본 모드에서 5개 축을 단일 프롬프트로 묶어 1회 호출.

        Args:
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변

        Returns:
            dict[str, AxisScore]: 축 이름 -> 평가 결과 매핑
        """
        ...
