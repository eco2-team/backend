# Chat Agent Flow Guide

> Eco² Chat 서비스의 E2E 테스트 및 트러블슈팅 가이드

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Chat Agent E2E Flow                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [1] POST /api/v1/chat              →  Create chat session (chat_id)        │
│  [2] POST /api/v1/chat/{id}/messages →  Send message (job_id, stream_url)   │
│  [3] GET  /api/v1/chat/{job_id}/events  →  Subscribe to SSE stream          │
│                                                                              │
│  ⚠️ SSE는 /sse/ 경로 없이 /chat/{job_id}/events로 직접 접근                   │
│     (chat-vs에서 regex 매칭으로 sse-gateway로 라우팅)                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## API Endpoints

| Step | Endpoint | Service | Response |
|------|----------|---------|----------|
| 1 | `POST /api/v1/chat` | chat-api | `{id, title, created_at}` |
| 2 | `POST /api/v1/chat/{chat_id}/messages` | chat-api | `{job_id, stream_url, status}` |
| 3 | `GET /api/v1/chat/{job_id}/events` | sse-gateway (via chat-vs) | SSE stream |

## Istio VirtualService Routing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Istio Routing Priority (chat-vs)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  순서가 중요! Regex는 Prefix보다 우선순위 낮음 → 같은 VS 내에서 순서로 제어   │
│                                                                              │
│  1. [regex]  /api/v1/chat/[^/]+/events  →  sse-gateway (SSE)                │
│  2. [prefix] /api/v1/chat               →  chat-api (REST)                  │
│                                                                              │
│  ⚠️ 순서 바뀌면 SSE 요청이 chat-api로 라우팅됨!                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**파일**: `workloads/routing/chat/base/virtual-service.yaml`

## E2E Test Commands

### 1. Create Chat Session

```bash
TOKEN="<JWT_TOKEN>"

curl -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"title": "E2E Test"}'

# Response: {"id": "chat_id", "title": "...", "created_at": "..."}
```

### 2. Send Message

```bash
CHAT_ID="<chat_id from step 1>"

curl -X POST "https://api.dev.growbin.app/api/v1/chat/${CHAT_ID}/messages" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message": "플라스틱 페트병은 어떻게 버려?"}'

# Response: {"job_id": "...", "stream_url": "...", "status": "submitted"}
```

### 3. Subscribe to SSE

```bash
JOB_ID="<job_id from step 2>"

# SSE 구독 (chat-vs가 sse-gateway로 라우팅)
# ⚠️ 경로: /api/v1/chat/{job_id}/events (NOT /api/v1/sse/...)
curl -sN --max-time 60 \
  "https://api.dev.growbin.app/api/v1/chat/${JOB_ID}/events" \
  -H "Accept: text/event-stream" \
  -H "Cookie: s_access=$TOKEN"
```

## SSE Event Types

| Event | Description | Example |
|-------|-------------|---------|
| `intent` | Intent 분류 완료 | `{"stage":"intent","status":"completed","progress":15}` |
| `waste_rag` | RAG 노드 시작/완료 | `{"stage":"waste_rag","status":"started"}` |
| `token` | 답변 토큰 스트리밍 | `{"stage":"token","content":"플라스틱","seq":1001}` |
| `done` | 처리 완료 | `{"stage":"done","status":"success","progress":100}` |
| `error` | 오류 발생 | `{"stage":"error","message":"..."}` |

## Intent Classification (10 types)

| Intent | Node | Description |
|--------|------|-------------|
| `WASTE` | waste_rag | 분리배출 질문 |
| `CHARACTER` | character | 캐릭터 정보 (gRPC) |
| `LOCATION` | location | 장소 검색 (Kakao API) |
| `BULK_WASTE` | bulk_waste | 대형폐기물 |
| `RECYCLABLE_PRICE` | recyclable_price | 재활용 시세 |
| `COLLECTION_POINT` | collection_point | 수거함 위치 (KECO API) |
| `WEB_SEARCH` | web_search | 웹 검색 |
| `IMAGE_GENERATION` | image_generation | 이미지 생성 |
| `GENERAL` | general | 일반 대화 |
| (weather) | weather | 날씨 enrichment (자동 추가) |

## Dynamic Routing (Send API)

