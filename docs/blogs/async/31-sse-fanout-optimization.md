# SSE Fan-out 최적화: 연결당 XREAD에서 중앙 Consumer 패턴으로

## 개요

Redis Streams 기반 SSE 구현에서 발생한 성능 병목을 분석하고, Twitter의 Fan-out 아키텍처를 참고하여 최적화 방안을 제시합니다.

**관련 문서:**
- [Redis Streams SSE 마이그레이션](./24-redis-streams-sse-migration.md)
- [KEDA 이벤트 드리븐 오토스케일링](./27-keda-event-driven-autoscaling.md)

---

## 1. 현재 아키텍처 분석

### 1.1. 구조: 연결당 XREAD (N:N)

```
┌─────────────────────────────────────────────────────────────┐
│                     현재 아키텍처                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SSE Client 1 ──→ [while True: XREAD] ──→ Redis Stream A   │
│  SSE Client 2 ──→ [while True: XREAD] ──→ Redis Stream B   │
│  SSE Client 3 ──→ [while True: XREAD] ──→ Redis Stream C   │
│       ...                                      ...          │
│  SSE Client N ──→ [while True: XREAD] ──→ Redis Stream N   │
│                                                             │
│  → N개의 SSE 연결 = N개의 asyncio 코루틴 = N개의 XREAD 루프  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2. 코드 구조

```python
# domains/_shared/events/redis_streams.py

async def subscribe_events(redis_client, job_id, timeout_ms=5000):
    """각 SSE 연결마다 독립적인 XREAD 루프 실행."""
    stream_key = get_stream_key(job_id)
    last_id = "0"
    
    while True:
        # 각 SSE 연결이 개별적으로 XREAD 호출
        events = await redis_client.xread(
            {stream_key: last_id},
            block=timeout_ms,  # 5초마다 폴링
            count=10,
        )
        
        if not events:
            yield {"type": "keepalive"}  # 5초마다 keepalive
            continue
            
        for stream_name, messages in events:
            for msg_id, data in messages:
                yield data
```

### 1.3. 문제점

| 지표 | 50 CCU 기준 | 설명 |
|------|------------|------|
| **asyncio 코루틴** | 50개 | 각각 독립적인 while True 루프 |
| **XREAD 호출** | 10회/초 | 50 CCU × 5초 timeout = 초당 10회 |
| **keepalive 이벤트** | 10회/초 | 타임아웃마다 발생 |
| **컨텍스트 스위칭** | 과다 | 50개 코루틴 순회 |

**관측된 증상:**
- 50 VU 테스트에서 Pod CPU 85% 도달
- `Connection closed by server` 오류 간헐적 발생
- SSE 완료율 저하

---

## 2. 유사 사례: Twitter Fan-out 아키텍처

### 2.1. 참조

- [실무에서 확인한 FAN-OUT과 대규모 트래픽에서의 FAN-OUT](https://velog.io/@akfls221/실무에서-확인한-FAN-OUT과-대규모-트레픽에서의-FAN-OUT)

### 2.2. Twitter의 문제

Twitter는 2012-2013년 기하급수적으로 성장하며 초당 약 600개의 트윗을 처리하게 되었습니다.

**읽기 문제:**
- 모든 사용자가 홈페이지를 쿼리할 때 팔로우하는 모든 사람의 트윗을 제공받아야 함
- 초당 600K (60만) 읽기 요청

**Twitter의 해결책:**

```
┌─────────────────────────────────────────────────────────────┐
│                 Twitter Fan-out 아키텍처                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User A가 트윗 작성                                          │
│       ↓                                                     │
│  Fan-out 프로세스                                            │
│       ↓                                                     │
│  ┌──────────────────────────────────────────┐               │
│  │ Follower 1의 홈 타임라인 (Redis) ← 트윗 삽입 │             │
│  │ Follower 2의 홈 타임라인 (Redis) ← 트윗 삽입 │             │
│  │ Follower 3의 홈 타임라인 (Redis) ← 트윗 삽입 │             │
│  │              ...                          │               │
│  └──────────────────────────────────────────┘               │
│                                                             │
│  → 쓰기 시 Fan-out (1:N), 읽기 시 단순 조회 (1:1)            │
└─────────────────────────────────────────────────────────────┘
```

**핵심 인사이트:**
- **쓰기 시 Fan-out**: 트윗 작성 시 모든 팔로워의 타임라인에 복제
- **읽기 시 단순 조회**: 사용자의 홈 타임라인을 Redis에서 바로 읽기
- **지연 시간 감소**: DB 디스크에 닿지 않고 Redis 캐시에서 즉시 서비스

### 2.3. 유명인 문제 (Influencer Problem)

일론 머스크가 트윗하면 1억 4천만 팔로워에게 Fan-out 발생.

**하이브리드 해결책:**
- 일반 사용자: Fan-out 방식 유지
- 유명인: 팔로워가 새로고침 시 유명인 타임라인에서 직접 조회 후 병합

---

## 3. 개선 계획

### 3.1. Phase A: 즉시 최적화 (현재 구조 유지)

**변경 내용:**
```python
# 기존
timeout_ms: int = 5000,   # 5초 → keepalive 빈도 높음

