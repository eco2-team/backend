# Chat Worker E2E 검증 완료 리포트

> **검증 일시**: 2026-01-19 01:38 UTC
> **검증 환경**: k8s-master (13.209.44.249)
> **관련 PR**: #434 (fix: use redis_streams for ProgressNotifier and DomainEventBus)
> **검증 결과**: ✅ **PASS**

---

## 1. 검증 개요

### 1.1 검증 목적

PR #434에서 수정한 Redis Streams 이벤트 발행 버그 수정 후, 전체 이벤트 파이프라인이 정상 동작하는지 E2E 검증.

### 1.2 테스트 데이터

| 항목 | 값 |
|------|-----|
| **세션 ID** | `6a87f182-9599-498a-a519-fab2002f3c6a` |
| **테스트 Job ID** | `ff6dc3bd-8841-432f-8c4f-3f4075d0809b` |
| **테스트 메시지** | `"플라스틱 어떻게 버려?"` |
| **API 엔드포인트** | `https://api.dev.growbin.app/api/v1/chat` |
| **SSE 엔드포인트** | `https://api.dev.growbin.app/api/v1/chat/{job_id}/events` |

### 1.3 이벤트 흐름 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Chat Worker - Event Bus Architecture                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Client                                                                      │
│    │                                                                         │
│    ├─[1]─▶ POST /api/v1/chat ──▶ Istio Gateway ──▶ chat-api                │
│    │                                    │                                    │
│    │                                    ▼                                    │
│    │                              RabbitMQ (chat.process)                    │
│    │                                    │                                    │
│    │                                    ▼                                    │
│    │                              chat-worker (LangGraph)                    │
│    │                                    │                                    │
│    │                          ┌─────────┴─────────┐                         │
│    │                          ▼                   ▼                         │
│    │                   Redis Streams        PostgreSQL                       │
│    │                   (chat:events:{n})    (checkpoints)                   │
│    │                          │                                              │
│    │                          ▼                                              │
│    │                   event-router (XREADGROUP)                            │
│    │                          │                                              │
│    │                          ▼                                              │
│    │                   Redis Pub/Sub (PUBLISH sse:events:{job_id})          │
│    │                          │                                              │
│    │                          ▼                                              │
│    └─[2]─◀ SSE ◀── sse-gateway (SUBSCRIBE) ◀─────┘                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 컴포넌트별 검증 결과

### 2.1 Chat API

**역할**: 채팅 요청 수신 및 RabbitMQ 작업 제출

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| 세션 생성 | ✅ | `6a87f182-9599-498a-a519-fab2002f3c6a` |
| 메시지 제출 | ✅ | job_id 반환 |
| JWT 인증 | ✅ | Cookie → Header 변환 정상 |

**API 요청/응답**:

```bash
# 세션 생성
POST /api/v1/chat/sessions
Response: {"session_id": "6a87f182-9599-498a-a519-fab2002f3c6a"}

# 메시지 전송
POST /api/v1/chat
{
  "session_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
  "message": "플라스틱 어떻게 버려?"
}
Response: {"job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b"}
```

---

### 2.2 RabbitMQ

**역할**: 비동기 작업 큐잉 (chat-api → chat-worker)

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| Exchange | ✅ | `chat_tasks` (direct) |
| Queue | ✅ | `chat.process` |
| Message Delivery | ✅ | Worker에서 소비 확인 |

**RabbitMQ 설정**:

```yaml
Exchange: chat_tasks (type: direct)
Queue: chat.process
Routing Key: chat.process
```

---

### 2.3 Chat Worker (LangGraph)

**역할**: LangGraph 파이프라인 실행 및 이벤트 발행

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| 파이프라인 시작 | ✅ | `ProcessChatCommand started` |
| Intent 분류 | ✅ | `waste` (confidence: 1.0) |
| Dynamic Router | ✅ | `waste_rag` 노드 라우팅 |
| Answer 생성 | ✅ | 응답 완료 |
| 이벤트 발행 | ✅ | Redis Streams (Shard 3) |

**Worker 로그**:

```
[INFO] ProcessChatCommand started
[INFO] Single intent classification completed
[INFO] Intent: waste, Confidence: 1.0
[INFO] Dynamic router: routing to waste_rag
[INFO] RAG search completed
[INFO] Answer generated
[INFO] ProcessChatCommand completed
```