```python
# Multi-Intent: "종이 버리는 법이랑 수거함도 알려줘"
→ intent = "waste"
→ additional_intents = ["collection_point"]
→ Sends:
   - Send("waste_rag", state)         # 주 intent
   - Send("collection_point", state)  # multi-intent
   - Send("weather", state)           # enrichment rule

# 3개 노드 병렬 실행!
```

## Redis Streams Event Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Redis Streams Event Pipeline                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [1] chat-worker                                                             │
│       │                                                                      │
│       │ XADD chat:events:{shard} (Redis Streams)                            │
│       ▼                                                                      │
│  [2] rfr-streams-redis (Redis Sentinel)                                     │
│       │                                                                      │
│       │ XREADGROUP (Consumer Group)                                         │
│       ▼                                                                      │
│  [3] event-router                                                            │
│       │                                                                      │
│       │ PUBLISH sse:events:{job_id} (Redis Pub/Sub)                         │
│       ▼                                                                      │
│  [4] rfr-pubsub-redis (Redis Sentinel)                                      │
│       │                                                                      │
│       │ SUBSCRIBE (SSE Gateway)                                              │
│       ▼                                                                      │
│  [5] sse-gateway → SSE Stream → Client                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Redis Instances

| Instance | Namespace | Purpose | Protocol |
|----------|-----------|---------|----------|
| `rfr-streams-redis` | redis | Event Streams (XADD/XREADGROUP) | Redis Streams |
| `rfr-pubsub-redis` | redis | SSE Broadcast (PUBLISH/SUBSCRIBE) | Redis Pub/Sub |

### Hop-by-Hop Address Reference

| Hop | Component | Kube DNS | Pod DNS (Master) | Protocol | Port |
|-----|-----------|----------|------------------|----------|------|
| 1→2 | chat-worker → Redis Streams | `rfr-streams-redis.redis.svc.cluster.local` | `rfr-streams-redis-0.rfr-streams-redis.redis.svc.cluster.local` | XADD | 6379 |
| 2→3 | Redis Streams → event-router | (Consumer Group) | - | XREADGROUP | 6379 |
| 3→4 | event-router → Redis Pub/Sub | `rfr-pubsub-redis.redis.svc.cluster.local` | `rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local` | PUBLISH | 6379 |
| 4→5 | Redis Pub/Sub → sse-gateway | (Subscriber) | - | SUBSCRIBE | 6379 |

### Stream Keys & Patterns

| Key Pattern | Example | Purpose |
|-------------|---------|---------|
| `chat:events:{shard}` | `chat:events:0` ~ `chat:events:3` | Sharded event streams (4 shards) |
| `chat:published:{job_id}:{stage}:{seq}` | `chat:published:abc123:intent:10` | Idempotency marker (TTL 2h) |
| `chat:tokens:{job_id}` | `chat:tokens:abc123` | Token stream for recovery |
| `chat:token_state:{job_id}` | `chat:token_state:abc123` | Accumulated text snapshot |
| `sse:events:{job_id}` | `sse:events:abc123` | Pub/Sub channel for SSE |

### Environment Variables

| Component | Variable | Value (Dev) |
|-----------|----------|-------------|
| chat-worker | `CHAT_WORKER_REDIS_STREAMS_URL` | `redis://rfr-streams-redis.redis.svc.cluster.local:6379/0` |
| chat-worker | `CHAT_WORKER_REDIS_URL` | `redis://rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379/0` |
| event-router | `REDIS_STREAMS_URL` | `redis://rfr-streams-redis.redis.svc.cluster.local:6379/0` |
| event-router | `REDIS_PUBSUB_URL` | `redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0` |

### Debug Commands (Redis)

```bash
# Redis Streams 확인 (rfr-streams-redis)
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XLEN chat:events:0
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XRANGE chat:events:0 - + COUNT 5

# Pub/Sub 모니터링 (rfr-pubsub-redis)
kubectl exec -n redis rfr-pubsub-redis-0 -- redis-cli PSUBSCRIBE "sse:events:*"

# Consumer Group 상태 확인
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XINFO GROUPS chat:events:0
```

## Troubleshooting

### Issue 1: SSE 요청이 404

**증상**: `GET /api/v1/chat/{job_id}/events` → 404

**원인**: VirtualService에서 SSE 규칙이 prefix 뒤에 배치

**해결**: `chat-vs`에서 SSE events 규칙을 prefix 규칙 **앞에** 배치

### Issue 2: TaskIQ 메시지 파싱 오류

**증상**: `Cannot parse message: b'{"args": [], "kwargs": {...}}'`

