# CQRS: Command와 Query의 책임 분리

> **Part II: 이벤트 기반 아키텍처** | [← 02. Event Sourcing](./02-event-sourcing-martin-fowler.md) | [인덱스](./00-index.md) | [05. EIP →](./05-enterprise-integration-patterns.md)

> 원문: [CQRS](https://martinfowler.com/bliki/CQRS.html) - Martin Fowler (2011)

---

## 들어가며

2011년, Martin Fowler가 Greg Young의 아이디어를 정리하여 발표한 CQRS(Command Query Responsibility Segregation)는 **읽기와 쓰기를 별도의 모델로 분리하는 패턴**이다.

흥미로운 점은 Fowler 본인이 이 글에서 CQRS의 **위험성을 강하게 경고**한다는 것이다. 그는 CQRS가 유용한 경우도 있지만, 대부분의 시스템에는 불필요한 복잡성을 추가한다고 강조한다.

> "CQRS is a significant mental leap for all concerned, so shouldn't be tackled unless the benefit is worth the jump."

이 문서에서는 CQRS가 해결하는 문제, 패턴의 핵심 구조, 그리고 언제 사용해야 하는지(사용하지 말아야 하는지)를 살펴본다.

---

## CRUD의 한계

### 단일 모델의 문제

전통적인 시스템은 하나의 모델로 모든 작업을 처리한다:

```
┌─────────────────────────────────────────────────────────────┐
│                   CRUD 단일 모델                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Record: { id, name, email, balance, ... }                 │
│                                                             │
│  모든 작업이 같은 모델 사용:                                │
│  • Create: 새 레코드 생성                                   │
│  • Read: 레코드 조회                                        │
│  • Update: 레코드 수정                                      │
│  • Delete: 레코드 삭제                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

단순한 시스템에서는 이 방식이 잘 작동한다. 하지만 요구사항이 복잡해지면 문제가 생긴다.

### 읽기와 쓰기의 불일치

실제 시스템에서는 읽기와 쓰기의 요구사항이 매우 다르다:

```
┌─────────────────────────────────────────────────────────────┐
│                읽기 vs 쓰기 요구사항                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  쓰기 (Command) 측면:                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • 복잡한 비즈니스 규칙 검증                          │   │
│  │ • 데이터 정합성 보장                                 │   │
│  │ • 트랜잭션 처리                                      │   │
│  │ • 예: "잔액이 충분해야만 이체 가능"                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  읽기 (Query) 측면:                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • 여러 테이블 조인                                   │   │
│  │ • 집계, 통계, 대시보드                               │   │
│  │ • 다양한 형태의 조회 (리스트, 상세, 검색)           │   │
│  │ • 예: "최근 30일 거래 내역 + 카테고리별 합계"        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  하나의 모델로 양쪽을 만족시키면?                           │
│  → 모델이 비대해지고, 양쪽 모두 최적화 불가                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## CQRS의 핵심: 모델 분리

### Command와 Query 분리

CQRS는 이 문제를 **모델 자체를 분리**하여 해결한다:

```
┌─────────────────────────────────────────────────────────────┐
│                      CQRS 구조                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                     ┌─────────────┐                        │
│                     │   Client    │                        │
│                     └──────┬──────┘                        │
│                            │                               │
│              ┌─────────────┴─────────────┐                 │
│              │                           │                 │
│              ▼                           ▼                 │
│  ┌─────────────────────┐     ┌─────────────────────┐      │
│  │    Command Side     │     │     Query Side      │      │
│  │                     │     │                     │      │
│  │  • 상태 변경        │     │  • 데이터 조회      │      │
│  │  • 비즈니스 규칙    │     │  • 최적화된 뷰      │      │
│  │  • 트랜잭션         │     │  • 집계/통계        │      │
│  │                     │     │                     │      │
│  │  void execute()     │     │  Data query()       │      │
│  └─────────────────────┘     └─────────────────────┘      │
│                                                             │
│  핵심: 완전히 다른 모델, 다른 최적화 전략                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### CQS 원칙

CQRS는 Bertrand Meyer의 CQS(Command Query Separation) 원칙에서 확장되었다:

| 구분 | Command | Query |
|------|---------|-------|
| **목적** | 상태 변경 | 데이터 반환 |
| **부작용** | 있음 | 없음 |
| **반환값** | void (또는 생성된 ID) | 데이터 |
| **멱등성** | 일반적으로 아님 | 항상 멱등 |

---

## 분리의 수준

CQRS는 다양한 수준으로 적용할 수 있다.

### 레벨 1: 같은 DB, 다른 모델

가장 단순한 형태로, 같은 데이터베이스를 사용하되 접근하는 모델만 분리한다:

```
┌─────────────────────────────────────────────────────────────┐
│                   같은 DB, 다른 모델                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────┐         ┌────────────────┐             │
│  │  Command Model │         │  Query Model   │             │
│  │  (ORM Entity)  │         │  (DTO/View)    │             │
│  └───────┬────────┘         └───────┬────────┘             │
│          │                          │                       │
│          └──────────┬───────────────┘                       │
│                     ▼                                       │
│          ┌─────────────────────┐                           │
│          │   Shared Database   │                           │
│          │                     │                           │
│          │  Tables + Views     │                           │
│          └─────────────────────┘                           │
│                                                             │
│  장점: 단순함, 즉시 일관성                                  │
│  단점: 읽기 성능 최적화 제한                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 레벨 2: 분리된 DB

읽기와 쓰기가 별도의 데이터베이스를 사용한다:

```
┌─────────────────────────────────────────────────────────────┐
│                   분리된 DB (Read Replica)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────┐         ┌────────────────┐             │
│  │  Command Model │         │  Query Model   │             │
│  └───────┬────────┘         └───────┬────────┘             │
│          │                          │                       │
│          ▼                          ▼                       │
│  ┌────────────────┐         ┌────────────────┐             │
│  │   Write DB     │ ──────▶ │   Read DB      │             │
│  │   (Primary)    │  동기화  │   (Replica)    │             │
│  │                │         │                │             │
│  │  정규화된 구조  │         │  비정규화/캐시  │             │
│  └────────────────┘         └────────────────┘             │
│                                                             │
│  장점: 읽기/쓰기 독립적 확장, 읽기 최적화                   │
│  단점: 복잡성 증가, 데이터 지연(Eventual Consistency)       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 레벨 3: Event Sourcing + Projection

가장 강력한 형태로, Event Sourcing과 결합한다:

```
┌─────────────────────────────────────────────────────────────┐
│              Event Sourcing + CQRS                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Command Side                    Query Side                 │
│  ─────────────                   ──────────                 │
│                                                             │
│  POST /orders                    GET /orders                │
│       │                               │                     │
│       ▼                               ▼                     │
│  ┌────────────┐               ┌────────────┐               │
│  │  Aggregate │               │ Read Model │               │
│  │   Order    │               │  (View)    │               │
│  └─────┬──────┘               └─────┬──────┘               │
│        │                            ▲                       │
│        │ 이벤트 발행                │ Projection            │
│        ▼                            │                       │
│  ┌─────────────────────────────────┴───────────┐           │
│  │              Event Store                     │           │
│  │                                              │           │
│  │  OrderCreated → ItemAdded → OrderShipped    │           │
│  └──────────────────────────────────────────────┘           │
│                                                             │
│  Write: Event를 저장                                        │
│  Read: Event를 재생하여 Projection 생성                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## CQRS와 함께 사용되는 패턴

CQRS는 단독으로 사용되기보다 다른 패턴과 자주 조합된다:

| 패턴 | 조합 방식 |
|------|----------|
| **Event Sourcing** | Command가 이벤트를 저장, Query가 Projection을 읽음 |
| **Eventual Consistency** | 읽기 모델이 비동기로 업데이트됨 |
| **Event-Driven** | 서비스 간 이벤트로 데이터 동기화 |
| **Task-based UI** | CRUD 대신 의도를 표현하는 명령 |

---

## 언제 사용해야 하는가?

### Martin Fowler의 경고

Fowler는 CQRS의 위험성을 강조한다:

```
┌─────────────────────────────────────────────────────────────┐
│                 ⚠️  CQRS 사용 시 주의                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ❌ 피해야 할 경우:                                         │
│  • 단순한 CRUD 시스템                                       │
│  • 읽기/쓰기 요구사항이 비슷한 경우                         │
│  • 팀이 CQRS 경험이 없는 경우                               │
│  • 복잡성을 감당할 수 없는 프로젝트                         │
│                                                             │
│  ✅ 적합한 경우:                                            │
│  • 읽기/쓰기 비율이 극단적으로 다름 (예: 읽기 90%)         │
│  • 읽기와 쓰기의 확장 요구가 다름                           │
│  • 복잡한 도메인 로직 + 다양한 조회 요구                    │
│  • Event Sourcing을 이미 사용 중                            │
│                                                             │
│  "대부분의 시스템에서 CQRS는 위험한 복잡성을 추가한다."     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### BoundedContext 단위로만 적용

CQRS는 **시스템 전체가 아닌 특정 Bounded Context에만** 적용해야 한다:

```
┌─────────────────────────────────────────────────────────────┐
│              CQRS 적용 범위                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  System:                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ Context A   │  │ Context B   │  │ Context C   │  │   │
│  │  │   (CRUD)    │  │   (CQRS)    │  │   (CRUD)    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ❌ 시스템 전체에 CQRS 강제                                 │
│  ✅ 필요한 Context에만 CQRS 적용                           │
│                                                             │
│  각 Context는 자신에게 맞는 패턴을 선택해야 한다.          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 대안: Reporting Database

CQRS가 과하다면 **Reporting Database** 패턴을 고려하라:

```
┌─────────────────────────────────────────────────────────────┐
│            Reporting Database (더 단순한 대안)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CQRS:                                                      │
│  → 모든 읽기가 분리된 모델 사용                             │
│  → 높은 복잡성                                              │
│                                                             │
│  Reporting Database:                                        │
│  → 대부분 읽기는 기존 시스템 사용                           │
│  → 복잡한 쿼리만 별도 DB로 오프로드                        │
│  → 낮은 복잡성                                              │
│                                                             │
│  ┌────────────┐                                            │
│  │ Main App   │──── 일반 쿼리 ────▶ Main DB                │
│  │            │                                            │
│  │            │──── 복잡한 쿼리 ──▶ Reporting DB           │
│  └────────────┘                    (동기화)                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 정리

| 개념 | 설명 |
|------|------|
| **CQRS** | Command(쓰기)와 Query(읽기) 모델을 분리하는 패턴 |
| **기원** | Greg Young 제안, Martin Fowler가 정리 (CQS에서 확장) |
| **적합** | 읽기/쓰기 불균형이 큰 고성능 시스템, 복잡한 도메인 |
| **경고** | 대부분의 시스템에는 불필요한 복잡성 추가 |
| **범위** | 시스템 전체가 아닌 BoundedContext 단위로만 적용 |
| **대안** | Reporting Database로 복잡한 쿼리만 분리 |

---

## 더 읽을 자료

- [CQRS, Task Based UIs, Event Sourcing agh!](http://codebetter.com/gregyoung/2010/02/16/cqrs-task-based-uis-event-sourcing-agh/) - Greg Young
- [Clarified CQRS](http://udidahan.com/2009/12/09/clarified-cqrs/) - Udi Dahan

---

## 부록: Eco² 적용 포인트

### 전환 계획: gRPC → Command-Event Separation

Eco²는 **Command-Event Separation** 아키텍처를 채택한다. CQRS의 핵심 원칙을 Event-Driven 방식으로 적용한다.

```
┌─────────────────────────────────────────────────────────────┐
│        Eco² CQRS via Command-Event Separation               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Command Side (쓰기)              Query Side (읽기)         │
│  ─────────────────────            ─────────────────         │
│                                                             │
│  POST /scan                        GET /my/profile          │
│       │                                 │                   │
│       ▼                                 ▼                   │
│  ┌──────────┐                    ┌──────────┐              │
│  │ Scan API │                    │  My API  │              │
│  │ (Write)  │                    │ (Read)   │              │
│  └────┬─────┘                    └────┬─────┘              │
│       │                               │                    │
│       ├──────────────┐                │                    │
│       ▼              ▼                ▼                    │
│  RabbitMQ      Event Store      Read Model                 │
│  (Task)        + Outbox         (Projection)               │
│       │              │                ▲                    │
│       │              │ CDC            │                    │
│       ▼              ▼                │                    │
│  Celery         Kafka ──────────────►│                    │
│  Workers       (Event)          Kafka Consumer             │
│                                 (Projection 업데이트)       │
│                                                             │
│  핵심: Write와 Read가 완전히 분리, Kafka로 동기화           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Martin Fowler 경고 준수

Eco²는 CQRS를 **필요한 BoundedContext에만** 선택적으로 적용한다:

```
┌─────────────────────────────────────────────────────────────┐
│               Eco² CQRS 적용 범위 (BoundedContext)          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────┐ │
│  │   Auth    │  │   Scan    │  │ Character │  │   My    │ │
│  │  (CRUD)   │  │  (CQRS)   │  │  (CQRS)   │  │ (Read)  │ │
│  └───────────┘  └───────────┘  └───────────┘  └─────────┘ │
│                                                             │
│  Auth: 단순 CRUD                                           │
│  → CQRS 불필요, 기존 패턴 유지                             │
│                                                             │
│  Scan: Command + Event                                     │
│  → ProcessImage(Command) → ScanCompleted(Event)            │
│  → CQRS 적용 ✅                                            │
│                                                             │
│  Character: Command + Event                                │
│  → Event Sourcing + Projection                             │
│  → CQRS 적용 ✅                                            │
│                                                             │
│  My: Query Only (Read Model)                               │
│  → 다른 도메인 Event를 Projection으로 수집                 │
│  → Query-side CQRS ✅                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### My Service: Kafka Consumer Projection

```python
# domains/my/consumers/projection_consumer.py

class MyProjectionConsumer:
    """Kafka Consumer - 모든 도메인 이벤트를 Projection으로 수집"""
    
    def __init__(self):
        self.consumer = Consumer({
            'bootstrap.servers': settings.KAFKA_SERVERS,
            'group.id': 'my-service-projection',
        })
        # 여러 토픽 구독
        self.consumer.subscribe([
            'eco2.events.scan',
            'eco2.events.character',
            'eco2.events.auth',
        ])
    
    async def handle_scan_completed(self, event: ScanCompleted):
        """Scan 이벤트 → My Read Model 업데이트"""
        await self.db.execute("""
            UPDATE user_profiles
            SET total_scans = total_scans + 1,
                last_scan_at = :completed_at
            WHERE user_id = :user_id
        """, {"user_id": event.user_id, "completed_at": event.completed_at})
    
    async def handle_character_granted(self, event: CharacterGranted):
        """Character 이벤트 → My Read Model 업데이트"""
        await self.db.execute("""
            INSERT INTO user_characters (user_id, character_id, acquired_at)
            VALUES (:user_id, :char_id, :acquired_at)
            ON CONFLICT DO NOTHING
        """, {"user_id": event.user_id, "char_id": event.character_id, ...})
```

### AS-IS vs TO-BE

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-----------------------------------|
| **Command** | gRPC 직접 호출 | RabbitMQ + Celery Task |
| **Query** | gRPC 또는 DB 직접 | Kafka Projection (Read Model) |
| **동기화** | 즉시 일관성 | Eventual Consistency |
| **분리 수준** | 논리적 분리 | 물리적 분리 (별도 DB) |
| **확장성** | 제한적 | Read/Write 독립 스케일링 |
| **BoundedContext** | 서비스 경계 | + Event Schema Contract |
