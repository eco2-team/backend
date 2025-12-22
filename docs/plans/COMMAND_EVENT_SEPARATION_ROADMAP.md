# Command-Event Separation 로드맵

> RabbitMQ(Command) + Kafka(Event) 아키텍처 구현 계획

## 핵심 원칙

| 구분 | RabbitMQ | Kafka |
|------|----------|-------|
| **역할** | Command (일감) | Event (사실 기록) |
| **메시지** | "해라" | "일어났다" |
| **처리** | 1개 Worker | N개 Consumer |
| **수명** | 처리 후 삭제 | 영구 보존 |

---

## Phase 1: RabbitMQ (Command)

### 상태: 🚧 진행 중

| 작업 | 상태 | 브랜치 |
|------|------|--------|
| RabbitMQ Operator ArgoCD 통합 | ✅ 완료 | `infra/rabbitmq-operator` |
| cert-manager 추가 | ✅ 완료 | `infra/rabbitmq-operator` |
| Topology (Queue/Exchange) 정의 | ✅ 완료 | `infra/rabbitmq-operator` |
| Network Policy | ✅ 완료 | `infra/rabbitmq-operator` |
| **인프라 배포** | ⏳ 대기 | PR → develop 머지 필요 |
| Celery Worker 구현 | ⏳ 대기 | `feat/celery-rabbitmq-taskqueue` |
| Scan API 비동기 전환 | ⏳ 대기 | - |
| ext-authz Local Cache + Fanout | ⏳ 대기 | - |

### Topology 설계

```
RabbitMQ (Command)
├── scan.direct → scan.vision, scan.rule, scan.answer (Celery Task)
├── reward.direct → reward.character (리워드 지급)
├── authz.fanout → ext-authz 로컬캐시 동기화 (Broadcast)
├── dlx → dlq.* (Dead Letter)
└── celery → celery (Celery 기본)
```

---

## Phase 2: Kafka (Event/CDC)

### 상태: 📋 계획

| 작업 | 상태 | 비고 |
|------|------|------|
| Strimzi Kafka Operator | 📋 계획 | Phase 1 완료 후 |
| Debezium CDC Connector | 📋 계획 | PostgreSQL WAL |
| Character → My 이벤트 | 📋 계획 | `CharacterGranted` Topic |
| Auth CQRS (CDC) | 📋 계획 | `auth.users` Topic |

### Topology 설계

```
Kafka (Event/CDC)
├── character.events → CharacterGranted, CharacterUpdated
├── auth.users → CDC (INSERT/UPDATE/DELETE)
└── scan.completed → ScanCompleted (향후)
```

---

## 즉시 다음 작업

1. **`infra/rabbitmq-operator` PR 생성 및 머지**
2. **ArgoCD Sync → RabbitMQ 클러스터 배포**
3. **Celery Worker 구현 재개** (`feat/celery-rabbitmq-taskqueue`)

---

## 참고

- [비동기 전환 #0: RabbitMQ + Celery 아키텍처](../blogs/async/00-rabbitmq-celery-architecture.md)
- [비동기 전환 #1: MQ 적용 가능 영역](../blogs/async/01-mq-optimization-opportunities.md)
- [비동기 전환 #2: MQ 구현 상세](../blogs/async/02-mq-architecture-design.md)
