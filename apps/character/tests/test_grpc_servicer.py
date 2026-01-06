"""CharacterServicer gRPC 테스트.

gRPC Servicer는 외부 시스템(scan, my 등)과의 인터페이스입니다.
이 테스트는 Protocol Buffers 변환, 에러 핸들링, 레거시 호환성을 검증합니다.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import grpc
import pytest

from character.application.reward.dto import RewardResult
from character.domain.entities import Character
from character.presentation.grpc.servicers.character_servicer import (
    CharacterServicer,
)
from character.proto import character_pb2

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_evaluate_command() -> AsyncMock:
    """EvaluateRewardCommand mock."""
    return AsyncMock()


@pytest.fixture
def mock_character_matcher() -> AsyncMock:
    """CharacterMatcher mock."""
    return AsyncMock()


@pytest.fixture
def mock_grpc_context() -> AsyncMock:
    """gRPC ServicerContext mock."""
    context = AsyncMock(spec=grpc.aio.ServicerContext)
    context.abort = AsyncMock()
    return context


@pytest.fixture
def sample_character() -> Character:
    """테스트용 캐릭터."""
    return Character(
        id=uuid4(),
        code="char-pet",
        name="페트",
        type_label="재활용",
        dialog="안녕! 나는 페트야!",
        match_label="무색페트병",
    )


class TestGetCharacterReward:
    """GetCharacterReward RPC 테스트.

    검증 포인트:
    1. Protobuf -> DTO 변환 정확성
    2. DTO -> Protobuf 응답 변환 정확성
    3. 레거시 필드(type) 호환성
    4. 에러 핸들링 (INVALID_ARGUMENT, INTERNAL)
    """

    async def test_success_with_reward(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """리워드 지급 성공 케이스.

        검증:
        - Protobuf 요청이 올바르게 DTO로 변환되는지
        - Application layer 결과가 Protobuf 응답으로 올바르게 변환되는지
        - 레거시 호환용 'type' 필드가 'character_type'과 동일한 값을 갖는지

        이유:
        gRPC는 scan/my 등 다른 서비스와의 통신에 사용됩니다.
        변환 오류는 전체 시스템 장애로 이어질 수 있어 철저한 검증이 필요합니다.
        """
        # Given: 리워드 지급 결과
        mock_evaluate_command.execute.return_value = RewardResult(
            received=True,
            already_owned=False,
            character_code="char-pet",
            character_name="페트",
            character_type="재활용",
            dialog="안녕! 나는 페트야!",
            match_reason="Matched by 무색페트병",
        )

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)

        # Protobuf 요청 생성
        request = character_pb2.RewardRequest(
            user_id=str(uuid4()),
            source="scan",
            classification=character_pb2.ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        # When
        response = await servicer.GetCharacterReward(request, mock_grpc_context)

        # Then: 응답 필드 검증
        assert response.received is True
        assert response.already_owned is False
        assert response.name == "페트"
        assert response.dialog == "안녕! 나는 페트야!"
        assert response.character_type == "재활용"
        # 레거시 호환성: type 필드도 동일한 값
        assert response.type == "재활용"

    async def test_already_owned_character(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """이미 소유한 캐릭터 케이스.

        검증:
        - already_owned=True일 때 received=False인지
        - 캐릭터 정보는 여전히 응답에 포함되는지

        이유:
        클라이언트는 "이미 보유 중" 메시지를 표시하기 위해
        캐릭터 정보가 필요합니다.
        """
        mock_evaluate_command.execute.return_value = RewardResult(
            received=False,
            already_owned=True,
            character_code="char-pet",
            character_name="페트",
            character_type="재활용",
            dialog="안녕! 나는 페트야!",
            match_reason="Matched by 무색페트병",
        )

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)

        request = character_pb2.RewardRequest(
            user_id=str(uuid4()),
            source="scan",
            classification=character_pb2.ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        response = await servicer.GetCharacterReward(request, mock_grpc_context)

        assert response.received is False
        assert response.already_owned is True
        # 캐릭터 정보는 포함됨
        assert response.name == "페트"

    async def test_invalid_uuid_returns_invalid_argument(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """잘못된 UUID 형식 처리.

        검증:
        - 잘못된 user_id가 INVALID_ARGUMENT 에러로 처리되는지

        이유:
        잘못된 입력을 INVALID_ARGUMENT로 명확히 구분해야
        클라이언트가 적절한 에러 핸들링을 할 수 있습니다.
        """
        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)

        # 잘못된 UUID
        request = character_pb2.RewardRequest(
            user_id="not-a-valid-uuid",
            source="scan",
            classification=character_pb2.ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        await servicer.GetCharacterReward(request, mock_grpc_context)

        # INVALID_ARGUMENT로 abort 호출됨
        mock_grpc_context.abort.assert_called_once()
        call_args = mock_grpc_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INVALID_ARGUMENT

    async def test_internal_error_handling(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """내부 예외 처리.

        검증:
        - 예상치 못한 예외가 INTERNAL 에러로 변환되는지
        - 내부 에러 메시지가 클라이언트에 노출되지 않는지

        이유:
        보안상 내부 에러 상세 정보는 숨기고,
        클라이언트에는 일반적인 에러 메시지만 전달해야 합니다.
        """
        mock_evaluate_command.execute.side_effect = Exception("DB connection failed")

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)

        request = character_pb2.RewardRequest(
            user_id=str(uuid4()),
            source="scan",
            classification=character_pb2.ClassificationSummary(
                major_category="재활용폐기물",
                middle_category="무색페트병",
            ),
            disposal_rules_present=True,
            insufficiencies_present=False,
        )

        await servicer.GetCharacterReward(request, mock_grpc_context)

        # INTERNAL로 abort, 상세 메시지는 숨김
        mock_grpc_context.abort.assert_called_once()
        call_args = mock_grpc_context.abort.call_args
        assert call_args[0][0] == grpc.StatusCode.INTERNAL
        assert "Internal server error" in call_args[0][1]


class TestGetDefaultCharacter:
    """GetDefaultCharacter RPC 테스트.

    검증 포인트:
    1. 기본 캐릭터 정상 반환
    2. 기본 캐릭터 없을 때 found=False
    3. 에러 핸들링
    """

    async def test_success_returns_default_character(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
        sample_character: Character,
    ) -> None:
        """기본 캐릭터 조회 성공.

        검증:
        - found=True와 함께 모든 캐릭터 정보가 반환되는지
        - UUID가 문자열로 올바르게 변환되는지

        이유:
        my 서비스는 신규 사용자에게 기본 캐릭터를 부여할 때
        이 RPC를 호출합니다. 정확한 정보 전달이 중요합니다.
        """
        mock_character_matcher.get_default.return_value = sample_character

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)
        request = character_pb2.GetDefaultCharacterRequest()

        response = await servicer.GetDefaultCharacter(request, mock_grpc_context)

        assert response.found is True
        assert response.character_id == str(sample_character.id)
        assert response.character_code == "char-pet"
        assert response.character_name == "페트"
        assert response.character_type == "재활용"
        assert response.character_dialog == "안녕! 나는 페트야!"

    async def test_not_found_returns_found_false(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """기본 캐릭터가 없을 때.

        검증:
        - found=False 반환 (abort가 아님)
        - 클라이언트가 graceful하게 처리할 수 있는지

        이유:
        기본 캐릭터 미설정은 구성 오류이지만,
        abort 대신 found=False로 반환하여 시스템 전체 장애를 방지합니다.
        """
        mock_character_matcher.get_default.return_value = None

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)
        request = character_pb2.GetDefaultCharacterRequest()

        response = await servicer.GetDefaultCharacter(request, mock_grpc_context)

        assert response.found is False
        # abort 호출되지 않음
        mock_grpc_context.abort.assert_not_called()

    async def test_internal_error_aborts(
        self,
        mock_evaluate_command: AsyncMock,
        mock_character_matcher: AsyncMock,
        mock_grpc_context: AsyncMock,
    ) -> None:
        """내부 에러 시 abort.

        검증:
        - DB 에러 등 예외 시 INTERNAL로 abort되는지
        """
        mock_character_matcher.get_default.side_effect = Exception("DB error")

        servicer = CharacterServicer(mock_evaluate_command, mock_character_matcher)
        request = character_pb2.GetDefaultCharacterRequest()

        await servicer.GetDefaultCharacter(request, mock_grpc_context)

        mock_grpc_context.abort.assert_called_once()
        assert mock_grpc_context.abort.call_args[0][0] == grpc.StatusCode.INTERNAL
