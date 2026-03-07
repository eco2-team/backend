# Domain-Driven Design: Aggregate와 트랜잭션 경계

> **Part IV: 도메인 주도 설계** | [← 09. Debezium](./09-debezium-outbox-event-router.md) | [인덱스](./00-index.md) | [11. AMQP →](./11-amqp-rabbitmq.md)

> 원문: [Domain-Driven Design: Tackling Complexity in the Heart of Software](https://www.domainlanguage.com/ddd/) - Eric Evans (Addison-Wesley, 2003)  
> 참고: [Implementing Domain-Driven Design](https://www.informit.com/store/implementing-domain-driven-design-9780321834577) - Vaughn Vernon (2013)

---

## 들어가며

2003년, Eric Evans가 발표한 **Domain-Driven Design(DDD)**은 소프트웨어 설계의 패러다임을 바꿨다. 특히 **Aggregate** 개념은 마이크로서비스 아키텍처에서 **트랜잭션 경계를 결정하는 핵심 원칙**이 되었다.

Pat Helland가 2007년 논문에서 말한 **Entity**는 사실 Evans의 **Aggregate**와 동일한 개념이다. 이 문서에서는 DDD의 핵심 개념과 분산 시스템에서의 적용을 다룬다.

---

## DDD의 핵심 개념

### 전략적 설계 vs 전술적 설계

DDD는 두 가지 수준의 설계를 제공한다:

```
┌─────────────────────────────────────────────────────────────┐
│                   DDD의 두 가지 수준                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  전략적 설계 (Strategic Design):                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • Bounded Context: 모델의 경계                      │   │
│  │ • Ubiquitous Language: 공통 언어                    │   │
│  │ • Context Map: 컨텍스트 간 관계                     │   │
│  │                                                     │   │
│  │ → "큰 그림": 시스템을 어떻게 나눌 것인가?           │   │
│  │ → 마이크로서비스 경계 결정에 활용                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  전술적 설계 (Tactical Design):                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • Aggregate: 트랜잭션 경계                          │   │
│  │ • Entity: 고유 식별자를 가진 객체                   │   │
│  │ • Value Object: 불변의 값 객체                      │   │
│  │ • Domain Event: 도메인에서 발생한 사건              │   │
│  │ • Repository: Aggregate 저장소                      │   │
│  │                                                     │   │
│  │ → "상세 설계": 모델 내부를 어떻게 구성할 것인가?    │   │
│  │ → 코드 레벨 설계에 활용                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Bounded Context: 모델의 경계

### 같은 단어, 다른 의미

"고객(Customer)"이라는 단어가 부서마다 다른 의미를 가질 수 있다:

```
┌─────────────────────────────────────────────────────────────┐
│              같은 단어, 다른 컨텍스트                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  영업팀의 "고객":                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Customer {                                           │   │
│  │   name: "김철수"                                     │   │
│  │   phone: "010-1234-5678"                            │   │
│  │   sales_rep: "박영희"        ← 담당 영업사원         │   │
│  │   potential_value: 1억      ← 예상 거래 규모        │   │
│  │ }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  배송팀의 "고객":                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Customer {                                           │   │
│  │   name: "김철수"                                     │   │
│  │   address: "서울시 강남구..."  ← 배송 주소          │   │
│  │   preferred_time: "오후 2-6시" ← 배송 선호 시간     │   │
│  │   access_code: "1234#"        ← 출입 비밀번호       │   │
│  │ }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  회계팀의 "고객":                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Customer {                                           │   │
│  │   name: "김철수"                                     │   │
│  │   tax_id: "123-45-67890"      ← 사업자등록번호      │   │
│  │   payment_terms: "30일"       ← 결제 조건           │   │
│  │   credit_limit: 5000만원      ← 신용 한도           │   │
│  │ }                                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  → 하나의 "Customer" 모델로 통합하면?                      │
│    모든 필드가 섞여서 복잡해지고, 변경이 어려워짐           │
│                                                             │
│  → 해결책: Bounded Context로 분리                          │
│    각 컨텍스트에서 자신만의 Customer 모델 유지              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Bounded Context 정의

```
┌─────────────────────────────────────────────────────────────┐
│                   Bounded Context                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정의:                                                      │
│  "특정 도메인 모델이 적용되는 명시적인 경계"                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │   ┌─────────────┐     ┌─────────────┐             │   │
│  │   │   Sales     │     │  Shipping   │             │   │
│  │   │   Context   │     │   Context   │             │   │
│  │   │             │     │             │             │   │
│  │   │ ┌─────────┐ │     │ ┌─────────┐ │             │   │
│  │   │ │Customer │ │     │ │Customer │ │             │   │
│  │   │ │(영업용) │ │     │ │(배송용) │ │             │   │
│  │   │ └─────────┘ │     │ └─────────┘ │             │   │
│  │   │             │     │             │             │   │
│  │   │ ┌─────────┐ │     │ ┌─────────┐ │             │   │
│  │   │ │  Lead   │ │     │ │Shipment │ │             │   │
│  │   │ └─────────┘ │     │ └─────────┘ │             │   │
│  │   │             │     │             │             │   │
│  │   └─────────────┘     └─────────────┘             │   │
│  │         │                    │                     │   │
│  │         └────────┬───────────┘                     │   │
│  │                  │                                 │   │
│  │            Integration                             │   │
│  │         (이벤트, API, 공유 ID)                     │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  핵심:                                                      │
│  • 각 Context는 독립적인 모델을 가짐                        │
│  • 같은 용어도 Context마다 다른 의미                        │
│  • Context 간 통신은 명시적인 인터페이스로                  │
│  • → 마이크로서비스의 자연스러운 경계                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Aggregate: 트랜잭션의 경계

### Aggregate란?

**Aggregate**는 DDD에서 가장 중요한 전술적 패턴이다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Aggregate 정의                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Aggregate = 데이터 변경의 단위                             │
│                                                             │
│  "하나의 단위로 취급되는 연관 객체의 클러스터로,           │
│   데이터 변경 목적으로 하나의 단위로 다뤄진다."            │
│   - Eric Evans                                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Order Aggregate                      │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │                                               │  │   │
│  │  │  ┌─────────────────┐                         │  │   │
│  │  │  │   Order (Root)  │ ← Aggregate Root        │  │   │
│  │  │  │   - order_id    │                         │  │   │
│  │  │  │   - status      │                         │  │   │
│  │  │  │   - total       │                         │  │   │
│  │  │  └────────┬────────┘                         │  │   │
│  │  │           │                                   │  │   │
│  │  │     ┌─────┴─────┐                            │  │   │
│  │  │     │           │                            │  │   │
│  │  │  ┌──▼───┐  ┌───▼────┐                       │  │   │
│  │  │  │ Item │  │  Item  │ ← 내부 Entity         │  │   │
│  │  │  │ #1   │  │   #2   │                       │  │   │
│  │  │  └──────┘  └────────┘                       │  │   │
│  │  │                                               │  │   │
│  │  │  ┌──────────────────┐                        │  │   │
│  │  │  │ ShippingAddress  │ ← Value Object         │  │   │
│  │  │  └──────────────────┘                        │  │   │
│  │  │                                               │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  │                     │                               │   │
│  │                     │ 트랜잭션 경계                 │   │
│  │                     │ (이 안에서만 ACID 보장)       │   │
│  └─────────────────────┴───────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Aggregate의 규칙

```
┌─────────────────────────────────────────────────────────────┐
│                   Aggregate 규칙                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  규칙 1: Aggregate Root를 통해서만 접근                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ✅ 올바른 접근:                                    │   │
│  │     order = repository.find(order_id)               │   │
│  │     order.add_item(product, quantity)               │   │
│  │                                                     │   │
│  │  ❌ 잘못된 접근:                                    │   │
│  │     item = item_repository.find(item_id)            │   │
│  │     item.update_quantity(5)                         │   │
│  │     → OrderItem을 직접 접근하면 안 됨!              │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  규칙 2: Aggregate 간 참조는 ID로만                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ✅ 올바른 참조:                                    │   │
│  │     class Order:                                    │   │
│  │         customer_id: UUID  ← ID로 참조             │   │
│  │                                                     │   │
│  │  ❌ 잘못된 참조:                                    │   │
│  │     class Order:                                    │   │
│  │         customer: Customer  ← 직접 참조            │   │
│  │     → 다른 Aggregate를 직접 참조하면 경계가 무너짐  │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  규칙 3: 하나의 트랜잭션에서 하나의 Aggregate만 수정        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ✅ 올바른 트랜잭션:                                │   │
│  │     BEGIN                                           │   │
│  │       UPDATE orders SET status = 'paid'             │   │
│  │       INSERT INTO order_items ...                   │   │
│  │     COMMIT                                          │   │
│  │     → 같은 Aggregate (Order) 내에서만 변경          │   │
│  │                                                     │   │
│  │  ❌ 잘못된 트랜잭션:                                │   │
│  │     BEGIN                                           │   │
│  │       UPDATE orders SET status = 'paid'             │   │
│  │       UPDATE inventory SET quantity = quantity - 1  │   │
│  │     COMMIT                                          │   │
│  │     → 다른 Aggregate (Inventory)까지 수정!         │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  규칙 4: Aggregate 간 일관성은 결과적 일관성으로            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Order 결제 완료 → Inventory 차감 필요              │   │
│  │                                                     │   │
│  │  [Order Aggregate]                                  │   │
│  │       │                                             │   │
│  │       │ "OrderPaid" 이벤트 발행                     │   │
│  │       ▼                                             │   │
│  │  [Message Queue]                                    │   │
│  │       │                                             │   │
│  │       │ 비동기 전달                                 │   │
│  │       ▼                                             │   │
│  │  [Inventory Aggregate]                              │   │
│  │       재고 차감 (별도 트랜잭션)                     │   │
│  │                                                     │   │
│  │  → 결과적 일관성 (Eventual Consistency)             │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Pat Helland의 Entity = DDD의 Aggregate

### 개념의 일치

```
┌─────────────────────────────────────────────────────────────┐
│           Pat Helland Entity ↔ DDD Aggregate                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Pat Helland (2007):                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "Entity는 단일 트랜잭션 내에서                      │   │
│  │  원자적으로 업데이트될 수 있는 데이터의 집합"       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Eric Evans (2003):                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "Aggregate는 데이터 변경 목적으로                   │   │
│  │  하나의 단위로 다뤄지는 연관 객체의 클러스터"       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  대응 관계:                                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Helland의 용어        Evans의 용어                 │   │
│  │  ──────────────        ──────────────               │   │
│  │  Entity            =   Aggregate                    │   │
│  │  Entity 내부       =   Aggregate 내부               │   │
│  │  Activity          =   Domain Event + Saga         │   │
│  │  메시지            =   Domain Event                │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  두 사람 모두 같은 결론:                                    │
│  "무한 확장을 위해서는 트랜잭션 경계를 작게 유지하라"       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Domain Event: Aggregate 간 통신

### Domain Event란?

```
┌─────────────────────────────────────────────────────────────┐
│                    Domain Event                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정의:                                                      │
│  "도메인에서 발생한 의미 있는 사건"                         │
│                                                             │
│  특징:                                                      │
│  • 과거 시제로 명명 (OrderCreated, PaymentReceived)         │
│  • 불변 (한 번 발생하면 변경 불가)                          │
│  • 발생 시점의 상태를 담음                                  │
│                                                             │
│  예시:                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ @dataclass(frozen=True)                              │   │
│  │ class OrderPlaced:                                   │   │
│  │     """주문이 생성됨"""                              │   │
│  │     event_id: UUID                                   │   │
│  │     order_id: UUID                                   │   │
│  │     customer_id: UUID                                │   │
│  │     items: list[OrderItem]                          │   │
│  │     total_amount: Money                             │   │
│  │     occurred_at: datetime                           │   │
│  │                                                     │   │
│  │ @dataclass(frozen=True)                              │   │
│  │ class OrderPaid:                                     │   │
│  │     """주문 결제 완료"""                             │   │
│  │     event_id: UUID                                   │   │
│  │     order_id: UUID                                   │   │
│  │     payment_id: UUID                                 │   │
│  │     amount: Money                                    │   │
│  │     occurred_at: datetime                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Aggregate와 Domain Event

```
┌─────────────────────────────────────────────────────────────┐
│           Aggregate가 Domain Event를 발행                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  class Order:                                               │
│      """Order Aggregate Root"""                             │
│                                                             │
│      def __init__(self):                                    │
│          self._events: list[DomainEvent] = []              │
│                                                             │
│      def place(self, customer_id, items):                   │
│          """주문 생성"""                                    │
│          self.status = OrderStatus.PLACED                   │
│          self.customer_id = customer_id                     │
│          self.items = items                                 │
│                                                             │
│          # 도메인 이벤트 기록                               │
│          self._events.append(OrderPlaced(                   │
│              order_id=self.id,                              │
│              customer_id=customer_id,                       │
│              items=items,                                   │
│          ))                                                 │
│                                                             │
│      def pay(self, payment_id, amount):                     │
│          """결제 처리"""                                    │
│          if self.status != OrderStatus.PLACED:              │
│              raise InvalidOrderState()                      │
│                                                             │
│          self.status = OrderStatus.PAID                     │
│          self.payment_id = payment_id                       │
│                                                             │
│          # 도메인 이벤트 기록                               │
│          self._events.append(OrderPaid(                     │
│              order_id=self.id,                              │
│              payment_id=payment_id,                         │
│              amount=amount,                                 │
│          ))                                                 │
│                                                             │
│      def collect_events(self) -> list[DomainEvent]:         │
│          """이벤트 수집 후 초기화"""                        │
│          events = self._events.copy()                       │
│          self._events.clear()                               │
│          return events                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Aggregate 설계 가이드

### 작게 유지하라

```
┌─────────────────────────────────────────────────────────────┐
│               Aggregate 크기 가이드                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ❌ 너무 큰 Aggregate:                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Customer Aggregate (잘못된 설계)        │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │                                               │  │   │
│  │  │  Customer                                     │  │   │
│  │  │    ├── Profile                               │  │   │
│  │  │    ├── Addresses[]                           │  │   │
│  │  │    ├── PaymentMethods[]                      │  │   │
│  │  │    ├── Orders[]          ← 수천 개?          │  │   │
│  │  │    ├── Reviews[]         ← 수백 개?          │  │   │
│  │  │    └── WishlistItems[]                       │  │   │
│  │  │                                               │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  │  문제:                                              │   │
│  │  • 로딩 시 모든 주문/리뷰 로드?                     │   │
│  │  • 주문 하나 추가할 때 전체 잠금?                   │   │
│  │  • 동시성 충돌 빈번                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ✅ 작은 Aggregate들로 분리:                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │   │
│  │  │ Customer │  │  Order   │  │  Review  │         │   │
│  │  │Aggregate │  │Aggregate │  │Aggregate │         │   │
│  │  │          │  │          │  │          │         │   │
│  │  │ id       │  │ id       │  │ id       │         │   │
│  │  │ name     │  │customer_ │  │customer_ │         │   │
│  │  │ email    │  │    id ───┼──│    id    │         │   │
│  │  │addresses │  │ items[]  │  │ product_ │         │   │
│  │  │          │  │ status   │  │    id    │         │   │
│  │  └──────────┘  └──────────┘  └──────────┘         │   │
│  │        │              │             │              │   │
│  │        └──────────────┼─────────────┘              │   │
│  │                       │                            │   │
│  │              ID로만 참조 (느슨한 결합)             │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Vaughn Vernon의 조언:                                      │
│  "가능하면 Aggregate를 하나의 Entity만 포함하도록 설계하라" │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 불변식(Invariant)이 경계를 결정

```
┌─────────────────────────────────────────────────────────────┐
│              불변식이 Aggregate 경계를 결정                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  불변식(Invariant):                                         │
│  "항상 참이어야 하는 비즈니스 규칙"                         │
│                                                             │
│  예: 주문의 불변식                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. 주문 총액 = 모든 항목 가격의 합                   │   │
│  │ 2. 최소 주문 금액은 10,000원 이상                    │   │
│  │ 3. 하나의 주문에 같은 상품은 최대 10개까지           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  이 불변식을 지키려면?                                      │
│  → Order와 OrderItem이 같은 Aggregate에 있어야 함           │
│  → 그래야 add_item() 시 검증 가능                          │
│                                                             │
│  class Order:                                               │
│      def add_item(self, product_id, quantity, price):       │
│          # 불변식 3 검증                                    │
│          existing = self.get_item(product_id)               │
│          if existing and existing.quantity + quantity > 10: │
│              raise MaxQuantityExceeded()                    │
│                                                             │
│          self.items.append(OrderItem(...))                  │
│                                                             │
│          # 불변식 1 유지                                    │
│          self.total = sum(item.subtotal for item in items) │
│                                                             │
│          # 불변식 2는 place() 시점에 검증                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Context Map: Bounded Context 간 관계

### 통합 패턴

```
┌─────────────────────────────────────────────────────────────┐
│               Context Map 통합 패턴                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Published Language                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 공개된 형식으로 통신 (JSON Schema, Protobuf)        │   │
│  │                                                     │   │
│  │  [Order Context] ──JSON Schema──▶ [Shipping]       │   │
│  │                                                     │   │
│  │  서로의 내부를 모르고, 정의된 계약으로만 통신       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. Anti-Corruption Layer (ACL)                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 외부 모델이 내부를 오염시키지 않도록 변환 계층      │   │
│  │                                                     │   │
│  │  [Legacy System]                                    │   │
│  │       │                                             │   │
│  │       ▼                                             │   │
│  │  ┌─────────────┐                                   │   │
│  │  │     ACL     │ ← 변환 계층                       │   │
│  │  │ (Adapter)   │                                   │   │
│  │  └──────┬──────┘                                   │   │
│  │         ▼                                           │   │
│  │  [New Context]                                      │   │
│  │                                                     │   │
│  │  레거시의 이상한 모델이 새 시스템에 침투 방지       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  3. Shared Kernel                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 두 Context가 일부 모델을 공유 (주의해서 사용)       │   │
│  │                                                     │   │
│  │  [Context A]──┬──[Shared Kernel]──┬──[Context B]   │   │
│  │               │    (공유 모델)    │                │   │
│  │               └───────────────────┘                │   │
│  │                                                     │   │
│  │  변경 시 양쪽 모두 영향 → 강한 결합, 신중히 사용   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  4. Customer-Supplier                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 상류(Supplier)가 하류(Customer)의 요구를 반영       │   │
│  │                                                     │   │
│  │  [Order Context] ◀── 요청 ── [Report Context]      │   │
│  │    (Supplier)                    (Customer)         │   │
│  │        │                                            │   │
│  │        └── 필요한 이벤트 제공                       │   │
│  │                                                     │   │
│  │  하류가 필요로 하는 것을 상류가 제공해줌            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 개념 정리

| 개념 | 설명 |
|------|------|
| **Bounded Context** | 특정 도메인 모델이 적용되는 경계, 마이크로서비스 경계 |
| **Aggregate** | 트랜잭션 경계, 데이터 변경의 단위 |
| **Aggregate Root** | Aggregate의 진입점, 외부에서 접근 가능한 유일한 Entity |
| **Domain Event** | 도메인에서 발생한 의미 있는 사건, Aggregate 간 통신 수단 |
| **Invariant** | 항상 참이어야 하는 비즈니스 규칙, Aggregate 경계 결정 |
| **Context Map** | Bounded Context 간의 관계를 나타내는 지도 |

---

## 더 읽을 자료

- [Domain-Driven Design](https://www.domainlanguage.com/ddd/) - Eric Evans (Blue Book)
- [Implementing Domain-Driven Design](https://www.informit.com/store/implementing-domain-driven-design-9780321834577) - Vaughn Vernon (Red Book)
- [Domain-Driven Design Distilled](https://www.informit.com/store/domain-driven-design-distilled-9780134434421) - Vaughn Vernon (입문서)
- [DDD Reference](https://www.domainlanguage.com/ddd/reference/) - Eric Evans (무료 PDF)

---

## 부록: Eco² 적용 포인트

### Bounded Context 설계

```
┌─────────────────────────────────────────────────────────────┐
│                 Eco² Bounded Context                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ┌───────────┐   ┌───────────┐   ┌───────────┐    │   │
│  │  │   Auth    │   │   Scan    │   │ Character │    │   │
│  │  │  Context  │   │  Context  │   │  Context  │    │   │
│  │  │           │   │           │   │           │    │   │
│  │  │ • User    │   │ • Task    │   │ • Char    │    │   │
│  │  │ • Token   │   │ • Result  │   │ • Reward  │    │   │
│  │  │ • Session │   │ • Image   │   │ • Points  │    │   │
│  │  └─────┬─────┘   └─────┬─────┘   └─────┬─────┘    │   │
│  │        │               │               │          │   │
│  │        │    Published Language (JSON Events)      │   │
│  │        │               │               │          │   │
│  │        └───────────────┼───────────────┘          │   │
│  │                        │                          │   │
│  │                        ▼                          │   │
│  │                 ┌───────────┐                     │   │
│  │                 │    My     │                     │   │
│  │                 │  Context  │                     │   │
│  │                 │           │                     │   │
│  │                 │ • Profile │                     │   │
│  │                 │ • Stats   │                     │   │
│  │                 │ • History │                     │   │
│  │                 └───────────┘                     │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  각 Context는:                                              │
│  • 독립적인 데이터베이스 (Physical Separation)             │
│  • 독립적인 배포 (Microservice)                            │
│  • Domain Event로 통신                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Scan Context의 Aggregate

```python
# domains/scan/models/aggregates.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from domains.scan.models.events import (
    ScanTaskCreated,
    ScanCompleted,
    ScanFailed,
)


@dataclass
class ScanTask:
    """Scan Task Aggregate Root"""
    
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = None
    image_url: str = None
    status: str = "pending"
    
    # 내부 상태
    classification: Optional[dict] = None
    answer: Optional[str] = None
    error_message: Optional[str] = None
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # 도메인 이벤트
    _events: list = field(default_factory=list)
    
    @classmethod
    def create(cls, user_id: UUID, image_url: str) -> "ScanTask":
        """팩토리 메서드: 스캔 태스크 생성"""
        task = cls(
            user_id=user_id,
            image_url=image_url,
            status="pending",
        )
        
        # 도메인 이벤트 발행
        task._events.append(ScanTaskCreated(
            task_id=task.id,
            user_id=user_id,
            image_url=image_url,
            created_at=task.created_at,
        ))
        
        return task
    
    def complete(
        self,
        classification: dict,
        answer: str,
    ) -> None:
        """스캔 완료 처리"""
        if self.status != "processing":
            raise InvalidStateError(f"Cannot complete task in {self.status} state")
        
        self.status = "completed"
        self.classification = classification
        self.answer = answer
        self.completed_at = datetime.utcnow()
        
        # 도메인 이벤트 발행
        self._events.append(ScanCompleted(
            task_id=self.id,
            user_id=self.user_id,
            classification=classification,
            completed_at=self.completed_at,
        ))
    
    def fail(self, error_message: str) -> None:
        """스캔 실패 처리"""
        self.status = "failed"
        self.error_message = error_message
        
        self._events.append(ScanFailed(
            task_id=self.id,
            user_id=self.user_id,
            error_message=error_message,
        ))
    
    def collect_events(self) -> list:
        """이벤트 수집 후 초기화"""
        events = self._events.copy()
        self._events.clear()
        return events
```

### Character Context의 Aggregate

```python
# domains/character/models/aggregates.py

@dataclass
class UserCharacter:
    """User's Character Collection Aggregate Root"""
    
    user_id: UUID
    characters: list[OwnedCharacter] = field(default_factory=list)
    total_points: int = 0
    
    _events: list = field(default_factory=list)
    
    # 불변식: 같은 캐릭터는 중복 소유 불가
    def _validate_no_duplicate(self, character_id: UUID) -> None:
        if any(c.character_id == character_id for c in self.characters):
            raise DuplicateCharacterError()
    
    def grant_character(
        self,
        character_id: UUID,
        character_name: str,
        source: str,  # "scan_reward", "quest", "purchase"
    ) -> None:
        """캐릭터 부여"""
        self._validate_no_duplicate(character_id)
        
        owned = OwnedCharacter(
            character_id=character_id,
            name=character_name,
            acquired_at=datetime.utcnow(),
            source=source,
        )
        self.characters.append(owned)
        
        self._events.append(CharacterGranted(
            user_id=self.user_id,
            character_id=character_id,
            character_name=character_name,
            source=source,
        ))
    
    def add_points(self, points: int, reason: str) -> None:
        """포인트 추가"""
        if points <= 0:
            raise InvalidPointsError("Points must be positive")
        
        self.total_points += points
        
        self._events.append(PointsAdded(
            user_id=self.user_id,
            points=points,
            reason=reason,
            new_total=self.total_points,
        ))
```

### DDD 원칙의 Eco² 적용 (Event Sourcing 전환)

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² Bounded Context Map (TO-BE)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Auth Context                        │   │
│  │                  (Upstream)                          │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │  User Aggregate                             │    │   │
│  │  │  Events: UserRegistered, UserLoggedOut      │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│                            │ Published Language             │
│                            │ (Kafka: eco2.events.auth)      │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Scan Context                        │   │
│  │                (Core Domain)                         │   │
│  │  ┌─────────────────────────────────────────────┐    │   │
│  │  │  ScanTask Aggregate                         │    │   │
│  │  │  Events: ScanCreated, VisionCompleted,      │    │   │
│  │  │          ScanCompleted, ScanFailed          │    │   │
│  │  │                                             │    │   │
│  │  │  Event Store: events + outbox 테이블        │    │   │
│  │  └─────────────────────────────────────────────┘    │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│                            │ Published Language             │
│                            │ (Kafka: eco2.events.scan)      │
│              ┌─────────────┴─────────────┐                 │
│              ▼                           ▼                 │
│  ┌───────────────────────┐   ┌───────────────────────┐    │
│  │   Character Context   │   │     My Context        │    │
│  │   (Supporting)        │   │   (Generic - CQRS)    │    │
│  │                       │   │                       │    │
│  │  UserCharacter Agg    │   │  UserProfile Agg      │    │
│  │  Events:              │   │  = Read Model         │    │
│  │  - CharacterGranted   │   │  (Projection)         │    │
│  │  - PointsAdded        │   │                       │    │
│  │                       │   │  Scan + Character     │    │
│  │  Customer-Supplier    │   │  이벤트 구독하여      │    │
│  │  (Scan → Character)   │   │  뷰 모델 구축         │    │
│  └───────────────────────┘   └───────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Event Sourcing Aggregate 구현

```python
# domains/_shared/aggregate.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic
from uuid import UUID

T = TypeVar('T', bound='DomainEvent')


@dataclass
class Aggregate(ABC, Generic[T]):
    """Event Sourcing Aggregate Base Class"""
    
    id: UUID
    version: int = 0
    _uncommitted_events: list[T] = field(default_factory=list)
    
    @abstractmethod
    def apply(self, event: T) -> None:
        """이벤트를 적용하여 상태 변경 (Event Sourcing 핵심)"""
        pass
    
    def load_from_history(self, events: list[T]) -> None:
        """이벤트 히스토리로부터 상태 재구성"""
        for event in events:
            self.apply(event)
            self.version += 1
    
    def raise_event(self, event: T) -> None:
        """새 이벤트 발생"""
        self.apply(event)
        self._uncommitted_events.append(event)
    
    def collect_uncommitted_events(self) -> list[T]:
        """미커밋 이벤트 수집 후 초기화"""
        events = self._uncommitted_events.copy()
        self._uncommitted_events.clear()
        return events


# domains/scan/aggregates/scan_task.py

@dataclass
class ScanTask(Aggregate[ScanEvent]):
    """Scan Task Aggregate - Event Sourcing"""
    
    user_id: UUID = None
    image_url: str = None
    status: ScanStatus = ScanStatus.PENDING
    classification: dict = None
    
    def apply(self, event: ScanEvent) -> None:
        """이벤트 적용 → 상태 변경"""
        match event:
            case ScanCreated(user_id=uid, image_url=url):
                self.user_id = uid
                self.image_url = url
                self.status = ScanStatus.CREATED
            
            case VisionCompleted(classification=cls):
                self.classification = cls
                self.status = ScanStatus.VISION_DONE
            
            case ScanCompleted():
                self.status = ScanStatus.COMPLETED
            
            case ScanFailed(reason=r):
                self.status = ScanStatus.FAILED
    
    # Command Methods (비즈니스 로직)
    @classmethod
    def create(cls, task_id: UUID, user_id: UUID, image_url: str):
        """Factory Method"""
        task = cls(id=task_id)
        task.raise_event(ScanCreated(
            task_id=task_id,
            user_id=user_id,
            image_url=image_url,
        ))
        return task
    
    def complete_vision(self, classification: dict):
        """Vision 분석 완료"""
        if self.status != ScanStatus.CREATED:
            raise InvalidStateError()
        
        self.raise_event(VisionCompleted(
            task_id=self.id,
            classification=classification,
        ))
```

### CQRS: My Context = Read Model (Projection)

```python
# domains/my/projections/user_profile_projection.py

class UserProfileProjection:
    """My Context = CQRS Read Model"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def handle_scan_completed(self, event: ScanCompleted):
        """Scan 이벤트 → My Read Model 업데이트"""
        await self.db.execute(
            """
            UPDATE user_profiles
            SET total_scans = total_scans + 1,
                last_scan_at = :completed_at,
                categories_scanned = categories_scanned || :category
            WHERE user_id = :user_id
            """,
            {
                "user_id": event.user_id,
                "completed_at": event.completed_at,
                "category": [event.classification["category"]],
            }
        )
    
    async def handle_character_granted(self, event: CharacterGranted):
        """Character 이벤트 → My Read Model 업데이트"""
        await self.db.execute(
            """
            INSERT INTO user_characters (user_id, character_id, acquired_at)
            VALUES (:user_id, :char_id, :acquired_at)
            ON CONFLICT DO NOTHING
            """,
            {
                "user_id": event.user_id,
                "char_id": event.character_id,
                "acquired_at": event.occurred_at,
            }
        )
```

### Command vs Event: Command-Event Separation에서의 DDD

```
┌─────────────────────────────────────────────────────────────┐
│       DDD + Command-Event Separation                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Command (RabbitMQ)              Event (Kafka)              │
│  ──────────────────              ─────────────              │
│                                                             │
│  "이 이미지를 분류해"            "스캔이 완료되었다"        │
│  ProcessImage Task               ScanCompleted Event        │
│                                                             │
│  • Aggregate 내부에서 실행       • Aggregate 경계를 넘음    │
│  • 하나의 Worker가 처리          • 여러 Consumer가 구독     │
│  • Celery Task                   • Kafka Topic              │
│  • 실패 시 재시도 (DLQ)          • Offset 재처리            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Scan Context                       │   │
│  │                                                     │   │
│  │  POST /scan                                         │   │
│  │       │                                             │   │
│  │       ├────────────────────┐                        │   │
│  │       ▼                    ▼                        │   │
│  │  RabbitMQ              Event Store                  │   │
│  │  (ProcessImage)        (ScanCreated)                │   │
│  │       │                    │                        │   │
│  │       │ Celery             │ CDC                    │   │
│  │       ▼                    ▼                        │   │
│  │  AI Worker             Kafka                        │   │
│  │       │                (eco2.events.scan)           │   │
│  │       │ 완료 시            │                        │   │
│  │       ▼                    │                        │   │
│  │  Event Store               │                        │   │
│  │  (ScanCompleted)───────────┘                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                Character Context                     │   │
│  │                                                     │   │
│  │  Kafka Consumer                                     │   │
│  │  (ScanCompleted)                                    │   │
│  │       │                                             │   │
│  │       ▼                                             │   │
│  │  UserCharacter Aggregate                            │   │
│  │  .grant_reward()                                    │   │
│  │       │                                             │   │
│  │       ▼                                             │   │
│  │  Event Store                                        │   │
│  │  (CharacterGranted) → CDC → Kafka                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-------------------|
| **Bounded Context** | 서비스 분리 | + Event Schema = Contract |
| **Aggregate** | 단순 Entity | Event Sourcing Aggregate |
| **Command 처리** | gRPC Handler | RabbitMQ + Celery Worker |
| **Event 발행** | 없음 | Event Store → CDC → Kafka |
| **ID 참조** | gRPC 호출 시 전달 | Event payload에 포함 |
| **Domain Event** | 부분적 | 모든 상태 변경 = Event |
| **결과적 일관성** | Circuit Breaker | Kafka Consumer |
| **Published Language** | gRPC Protobuf | Kafka + Schema Registry |
| **CQRS** | 없음 | My = Kafka Consumer Projection |
| **긴 작업** | gRPC Timeout | Celery Task (분리) |
