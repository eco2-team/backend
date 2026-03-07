# Transactional Outbox: 이중 쓰기 문제의 해결

> **Part VI: 이벤트 발행** | [← 07. Sagas](./07-sagas-garcia-molina.md) | [인덱스](./00-index.md) | [09. Debezium →](./09-debezium-outbox-event-router.md)

> 원문: [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html) - Chris Richardson (microservices.io)  
> 참고: [Microservices Patterns](https://www.manning.com/books/microservices-patterns) - Chris Richardson (Manning, 2018)  
> 참고: [Designing Data-Intensive Applications](https://dataintensive.net/) - Martin Kleppmann (O'Reilly, 2017)

---

## 들어가며

마이크로서비스 아키텍처에서 가장 까다로운 문제 중 하나: **데이터베이스 업데이트와 메시지 발행을 어떻게 원자적으로 처리할 것인가?**

Chris Richardson이 그의 책 "Microservices Patterns"에서 공식화한 **Transactional Outbox** 패턴은 이 문제에 대한 우아한 해결책을 제시한다. 이 패턴은 Pat Helland의 Entity 개념, Garcia-Molina의 Saga, 그리고 Jay Kreps의 Log 철학이 만나는 교차점이다.

---

## Dual Write Problem: 이중 쓰기 문제

### 문제의 본질

서비스가 데이터베이스를 업데이트하고 이벤트를 발행해야 하는 상황:

```
┌─────────────────────────────────────────────────────────────┐
│                   Dual Write Problem                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Order Service                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ async def create_order(order_data):                  │   │
│  │     # 1. 데이터베이스에 주문 저장                    │   │
│  │     await db.execute(                                │   │
│  │         "INSERT INTO orders ..."                     │   │
│  │     )                                                │   │
│  │                                                     │   │
│  │     # 2. 메시지 브로커에 이벤트 발행                 │   │
│  │     await message_broker.publish(                    │   │
│  │         "order.created",                            │   │
│  │         OrderCreatedEvent(order_id)                 │   │
│  │     )                                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  문제: 두 작업이 "원자적"이지 않음!                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 실패 시나리오

```
┌─────────────────────────────────────────────────────────────┐
│                     실패 시나리오                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시나리오 1: DB 성공, 메시지 실패                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. DB INSERT ✓ (주문 저장됨)                        │   │
│  │ 2. Message Broker ✗ (네트워크 장애)                 │   │
│  │                                                     │   │
│  │ 결과: 주문은 있는데 다른 서비스는 모름              │   │
│  │       → 재고 차감 안 됨, 결제 안 됨                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  시나리오 2: DB 성공, 서비스 크래시                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. DB INSERT ✓                                      │   │
│  │ 2. --- 서비스 크래시 ---                            │   │
│  │ 3. Message Broker (실행 안 됨)                      │   │
│  │                                                     │   │
│  │ 결과: 동일 - 이벤트 유실                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  시나리오 3: 메시지 성공, DB 실패                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. DB INSERT 시도 중... 타임아웃                    │   │
│  │ 2. 재시도 로직에서 메시지 먼저 발행?                │   │
│  │                                                     │   │
│  │ 결과: 주문 없는데 이벤트 발행됨                     │   │
│  │       → 존재하지 않는 주문에 대해 처리 시도         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  → 어떤 순서로 해도 불일치 가능!                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 분산 트랜잭션? No!

2PC로 해결하면 되지 않나?

```
┌─────────────────────────────────────────────────────────────┐
│            2PC가 해결책이 아닌 이유                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 메시지 브로커가 XA 트랜잭션을 지원해야 함               │
│     → RabbitMQ: 지원 안 함                                 │
│     → Kafka: 지원 안 함                                    │
│     → AWS SQS: 지원 안 함                                  │
│                                                             │
│  2. Pat Helland의 통찰:                                     │
│     "무한 확장 시스템에서 분산 트랜잭션은 불가능"           │
│                                                             │
│  3. 성능 문제:                                              │
│     2PC는 느리고 가용성을 해침                              │
│                                                             │
│  → 다른 접근법이 필요!                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Transactional Outbox 패턴

### 핵심 아이디어

**메시지를 직접 발행하지 말고, 데이터베이스의 Outbox 테이블에 저장하라.**

```
┌─────────────────────────────────────────────────────────────┐
│               Transactional Outbox 개념                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Order Service                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  BEGIN TRANSACTION                                  │   │
│  │                                                     │   │
│  │    1. INSERT INTO orders (...)                      │   │
│  │       → 주문 데이터 저장                            │   │
│  │                                                     │   │
│  │    2. INSERT INTO outbox (                          │   │
│  │         event_type, payload, ...                    │   │
│  │       )                                              │   │
│  │       → 이벤트를 DB에 저장                          │   │
│  │                                                     │   │
│  │  COMMIT                                             │   │
│  │                                                     │   │
│  │  → 두 INSERT가 같은 트랜잭션!                       │   │
│  │  → 둘 다 성공하거나 둘 다 실패                      │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  별도 프로세스 (Message Relay):                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. SELECT * FROM outbox WHERE published = false    │   │
│  │  2. 각 레코드를 Message Broker에 발행              │   │
│  │  3. UPDATE outbox SET published = true             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Outbox 테이블 스키마

```sql
-- Outbox 테이블 정의
CREATE TABLE outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 이벤트 메타데이터
    aggregate_type  VARCHAR(255) NOT NULL,  -- 'Order', 'Payment', ...
    aggregate_id    VARCHAR(255) NOT NULL,  -- 주문 ID, 결제 ID, ...
    event_type      VARCHAR(255) NOT NULL,  -- 'OrderCreated', 'PaymentProcessed', ...
    
    -- 이벤트 페이로드
    payload         JSONB NOT NULL,         -- 이벤트 데이터
    
    -- 발행 상태
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at    TIMESTAMP,
    
    -- 인덱스
    INDEX idx_outbox_unpublished (created_at) WHERE published_at IS NULL
);
```

### 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│              Transactional Outbox 아키텍처                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Order Service                                              │
│  ┌──────────────────────────────────────────┐              │
│  │  ┌────────────┐                          │              │
│  │  │ API Layer  │                          │              │
│  │  └─────┬──────┘                          │              │
│  │        │                                 │              │
│  │        ▼                                 │              │
│  │  ┌────────────────────────────────────┐ │              │
│  │  │         Transaction                 │ │              │
│  │  │  ┌──────────────┐ ┌──────────────┐ │ │              │
│  │  │  │    orders    │ │    outbox    │ │ │              │
│  │  │  │    table     │ │    table     │ │ │              │
│  │  │  └──────────────┘ └──────────────┘ │ │              │
│  │  └────────────────────────────────────┘ │              │
│  └──────────────────────────────────────────┘              │
│                          │                                  │
│                          │ 폴링 또는 CDC                    │
│                          ▼                                  │
│  ┌──────────────────────────────────────────┐              │
│  │           Message Relay                   │              │
│  │  (Polling Publisher 또는 Debezium CDC)   │              │
│  └─────────────────────┬────────────────────┘              │
│                        │                                    │
│                        ▼                                    │
│  ┌──────────────────────────────────────────┐              │
│  │           Message Broker                  │              │
│  │         (Kafka / RabbitMQ)               │              │
│  └─────────────────────┬────────────────────┘              │
│                        │                                    │
│           ┌────────────┼────────────┐                      │
│           ▼            ▼            ▼                      │
│      ┌─────────┐ ┌─────────┐ ┌─────────┐                  │
│      │Inventory│ │ Payment │ │Analytics│                  │
│      │ Service │ │ Service │ │ Service │                  │
│      └─────────┘ └─────────┘ └─────────┘                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Message Relay 구현 방식

Chris Richardson은 두 가지 구현 방식을 제시한다:

### 1. Polling Publisher

주기적으로 Outbox 테이블을 폴링:

```
┌─────────────────────────────────────────────────────────────┐
│                   Polling Publisher                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ while True:                                          │   │
│  │     # 1. 미발행 이벤트 조회                          │   │
│  │     events = db.query("""                            │   │
│  │         SELECT * FROM outbox                         │   │
│  │         WHERE published_at IS NULL                   │   │
│  │         ORDER BY created_at                          │   │
│  │         LIMIT 100                                    │   │
│  │         FOR UPDATE SKIP LOCKED                       │   │
│  │     """)                                             │   │
│  │                                                     │   │
│  │     for event in events:                            │   │
│  │         # 2. 메시지 브로커에 발행                    │   │
│  │         broker.publish(event.event_type, event.payload)   │
│  │                                                     │   │
│  │         # 3. 발행 완료 표시                          │   │
│  │         db.execute("""                               │   │
│  │             UPDATE outbox                            │   │
│  │             SET published_at = NOW()                 │   │
│  │             WHERE id = :id                           │   │
│  │         """, {"id": event.id})                       │   │
│  │                                                     │   │
│  │     sleep(POLL_INTERVAL)  # 예: 500ms               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  장점:                                                      │
│  • 구현이 단순함                                            │
│  • 특별한 인프라 불필요                                     │
│                                                             │
│  단점:                                                      │
│  • 지연시간 (폴링 간격)                                     │
│  • DB 부하 (반복 쿼리)                                      │
│  • 스케일링 어려움                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. Transaction Log Tailing (CDC)

데이터베이스의 트랜잭션 로그를 직접 읽기:

```
┌─────────────────────────────────────────────────────────────┐
│              Transaction Log Tailing (CDC)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PostgreSQL WAL                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LSN 0001: INSERT INTO orders (id=123, ...)          │   │
│  │ LSN 0002: INSERT INTO outbox (event_type=..., ...)  │   │
│  │ LSN 0003: COMMIT                                    │   │
│  │ LSN 0004: INSERT INTO orders (id=124, ...)          │   │
│  │ ...                                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          │ Debezium이 WAL 읽기             │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Debezium                          │   │
│  │                                                     │   │
│  │  1. WAL에서 outbox 테이블 변경 감지                 │   │
│  │  2. INSERT 이벤트를 Kafka 메시지로 변환             │   │
│  │  3. Outbox Event Router SMT로 라우팅               │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                     Kafka                            │   │
│  │                                                     │   │
│  │  Topic: order.events                                │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │ OrderCreated { order_id: 123, ... }         │   │   │
│  │  │ OrderCreated { order_id: 124, ... }         │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  장점:                                                      │
│  • 실시간에 가까운 지연시간                                 │
│  • DB 부하 최소화 (WAL은 이미 존재)                        │
│  • 높은 처리량                                              │
│                                                             │
│  단점:                                                      │
│  • 추가 인프라 필요 (Debezium, Kafka Connect)              │
│  • 복잡한 설정                                              │
│  • DB별 다른 구현 필요                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

이것이 바로 Jay Kreps가 "The Log"에서 말한 핵심이다:

> "데이터베이스의 트랜잭션 로그는 이미 모든 변경의 순서화된 기록이다. 이것을 활용하라."

---

## At-Least-Once와 Idempotent Consumer

### 중복 메시지 문제

Transactional Outbox는 **At-Least-Once Delivery**를 보장한다. 즉, 메시지가 최소 한 번은 전달되지만, 중복될 수 있다:

```
┌─────────────────────────────────────────────────────────────┐
│                 중복 전달 시나리오                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Polling Publisher:                                         │
│                                                             │
│  1. SELECT event FROM outbox WHERE ...                     │
│  2. broker.publish(event)  ✓ (발행 성공)                   │
│  3. UPDATE outbox SET published = true                     │
│     --- 여기서 크래시! ---                                  │
│                                                             │
│  재시작 후:                                                 │
│  1. SELECT event FROM outbox WHERE ...                     │
│     → 같은 이벤트 다시 조회됨 (published가 아직 false)     │
│  2. broker.publish(event)  ← 중복 발행!                    │
│                                                             │
│  CDC도 마찬가지:                                            │
│  • Debezium 커넥터 재시작 시 마지막 오프셋부터 재처리       │
│  • 오프셋 커밋 전 장애 시 중복 발행                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Idempotent Consumer

해결책: **소비자가 멱등성을 보장**

```
┌─────────────────────────────────────────────────────────────┐
│                  Idempotent Consumer                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Consumer Service                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ async def handle_order_created(event):               │   │
│  │                                                     │   │
│  │     # 1. 이미 처리된 이벤트인지 확인                 │   │
│  │     if await is_processed(event.event_id):          │   │
│  │         logger.info("Duplicate event, skipping")    │   │
│  │         return                                       │   │
│  │                                                     │   │
│  │     # 2. 비즈니스 로직 실행                          │   │
│  │     await reserve_inventory(event.order_id)          │   │
│  │                                                     │   │
│  │     # 3. 처리 완료 기록                              │   │
│  │     await mark_as_processed(event.event_id)         │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  처리 완료 기록 방법:                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 방법 1: DB 테이블                                    │   │
│  │   CREATE TABLE processed_events (                    │   │
│  │       event_id UUID PRIMARY KEY,                     │   │
│  │       processed_at TIMESTAMP                         │   │
│  │   )                                                  │   │
│  │                                                     │   │
│  │ 방법 2: Redis (TTL 활용)                             │   │
│  │   redis.setex(f"processed:{event_id}", 86400, "1")  │   │
│  │                                                     │   │
│  │ 방법 3: 자연 멱등성                                  │   │
│  │   UPDATE inventory SET reserved = true              │   │
│  │   WHERE order_id = :order_id                        │   │
│  │   → 여러 번 실행해도 결과 동일                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Martin Kleppmann: Stream Processing과의 연결

### DDIA의 통찰

Martin Kleppmann의 "Designing Data-Intensive Applications" Chapter 11에서 이 패턴을 더 넓은 맥락에서 설명한다:

```
┌─────────────────────────────────────────────────────────────┐
│          DDIA: Exactly-Once Semantics                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Delivery Guarantee 스펙트럼:                               │
│                                                             │
│  At-Most-Once    At-Least-Once    Exactly-Once             │
│  ────────────    ─────────────    ────────────             │
│  메시지 유실 가능   메시지 중복 가능    이상적이지만           │
│  처리 보장 없음    처리 보장 있음     구현 어려움            │
│                                                             │
│  Exactly-Once는 어떻게 달성하나?                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Exactly-Once = At-Least-Once + Idempotent Consumer │   │
│  │                                                     │   │
│  │  Outbox Pattern:    At-Least-Once 보장              │   │
│  │  Idempotent Key:    중복 처리 방지                  │   │
│  │  결과:             Exactly-Once 효과               │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Kleppmann의 조언:                                          │
│  "Exactly-Once를 추구하지 말고, 멱등성을 설계하라"          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Log-based Integration

Kleppmann은 데이터베이스와 메시징의 통합을 Log 관점에서 설명한다:

```
┌─────────────────────────────────────────────────────────────┐
│            Log as Unified Integration                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  전통적 방식 (Point-to-Point):                              │
│                                                             │
│  Service A ──────────────────▶ Service B                   │
│  (직접 API 호출)                                            │
│                                                             │
│  Log-based 방식:                                            │
│                                                             │
│  Service A ──▶ Log (Kafka) ──▶ Service B                   │
│                    │                                        │
│                    └──▶ Service C                          │
│                    │                                        │
│                    └──▶ Analytics                          │
│                                                             │
│  Outbox Pattern의 의미:                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  DB의 트랜잭션 로그 (WAL)                           │   │
│  │       ↓                                             │   │
│  │  CDC로 캡처                                         │   │
│  │       ↓                                             │   │
│  │  메시지 브로커의 로그 (Kafka Topic)                 │   │
│  │       ↓                                             │   │
│  │  모든 소비자가 같은 로그를 구독                     │   │
│  │                                                     │   │
│  │  → "Log로 시스템을 통합한다"                        │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 개념 정리

| 개념 | 설명 |
|------|------|
| **Dual Write Problem** | DB 업데이트와 메시지 발행의 원자성 문제 |
| **Transactional Outbox** | 이벤트를 같은 트랜잭션으로 DB에 저장 |
| **Polling Publisher** | 주기적으로 Outbox 폴링하여 발행 |
| **Transaction Log Tailing** | CDC로 DB 로그를 직접 읽어 발행 |
| **At-Least-Once Delivery** | 최소 1회 전달 보장 (중복 가능) |
| **Idempotent Consumer** | 중복 메시지를 안전하게 처리 |

---

## 더 읽을 자료

- [Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html) - Chris Richardson
- [DDIA Chapter 11: Stream Processing](https://dataintensive.net/) - Martin Kleppmann
- [Debezium Outbox Pattern](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html) - Red Hat

---

## 부록: Eco² 적용 포인트

### Scan 도메인 Outbox 테이블

```sql
-- domains/scan/migrations/create_outbox.sql

CREATE TABLE scan_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Aggregate 정보
    aggregate_type  VARCHAR(50) NOT NULL DEFAULT 'scan_task',
    aggregate_id    UUID NOT NULL,  -- task_id
    
    -- 이벤트 정보
    event_type      VARCHAR(100) NOT NULL,  -- ScanCompleted, RewardRequested, ...
    event_version   INTEGER NOT NULL DEFAULT 1,
    
    -- 페이로드
    payload         JSONB NOT NULL,
    
    -- 추적 정보
    trace_id        VARCHAR(64),  -- OpenTelemetry trace
    user_id         UUID,
    
    -- 발행 상태
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMP WITH TIME ZONE,
    
    -- 인덱스
    CONSTRAINT idx_scan_outbox_unpublished 
        CHECK (published_at IS NULL)
);

CREATE INDEX idx_scan_outbox_created 
    ON scan_outbox (created_at) 
    WHERE published_at IS NULL;
```

### 서비스 코드에서 Outbox 사용

```python
# domains/scan/services/scan.py

from sqlalchemy.orm import Session
from uuid import uuid4
import json

class ScanService:
    def __init__(self, db: Session):
        self.db = db
    
    async def complete_scan(
        self,
        task_id: str,
        user_id: str,
        classification_result: dict,
    ) -> ScanResult:
        """분류 완료 처리 (Transactional Outbox 패턴)"""
        
        # 단일 트랜잭션으로 처리
        async with self.db.begin():
            
            # 1. 스캔 결과 저장
            result = ScanResult(
                task_id=task_id,
                user_id=user_id,
                category=classification_result["category"],
                status="completed",
            )
            self.db.add(result)
            
            # 2. Outbox에 이벤트 저장 (같은 트랜잭션!)
            outbox_event = ScanOutbox(
                aggregate_id=task_id,
                event_type="ScanCompleted",
                payload=json.dumps({
                    "task_id": task_id,
                    "user_id": user_id,
                    "category": classification_result["category"],
                    "subcategory": classification_result.get("subcategory"),
                    "completed_at": datetime.utcnow().isoformat(),
                }),
                trace_id=get_current_trace_id(),
                user_id=user_id,
            )
            self.db.add(outbox_event)
            
            # 3. 보상 요청 이벤트도 Outbox에 저장
            reward_event = ScanOutbox(
                aggregate_id=task_id,
                event_type="RewardRequested",
                payload=json.dumps({
                    "task_id": task_id,
                    "user_id": user_id,
                    "category": classification_result["category"],
                    "points": self._calculate_points(classification_result),
                }),
                trace_id=get_current_trace_id(),
                user_id=user_id,
            )
            self.db.add(reward_event)
        
        # 트랜잭션 커밋 후, Polling Publisher 또는 CDC가 처리
        return result
```

### Polling Publisher 구현

```python
# domains/scan/tasks/outbox_publisher.py

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True)
def publish_outbox_events(self):
    """Outbox 이벤트를 메시지 브로커로 발행 (Polling)"""
    
    with db_session() as db:
        # 1. 미발행 이벤트 조회 (잠금으로 동시 처리 방지)
        events = db.execute("""
            SELECT * FROM scan_outbox
            WHERE published_at IS NULL
            ORDER BY created_at
            LIMIT 100
            FOR UPDATE SKIP LOCKED
        """).fetchall()
        
        published_count = 0
        
        for event in events:
            try:
                # 2. 메시지 브로커에 발행
                message_broker.publish(
                    topic=f"scan.{event.event_type.lower()}",
                    key=str(event.aggregate_id),
                    value=event.payload,
                    headers={
                        "event_type": event.event_type,
                        "trace_id": event.trace_id,
                        "event_id": str(event.id),
                    },
                )
                
                # 3. 발행 완료 표시
                db.execute("""
                    UPDATE scan_outbox
                    SET published_at = NOW()
                    WHERE id = :id
                """, {"id": event.id})
                
                published_count += 1
                
            except Exception as e:
                logger.error(f"Failed to publish event {event.id}: {e}")
                # 실패한 이벤트는 다음 폴링에서 재시도
        
        db.commit()
        
    logger.info(f"Published {published_count} events from outbox")
    return published_count


# Celery Beat 스케줄 설정
celery_app.conf.beat_schedule = {
    'publish-outbox-every-500ms': {
        'task': 'domains.scan.tasks.outbox_publisher.publish_outbox_events',
        'schedule': 0.5,  # 500ms
    },
}
```

### Idempotent Consumer 구현

```python
# domains/character/consumers/scan_events.py

from domains._shared.taskqueue.app import celery_app

PROCESSED_EVENTS_TTL = 86400  # 24시간


@celery_app.task(bind=True)
def handle_reward_requested(self, event_data: dict):
    """RewardRequested 이벤트 처리 (Idempotent)"""
    
    event_id = event_data.get("event_id")
    task_id = event_data["task_id"]
    user_id = event_data["user_id"]
    
    # 1. 중복 체크 (Idempotency)
    idempotency_key = f"reward:{task_id}:{user_id}"
    if redis.exists(f"processed:{idempotency_key}"):
        logger.info(f"Duplicate event {event_id}, skipping")
        return {"status": "duplicate"}
    
    # 2. 비즈니스 로직 실행
    try:
        character = await character_service.grant_reward(
            user_id=user_id,
            category=event_data["category"],
            points=event_data["points"],
        )
        
        # 3. 처리 완료 기록 (TTL로 자동 만료)
        redis.setex(
            f"processed:{idempotency_key}",
            PROCESSED_EVENTS_TTL,
            json.dumps({"character_id": str(character.id)}),
        )
        
        return {"status": "success", "character_id": str(character.id)}
        
    except Exception as e:
        logger.error(f"Failed to process reward: {e}")
        raise self.retry(exc=e, countdown=60)
```

### Chris Richardson 원칙의 Eco² 적용 (Command-Event Separation)

```
┌─────────────────────────────────────────────────────────────┐
│     Eco² Outbox + CDC (Command-Event Separation)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Scan Service                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  POST /scan/classify                                │   │
│  │       │                                             │   │
│  │       ├────────────────────┐                        │   │
│  │       │                    │                        │   │
│  │       ▼                    ▼                        │   │
│  │  Event Store           RabbitMQ                     │   │
│  │  (ScanCreated)         (AI Task)                    │   │
│  │       │                    │                        │   │
│  │       │ CDC                │ Celery                 │   │
│  │       ▼                    ▼                        │   │
│  │    Kafka              Vision/LLM                    │   │
│  │  (생성 이벤트)         Worker                       │   │
│  │                            │                        │   │
│  │                            │ 완료 시                │   │
│  │                            ▼                        │   │
│  │                       Event Store                   │   │
│  │                       (ScanCompleted)               │   │
│  │                            │                        │   │
│  │                            │ CDC                    │   │
│  │                            ▼                        │   │
│  │                         Kafka                       │   │
│  │                       (완료 이벤트)                 │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│           ┌──────────────┼──────────────┐                  │
│           ▼              ▼              ▼                  │
│     Character        My Service      Analytics             │
│     Consumer         Consumer        Consumer              │
│                                                             │
│  핵심: AI Task는 RabbitMQ, 도메인 이벤트는 Kafka           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Celery Task에서 Event Store 연동

```python
# domains/scan/tasks/ai_pipeline.py

@celery_app.task(bind=True, max_retries=3)
def answer_gen(self, prev_result: dict, task_id: str):
    """AI Task 완료 → Event Store에 이벤트 저장"""
    
    try:
        answer = llm_api.generate(prev_result)
        
        # Celery Task 완료 시 Event Store + Outbox에 저장
        async with db.begin():
            # 1. Event Store (Aggregate 재구성용)
            await db.execute("""
                INSERT INTO events (id, aggregate_id, event_type, event_data)
                VALUES (:id, :agg_id, 'ScanCompleted', :data)
            """, {...})
            
            # 2. Outbox (CDC → Kafka 발행용)
            await db.execute("""
                INSERT INTO outbox (id, aggregate_id, event_type, payload)
                VALUES (:id, :agg_id, 'ScanCompleted', :payload)
            """, {...})
        
        # COMMIT → Debezium CDC가 Kafka로 자동 발행
        # → Character Consumer가 보상 지급
        
        return answer
        
    except Exception as exc:
        raise self.retry(exc=exc)
```

### Kafka Consumer (Idempotent)

```python
# domains/character/consumers/event_consumer.py

class CharacterEventConsumer:
    """Kafka Consumer - 도메인 이벤트 처리"""
    
    async def handle(self, message: KafkaMessage):
        event_id = message.headers["event_id"]
        
        # DB 기반 멱등성 체크
        if await self.is_processed(event_id):
            return
        
        event = self.deserialize(message)
        
        async with self.db.begin():
            user_char = await self.event_store.load(
                UserCharacter, event.user_id
            )
            user_char.grant_reward(event.classification["category"])
            
            # Event Store + Outbox 저장 → CDC가 다시 Kafka로
            await self.event_store.save(user_char, user_char.collect_events())
            await self.mark_processed(event_id)
```

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-------------------|
| **Outbox 테이블** | 없음 | events + outbox |
| **발행 방식** | gRPC 직접 호출 | Debezium CDC |
| **AI 파이프라인** | gRPC 블로킹 | RabbitMQ + Celery |
| **도메인 이벤트** | 없음 | Kafka (CDC) |
| **At-Least-Once** | Circuit Breaker | Kafka Consumer + Celery DLQ |
| **Idempotent** | 없음 | processed_events 테이블 |
| **순서 보장** | 순차 호출 | Kafka Partition (aggregate_id) |
| **Event Replay** | 불가능 | Event Store에서 가능 |
