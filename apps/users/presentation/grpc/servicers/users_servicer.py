"""UsersService gRPC Servicer (Thin Adapter).

OAuth 콜백에서 auth 도메인이 호출하는 사용자 관련 gRPC 서비스입니다.

**Thin Adapter 패턴**:
    - request → DTO 변환
    - UseCase.execute(dto) 호출
    - result → protobuf 응답 변환

예외 처리는 ErrorHandlerInterceptor에서 담당합니다.

통합 스키마 사용:
    - users.accounts
    - users.social_accounts
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

import grpc

from apps.users.application.identity.dto import OAuthUserRequest, UpdateLoginTimeRequest
from apps.users.presentation.grpc.protos import (
    GetOrCreateFromOAuthResponse,
    GetUserResponse,
    SocialAccountInfo,
    UpdateLoginTimeResponse,
    UserInfo,
    UsersServiceServicer,
)

if TYPE_CHECKING:
    from apps.users.presentation.grpc.protos import (
        GetOrCreateFromOAuthRequest,
        GetUserRequest,
    )
    from apps.users.presentation.grpc.protos import (
        UpdateLoginTimeRequest as UpdateLoginTimeRequestProto,
    )
    from apps.users.setup.dependencies import GrpcUseCaseFactory

logger = logging.getLogger(__name__)


class UsersServicer(UsersServiceServicer):
    """Users gRPC Service (Thin Adapter).

    Application Layer의 UseCase를 호출하는 얇은 어댑터입니다.
    DB 접근, 트랜잭션 관리는 모두 UseCase와 Gateway에서 처리됩니다.
    예외 처리는 ErrorHandlerInterceptor에서 담당합니다.
    """

    def __init__(
        self,
        session_factory,
        use_case_factory: "GrpcUseCaseFactory",
    ) -> None:
        """
        Args:
            session_factory: AsyncSession 팩토리 (async_sessionmaker)
            use_case_factory: UseCase 생성 팩토리
        """
        self._session_factory = session_factory
        self._use_case_factory = use_case_factory

    async def GetOrCreateFromOAuth(
        self,
        request: "GetOrCreateFromOAuthRequest",
        context: grpc.aio.ServicerContext,
    ) -> GetOrCreateFromOAuthResponse:
        """OAuth 프로필로 사용자 조회 또는 생성."""
        # 1. Request → DTO 변환
        dto = OAuthUserRequest(
            provider=request.provider,
            provider_user_id=request.provider_user_id,
            email=request.email if request.HasField("email") else None,
            nickname=request.nickname if request.HasField("nickname") else None,
            profile_image_url=(
                request.profile_image_url if request.HasField("profile_image_url") else None
            ),
        )

        # 2. 세션 생성 및 UseCase 실행
        async with self._session_factory() as session:
            command = self._use_case_factory.create_get_or_create_from_oauth_command(session)
            result = await command.execute(dto)
            await session.commit()

        # 3. 비즈니스 로깅
        log_action = "Created new user" if result.is_new_user else "Found existing user"
        logger.info(
            f"{log_action} via OAuth",
            extra={
                "user_id": str(result.user_id),
                "provider": request.provider,
                "is_new_user": result.is_new_user,
            },
        )

        # 4. Result → Protobuf 응답 변환
        return GetOrCreateFromOAuthResponse(
            user=self._result_to_user_proto(result),
            social_account=self._result_to_social_account_proto(result),
            is_new_user=result.is_new_user,
        )

    async def GetUser(
        self,
        request: "GetUserRequest",
        context: grpc.aio.ServicerContext,
    ) -> GetUserResponse:
        """사용자 ID로 조회."""
        # 1. Request 파싱
        user_id = UUID(request.user_id)

        # 2. 세션 생성 및 Query 실행
        async with self._session_factory() as session:
            query = self._use_case_factory.create_get_user_query(session)
            result = await query.execute(user_id)

        if result is None:
            return GetUserResponse()

        # 3. Result → Protobuf 응답 변환
        return GetUserResponse(
            user=UserInfo(
                id=str(result.user_id),
                nickname=result.nickname or "",
                profile_image_url=result.profile_image_url or "",
                phone_number=result.phone_number or "",
                created_at=result.created_at.isoformat() if result.created_at else "",
                updated_at=result.updated_at.isoformat() if result.updated_at else "",
                last_login_at=result.last_login_at.isoformat() if result.last_login_at else "",
            )
        )

    async def UpdateLoginTime(
        self,
        request: "UpdateLoginTimeRequestProto",
        context: grpc.aio.ServicerContext,
    ) -> UpdateLoginTimeResponse:
        """로그인 시간 업데이트."""
        # 1. Request → DTO 변환
        dto = UpdateLoginTimeRequest(
            user_id=UUID(request.user_id),
            provider=request.provider,
            provider_user_id=request.provider_user_id,
        )

        # 2. 세션 생성 및 Command 실행
        async with self._session_factory() as session:
            command = self._use_case_factory.create_update_login_time_command(session)
            await command.execute(dto)
            await session.commit()

        # 3. 성공 응답
        return UpdateLoginTimeResponse(success=True)

    # =========================================================================
    # Private Methods - Protobuf Conversion (Only DTO → Protobuf)
    # =========================================================================

    def _result_to_user_proto(self, result) -> UserInfo:
        """OAuthUserResult → UserInfo protobuf."""
        return UserInfo(
            id=str(result.user_id),
            nickname=result.nickname or "",
            profile_image_url=result.profile_image_url or "",
            phone_number=result.phone_number or "",
            created_at=result.created_at.isoformat() if result.created_at else "",
            updated_at=result.updated_at.isoformat() if result.updated_at else "",
            last_login_at=result.last_login_at.isoformat() if result.last_login_at else "",
        )

    def _result_to_social_account_proto(self, result) -> SocialAccountInfo:
        """OAuthUserResult → SocialAccountInfo protobuf."""
        return SocialAccountInfo(
            id=str(result.social_account_id),
            user_id=str(result.user_id),
            provider=result.provider,
            provider_user_id=result.provider_user_id,
            email=result.social_email or "",
            created_at=result.created_at.isoformat() if result.created_at else "",
            last_login_at=(
                result.social_last_login_at.isoformat() if result.social_last_login_at else ""
            ),
        )
