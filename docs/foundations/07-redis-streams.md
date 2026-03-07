# Redis Streams

> Redis Streams는 로그 기반 데이터 구조로, Apache Kafka의 핵심 아이디어를  
> Redis의 단순성과 결합한 메시지 브로커/이벤트 소싱 도구입니다.

---

## 공식 자료

### Redis 공식 문서

| 문서 | URL | 핵심 내용 |
|------|-----|---------|
| **Introduction to Redis Streams** | [redis.io/docs/data-types/streams](https://redis.io/docs/latest/develop/data-types/streams/) | Stream 개념, 명령어 기초 |
| **XADD** | [redis.io/commands/xadd](https://redis.io/docs/latest/commands/xadd/) | 이벤트 발행, MAXLEN |
| **XREAD** | [redis.io/commands/xread](https://redis.io/docs/latest/commands/xread/) | 블로킹 읽기, 폴링 |
| **XREADGROUP** | [redis.io/commands/xreadgroup](https://redis.io/docs/latest/commands/xreadgroup/) | Consumer Group |
| **XRANGE** | [redis.io/commands/xrange](https://redis.io/docs/latest/commands/xrange/) | 범위 조회, 리플레이 |

### 설계 원문

| 자료 | 저자 | URL |
|------|------|-----|
| **Streams: A New General Purpose Data Structure** | Salvatore Sanfilippo (antirez) | [antirez.com/news/114](http://antirez.com/news/114) |
| **Kafka vs Redis Streams** | Redis Labs | [redis.com/blog/...](https://redis.com/blog/understanding-redis-5-0/) |

### 학술/이론적 배경

| 자료 | 저자 | 핵심 개념 |
|------|------|---------|
| **The Log** | Jay Kreps (LinkedIn) | Append-only 로그 = 분산 시스템의 핵심 추상화 |
| **Designing Data-Intensive Applications** | Martin Kleppmann | Log-based Message Brokers (Ch.11) |

---

## 핵심 개념

### 1. Stream = Append-Only Log

```
┌─────────────────────────────────────────────────────────────────┐
│  Stream: scan:events:abc123                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Entry ID (ms-seq)     Fields                                    │
│  ──────────────────    ──────────────────────────────           │
│  1735123456789-0       {stage: "vision", status: "started"}     │
│  1735123456890-0       {stage: "vision", status: "completed"}   │
│  1735123457001-0       {stage: "rule",   status: "started"}     │
│  1735123457123-0       {stage: "rule",   status: "completed"}   │
│  ...                                                             │
│                                                                  │
│  ← 시간순 정렬, 불변, ID = 밀리초-시퀀스                          │
└─────────────────────────────────────────────────────────────────┘
```

**Kafka와의 유사성:**
- Append-only, 시간순 정렬
- Entry ID ≈ Kafka offset
- Consumer Group ≈ Kafka Consumer Group

**차이점:**
- 단일 노드 (Cluster Mode 가능하지만 파티션 개념 없음)
- 메모리 기반 (RDB/AOF 영속화)
- 더 단순한 API

---

### 2. Entry ID 구조

```
1735123456789-0
│             │
│             └── 시퀀스 (같은 밀리초 내 순서)
└──────────────── 밀리초 타임스탬프

특수 ID:
  0             : Stream의 처음부터
  $             : 현재 마지막 이후부터 (새 이벤트만)
  >             : Consumer Group에서 아직 전달되지 않은 것만
```

---

### 3. 핵심 명령어

#### XADD: 이벤트 발행

```redis
XADD scan:events:abc123 MAXLEN ~50 * stage vision status started
│                        │          │ └── 필드들 (key-value 쌍)
│                        │          └── * = 자동 ID 생성
│                        └── 대략 50개 유지 (효율적 trim)
└── Stream 키
```

Python:
```python
redis.xadd(
    "scan:events:abc123",
    {"stage": "vision", "status": "started"},
    maxlen=50,
)
```

#### XREAD: 블로킹 읽기

```redis
XREAD BLOCK 5000 STREAMS scan:events:abc123 0
│           │            │                  └── 시작 ID (0 = 처음부터)
│           │            └── Stream 키
│           └── 5000ms 블로킹
└── 블로킹 읽기 (새 이벤트 대기)
```

Python (async):
```python
events = await redis.xread(
    {"scan:events:abc123": "0"},
    block=5000,
    count=10,
)
```

#### XRANGE: 범위 조회 (리플레이)

```redis
XRANGE scan:events:abc123 - +
│                         │ └── + = 마지막까지
│                         └── - = 처음부터
└── Stream 전체 조회
```

---

### 4. Consumer Group

```
┌─────────────────────────────────────────────────────────────────┐
│  Consumer Group 구조                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stream: mystream                                                │
│  ├── Entry 1 ──┬── Consumer Group: sse-consumers                │
│  ├── Entry 2   │       ├── Consumer A: last_id = 1-0            │
│  ├── Entry 3   │       ├── Consumer B: last_id = 2-0            │
│  ├── Entry 4   │       └── PEL (Pending Entry List)             │
│  └── ...      │             └── Entry 3 → Consumer A (미확인)   │
│               │                                                  │
│               └── Consumer Group: analytics                     │
│                       └── Consumer C: last_id = 4-0             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**핵심 개념:**
- **Consumer Group**: 동일한 Stream을 여러 Consumer가 분산 처리
- **PEL (Pending Entry List)**: 전달되었으나 ACK되지 않은 항목
- **XACK**: Consumer가 처리 완료를 확인

```redis
# 그룹 생성
XGROUP CREATE mystream sse-consumers $ MKSTREAM

# 그룹으로 읽기 (미전달 항목만)
XREADGROUP GROUP sse-consumers consumer-a STREAMS mystream >

# 처리 완료 확인
XACK mystream sse-consumers 1735123456789-0
```

---

## Eco² 적용: SSE 이벤트 소싱

### 문제 상황

[#13 SSE 병목 분석](../blogs/async/23-sse-bottleneck-analysis-50vu.md)에서 발견:

```
SSE 연결당 RabbitMQ 연결 = 1:21 비율 → 연결 폭발
50 VU 테스트 시 341개 RabbitMQ 연결 → 503 에러
```

### 해결: Redis Streams로 전환

```
┌─────────────────────────────────────────────────────────────────┐
│  변경 전: Celery Events (RabbitMQ)                               │
│                                                                  │
│  SSE ──→ Celery Event Receiver ──→ RabbitMQ                     │
│               │                                                  │
│               └── SSE당 ~21개 연결 폭발                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  변경 후: Redis Streams                                          │
│                                                                  │
│  Worker ──XADD──→ Redis Stream ──XREAD──→ scan-api ──SSE──→ Client│
│                                                                  │
│  scan-api당 Redis 연결 1개 (상수)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 구현 패턴

```python
# 1. Worker: 이벤트 발행 (동기)
def publish_stage_event(redis, job_id, stage, status):
    redis.xadd(
        f"scan:events:{job_id}",
        {"stage": stage, "status": status, "ts": str(time.time())},
        maxlen=50,  # retention
    )
    redis.expire(f"scan:events:{job_id}", 3600)  # TTL

# 2. API: 이벤트 구독 (비동기 SSE)
async def subscribe_events(redis, job_id):
    last_id = "0"  # 처음부터 (리플레이 지원)
    
    while True:
        events = await redis.xread(
            {f"scan:events:{job_id}": last_id},
            block=5000,
        )
        
        if not events:
            yield {"type": "keepalive"}
            continue
        
        for _, messages in events:
            for msg_id, data in messages:
                last_id = msg_id
                yield data
                
                if data.get("stage") == "done":
                    return
```

### 핵심 원칙: "구독 먼저, 발행 나중"

```python
async def classify_completion(payload):
    job_id = str(uuid.uuid4())
    
    async def generate():
        # 1. 구독 시작 (이벤트 누락 방지)
        async for event in subscribe_events(redis, job_id):
            yield format_sse(event)
    
    # 2. Chain 발행 (구독 후)
    background_tasks.add_task(
        lambda: chain.apply_async(task_id=job_id)
    )
    
    return StreamingResponse(generate())
```

---

## Kafka vs Redis Streams vs RabbitMQ

| 특성 | Kafka | Redis Streams | RabbitMQ |
|------|-------|---------------|----------|
| **설계 철학** | 분산 로그 | 인메모리 로그 | 메시지 큐 |
| **메시지 모델** | Log (offset) | Log (entry ID) | Queue (ACK) |
| **Consumer 패턴** | 각자 offset 관리 | XREAD / Consumer Group | Competing Consumers |
| **영속성** | 디스크 기본 | 메모리 (AOF 옵션) | 디스크 옵션 |
| **확장성** | 파티션 기반 | 단일 노드 (Cluster 가능) | 클러스터 |
| **지연 시간** | 수 ms | 수 us | 수 ms |
| **적합 용도** | 대용량 이벤트 스트림 | 실시간 이벤트, 캐시 겸용 | 작업 큐, RPC |

### Eco² 선택 근거

```
✅ Redis Streams 선택 이유:
  - 이미 Redis 사용 중 (캐시, Celery 결과)
  - 저지연 실시간 이벤트 (SSE)
  - 단순한 운영 (Kafka 대비)
  - job당 수십 개 이벤트 (대용량 아님)

❌ Kafka 미선택 이유:
  - 추가 인프라 복잡도
  - 작은 규모에 과도함
  - Eco² 요구사항에 비해 오버엔지니어링
```

---

## 운영 고려사항

### 1. Retention 정책

```yaml
# Stream별 MAXLEN
XADD ... MAXLEN ~50 ...   # 대략 50개 유지 (효율적)
XADD ... MAXLEN 50 ...    # 정확히 50개 유지 (느림)

# TTL (스트림 전체 만료)
EXPIRE scan:events:abc123 3600   # 1시간 후 삭제
```

### 2. 메모리 정책 분리

```yaml
# 캐시 Redis (db=0): LRU eviction 허용
maxmemory-policy: allkeys-lru

# Streams Redis (db=1): eviction 금지
maxmemory-policy: noeviction
```

**이유**: Streams에서 eviction 발생 시 이벤트 유실 → UX 깨짐

### 3. Consumer Group 활용 (수평 확장)

```
┌─────────────────────────────────────────────────────────────────┐
│  다중 SSE 서버 시나리오                                          │
│                                                                  │
│  Stream: scan:events:{job_id}                                   │
│       │                                                          │
│       ├──→ Consumer Group: sse-servers                          │
│       │         ├── sse-server-1 (pod-a)                        │
│       │         ├── sse-server-2 (pod-b)                        │
│       │         └── sse-server-3 (pod-c)                        │
│       │                                                          │
│       └── 각 서버가 담당 클라이언트에게 fan-out                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 관련 문서

### Eco² 구현

- [#13 SSE 50 VU 병목 분석](../blogs/async/23-sse-bottleneck-analysis-50vu.md)
- [#14 Redis Streams SSE 전환](../blogs/async/24-redis-streams-sse-migration.md)

### Foundations

- [03-amqp-protocol.md](./03-amqp-protocol.md) - RabbitMQ/AMQP 비교
- [05-event-loop-fundamentals.md](./05-event-loop-fundamentals.md) - 비동기 I/O 기초

### 외부 자료

- [The Log - Jay Kreps](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying)
- [Redis Streams Introduction](https://redis.io/docs/latest/develop/data-types/streams/)
- [antirez: Streams Design](http://antirez.com/news/114)

---

## 버전 정보

- 작성일: 2025-12-25
- Redis 버전: 7.0+
- 적용 대상: Eco² SSE Pipeline

