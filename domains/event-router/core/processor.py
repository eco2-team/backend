"""Event Router 이벤트 처리기.

Redis 역할 분리:
- Streams Redis: State KV 갱신 (scan:state:{job_id}) - 내구성
- Pub/Sub Redis: 실시간 브로드캐스트 (sse:events:{job_id})

Lua Script는 Streams Redis에서만 실행 (State + 발행 마킹)
Pub/Sub는 별도 Redis로 PUBLISH

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
# State 갱신 Lua Script (Streams Redis에서 실행)
# ─────────────────────────────────────────────────────────────────

# State 조건부 갱신 + 발행 마킹 (원자적)
# Pub/Sub는 별도 Redis로 분리했으므로 여기서는 State만 처리
UPDATE_STATE_SCRIPT = """
local state_key = KEYS[1]      -- scan:state:{job_id}
local publish_key = KEYS[2]    -- router:published:{job_id}:{seq}

local event_data = ARGV[1]     -- JSON 이벤트 데이터
local new_seq = tonumber(ARGV[2])
local state_ttl = tonumber(ARGV[3])
local published_ttl = tonumber(ARGV[4])

-- 이미 처리했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    return 0  -- 이미 처리됨
end

-- State 조건부 갱신 (seq 비교)
local current = redis.call('GET', state_key)
if current then
    local cur_data = cjson.decode(current)
    local cur_seq = tonumber(cur_data.seq) or 0
    if new_seq <= cur_seq then
        -- seq가 낮거나 같아도 처리 마킹 (중복 처리 방지)
        redis.call('SETEX', publish_key, published_ttl, '1')
        return 0  -- 역순/중복 이벤트
    end
end

-- State 갱신 (내구성 Redis에 저장)
redis.call('SETEX', state_key, state_ttl, event_data)

-- 처리 마킹
redis.call('SETEX', publish_key, published_ttl, '1')

return 1  -- State 갱신됨 → Pub/Sub 발행 필요
"""


class EventProcessor:
    """이벤트 처리기.

    Redis Streams에서 읽은 이벤트를 처리:
    - State KV 갱신 (Streams Redis - 내구성)
    - Pub/Sub 발행 (Pub/Sub Redis - 실시간)
    - 멱등성 보장
    """

    def __init__(
        self,
        streams_client: "aioredis.Redis",
        pubsub_client: "aioredis.Redis",
        state_key_prefix: str = "scan:state",
        published_key_prefix: str = "router:published",
        pubsub_channel_prefix: str = "sse:events",
        state_ttl: int = 3600,
        published_ttl: int = 7200,
    ) -> None:
        """초기화.

        Args:
            streams_client: Streams Redis (State KV + 발행 마킹)
            pubsub_client: Pub/Sub Redis (PUBLISH only)
        """
        self._streams_redis = streams_client
        self._pubsub_redis = pubsub_client
        self._state_key_prefix = state_key_prefix
        self._published_key_prefix = published_key_prefix
        self._pubsub_channel_prefix = pubsub_channel_prefix
        self._state_ttl = state_ttl
        self._published_ttl = published_ttl
        self._script: Any = None

    async def _ensure_script(self) -> None:
        """Lua Script 등록 (Streams Redis에)."""
        if self._script is None:
            self._script = self._streams_redis.register_script(UPDATE_STATE_SCRIPT)

    async def process_event(self, event: dict[str, Any]) -> bool:
        """이벤트 처리 (멱등성 보장).

        1. Streams Redis에서 State 갱신 (Lua Script)
        2. State 갱신 성공 시 Pub/Sub Redis로 발행

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

        # Step 1: State 갱신 (Streams Redis - Lua Script)
        result = await self._script(
            keys=[state_key, publish_key],
            args=[event_data, seq, self._state_ttl, self._published_ttl],
        )

        if result == 1:
            # Step 2: Pub/Sub 발행 (별도 Redis)
            try:
                await self._pubsub_redis.publish(channel, event_data)
                logger.debug(
                    "event_processed",
                    extra={
                        "job_id": job_id,
                        "stage": event.get("stage"),
                        "seq": seq,
                        "channel": channel,
                    },
                )
            except Exception as e:
                # Pub/Sub 실패해도 State는 이미 갱신됨
                # SSE 클라이언트는 State polling으로 복구 가능
                logger.warning(
                    "pubsub_publish_failed",
                    extra={
                        "job_id": job_id,
                        "seq": seq,
                        "channel": channel,
                        "error": str(e),
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
