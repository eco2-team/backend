"""Redis Adapters 단위 테스트.

DIP 적용으로 Redis 클라이언트를 Mock하여 어댑터 로직을 테스트합니다.
"""

import json
import time
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest

from apps.auth.infrastructure.persistence_redis.adapters.state_store_redis import (
    RedisStateStore,
)
from apps.auth.infrastructure.persistence_redis.adapters.token_blacklist_redis import (
    RedisTokenBlacklist,
)
from apps.auth.infrastructure.persistence_redis.adapters.users_token_store_redis import (
    RedisUsersTokenStore,
)
from apps.auth.infrastructure.persistence_redis.constants import (
    BLACKLIST_KEY_PREFIX,
    STATE_KEY_PREFIX,
    TOKEN_META_KEY_PREFIX,
    USER_TOKENS_KEY_PREFIX,
)
from apps.auth.application.oauth.ports import OAuthState


class TestRedisStateStore:
    """RedisStateStore 테스트."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def store(self, mock_redis: AsyncMock) -> RedisStateStore:
        return RedisStateStore(redis=mock_redis)

    @pytest.mark.asyncio
    async def test_save_state(
        self,
        store: RedisStateStore,
        mock_redis: AsyncMock,
    ) -> None:
        """상태 저장 테스트."""
        # Arrange
        state = "test-state-12345"
        oauth_state = OAuthState(
            provider="google",
            redirect_uri="http://localhost/callback",
            code_verifier="code-verifier-123",
            device_id="device-abc",
            frontend_origin="http://localhost:3000",
        )

        # Act
        await store.save(state, oauth_state, ttl_seconds=600)

        # Assert
        expected_key = f"{STATE_KEY_PREFIX}{state}"
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args

        assert call_args[0][0] == expected_key  # key
        assert call_args[0][1] == 600  # ttl

        saved_data = json.loads(call_args[0][2])
        assert saved_data["provider"] == "google"
        assert saved_data["redirect_uri"] == "http://localhost/callback"
        assert saved_data["code_verifier"] == "code-verifier-123"
        assert saved_data["device_id"] == "device-abc"
        assert saved_data["frontend_origin"] == "http://localhost:3000"

    @pytest.mark.asyncio
    async def test_consume_existing_state(
        self,
        store: RedisStateStore,
        mock_redis: AsyncMock,
    ) -> None:
        """기존 상태 조회 및 삭제 테스트."""
        # Arrange
        state = "test-state-67890"
        stored_data = json.dumps(
            {
                "provider": "kakao",
                "redirect_uri": "http://localhost/callback",
                "code_verifier": "verifier-456",
                "device_id": None,
                "frontend_origin": None,
            }
        )
        mock_redis.get.return_value = stored_data

        # Act
        result = await store.consume(state)

        # Assert
        expected_key = f"{STATE_KEY_PREFIX}{state}"
        mock_redis.get.assert_called_once_with(expected_key)
        mock_redis.delete.assert_called_once_with(expected_key)

        assert result is not None
        assert result.provider == "kakao"
        assert result.code_verifier == "verifier-456"

    @pytest.mark.asyncio
    async def test_consume_nonexistent_state(
        self,
        store: RedisStateStore,
        mock_redis: AsyncMock,
    ) -> None:
        """존재하지 않는 상태 조회 테스트."""
        # Arrange
        mock_redis.get.return_value = None

        # Act
        result = await store.consume("nonexistent-state")

        # Assert
        assert result is None
        mock_redis.delete.assert_not_called()


class TestRedisTokenBlacklist:
    """RedisTokenBlacklist 테스트.

    Note:
        add() 메서드는 제거되었습니다 (이벤트 기반으로 전환).
        auth_worker가 RabbitMQ 이벤트를 소비하여 Redis에 저장합니다.
    """

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def blacklist(self, mock_redis: AsyncMock) -> RedisTokenBlacklist:
        return RedisTokenBlacklist(redis=mock_redis)

    @pytest.mark.asyncio
    async def test_contains_blacklisted_token(
        self,
        blacklist: RedisTokenBlacklist,
        mock_redis: AsyncMock,
    ) -> None:
        """블랙리스트에 있는 토큰 확인 테스트."""
        # Arrange
        mock_redis.exists.return_value = 1

        # Act
        result = await blacklist.contains("blacklisted-jti")

        # Assert
        expected_key = f"{BLACKLIST_KEY_PREFIX}blacklisted-jti"
        mock_redis.exists.assert_called_once_with(expected_key)
        assert result is True

    @pytest.mark.asyncio
    async def test_contains_non_blacklisted_token(
        self,
        blacklist: RedisTokenBlacklist,
        mock_redis: AsyncMock,
    ) -> None:
        """블랙리스트에 없는 토큰 확인 테스트."""
        # Arrange
        mock_redis.exists.return_value = 0

        # Act
        result = await blacklist.contains("valid-jti")

        # Assert
        assert result is False


class TestRedisUsersTokenStore:
    """RedisUsersTokenStore 테스트."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def store(self, mock_redis: AsyncMock) -> RedisUsersTokenStore:
        return RedisUsersTokenStore(redis=mock_redis)

    @pytest.mark.asyncio
    async def test_register_token(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """토큰 등록 테스트."""
        # Arrange
        user_id = uuid4()
        jti = "new-refresh-jti"
        issued_at = int(time.time())
        expires_at = issued_at + 604800  # 7일

        # Act
        await store.register(
            user_id=user_id,
            jti=jti,
            issued_at=issued_at,
            expires_at=expires_at,
            device_id="test-device",
            user_agent="Mozilla/5.0",
        )

        # Assert
        expected_user_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        expected_meta_key = f"{TOKEN_META_KEY_PREFIX}{jti}"

        # sadd로 사용자 토큰 Set에 추가 확인
        mock_redis.sadd.assert_called_once_with(expected_user_key, jti)
        # expire로 TTL 설정 확인
        mock_redis.expire.assert_called_once()
        # setex로 메타데이터 저장 확인
        mock_redis.setex.assert_called_once()

        # 메타데이터 내용 확인
        meta_call = mock_redis.setex.call_args
        assert meta_call[0][0] == expected_meta_key
        meta_data = json.loads(meta_call[0][2])
        assert meta_data["device_id"] == "test-device"
        assert meta_data["user_agent"] == "Mozilla/5.0"

    @pytest.mark.asyncio
    async def test_contains_existing_token(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """토큰 존재 확인 테스트."""
        # Arrange
        user_id = uuid4()
        mock_redis.sismember.return_value = True

        # Act
        result = await store.contains(user_id, "existing-jti")

        # Assert
        expected_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        mock_redis.sismember.assert_called_once_with(expected_key, "existing-jti")
        assert result is True

    @pytest.mark.asyncio
    async def test_contains_nonexistent_token(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """토큰 미존재 확인 테스트."""
        # Arrange
        user_id = uuid4()
        mock_redis.sismember.return_value = False

        # Act
        result = await store.contains(user_id, "nonexistent-jti")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_token(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """토큰 삭제 테스트."""
        # Arrange
        user_id = uuid4()
        jti = "jti-to-remove"

        # Act
        await store.remove(user_id, jti)

        # Assert
        expected_user_key = f"{USER_TOKENS_KEY_PREFIX}{user_id}"
        expected_meta_key = f"{TOKEN_META_KEY_PREFIX}{jti}"

        mock_redis.srem.assert_called_once_with(expected_user_key, jti)
        mock_redis.delete.assert_called_once_with(expected_meta_key)

    @pytest.mark.asyncio
    async def test_get_metadata_existing(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """메타데이터 조회 테스트 - 존재하는 경우."""
        # Arrange
        jti = "test-jti"
        mock_redis.get.return_value = json.dumps(
            {
                "device_id": "device-123",
                "user_agent": "TestAgent/1.0",
                "issued_at": 1234567890,
            }
        )

        # Act
        result = await store.get_metadata(jti)

        # Assert
        expected_key = f"{TOKEN_META_KEY_PREFIX}{jti}"
        mock_redis.get.assert_called_once_with(expected_key)

        assert result is not None
        assert result.device_id == "device-123"
        assert result.user_agent == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent(
        self,
        store: RedisUsersTokenStore,
        mock_redis: AsyncMock,
    ) -> None:
        """메타데이터 조회 테스트 - 존재하지 않는 경우."""
        # Arrange
        mock_redis.get.return_value = None

        # Act
        result = await store.get_metadata("nonexistent-jti")

        # Assert
        assert result is None
