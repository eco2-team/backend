"""Users domain unit tests."""

from uuid import uuid4

from apps.users.domain.entities.user import User
from apps.users.domain.services.user_service import UserService


class TestUserService:
    """UserService 단위 테스트."""

    def test_validate_and_normalize_phone_valid(self):
        """유효한 전화번호 검증 (하이픈 포함)."""
        service = UserService()
        result = service.validate_and_normalize_phone("010-1234-5678")
        assert result.is_valid is True
        assert result.normalized == "010-1234-5678"

    def test_validate_and_normalize_phone_digits_only(self):
        """숫자만 있는 전화번호."""
        service = UserService()
        result = service.validate_and_normalize_phone("01012345678")
        assert result.is_valid is True
        assert result.normalized == "010-1234-5678"

    def test_validate_and_normalize_phone_international(self):
        """국제번호 형식."""
        service = UserService()
        result = service.validate_and_normalize_phone("+82-10-1234-5678")
        assert result.is_valid is True
        assert result.normalized == "010-1234-5678"

    def test_validate_and_normalize_phone_old_format(self):
        """구형 전화번호 (10자리)."""
        service = UserService()
        result = service.validate_and_normalize_phone("011-123-4567")
        assert result.is_valid is True
        assert result.normalized == "011-123-4567"

    def test_validate_and_normalize_phone_empty(self):
        """빈 전화번호."""
        service = UserService()
        result = service.validate_and_normalize_phone("")
        assert result.is_valid is False
        assert result.error == "Invalid phone number format"

    def test_validate_and_normalize_phone_invalid(self):
        """잘못된 전화번호."""
        service = UserService()
        result = service.validate_and_normalize_phone("invalid")
        assert result.is_valid is False
        assert result.error == "Invalid phone number format"

    def test_resolve_display_name_with_nickname(self):
        """닉네임이 있으면 닉네임 반환."""
        user = User(
            id=uuid4(),
            nickname="닉네임",
            name="홍길동",
            email="test@test.com",
        )
        result = UserService.resolve_display_name(user)
        assert result == "닉네임"

    def test_resolve_display_name_fallback_to_name(self):
        """닉네임이 없으면 name 반환."""
        user = User(
            id=uuid4(),
            nickname=None,
            name="홍길동",
            email="test@test.com",
        )
        result = UserService.resolve_display_name(user)
        assert result == "홍길동"

    def test_resolve_display_name_default(self):
        """둘 다 없으면 기본값."""
        user = User(
            id=uuid4(),
            nickname=None,
            name=None,
            email="test@test.com",
        )
        result = UserService.resolve_display_name(user)
        assert result == "사용자"

    def test_resolve_nickname_with_nickname(self):
        """닉네임 있으면 닉네임 반환."""
        user = User(
            id=uuid4(),
            nickname="닉네임",
            name="이름",
            email="test@test.com",
        )
        result = UserService.resolve_nickname(user, fallback="기본")
        assert result == "닉네임"

    def test_resolve_nickname_fallback_to_name(self):
        """닉네임 없으면 name 반환."""
        user = User(
            id=uuid4(),
            nickname=None,
            name="이름",
            email="test@test.com",
        )
        result = UserService.resolve_nickname(user, fallback="기본")
        assert result == "이름"

    def test_resolve_nickname_fallback(self):
        """모두 없으면 fallback 반환."""
        user = User(
            id=uuid4(),
            nickname=None,
            name=None,
            email="test@test.com",
        )
        result = UserService.resolve_nickname(user, fallback="기본값")
        assert result == "기본값"

    def test_format_phone_for_display(self):
        """전화번호 포맷팅."""
        result = UserService.format_phone_for_display("01012345678")
        assert result == "010-1234-5678"

    def test_format_phone_for_display_none(self):
        """None 전화번호 포맷팅."""
        result = UserService.format_phone_for_display(None)
        assert result is None

    def test_format_phone_for_display_already_formatted(self):
        """이미 포맷된 전화번호."""
        result = UserService.format_phone_for_display("010-1234-5678")
        assert result == "010-1234-5678"


class TestUser:
    """User 엔티티 단위 테스트."""

    def test_update_profile(self):
        """프로필 업데이트."""
        user = User(id=uuid4())
        user.update_profile(nickname="새닉네임", phone_number="010-1234-5678")
        assert user.nickname == "새닉네임"
        assert user.phone_number == "010-1234-5678"

    def test_update_login_time(self):
        """로그인 시간 업데이트."""
        user = User(id=uuid4())
        assert user.last_login_at is None
        user.update_login_time()
        assert user.last_login_at is not None

    def test_display_name_property(self):
        """display_name 프로퍼티 테스트."""
        # 닉네임 있음
        user1 = User(id=uuid4(), nickname="닉네임", name="이름")
        assert user1.display_name == "닉네임"

        # 닉네임 없음, 이름 있음
        user2 = User(id=uuid4(), nickname=None, name="이름")
        assert user2.display_name == "이름"

        # 둘 다 없음
        user3 = User(id=uuid4(), nickname=None, name=None)
        assert user3.display_name == "사용자"