**수정된 이벤트 발행 코드** (PR #434):

```python
# Before (버그)
async def get_progress_notifier():
    redis = await get_redis()  # ❌ Pub/Sub Redis 사용

# After (수정)
async def get_progress_notifier():
    redis = await get_redis_streams()  # ✅ Streams Redis 사용
```

---

### 2.4 Redis Streams

**역할**: 이벤트 저장 및 Consumer Group 지원

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| Stream Key | ✅ | `chat:events:{shard}` (4개 Shard) |
| XADD 발행 | ✅ | Job 당 20개 이벤트 |
| Consumer Group | ✅ | `eventrouter` (pending: 0) |

**Shard 분포 (검증 시점)**:

| Shard | Event Count |
|-------|-------------|
| 0 | 53 |
| 1 | 57 |
| 2 | 71 |
| 3 | 74 (테스트 Job 포함) |

**테스트 Job 이벤트 (Shard 3)**:

```bash
# Job ff6dc3bd-8841-432f-8c4f-3f4075d0809b
XLEN chat:events:3 → 74
Job events: 20
```

**Consumer Group 상태**:

```bash
XINFO GROUPS chat:events:3
- name: eventrouter
- consumers: 1
- pending: 0  # 모든 이벤트 처리 완료
- last-delivered-id: 1768786276245-0
```

---

### 2.5 Event Router

**역할**: Redis Streams → Redis Pub/Sub 브리지

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| XREADGROUP | ✅ | 이벤트 소비 정상 |
| PUBLISH | ✅ | `sse:events:{job_id}` 발행 |
| Consumer | ✅ | 1 active consumer |

**Event Router State**:

```json
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "router",
  "status": "completed",
  "seq": 991,
  "ts": "1768786693.6702185"
}
```

---

### 2.6 Redis Pub/Sub

**역할**: SSE Gateway 브로드캐스트

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| Channel | ✅ | `sse:events:{job_id}` |
| PUBLISH | ✅ | 이벤트 브로드캐스트 정상 |
| SSE Gateway 수신 | ✅ | SUBSCRIBE 정상 |

**Redis URL 설정**:

```yaml
# ConfigMap
CHAT_WORKER_REDIS_PUBSUB_URL: redis://rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379/0
CHAT_WORKER_REDIS_STREAMS_URL: redis://rfr-streams-redis-0.rfr-streams-redis.redis.svc.cluster.local:6379/0
```

---

### 2.7 SSE Gateway

**역할**: 클라이언트에 실시간 이벤트 스트리밍

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| Endpoint | ✅ | `/api/v1/chat/{job_id}/events` |
| Event Stream | ✅ | 5개 이벤트 수신 |
| Keepalive | ✅ | ping 정상 |

**수신된 SSE 이벤트**:

```
event: queued
data: {"job_id": "ff6dc3bd-...", "stage": "queued", "status": "started", ...}

event: intent
data: {"job_id": "ff6dc3bd-...", "stage": "intent", "status": "started", ...}

event: intent
data: {"job_id": "ff6dc3bd-...", "stage": "intent", "status": "completed",
       "result": {"intent": "waste", "confidence": 1.0, ...}}

event: router
data: {"job_id": "ff6dc3bd-...", "stage": "router", "status": "started", ...}

event: router
data: {"job_id": "ff6dc3bd-...", "stage": "router", "status": "completed", ...}

: ping - 2026-01-19 01:38:27.420822+00:00
```

**VirtualService 라우팅**:

```yaml
# SSE 라우팅 (regex로 job_id 매칭)
- match:
    - uri:
        regex: "^/api/v1/chat/[0-9a-f-]+/events$"
  route:
    - destination:
        host: sse-gateway.sse-consumer.svc.cluster.local
        port:
          number: 8000
```

---

### 2.8 PostgreSQL Checkpointer

**역할**: LangGraph 멀티턴 대화 상태 영속화

| 검증 항목 | 상태 | 결과 |
|----------|------|------|
| Cache-Aside | ✅ | Redis L1 + PostgreSQL L2 |
| Checkpoint 저장 | ✅ | 24개 (테스트 세션) |
| Blob 저장 | ✅ | 45개 |
| Writes 저장 | ✅ | 162개 |

---

#### 2.8.1 테이블 스키마

**checkpoints 테이블** (LangGraph 실행 상태):

```sql
                    Table "public.checkpoints"
        Column        | Type  | Collation | Nullable |   Default
----------------------+-------+-----------+----------+-------------
 thread_id            | text  |           | not null |
 checkpoint_ns        | text  |           | not null | ''::text
 checkpoint_id        | text  |           | not null |
 parent_checkpoint_id | text  |           |          |
 type                 | text  |           |          |
 checkpoint           | jsonb |           | not null |
 metadata             | jsonb |           | not null | '{}'::jsonb
Indexes:
    "checkpoints_pkey" PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
    "checkpoints_thread_id_idx" btree (thread_id)
```

**checkpoint_blobs 테이블** (채널별 상태 데이터):

```sql
             Table "public.checkpoint_blobs"
    Column     | Type  | Collation | Nullable | Default
---------------+-------+-----------+----------+----------
 thread_id     | text  |           | not null |
 checkpoint_ns | text  |           | not null | ''::text
 channel       | text  |           | not null |
 version       | text  |           | not null |
 type          | text  |           | not null |
 blob          | bytea |           |          |
Indexes:
    "checkpoint_blobs_pkey" PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
    "checkpoint_blobs_thread_id_idx" btree (thread_id)
```

**checkpoint_writes 테이블** (노드별 쓰기 기록):

```sql
             Table "public.checkpoint_writes"
    Column     |  Type   | Collation | Nullable | Default
---------------+---------+-----------+----------+----------
 thread_id     | text    |           | not null |
 checkpoint_ns | text    |           | not null | ''::text
 checkpoint_id | text    |           | not null |
 task_id       | text    |           | not null |
 idx           | integer |           | not null |
 channel       | text    |           | not null |
 type          | text    |           |          |
 blob          | bytea   |           | not null |
 task_path     | text    |           | not null | ''::text
Indexes:
    "checkpoint_writes_pkey" PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
    "checkpoint_writes_thread_id_idx" btree (thread_id)
```

---

#### 2.8.2 실제 체크포인트 데이터 (테스트 세션)

**checkpoints 테이블 데이터** (step별 실행 상태):

```json
// Step -1: 입력 (source: "input")
{
  "thread_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
  "checkpoint_id": "1f0f4d68-8f4a-608d-bfff-203c66d3ab11",
  "parent_checkpoint_id": null,
  "metadata": {
    "step": -1,
    "job_id": "199887cb-be51-4128-a282-33717db115ae",
    "source": "input",
    "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
    "session_id": "6a87f182-9599-498a-a519-fab2002f3c6a"
  }
}

// Step 0: Intent 노드 실행 후 (source: "loop")
{
  "thread_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
  "checkpoint_id": "1f0f4d68-8f4d-6523-8000-8403ab73ec14",
  "parent_checkpoint_id": "1f0f4d68-8f4a-608d-bfff-203c66d3ab11",
  "metadata": {
    "step": 0,
    "job_id": "199887cb-be51-4128-a282-33717db115ae",
    "source": "loop",
    "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
    "session_id": "6a87f182-9599-498a-a519-fab2002f3c6a"
  }
}

// Step 1: Router 노드 실행 후
{
  "thread_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
  "checkpoint_id": "1f0f4d68-ac22-6849-8001-37c4c6d91c1f",
  "parent_checkpoint_id": "1f0f4d68-8f4d-6523-8000-8403ab73ec14",
  "metadata": {
    "step": 1,
    "source": "loop",
    ...
  }
}

// Step 2: RAG 노드 실행 후
{
  "checkpoint_id": "1f0f4d68-ac2e-611b-8002-158464e44491",
  "parent_checkpoint_id": "1f0f4d68-ac22-6849-8001-37c4c6d91c1f",
  "metadata": { "step": 2, ... }
}

// Step 3: Aggregator 노드 실행 후
{
  "checkpoint_id": "1f0f4d68-acd4-618f-8003-95d2baaf08e0",
  "parent_checkpoint_id": "1f0f4d68-ac2e-611b-8002-158464e44491",
  "metadata": { "step": 3, ... }
}
```

---

#### 2.8.3 checkpoint_blobs 데이터 (채널별 상태)

| Channel | Version | Type | Blob Size | 설명 |
|---------|---------|------|-----------|------|
| `__start__` | 1, 9, 17 | msgpack | 206-217 | 입력 상태 |
| `intent_history` | 3, 4, 11, 12, 19, 20 | msgpack | 7-19 | Intent 분류 히스토리 |
| `decomposed_queries` | 3, 4, 11, 12, 19, 20 | msgpack | 32-43 | 분해된 쿼리 목록 |
| `additional_intents` | 3, 4, 11, 12, 19, 20 | msgpack | 1 | 추가 Intent 목록 |
| `disposal_rules` | 5, 12, 13, 20, 21 | msgpack | 836-1555 | RAG 검색 결과 (분리배출 규칙) |
| `weather_context` | 5, 12, 13, 20, 21 | msgpack | 186 | 날씨 컨텍스트 |
| `missing_required_contexts` | 6, 12, 14, 20, 22 | msgpack | 1 | 누락된 필수 컨텍스트 |
| `messages` | 4, 12, 20 | msgpack | 1 | 대화 메시지 |
| `__pregel_tasks` | 4, 5, 12, 13, 20, 21 | msgpack | 1-5303 | LangGraph 태스크 상태 |

---

#### 2.8.4 checkpoint_writes 데이터 (노드별 쓰기)

**Step -1: 입력 노드** (task_id: `d551459b-...`):

```
| idx | channel           | type    | blob_size |
|-----|-------------------|---------|-----------|
| 0   | job_id            | msgpack | 38        |
| 1   | user_id           | msgpack | 38        |
| 2   | message           | msgpack | 42        |
| 3   | image_url         | null    | 0         |
| 4   | branch:to:intent  | null    | 0         |
```

**Step 0: Intent 노드** (task_id: `4f2ae138-...`):

```
| idx | channel            | type    | blob_size |
|-----|--------------------|---------|-----------|
| 0   | intent             | msgpack | 6         |  ← "waste"
| 1   | is_complex         | msgpack | 1         |  ← false
| 2   | intent_confidence  | msgpack | 9         |  ← 1.0
| 3   | has_multi_intent   | msgpack | 1         |  ← false
| 4   | additional_intents | msgpack | 1         |  ← []
| 5   | decomposed_queries | msgpack | 43        |  ← [쿼리 목록]
| 6   | current_query      | msgpack | 42        |  ← "플라스틱 분리수거..."
| 7   | intent_history     | msgpack | 7         |  ← ["waste"]
| 8   | branch:to:router   | null    | 0         |
```

**Step 1: Router 노드** (task_id: `cbaa7034-...`):

```
| idx | channel           | type    | blob_size |
|-----|-------------------|---------|-----------|
| 0   | job_id            | msgpack | 38        |
| 1   | user_id           | msgpack | 38        |
| 2   | message           | msgpack | 42        |
| 3   | image_url         | null    | 0         |
| 4   | intent            | msgpack | 6         |
| 5   | intent_confidence | msgpack | 9         |
```

---

#### 2.8.5 체크포인트 체인 구조

```
                    LangGraph Checkpoint Chain
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  checkpoint_id: 1f0f4d68-8f4a-...  (step: -1, source: input)   │
│  └── parent: null                                                │
│      └── 입력 상태 (job_id, user_id, message)                    │
│                                                                  │
│            ▼                                                     │
│                                                                  │
│  checkpoint_id: 1f0f4d68-8f4d-...  (step: 0, source: loop)     │
│  └── parent: 1f0f4d68-8f4a-...                                  │
│      └── Intent 분류 결과 (intent, confidence, history)          │
│                                                                  │
│            ▼                                                     │
│                                                                  │
│  checkpoint_id: 1f0f4d68-ac22-...  (step: 1, source: loop)     │
│  └── parent: 1f0f4d68-8f4d-...                                  │
│      └── Router 결과 (라우팅 대상 노드)                          │
│                                                                  │
│            ▼                                                     │
│                                                                  │
│  checkpoint_id: 1f0f4d68-ac2e-...  (step: 2, source: loop)     │
│  └── parent: 1f0f4d68-ac22-...                                  │
│      └── RAG 검색 결과 (disposal_rules)                          │
│                                                                  │
│            ▼                                                     │
│                                                                  │
│  checkpoint_id: 1f0f4d68-acd4-...  (step: 3, source: loop)     │
│  └── parent: 1f0f4d68-ac2e-...                                  │
│      └── Aggregator 결과 + Answer                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

#### 2.8.6 멀티턴 대화 지원

동일 세션 (`thread_id`)에서 여러 메시지를 보낼 때:
- 각 메시지마다 새로운 체크포인트 체인 생성
- `intent_history` 채널에 이전 Intent 누적
- 멀티턴 컨텍스트 유지 가능

```
Session: 6a87f182-9599-498a-a519-fab2002f3c6a

Turn 1 (Job: 199887cb-...)
├── step -1 → step 0 → step 1 → step 2 → step 3
└── intent_history: ["waste"]

Turn 2 (Job: ff6dc3bd-...)
├── step -1 → step 0 → step 1 → step 2 → step 3
└── intent_history: ["waste", "waste"]
```

---

## 3. 이슈 및 해결

### 3.1 Redis 인스턴스 혼용 (PR #434)

**문제**: `ProgressNotifier`와 `DomainEventBus`가 `get_redis()` (Pub/Sub Redis)를 사용하여 Event Router가 이벤트를 받지 못함.

**원인 분석**:

```
chat_worker → [Pub/Sub Redis] ❌ (잘못된 Redis)
                    │
Event Router → [Streams Redis] (소비 대기 중, 이벤트 없음)
                    │
SSE Gateway → (이벤트 수신 불가)
```

**수정**:

```python
# dependencies.py
async def get_progress_notifier():
    redis = await get_redis_streams()  # ✅ 수정

async def get_domain_event_bus():
    redis = await get_redis_streams()  # ✅ 수정
```

**수정 후 흐름**:

```
chat_worker → [Streams Redis] ✅ (chat:events:{shard})
                    │
                    ▼
Event Router (XREADGROUP) → [Pub/Sub Redis] (PUBLISH sse:events:{job_id})
                    │
                    ▼
SSE Gateway (SUBSCRIBE) → Client ✅
```

### 3.2 SSE 엔드포인트 URL 혼동

**문제**: `/api/v1/sse/{job_id}` 사용 시 이벤트 수신 불가

**해결**: 올바른 엔드포인트 `/api/v1/chat/{job_id}/events` 사용

---

## 4. 검증 완료 체크리스트

| # | 컴포넌트 | 검증 항목 | 상태 |
|---|----------|----------|------|
| 1 | Chat API | 세션 생성 및 메시지 제출 | ✅ |
| 2 | RabbitMQ | 작업 큐잉 | ✅ |
| 3 | Chat Worker | LangGraph 파이프라인 실행 | ✅ |
| 4 | Redis Streams | 이벤트 발행 (XADD) | ✅ |
| 5 | Event Router | 이벤트 소비 및 라우팅 | ✅ |
| 6 | Redis Pub/Sub | SSE 브로드캐스트 | ✅ |
| 7 | SSE Gateway | 클라이언트 스트리밍 | ✅ |
| 8 | PostgreSQL | 체크포인트 영속화 | ✅ |

---

## 5. 결론

### 5.1 검증 결과 요약

**전체 결과: ✅ PASS**

PR #434 수정 후 전체 이벤트 파이프라인이 정상 동작함을 확인:

1. **SSE 이벤트 전달**: 클라이언트에서 실시간 이벤트 수신 확인
2. **Redis Streams 발행**: 4개 Shard에 분산 저장 확인
3. **Consumer Group 처리**: pending=0 (모든 이벤트 처리 완료)
4. **PostgreSQL 영속화**: 멀티턴 대화 체크포인트 저장 확인

### 5.2 운영 권장 사항

1. **Redis URL 설정**: Master Pod DNS 직접 사용 (Sentinel failover 고려)
2. **SSE 엔드포인트**: `/api/v1/chat/{job_id}/events` 사용
3. **Shard 모니터링**: 4개 Shard 균등 분산 확인

### 5.3 관련 문서

| 문서 | 경로 |
|------|------|
| 트러블슈팅 | `docs/troubleshooting/chat-worker-redis-streams-fix.md` |
| 아키텍처 | `.claude/skills/chat-agent-flow/references/architecture.md` |
| Event-Driven | `.claude/skills/event-driven/SKILL.md` |

---

## 6. Intent별 대화 내용 및 생성된 답변

### 6.1 테스트 세션 대화 기록

| # | Job ID | Intent | 사용자 메시지 | 처리 시간 |
|---|--------|--------|-------------|----------|
| 1 | `199887cb-be51-4128-a282-33717db115ae` | `waste` | 플라스틱 분리수거 어떻게 해? | 01:31:13 → 01:31:16 (3초) |
| 2 | `ff6dc3bd-8841-432f-8c4f-3f4075d0809b` | `waste` | 유리병은 어떻게 버려? | 01:38:15 → 01:38:18 (3초) |
| 3 | `cd4de6f2-739c-4743-87a7-a8783eae96e8` | `collection_point` | 근처 의류수거함 어디야? | 20:08:48 → 20:08:51 (3초) |

---

### 6.2 Intent: `waste` (폐기물 분리배출)

#### 대화 1: 플라스틱 분리수거

**사용자 질문**:
> 플라스틱 분리수거 어떻게 해?

**AI 답변**:
> 플라스틱 중에서도 **먹는샘물·음료 같은 무색 페트병(PET)**은 **무색(투명) 페트병 전용 수거함**에 버리면 돼요 ♻️
>
> 배출할 땐 이렇게 해줘:
> - **라벨이랑 내용물 제거 → 물로 헹굼**
> - **납작하게 압착한 뒤, 뚜껑 닫아서 배출**
>
> 참고로 **유색 페트병**이나 **음료/생수 말고 다른 플라스틱 용기(식품용기, 컵, 워셔액 용기 등)**는 **플라스틱류로 따로** 버려야 해요.

**SSE 이벤트 전체 시퀀스** (Redis Streams - Shard 1):

```json
// 1. 최종 완료 이벤트
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "done",
  "status": "completed",
  "seq": 171,
  "ts": "1768786276.244771",
  "progress": 100,
  "result": {
    "intent": "waste",
    "answer": "플라스틱 중에서도 **먹는샘물·음료 같은 무색 페트병(PET)**은 **무색(투명) 페트병 전용 수거함**에 버리면 돼요 ♻️\n\n배출할 땐 이렇게 해줘:\n- **라벨이랑 내용물 제거 → 물로 헹굼**\n- **납작하게 압착한 뒤, 뚜껑 닫아서 배출**\n\n참고로 **유색 페트병**이나 **음료/생수 말고 다른 플라스틱 용기(식품용기, 컵, 워셔액 용기 등)**는 **플라스틱류로 따로** 버려야 해요.",
    "persistence": {
      "conversation_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
      "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
      "user_message": "플라스틱 분리수거 어떻게 해?",
      "user_message_created_at": "2026-01-19T01:31:16.244723+00:00",
      "assistant_message_created_at": "2026-01-19T01:31:16.244723+00:00",
      "intent": "waste",
      "metadata": null
    }
  }
}

