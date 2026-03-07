# Debezium Outbox Event Router: CDC 기반 이벤트 발행

> **Part VI: 이벤트 발행** | [← 08. Outbox](./08-transactional-outbox.md) | [인덱스](./00-index.md) | [10. DDD Aggregate →](./10-ddd-aggregate-eric-evans.md)

> 원문: [Reliable Microservices Data Exchange with the Outbox Pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/) - Gunnar Morling (Red Hat, 2019)  
> 문서: [Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)

---

## 들어가며

Chris Richardson이 Transactional Outbox 패턴을 이론화했다면, **Gunnar Morling**은 이를 **실제로 구현하는 방법**을 제시했다. Red Hat의 Debezium 프로젝트를 통해 CDC(Change Data Capture) 기반의 우아한 해결책을 만들어냈다.

이 문서는 Polling Publisher의 한계를 넘어, **데이터베이스의 트랜잭션 로그를 직접 활용**하는 방법을 다룬다.

---

## Polling Publisher의 한계

### 왜 CDC가 필요한가?

```
┌─────────────────────────────────────────────────────────────┐
│              Polling Publisher의 문제점                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 지연시간 (Latency)                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 이벤트 생성 ─────────────────────────▶ 발행         │   │
│  │             └── 폴링 간격 (500ms~) ──┘              │   │
│  │                                                     │   │
│  │ 실시간성이 필요한 경우 문제                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. 데이터베이스 부하                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ SELECT * FROM outbox WHERE published = false        │   │
│  │       ↓                                             │   │
│  │ 1초에 2회 = 하루 172,800 쿼리                       │   │
│  │ 이벤트가 없어도 쿼리 실행                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  3. 스케일링 어려움                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Publisher 2개 실행?                                 │   │
│  │   → SELECT FOR UPDATE로 경합                       │   │
│  │   → 중복 발행 위험                                  │   │
│  │                                                     │   │
│  │ 분산 락 필요?                                       │   │
│  │   → 복잡성 증가                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  4. 순서 보장의 어려움                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 같은 Aggregate의 이벤트가 순서대로 발행되어야 함    │   │
│  │ 여러 Publisher가 있으면 순서 뒤바뀔 수 있음         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## CDC: Change Data Capture

### 트랜잭션 로그의 힘

모든 데이터베이스는 내부적으로 **트랜잭션 로그**를 유지한다:

```
┌─────────────────────────────────────────────────────────────┐
│              데이터베이스 트랜잭션 로그                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PostgreSQL WAL (Write-Ahead Log)                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LSN 000001: BEGIN                                   │   │
│  │ LSN 000002: INSERT orders (id=1, status='created')  │   │
│  │ LSN 000003: INSERT outbox (event_type='OrderCreated') │ │
│  │ LSN 000004: COMMIT                                  │   │
│  │ LSN 000005: BEGIN                                   │   │
│  │ LSN 000006: UPDATE orders SET status='paid' WHERE.. │   │
│  │ LSN 000007: INSERT outbox (event_type='OrderPaid')  │   │
│  │ LSN 000008: COMMIT                                  │   │
│  │ ...                                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  MySQL Binary Log                                          │
│  Oracle Redo Log                                           │
│  SQL Server Transaction Log                                │
│                                                             │
│  → 이 로그는 이미 존재하고, 순서가 보장됨!                 │
│  → 이것을 읽으면 폴링할 필요가 없음                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### CDC의 동작 원리

