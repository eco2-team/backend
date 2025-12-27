"""Event Router 이벤트 처리기.

Lua Script를 사용하여 원자적으로:
1. 발행 마킹 체크
2. State 조건부 갱신 (seq 비교)
3. Pub/Sub 발행
4. 발행 마킹 저장

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Event Router 처리 Lua Script
# ─────────────────────────────────────────────────────────────────

# State 갱신 + Pub/Sub 발행 (원자적)
PROCESS_EVENT_SCRIPT = """
local state_key = KEYS[1]      -- scan:state:{job_id}
local publish_key = KEYS[2]    -- router:published:{job_id}:{seq}
local channel = KEYS[3]        -- sse:events:{job_id}

local event_data = ARGV[1]     -- JSON 이벤트 데이터
local new_seq = tonumber(ARGV[2])
local state_ttl = tonumber(ARGV[3])
local published_ttl = tonumber(ARGV[4])

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    return 0  -- 이미 처리됨
end

-- State 조건부 갱신 (seq 비교)
local current = redis.call('GET', state_key)
if current then
    local cur_data = cjson.decode(current)
    local cur_seq = tonumber(cur_data.seq) or 0
    if new_seq <= cur_seq then
        -- seq가 낮거나 같아도 발행 마킹 (중복 처리 방지)
        redis.call('SETEX', publish_key, published_ttl, '1')
        return 0  -- 역순/중복 이벤트
    end
end

-- State 갱신
redis.call('SETEX', state_key, state_ttl, event_data)

-- Pub/Sub 발행
redis.call('PUBLISH', channel, event_data)

-- 발행 마킹
redis.call('SETEX', publish_key, published_ttl, '1')

return 1  -- 성공
"""


class EventProcessor:
    """이벤트 처리기.

    Redis Streams에서 읽은 이벤트를 처리:
    - State KV 갱신
    - Pub/Sub 발행
    - 멱등성 보장
    """

    def __init__(
        self,
        redis_client: "aioredis.Redis",
        state_key_prefix: str = "scan:state",
        published_key_prefix: str = "router:published",
        pubsub_channel_prefix: str = "sse:events",
        state_ttl: int = 3600,
        published_ttl: int = 7200,
    ) -> None:
        """초기화."""
        self._redis = redis_client
        self._state_key_prefix = state_key_prefix
        self._published_key_prefix = published_key_prefix
        self._pubsub_channel_prefix = pubsub_channel_prefix
        self._state_ttl = state_ttl
        self._published_ttl = published_ttl
        self._script: Any = None

    async def _ensure_script(self) -> None:
        """Lua Script 등록."""
        if self._script is None:
            self._script = self._redis.register_script(PROCESS_EVENT_SCRIPT)

    async def process_event(self, event: dict[str, Any]) -> bool:
        """이벤트 처리 (멱등성 보장).

        Args:
            event: Redis Streams 이벤트

        Returns:
            True if processed, False if skipped (duplicate or out-of-order)
        """
        await self._ensure_script()

        job_id = event.get("job_id")
        if not job_id:
            logger.warning("process_event_missing_job_id", extra={"event": event})
            return False

        seq = event.get("seq", 0)
        try:
            seq = int(seq)
        except (ValueError, TypeError):
            seq = 0

        # Redis 키
        state_key = f"{self._state_key_prefix}:{job_id}"
        publish_key = f"{self._published_key_prefix}:{job_id}:{seq}"
        channel = f"{self._pubsub_channel_prefix}:{job_id}"

        # 이벤트 JSON
        event_data = json.dumps(event, ensure_ascii=False)

        # Lua Script 실행
        result = await self._script(
            keys=[state_key, publish_key, channel],
            args=[event_data, seq, self._state_ttl, self._published_ttl],
        )

        if result == 1:
            logger.debug(
                "event_processed",
                extra={
                    "job_id": job_id,
                    "stage": event.get("stage"),
                    "seq": seq,
                    "channel": channel,
                },
            )
            return True
        else:
            logger.debug(
                "event_skipped",
                extra={
                    "job_id": job_id,
                    "stage": event.get("stage"),
                    "seq": seq,
                    "reason": "duplicate_or_out_of_order",
                },
            )
            return False

    async def process_batch(self, events: list[dict[str, Any]]) -> int:
        """배치 이벤트 처리.

        Args:
            events: 이벤트 목록

        Returns:
            처리된 이벤트 수
        """
        processed_count = 0
        for event in events:
            try:
                if await self.process_event(event):
                    processed_count += 1
            except Exception as e:
                logger.error(
                    "process_event_error",
                    extra={
                        "job_id": event.get("job_id"),
                        "error": str(e),
                    },
                )
        return processed_count
