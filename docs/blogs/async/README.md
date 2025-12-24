# 이코에코(Eco²) 비동기 전환 시리즈

> RabbitMQ + Celery 기반 비동기 아키텍처 전환 과정을 기록합니다.

## 시리즈 목차

| # | 제목 | 상태 | 주요 내용 |
|---|------|------|----------|
| 0 | [RabbitMQ + Celery 아키텍처 설계](./00-rabbitmq-celery-architecture.md) | ✅ 완료 | MQ 선정(vs NATS, Kafka), 의사결정 프레임워크, 업계 사례 |
| 1 | [MQ 적용 가능 영역 분석](./01-mq-optimization-opportunities.md) | ✅ 완료 | ext-authz 로컬 캐시, Character→My 동기화, gRPC 전환 분석 |
| 2 | [MQ 구현 상세](./02-mq-architecture-design.md) | ✅ 완료 | Kubernetes 배포 전략, 매니페스트 설계, 모니터링 |
| 3 | [RabbitMQ 인프라 구축](./03-rabbitmq-infrastructure.md) | ✅ 완료 | Operator 배포, Topology CRs, Network Policy, 검증 결과 |
| 4 | [RabbitMQ 트러블슈팅](./04-rabbitmq-troubleshooting.md) | ✅ 완료 | Operator Path, Toleration, Namespace 충돌, 401 인증, Finalizer |
| 5 | [Celery 기반 Scan Pipeline](./05-celery-scan-pipeline.md) | ✅ 완료 | AI 파이프라인 비동기화, Celery Chain, DLQ Beat 전략 |
| 9 | [Celery Chain 고도화](./09-celery-chain-events-part2.md) | ✅ 완료 | Stateless 응답 경로, Worker 4개 분리, Classic Queue 전환 |
| 10 | [Worker 로컬 캐시와 Fanout 동기화](./10-local-cache-event-broadcast.md) | ✅ 완료 | 인메모리 캐시, Fanout Exchange, PostSync Hook 워밍업 |
| 11 | [보상 판정과 Persistence 분리](./11-reward-persistence-separation-part2.md) | ✅ 완료 | Fire&Forget 저장, 도메인 간 통신, Eventual Consistency |
| 12 | [Celery Batches와 멱등성 처리](./12-batch-processing-idempotency.md) | ✅ 완료 | celery-batches, Bulk INSERT, ON CONFLICT DO NOTHING |
| 13 | [RabbitMQ/Celery 시스템 전체 분석](./13-rabbitmq-celery-system-analysis.md) | ✅ 완료 | 전체 아키텍처, Exchanges/Queues, Workers, Task Flow, DLQ |
| 14 | [Celery + RabbitMQ 트러블슈팅](./14-celery-rabbitmq-troubleshooting.md) | ✅ 완료 | Quorum Queue 호환성, 도메인 간 의존성, Fanout 브로드캐스트 |

---

## 이론적 기초 (Foundations)

EDA, MQ, 마이크로서비스 아키텍처의 핵심 패턴과 이론적 배경을 **한국 독자를 위한 학습 자료**로 정리합니다.

원문의 핵심 개념을 쉽게 풀어서 설명하고, Eco² 적용 포인트는 부록으로 분리되어 있습니다.

