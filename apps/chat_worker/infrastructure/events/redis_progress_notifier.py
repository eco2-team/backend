"""Redis Progress Notifier - ProgressNotifierPort 구현체.

SSE 스트리밍을 위한 Redis Streams 이벤트 발행.
scan_worker와 동일한 shard 기반 패턴 사용.

Event Types:
- stage: 파이프라인 단계 진행 상황 (intent, rag, answer 등)
- token: LLM 응답 토큰 스트리밍 (SSE delta)
- needs_input: 사용자 추가 입력 요청 (Human-in-the-Loop)

아키텍처:
```
chat_worker → Redis Streams (chat:events:{shard})
                    │
                    ▼
             Event Router (XREADGROUP)
                    │
                    ▼
             Redis Pub/Sub (sse:events:{job_id})
                    │
                    ▼
             Chat API (SSE Gateway)
```

분산 트레이싱 통합:
- XADD 시 trace context 포함 (trace_id, span_id, traceparent)
- Event Router가 trace context를 Pub/Sub에 전파
- Jaeger/Kiali에서 전체 파이프라인 시각화 가능

Port: application/ports/events/progress_notifier.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from chat_worker.application.ports.events.progress_notifier import ProgressNotifierPort
from chat_worker.infrastructure.metrics.metrics import (
    CHAT_STREAM_ACTIVE,
    CHAT_STREAM_DURATION,
    CHAT_STREAM_REQUESTS_TOTAL,
    CHAT_STREAM_TOKEN_COUNT,
    track_stream_token,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


def _get_current_trace_context() -> tuple[str, str, str]:
    """현재 OpenTelemetry span에서 trace context 추출.

    Returns:
        (trace_id, span_id, traceparent) 튜플. OTEL 비활성화 시 빈 문자열.
    """
    if not OTEL_ENABLED:
        return "", "", ""

    try:
        from opentelemetry import trace
        from opentelemetry.trace import format_trace_id, format_span_id

        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()

        if not span_context.is_valid:
            return "", "", ""

        trace_id = format_trace_id(span_context.trace_id)
        span_id = format_span_id(span_context.span_id)
        trace_flags = f"{span_context.trace_flags:02x}"
        traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"

        return trace_id, span_id, traceparent
    except ImportError:
        return "", "", ""
    except Exception as e:
        logger.debug(f"Failed to extract trace context: {e}")
        return "", "", ""


# ─────────────────────────────────────────────────────────────────
# 설정 (scan_worker와 동일한 패턴)
# ─────────────────────────────────────────────────────────────────

STREAM_PREFIX = "chat:events"
PUBLISHED_KEY_PREFIX = "chat:published:"
STREAM_MAXLEN = 10000
PUBLISHED_TTL = 7200  # 2시간

# Stage 순서 (단조증가 seq)
# Token은 별도 namespace (1000+)로 분리하여 충돌 방지
#
# Pipeline Flow:
# queued → intent → [vision?] → [subagents...] → aggregator → [feedback?] → answer → done
#
# Subagents (intent에 따라 선택적/병렬 실행):
# - waste_rag, character, location, kakao_place, bulk_waste, weather,
#   recyclable_price, collection_point, web_search, image_generation, general
STAGE_ORDER = {
    # Core Pipeline
    "queued": 0,
    "intent": 1,
    "vision": 2,  # 이미지 첨부 시
    # Subagents (intent에 따라 선택적/병렬 실행)
    "waste_rag": 3,  # waste intent
    "character": 4,  # greeting 등
    "location": 5,  # location intent (gRPC)
    "kakao_place": 6,  # place_search intent
    "bulk_waste": 7,  # bulk_waste intent
    "weather": 8,  # weather intent
    "recyclable_price": 9,  # price intent
    "collection_point": 10,  # collection_point intent
    "web_search": 11,  # web_search intent
    "image_generation": 12,  # image intent
    "general": 13,  # general intent (fallback)
    # Aggregation & Answer
    "aggregator": 14,  # 서브에이전트 결과 병합
    "feedback": 15,  # 품질 평가
    "answer": 16,  # 최종 답변 생성
    "done": 17,  # 완료
    "needs_input": 18,  # Human-in-the-Loop
}

# Token seq 시작값 (Stage seq와 충돌 방지)
# Stage: 0~179 (18개 stage * 10)
# Token: 1000+
TOKEN_SEQ_START = 1000

# 샤딩 설정 (event_router/config.py와 일치)
DEFAULT_SHARD_COUNT = int(os.environ.get("CHAT_SHARD_COUNT", "4"))

# ─────────────────────────────────────────────────────────────────
# Token v2 설정 (복구 가능한 토큰 스트리밍)
# ─────────────────────────────────────────────────────────────────

TOKEN_STREAM_PREFIX = "chat:tokens"  # job별 전용 Token Stream
TOKEN_STATE_PREFIX = "chat:token_state"  # 주기적 누적 텍스트 스냅샷
TOKEN_STREAM_TTL = 3600  # 1시간
TOKEN_STATE_SAVE_INTERVAL = 10  # 10 토큰마다 State 저장


# ─────────────────────────────────────────────────────────────────
# 멱등성 Lua Script (scan_worker와 동일)
# ─────────────────────────────────────────────────────────────────

IDEMPOTENT_XADD_SCRIPT = """
local publish_key = KEYS[1]  -- chat:published:{job_id}:{stage}:{seq}
local stream_key = KEYS[2]   -- chat:events:{shard}

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    local existing_msg_id = redis.call('GET', publish_key)
    return {0, existing_msg_id}  -- 이미 발행됨
