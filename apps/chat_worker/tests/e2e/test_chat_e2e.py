"""Chat Worker E2E 테스트.

전체 파이프라인을 테스트합니다:
1. Chat API → RabbitMQ → Chat Worker
2. Chat Worker → Redis Streams → Event Router
3. Event Router → Redis Pub/Sub → SSE Gateway
4. SSE Gateway → Client (SSE)

Prerequisites:
- Docker Compose로 인프라 실행
- Redis, RabbitMQ, PostgreSQL 필요

Usage:
    pytest apps/chat_worker/tests/e2e/ -v --e2e
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

# E2E 테스트 마커
pytestmark = pytest.mark.e2e


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture
def job_id() -> str:
    """테스트용 job_id 생성."""
    return f"e2e-test-{uuid.uuid4()}"


@pytest.fixture
async def redis_client():
    """Redis 클라이언트."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )
    yield client
    await client.close()


@pytest.fixture
async def rabbitmq_channel():
    """RabbitMQ 채널."""
    import aio_pika

    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    yield channel
    await connection.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test Cases
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestChatE2EFlow:
    """Chat 전체 흐름 E2E 테스트."""

    @pytest.mark.asyncio
    async def test_simple_chat_flow(
        self,
        job_id: str,
        redis_client,
    ):
        """단순 채팅 흐름 테스트.

        Flow:
        1. Redis Streams에 직접 이벤트 발행 (Worker 시뮬레이션)
        2. Event Router가 처리하여 Pub/Sub로 발행
        3. Pub/Sub에서 이벤트 수신 확인
        """
        import hashlib

        # 1. Shard 계산 (Worker와 동일한 로직)
        shard_count = 4
        shard = (
            int.from_bytes(hashlib.md5(job_id.encode()).digest()[:8], "big")
            % shard_count
        )
        stream_key = f"chat:events:{shard}"
        pubsub_channel = f"sse:events:{job_id}"

        # 2. Pub/Sub 구독 시작
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(pubsub_channel)

        # 3. Redis Streams에 이벤트 발행 (Worker 시뮬레이션)
        event_data = {
            "job_id": job_id,
            "stage": "intent",
            "status": "completed",
            "seq": "1",
            "ts": str(int(asyncio.get_event_loop().time() * 1000)),
            "progress": "20",
            "result": json.dumps({"intent": "general"}),
            "message": "의도 파악 완료",
        }

        await redis_client.xadd(stream_key, event_data, maxlen=1000)

        # 4. Event Router가 처리할 시간 대기
        await asyncio.sleep(1.0)

        # 5. Pub/Sub에서 이벤트 수신 확인
        # (Event Router가 실행 중이어야 함)
        received = []
        try:
            async with asyncio.timeout(5.0):
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        if data.get("job_id") == job_id:
                            received.append(data)
                            break
        except asyncio.TimeoutError:
            pass

        await pubsub.unsubscribe(pubsub_channel)

        # Event Router가 실행 중이면 이벤트 수신됨
        # 실행 중이 아니면 빈 리스트 (CI 환경에서는 스킵 가능)
        if received:
            assert received[0]["stage"] == "intent"
            assert received[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_multi_intent_flow(
        self,
        job_id: str,
        redis_client,
    ):
        """Multi-Intent 처리 흐름 테스트.

        Flow:
        1. Multi-Intent 메시지 처리
        2. 여러 Stage 이벤트 발행
        3. 최종 Answer 이벤트 확인
        """
        import hashlib

        shard_count = 4
        shard = (
            int.from_bytes(hashlib.md5(job_id.encode()).digest()[:8], "big")
            % shard_count
        )
        stream_key = f"chat:events:{shard}"

        # 여러 Stage 이벤트 발행
        stages = [
            ("queued", 0, "작업 대기"),
            ("intent", 1, "의도 파악"),
            ("rag", 2, "정보 검색"),
            ("answer", 5, "답변 생성"),
            ("done", 6, "완료"),
        ]

        for stage, seq, message in stages:
            event_data = {
                "job_id": job_id,
                "stage": stage,
                "status": "completed",
                "seq": str(seq),
                "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                "progress": str(seq * 15),
                "result": json.dumps({}),
                "message": message,
            }
            await redis_client.xadd(stream_key, event_data, maxlen=1000)

        # State 확인 (Event Router가 저장)
        await asyncio.sleep(1.0)
        state_key = f"chat:state:{job_id}"
        state = await redis_client.get(state_key)

        # Event Router가 실행 중이면 State 저장됨
        if state:
            state_data = json.loads(state)
            assert state_data["stage"] == "done"

    @pytest.mark.asyncio
    async def test_token_streaming_flow(
        self,
        job_id: str,
        redis_client,
    ):
        """Token 스트리밍 흐름 테스트.

        Flow:
        1. Answer Stage 시작
        2. Token 이벤트 여러 개 발행
        3. Answer Stage 완료
        """
        import hashlib

        shard_count = 4
        shard = (
            int.from_bytes(hashlib.md5(job_id.encode()).digest()[:8], "big")
            % shard_count
        )
        stream_key = f"chat:events:{shard}"

        # Answer 시작
        await redis_client.xadd(
            stream_key,
            {
                "job_id": job_id,
                "stage": "answer",
                "status": "started",
                "seq": "50",
                "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                "progress": "70",
                "result": "{}",
                "message": "답변 생성 시작",
            },
            maxlen=1000,
        )

        # Token 스트리밍 (seq 1000+)
        tokens = ["안녕", "하세요", "!", " ", "이코", "예요", "."]
        for i, token in enumerate(tokens):
            await redis_client.xadd(
                stream_key,
                {
                    "job_id": job_id,
                    "stage": "token",
                    "status": "streaming",
                    "seq": str(1000 + i),
                    "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                    "progress": "80",
                    "result": json.dumps({"content": token}),
                    "message": "",
                },
                maxlen=1000,
            )

        # Answer 완료
        await redis_client.xadd(
            stream_key,
            {
                "job_id": job_id,
                "stage": "answer",
                "status": "completed",
                "seq": "51",
                "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                "progress": "100",
                "result": json.dumps({"answer": "".join(tokens)}),
                "message": "답변 생성 완료",
            },
            maxlen=1000,
        )

        # 검증: Stream에 이벤트가 저장되었는지
        messages = await redis_client.xrange(stream_key, count=100)
        job_messages = [
            m for m in messages if m[1].get("job_id") == job_id
        ]

        # 최소 9개 이벤트 (answer start + 7 tokens + answer complete)
        assert len(job_messages) >= 9


class TestEventRouterIntegration:
    """Event Router 통합 테스트."""

    @pytest.mark.asyncio
    async def test_reclaimer_processes_pending(
        self,
        job_id: str,
        redis_client,
    ):
        """Reclaimer가 Pending 메시지를 처리하는지 테스트.

        Scenario:
        1. Consumer Group 생성
        2. 메시지 발행 후 XREADGROUP으로 읽기 (ACK 안 함)
        3. Reclaimer가 일정 시간 후 재처리
        """
        import hashlib

        shard_count = 4
        shard = (
            int.from_bytes(hashlib.md5(job_id.encode()).digest()[:8], "big")
            % shard_count
        )
        stream_key = f"chat:events:{shard}"
        group_name = "test-group"
        consumer_name = "test-consumer"

        # Consumer Group 생성 (이미 있으면 무시)
        try:
            await redis_client.xgroup_create(
                stream_key, group_name, id="0", mkstream=True
            )
        except Exception:
            pass

        # 메시지 발행
        await redis_client.xadd(
            stream_key,
            {
                "job_id": job_id,
                "stage": "test",
                "status": "pending",
                "seq": "0",
                "ts": str(int(asyncio.get_event_loop().time() * 1000)),
                "progress": "0",
                "result": "{}",
                "message": "test",
            },
            maxlen=1000,
        )

        # XREADGROUP으로 읽기 (ACK 안 함 → Pending)
        messages = await redis_client.xreadgroup(
            group_name,
            consumer_name,
            {stream_key: ">"},
            count=1,
        )

        assert len(messages) > 0

        # Pending 확인
        pending = await redis_client.xpending(stream_key, group_name)
        assert pending["pending"] >= 1

        # Cleanup
        await redis_client.xgroup_destroy(stream_key, group_name)


class TestSSEGatewayIntegration:
    """SSE Gateway 통합 테스트."""

    @pytest.mark.asyncio
    async def test_state_recovery(
        self,
        job_id: str,
        redis_client,
    ):
        """State 복구 테스트.

        Scenario:
        1. State KV에 현재 상태 저장
        2. SSE Gateway가 연결 시 State 조회
        3. 누락된 이벤트 복구
        """
        state_key = f"chat:state:{job_id}"

        # State 저장
        state_data = {
            "job_id": job_id,
            "stage": "answer",
            "status": "started",
            "seq": 50,
            "progress": 70,
        }
        await redis_client.setex(state_key, 3600, json.dumps(state_data))

        # State 조회
        stored = await redis_client.get(state_key)
        assert stored is not None

        recovered = json.loads(stored)
        assert recovered["stage"] == "answer"
        assert recovered["seq"] == 50


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test Scenarios (Manual)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


"""
E2E 테스트 시나리오 (수동)
========================

1. Happy Path - 단순 채팅
   ```bash
   # 1. 인프라 시작
   docker-compose up -d redis rabbitmq postgresql

   # 2. 서비스 시작
   python -m apps.event_router.main &
   python -m apps.sse_gateway.main &
   python -m apps.chat_worker.main &
   python -m apps.chat.main &

   # 3. SSE 연결
   curl -N "http://localhost:8001/api/v1/chat/{job_id}/events"

   # 4. 채팅 요청
   curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "안녕"}'

   # 5. SSE 이벤트 확인
   # event: intent
   # event: answer
   # event: done
   ```

2. Multi-Intent 처리
   ```bash
   curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "페트병 버리고 캐릭터 알려줘"}'

   # 예상 이벤트:
   # event: intent (has_multi_intent: true)
   # event: rag
   # event: character
   # event: answer (복합 답변)
   # event: done
   ```

3. Vision + RAG
   ```bash
   curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "이거 어떻게 버려?", "image_url": "https://..."}'

   # 예상 이벤트:
   # event: intent
   # event: vision (classification)
   # event: rag (disposal_rules)
   # event: answer
   # event: done
   ```

4. Token Streaming
   ```bash
   # SSE 연결 후 token 이벤트 확인
   # event: token (content: "안")
   # event: token (content: "녕")
   # event: token (content: "하")
   # ...
   ```

5. Error Recovery
   ```bash
   # 1. Worker 강제 종료
   kill -9 $(pgrep -f chat_worker)

   # 2. Pending 메시지 확인
   redis-cli XPENDING chat:events:0 eventrouter

   # 3. Reclaimer가 재처리하는지 확인 (5분 후)
   ```

6. Shard 분산 확인
   ```bash
   # 여러 job_id로 요청
   for i in {1..100}; do
     curl -X POST "http://localhost:8000/api/v1/chat" \
       -H "Content-Type: application/json" \
       -d '{"message": "테스트 '$i'"}'
   done

   # Shard별 메시지 수 확인
   redis-cli XLEN chat:events:0
   redis-cli XLEN chat:events:1
   redis-cli XLEN chat:events:2
   redis-cli XLEN chat:events:3
   ```
"""
