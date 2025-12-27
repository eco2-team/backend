"""Config 모듈 테스트."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPodIndex:
    """get_pod_index 함수 테스트 (StatefulSet 기반 동적 shard_id)."""

    def test_get_pod_index_default(self):
        """POD_NAME이 없으면 0 반환."""
        with patch.dict(os.environ, {}, clear=True):
            # 환경변수 제거
            os.environ.pop("POD_NAME", None)
            from config import get_pod_index

            assert get_pod_index() == 0

    def test_get_pod_index_from_statefulset_name(self):
        """StatefulSet Pod 이름에서 인덱스 추출."""
        from config import get_pod_index

        test_cases = [
            ("sse-gateway-0", 0),
            ("sse-gateway-1", 1),
            ("sse-gateway-2", 2),
            ("sse-gateway-10", 10),
            ("my-app-5", 5),
        ]

        for pod_name, expected_index in test_cases:
            with patch.dict(os.environ, {"POD_NAME": pod_name}):
                assert get_pod_index() == expected_index

    def test_get_pod_index_invalid_format(self):
        """잘못된 형식이면 0 반환."""
        from config import get_pod_index

        with patch.dict(os.environ, {"POD_NAME": "invalid-pod-name"}):
            assert get_pod_index() == 0

        with patch.dict(os.environ, {"POD_NAME": "sse-gateway"}):
            assert get_pod_index() == 0


class TestSettings:
    """Settings 클래스 테스트."""

    def test_default_settings(self):
        """기본 설정값 확인."""
        from config import Settings

        settings = Settings()

        assert settings.service_name == "sse-gateway"
        assert settings.service_version == "1.0.0"
        assert settings.environment == "development"
        assert settings.sse_shard_count >= 1
        assert settings.sse_shard_id >= 0  # property로 동적 계산
        assert settings.sse_keepalive_interval > 0
        assert settings.sse_max_wait_seconds > 0
        assert settings.sse_queue_maxsize > 0

    def test_settings_shard_count_from_env(self):
        """환경변수에서 shard_count 로드."""
        with patch.dict(
            os.environ,
            {
                "SSE_SHARD_COUNT": "8",
                "LOG_LEVEL": "DEBUG",
            },
        ):
            from config import Settings

            settings = Settings()
            assert settings.sse_shard_count == 8
            assert settings.log_level == "DEBUG"

    def test_settings_shard_id_from_pod_name(self):
        """sse_shard_id는 POD_NAME에서 동적으로 추출."""
        with patch.dict(os.environ, {"POD_NAME": "sse-gateway-3"}):
            from config import Settings

            settings = Settings()
            assert settings.sse_shard_id == 3  # POD_NAME에서 추출

    def test_get_settings_singleton(self):
        """get_settings 싱글톤 동작 확인."""
        from config import get_settings

        # 캐시 클리어
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2


class TestShardFunctions:
    """Shard 관련 함수 테스트."""

    def test_get_shard_for_job_deterministic(self):
        """동일 job_id는 동일 shard 반환."""
        from config import get_shard_for_job

        job_id = "test-job-123"
        shard1 = get_shard_for_job(job_id, shard_count=4)
        shard2 = get_shard_for_job(job_id, shard_count=4)

        assert shard1 == shard2
        assert 0 <= shard1 < 4

    def test_get_shard_for_job_distribution(self):
        """shard 분배 확인."""
        from config import get_shard_for_job

        shard_count = 4
        shards = set()

        # 다양한 job_id로 shard 분배 확인
        for i in range(100):
            job_id = f"job-{i}"
            shard = get_shard_for_job(job_id, shard_count=shard_count)
            assert 0 <= shard < shard_count
            shards.add(shard)

        # 최소 2개 이상의 다른 shard에 분배되어야 함
        assert len(shards) >= 2

    def test_get_shard_for_job_with_different_counts(self):
        """다른 shard_count에 대한 결과 확인."""
        from config import get_shard_for_job

        job_id = "test-job-456"

        shard_2 = get_shard_for_job(job_id, shard_count=2)
        shard_4 = get_shard_for_job(job_id, shard_count=4)
        shard_8 = get_shard_for_job(job_id, shard_count=8)

        assert 0 <= shard_2 < 2
        assert 0 <= shard_4 < 4
        assert 0 <= shard_8 < 8

    def test_get_sharded_stream_key(self):
        """Sharded stream key 생성 확인."""
        from config import get_sharded_stream_key

        job_id = "test-job-789"
        stream_key = get_sharded_stream_key(job_id, shard_count=4)

        assert stream_key.startswith("scan:events:")
        parts = stream_key.split(":")
        assert len(parts) == 3
        shard_id = int(parts[2])
        assert 0 <= shard_id < 4

    def test_get_sharded_stream_key_consistency(self):
        """동일 job_id는 동일 stream key."""
        from config import get_sharded_stream_key

        job_id = "consistent-job-id"
        key1 = get_sharded_stream_key(job_id, shard_count=4)
        key2 = get_sharded_stream_key(job_id, shard_count=4)

        assert key1 == key2