# 변경
timeout_ms: int = 15000,  # 15초 → keepalive 빈도 3배 감소
```

**예상 효과:**
- keepalive 이벤트: 초당 10회 → 초당 3.3회 (50 CCU 기준)
- asyncio 컨텍스트 스위칭 감소

### 3.2. Phase B: 중앙 Consumer + Memory Fan-out

**목표 아키텍처:**

```
┌─────────────────────────────────────────────────────────────┐
│                   개선된 아키텍처 (1:N Fan-out)              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ┌─ asyncio.Queue(A) → SSE Client 1      │
│  Central Consumer ─┼─ asyncio.Queue(B) → SSE Client 2      │
│   (단일 XREAD)     ├─ asyncio.Queue(C) → SSE Client 3      │
│        ↓           └─ asyncio.Queue(N) → SSE Client N      │
│  Redis Streams                                              │
│  (모든 활성 job_id)                                         │
│                                                             │
│  → 1개의 XREAD 루프가 N개의 Queue에 이벤트 분배              │
└─────────────────────────────────────────────────────────────┘
```

**핵심 컴포넌트:**

1. **SSEBroadcastManager**: 싱글톤 매니저
   - 활성 job_id별 subscriber(Queue) 관리
   - 단일 background task로 Redis XREAD
   - 이벤트 수신 시 해당 job_id의 모든 Queue에 분배

2. **subscribe() 메서드**: SSE 엔드포인트 연동
   - job_id에 대한 Queue 생성 및 등록
   - Queue에서 이벤트 수신 (asyncio.Queue.get())
   - 연결 종료 시 Queue 정리

**예상 효과:**

| 지표 | 현재 (N:N) | 개선 후 (1:N) | 개선율 |
|------|-----------|--------------|--------|
| **XREAD 호출** | 10회/초 | 0.2회/초 | **50배 감소** |
| **asyncio 루프** | 50개 | 1개 | **50배 감소** |
| **컨텍스트 스위칭** | 과다 | 최소화 | 대폭 개선 |

---

## 4. 구현 세부사항

### 4.1. SSEBroadcastManager 클래스

```python
# domains/_shared/events/broadcast_manager.py

