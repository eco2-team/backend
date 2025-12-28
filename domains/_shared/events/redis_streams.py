"""Redis Streams 기반 이벤트 발행 모듈.

Event Router + Pub/Sub 아키텍처:
- Worker는 Redis Streams에 이벤트 발행 (멱등성 보장)
- Event Router가 Streams를 소비하여 Pub/Sub로 발행
- SSE-Gateway는 Pub/Sub를 구독하여 클라이언트에게 전달

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────

STREAM_PREFIX = "scan:events"
STATE_KEY_PREFIX = "scan:state:"  # State KV (Event Router가 관리)
PUBLISHED_KEY_PREFIX = "published:"  # 멱등성 마킹
STREAM_MAXLEN = 10000  # Stream당 최대 메시지 수
PUBLISHED_TTL = 7200  # 발행 마킹 TTL (2시간)
# NOTE: State TTL은 Event Router (config.py)에서 관리

# Stage 순서 (단조증가 seq)
STAGE_ORDER = {
    "queued": 0,
    "vision": 1,
    "rule": 2,
    "answer": 3,
    "reward": 4,
    "done": 5,
}

# 샤딩 설정 (환경 변수로 오버라이드 가능)
DEFAULT_SHARD_COUNT = int(os.environ.get("SSE_SHARD_COUNT", "4"))

# ─────────────────────────────────────────────────────────────────
# 멱등성 Lua Script
# ─────────────────────────────────────────────────────────────────

# Worker → Streams 멱등성 XADD
# 동일한 job_id + stage + seq 조합은 한 번만 발행
# NOTE: State는 Event Router만 갱신 (단일 권위 원칙)
IDEMPOTENT_XADD_SCRIPT = """
local publish_key = KEYS[1]  -- published:{job_id}:{stage}:{seq}
local stream_key = KEYS[2]   -- scan:events:{shard}

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    local existing_msg_id = redis.call('GET', publish_key)
    return {0, existing_msg_id}  -- 이미 발행됨
end

-- XADD 실행 (MAXLEN ~ 로 효율적 trim)
local msg_id = redis.call('XADD', stream_key, 'MAXLEN', '~', ARGV[1],
    '*',
    'job_id', ARGV[2],
    'stage', ARGV[3],
    'status', ARGV[4],
    'seq', ARGV[5],
    'ts', ARGV[6],
    'progress', ARGV[7],
    'result', ARGV[8]
)

-- 발행 마킹 (TTL: 2시간)
redis.call('SETEX', publish_key, ARGV[9], msg_id)

-- NOTE: State 갱신은 Event Router가 담당
-- Worker는 XADD만 수행하여 "단일 State 권위" 보장

return {1, msg_id}  -- 새로 발행됨
"""


def get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산.

    일관된 해시를 위해 hashlib.md5 사용 (Python hash()는 세션마다 다름).

    Args:
        job_id: Celery task ID (UUID)
        shard_count: 전체 shard 수 (None이면 기본값 사용)

    Returns:
        shard ID (0-based)
    """
    import hashlib

    if shard_count is None:
        shard_count = DEFAULT_SHARD_COUNT
    # MD5 해시의 첫 8바이트를 정수로 변환
    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % shard_count


def get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """Sharded Stream key 생성.

    Args:
        job_id: Chain의 root task ID
        shard_count: 전체 shard 수

    Returns:
        Sharded Stream key (예: "scan:events:2")
    """
    shard = get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"


# ─────────────────────────────────────────────────────────────────
# Worker용: 동기 이벤트 발행 (Celery Task에서 호출)
# ─────────────────────────────────────────────────────────────────