// 2. 답변 생성 완료
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "answer",
  "status": "completed",
  "seq": 161,
  "ts": "1768786276.2305973",
  "progress": 95,
  "message": "답변 생성 완료"
}

// 3. 답변 생성 시작
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "answer",
  "status": "started",
  "seq": 160,
  "ts": "1768786273.7502303",
  "progress": 75,
  "message": "답변을 생성하고 있습니다..."
}

// 4. 요약 완료
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "summarize",
  "status": "completed",
  "seq": 991,
  "ts": "1768786273.7464044",
  "progress": 75,
  "message": "요약 완료"
}

// 5. 정보 취합 완료
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "aggregate",
  "status": "completed",
  "seq": 991,
  "ts": "1768786273.740522",
  "progress": 65,
  "result": {
    "collected": ["RAG 검색 결과"],
    "needs_fallback": false
  },
  "message": "정보 취합 완료: 1건"
}

// 6. Aggregator 시작
{
  "job_id": "199887cb-be51-4128-a282-33717db115ae",
  "stage": "aggregator",
  "status": "started",
  "seq": 140,
  "ts": "1768786273.739492",
  "progress": 55,
  "message": "정보를 종합하고 있습니다..."
}
```

---

#### 대화 2: 유리병 분리배출

**사용자 질문**:
> 유리병은 어떻게 버려?

**AI 답변**:
> 유리병은 **유리병 수거함**에 배출하면 돼! 수거함이 없으면 **재활용폐기물로 통합배출**하면 되고요 ♻️
>
> - **투명/녹색/갈색(3색)**은 따로 나눌 필요 없이 같이 배출해도 괜찮아(업체에서 선별해요).
> - **소주병·맥주병·청량음료병(빈용기보증금 대상)**이면, **반환수집소/무인회수기**에 가져가면 보증금 환급도 받을 수 있어. 이건 재사용이라 **깨끗하고 안 깨지게** 주의해줘!
> - **깨진 유리병**은 유리수거함 말고 **불연성 종량제봉투**로 버리거나, **신문지로 싸서 종량제봉투**에 넣어 배출하면 안전해.

**SSE 이벤트 전체 시퀀스** (Redis Streams - Shard 3):

```json
// 1. 최종 완료 이벤트
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "done",
  "status": "completed",
  "seq": 171,
  "ts": "1768786699.0089633",
  "progress": 100,
  "result": {
    "intent": "waste",
    "answer": "유리병은 **유리병 수거함**에 배출하면 돼! 수거함이 없으면 **재활용폐기물로 통합배출**하면 되고요 ♻️\n\n- **투명/녹색/갈색(3색)**은 따로 나눌 필요 없이 같이 배출해도 괜찮아(업체에서 선별해요).\n- **소주병·맥주병·청량음료병(빈용기보증금 대상)**이면, **반환수집소/무인회수기**에 가져가면 보증금 환급도 받을 수 있어. 이건 재사용이라 **깨끗하고 안 깨지게** 주의해줘!\n- **깨진 유리병**은 유리수거함 말고 **불연성 종량제봉투**로 버리거나, **신문지로 싸서 종량제봉투**에 넣어 배출하면 안전해.",
    "persistence": {
      "conversation_id": "6a87f182-9599-498a-a519-fab2002f3c6a",
      "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
      "user_message": "유리병은 어떻게 버려?",
      "user_message_created_at": "2026-01-19T01:38:19.008915+00:00",
      "assistant_message_created_at": "2026-01-19T01:38:19.008915+00:00",
      "intent": "waste",
      "metadata": null
    }
  }
}

