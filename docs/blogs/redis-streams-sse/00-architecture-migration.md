# 이코에코(Eco²) Redis Streams for SSE #0: 3-Node Redis Cluster 아키텍처 및 마이그레이션안

> **작성일**: 2025-12-26  
> **시리즈**: Redis Streams for SSE

---

## 배경: SSE 50 VU 병목 발견

Scan API의 SSE(Server-Sent Events) 스트리밍 기능에서 50 VU 부하 테스트 중 심각한 성능 저하가 발생했다.

### 테스트 환경

| 항목 | 값 |
|------|-----|
| 테스트 도구 | k6 |
| 가상 사용자 | 50 VU |
| 엔드포인트 | `POST /api/v1/scan/classify/completion` |
| 테스트 시간 | 10분 |

### 관측된 문제

| 지표 | 값 | 문제 |
|------|-----|------|
| SSE : RabbitMQ 연결 | **1 : 21** | 연결 폭발 |
| RabbitMQ 연결 (max) | 341개 | 8.7배 급증 |
| scan-api 메모리 | 676Mi | 512Mi limit 초과 |
| 503 에러 | 발생 | Readiness 실패 |

---

## 문제 분석: 연쇄 실패 흐름

```
50 VU 부하
    ↓
SSE 연결 16개 (동시 처리 중)
    ↓ × 21 연결/SSE
RabbitMQ 341개 연결
    ↓
메모리 676Mi > 512Mi
    ↓
Readiness 실패
    ↓
503 no healthy upstream
```

### 근본 원인: Celery Events

SSE 구현에서 Celery Events를 사용하여 작업 진행 상태를 실시간으로 수신했다.

```python
# 기존 구현 (문제)
with app.connection() as conn:           # RabbitMQ 연결
    recv = EventReceiver(conn, handlers) # Event 수신기
    recv.capture(limit=None, timeout=60) # Blocking 대기
```

**문제점**:
- 각 SSE 연결마다 새로운 RabbitMQ Connection 생성
- `celery.events` Exchange에 다수의 Consumer 생성
- Connection 재사용 불가 (Blocking 특성)

### 구조적 곱 폭발

