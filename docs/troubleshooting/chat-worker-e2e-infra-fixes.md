# Chat Worker E2E 인프라 정합성 트러블슈팅

> **기간**: 2026-01-17 ~ 2026-01-19
> **관련 PR**: #400 ~ #419
> **목적**: Chat Worker E2E 테스트 중 발생한 인프라 레벨 오류 해결

---

## 개요

Chat Worker E2E 테스트 진행 중 발생한 인프라 정합성 이슈들을 순차적으로 해결한 기록.

```
테스트 플로우:
POST /api/v1/chat (세션 생성)
    → POST /api/v1/chat/{session_id} (메시지 전송)
        → GET /api/v1/chat/{job_id}/events (SSE 스트림)
            → chat-worker 처리
                → SSE 이벤트 수신
```

---

## Issue #1: SSE 라우팅 오류

### PR #400

### 증상

```bash
GET /api/v1/chat/{job_id}/events
# 예상: sse-gateway로 라우팅
# 실제: chat-api로 라우팅 (404 또는 잘못된 응답)
```

### 원인

Istio VirtualService 매칭 우선순위:
1. Exact match
2. **Prefix match** (우선)
3. Regex match

`chat-vs`의 `prefix: /api/v1/chat`이 `sse-gateway-external`의 `regex: /api/v1/[^/]+/[^/]+/events`보다 우선 적용.

### 해결

`chat-vs` 내에 SSE events 라우팅 규칙을 prefix 규칙보다 **앞에** 배치:

```yaml
# workloads/routing/chat/base/virtual-service.yaml
http:
  # SSE Events → sse-gateway (먼저!)
  - name: chat-sse-events
    match:
    - uri:
        regex: /api/v1/chat/[^/]+/events
      method:
        exact: GET
    route:
    - destination:
        host: sse-gateway.sse-consumer.svc.cluster.local

  # Chat API (prefix - 나중에)
  - match:
    - uri:
        prefix: /api/v1/chat
    route:
    - destination:
        host: chat-api.chat.svc.cluster.local
```

### 교훈

> Istio VirtualService에서 regex는 prefix보다 우선순위가 낮다.
> 같은 VirtualService 내에서 순서로 우선순위를 제어해야 한다.

---

## Issue #2: TaskIQ 메시지 형식 불일치

### PR #401

### 증상

```
chat-worker 로그:
Cannot parse message: b'{"args": [], "kwargs": {...}}'
ValidationError: 3 validation errors for TaskiqMessage
  task_id: Field required
  task_name: Field required
  labels: Field required
```

### 원인

`job_submitter.py`에서 `BrokerMessage.message`에 `{"args": [], "kwargs": {...}}`만 전송.
Worker의 `broker.formatter.loads()`는 전체 `TaskiqMessage` 형식을 기대.

```python
# Before (잘못됨)
message = {"args": [], "kwargs": {...}}

# After (정상)
message = {
    "task_id": job_id,
    "task_name": "chat.process",
    "labels": {},
    "args": [],
    "kwargs": {...},
}
```

### 해결

```python
# apps/chat/infrastructure/messaging/job_submitter.py
taskiq_message = {
    "task_id": job_id,
    "task_name": "chat.process",
    "labels": {},
    "args": [],
    "kwargs": {
        "job_id": job_id,
        "user_id": user_id,
        "message": message,
        # ...
    },
}
```

### 교훈

> TaskIQ의 `BrokerMessage`와 `TaskiqMessage`는 다른 형식.
> API 측에서 직접 큐에 publish할 때는 Worker가 기대하는 전체 형식을 맞춰야 한다.

---

## Issue #3: LangGraph Checkpointer 타입 오류

### PR #408, #409, #410

### 증상

```
TypeError: Invalid checkpointer provided.
Expected an instance of BaseCheckpointSaver,
got <class 'AsyncGeneratorContextManager'>
```

### 원인