def publish_stage_event(
    redis_client: "redis.Redis[Any]",
    job_id: str,
    stage: str,
    status: str,
    result: dict | None = None,
    progress: int | None = None,
) -> str:
    """Worker가 호출: stage 이벤트를 Redis Streams에 발행 (멱등성 보장).

    Lua Script를 사용하여 원자적으로:
    1. 이미 발행했는지 체크 (published:{job_id}:{stage}:{seq})
    2. 미발행이면 XADD 실행
    3. 발행 마킹 저장

    NOTE: State 갱신은 Event Router가 담당 (단일 권위 원칙)
    Celery Task 재시도 시에도 중복 발행 없음.

    Args:
        redis_client: 동기 Redis 클라이언트 (Celery Worker용)
        job_id: Chain의 root task ID
        stage: 단계명 (queued, vision, rule, answer, reward, done)
        status: 상태 (started, completed, failed)
        result: 완료 시 결과 데이터 (선택)
        progress: 진행률 0~100 (선택)

    Returns:
        발행된 메시지 ID (예: "1735123456789-0")

    Example:
        >>> from domains._shared.events import publish_stage_event
        >>> publish_stage_event(redis, job_id, "vision", "started", progress=0)
        >>> # ... vision 처리 ...
        >>> publish_stage_event(redis, job_id, "vision", "completed", progress=25)
    """
    stream_key = get_stream_key(job_id)

    # 단조증가 seq 계산 (stage 기준 + status 보정)
    base_seq = STAGE_ORDER.get(stage, 99) * 10
    seq = base_seq + (1 if status == "completed" else 0)

    # 멱등성 키
    publish_key = f"{PUBLISHED_KEY_PREFIX}{job_id}:{stage}:{seq}"

    # 이벤트 데이터
    ts = str(time.time())
    progress_str = str(progress) if progress is not None else ""
    result_str = json.dumps(result, ensure_ascii=False) if result else ""

    # Lua Script 실행 (State 갱신 없이 XADD만)
    script = redis_client.register_script(IDEMPOTENT_XADD_SCRIPT)
    result_tuple = script(
        keys=[publish_key, stream_key],
        args=[
            str(STREAM_MAXLEN),  # ARGV[1]: maxlen
            job_id,  # ARGV[2]: job_id
            stage,  # ARGV[3]: stage
            status,  # ARGV[4]: status
            str(seq),  # ARGV[5]: seq
            ts,  # ARGV[6]: ts
            progress_str,  # ARGV[7]: progress
            result_str,  # ARGV[8]: result
            str(PUBLISHED_TTL),  # ARGV[9]: published TTL
        ],
    )

    is_new, msg_id = result_tuple
    if isinstance(msg_id, bytes):
        msg_id = msg_id.decode()

    shard = get_shard_for_job(job_id)
    if is_new:
        logger.debug(
            "stage_event_published",
            extra={
                "job_id": job_id,
                "shard": shard,
                "stream_key": stream_key,
                "stage": stage,
                "status": status,
                "seq": seq,
                "msg_id": msg_id,
            },
        )
    else:
        logger.debug(
            "stage_event_duplicate_skipped",
            extra={
                "job_id": job_id,
                "shard": shard,
                "stage": stage,
                "seq": seq,
                "existing_msg_id": msg_id,
            },
        )

    return msg_id


# ─────────────────────────────────────────────────────────────────
# DEPRECATED: 이전 아키텍처 호환 (Event Router + Pub/Sub로 대체됨)
# ─────────────────────────────────────────────────────────────────


async def subscribe_events(redis_client, job_id: str, timeout: int = 300):
    """DEPRECATED: 직접 Redis Streams 구독은 더 이상 사용되지 않습니다.

    새로운 아키텍처:
    - POST /api/v1/scan → job_id 반환
    - GET /api/v1/stream?job_id=xxx → SSE Gateway (Pub/Sub 구독)
    - GET /api/v1/scan/result/{job_id} → 결과 조회

    이 함수는 하위 호환성을 위해 유지되지만, 사용을 권장하지 않습니다.
    대신 SSE Gateway (/api/v1/stream)를 사용하세요.

    참조: docs/blogs/async/34-sse-HA-architecture.md
    """
    import warnings

    warnings.warn(
        "subscribe_events is deprecated. Use SSE Gateway (/api/v1/stream) instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Stub: 즉시 종료 (실제 구독 없음)
    yield {
        "type": "error",
        "error": "DEPRECATED",
        "message": "subscribe_events is deprecated. Use /api/v1/stream endpoint.",
    }