```
┌─────────────────────────────────────────────────────────────┐
│                    CDC 동작 원리                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Application                                                │
│      │                                                      │
│      │ INSERT INTO outbox ...                              │
│      ▼                                                      │
│  ┌─────────────────┐                                       │
│  │    Database     │                                       │
│  │  ┌───────────┐  │                                       │
│  │  │   Table   │  │                                       │
│  │  │  (outbox) │  │                                       │
│  │  └───────────┘  │                                       │
│  │       │         │                                       │
│  │       ▼         │                                       │
│  │  ┌───────────┐  │                                       │
│  │  │    WAL    │──┼──────▶ Debezium                      │
│  │  │  (로그)   │  │        (CDC Connector)               │
│  │  └───────────┘  │              │                        │
│  └─────────────────┘              │                        │
│                                   ▼                        │
│                           ┌─────────────┐                  │
│                           │    Kafka    │                  │
│                           │   Topic     │                  │
│                           └─────────────┘                  │
│                                                             │
│  핵심:                                                      │
│  • 애플리케이션은 DB에만 쓴다                               │
│  • Debezium이 WAL을 읽어서 Kafka로 전달                    │
│  • 폴링 없이 실시간 이벤트 전파                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Debezium 소개

### Debezium이란?

**Debezium**은 Red Hat이 개발한 오픈소스 CDC 플랫폼이다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Debezium 개요                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  지원 데이터베이스:                                         │
│  • PostgreSQL (Logical Replication)                        │
│  • MySQL (Binary Log)                                      │
│  • MongoDB (Oplog)                                         │
│  • Oracle (LogMiner)                                       │
│  • SQL Server (CT)                                         │
│  • Cassandra, Vitess, Spanner, ...                        │
│                                                             │
│  아키텍처:                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Kafka Connect                       │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  Debezium Connector (Source Connector)      │   │   │
│  │  │                                             │   │   │
│  │  │  • DB에 연결                                │   │   │
│  │  │  • 트랜잭션 로그 읽기                       │   │   │
│  │  │  • 변경을 Kafka 메시지로 변환               │   │   │
│  │  │  • 오프셋 관리 (재시작 시 이어서 처리)      │   │   │
│  │  │                                             │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  특징:                                                      │
│  • 실시간에 가까운 지연시간 (밀리초 단위)                   │
│  • 정확히 한 번 처리 (exactly-once) 지원                   │
│  • 스키마 레지스트리 통합                                   │
│  • 풍부한 SMT(Single Message Transform) 지원               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Outbox Event Router SMT

### Gunnar Morling의 핵심 기여

Debezium의 **Outbox Event Router**는 Outbox 패턴을 위해 특별히 설계된 SMT(Single Message Transform)다:

```
┌─────────────────────────────────────────────────────────────┐
│              Outbox Event Router 동작                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Outbox 테이블에 INSERT                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ INSERT INTO outbox (                                 │   │
│  │   aggregate_type = 'Order',                         │   │
│  │   aggregate_id = '12345',                           │   │
│  │   event_type = 'OrderCreated',                      │   │
│  │   payload = '{"orderId": "12345", ...}'             │   │
│  │ )                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  2. Debezium이 WAL에서 캡처                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ {                                                    │   │
│  │   "op": "c",  // create                             │   │
│  │   "after": {                                        │   │
│  │     "aggregate_type": "Order",                      │   │
│  │     "aggregate_id": "12345",                        │   │
│  │     "event_type": "OrderCreated",                   │   │
│  │     "payload": "{...}"                              │   │
│  │   }                                                 │   │
│  │ }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  3. Outbox Event Router SMT가 변환                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • 토픽 결정: outbox.event.Order                     │   │
│  │ • 키 설정: 12345 (aggregate_id)                     │   │
│  │ • 페이로드 추출: {"orderId": "12345", ...}          │   │
│  │ • 헤더 설정: event_type=OrderCreated                │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  4. Kafka 토픽으로 발행                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Topic: outbox.event.Order                           │   │
│  │ Key: 12345                                          │   │
│  │ Value: {"orderId": "12345", ...}                    │   │
│  │ Headers: {event_type: "OrderCreated"}               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Outbox 테이블 스키마

Debezium 권장 스키마:

```sql
-- Debezium Outbox Event Router 권장 스키마
CREATE TABLE outbox (
    id              UUID NOT NULL PRIMARY KEY,
    
    -- 라우팅 정보
    aggregatetype   VARCHAR(255) NOT NULL,  -- 토픽 결정에 사용
    aggregateid     VARCHAR(255) NOT NULL,  -- Kafka 파티션 키
    type            VARCHAR(255) NOT NULL,  -- 이벤트 타입 (헤더)
    
    -- 페이로드
    payload         JSONB,                   -- 실제 이벤트 데이터
    
    -- 추가 헤더 (선택)
    tracingspancontext VARCHAR(256),         -- 분산 추적
    timestamp       TIMESTAMP               -- 이벤트 시간
);

-- Debezium이 읽은 후 삭제 (선택적)
-- 또는 published 플래그로 관리
```

### Connector 설정

