"""Redis Streams 이벤트 발행.

scan API 전용 - domains 의존성 제거.

Event Router + Pub/Sub 아키텍처:
- scan API/Worker → Redis Streams (XADD)
- Event Router → Streams 소비 → Pub/Sub 발행
- SSE Gateway → Pub/Sub 구독 → 클라이언트 전달
"""

from __future__ import annotations

import hashlib
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
PUBLISHED_KEY_PREFIX = "published:"
STREAM_MAXLEN = 10000
PUBLISHED_TTL = 7200  # 2시간

# Stage 순서 (단조증가 seq)
STAGE_ORDER = {
    "queued": 0,
    "vision": 1,
    "rule": 2,
    "answer": 3,
    "reward": 4,
    "done": 5,
}

# 샤딩 설정
DEFAULT_SHARD_COUNT = int(os.environ.get("SSE_SHARD_COUNT", "4"))


# ─────────────────────────────────────────────────────────────────
# 멱등성 Lua Script
# ─────────────────────────────────────────────────────────────────

IDEMPOTENT_XADD_SCRIPT = """
local publish_key = KEYS[1]
local stream_key = KEYS[2]

if redis.call('EXISTS', publish_key) == 1 then
    local existing_msg_id = redis.call('GET', publish_key)
    return {0, existing_msg_id}
end

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

redis.call('SETEX', publish_key, ARGV[9], msg_id)

return {1, msg_id}
"""


# ─────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────


def get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산.

    Args:
        job_id: 작업 ID (UUID)
        shard_count: 전체 shard 수

    Returns:
        shard ID (0-based)
    """
    if shard_count is None:
        shard_count = DEFAULT_SHARD_COUNT

    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % shard_count


def get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """Sharded Stream key 생성.

    Args:
        job_id: 작업 ID
        shard_count: 전체 shard 수

    Returns:
        Sharded Stream key (예: "scan:events:2")
    """
    shard = get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"


# ─────────────────────────────────────────────────────────────────
# 이벤트 발행
# ─────────────────────────────────────────────────────────────────


def publish_stage_event(
    redis_client: "redis.Redis[Any]",
    job_id: str,
    stage: str,
    status: str,
    progress: int | None = None,
    result: dict | None = None,
) -> str:
    """stage 이벤트를 Redis Streams에 발행 (멱등성 보장).

    Lua Script를 사용하여 원자적으로:
    1. 이미 발행했는지 체크
    2. 미발행이면 XADD 실행
    3. 발행 마킹 저장

    Args:
        redis_client: 동기 Redis 클라이언트
        job_id: 작업 ID
        stage: 단계명 (queued, vision, rule, answer, reward, done)
        status: 상태 (started, completed, failed)
        progress: 진행률 0~100
        result: 결과 데이터

    Returns:
        발행된 메시지 ID
    """
    stream_key = get_stream_key(job_id)

    # 단조증가 seq 계산
    base_seq = STAGE_ORDER.get(stage, 99) * 10
    seq = base_seq + (1 if status == "completed" else 0)

    # 멱등성 키
    publish_key = f"{PUBLISHED_KEY_PREFIX}{job_id}:{stage}:{seq}"

    # 이벤트 데이터
    ts = str(time.time())
    progress_str = str(progress) if progress is not None else ""
    result_str = json.dumps(result, ensure_ascii=False) if result else ""

    # Lua Script 실행
    script = redis_client.register_script(IDEMPOTENT_XADD_SCRIPT)
    result_tuple = script(
        keys=[publish_key, stream_key],
        args=[
            str(STREAM_MAXLEN),
            job_id,
            stage,
            status,
            str(seq),
            ts,
            progress_str,
            result_str,
            str(PUBLISHED_TTL),
        ],
    )

    is_new, msg_id = result_tuple
    if isinstance(msg_id, bytes):
        msg_id = msg_id.decode()

    if is_new:
        logger.debug(
            "stage_event_published",
            extra={
                "job_id": job_id,
                "stage": stage,
                "status": status,
                "msg_id": msg_id,
            },
        )
    else:
        logger.debug(
            "stage_event_duplicate_skipped",
            extra={
                "job_id": job_id,
                "stage": stage,
                "existing_msg_id": msg_id,
            },
        )

    return msg_id
