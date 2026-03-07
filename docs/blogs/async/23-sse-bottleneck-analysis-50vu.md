# SSE 50 VU 부하 테스트 병목 분석 레포트

> **테스트 일시**: 2025-12-25 10:45 ~ 10:55 KST (약 10분)  
> **테스트 환경**: k6 SSE Load Test, 50 VU  
> **엔드포인트**: `POST /api/v1/scan/classify/completion`

---

## 📊 Executive Summary

| 구분 | 결과 |
|------|------|
| **테스트 결과** | 🔴 실패 (503 에러 폭증) |
| **주요 병목** | scan-api → RabbitMQ 연결 관리 |
| **근본 원인** | SSE 연결당 다수의 RabbitMQ 연결 생성 |
| **연결 비율** | SSE 16개 : RabbitMQ 341개 = **1:21** |

---

## 📈 Prometheus 메트릭 분석

### 1. RabbitMQ 연결 수

```
┌─────────────────────────────────────────────────────────┐
│  RabbitMQ Connections (10분 범위)                        │
├──────────────┬──────────────────────────────────────────┤
│  최소        │  39                                       │
│  최대        │  341  🔥 (8.7배 증가)                     │
│  평균        │  131                                      │
│  현재        │  129                                      │
└──────────────┴──────────────────────────────────────────┘
```

### 2. SSE 활성 연결 수

```
┌─────────────────────────────────────────────────────────┐
│  SSE Active Connections (10분 범위)                      │
├──────────────┬──────────────────────────────────────────┤
│  최소        │  0                                        │
│  최대        │  16                                       │
│  평균        │  3                                        │
│  현재        │  16                                       │
└──────────────┴──────────────────────────────────────────┘
```

### 3. 핵심 비율 분석

```
SSE 연결 : RabbitMQ 연결 = 16 : 341 = 1 : 21.3
```

**의미**: 각 SSE 클라이언트가 약 21개의 RabbitMQ 연결을 유발

### 4. RabbitMQ 연결 증가율

```
┌─────────────────────────────────────────────────────────┐
│  Connection Open Rate (1분당)                            │
├──────────────┬──────────────────────────────────────────┤
│  최대        │  226 연결/분  🔥                          │
│  평균        │  84.5 연결/분                             │
└──────────────┴──────────────────────────────────────────┘
```

### 5. scan-api 메모리 사용량

```
┌─────────────────────────────────────────────────────────┐
│  Memory Usage (scan-api 전체)                            │
├──────────────┬──────────────────────────────────────────┤
│  최소        │  108 Mi                                   │
│  최대        │  676 Mi  (Limit 512Mi 초과!)              │
│  평균        │  392 Mi  (76% of limit)                   │
└──────────────┴──────────────────────────────────────────┘
```

### 6. Pod 스케일링 이벤트

```
┌─────────────────────────────────────────────────────────┐
│  HPA Scaling Events                                      │
├──────────────┬──────────────────────────────────────────┤
│  Pod 범위    │  1 → 4 → 1  (불안정)                      │
│  스케일업    │  New size: 3 (CPU above target)           │
│  스케일다운  │  New size: 2 (CPU above target)           │
└──────────────┴──────────────────────────────────────────┘
```

### 7. Queue 메시지 적체

```
┌─────────────────────────────────────────────────────────┐
│  Queue Message Backlog (Max)                             │
├──────────────────────────┬──────────────────────────────┤
│  RPC Reply Queue (UUID)  │  372  🔥 (응답 대기 중)       │
│  scan.answer             │  9                            │
│  scan.vision             │  9                            │
│  scan.reward             │  2                            │
└──────────────────────────┴──────────────────────────────┘
```

---

## 🔍 병목 원인 분석

### 연쇄 실패 시퀀스

```
1. k6 50 VU 테스트 시작
   ↓
2. SSE 연결 급증 (최대 16개 동시)
   ↓
3. 각 SSE 연결이 Celery Events 구독을 위해
   별도 RabbitMQ 연결 생성 (341개 폭증)
   ↓
4. scan-api 메모리 사용량 증가 (676Mi > 512Mi limit)
   ↓
5. CPU 과부하 (HPA 감지: 165%/70%)
   ↓
6. Readiness probe 실패 (HTTP 503)
   ↓
7. Kubernetes가 Pod를 Unhealthy로 표시
   ↓
8. Envoy가 해당 Pod를 upstream에서 제외
   ↓
9. 503 "no healthy upstream" 에러 반환
   ↓
10. 남은 Pod에 부하 집중 → 연쇄 실패
```

### 핵심 병목 지점

