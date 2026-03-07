# 이코에코(Eco²) Redis Streams for SSE #3: Application, Integration Layer 업데이트

> **작성일**: 2025-12-26  
> **시리즈**: Redis Streams for SSE  
> **이전**: [#2 선언적 배포 (GitOps)](./02-gitops-deployment.md)

---

## 개요

Redis 인프라 배포 후 애플리케이션 레이어를 업데이트합니다.
Celery Events (RabbitMQ) 대신 Redis Streams를 사용하여 SSE 이벤트를 발행/구독합니다.

---

## 변경 범위

```
domains/
├── _shared/events/           # NEW: 공유 모듈
│   ├── __init__.py
│   ├── redis_client.py       # Redis 클라이언트 팩토리 (동기/비동기)
│   └── redis_streams.py      # Streams 발행/구독
│
├── scan/
│   ├── tasks/
│   │   ├── vision.py        # 이벤트 발행 추가
│   │   ├── rule.py          # 이벤트 발행 추가
│   │   ├── answer.py        # 이벤트 발행 추가
│   │   └── reward.py        # 이벤트 발행 추가
│   └── api/v1/endpoints/
│       └── completion.py     # SSE: Celery Events → Redis Streams
│
└── workloads/domains/        # 환경변수 업데이트
    ├── scan/
    └── scan-worker/
```

---

## 1. Redis Client 모듈

### 동기/비동기 클라이언트 팩토리

```python
# domains/_shared/events/redis_client.py

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis
    import redis.asyncio as aioredis

# 환경변수에서 Redis Streams URL 가져오기
# 로컬 개발: localhost, K8s: rfr-streams-redis.redis.svc.cluster.local
_REDIS_STREAMS_URL = os.getenv(
    "REDIS_STREAMS_URL",
    "redis://localhost:6379/0",
)


@lru_cache(maxsize=1)
def get_sync_redis_client() -> "redis.Redis[bytes]":
    """동기 Redis 클라이언트 (Celery Worker용).

    Celery gevent pool에서 사용됩니다.
    gevent가 socket I/O를 자동으로 greenlet 전환합니다.

    Returns:
        동기 Redis 클라이언트 (싱글톤)
    """
    import redis

    return redis.from_url(
        _REDIS_STREAMS_URL,
        decode_responses=False,  # 바이트 유지 (Streams 호환)
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )


_async_redis_client: "aioredis.Redis | None" = None


async def get_async_redis_client() -> "aioredis.Redis":
    """비동기 Redis 클라이언트 (FastAPI SSE용).

    FastAPI asyncio event loop에서 사용됩니다.
    redis.asyncio를 사용하여 non-blocking I/O를 수행합니다.

    Returns:
        비동기 Redis 클라이언트 (싱글톤)
    """
    global _async_redis_client

    if _async_redis_client is None:
        import redis.asyncio as aioredis

        _async_redis_client = aioredis.from_url(
            _REDIS_STREAMS_URL,
            decode_responses=False,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )

    return _async_redis_client


async def close_async_redis_client() -> None:
    """비동기 Redis 클라이언트 종료.

    FastAPI shutdown 이벤트에서 호출합니다.
    """
    global _async_redis_client

    if _async_redis_client is not None:
        await _async_redis_client.close()
        _async_redis_client = None
```

**설계 포인트**:

| 항목 | 설명 |
|------|------|
| `decode_responses=False` | Redis Streams는 바이트를 반환하므로 호환성 유지 |
| `@lru_cache` | 동기 클라이언트 싱글톤 보장 (Connection Pool 재사용) |
| 글로벌 변수 | 비동기 클라이언트 싱글톤 (event loop당 1개) |
| `close_async_redis_client()` | FastAPI shutdown 시 연결 정리 |

---

## 2. Redis Streams 모듈

### 이벤트 발행 (Worker용)

```python
# domains/_shared/events/redis_streams.py

STREAM_PREFIX = "scan:events"
STREAM_MAXLEN = 50   # 최근 50개 이벤트만 유지
STREAM_TTL = 3600    # 1시간 후 만료

def get_stream_key(job_id: str) -> str:
    """Stream key 생성."""
    return f"{STREAM_PREFIX}:{job_id}"

def publish_stage_event(
    redis_client: "redis.Redis[Any]",
    job_id: str,
    stage: str,
    status: str,
    result: dict | None = None,
    progress: int | None = None,
) -> str:
    """Worker가 호출: stage 이벤트를 Redis Streams에 발행.

    Args:
        redis_client: 동기 Redis 클라이언트 (Celery Worker용)
        job_id: Chain의 root task ID
        stage: 단계명 (queued, vision, rule, answer, reward, done)
        status: 상태 (started, completed, failed)
        result: 완료 시 결과 데이터 (선택)
        progress: 진행률 0~100 (선택)

    Returns:
        발행된 메시지 ID (예: "1735123456789-0")
    """
    stream_key = get_stream_key(job_id)

    event: dict[str, str] = {
        "stage": stage,
        "status": status,
        "ts": str(time.time()),
    }

    if progress is not None:
        event["progress"] = str(progress)

    if result:
        event["result"] = json.dumps(result, ensure_ascii=False)

    # XADD + MAXLEN (오래된 이벤트 자동 삭제)
    msg_id = redis_client.xadd(
        stream_key,
        event,
        maxlen=STREAM_MAXLEN,
    )

    # Stream에 TTL 설정 (마지막 이벤트 기준으로 갱신)
    redis_client.expire(stream_key, STREAM_TTL)

    logger.debug(
        "stage_event_published",
        extra={
            "job_id": job_id,
            "stage": stage,
            "status": status,
            "msg_id": msg_id,
        },
    )

    return msg_id
```

### 이벤트 구독 (API용)

```python
async def subscribe_events(
    redis_client: "aioredis.Redis",
    job_id: str,
    timeout_ms: int = 5000,
    max_wait_seconds: int = 300,
) -> AsyncGenerator[dict[str, Any], None]:
    """SSE 엔드포인트가 호출: Redis Streams 이벤트 구독.

    Args:
        redis_client: 비동기 Redis 클라이언트
        job_id: Chain의 root task ID
        timeout_ms: XREAD 블로킹 타임아웃 (밀리초, 기본 5초)
        max_wait_seconds: 최대 대기 시간 (초, 기본 5분)

    Yields:
        이벤트 딕셔너리:
        - {"type": "keepalive"}: 타임아웃 시 keepalive
        - {"stage": "vision", "status": "started", ...}: stage 이벤트
        - {"stage": "done", "result": {...}}: 완료 이벤트
    """
    stream_key = get_stream_key(job_id)
    last_id = "0"  # 처음부터 읽기 (리플레이 지원)
    start_time = time.time()

    while True:
        # 최대 대기 시간 체크
        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            yield {"type": "error", "error": "timeout"}
            return

        # XREAD: 새 이벤트 대기 (blocking)
        try:
            events = await redis_client.xread(
                {stream_key: last_id},
                block=timeout_ms,
                count=10,
            )
        except Exception as e:
            yield {"type": "error", "error": "redis_error", "message": str(e)}
            return

        if not events:
            # 타임아웃 → keepalive 이벤트
            yield {"type": "keepalive"}
            continue

        for stream_name, messages in events:
            for msg_id, data in messages:
                # msg_id 업데이트
                last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                # 바이트 → 문자열 디코딩
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

                # progress 정수 변환
                if "progress" in event:
                    try:
                        event["progress"] = int(event["progress"])
                    except (ValueError, TypeError):
                        pass

                yield event

                # done 이벤트면 종료
                if event.get("stage") == "done":
                    return
```

**핵심 원칙: "구독 먼저, 발행 나중"**

- SSE 엔드포인트에서 `last_id = "0"`으로 구독 시작
- Celery Chain 발행
- Worker가 이벤트 발행
- SSE에서 `XREAD`로 이벤트 수신 (누락 없음)

---

## 3. Worker Task 업데이트

각 Celery Task에서 시작/완료 시점에 이벤트를 발행합니다.

### Vision Task (실제 코드)

```python
# domains/scan/tasks/vision.py

from domains._shared.events import get_sync_redis_client, publish_stage_event

@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.vision",
    queue="scan.vision",
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def vision_task(
    self: BaseTask,
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None,
) -> dict[str, Any]:
    """Step 1: GPT Vision을 사용한 이미지 분류."""
    from domains._shared.waste_pipeline.vision import analyze_images

    logger.info("Vision task started", extra={"task_id": task_id})

    # Redis Streams: 시작 이벤트 발행
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, task_id, "vision", "started", progress=0)

    started = perf_counter()

    try:
        result_payload = analyze_images(prompt_text, image_url, save_result=False)
        classification_result = _to_dict(result_payload)
    except Exception as exc:
        # Redis Streams: 실패 이벤트 발행
        publish_stage_event(
            redis_client, task_id, "vision", "failed",
            result={"error": str(exc)},
        )
        raise self.retry(exc=exc)

    elapsed_ms = (perf_counter() - started) * 1000
    logger.info("Vision task completed", extra={"elapsed_ms": elapsed_ms})

    # Redis Streams: 완료 이벤트 발행
    publish_stage_event(redis_client, task_id, "vision", "completed", progress=25)

    return {
        "task_id": task_id,
        "user_id": user_id,
        "image_url": image_url,
        "classification_result": classification_result,
        "metadata": {"duration_vision_ms": elapsed_ms},
    }
```

### 이벤트 발행 위치 요약

| Task | Stage | Progress | 이벤트 발행 시점 |
|------|-------|----------|-----------------|
| completion.py | queued | 0 | Chain 발행 직전 |
| vision_task | vision | 0 → 25 | 시작/완료 |
| rule_task | rule | 25 → 50 | 시작/완료 |
| answer_task | answer | 50 → 75 | 시작/완료 |
| scan_reward_task | reward | 75 → 100 | 시작/완료 |
| scan_reward_task | done | 100 | 최종 완료 |

---

## 4. SSE Endpoint 업데이트 (v2)

### Before: Celery Events (문제)

```python
# 기존 (RabbitMQ 연결 폭발)
@router.post("/completion")
async def scan_completion(request: ScanRequest):
    chain = (vision_task.s() | rule_task.s() | answer_task.s() | reward_task.s())
    result = chain.apply_async()

    async def event_stream():
        with celery_app.connection() as conn:  # RabbitMQ 연결! (문제!)
            recv = EventReceiver(conn, handlers)
            recv.capture(limit=None, timeout=60)

    return EventSourceResponse(event_stream())
```

### After: Redis Streams (v2, 실제 코드)

```python
# domains/scan/api/v1/endpoints/completion.py

from domains._shared.events import (
    get_async_redis_client,
    get_sync_redis_client,
    publish_stage_event,
    subscribe_events,
)

@router.post("/classify/completion", response_class=StreamingResponse)
async def classify_completion(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> StreamingResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (SSE 스트리밍).

    v2 변경사항:
        - Celery Events → Redis Streams로 이벤트 소싱 변경
        - RabbitMQ 연결 폭발 문제 해결 (SSE:RabbitMQ 1:21 → 0)
    """
    return StreamingResponse(
        _completion_generator_v2(payload, user, service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx buffering 비활성화
        },
    )


async def _completion_generator_v2(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> AsyncGenerator[str, None]:
    """SSE 스트림 생성기 (v2: Redis Streams 기반).

    핵심 원칙: "구독 먼저, 발행 나중"
    1. Redis Streams 구독 준비
    2. queued 이벤트 발행
    3. Celery Chain 발행
    4. Streams 이벤트 → SSE 전송
    5. done 이벤트 수신 시 종료
    """
    SSE_CONNECTIONS_ACTIVE.inc()
    chain_start_time = time.time()

    task_id = str(uuid4())
    user_id = str(user.user_id)
    image_url = str(payload.image_url)

    try:
        # 1. Redis 클라이언트 획득
        redis_client = await get_async_redis_client()
        sync_redis = get_sync_redis_client()

        # 2. queued 이벤트 발행
        publish_stage_event(sync_redis, task_id, "queued", "started", progress=0)

        # 3. 첫 SSE 이벤트 전송 (즉시)
        yield _format_sse(
            {"step": "queued", "status": "started", "progress": 0, "job_id": task_id},
            event_type="stage",
        )

        # TTFB 메트릭
        ttfb = time.time() - chain_start_time
        SSE_TTFB.observe(ttfb)

        # 4. Celery Chain 발행
        pipeline = chain(
            vision_task.s(task_id, user_id, image_url, payload.user_input)
                .set(task_id=task_id),
            rule_task.s(),
            answer_task.s(),
            scan_reward_task.s(),
        )
        pipeline.apply_async()

        # 5. Redis Streams 구독 루프
        async for event in subscribe_events(redis_client, task_id):
            # keepalive 이벤트
            if event.get("type") == "keepalive":
                yield ": keepalive\n\n"
                continue

            # 에러 이벤트
            if event.get("type") == "error":
                yield _format_sse(event, event_type="error")
                break

            stage = event.get("stage", "")
            status = event.get("status", "")
            progress = event.get("progress", STAGE_PROGRESS_MAP.get(stage, 0))

            sse_data = {"step": stage, "status": status, "progress": progress}

            # done 이벤트
            if stage == "done":
                sse_data["result"] = event.get("result")
                sse_data["result_url"] = f"/api/v1/scan/result/{task_id}"
                yield _format_sse(sse_data, event_type="ready")
                break

            yield _format_sse(sse_data, event_type="stage")

    finally:
        SSE_CHAIN_DURATION.observe(time.time() - chain_start_time)
        SSE_CONNECTIONS_ACTIVE.dec()


def _format_sse(data: dict, event_type: str = "message") -> str:
    """SSE 형식으로 포맷팅."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

---

## 5. 환경변수 매핑 (실측)

### scan-worker 환경변수

```bash
ubuntu@k8s-master:~$ kubectl exec -n scan deployment/scan-worker -- printenv | grep REDIS

REDIS_STREAMS_URL=redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
CELERY_RESULT_BACKEND=redis://rfr-cache-redis.redis.svc.cluster.local:6379/0
```

### celery-beat 환경변수

```bash
ubuntu@k8s-master:~$ kubectl exec -n scan deployment/celery-beat -- printenv | grep CELERY

CELERY_RESULT_BACKEND=redis://rfr-cache-redis.redis.svc.cluster.local:6379/1
```

### 환경변수 매핑 테이블

| 환경변수 | Redis 인스턴스 | DB | 용도 |
|----------|---------------|-----|------|
| `REDIS_STREAMS_URL` | rfr-streams-redis | 0 | SSE 이벤트 스트림 |
| `CELERY_RESULT_BACKEND` | rfr-cache-redis | 0 | Celery 결과 저장 |
| `CELERY_RESULT_BACKEND` (beat) | rfr-cache-redis | 1 | Beat 스케줄 DB |

---

## 이벤트 흐름 시각화

```
┌───────────────────────────────────────────────────────────────────┐
│  POST /classify/completion                                         │
│                                                                    │
│  1. Redis 클라이언트 획득                                          │
│  2. queued 이벤트 발행 (sync)                                      │
│  3. 첫 SSE 이벤트 전송 (즉시)                                      │
│  4. Celery Chain 발행                                              │
│  5. Redis Streams 구독 시작 (XREAD BLOCK)                          │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  scan-worker → Redis Streams (rfr-streams-redis)            │  │
│  │                                                              │  │
│  │  XADD scan:events:{task_id}                                  │  │
│  │   {stage: "vision",  status: "started",  progress: 0}        │  │
│  │   {stage: "vision",  status: "completed", progress: 25}      │  │
│  │   {stage: "rule",    status: "started",  progress: 25}       │  │
│  │   {stage: "rule",    status: "completed", progress: 50}      │  │
│  │   {stage: "answer",  status: "started",  progress: 50}       │  │
│  │   {stage: "answer",  status: "completed", progress: 75}      │  │
│  │   {stage: "reward",  status: "started",  progress: 75}       │  │
│  │   {stage: "reward",  status: "completed", progress: 100}     │  │
│  │   {stage: "done",    result: {...}}                          │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                               │                                    │
│                               ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  scan-api ← XREAD BLOCK ← SSE → Client                       │  │
│  │                                                              │  │
│  │  event: stage                                                │  │
│  │  data: {"step": "vision", "status": "started", ...}          │  │
│  │                                                              │  │
│  │  : keepalive                                                 │  │
│  │                                                              │  │
│  │  event: stage                                                │  │
│  │  data: {"step": "vision", "status": "completed", ...}        │  │
│  │  ...                                                         │  │
│  │                                                              │  │
│  │  event: ready                                                │  │
│  │  data: {"step": "done", "result": {...}, "result_url": ...}  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## 6. 트러블슈팅: socket_timeout 이슈

### 문제 상황

초기 배포 후 테스트에서 `answer` 단계 대기 중 타임아웃 발생:

```
event: stage - vision:completed (3.0s)
event: stage - rule:completed
event: error - redis_error: "Timeout reading from rfr-streams-redis..."
```

### 원인 분석

```python
# 기존 설정
socket_timeout=5.0  # ← 문제!
```

- `answer_task` 소요시간: 6~10초 (GPT 답변 생성)
- `XREAD block=5000ms` 동안 소켓이 idle 상태
- `socket_timeout=5.0`이 먼저 트리거되어 연결 종료

### 해결

```python
# 수정 후
async def get_async_redis_client():
    _async_redis_client = aioredis.from_url(
        _REDIS_STREAMS_URL,
        decode_responses=False,
        socket_timeout=60.0,  # XREAD block(5s) + AI 처리(10s) 여유
        socket_connect_timeout=5.0,
    )
```

**Commit**: `4db8c6fc` - fix(events): increase async redis socket_timeout to 60s

---

## 7. 실측 테스트 결과

### 테스트 환경

- **날짜**: 2025-12-26
- **이미지**: 종이쇼핑백 (재활용폐기물)
- **API**: `POST /api/v1/scan/classify/completion`

### SSE 이벤트 흐름 (실측)

```
event: stage
data: {"step": "queued", "status": "started", "progress": 0, "job_id": "424e40b9-..."}

event: stage
data: {"step": "vision", "status": "started", "progress": 25}

: keepalive              ← 5초 대기 중 keepalive 정상 작동

event: stage
data: {"step": "vision", "status": "completed", "progress": 25}

event: stage
data: {"step": "rule", "status": "started", "progress": 25}

event: stage
data: {"step": "rule", "status": "completed", "progress": 50}

event: stage
data: {"step": "answer", "status": "started", "progress": 50}

event: stage
data: {"step": "answer", "status": "completed", "progress": 75}

event: stage
data: {"step": "reward", "status": "started", "progress": 75}

event: stage
data: {"step": "reward", "status": "completed", "progress": 100, "result": {...}}

event: ready
data: {"step": "done", "result": {...}, "result_url": "/api/v1/scan/result/424e40b9-..."}
```

### 성능 지표

| 항목 | 값 |
|------|-----|
| **Job ID** | `424e40b9-12b6-427e-b772-e749d910f888` |
| **분류 결과** | 종이쇼핑백 (재활용폐기물) |
| **총 소요시간** | ~12초 |
| **Vision** | 6.9초 |
| **Rule** | 0.5ms |
| **Answer** | 4.8초 |
| **Reward** | 0.1초 |

### Redis Streams 이벤트 검증

```bash
$ kubectl exec -n redis rfr-streams-redis-0 -c redis -- \
    redis-cli XLEN "scan:events:424e40b9-12b6-427e-b772-e749d910f888"
11  # queued(1) + vision(2) + rule(2) + answer(2) + reward(2) + done(1) + 중복queued(1)
```

---

## 예상 효과

### 연결 수 비교

| 상황 | Before (Celery Events) | After (Redis Streams) |
|------|------------------------|----------------------|
| 50 VU | 341+ RabbitMQ 연결 | 1 Redis Pool |
| 메모리 | 676Mi | < 300Mi (예상) |

### 장점

1. **연결 폭발 해결**: RabbitMQ 연결 대신 Redis Connection Pool 재사용
2. **메모리 안정화**: Celery Event Receiver 오버헤드 제거
3. **keepalive 지원**: 5초마다 keepalive로 연결 유지
4. **API 호환성 유지**: 기존 클라이언트 수정 불필요

---

## 참고 자료

- [Redis Streams 공식 문서](https://redis.io/docs/latest/develop/data-types/streams/)
- [XREAD BLOCK 패턴](https://redis.io/docs/latest/commands/xread/)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

---

## 다음 단계

→ [#4: Observability](./04-observability.md)
