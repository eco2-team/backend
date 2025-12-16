"""gRPC servicer for UserCharacter service.

character 도메인에서 캐릭터 지급 시 이 서비스를 호출합니다.
"""

import logging
from uuid import UUID

import grpc
from sqlalchemy import select

from domains.my.database.session import async_session_factory
from domains.my.models.user_character import UserCharacter
from domains.my.enums import UserCharacterStatus
from domains.my.proto import user_character_pb2, user_character_pb2_grpc

logger = logging.getLogger(__name__)


class UserCharacterServicer(user_character_pb2_grpc.UserCharacterServiceServicer):
    """gRPC servicer for granting characters to users."""

    async def GrantCharacter(self, request, context):
        """캐릭터를 사용자에게 지급합니다."""
        try:
            user_id = UUID(request.user_id)
            character_id = UUID(request.character_id)

            async with async_session_factory() as session:
                # 이미 소유한 캐릭터인지 확인
                stmt = select(UserCharacter).where(
                    UserCharacter.user_id == user_id,
                    UserCharacter.character_id == character_id,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    logger.info(
                        "User %s already owns character %s",
                        user_id,
                        request.character_name,
                    )
                    return user_character_pb2.GrantCharacterResponse(
                        success=True,
                        already_owned=True,
                        message=f"Already owns {request.character_name}",
                    )

                # 새 캐릭터 지급
                new_ownership = UserCharacter(
                    user_id=user_id,
                    character_id=character_id,
                    character_code=request.character_code,
                    character_name=request.character_name,
                    character_type=request.character_type or None,
                    character_dialog=request.character_dialog or None,
                    source=request.source or None,
                    status=UserCharacterStatus.OWNED,
                )
                session.add(new_ownership)
                await session.commit()

                logger.info(
                    "Granted character %s to user %s (source=%s)",
                    request.character_name,
                    user_id,
                    request.source,
                )
                return user_character_pb2.GrantCharacterResponse(
                    success=True,
                    already_owned=False,
                    message=f"Granted {request.character_name}",
                )

        except ValueError as e:
            logger.error(f"Invalid argument: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.exception("Internal error in GrantCharacter")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