```
┌──────────────────────────────────────────────────────────────┐
│                        BOTTLENECK                             │
│                                                               │
│   ┌─────────┐     1:21 비율     ┌──────────────┐             │
│   │  SSE    │ ─────────────────→│  RabbitMQ    │             │
│   │ Client  │    연결 폭증      │  Connections │             │
│   └─────────┘                   └──────────────┘             │
│        │                              │                       │
│        │                              ↓                       │
│        │                    ┌──────────────────┐             │
│        │                    │  scan-api        │             │
│        │                    │  Memory > Limit  │             │
│        │                    │  CPU 165%        │             │
│        │                    └──────────────────┘             │
│        │                              │                       │
│        │                              ↓                       │
│        │                    ┌──────────────────┐             │
│        └───────────────────→│  503 Error       │             │
│                             │  Readiness Fail  │             │
│                             └──────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

---

## 📋 SSE Celery Events 구조 분석

### 현재 구현

```python
# domains/scan/api/v1/endpoints/completion.py

async def stream_task_progress(...):
    with app.connection() as connection:  # 🔥 SSE마다 새 연결
        recv = app.events.Receiver(connection, handlers={...})
        for _ in recv.itercapture():
            # Celery 이벤트 수신
            yield format_sse(...)
```

### 문제점

| 구성요소 | 설명 | 문제 |
|---------|------|------|
| **SSE 연결** | 클라이언트 1개당 1개 | 정상 |
| **Celery Events Receiver** | SSE 1개당 1개 | 🔥 과다 |
| **RabbitMQ 연결** | Receiver 1개당 N개 | 🔥 폭증 |
| **celeryev.* 큐 구독** | Receiver마다 생성 | 🔥 과다 |

### RabbitMQ 연결 내역 (추정)

```
1 SSE 클라이언트당:
  - 1x Celery Events connection
  - 1x task-sent 이벤트 구독
  - 1x task-received 이벤트 구독
  - 1x task-started 이벤트 구독
  - 1x task-succeeded 이벤트 구독
  - 1x task-failed 이벤트 구독
  - 1x worker-heartbeat 구독
  - 1x 결과 조회 (Redis이지만 추가 연결)
  ─────────────────────────
  ≈ 8~10개 연결/SSE
```

50 VU × 10 연결 = **500개 잠재 연결**

---

## 🏗️ 권장 아키텍처: 오케스트레이션과 SSE 분리

### 핵심 원칙

> **"Celery/RabbitMQ는 작업 큐로만 쓰고, 단계 이벤트는 Redis Streams에 발행.  
> SSE 서버는 Streams를 1~소수 consumer로 읽어 fan-out만 담당.  
> 클라이언트 수 증가가 Redis read/AMQP connection 증가로 직결되지 않게 만든다."**

### 현재 vs 권장 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  ❌ 현재 구조 (곱 폭발)                                          │
│                                                                  │
│  Client ──SSE──→ scan-api ──→ Celery Events (RabbitMQ)          │
│                                      │                          │
│                    클라이언트 × RabbitMQ 연결 = 곱 폭발          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ✅ 권장 구조 (분리)                                             │
│                                                                  │
│  1. POST /start → job_id 즉시 반환 → Celery Chain 발행          │
│                         │                                        │
│                         ▼ 단계마다 이벤트 1개 발행               │
│  2. Worker ────────→ Redis Streams (scan:events:{job_id})       │
│                         │                                        │
│                         ▼ Pod당 1개 consumer                     │
│  3. SSE Server ────→ 해당 job_id 클라이언트에 fan-out           │
│                         │                                        │
│                         ▼ 최종 결과는 단발 REST                  │
│  4. GET /result/{job_id} → 캐시/리플레이 가능                   │
└─────────────────────────────────────────────────────────────────┘
```

### Stage 이벤트 전달 흐름

**새 구조에서도 stage 진행 상황을 클라이언트에게 전달 가능!**

