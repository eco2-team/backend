# Event Router 코드 구현 상세

## TL;DR

[이전 포스팅](https://rooftopsnow.tistory.com/102)에서 Eco² Composite Event Bus의 아키텍처를 설명했습니다. 이번 포스팅에서는 **Event Router**의 코드 구현을 상세히 살펴봅니다.

핵심 모듈:
- `main.py`: FastAPI 앱, 라이프사이클 관리
- `core/consumer.py`: XREADGROUP 기반 이벤트 소비
- `core/processor.py`: Lua Script 기반 멱등성 처리
- `core/reclaimer.py`: XAUTOCLAIM 기반 장애 복구

---

## 1. 모듈 구조

```
domains/event-router/
├── main.py              # FastAPI 앱 진입점
├── config.py            # 환경 설정
├── core/
│   ├── consumer.py      # StreamConsumer (XREADGROUP)
│   ├── processor.py     # EventProcessor (Lua + Pub/Sub)
│   └── reclaimer.py     # PendingReclaimer (XAUTOCLAIM)
├── tests/
├── Dockerfile
└── requirements.txt
```

---

## 2. main.py: 앱 라이프사이클

### 2.1 Redis 클라이언트 분리

```python
# 전역 상태
redis_streams_client: aioredis.Redis | None = None  # XREADGROUP/XACK + State KV
redis_pubsub_client: aioredis.Redis | None = None   # PUBLISH only

@app.on_event("startup")
async def startup() -> None:
    global redis_streams_client, redis_pubsub_client, consumer, reclaimer

    # Redis Streams 연결 (내구성: State + 발행 마킹)
    redis_streams_client = aioredis.from_url(
        settings.redis_streams_url,
        decode_responses=False,
        socket_timeout=60.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )

    # Redis Pub/Sub 연결 (실시간: fan-out)
    redis_pubsub_client = aioredis.from_url(
        settings.redis_pubsub_url,
        decode_responses=False,
        socket_timeout=60.0,
        retry_on_timeout=True,
        health_check_interval=30,
    )
```

**왜 2개 Redis?**
- **Streams Redis**: State KV 저장 + 발행 마킹 (내구성 필요)
- **Pub/Sub Redis**: 실시간 브로드캐스트 (휘발성, 장애 격리)

### 2.2 컴포넌트 의존성

```python
    # EventProcessor: 2개 Redis 클라이언트 주입
    processor = EventProcessor(
        streams_client=redis_streams_client,  # State KV
        pubsub_client=redis_pubsub_client,    # PUBLISH
        state_key_prefix=settings.state_key_prefix,
        published_key_prefix=settings.router_published_prefix,
        pubsub_channel_prefix=settings.pubsub_channel_prefix,
    )

    # Consumer: Streams 클라이언트만 사용
    consumer = StreamConsumer(
        redis_client=redis_streams_client,
        processor=processor,  # Processor 주입
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream_prefix=settings.stream_prefix,
        shard_count=settings.shard_count,
    )

    # Reclaimer: Streams 클라이언트만 사용
    reclaimer = PendingReclaimer(
        redis_client=redis_streams_client,
        processor=processor,  # 동일 Processor 공유
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
    )
```

### 2.3 Background Task 실행

```python
    # Consumer Group 설정 (없으면 생성)
    await consumer.setup()

    # Background tasks 시작
    consumer_task = asyncio.create_task(consumer.consume())
    reclaimer_task = asyncio.create_task(reclaimer.run())
```

### 2.4 Readiness Probe

```python
@app.get("/ready")
async def ready() -> JSONResponse:
    # 1. Streams Redis ping
    if redis_streams_client is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    await redis_streams_client.ping()

    # 2. Pub/Sub Redis ping
    if redis_pubsub_client is None:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    await redis_pubsub_client.ping()

    # 3. Consumer task alive check
    if consumer_task is None or consumer_task.done():
        return JSONResponse({"status": "not_ready"}, status_code=503)

    # 4. Reclaimer task alive check
    if reclaimer_task is None or reclaimer_task.done():
        return JSONResponse({"status": "not_ready"}, status_code=503)

    return JSONResponse({"status": "ready"})
```

---

## 3. consumer.py: XREADGROUP 기반 이벤트 소비

### 3.1 Consumer Group 설정

```python
class StreamConsumer:
    async def setup(self) -> None:
        """Consumer Group 생성 (없으면 생성)."""
        for shard in range(self._shard_count):
            stream_key = f"{self._stream_prefix}:{shard}"
            try:
                await self._redis.xgroup_create(
                    stream_key,
                    self._consumer_group,
                    id="0",           # 처음부터 읽기
                    mkstream=True,    # Stream 없으면 생성
                )
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    pass  # 이미 존재 → 정상
                else:
                    raise

            # XREADGROUP에서 사용할 streams dict
            self._streams[stream_key] = ">"  # ">" = 새 메시지만
```

**주요 포인트**:
- `id="0"`: 그룹 생성 시 처음부터 읽도록 설정
- `mkstream=True`: Stream이 없으면 자동 생성
- `">"`: 아직 어떤 Consumer도 읽지 않은 새 메시지만 읽기

### 3.2 메인 Consumer 루프

```python
    async def consume(self) -> None:
        """메인 Consumer 루프."""
        while not self._shutdown:
            try:
                # XREADGROUP: 모든 shard에서 블로킹 읽기
                events = await self._redis.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=self._consumer_name,
                    streams=self._streams,  # {stream_key: ">", ...}
                    count=self._count,      # 한 번에 읽을 최대 메시지 수
                    block=self._block_ms,   # 블로킹 타임아웃 (ms)
                )

                if not events:
                    continue

                for stream_name, messages in events:
                    for msg_id, data in messages:
                        # 이벤트 파싱
                        event = self._parse_event(data)

                        # 이벤트 처리 (Processor)
                        await self._processor.process_event(event)

                        # ACK (처리 완료 마킹)
                        await self._redis.xack(
                            stream_name,
                            self._consumer_group,
                            msg_id,
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("consumer_error", extra={"error": str(e)})
                await asyncio.sleep(1)  # 에러 시 1초 대기 후 재시도
```

**XREADGROUP 흐름**:
```
XREADGROUP GROUP eventrouter event-router-0
    STREAMS scan:events:0 scan:events:1 scan:events:2 scan:events:3
    > > > >
    COUNT 100
    BLOCK 5000
```

### 3.3 이벤트 파싱

```python
    def _parse_event(self, data: dict[bytes, bytes]) -> dict[str, Any]:
        """Redis 메시지 파싱."""
        event: dict[str, Any] = {}

        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            value = v.decode() if isinstance(v, bytes) else v
            event[key] = value

        # result JSON 파싱
        if "result" in event and isinstance(event["result"], str):
            try:
                event["result"] = json.loads(event["result"])
            except json.JSONDecodeError:
                pass

        # seq, progress 정수 변환
        for int_field in ("seq", "progress"):
            if int_field in event:
                try:
                    event[int_field] = int(event[int_field])
                except (ValueError, TypeError):
                    pass

        return event
```

---

## 4. processor.py: Lua Script 기반 멱등성 처리

### 4.1 UPDATE_STATE_SCRIPT (Lua)

```lua
local state_key = KEYS[1]      -- scan:state:{job_id}
local publish_key = KEYS[2]    -- router:published:{job_id}:{seq}

local event_data = ARGV[1]     -- JSON 이벤트 데이터
local new_seq = tonumber(ARGV[2])
local state_ttl = tonumber(ARGV[3])
local published_ttl = tonumber(ARGV[4])

-- 1. 이미 처리했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    return 0  -- 이미 처리됨 → 중복
end

-- 2. State 조건부 갱신 (seq 비교)
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

-- 3. State 갱신
redis.call('SETEX', state_key, state_ttl, event_data)

-- 4. 처리 마킹
redis.call('SETEX', publish_key, published_ttl, '1')

return 1  -- State 갱신됨 → Pub/Sub 발행 필요
```

**핵심 로직**:
1. **중복 체크**: `router:published:{job_id}:{seq}` 키 존재 여부
2. **역순 방지**: 현재 State의 seq와 비교
3. **원자적 갱신**: State + 마킹을 한 트랜잭션에서 처리
4. **반환값**: 1이면 Pub/Sub 발행, 0이면 스킵

### 4.2 EventProcessor 클래스

```python
class EventProcessor:
    def __init__(
        self,
        streams_client: "aioredis.Redis",   # State KV + 발행 마킹
        pubsub_client: "aioredis.Redis",    # PUBLISH
        state_key_prefix: str = "scan:state",
        published_key_prefix: str = "router:published",
        pubsub_channel_prefix: str = "sse:events",
        state_ttl: int = 3600,              # 1시간
        published_ttl: int = 7200,          # 2시간
    ) -> None:
        self._streams_redis = streams_client
        self._pubsub_redis = pubsub_client
        # ...
        self._script: Any = None

    async def _ensure_script(self) -> None:
        """Lua Script 등록 (lazy)."""
        if self._script is None:
            self._script = self._streams_redis.register_script(UPDATE_STATE_SCRIPT)
```

### 4.3 process_event 메서드

```python
    async def process_event(self, event: dict[str, Any]) -> bool:
        await self._ensure_script()

        job_id = event.get("job_id")
        if not job_id:
            logger.warning("process_event_missing_job_id")
            return False

        seq = int(event.get("seq", 0))

        # Redis 키 생성
        state_key = f"{self._state_key_prefix}:{job_id}"
        publish_key = f"{self._published_key_prefix}:{job_id}:{seq}"
        channel = f"{self._pubsub_channel_prefix}:{job_id}"

        # 이벤트 JSON 직렬화
        event_data = json.dumps(event, ensure_ascii=False)

        # Step 1: Lua Script 실행 (Streams Redis)
        result = await self._script(
            keys=[state_key, publish_key],
            args=[event_data, seq, self._state_ttl, self._published_ttl],
        )

        if result == 1:
            # Step 2: Pub/Sub 발행 (Pub/Sub Redis)
            try:
                await self._pubsub_redis.publish(channel, event_data)
                logger.debug("event_processed", extra={"job_id": job_id, "seq": seq})
            except Exception as e:
                # Pub/Sub 실패해도 State는 이미 갱신됨
                # SSE 클라이언트는 State polling으로 복구 가능
                logger.warning("pubsub_publish_failed", extra={"error": str(e)})
            return True
        else:
            logger.debug("event_skipped", extra={"reason": "duplicate_or_out_of_order"})
            return False
```

**2단계 처리**:
```
Step 1: Lua Script (Streams Redis)
   └── State 갱신 + 발행 마킹 (원자적)

Step 2: PUBLISH (Pub/Sub Redis)
   └── 실시간 fan-out (실패해도 State로 복구 가능)
```

---

## 5. reclaimer.py: XAUTOCLAIM 기반 장애 복구

### 5.1 PendingReclaimer 클래스

```python
class PendingReclaimer:
    def __init__(
        self,
        redis_client: "aioredis.Redis",
        processor: EventProcessor,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int = 300000,       # 5분
        interval_seconds: int = 60,       # 1분마다 실행
        count: int = 100,
    ) -> None:
        self._min_idle_ms = min_idle_ms   # Pending 상태 유지 최소 시간
        self._interval = interval_seconds
```

### 5.2 메인 루프

```python
    async def run(self) -> None:
        """Reclaimer 메인 루프."""
        while not self._shutdown:
            try:
                await self._reclaim_pending()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("reclaimer_error", extra={"error": str(e)})
                await asyncio.sleep(self._interval)
```

### 5.3 XAUTOCLAIM 실행

```python
    async def _reclaim_pending(self) -> None:
        """모든 shard의 Pending 메시지 재할당."""
        for shard in range(self._shard_count):
            stream_key = f"{self._stream_prefix}:{shard}"

            try:
                # XAUTOCLAIM: 오래된 Pending 메시지 재할당
                result = await self._redis.xautoclaim(
                    stream_key,
                    self._consumer_group,
                    self._consumer_name,
                    min_idle_time=self._min_idle_ms,  # 5분 이상 Pending
                    start_id="0-0",
                    count=self._count,
                )

                # result: (next_start_id, [(msg_id, data), ...], deleted_ids)
                if len(result) >= 2:
                    messages = result[1]
                    if messages:
                        await self._process_reclaimed(stream_key, messages)

            except Exception as e:
                if "NOGROUP" in str(e):
                    continue  # Consumer Group 미생성
                logger.error("xautoclaim_error", extra={"error": str(e)})
```

**XAUTOCLAIM 동작**:
```
Consumer A가 메시지 읽고 처리 중 죽음
  └── Pending 상태로 남음 (ACK 안됨)

5분 후 Reclaimer 실행
  └── XAUTOCLAIM: Pending 메시지를 현재 Consumer로 재할당
      └── process_event() 재실행 (멱등성 보장)
          └── XACK
```

### 5.4 재할당 메시지 처리

```python
    async def _process_reclaimed(
        self,
        stream_key: str,
        messages: list[tuple[bytes, dict]],
    ) -> int:
        processed_count = 0

        for msg_id, data in messages:
            event = self._parse_event(data)

            try:
                # 이벤트 처리 (멱등성 보장되므로 안전)
                await self._processor.process_event(event)
                processed_count += 1
            except Exception as e:
                logger.error("reclaim_process_error", extra={"error": str(e)})

            # ACK (처리 성공/실패 무관하게)
            await self._redis.xack(
                stream_key,
                self._consumer_group,
                msg_id,
            )

        return processed_count
```

---

## 6. 전체 이벤트 처리 흐름

```
Worker (scan-worker)
    │
    │  XADD scan:events:{shard} + SETEX published:{job_id}:{stage}:{seq}
    ▼
┌────────────────────────────────────────────────────────────────┐
│                    Redis Streams                               │
│  scan:events:0   scan:events:1   scan:events:2   scan:events:3│
└────────────────────────────┬───────────────────────────────────┘
                             │
          XREADGROUP (Consumer Group: eventrouter)
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                    Event Router                                │
│                                                                │
│  ┌──────────────────┐    ┌──────────────────┐                 │
│  │  StreamConsumer  │───▶│  EventProcessor  │                 │
│  │  (XREADGROUP)    │    │  (Lua + PUBLISH) │                 │
│  └──────────────────┘    └──────────────────┘                 │
│           │                        │                           │
│           │                        │                           │
│  ┌──────────────────┐              │                           │
│  │ PendingReclaimer │──────────────┘                           │
│  │  (XAUTOCLAIM)    │                                          │
│  └──────────────────┘                                          │
│                                                                │
│  Background Tasks:                                             │
│  - consumer.consume()     │  메인 이벤트 소비                   │
│  - reclaimer.run()        │  장애 복구 (5분 idle Pending)       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                             │
          PUBLISH sse:events:{job_id} (Pub/Sub Redis)
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                    SSE Gateway                                 │
│  SUBSCRIBE sse:events:{job_id}                                │
│  GET scan:state:{job_id} (재접속 복구)                         │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. 결론

| 컴포넌트 | 역할 | Redis 명령 |
|----------|------|-----------|
| **StreamConsumer** | 이벤트 소비 | XREADGROUP, XACK |
| **EventProcessor** | 멱등성 처리 + fan-out | Lua Script, PUBLISH |
| **PendingReclaimer** | 장애 복구 | XAUTOCLAIM |

**핵심 설계 원칙**:
1. **2-Redis 분리**: Streams(내구성) + Pub/Sub(실시간)
2. **Lua Script**: State 갱신 + 발행 마킹 원자적 처리
3. **XAUTOCLAIM**: Consumer 장애 시 자동 복구
4. **멱등성**: seq 기반 중복/역순 방지

---

## 참고 자료

- [Redis Streams XREADGROUP](https://redis.io/commands/xreadgroup/)
- [Redis Streams XAUTOCLAIM](https://redis.io/commands/xautoclaim/)
- [Redis Lua Scripting](https://redis.io/docs/interact/programmability/eval-intro/)
- [Eco² Event Bus Layer 아키텍처](./38-event-router-implementation.md)


