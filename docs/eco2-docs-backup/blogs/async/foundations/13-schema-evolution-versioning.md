# Schema Evolution: 이벤트 스키마 버전 관리

> **Part VII: 운영과 품질** | [← 12. Celery](./12-celery-distributed-task-queue.md) | [인덱스](./00-index.md) | [14. Idempotent Consumer →](./14-idempotent-consumer-patterns.md)

> 참고: [Designing Data-Intensive Applications](https://dataintensive.net/) - Martin Kleppmann (O'Reilly, 2017) Ch.4  
> 참고: [Confluent Schema Registry](https://docs.confluent.io/platform/current/schema-registry/)

---

## 들어가며

Event Sourcing과 Event-Driven Architecture에서 **이벤트 스키마는 곧 계약(Contract)**이다. 한번 발행된 이벤트는 Event Store에 영원히 남고, 여러 Consumer가 구독한다.

문제는 비즈니스가 변화한다는 것이다:

```
┌─────────────────────────────────────────────────────────────┐
│                  스키마 변경의 위험                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Day 1: ScanCompleted v1                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ {                                                   │   │
│  │   "task_id": "abc-123",                            │   │
│  │   "category": "plastic"                            │   │
│  │ }                                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Day 100: 요구사항 변경 - 상세 분류 추가                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ {                                                   │   │
│  │   "task_id": "abc-123",                            │   │
│  │   "category": "plastic",                           │   │
│  │   "sub_category": "PET",        ← 신규 필드        │   │
│  │   "confidence": 0.95            ← 신규 필드        │   │
│  │ }                                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  문제:                                                      │
│  • Event Store에는 v1 이벤트가 100만 개 존재               │
│  • 기존 Consumer들은 새 필드를 모름                        │
│  • 새 Consumer는 구 이벤트의 새 필드가 없어서 오류         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Martin Kleppmann은 이 문제를 **"데이터가 코드보다 오래 산다(Data outlives code)"**라고 표현했다.

---

## 호환성의 유형

스키마 변경 시 호환성을 유지하는 방법은 세 가지가 있다.

### Backward Compatibility (하위 호환성)

**새 코드가 구 데이터를 읽을 수 있음**

```
┌─────────────────────────────────────────────────────────────┐
│                 Backward Compatibility                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Event Store                        New Consumer (v2)       │
│  ┌─────────────────────┐           ┌─────────────────────┐ │
│  │ v1: {category}      │ ────────▶ │ 구 이벤트 처리 가능  │ │
│  │ v2: {category,      │ ────────▶ │ 신 이벤트 처리 가능  │ │
│  │     sub_category}   │           │                     │ │
│  └─────────────────────┘           └─────────────────────┘ │
│                                                             │
│  구현 방법:                                                 │
│  • 새 필드에 기본값(default) 지정                          │
│  • 필드 삭제 금지 (또는 optional로 변경)                   │
│                                                             │
│  예시 (새 Consumer 코드):                                  │
│  sub_category = event.get("sub_category", "unknown")       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Forward Compatibility (상위 호환성)

**구 코드가 새 데이터를 읽을 수 있음**

```
┌─────────────────────────────────────────────────────────────┐
│                  Forward Compatibility                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  New Producer (v2)                  Old Consumer (v1)       │
│  ┌─────────────────────┐           ┌─────────────────────┐ │
│  │ {category,          │ ────────▶ │ 모르는 필드 무시    │ │
│  │  sub_category,      │           │ category만 사용     │ │
│  │  confidence}        │           │                     │ │
│  └─────────────────────┘           └─────────────────────┘ │
│                                                             │
│  구현 방법:                                                 │
│  • Consumer가 알 수 없는 필드를 무시하도록 구현             │
│  • 필수 필드 추가 금지                                     │
│                                                             │
│  예시 (구 Consumer 코드):                                  │
│  # sub_category 필드가 있어도 무시하고 category만 사용     │
│  category = event["category"]                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Full Compatibility (완전 호환성)

**양방향 모두 호환**

```
┌─────────────────────────────────────────────────────────────┐
│                   Full Compatibility                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Backward + Forward = Full                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  v1 Event ◀────────────────────────▶ v1 Consumer    │   │
│  │     │                                    │          │   │
│  │     │                                    │          │   │
│  │     ▼                                    ▼          │   │
│  │  v2 Event ◀────────────────────────▶ v2 Consumer    │   │
│  │                                                     │   │
│  │  모든 조합이 동작!                                  │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  가장 안전하지만 제약이 큼:                                 │
│  • 필드 추가: optional + default 필수                      │
│  • 필드 삭제: 불가 (deprecate만 가능)                      │
│  • 필드 타입 변경: 불가                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 호환성 요약

| 변경 유형 | Backward | Forward | Full |
|----------|----------|---------|------|
| **필드 추가 (optional)** | ✅ | ✅ | ✅ |
| **필드 추가 (required)** | ❌ | ✅ | ❌ |
| **필드 삭제** | ✅ | ❌ | ❌ |
| **필드 이름 변경** | ❌ | ❌ | ❌ |
| **타입 변경** | ❌ | ❌ | ❌ |

---

## 스키마 포맷 비교

### JSON (Schema 없음)

```
┌─────────────────────────────────────────────────────────────┐
│                       JSON                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  장점:                                                      │
│  • 사람이 읽기 쉬움                                         │
│  • 스키마 없이 유연하게 사용 가능                           │
│  • 모든 언어에서 지원                                       │
│                                                             │
│  단점:                                                      │
│  • 타입 안정성 없음                                         │
│  • 스키마 강제 불가                                         │
│  • 용량이 큼 (필드명 반복)                                 │
│                                                             │
│  {                                                          │
│    "task_id": "abc-123",     ← 필드명이 매번 포함          │
│    "category": "plastic",                                   │
│    "sub_category": "PET"                                    │
│  }                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### JSON Schema

```
┌─────────────────────────────────────────────────────────────┐
│                    JSON Schema                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  스키마 정의:                                               │
│  {                                                          │
│    "$schema": "https://json-schema.org/draft/2020-12/schema"│
│    "type": "object",                                        │
│    "properties": {                                          │
│      "task_id": {"type": "string"},                        │
│      "category": {"type": "string"},                       │
│      "sub_category": {                                     │
│        "type": "string",                                   │
│        "default": "unknown"      ← 기본값으로 호환성 유지  │
│      }                                                      │
│    },                                                       │
│    "required": ["task_id", "category"]                     │
│  }                                                          │
│                                                             │
│  장점: JSON 유지하면서 검증 가능                           │
│  단점: 직렬화 최적화 없음                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Apache Avro

```
┌─────────────────────────────────────────────────────────────┐
│                      Apache Avro                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  스키마 정의 (.avsc):                                       │
│  {                                                          │
│    "type": "record",                                        │
│    "name": "ScanCompleted",                                │
│    "namespace": "eco2.events.scan",                        │
│    "fields": [                                              │
│      {"name": "task_id", "type": "string"},                │
│      {"name": "category", "type": "string"},               │
│      {                                                      │
│        "name": "sub_category",                             │
│        "type": ["null", "string"],    ← Union: nullable    │
│        "default": null                                     │
│      }                                                      │
│    ]                                                        │
│  }                                                          │
│                                                             │
│  직렬화된 데이터 (바이너리):                                │
│  [schema_id][binary_data]  ← 필드명 없음, 매우 작음        │
│                                                             │
│  장점:                                                      │
│  • 컴팩트한 바이너리 포맷                                  │
│  • Schema Registry와 완벽 통합                             │
│  • 자동 호환성 검사                                        │
│                                                             │
│  단점:                                                      │
│  • 사람이 읽기 어려움                                       │
│  • 디버깅 시 디코딩 필요                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Protocol Buffers (Protobuf)

```
┌─────────────────────────────────────────────────────────────┐
│                    Protocol Buffers                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  스키마 정의 (.proto):                                      │
│  syntax = "proto3";                                         │
│                                                             │
│  message ScanCompleted {                                    │
│    string task_id = 1;        ← 필드 번호로 식별           │
│    string category = 2;                                     │
│    optional string sub_category = 3;                       │
│    optional float confidence = 4;                          │
│  }                                                          │
│                                                             │
│  직렬화된 데이터:                                           │
│  [field_number][type][value]...  ← 필드명 없음             │
│                                                             │
│  장점:                                                      │
│  • 매우 컴팩트                                              │
│  • 강력한 타입 시스템                                      │
│  • gRPC와 통합                                             │
│                                                             │
│  단점:                                                      │
│  • 코드 생성 필요                                          │
│  • Schema Registry 통합이 Avro만큼 성숙하지 않음           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 포맷 선택 가이드

| 기준 | JSON | JSON Schema | Avro | Protobuf |
|------|------|-------------|------|----------|
| **가독성** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| **크기** | 큼 | 큼 | 작음 | 매우 작음 |
| **스키마 강제** | ❌ | ✅ | ✅ | ✅ |
| **Schema Registry** | ❌ | ⚠️ | ⭐⭐⭐ | ⭐⭐ |
| **Kafka 통합** | ✅ | ✅ | ⭐⭐⭐ | ⭐⭐ |
| **학습 곡선** | 낮음 | 낮음 | 중간 | 중간 |

---

## Schema Registry

### 왜 필요한가?

```
┌─────────────────────────────────────────────────────────────┐
│               Schema Registry의 역할                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Without Registry:                                          │
│  ┌─────────────┐                    ┌─────────────┐        │
│  │  Producer   │ ── raw JSON ────▶ │  Consumer   │        │
│  │  (스키마?)  │                    │  (파싱 실패)│        │
│  └─────────────┘                    └─────────────┘        │
│                                                             │
│  With Registry:                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│  │  Producer   │───▶│   Schema    │◀───│  Consumer   │    │
│  │             │    │  Registry   │    │             │    │
│  └──────┬──────┘    │             │    └──────┬──────┘    │
│         │           │ • 스키마 저장│           │           │
│         │           │ • 버전 관리 │           │           │
│         │           │ • 호환성 검사│           │           │
│         │           └──────┬──────┘           │           │
│         │                  │                   │           │
│         └──────────────────┼───────────────────┘           │
│                            ▼                               │
│                    ┌─────────────┐                        │
│                    │    Kafka    │                        │
│                    │  [id][data] │ ← 스키마 ID만 포함     │
│                    └─────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Confluent Schema Registry

```
┌─────────────────────────────────────────────────────────────┐
│             Confluent Schema Registry 동작                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Producer가 스키마 등록                                  │
│  POST /subjects/scan-completed-value/versions               │
│  {                                                          │
│    "schema": "{\"type\":\"record\",\"name\":...}"          │
│  }                                                          │
│  → 응답: {"id": 1}                                         │
│                                                             │
│  2. 메시지 발행 (schema_id 포함)                           │
│  [0x00][schema_id=1][avro_binary_data]                     │
│   │        │              │                                │
│   │        │              └── 실제 데이터                  │
│   │        └── 4바이트 스키마 ID                           │
│   └── Magic Byte                                           │
│                                                             │
│  3. Consumer가 스키마 조회                                  │
│  GET /schemas/ids/1                                        │
│  → 캐시하여 재사용                                         │
│                                                             │
│  4. 호환성 검사 (자동)                                     │
│  PUT /config/scan-completed-value                          │
│  {"compatibility": "BACKWARD"}                             │
│  → 비호환 스키마 등록 시 거부                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 호환성 모드 설정

```python
# Schema Registry 호환성 모드

# BACKWARD (기본값): 새 스키마가 구 데이터를 읽을 수 있어야 함
# → Consumer 먼저 배포 가능

# FORWARD: 구 스키마가 새 데이터를 읽을 수 있어야 함
# → Producer 먼저 배포 가능

# FULL: 양방향 호환
# → 배포 순서 무관

# NONE: 호환성 검사 안 함 (위험!)

# 설정 예시 (REST API)
PUT /config/eco2.events.scan-value
{
  "compatibility": "BACKWARD"
}
```

---

## 버전 관리 전략

### 1. Upcasting (읽기 시점 변환)

```
┌─────────────────────────────────────────────────────────────┐
│                      Upcasting                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Event Store                        Consumer                │
│  ┌─────────────────────┐           ┌─────────────────────┐ │
│  │ v1: {category}      │           │                     │ │
│  │                     │           │   Upcaster          │ │
│  │ v2: {category,      │──읽기───▶│   v1 → v2 변환      │ │
│  │     sub_category}   │           │                     │ │
│  │                     │           │   항상 v2로 처리    │ │
│  └─────────────────────┘           └─────────────────────┘ │
│                                                             │
│  구현:                                                      │
│  class ScanCompletedUpcaster:                              │
│      def upcast(self, event: dict, version: int) -> dict:  │
│          if version == 1:                                  │
│              event["sub_category"] = "unknown"             │
│              event["confidence"] = 0.0                     │
│          return event                                       │
│                                                             │
│  장점: Event Store 변경 없음, 점진적 마이그레이션          │
│  단점: 읽기 성능 오버헤드                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. Event Transformation (일괄 변환)

```
┌─────────────────────────────────────────────────────────────┐
│               Event Transformation                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  마이그레이션 작업:                                         │
│                                                             │
│  Event Store (v1)         Event Store (v2)                 │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │ {category}      │     │ {category,      │               │
│  │ {category}      │────▶│  sub_category}  │               │
│  │ {category}      │     │ {category,      │               │
│  │       ...       │     │  sub_category}  │               │
│  └─────────────────┘     └─────────────────┘               │
│                                                             │
│  # 마이그레이션 스크립트                                    │
│  async def migrate_events():                               │
│      async for event in event_store.read_all("ScanTask"):  │
│          if event.version == 1:                            │
│              new_event = transform_v1_to_v2(event)         │
│              await event_store.append(new_event)           │
│                                                             │
│  장점: 읽기 성능 유지                                       │
│  단점: 마이그레이션 중 다운타임 또는 복잡한 동시성 처리    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. Polymorphic Handlers (다형성 핸들러)

```
┌─────────────────────────────────────────────────────────────┐
│               Polymorphic Handlers                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  버전별 핸들러:                                             │
│                                                             │
│  class ScanCompletedHandler:                               │
│      @handle("ScanCompleted", version=1)                   │
│      def handle_v1(self, event):                           │
│          # v1 전용 로직                                    │
│          self.process(event["category"], None)             │
│                                                             │
│      @handle("ScanCompleted", version=2)                   │
│      def handle_v2(self, event):                           │
│          # v2 전용 로직                                    │
│          self.process(                                      │
│              event["category"],                            │
│              event["sub_category"]                         │
│          )                                                  │
│                                                             │
│  장점: 버전별 명시적 처리, 복잡한 변환 가능                │
│  단점: 코드 복잡성 증가                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 전략 선택 가이드

| 상황 | 추천 전략 |
|------|----------|
| **필드 추가 (optional)** | Upcasting |
| **대규모 스키마 변경** | Event Transformation |
| **버전별 로직이 완전히 다름** | Polymorphic Handlers |
| **빠른 읽기가 중요** | Event Transformation |
| **무중단 운영 필요** | Upcasting |

---

## CloudEvents 표준

### 왜 CloudEvents인가?

```
┌─────────────────────────────────────────────────────────────┐
│                    CloudEvents 표준                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CNCF(Cloud Native Computing Foundation)가 정의한          │
│  이벤트 메타데이터 표준                                    │
│                                                             │
│  Before (각자 다른 포맷):                                   │
│  Service A: {"eventType": "...", "data": {...}}            │
│  Service B: {"type": "...", "payload": {...}}              │
│  Service C: {"kind": "...", "body": {...}}                 │
│                                                             │
│  After (CloudEvents 표준):                                  │
│  {                                                          │
│    "specversion": "1.0",                                   │
│    "type": "eco2.scan.completed",                          │
│    "source": "/scan/tasks/abc-123",                        │
│    "id": "evt-456",                                        │
│    "time": "2025-12-19T10:00:00Z",                         │
│    "datacontenttype": "application/json",                  │
│    "data": {                                               │
│      "task_id": "abc-123",                                 │
│      "category": "plastic"                                 │
│    }                                                        │
│  }                                                          │
│                                                             │
│  장점:                                                      │
│  • 서비스 간 일관된 메타데이터                             │
│  • 라우팅, 필터링, 추적 용이                               │
│  • 다양한 프로토콜 지원 (HTTP, Kafka, AMQP)               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### CloudEvents 필수 속성

| 속성 | 설명 | 예시 |
|------|------|------|
| **specversion** | CloudEvents 버전 | "1.0" |
| **type** | 이벤트 유형 | "eco2.scan.completed" |
| **source** | 이벤트 발생 위치 | "/scan/tasks/abc-123" |
| **id** | 고유 식별자 | "evt-456" |

### 선택 속성

| 속성 | 설명 | 예시 |
|------|------|------|
| **time** | 발생 시각 | "2025-12-19T10:00:00Z" |
| **datacontenttype** | 데이터 형식 | "application/json" |
| **dataschema** | 스키마 URI | "https://eco2.app/schemas/scan/v2" |
| **subject** | 이벤트 대상 | "user-789" |

---

## 참고 자료

- [Designing Data-Intensive Applications](https://dataintensive.net/) - Martin Kleppmann, Ch.4 Encoding and Evolution
- [Confluent Schema Registry](https://docs.confluent.io/platform/current/schema-registry/)
- [CloudEvents Specification](https://cloudevents.io/)
- [Avro Specification](https://avro.apache.org/docs/current/spec.html)

---

## 부록: Eco² 적용 포인트

### ScanCompleted 이벤트 스키마 설계

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² Event Schema 설계                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CloudEvents 형식 + JSON Schema:                           │
│                                                             │
│  {                                                          │
│    // CloudEvents 메타데이터                                │
│    "specversion": "1.0",                                   │
│    "type": "eco2.scan.completed",                          │
│    "source": "/scan/tasks",                                │
│    "id": "evt-${uuid}",                                    │
│    "time": "2025-12-19T10:00:00Z",                         │
│    "datacontenttype": "application/json",                  │
│    "dataschema": "https://eco2.app/schemas/scan/v2",       │
│                                                             │
│    // Eco² 확장 속성                                        │
│    "eco2traceid": "trace-abc-123",     ← 분산 추적용       │
│    "eco2userid": "user-789",           ← 사용자 컨텍스트   │
│                                                             │
│    // 비즈니스 데이터                                       │
│    "data": {                                               │
│      "task_id": "abc-123",                                 │
│      "category": "plastic",                                │
│      "sub_category": "PET",            ← v2 추가 필드      │
│      "confidence": 0.95,               ← v2 추가 필드      │
│      "answer": "..."                                       │
│    }                                                        │
│  }                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Upcaster 구현

```python
# domains/_shared/events/upcasters.py

from typing import Dict, Any

class ScanCompletedUpcaster:
    """ScanCompleted 이벤트 버전 변환"""
    
    def upcast(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """모든 버전을 최신 버전(v2)으로 변환"""
        
        version = event.get("_version", 1)
        data = event.get("data", event)
        
        if version == 1:
            # v1 → v2: 새 필드 기본값 추가
            data.setdefault("sub_category", "unknown")
            data.setdefault("confidence", 0.0)
        
        return {
            **event,
            "data": data,
            "_version": 2,
        }


class EventUpcasterRegistry:
    """이벤트 타입별 Upcaster 관리"""
    
    upcasters = {
        "eco2.scan.completed": ScanCompletedUpcaster(),
        "eco2.character.granted": CharacterGrantedUpcaster(),
    }
    
    @classmethod
    def upcast(cls, event_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
        upcaster = cls.upcasters.get(event_type)
        if upcaster:
            return upcaster.upcast(event)
        return event
```

### Kafka Consumer에서 Upcasting

```python
# domains/character/consumers/event_consumer.py

class CharacterEventConsumer:
    async def handle_message(self, message: KafkaMessage):
        event_type = message.headers.get("ce_type")
        raw_event = json.loads(message.value())
        
        # 1. Upcasting - 구 이벤트를 최신 버전으로 변환
        event = EventUpcasterRegistry.upcast(event_type, raw_event)
        
        # 2. 이후 로직은 항상 최신 버전 기준
        if event_type == "eco2.scan.completed":
            await self.handle_scan_completed(event)
    
    async def handle_scan_completed(self, event: dict):
        # 항상 v2 스키마 기준으로 처리
        category = event["data"]["category"]
        sub_category = event["data"]["sub_category"]  # v1도 upcasting으로 존재
        confidence = event["data"]["confidence"]
        
        # 보상 지급 로직...
```

### AS-IS vs TO-BE

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-----------------------------------|
| **스키마 정의** | .proto 파일 | CloudEvents + JSON Schema |
| **버전 관리** | proto 파일 버전 | Schema Registry + Upcasting |
| **호환성 검사** | 수동 (proto-lint) | 자동 (Registry 호환성 모드) |
| **마이그레이션** | Breaking Change | Backward Compatible |
| **메타데이터** | gRPC Metadata | CloudEvents 표준 속성 |
| **확장성** | 커스텀 | eco2* 확장 속성 |
