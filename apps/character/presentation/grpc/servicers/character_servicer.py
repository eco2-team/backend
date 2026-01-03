"""Character gRPC Servicer.

gRPC 요청을 처리하고 Clean Architecture의 Application 계층을 호출합니다.
"""

import logging
from uuid import UUID

import grpc

from apps.character.application.reward import EvaluateRewardCommand
from apps.character.application.reward.dto import ClassificationSummary, RewardRequest
from apps.character.application.reward.ports import CharacterMatcher
from apps.character.domain.enums import CharacterRewardSource
from domains.character.proto import character_pb2, character_pb2_grpc

logger = logging.getLogger(__name__)


class CharacterServicer(character_pb2_grpc.CharacterServiceServicer):
    """Character gRPC Servicer.

    Clean Architecture의 Application 계층과 연결됩니다.
    """

    def __init__(
        self,
        evaluate_command: EvaluateRewardCommand,
        character_matcher: CharacterMatcher,
    ) -> None:
        """Initialize.

        Args:
            evaluate_command: 리워드 평가 Command
            character_matcher: 캐릭터 매처 (기본 캐릭터 조회용)
        """
        self._evaluate_command = evaluate_command
        self._character_matcher = character_matcher

    async def GetCharacterReward(
        self,
        request: character_pb2.RewardRequest,
        context: grpc.aio.ServicerContext,
    ) -> character_pb2.RewardResponse:
        """캐릭터 리워드를 평가합니다."""
        try:
            # 1. Protobuf -> Application DTO
            dto = RewardRequest(
                user_id=UUID(request.user_id),
                source=CharacterRewardSource(request.source or "scan"),
                classification=ClassificationSummary(
                    major_category=request.classification.major_category,
                    middle_category=request.classification.middle_category,
                    minor_category=(
                        request.classification.minor_category
                        if request.classification.HasField("minor_category")
                        else None
                    ),
                ),
                # 리워드 조건 필드 (레거시 정합성)
                disposal_rules_present=request.disposal_rules_present,
                insufficiencies_present=request.insufficiencies_present,
            )

            # 2. Application Command 실행
            result = await self._evaluate_command.execute(dto)

            # 3. Application DTO -> Protobuf
            response = character_pb2.RewardResponse(
                received=result.received,
                already_owned=result.already_owned,
                name=result.character_name or "",
                dialog=result.dialog or "",
                match_reason=result.match_reason or "",
                character_type=result.character_type or "",
                type=result.character_type or "",  # Legacy compatibility
            )

            logger.info(
                "Evaluated reward via gRPC",
                extra={
                    "user_id": str(dto.user_id),
                    "received": result.received,
                    "already_owned": result.already_owned,
                },
            )
            return response

        except ValueError as e:
            logger.error(
                "Invalid argument in GetCharacterReward",
                extra={"error": str(e), "user_id": request.user_id},
            )
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception:
            logger.exception(
                "Internal error in GetCharacterReward",
                extra={"user_id": request.user_id},
            )
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")

    async def GetDefaultCharacter(
        self,
        request: character_pb2.GetDefaultCharacterRequest,
        context: grpc.aio.ServicerContext,
    ) -> character_pb2.GetDefaultCharacterResponse:
        """기본 캐릭터 정보를 조회합니다."""
        try:
            character = await self._character_matcher.get_default()

            # Null 체크 (domains 정합성)
            if character is None:
                logger.warning("Default character not found")
                return character_pb2.GetDefaultCharacterResponse(found=False)

            logger.info(
                "Returning default character",
                extra={"character_name": character.name, "character_id": str(character.id)},
            )

            return character_pb2.GetDefaultCharacterResponse(
                found=True,
                character_id=str(character.id),
                character_code=character.code,
                character_name=character.name,
                character_type=character.type_label or "",
                character_dialog=character.dialog or "",
            )

        except Exception:
            logger.exception("Internal error in GetDefaultCharacter")
            await context.abort(grpc.StatusCode.INTERNAL, "Internal server error")
