"""Unit tests for MyService."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domains.my.services.my import MyService  # noqa: E402


@pytest.fixture
def mock_user():
    """Mock User model."""
    user = MagicMock()
    user.id = 1
    user.auth_user_id = uuid4()
    user.username = "testuser"
    user.name = "테스트"
    user.nickname = "테스트닉네임"
    user.phone_number = "010-1234-5678"
    return user


@pytest.fixture
def mock_social_account():
    """Mock AuthUserSocialAccount model."""
    account = MagicMock()
    account.provider = "kakao"
    account.email = "test@example.com"
    account.last_login_at = datetime.now(timezone.utc)
    account.updated_at = datetime.now(timezone.utc)
    account.created_at = datetime.now(timezone.utc)
    return account


@pytest.fixture
def service(mock_session, mock_user_repo, mock_social_repo):
    """Create MyService with mocked dependencies."""
    svc = MyService.__new__(MyService)
    svc.session = mock_session
    svc.repo = mock_user_repo
    svc.social_repo = mock_social_repo
    return svc


class TestGetCurrentUser:
    """Tests for get_current_user method."""

    @pytest.mark.asyncio
    async def test_returns_existing_user_profile(self, service, mock_user, mock_social_account):
        """기존 사용자 프로필을 반환합니다."""
        service.repo.get_by_auth_user_id = AsyncMock(return_value=mock_user)
        service.social_repo.list_by_user_id = AsyncMock(return_value=[mock_social_account])

        result = await service.get_current_user(mock_user.auth_user_id, "kakao")

        assert result.username == "테스트"
        assert result.nickname == "테스트닉네임"
        assert result.provider == "kakao"

    @pytest.mark.asyncio
    async def test_creates_user_if_not_exists(self, service, mock_user, mock_social_account):
        """사용자가 없으면 생성합니다."""
        auth_user_id = uuid4()
        service.repo.get_by_auth_user_id = AsyncMock(return_value=None)
        service.repo.create_from_auth = AsyncMock(return_value=mock_user)
        service.social_repo.list_by_user_id = AsyncMock(return_value=[mock_social_account])

        result = await service.get_current_user(auth_user_id, "kakao")

        service.repo.create_from_auth.assert_called_once()
        service.session.commit.assert_called_once()
        assert result.provider == "kakao"


class TestUpdateCurrentUser:
    """Tests for update_current_user method."""

    @pytest.mark.asyncio
    async def test_updates_user_profile(self, service, mock_user, mock_social_account):
        """사용자 프로필을 업데이트합니다."""
        from domains.my.schemas import UserUpdate

        service.repo.get_by_auth_user_id = AsyncMock(return_value=mock_user)
        service.repo.update_user = AsyncMock(return_value=mock_user)
        service.social_repo.list_by_user_id = AsyncMock(return_value=[mock_social_account])

        payload = UserUpdate(nickname="새닉네임")
        result = await service.update_current_user(mock_user.auth_user_id, payload, "kakao")

        service.repo.update_user.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_raises_404_when_user_not_found(self, service):
        """사용자가 없으면 404를 반환합니다."""
        from fastapi import HTTPException
        from domains.my.schemas import UserUpdate

        service.repo.get_by_auth_user_id = AsyncMock(return_value=None)
        payload = UserUpdate(nickname="새닉네임")

        with pytest.raises(HTTPException) as exc_info:
            await service.update_current_user(uuid4(), payload, "kakao")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_422_when_no_changes(self, service, mock_user):
        """변경사항이 없으면 422를 반환합니다."""
        from fastapi import HTTPException
        from domains.my.schemas import UserUpdate

        service.repo.get_by_auth_user_id = AsyncMock(return_value=mock_user)
        payload = UserUpdate()  # 빈 페이로드

        with pytest.raises(HTTPException) as exc_info:
            await service.update_current_user(mock_user.auth_user_id, payload, "kakao")

        assert exc_info.value.status_code == 422
        assert "No changes" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_normalizes_phone_number_on_update(self, service, mock_user, mock_social_account):
        """전화번호 업데이트 시 정규화합니다."""
        from domains.my.schemas import UserUpdate

        service.repo.get_by_auth_user_id = AsyncMock(return_value=mock_user)
        service.repo.update_user = AsyncMock(return_value=mock_user)
        service.repo.update_auth_user_phone = AsyncMock()
        service.social_repo.list_by_user_id = AsyncMock(return_value=[mock_social_account])

        payload = UserUpdate(phone_number="01012345678")
        await service.update_current_user(mock_user.auth_user_id, payload, "kakao")

        # update_user가 정규화된 번호로 호출되었는지 확인
        call_args = service.repo.update_user.call_args
        assert call_args[0][1]["phone_number"] == "010-1234-5678"


class TestDeleteCurrentUser:
    """Tests for delete_current_user method."""

    @pytest.mark.asyncio
    async def test_deletes_user(self, service, mock_user):
        """사용자를 삭제합니다."""
        service.repo.get_by_auth_user_id = AsyncMock(return_value=mock_user)
        service.repo.delete_user = AsyncMock()

        await service.delete_current_user(mock_user.auth_user_id)

        service.repo.delete_user.assert_called_once_with(mock_user.id)
        service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_user_not_found(self, service):
        """사용자가 없으면 404를 반환합니다."""
        from fastapi import HTTPException

        service.repo.get_by_auth_user_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_current_user(uuid4())

        assert exc_info.value.status_code == 404


class TestMetrics:
    """Tests for metrics method."""

    @pytest.mark.asyncio
    async def test_returns_combined_metrics(self, service):
        """결합된 메트릭스를 반환합니다."""
        service.repo.metrics = AsyncMock(return_value={"total_users": 100})
        service.social_repo.count_by_provider = AsyncMock(return_value={"kakao": 60, "google": 40})

        result = await service.metrics()

        assert result["total_users"] == 100
        assert result["by_provider"]["kakao"] == 60
        assert result["by_provider"]["google"] == 40


class TestSelectSocialAccount:
    """Tests for _select_social_account static method."""

    def test_returns_none_when_no_accounts(self):
        """계정이 없으면 None을 반환합니다."""
        result = MyService._select_social_account([], "kakao")
        assert result is None

    def test_returns_matching_provider(self, mock_social_account):
        """매칭되는 provider의 계정을 반환합니다."""
        result = MyService._select_social_account([mock_social_account], "kakao")
        assert result == mock_social_account

    def test_returns_fallback_when_no_match(self, mock_social_account):
        """매칭되는 provider가 없으면 가장 최근 계정을 반환합니다."""
        mock_social_account.provider = "google"
        result = MyService._select_social_account([mock_social_account], "kakao")
        assert result == mock_social_account


class TestResolveUsername:
    """Tests for _resolve_username static method."""

    def test_returns_name_first(self, mock_user):
        """name이 있으면 name을 반환합니다."""
        result = MyService._resolve_username(mock_user, None)
        assert result == "테스트"

    def test_returns_username_when_no_name(self, mock_user):
        """name이 없으면 username을 반환합니다."""
        mock_user.name = None
        result = MyService._resolve_username(mock_user, None)
        assert result == "testuser"

    def test_returns_default_when_all_empty(self, mock_user):
        """모든 값이 없으면 기본값을 반환합니다."""
        mock_user.name = None
        mock_user.username = None
        result = MyService._resolve_username(mock_user, None)
        assert result == "사용자"


class TestResolveNickname:
    """Tests for _resolve_nickname static method."""

    def test_returns_nickname_first(self, mock_user):
        """nickname이 있으면 nickname을 반환합니다."""
        result = MyService._resolve_nickname(mock_user, None, "fallback")
        assert result == "테스트닉네임"

    def test_returns_username_when_no_nickname(self, mock_user):
        """nickname이 없으면 username을 반환합니다."""
        mock_user.nickname = None
        result = MyService._resolve_nickname(mock_user, None, "fallback")
        assert result == "testuser"

    def test_returns_fallback_when_all_empty(self, mock_user):
        """모든 값이 없으면 fallback을 반환합니다."""
        mock_user.nickname = None
        mock_user.username = None
        mock_user.name = None
        result = MyService._resolve_nickname(mock_user, None, "fallback")
        assert result == "fallback"


class TestCleanText:
    """Tests for _clean_text static method."""

    def test_returns_none_for_none(self):
        """None이면 None을 반환합니다."""
        assert MyService._clean_text(None) is None

    def test_strips_whitespace(self):
        """공백을 제거합니다."""
        assert MyService._clean_text("  hello  ") == "hello"

    def test_returns_none_for_empty_string(self):
        """빈 문자열이면 None을 반환합니다."""
        assert MyService._clean_text("   ") is None


class TestFormatPhoneNumber:
    """Tests for _format_phone_number static method."""

    def test_returns_none_for_empty(self):
        """빈 값이면 None을 반환합니다."""
        assert MyService._format_phone_number(None) is None
        assert MyService._format_phone_number("") is None

    def test_formats_11_digit_mobile(self):
        """11자리 휴대폰 번호를 포맷합니다."""
        assert MyService._format_phone_number("01012345678") == "010-1234-5678"

    def test_formats_10_digit_phone(self):
        """10자리 전화번호를 포맷합니다."""
        assert MyService._format_phone_number("0212345678") == "021-234-5678"

    def test_converts_international_format(self):
        """국제 형식(82)을 국내 형식으로 변환합니다."""
        assert MyService._format_phone_number("821012345678") == "010-1234-5678"

    def test_returns_original_for_invalid_format(self):
        """유효하지 않은 형식은 원본을 반환합니다."""
        assert MyService._format_phone_number("12345") == "12345"


class TestNormalizePhoneNumber:
    """Tests for _normalize_phone_number static method."""

    def test_normalizes_11_digit_mobile(self):
        """11자리 휴대폰 번호를 정규화합니다."""
        assert MyService._normalize_phone_number("01012345678") == "010-1234-5678"

    def test_normalizes_10_digit_mobile(self):
        """10자리 휴대폰 번호를 정규화합니다."""
        assert MyService._normalize_phone_number("0161234567") == "016-123-4567"

    def test_converts_international_format(self):
        """국제 형식(82)을 국내 형식으로 변환합니다."""
        assert MyService._normalize_phone_number("821012345678") == "010-1234-5678"

    def test_raises_for_invalid_format(self):
        """유효하지 않은 형식은 에러를 발생시킵니다."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            MyService._normalize_phone_number("12345")

        assert exc_info.value.status_code == 422
        assert "Invalid phone number" in exc_info.value.detail

    def test_raises_for_empty(self):
        """빈 값은 에러를 발생시킵니다."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            MyService._normalize_phone_number("")

        assert exc_info.value.status_code == 422


class TestToProfile:
    """Tests for _to_profile method."""

    def test_creates_profile_with_account(self, service, mock_user, mock_social_account):
        """소셜 계정이 있으면 프로필을 생성합니다."""
        result = service._to_profile(mock_user, [mock_social_account], current_provider="kakao")

        assert result.username == "테스트"
        assert result.nickname == "테스트닉네임"
        assert result.provider == "kakao"
        assert result.phone_number == "010-1234-5678"

    def test_creates_profile_without_account(self, service, mock_user):
        """소셜 계정이 없어도 프로필을 생성합니다."""
        result = service._to_profile(mock_user, [], current_provider="kakao")

        assert result.username == "테스트"
        assert result.provider == "kakao"
        assert result.last_login_at is None