1. `CachedPostgresSaver`가 `BaseCheckpointSaver`를 상속하지 않음
2. `AsyncRedisSaver`가 async context manager를 반환하여 싱글톤 패턴과 호환 안 됨

### 해결

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/checkpointer.py

from langgraph.checkpoint.base import BaseCheckpointSaver  # 상속 추가

class CachedPostgresSaver(BaseCheckpointSaver):  # 상속!
    """PostgreSQL 체크포인터 with 캐싱."""
    ...

# Redis checkpointer: AsyncRedisSaver 대신 MemorySaver fallback
def create_redis_checkpointer():
    # AsyncRedisSaver는 context manager라 싱글톤 불가
    # MemorySaver로 fallback (개발 환경)
    return MemorySaver()
```

### 교훈

> LangGraph 1.0+에서 커스텀 체크포인터는 반드시 `BaseCheckpointSaver`를 상속해야 한다.
> `AsyncRedisSaver`는 async context manager로 설계되어 DI 컨테이너의 싱글톤 패턴과 호환되지 않는다.

---

## Issue #4: Redis DNS 해석 실패

### PR #411

### 증상

```
redis.exceptions.ConnectionError:
Error -2 connecting to dev-redis.redis.svc.cluster.local:6379.
Name or service not known.
```

### 원인

`dev-redis.redis.svc.cluster.local` 서비스가 클러스터에 존재하지 않음.
실제 Redis 서비스명: `rfr-pubsub-redis` (Redis Failover for Pub/Sub)

### 해결

```yaml
# workloads/secrets/external-secrets/dev/chat-worker-secrets.yaml
CHAT_WORKER_REDIS_URL: redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0
```

### 클러스터 Redis 서비스 구조

```
redis namespace:
├── rfr-streams-redis       # Redis Streams용 (이벤트 버스)
├── rfr-pubsub-redis        # Pub/Sub용 (SSE)
└── rfr-cache-redis         # 캐시용 (선택)
```

### 교훈

> Redis Failover(rfr-*) 서비스 명명 규칙을 문서화하고 일관되게 사용해야 한다.

---

## Issue #5: Redis READONLY 오류

### PR #412

### 증상

```
redis.exceptions.ResponseError:
-READONLY You can't write against a read only replica.
```

### 원인

`rfr-pubsub-redis` headless service가 port 6379를 노출하지 않음 (9121만 노출).
서비스 DNS로 연결 시 replica pod에 연결될 수 있음.

```bash
kubectl get svc -n redis rfr-pubsub-redis -o yaml
# ports:
#   - port: 9121  # metrics만!
#   # 6379 없음
```

### 해결

Master pod DNS로 직접 연결:

```yaml
# Before (서비스 DNS - replica 연결 가능)
CHAT_WORKER_REDIS_URL: redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0

# After (Master pod DNS - 직접 연결)
CHAT_WORKER_REDIS_URL: redis://rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379/0
```

### Pod DNS 형식

```
{pod-name}.{headless-service}.{namespace}.svc.cluster.local

예: rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local
    ^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^^^^
    Pod 이름          Headless Service  Namespace
```

### 주의사항

> Direct pod DNS는 failover 시 수동 업데이트 필요.
> 장기적으로 Sentinel-aware client 또는 서비스 포트 수정 필요.

### 교훈

> Headless service가 애플리케이션 포트를 노출하지 않으면 pod DNS를 직접 사용해야 한다.
> Redis Sentinel 환경에서는 Sentinel-aware client 사용을 권장.

---

## Issue #6: OpenAI API 파라미터 오류

### PR #413

### 증상

```
400 Bad Request:
Unsupported parameter: 'max_tokens' is not supported with this model.
Use 'max_completion_tokens' instead.
```

### 원인

OpenAI의 새로운 모델(gpt-4o 등)에서 `max_tokens` 파라미터가 `max_completion_tokens`로 변경됨.

### 해결

```python
# apps/chat_worker/infrastructure/llm/clients/openai_client.py

# Before
if max_tokens is not None:
    kwargs["max_tokens"] = max_tokens