```json
{
  "name": "outbox-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "secret",
    "database.dbname": "orderdb",
    "database.server.name": "order-service",
    
    "table.include.list": "public.outbox",
    
    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
    
    "transforms.outbox.table.field.event.id": "id",
    "transforms.outbox.table.field.event.key": "aggregateid",
    "transforms.outbox.table.field.event.type": "type",
    "transforms.outbox.table.field.event.payload": "payload",
    "transforms.outbox.table.field.event.timestamp": "timestamp",
    
    "transforms.outbox.route.topic.replacement": "outbox.event.${routedByValue}",
    "transforms.outbox.route.by.field": "aggregatetype",
    
    "transforms.outbox.table.expand.json.payload": "true"
  }
}
```

---

## 순서 보장과 파티셔닝

### 같은 Aggregate의 이벤트 순서

```
┌─────────────────────────────────────────────────────────────┐
│                    순서 보장 메커니즘                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  문제: Order #123의 이벤트 순서                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. OrderCreated   (먼저)                            │   │
│  │ 2. OrderPaid      (나중)                            │   │
│  │ 3. OrderShipped   (더 나중)                         │   │
│  │                                                     │   │
│  │ 이 순서가 바뀌면 안 됨!                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  해결: Kafka 파티셔닝                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  aggregate_id = "123" → Key = "123"                │   │
│  │                                                     │   │
│  │  Kafka Topic: outbox.event.Order                   │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │ Partition 0: (key 해시값 기준)              │   │   │
│  │  │   [Order#123: Created] → [Order#123: Paid]  │   │   │
│  │  │   → [Order#123: Shipped]                    │   │   │
│  │  │                                             │   │   │
│  │  │ Partition 1:                                │   │   │
│  │  │   [Order#456: Created] → [Order#456: Paid]  │   │   │
│  │  │                                             │   │   │
│  │  │ Partition 2:                                │   │   │
│  │  │   [Order#789: Created]                      │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │                                                     │   │
│  │  같은 Key는 같은 Partition → 순서 보장              │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 중복 처리와 Exactly-Once

### Debezium의 Exactly-Once

Debezium 2.0부터 **exactly-once delivery**를 지원:

```
┌─────────────────────────────────────────────────────────────┐
│              Exactly-Once Delivery                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이전 (at-least-once):                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. WAL에서 읽기                                      │   │
│  │ 2. Kafka에 발행                                      │   │
│  │ 3. 오프셋 커밋                                       │   │
│  │    --- 여기서 장애 시 2-3 반복 → 중복 발행 ---       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Debezium 2.0+ (exactly-once):                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Kafka Transactions 활용:                             │   │
│  │                                                     │   │
│  │ 1. Kafka Transaction 시작                           │   │
│  │ 2. 메시지 발행                                      │   │
│  │ 3. 오프셋 정보도 같은 트랜잭션에 포함               │   │
│  │ 4. Kafka Transaction 커밋                           │   │
│  │                                                     │   │
│  │ → 메시지와 오프셋이 원자적으로 커밋                 │   │
│  │ → 중복 발행 없음                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  설정:                                                      │
│  exactly.once.support = true                               │
│  transaction.id = ${database.server.name}-connector        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Outbox 테이블 정리

### 이벤트 발행 후 처리