```
┌─────────────────────────────────────────────────────────────────┐
│  Worker가 Redis Streams에 발행하는 이벤트 (job당 8~12개)         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. {stage: "queued",   status: "started"}                      │
│  2. {stage: "vision",   status: "started"}                      │
│  3. {stage: "vision",   status: "completed", result: {...}}     │
│  4. {stage: "rule",     status: "started"}                      │
│  5. {stage: "rule",     status: "completed", result: {...}}     │
│  6. {stage: "answer",   status: "started"}                      │
│  7. {stage: "answer",   status: "completed", result: {...}}     │
│  8. {stage: "reward",   status: "started"}                      │
│  9. {stage: "reward",   status: "completed", result: {...}}     │
│ 10. {stage: "done",     result_url: "/result/{job_id}"}         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  SSE Server가 클라이언트에 전달하는 이벤트                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  event: stage                                                    │
│  data: {"step": "vision", "status": "started"}                  │
│                                                                  │
│  event: stage                                                    │
│  data: {"step": "vision", "status": "completed"}                │
│                                                                  │
│  event: stage                                                    │
│  data: {"step": "rule", "status": "started"}                    │
│  ...                                                             │
│                                                                  │
│  event: ready                                                    │
│  data: {"result_url": "/result/abc123"}                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### OpenAI 스타일 UX 매핑

| 내부 Stage | 사용자 친화 라벨 | 설명 |
|-----------|-----------------|------|
| `vision` | 🔍 찾는 중... | 이미지 분석 |
| `rule` | 📚 규칙 확인 중... | Rule-based retrieval |
| `answer` | 💭 정리 중... | LLM 답변 생성 |
| `reward` | 🎁 보상 확인 중... | 캐릭터 매칭 |
| `done` | ✅ 완료 | 결과 준비됨 |

### 구현 예시

```python
# 1. Worker: 단계마다 Redis Streams에 발행
import redis
import time

def publish_stage_event(job_id: str, stage: str, status: str, result: dict = None):
    """Worker가 호출: 단계 전환마다 1개 이벤트"""
    r = redis.Redis(host="streams-redis", port=6379, db=1)
    event = {
        "stage": stage,
        "status": status,
        "ts": str(time.time()),
    }
    if result:
        event["result"] = json.dumps(result)
    
    r.xadd(
        f"scan:events:{job_id}",
        event,
        maxlen=50  # retention: 최근 50개만 유지
    )


# 2. SSE 엔드포인트: 단일 /completion (기존 API 유지)
@router.post("/classify/completion")
async def classify_completion(payload: ClassificationRequest):
    """내부만 Celery Events → Redis Streams로 전환."""
    job_id = str(uuid.uuid4())
    
    async def generate():
        # 1. 구독 먼저 (이벤트 누락 방지)
    last_id = "0"
    
        # 2. Chain 발행 (구독 후 발행)
        publish_stage_event(job_id, "queued", "started")
        chain.apply_async(task_id=job_id)
        
        # 3. Redis Streams 구독 루프 (RabbitMQ 연결 없음!)
        r = await aioredis.from_url("redis://dev-redis:6379/1")
        while True:
            events = await r.xread({f"scan:events:{job_id}": last_id}, block=5000)
            if not events:
                yield ": keepalive\n\n"
                continue
            for _, messages in events:
            for msg_id, data in messages:
                last_id = msg_id
                yield f"event: stage\ndata: {json.dumps(data)}\n\n"
                if data.get("stage") == "done":
                    return
        
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Redis 분리 전략

| 초기 (합쳐도 OK) | 성숙기 (분리 권장) |
|-----------------|-------------------|
| 같은 Redis, DB만 분리 | 별도 Redis 인스턴스 |

```yaml
# 초기: 같은 Redis, DB 분리
REDIS_CACHE_URL: redis://dev-redis:6379/0      # 캐시 (LRU eviction)
REDIS_STREAMS_URL: redis://dev-redis:6379/1    # 이벤트 (noeviction)
REDIS_RESULT_URL: redis://dev-redis:6379/2     # Celery 결과

# 성숙기: 별도 인스턴스
REDIS_CACHE_URL: redis://cache-redis:6379/0
REDIS_STREAMS_URL: redis://streams-redis:6379/0  # 전용, retention 정책
```

**왜 분리?**
- 캐시: LRU/LFU eviction 정상 동작 필요
- Streams: eviction 발생 시 이벤트 유실 → UX 깨짐

---

## 🛠️ 개선 방안 (우선순위별)

### 즉시 (Hot Fix) - 현재 구조 유지

| 방안 | 효과 | 난이도 |
|------|------|--------|
| **scan-api 리소스 증가** | 메모리 512Mi → 1Gi | 낮음 |
| **HPA 최소 Pod 증가** | 1 → 2 | 낮음 |
| **Readiness probe 완화** | failureThreshold 증가 | 낮음 |

### 단기 (1주) - 아키텍처 분리

| 방안 | 효과 | 난이도 |
|------|------|--------|
| **Redis Streams 도입** | 이벤트 발행 분리 | 중간 |
| **SSE 서버 리팩토링** | RabbitMQ 의존성 제거 | 중간 |
| **결과 REST 분리** | `/result/{job_id}` 엔드포인트 | 낮음 |

### 중기 (2주) - 최적화