# After
if max_tokens is not None:
    kwargs["max_completion_tokens"] = max_tokens  # 파라미터명 변경
```

### 교훈

> OpenAI API 버전/모델별 파라미터 차이를 확인해야 한다.
> 새 모델 사용 시 API 문서를 반드시 확인.

---

## Issue #7: LangGraph State Access 오류

### PR #413

### 증상

```
KeyError: 'job_id'
```

### 원인

`astream_events` 사용 시 일부 이벤트에서 state 필드가 누락될 수 있음.
`state["job_id"]` 직접 접근 시 KeyError 발생.

### 해결

모든 노드에서 안전한 접근 방식으로 변경:

```python
# Before (위험)
job_id = state["job_id"]

# After (안전)
job_id = state.get("job_id", "")
```

**수정된 노드**:
- `answer_node.py`
- `feedback_node.py`
- `intent_node.py`
- `rag_node.py`
- `web_search_node.py`

### 교훈

> LangGraph의 `astream_events`는 다양한 이벤트 타입을 발생시키며,
> 모든 이벤트에 전체 state가 포함되지 않을 수 있다.
> 항상 `.get()` 메서드로 안전하게 접근해야 한다.

---

## Issue #8: LangGraph Send API 병렬 실행 충돌

### PR #414

### 증상

```
langgraph.errors.InvalidUpdateError:
At key '__root__': Can receive only one value per step.
Use an Annotated key with a reducer.
```

### 원인

```python
# StateGraph(dict) 사용
graph = StateGraph(dict)  # Untyped state

# Send API로 병렬 실행
sends = [
    Send("waste_rag", state),
    Send("weather", state),
    Send("collection_point", state),
]

# 각 노드가 {**state, "my_field": value} 반환
# → 병렬로 __root__ 업데이트 시도 → 충돌!
```

### 임시 해결

Dynamic routing 비활성화:

```python
# apps/chat_worker/setup/dependencies.py
return create_chat_graph(
    ...
    enable_dynamic_routing=False,  # 임시 비활성화
)
```

### 근본 해결 (TODO)

1. `StateGraph(ChatState)` - Typed State 사용
2. 각 subagent별 전용 채널 정의 with Annotated reducer
3. 노드는 자기 채널만 반환 (`{**state, ...}` 금지)

> 상세 설계: `docs/plans/langgraph-channel-separation-adr.md`

### 교훈

> LangGraph Send API로 병렬 실행 시 반드시 Typed State + Annotated Reducer 필요.
> `StateGraph(dict)`는 단일 노드 순차 실행에만 안전.

---

## Issue #9: Redis Streams URL 불일치

### PR #419

### 증상

```
SSE 연결 성공, keepalive만 수신, 실제 이벤트 없음
```

### 진단 과정

1. **Worker 처리 확인** - 로그에서 `ProcessChatCommand completed` 확인 → Worker 정상
2. **Redis Streams 확인** - `rfr-streams-redis`의 `chat:events:*` 길이 0 → 이벤트 없음
3. **환경변수 확인**:
   - `chat-worker`: `REDIS_URL` → `rfr-pubsub-redis`
   - `event-router`: `REDIS_STREAMS_URL` → `rfr-streams-redis`
4. **발행 위치 확인** - `rfr-pubsub-redis`에 `chat:published:*` 키 존재 → 잘못된 Redis에 발행

### 원인

```
┌─────────────────────────────────────────────────────────────────┐
│                    Redis URL Mismatch                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  chat-worker                                                     │
│  └─ RedisProgressNotifier                                       │
│      └─ get_redis() → settings.redis_url                        │
│          └─ CHAT_WORKER_REDIS_URL (rfr-pubsub-redis) ❌         │
│                                                                  │
│  event-router                                                    │
│  └─ REDIS_STREAMS_URL (rfr-streams-redis) ✅                    │
│                                                                  │
│  결과: chat-worker는 pubsub에 발행, event-router는 streams 감시 │
│        → 이벤트 손실!                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**코드 문제점**:
- `config.py`에 `redis_streams_url` 설정 없음
- `dependencies.py`에서 `RedisProgressNotifier`가 `get_redis()` 사용
- `get_redis()`는 `settings.redis_url` 반환 (pubsub Redis)

