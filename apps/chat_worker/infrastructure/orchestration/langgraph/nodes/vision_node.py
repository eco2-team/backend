"""Vision Node - 이미지 분류 노드.

LangGraph 파이프라인의 Vision 분석 노드입니다.

노드 책임:
1. 이벤트 발행 (진행 상황)
2. Vision 모델 호출 (이미지 분류)
3. state 업데이트 (classification_result)

Clean Architecture:
- Node: Orchestration만 담당 (이 파일)
- Port: VisionModelPort (이미지 분석 API)

흐름:
1. image_url 확인
2. 진행 이벤트 발행
3. Vision 모델로 분류
4. classification_result를 state에 저장
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.vision import VisionModelPort

logger = logging.getLogger(__name__)


def create_vision_node(
    vision_model: "VisionModelPort",
    event_publisher: "ProgressNotifierPort",
):
    """Vision 노드 생성.

    Args:
        vision_model: Vision 모델 클라이언트
        event_publisher: 이벤트 발행자 (SSE)

    Returns:
        LangGraph 노드 함수
    """

    async def vision_node(state: dict[str, Any]) -> dict[str, Any]:
        """이미지를 분석하여 폐기물을 분류합니다.

        Args:
            state: 현재 상태 (image_url 필드 필요)

        Returns:
            업데이트된 상태 (classification_result 추가)
        """
        job_id = state.get("job_id", "")
        image_url = state.get("image_url")
        message = state.get("message", "")

        # image_url이 없으면 스킵
        if not image_url:
            logger.debug("No image_url, skipping vision node (job=%s)", job_id)
            return state

        # 1. 이벤트: 시작
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="vision",
            status="processing",
            progress=15,
            message="🔍 이미지 분석 중...",
        )

        try:
            # 2. Vision 모델 호출
            result = await vision_model.analyze_image(
                image_url=image_url,
                user_input=message,
            )

            # 3. 이벤트: 완료
            major_category = result.get("classification", {}).get("major_category", "unknown")
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="vision",
                status="completed",
                progress=25,
                result={"major_category": major_category},
                message=f"✅ 분류 완료: {major_category}",
            )

            logger.info(
                "Vision analysis completed",
                extra={
                    "job_id": job_id,
                    "major_category": major_category,
                },
            )

            # 4. state 업데이트
            return {
                **state,
                "classification_result": result,
                "has_image": True,
            }

        except Exception as e:
            logger.error(
                "Vision analysis failed",
                extra={"job_id": job_id, "error": str(e)},
            )

            await event_publisher.notify_stage(
                task_id=job_id,
                stage="vision",
                status="failed",
                result={"error": str(e)},
                message="⚠️ 이미지 분석 실패",
            )

            return {
                **state,
                "classification_result": None,
                "has_image": True,
                "vision_error": str(e),
            }

    return vision_node
