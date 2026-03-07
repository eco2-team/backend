# Event Router Pub/Sub 발행 지연 트러블슈팅

> **작성일**: 2026-01-19
> **환경**: dev (ap-northeast-2)
> **상태**: 🟢 해결됨 (PR #439)
> **목적**: Event Router가 Redis Streams 이벤트를 Pub/Sub으로 발행하지 않는 문제 분석

---

## 1. 개요

### 1.1. 배경

Multi-Intent 테스트 중 SSE 스트림이 중간에 멈추는 현상 발생. Worker는 정상 완료되고 Redis Streams에 이벤트가 기록되지만, SSE 클라이언트에게 전달되지 않음.

### 1.2. 영향 범위

- Event Router: `event-router` namespace
- SSE Gateway: `sse-consumer` namespace
- 모든 Chat/Scan SSE 스트리밍

---

## 2. 관측된 문제

### 2.1. 증상

```bash
# SSE 스트림 연결
curl -sN "https://api.dev.growbin.app/api/v1/chat/$JOB_ID/events" \
  -H "Cookie: s_access=$TOKEN"
```

**예상 결과:**
```
event: queued
event: intent
event: router
event: rag
event: weather
event: aggregate
event: answer
event: done
```

**실제 결과:**
```
event: queued
event: intent
event: router    ← 여기서 멈춤
event: rag
: keepalive
: keepalive      ← 타임아웃까지 keepalive만 반복
```

→ **후반 이벤트(aggregate, answer, done)가 SSE로 전달되지 않음**

### 2.2. Worker 로그 (정상)

```
[04:02:39] Multi-intent classification completed
[04:02:39] Built multi-intent prompt for intents=['waste', 'location']
[04:02:46] Answer generated
[04:02:46] ProcessChatCommand completed
```

### 2.3. Redis Streams (정상)

```bash
redis-cli XREVRANGE chat:events:3 + - COUNT 5
```

```
1768796161991-0
  job_id: 156f6b9c-319a-4974-a590-c571d26170a1
  stage: done
  status: completed
  seq: 171
  progress: 100
  result: {"intent": "waste", "answer": "1) 플라스틱 중에서도..."}
```

→ **Redis Streams에는 `done` 이벤트까지 정상 기록됨**

### 2.4. Event Router 로그 (이상)

```bash
kubectl logs -n event-router deploy/event-router --tail=100
```

```
INFO:     127.0.0.6:42841 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.6:57485 - "GET /ready HTTP/1.1" 200 OK
INFO:     127.0.0.6:53383 - "GET /ready HTTP/1.1" 200 OK
# ... 오직 health check만 반복
```

→ **이벤트 처리/발행 로그가 전혀 없음**

### 2.5. SSE Gateway 로그

```bash
kubectl logs -n sse-consumer deploy/sse-gateway --tail=50
```

```
[04:09:12] broadcast_subscribe_started
[04:10:12] broadcast_subscribe_ended    ← 60초 후 타임아웃
```

→ **Pub/Sub 구독 시작했으나 이벤트 수신 없이 타임아웃**

---

## 3. 데이터 흐름 분석

### 3.1. 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Event Bus 데이터 흐름                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Chat Worker                                                               │
│   └─ XADD chat:events:{shard}  ✅ 정상                                      │
│                                                                             │
│   Redis Streams (rfr-streams-redis)                                         │
│   └─ chat:events:0 ~ chat:events:3  ✅ 이벤트 존재                          │
│                                                                             │
│   Event Router                                                              │
│   └─ XREADGROUP eventrouter  ✅ Consumer Group 활성                         │
│   └─ Lua Script 실행  ❓ 실행 여부 불명                                     │
│   └─ PUBLISH sse:events:{job_id}  ❌ 발행 로그 없음                         │
│                                                                             │
│   Redis Pub/Sub (rfr-pubsub-redis)                                          │
│   └─ sse:events:{job_id}  ❌ 채널 비활성                                    │
│                                                                             │
│   SSE Gateway                                                               │
│   └─ SUBSCRIBE sse:events:{job_id}  ✅ 구독 시작                            │
│   └─ 이벤트 수신  ❌ 타임아웃                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2. Consumer Group 상태

```bash
redis-cli XINFO GROUPS chat:events:1
```

```
name: eventrouter
consumers: 2
pending: 0
last-delivered-id: 1768795761609-0
```

**분석:**
- `pending: 0` → 모든 메시지가 ACK됨
- `last-delivered-id`가 최신 → 메시지를 읽긴 함
- **하지만 Pub/Sub 발행이 안 됨**

### 3.3. Pub/Sub 채널 상태

```bash
redis-cli -h rfr-pubsub-redis PUBSUB CHANNELS
```

```
(empty array)
```

→ **활성 구독 채널 없음**

---

## 4. 원인 가설

### 4.1. 가설 1: Event Router Consumer 블로킹

XREADGROUP이 블로킹 모드로 대기 중이거나, 이벤트 처리 루프가 멈춤.

**검증 방법:**
```bash
kubectl exec -n event-router deploy/event-router -- ps aux
kubectl exec -n event-router deploy/event-router -- cat /proc/1/stack
```

### 4.2. 가설 2: Lua Script 실행 실패

Event Router의 `UPDATE_STATE_SCRIPT` Lua 스크립트가 에러 반환.

**검증 방법:**
```bash
# Event Router 로그 레벨 DEBUG로 변경
kubectl set env deploy/event-router -n event-router LOG_LEVEL=DEBUG
kubectl rollout restart deploy/event-router -n event-router
```

### 4.3. 가설 3: Pub/Sub Redis 연결 문제

Event Router가 Streams Redis에는 연결되었지만, Pub/Sub Redis에는 연결 실패.

**검증 방법:**
```bash
# Event Router 환경변수 확인
kubectl exec -n event-router deploy/event-router -- env | grep REDIS
```

### 4.4. 가설 4: 멱등성 키 충돌

`router:published:{job_id}:{seq}` 키가 이미 존재하여 발행 스킵.

**검증 방법:**
```bash
redis-cli KEYS "router:published:156f6b9c*"
```

---

## 5. 임시 완화 조치

### 5.1. Event Router 재시작

```bash
kubectl rollout restart deploy/event-router -n event-router
kubectl rollout status deploy/event-router -n event-router --timeout=60s
```

**결과:** 재시작 후 일부 이벤트(queued, intent, rag) 전달 성공, 하지만 후반 이벤트는 여전히 지연

### 5.2. SSE Gateway State Polling

SSE Gateway의 fallback 메커니즘(5초 무소식 시 State KV 폴링)으로 최종 결과는 전달됨.

```python
# sse-gateway/core/broadcast_manager.py
except asyncio.TimeoutError:
    # 5초 무소식 → State 폴링
    state = await self._get_state_snapshot(job_id)
    if state and state.get("stage") == "done":
        async for event in self._catch_up_from_streams(...):
            yield event
        yield state
        break
```

---

## 6. 추가 조사 필요 사항

### 6.1. Event Router 코드 분석

- `event_router/core/consumer.py`: XREADGROUP 루프 로직
- `event_router/core/processor.py`: Lua Script 실행 및 PUBLISH 로직

### 6.2. 메트릭 확인

```bash
curl http://event-router:8000/metrics | grep -E 'events_processed|pubsub_published'
```

### 6.3. 네트워크 정책 확인

```bash
kubectl get networkpolicy -n event-router -o yaml
```

Event Router → Pub/Sub Redis 통신이 차단되었을 가능성.

---

## 7. 관련 문서

- [37-sse-event-bus-troubleshooting.md](../async/37-sse-event-bus-troubleshooting.md) - 이전 Event Bus 트러블슈팅
- [38-event-router-implementation.md](../async/38-event-router-implementation.md) - Event Router 구현
- [SKILL.md: k8s-debugging](../../.claude/skills/k8s-debugging/SKILL.md) - 클러스터 디버깅

---

## 8. 해결

### 8.1. 근본 원인

| 문제 | 원인 |
|------|------|
| Pub/Sub 발행 실패 시 재시도 없음 | `processor.py`: 실패해도 `publish_key` 설정됨 → 재시도 시 duplicate로 스킵 |
| 로깅 레벨 DEBUG | `event_processed` 로그가 DEBUG → LOG_LEVEL=INFO에서 추적 불가 |

### 8.2. 수정 사항 (PR #439)

**processor.py**:
- Pub/Sub 발행 재시도 로직 추가 (max 3회, exponential backoff)
- 로그 레벨 DEBUG → INFO

**consumer.py**:
- `batch_received`, `event_received` 로그 추가 (INFO 레벨)

### 8.3. 검증 결과

**SSE 스트림:**
```
event: token_recovery  ← 토큰 스냅샷
event: answer (started/completed)  ← 답변 생성
event: done (completed)  ← 작업 완료 ✅
```

**Event Router 로그:**
```
2026-01-19 05:06:32 INFO batch_received
2026-01-19 05:06:32 INFO event_received
2026-01-19 05:06:32 INFO event_processed  ✅
```

### 8.4. 관련 PR

- [PR #439: fix(event-router): Pub/Sub 발행 재시도 로직 및 로깅 개선](https://github.com/eco2-team/backend/pull/439)
