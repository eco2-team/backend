"""RedisBlacklistStore 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from apps.auth_worker.infrastructure.persistence_redis.blacklist_store_redis import (
    BLACKLIST_KEY_PREFIX,
    RedisBlacklistStore,
)


class TestRedisBlacklistStore:
    """RedisBlacklistStore 테스트."""

    @pytest.fixture
    def store(self, mock_redis: AsyncMock) -> RedisBlacklistStore:
        """테스트용 Store 인스턴스."""
        return RedisBlacklistStore(mock_redis)

    @pytest.mark.asyncio
    async def test_add_with_valid_ttl(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """유효한 TTL로 추가."""
        jti = "test-jti-123"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await store.add(jti, expires_at, user_id="user-1", reason="logout")

        mock_redis.setex.assert_awaited_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"{BLACKLIST_KEY_PREFIX}{jti}"
        assert 3500 <= call_args[0][1] <= 3600  # TTL 약 1시간

    @pytest.mark.asyncio
    async def test_add_with_naive_datetime(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """timezone 없는 datetime도 처리."""
        jti = "test-jti-naive"
        expires_at = datetime.now() + timedelta(hours=1)  # naive datetime

        await store.add(jti, expires_at)

        mock_redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_expired_token_skips(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """이미 만료된 토큰은 저장 안함."""
        jti = "expired-jti"
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)  # 과거

        await store.add(jti, expires_at)

        mock_redis.setex.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_contains_returns_true(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """블랙리스트에 있으면 True."""
        mock_redis.exists.return_value = 1
        jti = "existing-jti"

        result = await store.contains(jti)

        assert result is True
        mock_redis.exists.assert_awaited_once_with(f"{BLACKLIST_KEY_PREFIX}{jti}")

    @pytest.mark.asyncio
    async def test_contains_returns_false(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """블랙리스트에 없으면 False."""
        mock_redis.exists.return_value = 0
        jti = "nonexistent-jti"

        result = await store.contains(jti)

        assert result is False

    @pytest.mark.asyncio
    async def test_remove(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """블랙리스트에서 제거."""
        jti = "remove-jti"

        await store.remove(jti)

        mock_redis.delete.assert_awaited_once_with(f"{BLACKLIST_KEY_PREFIX}{jti}")

    @pytest.mark.asyncio
    async def test_add_stores_metadata(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """메타데이터가 저장됨."""
        import json

        jti = "metadata-jti"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await store.add(jti, expires_at, user_id="user-123", reason="security")

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])

        assert stored_data["user_id"] == "user-123"
        assert stored_data["reason"] == "security"
        assert "blacklisted_at" in stored_data
        assert "expires_at" in stored_data

    @pytest.mark.asyncio
    async def test_add_default_reason(
        self,
        store: RedisBlacklistStore,
        mock_redis: AsyncMock,
    ) -> None:
        """reason 없으면 'logout' 기본값."""
        import json

        jti = "default-reason-jti"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await store.add(jti, expires_at)

        call_args = mock_redis.setex.call_args
        stored_data = json.loads(call_args[0][2])

        assert stored_data["reason"] == "logout"
