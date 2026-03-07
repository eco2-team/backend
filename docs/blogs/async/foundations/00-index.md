# Eco² Foundations: 이론적 기반 문서 인덱스

> Event-Driven Architecture + Command-Event Separation을 위한 핵심 이론 정리

---

## 개요

이 문서들은 Eco² 아키텍처의 **이론적 기반**을 제공한다. 각 문서는 원전(original source)을 중심으로 핵심 개념을 정리하고, Eco²에 어떻게 적용되는지 설명한다.

### 아키텍처 전환: gRPC → Command-Event Separation

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² Command-Event Separation                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Command (RabbitMQ + Celery)       Event (Kafka + CDC)      │
│  ────────────────────────────      ──────────────────       │
│                                                             │
│  "이 이미지를 분류해"              "스캔이 완료되었다"       │
│  ProcessImage Task                 ScanCompleted Event      │
│                                                             │
│  • 하나의 Worker가 처리            • 여러 Consumer가 구독   │
│  • 처리 후 삭제                    • 영구 보존 (Replay)     │
│  • Retry/DLQ 내장                  • Offset 기반 재처리     │
│                                                             │
│  Part III: 메시징 패턴              Part I, II: 이벤트 기반 │
│  Part V: 분산 트랜잭션              Part VI: 이벤트 발행    │
│  Part IV: DDD Aggregate             Part VII: 운영/품질     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Part I: 로그와 스트리밍 기초

> Kafka의 근간이 되는 "The Log" 개념

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 01 | [The Log](./01-the-log-jay-kreps.md) | Jay Kreps (2013) | Append-only Log, Kafka 설계 철학 |

**Eco² 적용**: Kafka를 Event Bus로 사용, CDC를 통한 Event 발행

---

## Part II: 이벤트 기반 아키텍처

> Event Sourcing + CQRS의 이론적 토대

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 02 | [Event Sourcing](./02-event-sourcing-martin-fowler.md) | Martin Fowler (2005) | 상태 대신 이벤트 저장, Replay |
| 03 | [CQRS](./03-cqrs-martin-fowler.md) | Martin Fowler (2011) | Command/Query 분리, Read Model |

**Eco² 적용**: Event Store + Kafka Projection = CQRS, My Service = Read Model

---

## Part III: 메시징 패턴

> Enterprise Integration Patterns + AMQP + Task Queue

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 05 | [Enterprise Integration Patterns](./05-enterprise-integration-patterns.md) | Hohpe & Woolf (2003) | 65개 메시징 패턴 |
| 11 | [AMQP / RabbitMQ](./11-amqp-rabbitmq.md) | AMQP WG (2003) | Exchange, Queue, Routing |
| 12 | [Celery](./12-celery-distributed-task-queue.md) | Ask Solem (2009) | Python Task Queue, Canvas |

**Eco² 적용**: RabbitMQ + Celery = AI 파이프라인 Task Queue

---

## Part IV: 도메인 주도 설계

> DDD Aggregate + Bounded Context

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 10 | [DDD Aggregate](./10-ddd-aggregate-eric-evans.md) | Eric Evans (2003) | Aggregate Root, 트랜잭션 경계 |
| 04 | [Uber DOMA](./04-uber-doma.md) | Uber Engineering (2020) | Domain Gateway, 대규모 마이크로서비스 |

**Eco² 적용**: 각 도메인 = Bounded Context, Aggregate = Event Sourcing 단위

---

## Part V: 분산 트랜잭션

> 2PC 대신 Saga와 Eventual Consistency

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 06 | [Life Beyond Distributed Transactions](./06-life-beyond-distributed-transactions.md) | Pat Helland (2007) | Entity, Activity, 멱등성 |
| 07 | [Sagas](./07-sagas-garcia-molina.md) | Garcia-Molina (1987) | Long-lived Transactions, 보상 트랜잭션 |

**Eco² 적용**: Celery Task Chain = Saga, Kafka Event = 도메인 간 통신

---

## Part VI: 이벤트 발행

> Transactional Outbox + CDC

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 08 | [Transactional Outbox](./08-transactional-outbox.md) | Chris Richardson (2018) | Outbox 테이블, At-Least-Once |
| 09 | [Debezium Outbox Event Router](./09-debezium-outbox-event-router.md) | Gunnar Morling (2019) | CDC, WAL Capture |

**Eco² 적용**: Event Store + Outbox → Debezium CDC → Kafka

---

## Part VII: 운영과 품질

> 프로덕션 운영을 위한 패턴과 도구

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 13 | [Schema Evolution](./13-schema-evolution-versioning.md) | Confluent/Kleppmann | 호환성, Upcasting |
| 14 | [Idempotent Consumer](./14-idempotent-consumer-patterns.md) | EIP/Richardson | Inbox, Deduplication |
| 15 | [Distributed Tracing](./15-distributed-tracing-opentelemetry.md) | CNCF/W3C | OpenTelemetry, Context 전파 |

**Eco² 적용**: CloudEvents + Schema Registry, Redis 멱등성, Grafana Tempo

---

## Part VIII: 인프라 스케일링