### 해결

**1. config.py에 redis_streams_url 추가**:

```python
# apps/chat_worker/setup/config.py

# Redis (기본 - 캐시, Pub/Sub 등)
redis_url: str = "redis://localhost:6379/0"

# Redis Streams (이벤트 스트리밍 전용)
# event-router와 동일한 Redis를 바라봐야 함
# None이면 redis_url 사용 (로컬 개발용)
redis_streams_url: str | None = None
```

**2. dependencies.py에 get_redis_streams() 추가**:

```python
# apps/chat_worker/setup/dependencies.py

_redis_streams: Redis | None = None

async def get_redis_streams() -> Redis:
    """Redis Streams 클라이언트 싱글톤 (이벤트 스트리밍 전용)."""
    global _redis_streams
    if _redis_streams is None:
        settings = get_settings()
        # redis_streams_url이 설정되면 사용, 아니면 redis_url 폴백
        streams_url = settings.redis_streams_url or settings.redis_url
        _redis_streams = Redis.from_url(
            streams_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis Streams connected: %s", streams_url)
    return _redis_streams


async def get_progress_notifier() -> ProgressNotifierPort:
    """ProgressNotifier 싱글톤 (SSE/UI 이벤트)."""
    global _progress_notifier
    if _progress_notifier is None:
        # Streams 전용 Redis 사용 (event-router와 동일)
        redis = await get_redis_streams()  # get_redis() → get_redis_streams()
        _progress_notifier = RedisProgressNotifier(redis=redis)
    return _progress_notifier
```

### 검증

**1. 설정 로드 확인**:

```bash
kubectl exec -n chat deploy/chat-worker -c chat-worker -- python3 -c "
from chat_worker.setup.config import get_settings
s = get_settings()
print(f'redis_url: {s.redis_url}')
print(f'redis_streams_url: {s.redis_streams_url}')
"
# redis_url: redis://rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379/0
# redis_streams_url: redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
```

**2. Redis 연결 확인**:

```bash
kubectl exec -n chat deploy/chat-worker -c chat-worker -- python3 -c "
import asyncio
from chat_worker.setup.dependencies import get_redis_streams

async def check():
    redis = await get_redis_streams()
    print(f'Connection: {redis.connection_pool}')
    pong = await redis.ping()
    print(f'Ping: {pong}')

asyncio.run(check())
"
# Connection: <...host=rfr-streams-redis.redis.svc.cluster.local...>
# Ping: True
```

**3. XADD 테스트**:

```bash
kubectl exec -n chat deploy/chat-worker -c chat-worker -- python3 -c "
import asyncio
from chat_worker.setup.dependencies import get_progress_notifier
import time

async def test():
    notifier = await get_progress_notifier()
    job_id = f'test-{int(time.time())}'
    msg_id = await notifier.notify_stage(job_id, 'queued', 'pending', 0)
    print(f'Published: {msg_id}')

asyncio.run(test())
"
# Published: 1768763110543-0

# rfr-streams-redis에서 확인
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XLEN chat:events:1
# 1  ← 이벤트 존재!
```

**4. E2E 테스트 성공**:

```
=== E2E Test Results ===
✅ Chat 생성: b8447c1e-3e29-4dd9-a52f-4f42e09a47cb
✅ 메시지 전송: job_id 8aed43be-0a7e-49e4-9bae-5c8db5dd9166
✅ SSE 이벤트 수신:
   - queued → intent → waste_rag → weather → aggregator → answer → done
✅ 답변 생성: "무색 음료/생수 페트병(PET)이라면..."
```

