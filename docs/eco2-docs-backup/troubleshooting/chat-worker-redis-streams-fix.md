# Chat Worker Redis Streams 버그 수정 및 E2E 검증

> 날짜: 2026-01-19
> PR: #434
> 관련 이슈: SSE 이벤트가 클라이언트에 전달되지 않음

---

## 문제 요약

Chat Worker의 `ProgressNotifier`와 `DomainEventBus`가 잘못된 Redis 인스턴스에 이벤트를 발행하여 SSE 스트림이 작동하지 않음.

### 증상

- 채팅 메시지 전송 후 SSE 스트림이 비어 있음
- Worker 로그에서 파이프라인은 정상 완료
- Redis Streams 키가 존재하지 않음 (`ERR no such key`)

---

## 원인 분석

### Redis 인스턴스 구조

| 인스턴스 | URL | 용도 |
|----------|-----|------|
| **Pub/Sub Redis** | `rfr-pubsub-redis` | 캐시, Pub/Sub, 일반 KV |
| **Streams Redis** | `rfr-streams-redis` | Redis Streams (Event Router 소비) |

### 버그 위치

`apps/chat_worker/setup/dependencies.py:154, 167`

```python
# Before (버그)
async def get_progress_notifier() -> ProgressNotifierPort:
    redis = await get_redis()  # ❌ Pub/Sub Redis 사용
    _progress_notifier = RedisProgressNotifier(redis=redis)

async def get_domain_event_bus() -> RedisStreamDomainEventBus:
    redis = await get_redis()  # ❌ Pub/Sub Redis 사용
    _domain_event_bus = RedisStreamDomainEventBus(redis=redis)
```

### 이벤트 흐름 단절

```
chat_worker → [Pub/Sub Redis] ❌ (잘못된 Redis)
                    │
Event Router → [Streams Redis] (소비 대기 중, 이벤트 없음)
                    │
SSE Gateway → (이벤트 수신 불가)
```

---

## 수정 내용

### PR #434: fix(chat_worker): use redis_streams for ProgressNotifier and DomainEventBus

```python
# After (수정)
async def get_progress_notifier() -> ProgressNotifierPort:
    redis = await get_redis_streams()  # ✅ Streams Redis 사용
    _progress_notifier = RedisProgressNotifier(redis=redis)

async def get_domain_event_bus() -> RedisStreamDomainEventBus:
    redis = await get_redis_streams()  # ✅ Streams Redis 사용
    _domain_event_bus = RedisStreamDomainEventBus(redis=redis)
```

### 수정된 이벤트 흐름

```
chat_worker → [Streams Redis] ✅ (chat:events:{shard})
                    │
                    ▼
Event Router (XREADGROUP) → [Pub/Sub Redis] (PUBLISH sse:events:{job_id})
                    │
                    ▼
SSE Gateway (SUBSCRIBE) → Client ✅
```

---

## E2E 테스트 결과

### 테스트 환경

| 항목 | 값 |
|------|-----|
| **클러스터** | k8s-master (13.209.44.249) |
| **테스트 시각** | 2026-01-19 01:38 UTC |
| **테스트 세션** | `6a87f182-9599-498a-a519-fab2002f3c6a` |
| **테스트 Job ID** | `ff6dc3bd-8841-432f-8c4f-3f4075d0809b` |

### SSE 이벤트 수신 확인

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

### Redis Streams 검증

```bash
# Shard 분포 확인 (모든 shard에 이벤트 존재)
Shard 0: 53 events
Shard 1: 57 events
Shard 2: 71 events
Shard 3: 74 events

# 테스트 Job의 이벤트 (Shard 3)
Job ff6dc3bd-...: 20 events

# Consumer Group 상태
eventrouter group:
  - consumers: 1
  - pending: 0 (모두 처리됨)
  - last-delivered-id: 1768786276245-0
```

### Event Router State 확인

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

## PostgreSQL 체크포인트 검증

### 테이블 현황

| 테이블 | Row Count |
|--------|-----------|
| `checkpoints` | 40 |
| `checkpoint_blobs` | 71 |
| `checkpoint_writes` | 162 |

### 세션별 체크포인트 수

| Session (thread_id) | Checkpoint Count |
|---------------------|------------------|
| `6a87f182-...-fab2002f3c6a` (E2E 테스트) | **24** |
| `0530395a-...-467e2f9706b4` | 8 |
| `a5c0234a-...-2a9bd028eb74` | 8 |

### Blob 채널 분포 (E2E 세션)

| Channel | Count |
|---------|-------|
| `intent_history` | 6 |
| `decomposed_queries` | 6 |
| `__pregel_tasks` | 6 |
| `additional_intents` | 6 |
| `weather_context` | 5 |
| `missing_required_contexts` | 5 |
| `disposal_rules` | 5 |
| `__start__` | 3 |
| `messages` | 3 |

### checkpoint_writes 채널 분포

| Channel | Write Count |
|---------|-------------|
| `__pregel_tasks` | 6 |
| `job_id` | 6 |
| `intent_history` | 6 |
| `intent` | 6 |
| `intent_confidence` | 6 |
| `additional_intents` | 6 |
| `message` | 6 |
| `answer` | 5 |
| ... | ... |

---

## Worker 로그 분석

### 정상 시작 로그

```
[INFO] Redis connected: redis://rfr-pubsub-redis-0.rfr-pubsub-redis.redis.svc.cluster.local:6379/0
[INFO] RedisCacheAdapter created
[INFO] Redis Streams connected: redis://rfr-streams-redis-0.rfr-streams-redis.redis.svc.cluster.local:6379/0
[INFO] RedisProgressNotifier initialized
[INFO] CachedPostgresSaver created (PostgreSQL + Redis cache)
```

### 파이프라인 실행 로그

```
[INFO] ProcessChatCommand started
[INFO] Single intent classification completed
[INFO] Intent node completed
[INFO] Dynamic router completed
[INFO] RAG search completed
[INFO] Answer generated
[INFO] ProcessChatCommand completed
```

---

## 관련 PR 히스토리

| PR | 제목 | 상태 |
|----|------|------|
| #430 | fix(secrets): remove incorrect CHAT_WORKER_REDIS_URL | Merged |
| #431 | fix(workloads): add CHAT_WORKER_REDIS_URL to configmap | Merged |
| #432 | fix(workloads): use Redis master pod DNS | Merged |
| #433 | fix(chat_worker): add task_path column to checkpoint_writes | Merged |
| #434 | **fix(chat_worker): use redis_streams for ProgressNotifier** | Merged |

---

## 결론

### 해결된 문제

1. **SSE 이벤트 미전달**: `get_redis()` → `get_redis_streams()` 수정으로 해결
2. **PostgreSQL 체크포인트**: 정상 저장 확인 (24개 체크포인트)
3. **멀티턴 대화 지원**: LangGraph 상태 영속화 검증 완료

### 검증된 컴포넌트

| 컴포넌트 | 상태 |
|----------|------|
| Chat Worker | ✅ 정상 |
| Redis Streams 발행 | ✅ 정상 |
| Event Router 소비 | ✅ 정상 |
| Redis Pub/Sub 브로드캐스트 | ✅ 정상 |
| SSE Gateway | ✅ 정상 |
| PostgreSQL 체크포인터 | ✅ 정상 |

### 주의사항

- SSE 엔드포인트: `/api/v1/chat/{job_id}/events` (not `/api/v1/sse/{job_id}`)
- Redis URL 설정 시 Master Pod DNS 사용 권장 (Sentinel failover 고려)
