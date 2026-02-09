"""OpenAI BARS Evaluator Adapter.

BARSEvaluator Protocol 구현체.
LLM Structured Output을 사용하여 BARS 5축 평가를 수행합니다.

Clean Architecture:
- Adapter: 이 파일 (구현체, Infrastructure Layer)
- Port: application/ports/eval/bars_evaluator.py (추상화)
- Schema: infrastructure/llm/evaluators/schemas.py (Pydantic)

retry-with-repair: Structured Output 파싱 실패 시 최대 2회 재시도.
재실패 시 호출자(LLMGraderService)에서 graceful degradation 처리.

See: docs/plans/chat-eval-pipeline-plan.md §3.2.2, B.6
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from chat_worker.domain.value_objects.axis_score import AxisScore
from chat_worker.infrastructure.assets.prompt_loader import load_prompt_file
from chat_worker.infrastructure.llm.evaluators.schemas import (
    EVAL_AXES,
    BARSEvalOutput,
    SingleAxisEvalOutput,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)

# retry-with-repair 최대 재시도 횟수
_MAX_PARSE_RETRIES: int = 2


class OpenAIBARSEvaluator:
    """LLM 기반 BARS 5축 평가 어댑터.

    BARSEvaluator Protocol을 구현합니다.
    루브릭 로딩은 어댑터 내부에서 처리 (B.6).
    LLMClientPort.generate_structured()로 Structured Output 보장.

    Attributes:
        _llm: LLM 클라이언트 (DI 주입)
        _system_prompt: 공통 System prompt
        _rubrics: 축별 BARS 루브릭 텍스트
    """

    def __init__(
        self,
        llm_client: "LLMClientPort",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> None:
        """어댑터 초기화.

        Args:
            llm_client: LLM 클라이언트 (DI 주입)
            temperature: LLM 온도 (낮을수록 일관됨)
            max_tokens: 최대 응답 토큰
        """
        self._llm = llm_client
        self._temperature = temperature
        self._max_tokens = max_tokens

        # 프롬프트 로딩 (LRU 캐싱됨)
        self._system_prompt = load_prompt_file("evaluation", "bars_system")
        self._rubrics: dict[str, str] = {}
        for axis in EVAL_AXES:
            self._rubrics[axis] = load_prompt_file("evaluation", f"bars_{axis}")

        logger.info(
            "OpenAIBARSEvaluator initialized",
            extra={"axes": list(EVAL_AXES), "temperature": temperature},
        )

    async def evaluate_all_axes(
        self,
        query: str,
        context: str,
        answer: str,
    ) -> dict[str, AxisScore]:
        """전체 5축 BARS 평가 (단일 프롬프트, 비용 절감).

        Args:
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변

        Returns:
            축 이름 -> AxisScore 매핑

        Raises:
            ValueError: 파싱 재시도 모두 실패 시
        """
        # Bias mitigation: 축 순서 셔플로 위치 편향(positional bias) 완화
        shuffled_axes = list(EVAL_AXES)
        random.shuffle(shuffled_axes)

        rubric_block = "\n\n".join(
            f"### {axis.upper()}\n{self._rubrics[axis]}" for axis in shuffled_axes
        )

        prompt = (
            f"## 평가 대상\n\n"
            f"**사용자 질문**: {query}\n\n"
            f"**검색 컨텍스트**:\n{context}\n\n"
            f"**생성된 답변**:\n{answer}\n\n"
            f"## 평가 루브릭\n\n{rubric_block}\n\n"
            f"위 루브릭에 따라 5개 축 모두를 평가해주세요."
        )

        result = await self._call_structured(
            prompt=prompt,
            schema=BARSEvalOutput,
        )

        return self._to_axis_scores(result)

    async def evaluate_axis(
        self,
        axis: str,
        query: str,
        context: str,
        answer: str,
    ) -> AxisScore:
        """단일 축 BARS 평가 (Self-Consistency 용).

        Args:
            axis: 평가 축 이름
            query: 사용자 질문
            context: RAG 컨텍스트
            answer: 생성된 답변

        Returns:
            해당 축의 AxisScore

        Raises:
            ValueError: 파싱 재시도 모두 실패 시
        """
        rubric = self._rubrics[axis]

        prompt = (
            f"## 평가 대상\n\n"
            f"**사용자 질문**: {query}\n\n"
            f"**검색 컨텍스트**:\n{context}\n\n"
            f"**생성된 답변**:\n{answer}\n\n"
            f"## 평가 루브릭 ({axis.upper()})\n\n{rubric}\n\n"
            f"위 루브릭에 따라 {axis} 축만 평가해주세요."
        )

        result = await self._call_structured(
            prompt=prompt,
            schema=SingleAxisEvalOutput,
        )

        eval_data = result.evaluation
        return AxisScore(
            axis=axis,
            score=eval_data.score,
            evidence=eval_data.evidence,
            reasoning=eval_data.reasoning,
        )

    async def _call_structured(self, prompt: str, schema: type):
        """Structured Output 호출 + retry-with-repair.

        Args:
            prompt: 평가 프롬프트
            schema: Pydantic 스키마

        Returns:
            파싱된 스키마 인스턴스

        Raises:
            ValueError: 최대 재시도 후에도 파싱 실패
        """
        last_error: Exception | None = None

        for attempt in range(_MAX_PARSE_RETRIES + 1):
            try:
                if attempt == 0:
                    result = await self._llm.generate_structured(
                        prompt=prompt,
                        response_schema=schema,
                        system_prompt=self._system_prompt,
                        max_tokens=self._max_tokens,
                        temperature=self._temperature,
                    )
                else:
                    # retry-with-repair: 에러 메시지 포함하여 재호출
                    repair_prompt = (
                        f"{prompt}\n\n"
                        f"[이전 시도에서 파싱 오류 발생: {last_error}]\n"
                        f"올바른 JSON 형식으로 다시 응답해주세요."
                    )
                    result = await self._llm.generate_structured(
                        prompt=repair_prompt,
                        response_schema=schema,
                        system_prompt=self._system_prompt,
                        max_tokens=self._max_tokens,
                        temperature=self._temperature,
                    )

                logger.debug(
                    "Structured output parsed successfully",
                    extra={"attempt": attempt + 1, "schema": schema.__name__},
                )
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    "Structured output parse failed, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": _MAX_PARSE_RETRIES,
                        "error": str(e),
                    },
                )

        raise ValueError(
            f"Structured output parse failed after {_MAX_PARSE_RETRIES + 1} attempts: {last_error}"
        )

    def _to_axis_scores(self, output: BARSEvalOutput) -> dict[str, AxisScore]:
        """BARSEvalOutput → dict[str, AxisScore] 변환.

        Args:
            output: 파싱된 5축 평가 결과

        Returns:
            축 이름 -> AxisScore 매핑
        """
        scores: dict[str, AxisScore] = {}
        for axis in EVAL_AXES:
            eval_data = getattr(output, axis)
            scores[axis] = AxisScore(
                axis=axis,
                score=eval_data.score,
                evidence=eval_data.evidence,
                reasoning=eval_data.reasoning,
            )
        return scores


__all__ = ["OpenAIBARSEvaluator"]