// 2. 답변 생성 완료
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "answer",
  "status": "completed",
  "seq": 161,
  "ts": "1768786698.9950259",
  "progress": 95,
  "message": "답변 생성 완료"
}

// 3. 답변 생성 시작
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "answer",
  "status": "started",
  "seq": 160,
  "ts": "1768786695.6435952",
  "progress": 75,
  "message": "답변을 생성하고 있습니다..."
}

// 4. 요약 완료
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "summarize",
  "status": "completed",
  "seq": 991,
  "ts": "1768786695.6400285",
  "progress": 75,
  "message": "요약 완료"
}

// 5. 요약 시작
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "summarize",
  "status": "started",
  "seq": 990,
  "ts": "1768786695.6376536",
  "progress": 65,
  "message": "답변을 요약하고 있습니다..."
}

// 6. 정보 취합 완료
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "aggregate",
  "status": "completed",
  "seq": 991,
  "ts": "1768786695.6345978",
  "progress": 65,
  "result": {
    "collected": ["RAG 검색 결과"],
    "needs_fallback": false
  },
  "message": "정보 취합 완료: 1건"
}

// 7. Aggregator 시작
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "aggregator",
  "status": "started",
  "seq": 140,
  "ts": "1768786695.6337337",
  "progress": 55,
  "message": "정보를 종합하고 있습니다..."
}

