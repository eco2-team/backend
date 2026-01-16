"""Aggregator Node - 병렬 실행 결과 수집 및 검증.

Send API로 병렬 실행된 노드들의 결과를 수집하고
answer_node로 전달할 최종 state를 준비합니다.

LangGraph의 Send API 특성:
- 여러 Send가 병렬 실행되면 각 결과가 state에 병합됨
- 이 노드는 병합된 결과를 검증/로깅하고 answer로 전달

역할:
1. 병렬 실행 결과 존재 여부 확인
2. 필수(Required) vs 선택(Optional) 컨텍스트 검증
3. 필수 컨텍스트 누락 시 fallback 트리거
4. answer_node를 위한 최종 state 정리

Production Architecture:
- contracts.py의 INTENT_REQUIRED_FIELDS가 Single Source of Truth
- 필수 컨텍스트 실패 시 needs_fallback=True로 fallback 라우팅
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.infrastructure.orchestration.langgraph.contracts import (
    get_required_fields,
    validate_missing_fields,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort

logger = logging.getLogger(__name__)


def create_aggregator_node(
    event_publisher: "ProgressNotifierPort",
):
    """결과 수집 노드 팩토리.

    Args:
        event_publisher: 이벤트 발행자 (SSE)

    Returns:
        aggregator_node 함수
    """

    async def aggregator_node(state: dict[str, Any]) -> dict[str, Any]:
        """병렬 실행 결과 수집, 검증 및 정리.

        LangGraph Send API가 병렬 실행 후 자동 병합한 state를 받아서:
        1. 어떤 컨텍스트가 수집되었는지 로깅
        2. 필수 컨텍스트 누락 검증
        3. 필수 누락 시 needs_fallback=True 설정
        4. answer_node를 위한 최종 state 반환

        Args:
            state: 병렬 실행 후 병합된 상태

        Returns:
            정리된 상태 (+ needs_fallback, missing_required_contexts)
        """
        job_id = state.get("job_id", "")
        intent = state.get("intent", "general")

        # Progress: 집계 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="aggregate",
            status="started",
            progress=60,
            message="정보 취합 중",
        )

        # 수집된 컨텍스트 필드들
        context_fields = {
            "disposal_rules": "RAG 검색 결과",
            "character_context": "캐릭터 정보",
            "location_context": "장소 정보",
            "web_search_results": "웹 검색 결과",
            "bulk_waste_context": "대형폐기물 정보",
            "recyclable_price_context": "재활용 시세",
            "weather_context": "날씨 정보",
            "collection_point_context": "수거함 위치",
            "image_generation_context": "이미지 생성",
        }

        # 수집된 컨텍스트 확인
        collected: list[str] = []
        failed: list[str] = []
        collected_fields: set[str] = set()

        for field, description in context_fields.items():
            value = state.get(field)
            if value is not None:
                # dict인 경우 success 필드 확인
                if isinstance(value, dict):
                    if value.get("success", True):  # success 없으면 True로 간주
                        collected.append(description)
                        collected_fields.add(field)
                    else:
                        failed.append(f"{description} (실패)")
                else:
                    collected.append(description)
                    collected_fields.add(field)
            # None인 것은 해당 노드가 실행되지 않았거나 결과 없음

        # 필수 컨텍스트 검증 (contracts.py Single Source of Truth)
        missing_required, missing_optional = validate_missing_fields(
            intent=intent,
            collected_fields=collected_fields,
        )
        needs_fallback = len(missing_required) > 0

        logger.info(
            "Aggregator: contexts collected",
            extra={
                "job_id": job_id,
                "intent": intent,
                "collected_count": len(collected),
                "collected": collected,
                "required_fields": list(get_required_fields(intent)),
                "missing_required": list(missing_required),
                "missing_optional": list(missing_optional),
                "needs_fallback": needs_fallback,
            },
        )

        if failed:
            logger.warning(
                "Aggregator: some contexts failed",
                extra={
                    "job_id": job_id,
                    "failed": failed,
                },
            )

        if needs_fallback:
            logger.warning(
                "Aggregator: required context missing, triggering fallback",
                extra={
                    "job_id": job_id,
                    "intent": intent,
                    "missing_required": list(missing_required),
                },
            )

        # Progress: 집계 완료
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="aggregate",
            status="completed",
            progress=65,
            result={
                "collected": collected,
                "needs_fallback": needs_fallback,
            },
            message=f"정보 취합 완료: {len(collected)}건",
        )

        # state 반환 (검증 결과 포함)
        return {
            **state,
            "needs_fallback": needs_fallback,
            "missing_required_contexts": list(missing_required),
        }

    return aggregator_node


__all__ = ["create_aggregator_node"]
