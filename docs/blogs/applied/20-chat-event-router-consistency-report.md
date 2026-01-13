# Chat - Event Router 정합성 검증 리포트

> **작성일**: 2026-01-14  
> **검증 범위**: Chat Worker, Event Router, Chat API SSE Gateway  
> **상태**: ✅ 정합성 확보 완료

---

## 목차

0. [전체 아키텍처 개요](#0-전체-아키텍처-개요)
1. [검증 개요](#1-검증-개요)
2. [Shard 기반 아키텍처](#2-shard-기반-아키텍처)
3. [환경 변수 정합성](#3-환경-변수-정합성)
4. [버그 발견 및 수정](#4-버그-발견-및-수정)
5. [LangGraph + SSE 흐름 검증](#5-langgraph--sse-흐름-검증)
6. [Subagent 호환성](#6-subagent-호환성)
7. [도메인 분리 설계](#7-도메인-분리-설계)
8. [결론 및 권장사항](#8-결론-및-권장사항)

---

## 0. 전체 아키텍처 개요

### 0.1 Event Relay Layer 전체 흐름

```
┌─────────────────────────────────────────────────────────┐
│                     Client (Mobile/Web)                 │
│  ┌────────────────┐        ┌────────────────────────┐  │
│  │ POST /chat     │        │ GET /chat/{id}/events  │  │
│  │ {message, ...} │        │ (SSE Connection)       │  │
│  └───────┬────────┘        └────────────▲───────────┘  │
└──────────│─────────────────────────────│───────────────┘
           │                              │
           ▼                              │
┌────────────────────┐   ┌────────────────┴───────────────┐
│  Chat API          │   │  SSE Gateway (별도 서비스)     │
│  ┌──────────────┐  │   │  ┌──────────────────────────┐  │
│  │ JobProducer  │  │   │  │ BroadcastManager         │  │
│  │ XADD task    │  │   │  │ - GET {domain}:state:id  │  │
│  └──────┬───────┘  │   │  │ - SUB sse:events:{id}    │  │
│         │          │   │  └──────────────────────────┘  │
└─────────│──────────┘   └────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────┐
│  Redis (Task Queue)                                      │
│  chat:tasks                                              │
└───────────────────────────────┬──────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────┐
│  Chat Worker (LangGraph Pipeline)                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ProcessChatCommand                               │   │
│  │       ├── IntentNode → notify_stage(intent)       │   │
│  │       ├── [Router]                                │   │
│  │       ├── RAGNode → notify_stage(rag)             │   │
│  │       ├── CharacterNode → notify_stage(character) │   │ ← Subagent
│  │       ├── LocationNode → notify_stage(location)   │   │ ← Subagent
│  │       │                └→ notify_needs_input()    │   │ ← HITL
│  │       └── AnswerNode → notify_token() × N         │   │ ← Streaming
│  │                      → notify_stage(done)         │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  RedisProgressNotifier                            │   │
│  │  - hash(job_id) % 4 → shard                       │   │
│  │  - XADD chat:events:{shard}                       │   │
│  └─────────────────────────────┬────────────────────┘   │
└────────────────────────────────│────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────┐
│  Redis Streams (chat:events)                             │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐            │
│  │ :0     │ │ :1     │ │ :2     │ │ :3     │ (4 shards) │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘            │
│      └──────────┴──────────┴──────────┘                  │
└────────────────────────────────┬─────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────┐
│  Event Router                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  StreamConsumer (XREADGROUP)                      │   │
│  │  - Group: "eventrouter"                           │   │
│  │  - Streams: scan:events(4) + chat:events(4)       │   │
│  └─────────────────────────────┬────────────────────┘   │
│  ┌─────────────────────────────▼────────────────────┐   │
│  │  EventProcessor                                   │   │
│  │  - chat:events → chat:state (도메인별 prefix)     │   │
│  │  - stage=token → State 갱신 제외 (Pub/Sub만)      │   │
│  │  - Lua Script: 멱등성 + seq 기반 순서 보장        │   │
│  └─────────────────────────────┬────────────────────┘   │
│                                │                         │
│              ┌─────────────────┴─────────────────┐       │
│              ▼                                   ▼       │
│  ┌─────────────────────┐   ┌──────────────────────┐     │
│  │ State KV (Streams)  │   │ Pub/Sub (별도 Redis) │     │
│  │ chat:state:{job_id} │   │ sse:events:{job_id}  │     │
│  │ TTL: 1시간          │   │ (Fire-and-forget)    │     │
│  └─────────────────────┘   └──────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### 0.2 이벤트 발행 상세 흐름 (Subagent + SSE)

```
[Chat Worker]                [Event Router]           [Chat API]
     │                             │                       │
     │  1. notify_stage(intent)    │                       │
     │  ─────────────────────────► │                       │
     │  XADD chat:events:2         │                       │
     │                             │ 2. State 갱신         │
     │                             │ SETEX chat:state:123  │
     │                             │                       │
     │                             │ 3. Pub/Sub 발행       │
     │                             │ PUBLISH sse:events:123│
     │                             │ ──────────────────────┼► SSE
     │                             │                       │  data:{...}
     │                             │                       │
     │  4. CharacterNode (Subagent)│                       │
     │  gRPC → Character API       │                       │
     │  notify_stage(character)    │                       │
     │  ─────────────────────────► │ ────────────────────► │  data:{...}
     │                             │                       │
     │  5. LocationNode (Subagent) │                       │
     │  gRPC → Location API        │                       │
     │  notify_stage(location)     │                       │
     │  ─────────────────────────► │ ────────────────────► │  data:{...}
     │                             │                       │
     │  6. notify_needs_input()    │                       │  [HITL]
     │  ─────────────────────────► │ ────────────────────► │  data:{needs_input}
     │                             │                       │  ↓
     │         [Pipeline Pause]    │                       │  사용자 입력 대기
     │              ...            │                       │
     │                             │                       │
     │  7. AnswerNode (streaming)  │                       │
     │  notify_token("안") → seq 1001                      │
     │  ─────────────────────────► │ ────────────────────► │  data:{token:"안"}
     │  notify_token("녕") → seq 1002                      │
     │  ─────────────────────────► │ ────────────────────► │  data:{token:"녕"}
     │         ... (N tokens)      │                       │
     │                             │  Token은 State 제외   │
     │                             │  (Pub/Sub만 발행)     │
     │                             │                       │
     │  8. notify_stage(done)      │                       │
     │  ─────────────────────────► │ State 갱신 + Pub/Sub  │
     │                             │ ────────────────────► │  data:{done}
     │                             │                       │  SSE 종료
```

### 0.3 정합성 체크 포인트

| # | 체크 포인트 | 컴포넌트 | 상태 |
|---|------------|----------|------|
| 1 | Stream Key 형식 | chat_worker, event_router | ✅ `chat:events:{shard}` |
| 2 | Shard 수 | chat_worker, event_router, sse_gateway | ✅ 4개 |
| 3 | State Key Prefix | event_router, sse_gateway | ✅ `chat:state`, `scan:state` |
| 4 | Pub/Sub Channel | event_router, sse_gateway | ✅ `sse:events` |
| 5 | Token/Stage seq 분리 | chat_worker, event_router | ✅ Stage(0-79), Token(1000+) |
| 6 | 환경 변수 매핑 | 모든 config, deployment, configmap | ✅ 일치 |
| 7 | SSE 처리 분리 | Chat API → SSE Gateway | ✅ 멀티 도메인 지원 |

---

## 1. 검증 개요

### 1.1 검증 대상

| 컴포넌트 | 역할 | 파일 |
|---------|------|------|
| **Chat Worker** | LangGraph 파이프라인, 이벤트 발행 | `apps/chat_worker/` |
| **Event Router** | Redis Streams → State KV + Pub/Sub | `apps/event_router/` |
| **SSE Gateway** | 멀티 도메인 SSE 스트리밍 | `apps/sse_gateway/` |
| **Chat API** | 작업 제출, 상태 조회 | `apps/chat/` |

### 1.2 검증 항목

- [x] Shard 수 일치 (4개)
- [x] Stream Key 형식 일치 (`chat:events:{shard}`)
- [x] State Key Prefix 일치 (`chat:state`)
- [x] 환경 변수 매핑
- [x] Token seq vs Stage seq 충돌 방지
- [x] Subagent 이벤트 흐름
- [x] Human-in-the-Loop (needs_input) 처리

---

## 2. Shard 기반 아키텍처

### 2.1 전체 흐름

```
┌──────────────────────────────────────────────────┐
│  Chat Worker                                     │
│  ┌────────────────────────────────────────────┐  │
│  │  RedisProgressNotifier                     │  │
│  │  - hash(job_id) % 4 → shard 결정           │  │
│  │  - XADD chat:events:{shard}                │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│  Redis Streams                                   │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │:events │ │:events │ │:events │ │:events │    │
│  │  :0    │ │  :1    │ │  :2    │ │  :3    │    │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘    │
│      └──────────┴──────────┴──────────┘         │
└──────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│  Event Router                                    │
│  ┌────────────────────────────────────────────┐  │
│  │  StreamConsumer (XREADGROUP)               │  │
│  │  - Consumer Group: "eventrouter"           │  │
│  │  - scan:events(4) + chat:events(4)         │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  EventProcessor                            │  │
│  │  - chat:events:0 → chat:state              │  │
│  │  - SETEX chat:state:{job_id}               │  │
│  │  - PUBLISH sse:events:{job_id}             │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────┐
│  Chat API                                        │
│  ┌────────────────────────────────────────────┐  │
│  │  SSE Gateway                               │  │
│  │  - GET chat:state:{job_id} (재접속 복구)   │  │
│  │  - SUBSCRIBE sse:events:{job_id} (실시간)  │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  GetJobStatusQuery                         │  │
│  │  - GET chat:state:{job_id} (상태 조회)     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 2.2 Shard vs Pod 스케일링

```
┌────────────────────────────────────────────────┐
│  Shard 수: 고정 (4개)                          │
│  - 해시 불일치 방지                            │
│  - 변경 시 전체 재배포 필요                    │
│                                                │
│  Consumer (Pod) 수: 동적 (1~4개)               │
│  - HPA/KEDA로 스케일링                         │
│  - Consumer Group이 자동 분배                  │
│                                                │
│  Pod 1개: 모든 shard 처리                      │
│  Pod 2개: 각 2개 shard (자동 분배)             │
│  Pod 4개: 각 1개 shard (최적)                  │
└────────────────────────────────────────────────┘
```

---

## 3. 환경 변수 정합성

### 3.1 검증 결과

| 컴포넌트 | 환경 변수 | 값 | 상태 |
|---------|----------|---|------|
| Chat Worker | `CHAT_SHARD_COUNT` | 4 | ✅ |
| Chat Worker ConfigMap | `CHAT_SHARD_COUNT` | 4 | ✅ |
| Event Router | `shard_count` | 4 | ✅ |
| Event Router | `chat_shard_count` | 4 | ✅ |
| Event Router Deploy | `SHARD_COUNT` | 4 | ✅ |
| Event Router Deploy | `CHAT_SHARD_COUNT` | 4 | ✅ |
| SSE Gateway | `shard_count` | 4 | ✅ |
| SSE Gateway Deploy | `SSE_SHARD_COUNT` | 4 | ✅ |

### 3.2 수정된 파일

**문제**: `SSE_SHARD_COUNT` → pydantic-settings 불일치

**수정**:
```yaml
# Before
- name: SSE_SHARD_COUNT
  value: '4'

# After
- name: SHARD_COUNT
  value: '4'
- name: CHAT_SHARD_COUNT
  value: '4'
```

### 3.3 State Key Prefix 정합성

| 컴포넌트 | Prefix | 상태 |
|---------|--------|------|
| Chat SSE Gateway | `chat:state` | ✅ |
| Chat GetJobStatusQuery | `chat:state` | ✅ |
| Event Router | `chat:events:* → chat:state` | ✅ |

**수정**: `get_job_status.py`
- Before: `chat:events:{job_id}` (잘못된 스트림 조회)
- After: `chat:state:{job_id}` (State KV 조회)

---

## 4. 버그 발견 및 수정

### 4.1 Token seq vs Stage seq 충돌

**문제 발견**:

```
Stage seq 범위:
  queued:    0, 1
  intent:    10, 11
  rag:       20, 21
  character: 30, 31
  location:  40, 41
  answer:    50, 51  ← 충돌!
  done:      60, 61

Token seq 범위 (수정 전):
  token[0]:  51  ← answer와 충돌!
  token[10]: 61  ← done와 충돌!
  token[11]: 62  ← done보다 높음!
```

**영향**: 토큰 11개 이상 시 `done` State 반영 안됨

**원인**: Lua Script 조건부 갱신
```lua
if new_seq <= cur_seq then
    should_update_state = false
end
```

### 4.2 수정 내용

**1. Token seq 시작값 변경**:
```python
# Before
self._token_seq[task_id] = 50

# After
TOKEN_SEQ_START = 1000
self._token_seq[task_id] = TOKEN_SEQ_START
```

**2. Token State 갱신 제외**:
```python
is_token_event = stage == "token"

if is_token_event:
    await self._pubsub_redis.publish(channel, event_data)
    return True  # State 갱신 스킵
```

### 4.3 수정 후 검증

```
Stage seq: 0~79 (8개 stage * 10)
Token seq: 1000+ (별도 namespace)

✅ seq 충돌 없음
✅ done 상태 정상 반영
✅ 토큰 스트리밍 정상
```

---

## 5. LangGraph + SSE 흐름 검증

### 5.1 이벤트 발행 흐름

```
ProcessChatCommand.execute()
    │
    ├── notify_stage(stage="queued")
    │
    └── pipeline.ainvoke(state)
            │
            ├── IntentNode
            │   ├── stage="intent" started
            │   └── stage="intent" completed
            │
            ├── [Router: intent별 분기]
            │
            ├── RAGNode (waste)
            │   ├── stage="rag" started
            │   └── stage="rag" completed
            │
            ├── CharacterNode [Subagent]
            │   └── stage="character" processing
            │
            ├── LocationNode [Subagent + HITL]
            │   ├── stage="location" processing
            │   └── [선택] needs_input
            │
            └── AnswerNode
                ├── stage="answer" started
                ├── [Loop] token (1001, 1002, ...)
                └── stage="answer" completed
    │
    └── notify_stage(stage="done")
```

### 5.2 이벤트 필드 정합성

```python
# Stage 이벤트
{
    "job_id": str,    # 필수
    "stage": str,     # intent, rag, answer, done
    "status": str,    # started, completed, failed
    "seq": int,       # 0~79
    "ts": str,
    "progress": str,  # 선택
    "result": str,    # 선택
    "message": str,   # 선택
}

# Token 이벤트
{
    "job_id": str,
    "stage": "token",
    "status": "streaming",
    "seq": int,       # 1001, 1002, ...
    "ts": str,
    "content": str,   # 토큰 내용
}
```

---

## 6. Subagent 호환성

### 6.1 Subagent 종류

| Subagent | 호출 방식 | Stage | 비고 |
|----------|----------|-------|------|
| Character | gRPC | `character` | - |
| Location | gRPC | `location` | HITL 지원 |

### 6.2 이벤트 발행 패턴

모든 Subagent가 동일한 `ProgressNotifierPort` 사용:

```python
# Character Subagent (gRPC only)
await event_publisher.notify_stage(
    task_id=job_id,
    stage="character",
    status="processing",
)

# Location Subagent (gRPC + HITL via HTTP)
# 1. 위치 없으면 needs_input 발행
await event_publisher.notify_needs_input(
    task_id=job_id,
    input_type="location",
    message="위치 권한이 필요해요!",
)
# 2. 스킵 후 진행 (blocking wait 없음)
# 3. 클라이언트가 HTTP로 위치 전송 후 재요청
```

### 6.2.1 HITL 흐름 (HTTP 기반)

```
Client             Chat API           Chat Worker        Location API
   │                  │                   │                   │
   ├─ POST /chat ────►│                   │                   │
   │  (위치 없음)      │── Redis Queue ───►│                   │
   │                  │                   │                   │
   │                  │◄─ needs_input ────┤                   │
   │◄─ SSE ───────────┤                   │                   │
   │                  │                   │                   │
   │  Geolocation API │                   │                   │
   │  (위치 수집)      │                   │                   │
   │                  │                   │                   │
   ├─ POST /chat ────►│                   │                   │
   │  (위치 포함)      │── Redis Queue ───►│── gRPC ──────────►│
   │                  │                   │◄──────────────────┤
   │◄─ SSE (done) ────┤◄─────────────────┤                   │
```

### 6.3 호환성 확인

```
┌──────────────┬────────┬─────────────────────┐
│ Stage        │ Seq    │ 발행 노드           │
├──────────────┼────────┼─────────────────────┤
│ queued       │  0-1   │ ProcessChatCommand  │
│ intent       │ 10-11  │ IntentNode          │
│ rag          │ 20-21  │ RAGNode             │
│ character    │ 30-31  │ CharacterNode       │
│ location     │ 40-41  │ LocationNode        │
│ answer       │ 50-51  │ AnswerNode          │
│ done         │ 60-61  │ ProcessChatCommand  │
│ needs_input  │ 70-71  │ LocationNode (HITL) │
├──────────────┼────────┼─────────────────────┤
│ token        │ 1000+  │ AnswerNode          │
└──────────────┴────────┴─────────────────────┘

✅ 모든 Subagent 동일 패턴
✅ Event Router 동일 처리
✅ Token 별도 처리 (State 제외)
```

---

## 7. 도메인 분리 설계

### 7.1 현재 구조 (단일 Event Router)

```
┌────────────────────────────────────────────┐
│  Event Router (단일 Pod)                   │
│                                            │
│  STREAM_PREFIXES: "scan:events,chat:events"│
│                                            │
│  ┌─────────────┐  ┌─────────────┐          │
│  │scan:events  │  │chat:events  │          │
│  │  :0-3       │  │  :0-3       │          │
│  └──────┬──────┘  └──────┬──────┘          │
│         └────────┬───────┘                 │
│                  ▼                         │
│         Consumer Group                     │
│         "eventrouter"                      │
│                  │                         │
│         _get_state_prefix():               │
│           scan:events → scan:state         │
│           chat:events → chat:state         │
└────────────────────────────────────────────┘
```

### 7.2 분리 가능성

**환경 변수만으로 분리 가능** (코드 변경 없음):

```yaml
# scan-event-router
env:
- name: STREAM_PREFIXES_STR
  value: "scan:events"
- name: CONSUMER_GROUP
  value: "scan-router"

# chat-event-router
env:
- name: STREAM_PREFIXES_STR
  value: "chat:events"
- name: CONSUMER_GROUP
  value: "chat-router"
```

### 7.3 분리 시 장단점

| 항목 | 단일 | 분리 |
|-----|------|------|
| 장애 격리 | ❌ | ✅ |
| 독립 스케일링 | ❌ | ✅ |
| 배포 | 한 번 | 독립 |
| 리소스 | 적음 | 많음 |
| 운영 복잡도 | 낮음 | 중간 |

**결정**: 단일 유지, 필요 시 환경 변수로 분리

---

## 8. 결론 및 권장사항

### 8.1 정합성 상태

| 검증 항목 | 상태 |
|----------|------|
| Shard 수 일치 | ✅ |
| Stream Key 형식 | ✅ |
| State Key Prefix | ✅ |
| 환경 변수 매핑 | ✅ |
| Token/Stage seq 분리 | ✅ |
| Subagent 호환성 | ✅ |
| 도메인 분리 | ✅ |
| SSE 처리 통합 | ✅ |

### 8.2 수정된 파일 목록

| 파일 | 변경 내용 |
|-----|----------|
| `redis_progress_notifier.py` | Token seq 1000+ |
| `event_router/processor.py` | Token State 제외 |
| `event_router/config.py` | 환경 변수 문서 |
| `event_router/deployment.yaml` | SHARD_COUNT 추가 |
| `chat-worker/configmap.yaml` | CHAT_SHARD_COUNT |
| `get_job_status.py` | State KV 조회 |
| `sse_gateway/config.py` | SSE_SHARD_COUNT 환경변수 추가 |
| `sse_gateway/broadcast_manager.py` | 멀티 도메인 지원 (scan, chat) |
| `sse_gateway/stream.py` | domain 파라미터 전달 |
| `sse-gateway/deployment.yaml` | SSE_SHARD_COUNT 환경변수 |
| `chat/main.py` | 내장 SSE 제거 |
| `chat/presentation/http/sse.py` | 삭제 (SSE Gateway로 이전) |

### 8.3 권장사항

1. **Shard 변경**: 모든 컴포넌트 동시 배포
2. **스케일링**: Pod만 동적, Shard 고정
3. **모니터링**: Token 발행량, Pub/Sub 지연
4. **개선**: Character/Location 완료 이벤트 추가

---

## 커밋 정보

### Commits

1. **fix(sse-gateway): replace hardcoded shard_count with env var**
   - `apps/sse_gateway/config.py`
   - `apps/sse_gateway/core/broadcast_manager.py`
   - `workloads/domains/sse-gateway/base/deployment.yaml`

2. **fix(event-router): align env vars and fix token state update**
   - `apps/event_router/config.py`
   - `apps/event_router/core/processor.py`
   - `workloads/domains/event-router/base/deployment.yaml`

3. **refactor(chat-worker): unify subagent to gRPC and HITL to HTTP**
   - `apps/chat_worker/.../location_node.py`
   - `apps/chat_worker/.../factory.py`
   - `apps/chat_worker/.../redis_progress_notifier.py`

4. **refactor(sse-gateway): add multi-domain support (scan, chat)**
   - `apps/sse_gateway/core/broadcast_manager.py`: 도메인별 state prefix
   - `apps/sse_gateway/api/v1/stream.py`: domain 파라미터 지원
   - `apps/chat/main.py`: 내장 SSE 제거
   - `apps/chat/presentation/http/sse.py`: 삭제 (SSE Gateway로 이전)

### Summary

| 변경 | 설명 |
|-----|------|
| Token seq 시작값 | 50 → 1000 (Stage seq 충돌 방지) |
| Token State 갱신 | 제외 (Pub/Sub만 발행) |
| SSE Gateway shard | 하드코딩 → 환경변수 |
| Event Router env | SSE_SHARD_COUNT → SHARD_COUNT |
| Location Subagent | HITL 제거, gRPC 통일 |
| HITL 흐름 | needs_input 이벤트 + HTTP 입력 |
| SSE 처리 통합 | Chat API 내장 SSE → SSE Gateway |
| 멀티 도메인 | SSE Gateway가 scan + chat 모두 처리 |

**Affected Services**: `chat_worker`, `event_router`, `chat`, `sse_gateway`