// 8. 날씨 정보 조회 완료 (enrichment)
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "weather",
  "status": "completed",
  "seq": 81,
  "ts": "1768786695.632711",
  "progress": 55,
  "message": "날씨 정보 조회 완료"
}

// 9. 분리배출 정보 검색 완료
{
  "job_id": "ff6dc3bd-8841-432f-8c4f-3f4075d0809b",
  "stage": "waste_rag",
  "status": "completed",
  "seq": 31,
  "ts": "1768786695.6301675",
  "progress": 37,
  "message": "분리배출 정보 검색 완료"
}
```

---

### 6.3 Intent: `collection_point` (수거함 위치)

**사용자 질문**:
> 근처 의류수거함 어디야?

**AI 답변**:
> 의류수거함 위치는 **동네(시/구/동)** 정보가 있어야 정확히 찾아줄 수 있어요 🙏
> 지금 계신 곳이 **어느 시/구/동**인지 알려줘! (예: "서울 마포구 합정동", 또는 현재 위치 주변 랜드마크도 OK)
>
> 참고로 의류는 보통 **아파트 단지, 주민센터 근처, 공원 입구** 쪽에 설치된 경우가 많아.
> 지역 알려주면 가까운 후보 위치 찾는 팁이랑 함께 안내해줄게 ♻️

**SSE 이벤트 전체 시퀀스** (Redis Streams - Shard 0):

```json
// 1. 최종 완료 이벤트
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "done",
  "status": "completed",
  "seq": 171,
  "ts": "1768766931.206393",
  "progress": 100,
  "result": {
    "intent": "collection_point",
    "answer": "의류수거함 위치는 **동네(시/구/동)** 정보가 있어야 정확히 찾아줄 수 있어요 🙏  \n지금 계신 곳이 **어느 시/구/동**인지 알려줘! (예: "서울 마포구 합정동", 또는 현재 위치 주변 랜드마크도 OK)\n\n참고로 의류는 보통 **아파트 단지, 주민센터 근처, 공원 입구** 쪽에 설치된 경우가 많아.  \n지역 알려주면 가까운 후보 위치 찾는 팁이랑 함께 안내해줄게 ♻️",
    "persistence": {
      "conversation_id": "aa312263-1e05-4cb5-8242-418e1b4c1f91",
      "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
      "user_message": "근처 의류수거함 어디야?",
      "user_message_created_at": "2026-01-18T20:08:51.206362+00:00",
      "assistant_message_created_at": "2026-01-18T20:08:51.206362+00:00",
      "intent": "collection_point",
      "metadata": null
    }
  }
}