```
┌─────────────────────────────────────────────────────────────┐
│              Outbox 테이블 관리 전략                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  전략 1: 발행 후 즉시 삭제                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Debezium 설정:                                       │   │
│  │ transforms.outbox.table.op.invalid.behavior=warn    │   │
│  │                                                     │   │
│  │ 애플리케이션에서:                                    │   │
│  │ BEGIN;                                               │   │
│  │   INSERT INTO outbox ...;                           │   │
│  │   INSERT INTO orders ...;                           │   │
│  │ COMMIT;                                             │   │
│  │                                                     │   │
│  │ -- Debezium이 읽은 후 별도 프로세스가 삭제          │   │
│  │ DELETE FROM outbox WHERE id IN (...);               │   │
│  │                                                     │   │
│  │ 장점: 테이블 크기 최소화                            │   │
│  │ 단점: 삭제 작업 필요                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  전략 2: 일정 기간 보관 후 삭제                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ -- 파티셔닝 활용                                     │   │
│  │ CREATE TABLE outbox (                                │   │
│  │   ...                                                │   │
│  │ ) PARTITION BY RANGE (created_at);                  │   │
│  │                                                     │   │
│  │ -- 오래된 파티션 DROP (빠름)                         │   │
│  │ DROP TABLE outbox_2024_01;                          │   │
│  │                                                     │   │
│  │ 장점: 감사 추적, 디버깅                             │   │
│  │ 단점: 저장 공간                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  전략 3: Debezium Log-based Compaction                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Kafka의 Log Compaction과 함께 사용                  │   │
│  │                                                     │   │
│  │ 같은 Key의 최신 메시지만 유지                       │   │
│  │ 오래된 이벤트는 Kafka가 자동 정리                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 스키마 진화

### JSON Payload의 유연성

```
┌─────────────────────────────────────────────────────────────┐
│                   스키마 진화 전략                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  JSONB 페이로드의 장점:                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ V1: {"orderId": "123", "total": 100}                │   │
│  │                                                     │   │
│  │ V2: {"orderId": "123", "total": 100,                │   │
│  │      "currency": "KRW"}  ← 필드 추가                │   │
│  │                                                     │   │
│  │ → DB 스키마 변경 없이 이벤트 스키마 확장            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Schema Registry 활용 (권장):                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Debezium + Confluent Schema Registry:               │   │
│  │                                                     │   │
│  │ 1. Avro/Protobuf로 스키마 정의                      │   │
│  │ 2. Schema Registry에 등록                           │   │
│  │ 3. 스키마 호환성 검증 (backward, forward)           │   │
│  │ 4. Consumer가 자동으로 버전 처리                    │   │
│  │                                                     │   │
│  │ key.converter.schema.registry.url=http://...        │   │
│  │ value.converter.schema.registry.url=http://...      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 개념 정리

| 개념 | 설명 |
|------|------|
| **CDC** | 데이터베이스 트랜잭션 로그를 읽어 변경 캡처 |
| **Debezium** | Red Hat의 오픈소스 CDC 플랫폼 |
| **Outbox Event Router** | Outbox 테이블을 위한 SMT |
| **aggregate_id** | Kafka 파티션 키로 사용, 순서 보장 |
| **Exactly-Once** | Kafka Transactions로 중복 방지 |
| **SMT** | Single Message Transform |

---

## 더 읽을 자료