end

-- XADD 실행 (MAXLEN ~ 로 효율적 trim)
-- ARGV[11]: trace_id, ARGV[12]: span_id, ARGV[13]: traceparent
local msg_id = redis.call('XADD', stream_key, 'MAXLEN', '~', ARGV[1],
    '*',
    'job_id', ARGV[2],
    'stage', ARGV[3],
    'status', ARGV[4],
    'seq', ARGV[5],
    'ts', ARGV[6],
    'progress', ARGV[7],
    'result', ARGV[8],
    'message', ARGV[9],
    'trace_id', ARGV[11],
    'span_id', ARGV[12],
    'traceparent', ARGV[13]
)

-- 발행 마킹 (TTL: 2시간)
redis.call('SETEX', publish_key, ARGV[10], msg_id)

return {1, msg_id}  -- 새로 발행됨
"""

# Token 스트리밍용 Script (멱등성 없음 - 순서대로 발행)
# ARGV[6]: trace_id, ARGV[7]: span_id, ARGV[8]: traceparent
TOKEN_XADD_SCRIPT = """
local stream_key = KEYS[1]   -- chat:events:{shard}

local msg_id = redis.call('XADD', stream_key, 'MAXLEN', '~', ARGV[1],
    '*',
    'job_id', ARGV[2],
    'stage', 'token',
    'status', 'streaming',
    'seq', ARGV[3],
    'ts', ARGV[4],
    'content', ARGV[5],
    'trace_id', ARGV[6],
    'span_id', ARGV[7],
    'traceparent', ARGV[8]
)

return msg_id
"""

# Token v2 스트리밍용 Script (복구 가능 - Token Stream + State)
# ARGV[10]: trace_id, ARGV[11]: span_id, ARGV[12]: traceparent
TOKEN_XADD_V2_SCRIPT = """
local token_stream = KEYS[1]   -- chat:tokens:{job_id}
local token_state = KEYS[2]    -- chat:token_state:{job_id}
local stage_stream = KEYS[3]   -- chat:events:{shard}

local job_id = ARGV[1]
local seq = ARGV[2]
local delta = ARGV[3]
local ts = ARGV[4]
local accumulated = ARGV[5]
local save_state = tonumber(ARGV[6])  -- 1이면 State 저장
local ttl = tonumber(ARGV[7])
local maxlen = ARGV[8]
local node = ARGV[9]
local trace_id = ARGV[10]
local span_id = ARGV[11]
local traceparent = ARGV[12]