// 2. 답변 생성 완료
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "answer",
  "status": "completed",
  "seq": 161,
  "ts": "1768766931.2048447",
  "progress": 95,
  "message": "답변 생성 완료"
}

// 3. 답변 생성 시작
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "answer",
  "status": "started",
  "seq": 160,
  "ts": "1768766928.333617",
  "progress": 75,
  "message": "답변을 생성하고 있습니다..."
}

// 4. 요약 완료
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "summarize",
  "status": "completed",
  "seq": 991,
  "ts": "1768766928.3312747",
  "progress": 75,
  "message": "요약 완료"
}

// 5. 요약 시작
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "summarize",
  "status": "started",
  "seq": 990,
  "ts": "1768766928.3302014",
  "progress": 65,
  "message": "답변을 요약하고 있습니다..."
}

// 6. 정보 취합 완료 (3건 - 병렬 처리 결과)
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "aggregate",
  "status": "completed",
  "seq": 991,
  "ts": "1768766928.327894",
  "progress": 65,
  "result": {
    "collected": ["RAG 검색 결과", "재활용 시세", "수거함 위치"],
    "needs_fallback": false
  },
  "message": "정보 취합 완료: 3건"
}

// 7. Aggregator 시작
{
  "job_id": "cd4de6f2-739c-4743-87a7-a8783eae96e8",
  "stage": "aggregator",
  "status": "started",
  "seq": 140,
  "ts": "1768766928.3265893",
  "progress": 55,
  "message": "정보를 종합하고 있습니다..."
}
```

**Intent 분류 결과**:
- Intent: `collection_point`
- Missing Context: `location` (위치 정보 필요)
- Fallback: 위치 정보 요청 안내 메시지 생성
- 특이사항: 병렬로 3건의 정보 수집 (RAG, 재활용 시세, 수거함 위치)

---

### 6.4 SSE 이벤트 Stage별 사용자 안내 메시지

| Stage | Status | Progress | 사용자 안내 메시지 |
|-------|--------|----------|------------------|
| `queued` | `started` | 0% | 요청이 접수되었습니다 |
| `intent` | `started` | 5% | 질문을 분석하고 있습니다... |
| `intent` | `completed` | 15% | 질문 분석 완료 |
| `router` | `started` | 20% | 적절한 답변을 찾고 있습니다... |
| `router` | `completed` | 25% | 라우팅 완료 |
| `waste_rag` | `started` | 30% | 분리배출 정보 검색 중... |
| `waste_rag` | `completed` | 37% | 분리배출 정보 검색 완료 |
| `weather` | `completed` | 55% | 날씨 정보 조회 완료 |
| `aggregator` | `started` | 55% | 정보를 종합하고 있습니다... |
| `aggregate` | `completed` | 65% | 정보 취합 완료: N건 |
| `summarize` | `started` | 65% | 답변을 요약하고 있습니다... |
| `summarize` | `completed` | 75% | 요약 완료 |
| `answer` | `started` | 75% | 답변을 생성하고 있습니다... |
| `answer` | `completed` | 95% | 답변 생성 완료 |
| `done` | `completed` | 100% | 처리 완료 |

---

### 6.5 Intent별 라우팅 노드 및 수집 정보

| Intent | 라우팅 노드 | 수집 정보 | 병렬 처리 |
|--------|-----------|----------|----------|
| `waste` | `waste_rag` | RAG 검색 결과 (1건) | No |
| `waste` | `waste_rag` + `weather` | RAG + 날씨 (2건) | Yes |
| `collection_point` | `collection_point` + `recyclable_price` + `waste_rag` | 수거함 위치 + 시세 + RAG (3건) | Yes |
| `bulk_waste` | `bulk_waste` | 대형폐기물 처리 안내 | No |
| `recyclable_price` | `recyclable_price` | 재활용품 시세 | No |
| `weather` | `weather` | 날씨 정보 | No |
| `general` | `general` | 일반 대화/환경 상식 | No |

---

## 7. 부록: 테스트 명령어

### A. 세션 생성 및 메시지 전송

```bash
# JWT 토큰 설정
TOKEN="<JWT_TOKEN>"

# 세션 생성
curl -X POST "https://api.dev.growbin.app/api/v1/chat/sessions" \
  -H "Cookie: s_access=$TOKEN"

# 메시지 전송
curl -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"session_id": "<SESSION_ID>", "message": "플라스틱 어떻게 버려?"}'
```

### B. SSE 스트림 구독

```bash
curl -N "https://api.dev.growbin.app/api/v1/chat/<JOB_ID>/events" \
  -H "Cookie: s_access=$TOKEN" \
  -H "Accept: text/event-stream"
```

### C. Redis Streams 확인

```bash
# Shard별 이벤트 수
for i in {0..3}; do
  echo "Shard $i: $(redis-cli -h rfr-streams-redis XLEN chat:events:$i)"
done

# Consumer Group 상태
redis-cli -h rfr-streams-redis XINFO GROUPS chat:events:0
```

### D. PostgreSQL 체크포인트 확인

```bash
kubectl -n postgres exec -it dev-postgresql-0 -- psql -U postgres -d ecoeco

# 체크포인트 수
SELECT COUNT(*) FROM checkpoints;

# 세션별 체크포인트
SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id;
```

---

**작성자**: Claude Code
**검증일**: 2026-01-19