| 방안 | 효과 | 난이도 |
|------|------|--------|
| **Redis Streams 분리** | 캐시/이벤트 Redis 분리 | 중간 |
| **Consumer Group 도입** | 다중 SSE 서버 지원 | 중간 |
| **이벤트 압축** | stage 이벤트 최소화 | 낮음 |

---

## 📊 리소스 설정 권장

### scan-api Deployment

```yaml
# 현재
resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

# 권장 (50 VU 기준)
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### HPA 설정

```yaml
# 현재
minReplicas: 1
maxReplicas: 4
targetCPUUtilizationPercentage: 70

# 권장
minReplicas: 2  # 최소 2개로 가용성 확보
maxReplicas: 6  # 최대 증가
targetCPUUtilizationPercentage: 60  # 더 빨리 스케일
```

---

## 📊 예상 효과 비교

### 연결 비율 변화

| 구조 | SSE:RabbitMQ | SSE:Redis |
|------|-------------|-----------|
| 현재 | 1:21 🔥 | N/A |
| Redis Streams | 1:0 ✅ | Pod당 1개 |

### VU 수용량 예상

| 조치 | 예상 VU |
|------|---------|
| 현재 | 20~30 VU |
| 리소스 증가만 | 40~50 VU |
| **Redis Streams 분리** | **150~200+ VU** |

---

## 📌 결론

### 핵심 문제

> **SSE가 "파이프라인 실행 감시"와 "결과 전달"을 동시에 하면서  
> 클라이언트 × RabbitMQ 연결 = 곱 폭발 발생**

### 해결 원칙

> **오케스트레이션(Celery)과 표현(SSE)을 완전히 분리**
>
> - Celery/RabbitMQ: 작업 큐로만 사용
> - Redis Streams: 단계 이벤트 발행 (job당 8~12개)
> - SSE Server: Streams fan-out만 담당 (Pod당 1 consumer)
> - 결과 조회: 단발 REST `/result/{job_id}`

### Stage UX 유지

새 구조에서도 **stage 진행 상황을 클라이언트에게 전달 가능**:

```
vision[started] → vision[completed] → rule[started] → ...
```

Worker가 Redis Streams에 이벤트를 발행하고,  
SSE Server가 이를 클라이언트에 fan-out하는 구조.

### 최종 결정

| 조치 | 상태 | 효과 |
|------|------|------|
| **단일 /completion + Redis Streams** | ✅ 채택 | API 변경 없음, 연결 폭발 해결 |
| 구독 먼저 → 발행 나중 | ✅ 채택 | Race condition 방지 |
| /start + /stream 분리 | ❌ 기각 | Race condition 문제 |

---

## 후속 조치: Redis Streams 전환

이 분석 결과를 바탕으로 **Redis Streams 기반 SSE 전환**을 진행했습니다.

### 최종 결정 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  ✅ 최종 구조: 단일 /completion + Redis Streams                   │
│                                                                  │
│  POST /completion                                                │
│       │                                                          │
│       ├─ 1. Redis Streams 구독 시작                              │
│       ├─ 2. Celery Chain 발행                                    │
│       └─ 3. Streams 이벤트 → SSE 전송                            │
│                                                                  │
│  Worker ──XADD──→ Redis Streams ──XREAD──→ scan-api ──SSE──→ Client│
│                                                                  │
│  핵심: "구독 먼저, 발행 나중" → Race condition 방지              │
└─────────────────────────────────────────────────────────────────┘
```

### 기대 효과

| 지표 | 현재 | 예상 | 개선 |
|------|------|------|------|
| SSE : RabbitMQ | 1:21 | 1:0 | 100% 제거 |
| SSE : Redis | N/A | Pod당 1개 | 상수 |
| 메모리 (50 VU) | 676Mi | ~200Mi | 70% 감소 |
| 예상 VU | 20~30 | 150~200+ | 5~7x |

### 선택 근거

| 방법 | 설명 | 선택 |
|------|------|------|
| 방법 1: 단일 `/completion` + Redis Streams | API 변경 없음, UX 동일 | ✅ |
| 방법 2: `/start` + `/stream/{job_id}` 분리 | Race condition 발생 | ❌ |
| 방법 3: Polling | 실시간 UX 포기 | ❌ |

상세 구현은 [#14 Redis Streams SSE 전환](./24-redis-streams-sse-migration.md) 참조.

---

## 관련 문서

- [24. Redis Streams SSE 전환](./24-redis-streams-sse-migration.md) ← **후속 구현**
- [21. LLM Queue System Architecture](./21-llm-queue-system-architecture.md)
- [22. SSE Performance Benchmark](./22-scan-sse-performance-benchmark.md)
- [20. Gevent Migration Troubleshooting](./20-gevent-migration-troubleshooting.md)