### Redis 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                 Redis Streams Event Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  chat-worker                                                     │
│      │ XADD chat:events:{shard}                                 │
│      ▼                                                          │
│  rfr-streams-redis ◄─── event-router (XREADGROUP)              │
│                              │                                   │
│                              │ PUBLISH sse:events:{job_id}      │
│                              ▼                                   │
│                         rfr-pubsub-redis                        │
│                              │                                   │
│                              │ SUBSCRIBE                        │
│                              ▼                                   │
│                         sse-gateway → SSE → Client              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 환경변수 매핑

| Component | Variable | Redis Instance | Purpose |
|-----------|----------|----------------|---------|
| chat-worker | `REDIS_URL` | rfr-pubsub-redis | 캐시, 기타 |
| chat-worker | `REDIS_STREAMS_URL` | rfr-streams-redis | 이벤트 발행 |
| event-router | `REDIS_STREAMS_URL` | rfr-streams-redis | 이벤트 소비 |
| event-router | `REDIS_PUBSUB_URL` | rfr-pubsub-redis | SSE 브로드캐스트 |

### 교훈

> 분산 시스템에서 Producer와 Consumer는 반드시 같은 데이터 저장소를 바라봐야 한다.
> Redis Streams와 Pub/Sub은 용도가 다르며, 각각 전용 인스턴스를 사용할 때는 연결 설정을 분리해야 한다.
> 환경변수 네이밍 (`REDIS_URL` vs `REDIS_STREAMS_URL`)을 명확히 하여 혼동을 방지해야 한다.

---

## 요약

| Issue | PR | 레이어 | 원인 | 해결 |
|-------|-----|-------|------|------|
| SSE 라우팅 | #400 | Istio | VirtualService 우선순위 | 규칙 순서 조정 |
| TaskIQ 메시지 | #401 | Messaging | 메시지 형식 불일치 | 전체 TaskiqMessage 형식 사용 |
| Checkpointer | #408-410 | LangGraph | BaseCheckpointSaver 미상속 | 상속 추가, MemorySaver fallback |
| Redis DNS | #411 | K8s | 잘못된 서비스명 | rfr-pubsub-redis 사용 |
| Redis READONLY | #412 | K8s | Headless service 포트 | Direct pod DNS |
| OpenAI API | #413 | LLM | 파라미터명 변경 | max_completion_tokens |
| State Access | #413 | LangGraph | astream_events 동작 | .get() 안전 접근 |
| Send API 충돌 | #414 | LangGraph | Untyped State + 병렬 | Typed State + Reducer (TODO) |
| Redis Streams URL | #419 | Redis | Producer/Consumer URL 불일치 | redis_streams_url 분리 |

---

## 레이어별 교훈

### Istio/Routing

- VirtualService에서 regex < prefix 우선순위
- 같은 서비스 내에서 규칙 순서로 제어

### Kubernetes/Service Discovery

- Redis Failover 서비스 명명 규칙 (rfr-*)
- Headless service 포트 확인 필수
- Sentinel 환경에서 master pod DNS 직접 사용 시 failover 고려

### Messaging (TaskIQ/RabbitMQ)

- BrokerMessage와 TaskiqMessage 형식 구분
- API → Worker 직접 publish 시 전체 메시지 형식 준수

### LangGraph

- 커스텀 Checkpointer는 BaseCheckpointSaver 상속 필수
- astream_events 시 state 필드 안전 접근
- Send API 병렬 실행 시 Typed State + Reducer 필수

### OpenAI API

- 모델별 파라미터 차이 확인 (max_tokens vs max_completion_tokens)

### Redis (Streams/Pub/Sub)

- Producer와 Consumer는 반드시 같은 Redis 인스턴스를 바라봐야 함
- Redis Streams와 Pub/Sub은 용도별로 분리된 인스턴스 사용 권장
- 환경변수 네이밍을 명확히 구분 (`REDIS_URL` vs `REDIS_STREAMS_URL` vs `REDIS_PUBSUB_URL`)
- 코드에서도 용도별로 클라이언트 분리 (`get_redis()` vs `get_redis_streams()`)