> Kubernetes 노드/Pod 오토스케일링

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 16 | [Karpenter](./16-karpenter-node-autoscaling.md) | AWS/CNCF (2021) | Node Autoscaling, EC2 Fleet API, Bin Packing |

**Eco² 적용**: KEDA(Pod) + Karpenter(Node) 통합으로 완전한 오토스케일링

---

## Part IX: LLM 추론 전략

> 대규모 언어 모델의 컨텍스트 처리와 추론 최적화

| # | 문서 | 원저자 | 핵심 개념 |
|---|------|--------|-----------|
| 17 | [Recursive Language Models](./17-recursive-language-models.md) | Zhang, Kraska, Khattab (2025) | Context Rot 해결, 분할 정복, 재귀적 자기 호출 |

**Eco² 적용**: 
- Chat 서비스의 긴 문서 분석에 RLM 패턴 적용
- LangGraph 노드에서 재귀적 문서 처리 구현
- 컨텍스트 윈도우 한계를 넘어서는 입력 처리

---

## 읽기 순서 추천

### 초심자

```
01 (The Log)
    → 02 (Event Sourcing)
    → 03 (CQRS)
    → 05 (EIP)
    → 12 (Celery)
```

### 분산 시스템 이해

```
06 (Life Beyond Distributed Transactions)
    → 07 (Sagas)
    → 10 (DDD Aggregate)
    → 08 (Transactional Outbox)
    → 09 (Debezium CDC)
```

### 메시징 심화

```
05 (EIP)
    → 11 (AMQP/RabbitMQ)
    → 12 (Celery)
    → 01 (The Log)
```

### 프로덕션 운영

```
13 (Schema Evolution)
    → 14 (Idempotent Consumer)
    → 15 (Distributed Tracing)
```

### LLM 기반 서비스 (Chat, Scan)

```
17 (Recursive Language Models)
    → docs/blogs/applied/01-langgraph-reference.md
    → docs/blogs/applied/02-langgraph-streaming-patterns.md
```

---

## 문서 간 관계도

```
┌─────────────────────────────────────────────────────────────┐
│                    Foundation 문서 관계도                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Part I: 로그                      │   │
│  │  ┌────────────────────────────────────────────────┐ │   │
│  │  │ 01. The Log (Jay Kreps)                        │ │   │
│  │  │     └──▶ Kafka 설계의 근간                     │ │   │
│  │  └────────────────────────────────────────────────┘ │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │               Part II: 이벤트 기반                   │   │
│  │  ┌─────────────────┐    ┌─────────────────┐        │   │
│  │  │ 02. Event       │    │ 03. CQRS        │        │   │
│  │  │     Sourcing    │───▶│ (읽기/쓰기 분리)│        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │                 Part IV: DDD                         │   │
│  │  ┌─────────────────┐    ┌─────────────────┐        │   │
│  │  │ 10. DDD         │    │ 04. Uber DOMA   │        │   │
│  │  │     Aggregate   │───▶│ (대규모 적용)   │        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │               Part V: 분산 트랜잭션                  │   │
│  │  ┌─────────────────┐    ┌─────────────────┐        │   │
│  │  │ 06. Life Beyond │    │ 07. Sagas       │        │   │
│  │  │     Distributed │───▶│ (보상 트랜잭션) │        │   │
│  │  │     Transactions│    │                 │        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │               Part VI: 이벤트 발행                   │   │
│  │  ┌─────────────────┐    ┌─────────────────┐        │   │
│  │  │ 08. Transactional│   │ 09. Debezium    │        │   │
│  │  │     Outbox       │──▶│     CDC         │        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │               Part III: 메시징 패턴                  │   │
│  │  ┌─────────────────┐                               │   │
│  │  │ 05. Enterprise  │                               │   │
│  │  │     Integration │                               │   │
│  │  │     Patterns    │                               │   │
│  │  └────────┬────────┘                               │   │
│  │           │                                         │   │
│  │  ┌────────▼────────┐    ┌─────────────────┐        │   │
│  │  │ 11. AMQP/       │    │ 12. Celery      │        │   │
│  │  │     RabbitMQ    │───▶│ (Task Queue)    │        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│  ┌─────────────────────────▼───────────────────────────┐   │
│  │               Part VII: 운영과 품질                  │   │
│  │  ┌─────────────────┐                               │   │
│  │  │ 13. Schema      │                               │   │
│  │  │     Evolution   │                               │   │
│  │  └────────┬────────┘                               │   │
│  │           │                                         │   │
│  │  ┌────────▼────────┐    ┌─────────────────┐        │   │
│  │  │ 14. Idempotent  │    │ 15. Distributed │        │   │
│  │  │     Consumer    │───▶│     Tracing     │        │   │
│  │  └─────────────────┘    └─────────────────┘        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 버전 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-12-19 | 1.0 | 인덱스 생성, Part 구조화 |
| 2025-12-19 | 1.1 | Part VII (운영과 품질) 추가: Schema Evolution, Idempotent Consumer, Distributed Tracing |
| 2026-01-09 | 1.2 | Part IX (LLM 추론 전략) 추가: Recursive Language Models |

