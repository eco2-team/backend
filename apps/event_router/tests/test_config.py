"""Config 모듈 테스트."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSettings:
    """Settings 클래스 테스트."""

    def test_default_settings(self):
        """기본 설정값 확인."""
        from config import Settings

        settings = Settings()

        assert settings.service_name == "event-router"
        assert settings.service_version == "1.0.0"
        assert settings.environment == "development"
        assert settings.shard_count >= 1
        assert settings.xread_block_ms > 0
        assert settings.xread_count > 0

    def test_settings_from_env(self):
        """환경변수에서 설정 로드."""
        with patch.dict(
            os.environ,
            {
                "LOG_LEVEL": "DEBUG",
                "REDIS_STREAMS_URL": "redis://test-streams:6379/0",
                "REDIS_PUBSUB_URL": "redis://test-pubsub:6379/1",
                "SHARD_COUNT": "8",
            },
        ):
            from config import Settings

            settings = Settings()
            assert settings.log_level == "DEBUG"
            assert settings.redis_streams_url == "redis://test-streams:6379/0"
            assert settings.redis_pubsub_url == "redis://test-pubsub:6379/1"
            assert settings.shard_count == 8

    def test_get_settings_singleton(self):
        """get_settings 싱글톤 동작 확인."""
        from config import get_settings

        # 캐시 클리어
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_stream_prefix(self):
        """Stream 접두사 확인."""
        from config import Settings

        settings = Settings()
        assert settings.stream_prefix == "scan:events"

    def test_pubsub_channel_prefix(self):
        """Pub/Sub 채널 접두사 확인."""
        from config import Settings

        settings = Settings()
        assert settings.pubsub_channel_prefix == "sse:events"

    def test_state_key_prefix(self):
        """State KV 접두사 확인."""
        from config import Settings

        settings = Settings()
        assert settings.state_key_prefix == "scan:state"

    def test_consumer_group_settings(self):
        """Consumer Group 설정 확인."""
        from config import Settings

        settings = Settings()
        assert settings.consumer_group == "eventrouter"
        assert settings.reclaim_interval_seconds > 0
        assert settings.reclaim_min_idle_ms > 0