**원인**: Worker가 `TaskiqMessage` 전체 형식을 기대

**해결**: `task_id`, `task_name`, `labels` 필드 포함

```python
message = {
    "task_id": job_id,
    "task_name": "chat.process",
    "labels": {},
    "args": [],
    "kwargs": {...},
}
```

### Issue 3: Redis READONLY 오류

**증상**: `-READONLY You can't write against a read only replica`

**원인**: Headless service가 replica로 연결

**해결**: Master pod DNS 직접 사용

```
rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379
```

### Issue 4: LangGraph State Access 오류

**증상**: `KeyError: 'job_id'`

**원인**: `astream_events`에서 일부 이벤트에 state 누락

**해결**: `.get()` 메서드로 안전한 접근

```python
# Bad
job_id = state["job_id"]

# Good
job_id = state.get("job_id", "")
```

### Issue 5: Send API 병렬 실행 충돌

**증상**: `InvalidUpdateError: Can receive only one value per step`

**원인**: `StateGraph(dict)` + Send API 병렬 실행

**해결**: Typed State + Annotated Reducer (진행 중)

```python
# 임시: dynamic_routing 비활성화
enable_dynamic_routing=False

# 근본: StateGraph(ChatState) + Reducer
```

### Issue 6: SSE 이벤트 수신 불가 (Redis 불일치)

**증상**: SSE 연결 성공, keepalive만 수신, 실제 이벤트 없음

**원인**: chat-worker와 event-router가 다른 Redis를 바라봄

```
chat-worker → rfr-pubsub-redis (잘못됨)
event-router → rfr-streams-redis (올바름)
```

**진단**:
```bash
# chat-worker Redis 확인
kubectl exec -n chat deploy/chat-worker -c chat-worker -- env | grep REDIS

# event-router Redis 확인
kubectl exec -n event-router deploy/event-router -- env | grep REDIS

# Redis Streams 데이터 확인 (rfr-streams-redis에 데이터가 없으면 문제)
kubectl exec -n redis rfr-streams-redis-0 -- redis-cli XLEN chat:events:0
```

**해결**:
- `config.py`에 `redis_streams_url` 설정 추가
- `dependencies.py`에서 RedisProgressNotifier가 `get_redis_streams()` 사용
- ConfigMap에 `CHAT_WORKER_REDIS_STREAMS_URL` 설정 확인

## Debug Commands

```bash
# chat-worker 로그
kubectl logs -n chat -l app=chat-worker -f --tail=100

# event-router 로그
kubectl logs -n event-router -l app=event-router -f --tail=50

# sse-gateway 로그
kubectl logs -n sse-consumer -l app=sse-gateway -f --tail=50

# Redis Pub/Sub 모니터링
kubectl exec -n redis rfr-pubsub-redis-0 -- \
  redis-cli PSUBSCRIBE "sse:events:*"
```

## Reference Files

- **E2E Test Plan**: `docs/reports/e2e-intent-test-plan.md`
- **Troubleshooting**: `docs/troubleshooting/chat-worker-e2e-infra-fixes.md`
- **VirtualService (Chat)**: `workloads/routing/chat/base/virtual-service.yaml`
- **VirtualService (SSE)**: `workloads/domains/sse-gateway/base/virtualservice.yaml`
- **Frontend Spec**: `docs/specs/chat-agent-frontend-spec.md`
- **Dynamic Routing**: `docs/blogs/applied/30-langgraph-dynamic-routing-send-api.md`
- **Native Streaming**: `docs/blogs/applied/32-langgraph-native-streaming.md`

## Related PRs

| PR | Title | Issue |
|----|-------|-------|
| #400 | fix(routing): chat SSE 이벤트를 sse-gateway로 라우팅 | SSE 라우팅 오류 |
| #401 | fix(chat): TaskIQ 메시지 형식 수정 | 메시지 파싱 오류 |
| #408-410 | fix(chat_worker): BaseCheckpointSaver 상속 | Checkpointer 오류 |
| #411 | fix(chat-worker): Redis URL 수정 | DNS 해석 실패 |
| #412 | fix(chat-worker): Master pod DNS 사용 | READONLY 오류 |
| #413 | fix(chat_worker): max_completion_tokens 사용 | OpenAI API 오류 |
| #415 | feat(chat_worker): Channel Separation + Priority | Send API 병렬 충돌 |
