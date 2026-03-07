# Idempotent Consumer: 중복 메시지 처리 패턴

> **Part VII: 운영과 품질** | [← 13. Schema Evolution](./13-schema-evolution-versioning.md) | [인덱스](./00-index.md) | [15. Distributed Tracing →](./15-distributed-tracing-opentelemetry.md)

> 참고: [Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html) - Gregor Hohpe  
> 참고: [Microservices Patterns](https://microservices.io/patterns/communication-style/idempotent-consumer.html) - Chris Richardson

---

## 들어가며

분산 시스템에서 메시지는 **정확히 한 번(Exactly-Once)** 전달되기 어렵다. 네트워크 장애, Consumer 재시작, Broker 장애 등으로 같은 메시지가 **여러 번 전달(At-Least-Once)**될 수 있다.

```
┌─────────────────────────────────────────────────────────────┐
│                 메시지 중복 전달 시나리오                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시나리오 1: Ack 유실                                       │
│  ────────────────────                                       │
│  Kafka/RabbitMQ           Consumer                          │
│       │                      │                              │
│       │  1. 메시지 전달      │                              │
│       │ ──────────────────▶ │                              │
│       │                      │ 2. 처리 완료                 │
│       │                      │    (DB 저장)                 │
│       │  3. Ack              │                              │
│       │ ◀─────── X ───────── │  ← 네트워크 장애로 Ack 유실 │
│       │                      │                              │
│       │  4. Ack 없음 → 재전송│                              │
│       │ ──────────────────▶ │                              │
│       │                      │ 5. 또 처리 (중복!)          │
│       │                      │                              │
│                                                             │
│  시나리오 2: Consumer 재시작                                │
│  ────────────────────────                                   │
│  • 메시지 처리 중 Consumer 크래시                          │
│  • Offset 커밋 전이라 재시작 시 같은 메시지 다시 수신      │
│                                                             │
│  시나리오 3: Producer 재시도                                │
│  ────────────────────────                                   │
│  • Producer가 타임아웃으로 재전송                          │
│  • 실제로는 첫 번째 전송이 성공했을 수 있음                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

결과: **같은 메시지로 포인트가 두 번 지급되거나, 같은 주문이 두 번 처리됨**

해결책은 **멱등성(Idempotency)**: 같은 연산을 여러 번 수행해도 결과가 같아야 한다.

---

## 멱등성의 정의

### 수학적 정의

```
f(f(x)) = f(x)
```

같은 함수를 여러 번 적용해도 결과가 변하지 않음.

### 실제 예시

```
┌─────────────────────────────────────────────────────────────┐
│              멱등 vs 비멱등 연산                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ 멱등 연산 (Idempotent):                                 │
│  ───────────────────────                                    │
│  • "주문 #123의 상태를 '완료'로 변경"                       │
│    1회: 진행중 → 완료                                       │
│    2회: 완료 → 완료  (결과 동일)                           │
│                                                             │
│  • "사용자 #456의 이메일을 'a@b.com'으로 설정"              │
│    1회: null → a@b.com                                      │
│    2회: a@b.com → a@b.com  (결과 동일)                     │
│                                                             │
│  • DELETE /users/123                                        │
│    1회: 삭제됨                                              │
│    2회: 이미 없음 (결과 동일)                              │
│                                                             │
│  ❌ 비멱등 연산 (Non-Idempotent):                           │
│  ─────────────────────────                                  │
│  • "잔액에 1000원 추가"                                    │
│    1회: 5000 → 6000                                        │
│    2회: 6000 → 7000  (결과 다름!)                          │
│                                                             │
│  • "재고 1개 차감"                                          │
│    1회: 10 → 9                                             │
│    2회: 9 → 8  (결과 다름!)                                │
│                                                             │
│  • POST /orders (새 주문 생성)                             │
│    1회: 주문 #1 생성                                       │
│    2회: 주문 #2 생성  (중복 주문!)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 구현 패턴

### 1. Natural Idempotency (자연적 멱등)

연산 자체가 멱등하도록 설계:

```
┌─────────────────────────────────────────────────────────────┐
│               Natural Idempotency                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ❌ 비멱등 설계:                                            │
│  "포인트 100 추가"                                          │
│                                                             │
│  UPDATE users SET points = points + 100 WHERE id = ?       │
│  → 실행할 때마다 100씩 증가                                │
│                                                             │
│  ✅ 멱등 설계:                                              │
│  "event_id=abc로 포인트를 6000으로 설정"                   │
│                                                             │
│  UPDATE users                                               │
│  SET points = 6000,                                         │
│      last_event_id = 'abc'                                 │
│  WHERE id = ? AND (last_event_id IS NULL                   │
│                    OR last_event_id != 'abc')              │
│  → 같은 event_id로는 한 번만 적용                          │
│                                                             │
│  또는 INSERT ... ON CONFLICT DO NOTHING:                   │
│  INSERT INTO point_grants (event_id, user_id, amount)      │
│  VALUES ('abc', 123, 100)                                  │
│  ON CONFLICT (event_id) DO NOTHING                         │
│  → event_id가 같으면 무시                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. Idempotency Key 패턴

클라이언트가 고유 키를 생성하여 전달:

```
┌─────────────────────────────────────────────────────────────┐
│                 Idempotency Key Pattern                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Producer                          Consumer                 │
│  ┌─────────────────────┐          ┌─────────────────────┐  │
│  │ {                   │          │                     │  │
│  │   "idempotency_key":│ ───────▶ │ 1. key 존재 확인   │  │
│  │     "scan-abc-v1",  │          │                     │  │
│  │   "user_id": 123,   │          │ 2. 없으면 처리     │  │
│  │   "points": 100     │          │                     │  │
│  │ }                   │          │ 3. key 저장        │  │
│  └─────────────────────┘          │                     │  │
│                                    │ 4. 있으면 무시     │  │
│                                    └─────────────────────┘  │
│                                                             │
│  Key 구성 예시:                                             │
│  • "{event_type}-{aggregate_id}-{version}"                 │
│  • "{task_id}-{step}"                                      │
│  • "{user_id}-{date}-{action}"                             │
│                                                             │
│  주의: Key는 비즈니스적으로 유일해야 함                    │
│  • ❌ UUID만 사용 → 재시도 시 다른 UUID 생성              │
│  • ✅ 비즈니스 ID 조합 → 같은 작업은 같은 Key             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. Inbox Pattern (메시지 추적 테이블)

수신한 모든 메시지를 DB에 기록:

```
┌─────────────────────────────────────────────────────────────┐
│                    Inbox Pattern                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  메시지 수신 → Inbox 테이블 확인 → 처리 → Inbox 저장       │
│                                                             │
│  Inbox Table:                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ message_id │ event_type │ processed_at │ status    │   │
│  ├────────────┼────────────┼──────────────┼───────────┤   │
│  │ evt-001    │ scan.done  │ 2025-12-19   │ COMPLETED │   │
│  │ evt-002    │ scan.done  │ 2025-12-19   │ COMPLETED │   │
│  │ evt-003    │ scan.done  │ NULL         │ PENDING   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  처리 로직:                                                 │
│  async def handle(message):                                │
│      # 1. Inbox 확인 (SELECT FOR UPDATE)                   │
│      existing = await inbox.get(message.id)                │
│      if existing and existing.status == "COMPLETED":       │
│          return  # 이미 처리됨                             │
│                                                             │
│      # 2. Inbox에 PENDING으로 기록                         │
│      await inbox.insert(message.id, status="PENDING")      │
│                                                             │
│      # 3. 실제 비즈니스 로직 실행                          │
│      await process_business_logic(message)                 │
│                                                             │
│      # 4. COMPLETED로 업데이트                             │
│      await inbox.update(message.id, status="COMPLETED")    │
│                                                             │
│  장점: 완전한 추적, 재처리 가능                            │
│  단점: DB 오버헤드, 테이블 관리 필요                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4. Deduplication Window (시간 기반 중복 제거)

일정 시간 동안만 중복 체크:

```
┌─────────────────────────────────────────────────────────────┐
│               Deduplication Window                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Redis TTL 사용:                                            │
│                                                             │
│  async def handle(message):                                │
│      key = f"processed:{message.id}"                       │
│                                                             │
│      # SETNX: 없으면 설정, 있으면 실패                     │
│      is_new = await redis.setnx(key, "1")                  │
│      if not is_new:                                        │
│          return  # 이미 처리됨                             │
│                                                             │
│      # TTL 설정 (24시간)                                   │
│      await redis.expire(key, 86400)                        │
│                                                             │
│      # 비즈니스 로직                                       │
│      await process(message)                                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Redis                                              │   │
│  │  ┌────────────────────────────────────────────────┐│   │
│  │  │ processed:evt-001 = "1"  TTL: 86400s          ││   │
│  │  │ processed:evt-002 = "1"  TTL: 85000s          ││   │
│  │  │ processed:evt-003 = "1"  TTL: 80000s          ││   │
│  │  │                                                ││   │
│  │  │ → 24시간 후 자동 삭제                         ││   │
│  │  └────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  장점: 빠름, 메모리 효율적 (TTL로 자동 정리)              │
│  단점: TTL 후 같은 메시지 재처리 가능                     │
│        → 정상 상황에서는 문제 없음 (재전송은 빠르게 발생) │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 저장소 선택

### 비교표

| 저장소 | 속도 | 영속성 | 용량 | 사용 사례 |
|--------|------|--------|------|----------|
| **Redis TTL** | ⚡ 매우 빠름 | ❌ 휘발 | 제한적 | 단기 중복 제거 |
| **DB 테이블** | 보통 | ✅ 영구 | 무제한 | 완전한 추적 필요 |
| **Bloom Filter** | ⚡ 빠름 | ❌ 휘발 | 매우 작음 | 대용량, 거짓 양성 허용 |

### Redis TTL (권장: 대부분의 경우)

```python
class RedisIdempotencyStore:
    def __init__(self, redis: Redis, ttl: int = 86400):
        self.redis = redis
        self.ttl = ttl  # 기본 24시간
    
    async def is_processed(self, message_id: str) -> bool:
        """이미 처리된 메시지인지 확인"""
        return await self.redis.exists(f"processed:{message_id}")
    
    async def mark_processed(self, message_id: str) -> bool:
        """처리 완료 표시 (원자적 연산)"""
        key = f"processed:{message_id}"
        # SETNX + EXPIRE를 원자적으로 수행
        result = await self.redis.set(key, "1", nx=True, ex=self.ttl)
        return result is not None  # True면 새로 설정됨
```

### DB 테이블 (권장: 감사/추적 필요 시)

```python
# 테이블 정의
"""
CREATE TABLE processed_events (
    event_id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    aggregate_id VARCHAR(255),
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processor VARCHAR(255),  -- 어떤 Consumer가 처리했는지
    
    INDEX idx_aggregate (aggregate_id),
    INDEX idx_processed_at (processed_at)
);
"""

class DBIdempotencyStore:
    async def check_and_mark(self, event_id: str, event_type: str) -> bool:
        """확인과 마킹을 원자적으로 수행"""
        try:
            await self.db.execute("""
                INSERT INTO processed_events (event_id, event_type, processor)
                VALUES (:event_id, :event_type, :processor)
            """, {
                "event_id": event_id,
                "event_type": event_type,
                "processor": self.consumer_id,
            })
            return True  # 새로 삽입됨 → 처리 필요
        except UniqueViolationError:
            return False  # 이미 존재 → 중복
```

### Bloom Filter (대용량 + 거짓 양성 허용)

```python
from pybloom_live import BloomFilter

class BloomIdempotencyStore:
    """
    확률적 자료구조: "없음"은 확실, "있음"은 불확실
    
    거짓 양성(False Positive): 실제로 없는데 있다고 판단
    → 일부 메시지가 중복으로 잘못 판단되어 무시될 수 있음
    → 중요하지 않은 대용량 처리에 적합
    """
    
    def __init__(self, capacity: int = 10_000_000, error_rate: float = 0.001):
        self.bloom = BloomFilter(capacity=capacity, error_rate=error_rate)
    
    def is_probably_processed(self, message_id: str) -> bool:
        return message_id in self.bloom
    
    def mark_processed(self, message_id: str):
        self.bloom.add(message_id)
```

---

## Idempotency Key 설계

### 좋은 Key의 조건

```
┌─────────────────────────────────────────────────────────────┐
│               Idempotency Key 설계 원칙                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 비즈니스적으로 유일해야 함                              │
│  ─────────────────────────────                              │
│  같은 비즈니스 작업은 같은 Key를 생성해야 함               │
│                                                             │
│  ❌ 나쁜 예:                                                │
│  key = str(uuid.uuid4())  # 재시도마다 다른 Key            │
│                                                             │
│  ✅ 좋은 예:                                                │
│  key = f"{event_type}:{aggregate_id}:{event_version}"      │
│  key = f"scan:{task_id}:completed"                         │
│  key = f"reward:{user_id}:{scan_id}"                       │
│                                                             │
│  2. 충돌을 피해야 함                                        │
│  ─────────────────────                                      │
│  다른 비즈니스 작업이 같은 Key를 생성하면 안 됨            │
│                                                             │
│  ❌ 나쁜 예:                                                │
│  key = f"{user_id}"  # 같은 사용자의 모든 이벤트가 충돌    │
│                                                             │
│  ✅ 좋은 예:                                                │
│  key = f"{event_type}:{user_id}:{timestamp_ms}"            │
│                                                             │
│  3. 추적 가능해야 함                                        │
│  ─────────────────────                                      │
│  Key만 보고 어떤 작업인지 알 수 있어야 디버깅 용이         │
│                                                             │
│  ❌ 나쁜 예:                                                │
│  key = "abc123def456"  # 무슨 작업인지 모름                │
│                                                             │
│  ✅ 좋은 예:                                                │
│  key = "scan.completed:task-abc:user-123:v2"               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key 구성 패턴

| 패턴 | 예시 | 사용 사례 |
|------|------|----------|
| **Event 기반** | `{event_id}` | CloudEvents 사용 시 |
| **Aggregate 기반** | `{aggregate_id}:{version}` | Event Sourcing |
| **작업 기반** | `{task_id}:{step}` | Saga/Pipeline |
| **사용자 기반** | `{user_id}:{action}:{date}` | 일일 제한 |
| **복합** | `{type}:{aggregate}:{event_id}` | 범용 |

---

## 트랜잭션과의 통합

### 문제: 처리 완료 후 마킹 전 크래시

```
┌─────────────────────────────────────────────────────────────┐
│              트랜잭션 경계 문제                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ❌ 문제 있는 구현:                                         │
│                                                             │
│  async def handle(message):                                │
│      if await store.is_processed(message.id):              │
│          return                                             │
│                                                             │
│      await db.execute("UPDATE ...")  # 1. 비즈니스 로직    │
│      # ← 여기서 크래시하면?                                │
│      await store.mark_processed(message.id)  # 2. 마킹     │
│                                                             │
│  → 비즈니스 로직은 실행됐는데 마킹 안 됨                   │
│  → 재시작 시 또 실행됨 (중복!)                             │
│                                                             │
│  ✅ 해결: 같은 트랜잭션에서 처리                           │
│                                                             │
│  async def handle(message):                                │
│      async with db.begin() as tx:                          │
│          # 같은 트랜잭션에서 체크 + 마킹 + 비즈니스 로직   │
│          result = await tx.execute("""                     │
│              INSERT INTO processed_events (event_id)       │
│              VALUES (:id) ON CONFLICT DO NOTHING           │
│              RETURNING event_id                            │
│          """, {"id": message.id})                          │
│                                                             │
│          if not result:                                    │
│              return  # 이미 처리됨                         │
│                                                             │
│          await tx.execute("UPDATE ...")  # 비즈니스 로직   │
│          # 트랜잭션 커밋 시 둘 다 적용                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 참고 자료

- [Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html) - Enterprise Integration Patterns
- [Handling Duplicate Messages](https://microservices.io/patterns/communication-style/idempotent-consumer.html) - Chris Richardson
- [Exactly-once Semantics in Kafka](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/) - Confluent

---

## 부록: Eco² 적용 포인트

### Character 보상 중복 지급 방지

```
┌─────────────────────────────────────────────────────────────┐
│           Eco² Character 보상 Idempotency                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시나리오:                                                  │
│  • ScanCompleted 이벤트 → Character 보상 지급              │
│  • 같은 스캔으로 보상이 두 번 지급되면 안 됨               │
│                                                             │
│  Idempotency Key 설계:                                      │
│  key = f"reward:{scan_task_id}:{user_id}"                  │
│                                                             │
│  • scan_task_id: 어떤 스캔인지                             │
│  • user_id: 누구에게 지급하는지                            │
│  • 같은 스캔 + 같은 사용자 = 같은 Key                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Kafka Consumer 구현

```python
# domains/character/consumers/event_consumer.py

class CharacterEventConsumer:
    def __init__(self):
        self.idempotency_store = RedisIdempotencyStore(
            redis=redis_client,
            ttl=86400 * 7,  # 7일
        )
    
    async def handle_scan_completed(self, event: dict):
        """ScanCompleted 이벤트 처리 (멱등)"""
        
        # 1. Idempotency Key 생성
        idempotency_key = self._build_key(event)
        
        # 2. 이미 처리되었는지 확인 + 마킹 (원자적)
        is_new = await self.idempotency_store.mark_processed(idempotency_key)
        if not is_new:
            logger.info(f"Duplicate event ignored: {idempotency_key}")
            return
        
        # 3. 비즈니스 로직 실행
        try:
            await self._grant_reward(event)
        except Exception as e:
            # 실패 시 마킹 제거 (재처리 가능하도록)
            await self.idempotency_store.remove(idempotency_key)
            raise
    
    def _build_key(self, event: dict) -> str:
        """Idempotency Key 생성"""
        event_id = event.get("id")  # CloudEvents id
        event_type = event.get("type")
        
        # CloudEvents id가 있으면 사용
        if event_id:
            return f"{event_type}:{event_id}"
        
        # 없으면 비즈니스 ID 조합
        task_id = event["data"]["task_id"]
        user_id = event["eco2userid"]
        return f"reward:{task_id}:{user_id}"
```

### processed_events 테이블 (감사 추적용)

```sql
-- 이벤트 처리 이력 테이블
CREATE TABLE processed_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    aggregate_id VARCHAR(255),
    aggregate_type VARCHAR(255),
    
    -- 추적 정보
    consumer_id VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 원본 이벤트 (디버깅용)
    event_payload JSONB,
    
    -- 인덱스
    INDEX idx_aggregate (aggregate_type, aggregate_id),
    INDEX idx_processed_at (processed_at),
    INDEX idx_event_type (event_type)
);

-- 오래된 레코드 정리 (7일 이상)
DELETE FROM processed_events 
WHERE processed_at < NOW() - INTERVAL '7 days';
```

### Celery Task Idempotency

```python
# domains/scan/tasks/ai_pipeline.py

@celery_app.task(bind=True, max_retries=3)
def process_image(self, task_id: str, image_url: str, idempotency_key: str):
    """AI 파이프라인 (멱등)"""
    
    # 1. 이미 처리되었는지 확인
    if redis.exists(f"celery:processed:{idempotency_key}"):
        logger.info(f"Task already processed: {idempotency_key}")
        return {"status": "already_processed"}
    
    try:
        # 2. 처리 시작 표시 (동시 실행 방지)
        acquired = redis.setnx(f"celery:processing:{idempotency_key}", "1")
        if not acquired:
            logger.info(f"Task already processing: {idempotency_key}")
            return {"status": "already_processing"}
        
        redis.expire(f"celery:processing:{idempotency_key}", 600)  # 10분 타임아웃
        
        # 3. AI 처리
        result = vision_api.analyze(image_url)
        answer = llm_api.generate(result)
        
        # 4. 완료 표시
        redis.setex(f"celery:processed:{idempotency_key}", 86400 * 7, "1")
        redis.delete(f"celery:processing:{idempotency_key}")
        
        return {"classification": result, "answer": answer}
        
    except Exception as exc:
        redis.delete(f"celery:processing:{idempotency_key}")
        raise self.retry(exc=exc)
```

### AS-IS vs TO-BE

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-----------------------------------|
| **중복 방지** | 클라이언트 책임 | Consumer Idempotency |
| **저장소** | 없음 | Redis TTL + DB 추적 |
| **Key 설계** | 없음 | CloudEvents id + 비즈니스 ID |
| **트랜잭션** | gRPC 단위 | DB 트랜잭션 내 체크+마킹 |
| **재시도** | Circuit Breaker | Idempotent 재처리 |
| **추적** | 로그만 | processed_events 테이블 |