| # | 제목 | 원문 | 핵심 내용 |
|---|------|------|----------|
| 1 | [The Log](./foundations/01-the-log-jay-kreps.md) | [Jay Kreps, LinkedIn 2013](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying) | 로그 데이터 구조, Log↔Table 이중성, 중앙 로그 허브 |
| 2 | [Event Sourcing](./foundations/02-event-sourcing-martin-fowler.md) | [Martin Fowler](https://martinfowler.com/eaaDev/EventSourcing.html) | 상태 대신 이벤트 저장, 시간 여행, 스냅샷 |
| 3 | [CQRS](./foundations/03-cqrs-martin-fowler.md) | [Martin Fowler](https://martinfowler.com/bliki/CQRS.html) | Command/Query 분리, 복잡도 트레이드오프 |
| 4 | [Uber DOMA](./foundations/04-uber-doma.md) | [Uber Engineering 2020](https://www.uber.com/blog/microservice-architecture/) | Domain, Layer, Gateway, Extension 원칙 |
| 5 | [Enterprise Integration Patterns](./foundations/05-enterprise-integration-patterns.md) | Gregor Hohpe, Bobby Woolf (2003) | Pub/Sub, Competing Consumers, DLQ, Idempotency |

---

## 기술 스택

| 구성 요소 | 기술 | 버전 |
|----------|------|------|
| Message Broker | RabbitMQ | 4.0+ |
| Task Queue | Celery | 5.3+ |
| Result Backend | Redis | 7.0+ |
| API Framework | FastAPI | 0.100+ |
| Kubernetes Operator | RabbitMQ Cluster Operator | 2.11+ |
| Topology Operator | Messaging Topology Operator | 1.15+ |
| GitOps | ArgoCD | 2.13+ |

---

## 현재 진행 상황

### Phase 1: RabbitMQ 인프라 (완료)

- [x] RabbitMQ Cluster Operator 배포
- [x] Messaging Topology Operator 배포
- [x] RabbitmqCluster CR (dev: 1 replica)
- [x] Topology CRs (1 Vhost + 5 Exchanges + 10 Queues + 10 Bindings)
- [x] Network Policy 구성
- [x] Istio Sidecar 통합

### Phase 1: Celery Worker (완료)

- [x] RabbitMQ ServiceMonitor 추가
- [x] Celery 공통 모듈 개발 (BaseTask, WebhookTask, CelerySettings)
- [x] scan-worker Deployment 작성
- [x] character-api Reward Consumer 구현
- [x] Grafana RabbitMQ 대시보드 추가

### Phase 2: Pipeline 큐 분리 (예정)

- [ ] 4단계 Celery Chain 구현 (vision → rule → answer → reward)
- [ ] DLQ 재처리 Task (Celery Beat)
- [ ] Archive Queue 생성
- [ ] 단계별 메트릭 수집

### Phase 1: ext-authz 캐시 동기화 (예정)

- [ ] authz.fanout Exchange 연동
- [ ] ext-authz Go AMQP Consumer 구현
- [ ] Blacklist 이벤트 발행/구독 테스트

---

## 핵심 참고 자료

### 1차 지식 공급자 (Primary Sources)

| 자료 | 저자 | 핵심 개념 |
|------|------|----------|
| [The Log](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying) | Jay Kreps | 로그 = 분산 시스템의 핵심 추상화 |
| [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) | Martin Fowler | 상태 대신 이벤트 시퀀스 저장 |
| [CQRS](https://martinfowler.com/bliki/CQRS.html) | Martin Fowler | Command/Query 모델 분리, 경고 |
| [Uber DOMA](https://www.uber.com/blog/microservice-architecture/) | Uber Engineering | 도메인 지향 MSA |
| [EIP](https://www.enterpriseintegrationpatterns.com/) | Hohpe, Woolf | 메시징 패턴의 표준 어휘 |

### 공식 문서

- [Celery Documentation](https://docs.celeryq.dev/)
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [RabbitMQ Cluster Operator](https://www.rabbitmq.com/kubernetes/operator/operator-overview)
- [Messaging Topology Operator](https://www.rabbitmq.com/kubernetes/operator/using-topology-operator)

### 서적

- **Enterprise Integration Patterns** - Gregor Hohpe, Bobby Woolf (2003)
- **Designing Data-Intensive Applications** - Martin Kleppmann (2017)
- **Building Microservices** - Sam Newman (2021, 2nd Ed)
- **Domain-Driven Design** - Eric Evans (2003)
- **I Heart Logs** - Jay Kreps (2014)