class SSEBroadcastManager:
    """단일 Redis Consumer + Memory Fan-out 패턴.
    
    Twitter의 Fan-out 아키텍처 참조:
    - 단일 background task가 Redis XREAD
    - job_id별 asyncio.Queue로 이벤트 분배
    
    사용법:
        manager = SSEBroadcastManager.get_instance()
        async for event in manager.subscribe(job_id):
            yield format_sse(event)
    """
    
    _instance: ClassVar[SSEBroadcastManager | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    
    def __init__(self):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._last_ids: dict[str, str] = {}  # job_id → last_id
        self._background_task: asyncio.Task | None = None
        self._redis_client: aioredis.Redis | None = None
    
    @classmethod
    async def get_instance(cls) -> SSEBroadcastManager:
        """싱글톤 인스턴스 반환."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._start_consumer()
            return cls._instance
    
    async def subscribe(self, job_id: str) -> AsyncGenerator[dict, None]:
        """job_id에 대한 구독 시작."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[job_id].add(queue)
        self._last_ids.setdefault(job_id, "0")
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield event
                    if event.get("stage") == "done":
                        break
                except asyncio.TimeoutError:
                    yield {"type": "keepalive"}
        finally:
            self._subscribers[job_id].discard(queue)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
                self._last_ids.pop(job_id, None)
    
    async def _consumer_loop(self):
        """단일 background task: Redis XREAD → Queue 분배."""
        self._redis_client = await get_async_redis_client()
        
        while True:
            try:
                if not self._subscribers:
                    await asyncio.sleep(0.1)
                    continue
                
                # 모든 활성 job_id의 Stream을 XREAD
                streams = {
                    get_stream_key(jid): self._last_ids.get(jid, "0")
                    for jid in self._subscribers
                }
                
                events = await self._redis_client.xread(
                    streams, block=5000, count=100
                )
                
                if not events:
                    continue
                
                for stream_key, messages in events:
                    job_id = self._extract_job_id(stream_key)
                    
                    for msg_id, data in messages:
                        self._last_ids[job_id] = msg_id
                        event = self._parse_event(data)
                        
                        # 해당 job_id의 모든 Queue에 이벤트 전달
                        for queue in self._subscribers.get(job_id, []):
                            await queue.put(event)
                            
            except Exception as e:
                logger.error("consumer_loop_error", extra={"error": str(e)})
                await asyncio.sleep(1)
```

### 4.2. completion.py 연동

```python
# domains/scan/api/v1/endpoints/completion.py

async def _completion_generator_v2(payload, user, service):
    # ... 기존 로직 ...
    
    # 변경: BroadcastManager 사용
    manager = await SSEBroadcastManager.get_instance()
    
    async for event in manager.subscribe(task_id):
        if event.get("type") == "keepalive":
            yield ": keepalive\n\n"
            continue
            
        # ... 이벤트 처리 ...
        yield _format_sse(sse_data, event_type="stage")
```

---

## 5. 테스트 계획

### 5.1. 성능 테스트

```bash
# k6 SSE 부하 테스트
k6 run -e BASE_URL=https://api.dev.growbin.app \
       -e ACCESS_COOKIE="..." \
       tests/performance/k6-sse-test.js
```

**테스트 시나리오:**
1. Phase A 적용 후: 50 VU
2. Phase B 적용 후: 50 VU → 100 VU → 200 VU

### 5.2. 모니터링 지표

| 메트릭 | Phase A 목표 | Phase B 목표 |
|--------|-------------|-------------|
| Pod CPU | < 70% | < 50% |
| XREAD/초 | 3.3회 | 0.2회 |
| SSE 완료율 | > 90% | > 95% |
| `connected_clients` | 안정적 | 최소화 |

---

## 6. API 엔드포인트 구조

### 6.1. 새 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│  ① POST /api/v1/scan → scan-api                                 │
│     Request: { image_url, user_input }                          │
│     Response: { job_id, stream_url, result_url, status }        │
│     → Celery Chain 비동기 발행                                   │
├─────────────────────────────────────────────────────────────────┤
│  ② GET /api/v1/stream?job_id=xxx → sse-gateway                  │
│     → SSE 스트리밍 (Istio sticky session)                       │
│     Header: X-Job-Id (Consistent Hash 라우팅용)                  │
├─────────────────────────────────────────────────────────────────┤
│  ③ GET /api/v1/scan/result/{job_id} → scan-api                  │
│     → 최종 결과 조회 (Redis Cache)                               │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2. 클라이언트 흐름

```javascript
// 1. 작업 제출
const submitRes = await fetch('/api/v1/scan', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ image_url: '...' }),
});
const { job_id, stream_url } = await submitRes.json();

// 2. SSE 스트리밍 구독
const eventSource = new EventSource(`/api/v1/stream?job_id=${job_id}`);
eventSource.addEventListener('vision', (e) => updateUI('vision', e.data));
eventSource.addEventListener('rule', (e) => updateUI('rule', e.data));
eventSource.addEventListener('answer', (e) => updateUI('answer', e.data));
eventSource.addEventListener('reward', (e) => updateUI('reward', e.data));
eventSource.addEventListener('done', (e) => {
  eventSource.close();
  // 3. 최종 결과 조회 (선택)
  fetchResult(job_id);
});
```

### 6.3. VirtualService 라우팅

```yaml
# /api/v1/stream → sse-gateway
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: sse-gateway-external
spec:
  hosts:
  - api.dev.growbin.app
  http:
  - match:
    - uri:
        prefix: /api/v1/stream
    route:
    - destination:
        host: sse-gateway.sse-consumer.svc.cluster.local
        port:
          number: 8000
    timeout: 86400s  # 24시간 (SSE long-lived)
```

---

## 7. 결론

현재 "연결당 XREAD" 패턴은 CCU 증가 시 선형적으로 부하가 증가하는 구조입니다.

Twitter의 Fan-out 아키텍처를 참고하여:
1. **Phase A**: 즉시 적용 가능한 timeout 조정으로 폴링 빈도 감소
2. **Phase B**: 중앙 Consumer + Memory Fan-out으로 근본적 해결

이를 통해 수천 CCU까지 확장 가능한 SSE 아키텍처를 구축할 수 있습니다.

---

## 관련 파일

- `domains/scan/api/v1/endpoints/scan.py`: 비동기 제출 및 결과 조회 엔드포인트
- `domains/sse-gateway/api/v1/stream.py`: SSE 스트리밍 엔드포인트
- `workloads/routing/sse-gateway/`: VirtualService 라우팅
- `workloads/routing/scan/`: scan-api VirtualService

---

## 참고 자료

- [Redis Streams 공식 문서](https://redis.io/docs/latest/develop/data-types/streams/)
- [antirez: Streams Design](http://antirez.com/news/114)
- [Twitter Fan-out 아키텍처](https://velog.io/@akfls221/실무에서-확인한-FAN-OUT과-대규모-트레픽에서의-FAN-OUT)
- [Python asyncio Queue](https://docs.python.org/3/library/asyncio-queue.html)

