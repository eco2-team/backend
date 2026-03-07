# Message Queue #14: Redis Streams 기반 SSE 이벤트 소싱 전환

> **목표**: Celery Events → Redis Streams 전환으로 SSE:RabbitMQ 연결 폭발 문제 해결  
> **이전 문서**: [#13 SSE 50 VU 병목 분석](./23-sse-bottleneck-analysis-50vu.md)

---

## 배경: 병목 원인 요약

[#13 병목 분석](./23-sse-bottleneck-analysis-50vu.md)에서 발견된 문제:

| 지표 | 값 | 문제 |
|------|-----|------|
| SSE : RabbitMQ 연결 | **1 : 21** | 연결 폭발 |
| RabbitMQ 연결 (max) | 341개 | 8.7배 급증 |
| scan-api 메모리 | 676Mi | 512Mi limit 초과 |
| 503 에러 | 발생 | Readiness 실패 |

### 연쇄 실패 흐름

```
50 VU 부하
    ↓
SSE 연결 16개
    ↓ × 21 연결/SSE
RabbitMQ 341개 연결
    ↓
메모리 676Mi > 512Mi
    ↓
Readiness 실패
    ↓
503 no healthy upstream
```

### 핵심 문제: 구조적 곱 폭발

```
❌ 현재: Client × RabbitMQ 연결 = 곱 폭발
✅ 목표: Client × Redis 읽기 = Pod당 1개 (상수)
```

---

## 해결 전략 비교

### 방법 1: 단일 `/completion` + Redis Streams (선택)

```
POST /completion
    │
    ├─ 1. Redis Streams 구독 시작
    ├─ 2. Celery Chain 발행
    └─ 3. Streams 이벤트 → SSE 전송
```

**장점**:
- API 변경 없음 (기존 클라이언트 호환)
- UX 동일 (실시간 stage 진행)
- 변경 최소화

**단점**:
- SSE 연결 시간 = Chain 완료 시간 (~10~20초)

### 방법 2: `/start` + `/stream/{job_id}` 분리

```
POST /start → job_id 반환
GET /stream/{job_id} → SSE 구독
```

**문제점**:
- Race condition: `/start` 후 `/stream` 연결 전에 작업 완료 가능
- 리플레이 구현 필요

### 방법 3: Polling + `/result/{job_id}`

**문제점**:
- 실시간 UX 포기
- 불필요한 폴링 오버헤드

---

## 선택: 방법 1

### 선택 근거

| 기준 | 방법 1 | 방법 2 | 방법 3 |
|------|--------|--------|--------|
| API 호환 | ✅ | ❌ | ❌ |
| 실시간 UX | ✅ | ✅ | ❌ |
| 변경 범위 | 최소 | 중간 | 낮음 |
| Race condition | 없음 | 있음 | 없음 |

### 핵심 원칙

> **"구독 먼저, 발행 나중"**
>
> Redis Streams 구독을 먼저 시작한 후 Celery Chain을 발행하면,
> 이벤트 누락 없이 모든 stage를 수신할 수 있다.

---

## 구현 상세

### 아키텍처 변경

```
┌─────────────────────────────────────────────────────────────────┐
│  ❌ 현재 구조 (곱 폭발)                                          │
│                                                                  │
│  Client ──SSE──→ scan-api ──→ Celery Events (RabbitMQ)          │
│                                      │                          │
│                    클라이언트 × RabbitMQ 연결 = 곱 폭발          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ✅ 변경 후 (상수 연결)                                          │
│                                                                  │
│  Client ──SSE──→ scan-api ──→ Redis Streams                     │
│                                      ▲                          │
│                              Worker ─┘                          │
│                    scan-api당 1개 연결 (상수)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 이벤트 흐름

```
┌───────────────────────────────────────────────────────────────────┐
│  Worker → Redis Streams                                           │
├───────────────────────────────────────────────────────────────────┤
│  Stream Key: scan:events:{job_id}                                 │
│                                                                   │
│  1. XADD {stage: "queued",  status: "started",  ts: ...}         │
│  2. XADD {stage: "vision",  status: "started",  ts: ...}         │
│  3. XADD {stage: "vision",  status: "completed", ts: ...}        │
│  4. XADD {stage: "rule",    status: "started",  ts: ...}         │
│  5. XADD {stage: "rule",    status: "completed", ts: ...}        │
│  6. XADD {stage: "answer",  status: "started",  ts: ...}         │
│  7. XADD {stage: "answer",  status: "completed", ts: ...}        │
│  8. XADD {stage: "reward",  status: "started",  ts: ...}         │
│  9. XADD {stage: "reward",  status: "completed", result: {...}}  │
│ 10. XADD {stage: "done",    result_url: "/result/{job_id}"}      │
│                                                                   │
│  MAXLEN: 50 (retention)                                           │
│  TTL: 3600초 (EXPIRE)                                             │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│  scan-api → Client (SSE)                                          │
├───────────────────────────────────────────────────────────────────┤
│  event: stage                                                     │
│  data: {"step": "vision", "status": "started", "progress": 0}    │
│                                                                   │
│  event: stage                                                     │
│  data: {"step": "vision", "status": "completed", "progress": 25} │
│                                                                   │
│  ...                                                              │
│                                                                   │
│  event: ready                                                     │
│  data: {"result_url": "/result/abc123", "result": {...}}         │
└───────────────────────────────────────────────────────────────────┘
```

### 1. 공유 모듈: Redis Streams 이벤트 발행/구독

파일: `domains/_shared/events/redis_streams.py`

```python
"""Redis Streams 기반 이벤트 발행/구독 모듈.

Celery Events 대신 Redis Streams를 사용하여
SSE:RabbitMQ 연결 폭발 문제를 해결합니다.
"""

import json
import time
from typing import AsyncGenerator

import redis.asyncio as aioredis

# 설정
STREAM_PREFIX = "scan:events"
STREAM_MAXLEN = 50  # 최근 50개 이벤트만 유지
STREAM_TTL = 3600   # 1시간 후 만료


def get_stream_key(job_id: str) -> str:
    """Stream key 생성."""
    return f"{STREAM_PREFIX}:{job_id}"


# ─────────────────────────────────────────────────────────────────
# Worker용: 동기 이벤트 발행 (Celery Task에서 호출)
# ─────────────────────────────────────────────────────────────────

def publish_stage_event(
    redis_client,
    job_id: str,
    stage: str,
    status: str,
    result: dict | None = None,
    progress: int | None = None,
) -> str:
    """Worker가 호출: stage 이벤트를 Redis Streams에 발행.
    
    Args:
        redis_client: 동기 Redis 클라이언트
        job_id: Chain의 root task ID
        stage: queued, vision, rule, answer, reward, done
        status: started, completed, failed
        result: 완료 시 결과 데이터
        progress: 진행률 (0~100)
    
    Returns:
        발행된 메시지 ID
    """
    stream_key = get_stream_key(job_id)
    
    event = {
        "stage": stage,
        "status": status,
        "ts": str(time.time()),
    }
    
    if progress is not None:
        event["progress"] = str(progress)
    
    if result:
        event["result"] = json.dumps(result, ensure_ascii=False)
    
    # XADD + MAXLEN (오래된 이벤트 자동 삭제)
    msg_id = redis_client.xadd(stream_key, event, maxlen=STREAM_MAXLEN)
    
    # Stream에 TTL 설정 (첫 이벤트 발행 시)
    redis_client.expire(stream_key, STREAM_TTL)
    
    return msg_id


# ─────────────────────────────────────────────────────────────────
# API용: 비동기 이벤트 구독 (SSE 엔드포인트에서 호출)
# ─────────────────────────────────────────────────────────────────

async def subscribe_events(
    redis_client: aioredis.Redis,
    job_id: str,
    timeout_ms: int = 5000,
) -> AsyncGenerator[dict, None]:
    """SSE 엔드포인트가 호출: Redis Streams 이벤트 구독.
    
    Args:
        redis_client: 비동기 Redis 클라이언트
        job_id: Chain의 root task ID
        timeout_ms: XREAD 블로킹 타임아웃 (밀리초)
    
    Yields:
        이벤트 딕셔너리 (stage, status, result 등)
    """
    stream_key = get_stream_key(job_id)
    last_id = "0"  # 처음부터 읽기 (리플레이 지원)
    
    while True:
        # XREAD: 새 이벤트 대기 (blocking)
        events = await redis_client.xread(
            {stream_key: last_id},
            block=timeout_ms,
            count=10,
        )
        
        if not events:
            # 타임아웃 → keepalive 이벤트
            yield {"type": "keepalive"}
            continue
        
        for stream_name, messages in events:
            for msg_id, data in messages:
                last_id = msg_id
                
                # 바이트 → 문자열 디코딩
                event = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in data.items()
                }
                
                # result JSON 파싱
                if "result" in event:
                    try:
                        event["result"] = json.loads(event["result"])
                    except json.JSONDecodeError:
                        pass
                
                # progress 정수 변환
                if "progress" in event:
                    try:
                        event["progress"] = int(event["progress"])
                    except ValueError:
                        pass
                
                yield event
                
                # done 이벤트면 종료
                if event.get("stage") == "done":
                    return
```

### 2. Worker 태스크 수정

각 태스크 시작/완료 시 이벤트 발행:

파일: `domains/scan/tasks/vision.py` (예시)

```python
from domains._shared.events.redis_streams import publish_stage_event

@celery_app.task(bind=True, base=BaseTask)
def scan_vision_task(self, payload: dict, job_id: str):
    """Vision 분류 태스크."""
    redis_client = get_sync_redis()
    
    # 시작 이벤트
    publish_stage_event(redis_client, job_id, "vision", "started", progress=0)
    
    try:
        result = run_vision_classification(payload)
        
        # 완료 이벤트
        publish_stage_event(
            redis_client, job_id, "vision", "completed",
            progress=25,
        )
        
        return {"job_id": job_id, "vision_result": result}
    
    except Exception as e:
        # 실패 이벤트
        publish_stage_event(
            redis_client, job_id, "vision", "failed",
            result={"error": str(e)},
        )
        raise
```

### 3. SSE 엔드포인트 수정

파일: `domains/scan/api/v1/endpoints/completion.py`

```python
import redis.asyncio as aioredis
from domains._shared.events.redis_streams import (
    get_stream_key,
    publish_stage_event,
    subscribe_events,
)

@router.post("/classify/completion")
async def classify_completion(payload: ClassificationRequest, user: CurrentUser):
    """SSE 스트리밍 분류 엔드포인트.
    
    핵심 변경: Celery Events → Redis Streams
    """
    job_id = str(uuid.uuid4())
    
    async def generate():
        # 1. Redis 연결 (비동기)
        redis_client = aioredis.from_url(
            settings.REDIS_STREAMS_URL,
            decode_responses=False,  # 바이트 유지
        )
        
        try:
            # 2. 구독 시작 전에 queued 이벤트 발행 (동기 Redis로)
            sync_redis = get_sync_redis()
            publish_stage_event(sync_redis, job_id, "queued", "started", progress=0)
            
            # 3. Celery Chain 발행
            chain = (
                scan_vision_task.s(payload.dict(), job_id) |
                scan_rule_task.s() |
                scan_answer_task.s() |
                scan_reward_task.s()
            )
            chain.apply_async(task_id=job_id)
            
            # 4. 첫 SSE 이벤트 (즉시)
            yield format_sse({
                "step": "queued",
                "status": "started",
                "progress": 0,
                "job_id": job_id,
            })
            
            # 5. Redis Streams 구독 루프
            async for event in subscribe_events(redis_client, job_id):
                if event.get("type") == "keepalive":
                    yield ": keepalive\n\n"
                    continue
                
                stage = event.get("stage")
                status = event.get("status")
                progress = event.get("progress", 0)
                
                sse_data = {
                    "step": stage,
                    "status": status,
                    "progress": progress,
                }
                
                # 완료 이벤트
                if stage == "done":
                    sse_data["result"] = event.get("result")
                    sse_data["result_url"] = f"/api/v1/scan/result/{job_id}"
                    yield format_sse(sse_data, event_type="ready")
                    break
                
                # reward 완료 시 결과 포함
                if stage == "reward" and status == "completed":
                    sse_data["result"] = event.get("result")
                
                yield format_sse(sse_data, event_type="stage")
        
        finally:
            await redis_client.close()
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def format_sse(data: dict, event_type: str = "stage") -> str:
    """SSE 포맷으로 변환."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

---

## 기대 효과

### 연결 비율 개선

| 지표 | 현재 | 예상 | 개선 |
|------|------|------|------|
| SSE : RabbitMQ | 1:21 | 1:0 | 100% 제거 |
| SSE : Redis | N/A | Pod당 1개 | 상수 |
| 메모리 (50 VU) | 676Mi | ~200Mi | 70% 감소 |
| 503 에러 | 발생 | 해소 | - |

### VU 수용량 예상

| 구조 | 예상 VU | 비고 |
|------|---------|------|
| 현재 (Celery Events) | 20~30 | 연결 폭발 |
| Redis Streams | 150~200+ | 상수 연결 |

### Stage UX 유지

기존과 동일한 실시간 진행 상황 전달:

```
event: stage
data: {"step": "vision", "status": "started", "progress": 0}

event: stage
data: {"step": "vision", "status": "completed", "progress": 25}

event: stage
data: {"step": "rule", "status": "started", "progress": 25}

...

event: ready
data: {"step": "done", "result": {...}, "result_url": "/result/abc123"}
```

---

## 테스트 계획

### 1. 단위 테스트

```python
# tests/unit/test_redis_streams.py

async def test_publish_subscribe_flow():
    """이벤트 발행 → 구독 흐름 검증."""
    job_id = "test-job-123"
    
    # 발행
    publish_stage_event(redis, job_id, "vision", "started")
    publish_stage_event(redis, job_id, "vision", "completed")
    publish_stage_event(redis, job_id, "done", "completed", result={"key": "value"})
    
    # 구독
    events = []
    async for event in subscribe_events(async_redis, job_id):
        events.append(event)
    
    assert len(events) == 3
    assert events[0]["stage"] == "vision"
    assert events[2]["stage"] == "done"
```

### 2. 통합 테스트

```python
# tests/integration/test_sse_redis_streams.py

async def test_completion_endpoint_with_redis_streams():
    """실제 SSE 엔드포인트 E2E 테스트."""
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "/api/v1/scan/classify/completion",
            json={"image_url": "..."},
        ) as response:
            events = []
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
            
            # 모든 stage 수신 확인
            stages = [e["step"] for e in events]
            assert "vision" in stages
            assert "rule" in stages
            assert "answer" in stages
            assert "reward" in stages
```

### 3. 부하 테스트 (k6)

```javascript
// tests/performance/sse-redis-streams.js

export const options = {
  stages: [
    { duration: "60s", target: 50 },   // 0 → 50 VU ramp-up
    { duration: "120s", target: 50 },  // 50 VU 유지
    { duration: "30s", target: 0 },    // ramp-down
  ],
  thresholds: {
    http_req_failed: ["rate<0.05"],      // 실패율 5% 미만
    sse_total_duration: ["p(95)<30000"], // 95%가 30초 이내
  },
};
```

### 4. 검증 지표

| 지표 | 목표 | 모니터링 |
|------|------|---------|
| RabbitMQ 연결 | SSE와 무관 | Prometheus |
| scan-api 메모리 | < 300Mi | Grafana |
| 503 에러 | 0% | k6 |
| SSE 성공률 | > 95% | k6 |

---

---

## 구현 현황

### 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `domains/_shared/events/__init__.py` | 신규: Redis Streams 모듈 export |
| `domains/_shared/events/redis_streams.py` | 신규: 이벤트 발행/구독 함수 |
| `domains/scan/tasks/vision.py` | 수정: 시작/완료 이벤트 발행 추가 |
| `domains/scan/tasks/rule.py` | 수정: 시작/완료 이벤트 발행 추가 |
| `domains/scan/tasks/answer.py` | 수정: 시작/완료 이벤트 발행 추가 |
| `domains/scan/tasks/reward.py` | 수정: 시작/완료/done 이벤트 발행 추가 |
| `domains/scan/api/v1/endpoints/completion.py` | 수정: Celery Events → Redis Streams 전환 |

### 다음 단계

1. 클러스터 배포
2. k6 50 VU 테스트 수행
3. 결과 검증:
   - RabbitMQ 연결 수 (SSE와 무관해야 함)
   - scan-api 메모리 사용량 (< 300Mi 목표)
   - SSE 성공률 (> 95% 목표)
4. 결과 반영 후 문서 업데이트

---

## 관련 문서

- [#13 SSE 50 VU 병목 분석](./23-sse-bottleneck-analysis-50vu.md)
- [#12 LLM Queue System Architecture](./21-llm-queue-system-architecture.md)
- [#11 SSE Performance Benchmark](./22-scan-sse-performance-benchmark.md)

---

## Appendix: Redis 설정

### DB 분리 전략

```yaml
# 같은 Redis 인스턴스, DB만 분리
REDIS_CACHE_URL: redis://dev-redis:6379/0      # 캐시 (LRU eviction)
REDIS_STREAMS_URL: redis://dev-redis:6379/1    # 이벤트 (noeviction)
REDIS_RESULT_URL: redis://dev-redis:6379/2     # Celery 결과
```

### Streams 정책

```yaml
# redis.conf (성숙기)
maxmemory-policy: noeviction  # Streams DB에서 eviction 방지
```

### MAXLEN vs TTL

| 설정 | 값 | 목적 |
|------|-----|------|
| MAXLEN | 50 | 오래된 이벤트 자동 삭제 |
| TTL (EXPIRE) | 3600초 | 완료된 job stream 정리 |
