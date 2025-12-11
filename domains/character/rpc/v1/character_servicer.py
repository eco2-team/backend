import logging
from uuid import UUID

import grpc
from domains.character.database.session import async_session_factory
from domains.character.proto import character_pb2, character_pb2_grpc
from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.character.services.character import CharacterService

logger = logging.getLogger(__name__)


class CharacterServicer(character_pb2_grpc.CharacterServiceServicer):
    async def GetCharacterReward(self, request, context):
        try:
            # 1. Convert Protobuf request to Pydantic model
            payload = CharacterRewardRequest(
                source=CharacterRewardSource(request.source or "scan"),
                user_id=UUID(request.user_id),
                task_id=request.task_id,
                classification=ClassificationSummary(
                    major_category=request.classification.major_category,
                    middle_category=request.classification.middle_category,
                    minor_category=(
                        request.classification.minor_category
                        if request.classification.HasField("minor_category")
                        else None
                    ),
                ),
                situation_tags=list(request.situation_tags),
                disposal_rules_present=request.disposal_rules_present,
                insufficiencies_present=request.insufficiencies_present,
            )

            # 2. Invoke Business Logic (Service Layer)
            async with async_session_factory() as session:
                service = CharacterService(session)
                result = await service.evaluate_reward(payload)

            # 3. Convert Pydantic response to Protobuf response
            response = character_pb2.RewardResponse(
                received=result.received,
                already_owned=result.already_owned,
                name=result.name,
                dialog=result.dialog,
                match_reason=result.match_reason,
                character_type=result.character_type,
                type=result.type,
            )
            return response

        except ValueError as e:
            # UUID 변환 실패 등 validation 에러
            logger.error(f"Invalid argument: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.exception("Internal error in GetCharacterReward")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