-- 1. Token Stream에 추가 (job별 전용)
local token_msg_id = redis.call('XADD', token_stream, 'MAXLEN', '~', 10000, '*',
    'seq', seq,
    'delta', delta,
    'node', node,
    'ts', ts
)

-- 2. Token Stream TTL 설정 (첫 메시지일 때만)
local stream_len = redis.call('XLEN', token_stream)
if stream_len == 1 then
    redis.call('EXPIRE', token_stream, ttl)
end

-- 3. 주기적으로 State 저장 (accumulated 복구용)
if save_state == 1 then
    local state = cjson.encode({
        last_seq = tonumber(seq),
        accumulated = accumulated,
        accumulated_len = string.len(accumulated),
        node = node,
        updated_at = tonumber(ts)
    })
    redis.call('SETEX', token_state, ttl, state)
end

-- 4. Stage Stream에도 발행 (기존 호환성 유지, trace context 포함)
local stage_msg_id = redis.call('XADD', stage_stream, 'MAXLEN', '~', maxlen,
    '*',
    'job_id', job_id,
    'stage', 'token',
    'status', 'streaming',
    'seq', seq,
    'ts', ts,
    'content', delta,
    'node', node,
    'trace_id', trace_id,
    'span_id', span_id,
    'traceparent', traceparent
)

return {token_msg_id, stage_msg_id}
"""


def _get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산.

    scan_worker와 동일한 해시 함수 사용.
    """
    if shard_count is None:
        shard_count = DEFAULT_SHARD_COUNT
    hash_bytes = hashlib.md5(job_id.encode()).digest()[:8]
    hash_int = int.from_bytes(hash_bytes, byteorder="big")
    return hash_int % shard_count


def _get_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """Sharded Stream key 생성."""
    shard = _get_shard_for_job(job_id, shard_count)
    return f"{STREAM_PREFIX}:{shard}"