- [Debezium Documentation](https://debezium.io/documentation/)
- [Outbox Event Router Reference](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Kafka Connect](https://kafka.apache.org/documentation/#connect)
- [Gunnar Morling's Blog](https://www.morling.dev/)

---

## 부록: Eco² 적용 포인트

### PostgreSQL + Debezium 구성

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² CDC 아키텍처                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Scan Service                       │   │
│  │  ┌────────────┐    ┌────────────┐                  │   │
│  │  │   FastAPI  │───▶│ PostgreSQL │                  │   │
│  │  └────────────┘    │  ┌──────┐  │                  │   │
│  │                    │  │outbox│  │                  │   │
│  │                    │  └──────┘  │                  │   │
│  │                    │     │      │                  │   │
│  │                    │     │ WAL  │                  │   │
│  │                    └─────┼──────┘                  │   │
│  └──────────────────────────┼──────────────────────────┘   │
│                             │                               │
│                             ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               Kafka Connect Cluster                  │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │        Debezium PostgreSQL Connector        │   │   │
│  │  │        + Outbox Event Router SMT            │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                             │                               │
│                             ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Kafka Cluster                     │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │ Topic: outbox.event.scan_task               │   │   │
│  │  │   [ScanCompleted] [RewardRequested] ...     │   │   │
│  │  │                                             │   │   │
│  │  │ Topic: outbox.event.character               │   │   │
│  │  │   [CharacterGranted] [PointsAdded] ...      │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                             │                               │
│              ┌──────────────┼──────────────┐               │
│              ▼              ▼              ▼               │
│       ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│       │Character │   │    My    │   │Analytics │         │
│       │ Service  │   │ Service  │   │ Service  │         │
│       └──────────┘   └──────────┘   └──────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Kubernetes에서 Debezium 배포

```yaml
# workloads/kafka-connect/debezium-connector.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaConnector
metadata:
  name: scan-outbox-connector
  namespace: kafka
  labels:
    strimzi.io/cluster: kafka-connect
spec:
  class: io.debezium.connector.postgresql.PostgresConnector
  tasksMax: 1
  config:
    # 데이터베이스 연결
    database.hostname: scan-postgresql.scan.svc.cluster.local
    database.port: 5432
    database.user: ${file:/opt/kafka/external-configuration/connector-secrets/database-user}
    database.password: ${file:/opt/kafka/external-configuration/connector-secrets/database-password}
    database.dbname: scan
    database.server.name: scan
    
    # Logical Replication
    plugin.name: pgoutput
    slot.name: scan_outbox_slot
    publication.name: scan_outbox_publication
    
    # Outbox 테이블만 캡처
    table.include.list: public.scan_outbox
    
    # Outbox Event Router
    transforms: outbox
    transforms.outbox.type: io.debezium.transforms.outbox.EventRouter
    transforms.outbox.table.field.event.id: id
    transforms.outbox.table.field.event.key: aggregate_id
    transforms.outbox.table.field.event.type: event_type
    transforms.outbox.table.field.event.payload: payload
    transforms.outbox.table.fields.additional.placement: trace_id:header,user_id:header
    
    # 토픽 라우팅
    transforms.outbox.route.topic.replacement: eco2.events.${routedByValue}
    transforms.outbox.route.by.field: aggregate_type
    
    # JSON 확장
    transforms.outbox.table.expand.json.payload: true
    
    # Exactly-Once
    exactly.once.support: requested
    
    # 스키마
    key.converter: org.apache.kafka.connect.json.JsonConverter
    key.converter.schemas.enable: false
    value.converter: org.apache.kafka.connect.json.JsonConverter
    value.converter.schemas.enable: false
```

### PostgreSQL Logical Replication 설정

```sql
-- PostgreSQL 설정 (postgresql.conf)
-- wal_level = logical
-- max_replication_slots = 4
-- max_wal_senders = 4

-- Outbox 테이블 생성
CREATE TABLE scan_outbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(50) NOT NULL DEFAULT 'scan_task',
    aggregate_id    UUID NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,
    trace_id        VARCHAR(64),
    user_id         UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Publication 생성 (Debezium이 구독)
CREATE PUBLICATION scan_outbox_publication FOR TABLE scan_outbox;

-- Replication 권한 부여
GRANT USAGE ON SCHEMA public TO debezium;
GRANT SELECT ON scan_outbox TO debezium;
ALTER USER debezium WITH REPLICATION;
```

### Consumer 구현 (Kafka Consumer)

```python
# domains/character/consumers/kafka_consumer.py

from confluent_kafka import Consumer, KafkaError
import json

class ScanEventConsumer:
    def __init__(self):
        self.consumer = Consumer({
            'bootstrap.servers': 'kafka:9092',
            'group.id': 'character-service',
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,  # 수동 커밋
        })
        self.consumer.subscribe(['eco2.events.scan_task'])
    
    async def process_messages(self):
        while True:
            msg = self.consumer.poll(1.0)
            
            if msg is None:
                continue
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise Exception(msg.error())
            
            # 헤더에서 메타데이터 추출
            headers = {h[0]: h[1].decode() for h in msg.headers()}
            event_type = headers.get('event_type')
            event_id = headers.get('id')
            trace_id = headers.get('trace_id')
            
            # Idempotency 체크
            if await self.is_processed(event_id):
                self.consumer.commit(msg)
                continue
            
            # 페이로드 파싱
            payload = json.loads(msg.value().decode())
            
            # 이벤트 타입별 처리
            if event_type == 'ScanCompleted':
                await self.handle_scan_completed(payload, trace_id)
            elif event_type == 'RewardRequested':
                await self.handle_reward_requested(payload, trace_id)
            
            # 처리 완료 기록 및 커밋
            await self.mark_processed(event_id)
            self.consumer.commit(msg)
    
    async def handle_reward_requested(self, payload: dict, trace_id: str):
        """RewardRequested 이벤트 처리"""
        await character_service.grant_reward(
            user_id=payload['user_id'],
            task_id=payload['task_id'],
            category=payload['category'],
            points=payload['points'],
        )
```

### Gunnar Morling 원칙의 Eco² 적용 (Command-Event Separation)

```
┌─────────────────────────────────────────────────────────────┐
│       Eco² CDC Pipeline (Command-Event Separation)           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │                   Domain Services                      │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │ │
│  │  │  Scan   │  │Character│  │   My    │  │  Auth   │  │ │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  │ │
│  └───────┼────────────┼────────────┼────────────┼────────┘ │
│          │            │            │            │          │
│     ┌────┴────┐       │            │            │          │
│     │         │       │            │            │          │
│     ▼         ▼       ▼            ▼            ▼          │
│ ┌────────┐ ┌─────────────────────────────────────────────┐ │
│ │RabbitMQ│ │              PostgreSQL                     │ │
│ │        │ │  events (Event Store) + outbox (CDC용)      │ │
│ │AI Task │ └─────────────────────┬───────────────────────┘ │
│ └───┬────┘                       │                         │
│     │                            │ WAL                     │
│     │ Celery                     ▼                         │
│     ▼                 ┌─────────────────────────────────┐  │
│ ┌────────────┐        │      Debezium CDC               │  │
│ │ Vision/LLM │        │  + Outbox Event Router          │  │
│ │  Workers   │        └─────────────┬───────────────────┘  │
│ └─────┬──────┘                      │                      │
│       │                             ▼                      │
│       │ 완료 시 Event Store  ┌─────────────────────────┐   │
│       └─────────────────────▶│        Kafka            │   │
│                              │                         │   │
│                              │  eco2.events.scan       │   │
│                              │  eco2.events.character  │   │
│                              │  eco2.events.dlq        │   │
│                              └───────────┬─────────────┘   │
│                                          │                 │
│                           ┌──────────────┼──────────────┐  │
│                           ▼              ▼              ▼  │
│                     Character        My           Analytics│
│                     Consumer     Consumer         Consumer │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Command-Event Separation: AI Task → Event Store → CDC

```python
# domains/scan/tasks/ai_pipeline.py

@celery_app.task(bind=True, max_retries=3)
def answer_gen(self, prev_result: dict, task_id: str):
    """Celery Task 완료 → Event Store 저장 → CDC가 Kafka로"""
    
    try:
        answer = llm_api.generate(prev_result)
        
        # Event Store + Outbox 저장
        async with db.begin():
            # Event Store (영구 저장)
            await db.execute("""
                INSERT INTO events (aggregate_id, event_type, event_data)
                VALUES (:task_id, 'ScanCompleted', :data)
            """)
            
            # Outbox (Debezium CDC가 캡처)
            await db.execute("""
                INSERT INTO outbox (aggregate_id, event_type, payload)
                VALUES (:task_id, 'ScanCompleted', :payload)
            """)
        
        # COMMIT 후 Debezium이 WAL → Kafka 자동 발행
        return answer
        
    except Exception as exc:
        # Celery DLQ로 이동
        raise self.retry(exc=exc)
```

### Kafka Consumer (도메인 이벤트 처리)

```python
# domains/character/consumers/kafka_consumer.py

class CharacterKafkaConsumer:
    """Kafka Consumer - CDC 이벤트 처리"""
    
    def __init__(self):
        self.consumer = Consumer({
            'bootstrap.servers': settings.KAFKA_SERVERS,
            'group.id': 'character-service',
            'enable.auto.commit': False,
        })
        self.consumer.subscribe(['eco2.events.scan_task'])
    
    async def handle_message(self, msg):
        event_id = msg.headers().get('event_id')
        trace_id = msg.headers().get('trace_id')
        
        # OpenTelemetry 컨텍스트 복원
        with tracer.start_span(f"consume", trace_id=trace_id):
            
            # Idempotency 체크
            if await self.is_processed(event_id):
                return
            
            # 보상 지급
            event = json.loads(msg.value())
            await self.grant_reward(event)
            
            # 처리 완료 + Offset 커밋
            await self.mark_processed(event_id)
            self.consumer.commit(msg)
```

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-------------------|
| **CDC 기반** | 없음 | Debezium (모든 도메인) |
| **AI 파이프라인** | gRPC 블로킹 | RabbitMQ + Celery |
| **도메인 이벤트** | gRPC 직접 호출 | Kafka (CDC) |
| **Outbox Router** | 없음 | 도메인별 토픽 분리 |
| **순서 보장** | 순차 호출 | aggregate_id Partition |
| **Exactly-Once** | 없음 | Debezium + Consumer 멱등성 |
| **실패 처리** | Circuit Breaker | Celery DLQ + Kafka DLQ |
| **추적** | gRPC Interceptor | trace_id 헤더 전파 |
| **Projection** | 없음 | My = Kafka Consumer Read Model |