```
❌ 현재: Client × RabbitMQ 연결 = 곱 폭발
   예: 50 VU × 21 연결 = 1,050+ 연결 (최악의 경우)

✅ 목표: Client × Redis 읽기 = Pod당 1개 (상수)
   예: 50 VU × 1 연결 = 50 연결
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

| 장점 | 단점 |
|------|------|
| API 변경 없음 (기존 클라이언트 호환) | SSE 연결 시간 = Chain 완료 시간 (~10~20초) |
| UX 동일 (실시간 stage 진행) | |
| 변경 최소화 | |

### 방법 2: `/start` + `/stream/{job_id}` 분리

```
POST /start → job_id 반환
GET /stream/{job_id} → SSE 구독
```

| 장점 | 단점 |
|------|------|
| 연결 시간 분리 | API 변경 필요 |
| | Race condition: `/start` 후 `/stream` 전에 완료 가능 |
| | 리플레이 구현 필요 |

### 방법 3: Polling + `/result/{job_id}`

| 장점 | 단점 |
|------|------|
| 구현 단순 | 실시간 UX 포기 |
| | 불필요한 폴링 오버헤드 |

### 선택: 방법 1

| 기준 | 방법 1 | 방법 2 | 방법 3 |
|------|--------|--------|--------|
| API 호환 | ✅ | ❌ | ❌ |
| 실시간 UX | ✅ | ✅ | ❌ |
| 변경 범위 | 최소 | 중간 | 낮음 |
| Race condition | 없음 | 있음 | 없음 |

**핵심 원칙**: "구독 먼저, 발행 나중"

> Redis Streams 구독을 먼저 시작한 후 Celery Chain을 발행하면,
> 이벤트 누락 없이 모든 stage를 수신할 수 있다.

---

## 목표 아키텍처: Redis Streams 기반 이벤트 소싱

### 아키텍처 변경

```
┌─────────────────────────────────────────────────────────────────┐
│  ❌ 기존 구조 (곱 폭발)                                          │
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
│  scan-api → SSE (XREAD BLOCK)                                     │
├───────────────────────────────────────────────────────────────────┤
│  async for event in redis.xread_stream("scan:events:{job_id}"):   │
│      yield f"data: {json.dumps(event)}\\n\\n"                     │
└───────────────────────────────────────────────────────────────────┘
```

---

## Redis 분리 설계: 3-Node Cluster

### 기존 구조의 문제

```
┌─────────────────────────────────────────────────────────────┐
│  단일 Redis (k8s-redis, t3.medium)                          │
│                                                              │
│  DB 0: JWT Blacklist (보안, noeviction 필요)                │
│  DB 1: Celery Result (휘발성, LRU eviction 가능)            │
│  DB 2: SSE Streams (휘발성, 빠른 응답 필요)                  │
│  DB 3: OAuth State (보안, noeviction 필요)                  │
│  ...                                                         │
│                                                              │
│  ❌ 문제:                                                    │
│  - eviction 정책 충돌 (보안 vs 캐시)                        │
│  - 장애 시 전체 시스템 영향                                 │
│  - 용도별 리소스 튜닝 불가                                  │
└─────────────────────────────────────────────────────────────┘
```

### 목표 구조: 용도별 분리

```
┌─────────────────────────────────────────────────────────────┐
│  k8s-redis-auth (t3.medium)                                  │
│  ├─ JWT Blacklist + OAuth State                              │
│  ├─ Policy: noeviction (보안 데이터 보호)                   │
│  └─ Storage: PVC (AOF 영속성)                               │
├─────────────────────────────────────────────────────────────┤
│  k8s-redis-streams (t3.small)                                │
│  ├─ SSE 이벤트 (Redis Streams)                              │
│  ├─ Policy: noeviction (이벤트 유실 방지)                   │
│  └─ Storage: emptyDir (휘발성, TTL 자동 정리)               │
├─────────────────────────────────────────────────────────────┤
│  k8s-redis-cache (t3.small)                                  │
│  ├─ Celery Result + Domain Cache                             │
│  ├─ Policy: allkeys-lru (메모리 부족 시 eviction)           │
│  └─ Storage: emptyDir (휘발성)                              │
└─────────────────────────────────────────────────────────────┘
```

### Eviction 정책 선택 근거

| Redis 인스턴스 | Policy | 근거 |
|----------------|--------|------|
| auth-redis | noeviction | JWT Blacklist 삭제 시 만료된 토큰 재사용 가능 (보안 위험) |
| streams-redis | noeviction | 처리 전 이벤트 삭제 시 SSE 스트림 끊김 |
| cache-redis | allkeys-lru | 오래된 Celery 결과는 eviction해도 재요청 가능 |

---

## 예상 효과

### 연결 수 비교

| 상황 | 기존 (Celery Events) | 변경 (Redis Streams) |
|------|----------------------|----------------------|
| 50 VU | 341+ 연결 | 50 연결 |
| 100 VU | 700+ 연결 (추정) | 100 연결 |
| 확장성 | O(n × m) | O(n) |

### 메모리 사용량 예상

| 구성 요소 | 기존 | 변경 |
|----------|------|------|
| RabbitMQ 연결 | 높음 | 없음 (SSE 관련) |
| Redis 연결 | - | 낮음 (Pool 재사용) |
| scan-api 메모리 | 676Mi | < 300Mi (예상) |

---

## 마이그레이션 단계

1. **#1 리소스 프로비저닝**: EC2 3노드 추가 (Terraform, Ansible)
2. **#2 선언적 배포**: Spotahome Redis Operator + RedisFailover CR
3. **#3 Application Layer**: Redis Streams 모듈, Worker 이벤트 발행
4. **#4 Observability**: ServiceMonitor, 대시보드, Alert Rules
5. **검증**: k6 50 VU 재테스트

---

## 참고 자료

- [Redis Streams 공식 문서](https://redis.io/docs/latest/develop/data-types/streams/)
- [Celery Events 문서](https://docs.celeryq.dev/en/stable/userguide/monitoring.html#events)
- [XREAD BLOCK 패턴](https://redis.io/docs/latest/commands/xread/)

---

## 다음 단계

→ [#1: 리소스 프로비저닝](./01-provisioning.md)

