"""Reward HTTP Controller.

내부 API로, Istio AuthorizationPolicy로 접근 제어됩니다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from apps.character.application.reward import EvaluateRewardCommand
from apps.character.application.reward.dto import ClassificationSummary
from apps.character.application.reward.dto import RewardRequest as RewardRequestDTO
from apps.character.presentation.http.schemas import RewardRequest, RewardResponse
from apps.character.setup.dependencies import get_evaluate_reward_command

router = APIRouter(prefix="/internal/characters", tags=["internal"])


@router.post(
    "/rewards",
    response_model=RewardResponse,
    summary="캐릭터 리워드 평가",
    description="분류 결과를 기반으로 캐릭터 리워드를 평가합니다. 내부 API입니다.",
)
async def evaluate_reward(
    request: RewardRequest,
    command: Annotated[EvaluateRewardCommand, Depends(get_evaluate_reward_command)],
) -> RewardResponse:
    """캐릭터 리워드를 평가합니다."""
    # HTTP 스키마를 Application DTO로 변환
    dto = RewardRequestDTO(
        user_id=request.user_id,
        source=request.source,
        classification=ClassificationSummary(
            major_category=request.classification.major_category,
            middle_category=request.classification.middle_category,
            minor_category=request.classification.minor_category,
            confidence=request.classification.confidence,
        ),
        # 리워드 조건 (레거시 정합성)
        disposal_rules_present=request.disposal_rules_present,
        insufficiencies_present=request.insufficiencies_present,
    )

    result = await command.execute(dto)

    return RewardResponse(
        received=result.received,
        already_owned=result.already_owned,
        name=result.character_name,
        dialog=result.dialog,
        match_reason=result.match_reason,
        character_type=result.character_type,
        type=result.character_type,  # Legacy compatibility
    )