class RedisProgressNotifier(ProgressNotifierPort):
    """Redis Streams 기반 진행률 알림.

    scan_worker와 동일한 shard 기반 패턴:
    - job_id → hash → shard 번호 결정
    - chat:events:{shard}에 이벤트 발행
    - Event Router가 Consumer Group으로 소비
    """

    def __init__(
        self,
        redis: "Redis",
        shard_count: int | None = None,
        maxlen: int = STREAM_MAXLEN,
    ):
        """초기화.

        Args:
            redis: Redis 클라이언트 (async)
            shard_count: Shard 수 (기본: 4)
            maxlen: 스트림 최대 길이 (오래된 메시지 자동 삭제)
        """
        self._redis = redis
        self._shard_count = shard_count or DEFAULT_SHARD_COUNT
        self._maxlen = maxlen
        self._stage_script = None
        self._token_script = None
        self._token_v2_script = None
        self._token_seq: dict[str, int] = {}  # job_id → token seq counter
        # Token v2: 누적 텍스트 추적
        self._accumulated: dict[str, str] = {}  # job_id → 누적 텍스트
        self._token_count: dict[str, int] = {}  # job_id → 토큰 카운트
        # Token v2: 스트림 시작 시간 (부하테스트 메트릭)
        self._stream_start_time: dict[str, float] = {}  # job_id → start time
        self._stream_node: dict[str, str] = {}  # job_id → 마지막 노드명
        logger.info(
            "RedisProgressNotifier initialized",
            extra={"shards": self._shard_count, "maxlen": maxlen},
        )

    async def _ensure_scripts(self) -> None:
        """Lua Script 등록.

        register_script는 로컬 캐싱만 수행하므로 Redis 연결 불필요.
        실제 EVALSHA는 스크립트 실행 시 수행됨.
        """
        if self._stage_script is None:
            self._stage_script = self._redis.register_script(IDEMPOTENT_XADD_SCRIPT)
        if self._token_script is None:
            self._token_script = self._redis.register_script(TOKEN_XADD_SCRIPT)
        if self._token_v2_script is None:
            self._token_v2_script = self._redis.register_script(TOKEN_XADD_V2_SCRIPT)

    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> str:
        """단계 이벤트 발행 (멱등성 보장).

        Args:
            task_id: 작업 ID (job_id)
            stage: 단계명 (intent, rag, character, location, answer, done)
            status: 상태 (started, completed, failed)
            progress: 진행률 0~100 (선택)
            result: 완료 시 결과 데이터 (선택)
            message: UI 표시 메시지 (선택)

        Returns:
            발행된 메시지 ID
        """
        await self._ensure_scripts()

        stream_key = _get_stream_key(task_id, self._shard_count)
        shard = _get_shard_for_job(task_id, self._shard_count)

        # 단조증가 seq 계산
        base_seq = STAGE_ORDER.get(stage, 99) * 10
        seq = base_seq + (1 if status == "completed" else 0)

        # 멱등성 키
        publish_key = f"{PUBLISHED_KEY_PREFIX}{task_id}:{stage}:{seq}"

        # 이벤트 데이터
        ts = str(time.time())
        progress_str = str(progress) if progress is not None else ""
        result_str = json.dumps(result, ensure_ascii=False) if result else ""
        message_str = message or ""

        # Trace context 추출
        trace_id, span_id, traceparent = _get_current_trace_context()

        # Lua Script 실행
        try:
            result_tuple = await self._stage_script(
                keys=[publish_key, stream_key],
                args=[
                    str(self._maxlen),  # ARGV[1]
                    task_id,  # ARGV[2] - job_id
                    stage,  # ARGV[3]
                    status,  # ARGV[4]
                    str(seq),  # ARGV[5]
                    ts,  # ARGV[6]
                    progress_str,  # ARGV[7]
                    result_str,  # ARGV[8]
                    message_str,  # ARGV[9]
                    str(PUBLISHED_TTL),  # ARGV[10]
                    trace_id,  # ARGV[11]
                    span_id,  # ARGV[12]
                    traceparent,  # ARGV[13]
                ],
            )
        except Exception as e:
            logger.error(
                "stage_event_publish_failed",
                extra={
                    "job_id": task_id,
                    "shard": shard,
                    "stage": stage,
                    "status": status,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ""

        is_new, msg_id = result_tuple
        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode()

        if is_new:
            logger.debug(
                "stage_event_published",
                extra={
                    "job_id": task_id,
                    "shard": shard,
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
                    "job_id": task_id,
                    "shard": shard,
                    "stage": stage,
                    "existing_msg_id": msg_id,
                },
            )

        return msg_id

    async def notify_token(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """토큰 스트리밍 이벤트 발행.

        LLM 응답의 각 토큰을 실시간으로 전달.
        멱등성 없음 (순서대로 모든 토큰 발행).

        Args:
            task_id: 작업 ID (job_id)
            content: 토큰 내용

        Returns:
            발행된 메시지 ID
        """
        await self._ensure_scripts()

        stream_key = _get_stream_key(task_id, self._shard_count)

        # 토큰 seq (job별 카운터)
        # Stage seq (0~79)와 충돌 방지를 위해 1000+부터 시작
        if task_id not in self._token_seq:
            self._token_seq[task_id] = TOKEN_SEQ_START
        self._token_seq[task_id] += 1
        seq = self._token_seq[task_id]

        ts = str(time.time())

        # Trace context 추출
        trace_id, span_id, traceparent = _get_current_trace_context()

        try:
            msg_id = await self._token_script(
                keys=[stream_key],
                args=[
                    str(self._maxlen),  # ARGV[1]
                    task_id,  # ARGV[2] - job_id
                    str(seq),  # ARGV[3]
                    ts,  # ARGV[4]
                    content,  # ARGV[5]
                    trace_id,  # ARGV[6]
                    span_id,  # ARGV[7]
                    traceparent,  # ARGV[8]
                ],
            )
        except Exception as e:
            logger.error(
                "token_publish_failed",
                extra={
                    "job_id": task_id,
                    "seq": seq,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ""

        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode()

        return msg_id

    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ) -> str:
        """Human-in-the-Loop 입력 요청 이벤트 발행.

        Frontend가 이 이벤트를 수신하면:
        1. 권한 요청 UI 표시
        2. 사용자 입력 수집
        3. POST /chat/{job_id}/input으로 전송

        Args:
            task_id: 작업 ID (job_id)
            input_type: 입력 타입 (location, confirmation, selection)
            message: 사용자에게 표시할 메시지
            timeout: 입력 대기 시간 (초)

        Returns:
            발행된 메시지 ID
        """
        # needs_input은 특별한 stage로 처리
        result = {
            "input_type": input_type,
            "timeout": timeout,
        }

        return await self.notify_stage(
            task_id=task_id,
            stage="needs_input",
            status="waiting",
            message=message,
            result=result,
        )

    def clear_token_counter(self, task_id: str) -> None:
        """토큰 관련 메모리 정리 (작업 완료 시 호출).

        모든 job 관련 in-memory 상태를 정리합니다.
        예외 상황이나 timeout 시에도 finally에서 호출되어
        메모리 누수를 방지합니다.

        Args:
            task_id: 작업 ID (job_id)
        """
        # Token sequence counter 정리
        if task_id in self._token_seq:
            del self._token_seq[task_id]
        # Token v2: 누적 텍스트 정리
        if task_id in self._accumulated:
            del self._accumulated[task_id]
        # Token v2: 토큰 카운트 정리
        if task_id in self._token_count:
            del self._token_count[task_id]
        # Token v2: 스트림 시작 시간 정리
        if task_id in self._stream_start_time:
            del self._stream_start_time[task_id]
        # Token v2: 노드 추적 정리
        if task_id in self._stream_node:
            del self._stream_node[task_id]

    async def notify_token_v2(
        self,
        task_id: str,
        content: str,
        node: str | None = None,
    ) -> str:
        """토큰 스트리밍 이벤트 발행 (복구 가능).

        Token Stream + Token State 저장으로 재연결 시 복구 지원.

        아키텍처:
        - Token Stream (chat:tokens:{job_id}): 모든 토큰 저장, catch-up 지원
        - Token State (chat:token_state:{job_id}): 주기적 누적 텍스트 스냅샷
        - Stage Stream (chat:events:{shard}): 기존 호환성 유지

        Args:
            task_id: 작업 ID (job_id)
            content: 토큰 내용
            node: 토큰 발생 노드명 (answer, summarize 등)

        Returns:
            발행된 메시지 ID (Token Stream)
        """
        await self._ensure_scripts()

        # 누적 텍스트 계산
        is_first_token = task_id not in self._accumulated
        if is_first_token:
            self._accumulated[task_id] = ""
            self._token_count[task_id] = 0
            self._stream_start_time[task_id] = time.perf_counter()
            # Metrics: Active stream started
            CHAT_STREAM_ACTIVE.inc()

        self._accumulated[task_id] += content
        self._token_count[task_id] += 1
        # 노드 추적 (마지막 노드)
        if node:
            self._stream_node[task_id] = node
        accumulated = self._accumulated[task_id]

        # seq 계산 (Stage seq와 충돌 방지를 위해 1000+부터 시작)
        if task_id not in self._token_seq:
            self._token_seq[task_id] = TOKEN_SEQ_START
        self._token_seq[task_id] += 1
        seq = self._token_seq[task_id]

        # State 저장 여부 (10 토큰마다)
        save_state = 1 if self._token_count[task_id] % TOKEN_STATE_SAVE_INTERVAL == 0 else 0

        ts = str(time.time())
        node_str = node or ""

        # Trace context 추출
        trace_id, span_id, traceparent = _get_current_trace_context()

        # Redis keys
        token_stream_key = f"{TOKEN_STREAM_PREFIX}:{task_id}"
        token_state_key = f"{TOKEN_STATE_PREFIX}:{task_id}"
        stage_stream_key = _get_stream_key(task_id, self._shard_count)

        # Lua Script 실행 (with latency tracking)
        xadd_start = time.perf_counter()
        try:
            result = await self._token_v2_script(
                keys=[token_stream_key, token_state_key, stage_stream_key],
                args=[
                    task_id,  # ARGV[1] - job_id
                    str(seq),  # ARGV[2] - seq
                    content,  # ARGV[3] - delta
                    ts,  # ARGV[4] - ts
                    accumulated,  # ARGV[5] - accumulated
                    str(save_state),  # ARGV[6] - save_state
                    str(TOKEN_STREAM_TTL),  # ARGV[7] - ttl
                    str(self._maxlen),  # ARGV[8] - maxlen
                    node_str,  # ARGV[9] - node
                    trace_id,  # ARGV[10]
                    span_id,  # ARGV[11]
                    traceparent,  # ARGV[12]
                ],
            )
        except Exception as e:
            xadd_latency = time.perf_counter() - xadd_start
            track_stream_token(node=node_str or "answer", status="error", latency=xadd_latency)
            logger.error(
                "token_v2_publish_failed",
                extra={
                    "job_id": task_id,
                    "seq": seq,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return ""
        xadd_latency = time.perf_counter() - xadd_start

        # Metrics: Token count + Redis XADD latency (track_stream_token이 latency 기록 포함)
        track_stream_token(node=node_str or "answer", status="success", latency=xadd_latency)

        token_msg_id, stage_msg_id = result
        if isinstance(token_msg_id, bytes):
            token_msg_id = token_msg_id.decode()
        if isinstance(stage_msg_id, bytes):
            stage_msg_id = stage_msg_id.decode()

        logger.debug(
            "token_v2_published",
            extra={
                "job_id": task_id,
                "seq": seq,
                "node": node_str,
                "token_msg_id": token_msg_id,
                "stage_msg_id": stage_msg_id,
                "save_state": bool(save_state),
            },
        )

        return token_msg_id

    async def finalize_token_stream(self, task_id: str) -> None:
        """토큰 스트림 완료 처리.

        토큰 스트리밍 완료 시 최종 State 저장 및 메모리 정리.

        Args:
            task_id: 작업 ID
        """
        if task_id not in self._accumulated:
            return

        accumulated = self._accumulated[task_id]
        seq = self._token_seq.get(task_id, TOKEN_SEQ_START)
        token_count = self._token_count.get(task_id, 0)
        stream_node = self._stream_node.get(task_id, "answer")
        start_time = self._stream_start_time.get(task_id)

        # Metrics: Active stream finished
        CHAT_STREAM_ACTIVE.dec()

        # Metrics: Stream duration
        if start_time is not None:
            duration = time.perf_counter() - start_time
            CHAT_STREAM_DURATION.labels(node=stream_node, status="success").observe(duration)

        # Metrics: Token count per stream
        CHAT_STREAM_TOKEN_COUNT.labels(node=stream_node).observe(token_count)

        # Metrics: Stream request completed
        CHAT_STREAM_REQUESTS_TOTAL.labels(status="success").inc()

        # 최종 State 저장 (completed 플래그 추가)
        token_state_key = f"{TOKEN_STATE_PREFIX}:{task_id}"
        state = {
            "last_seq": seq,
            "accumulated": accumulated,
            "accumulated_len": len(accumulated),
            "completed": True,
            "updated_at": time.time(),
        }

        try:
            await self._redis.setex(
                token_state_key,
                TOKEN_STREAM_TTL,
                json.dumps(state, ensure_ascii=False),
            )
            logger.info(
                "token_stream_finalized",
                extra={
                    "job_id": task_id,
                    "last_seq": seq,
                    "accumulated_len": len(accumulated),
                },
            )
        except Exception as e:
            logger.error(
                "token_stream_finalize_error",
                extra={"job_id": task_id, "error": str(e)},
            )
        finally:
            # 메모리 정리 (clear_token_counter가 모든 상태 정리)
            self.clear_token_counter(task_id)
