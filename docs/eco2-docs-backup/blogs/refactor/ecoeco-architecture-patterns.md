# 이코에코(Eco²) 아키텍처 패턴 종합

이코에코 프로젝트에 적용된 설계 패턴을 백엔드/인프라/Observability 레이어별로 정리한다.

---

## 핵심 아키텍처 패턴

시스템의 안정성, 확장성, 운영 효율성에 가장 큰 영향을 미치는 핵심 패턴들이다.

| 패턴 | 레이어 | 적용 위치 | 핵심 역할 |
|------|--------|-----------|-----------|
| **Circuit Breaker** | Backend | `domains/character/rpc/my_client.py` | 외부 서비스 장애 시 fail-fast, 시스템 전체 안정성 보장 |
| **Strategy** | Backend | `domains/character/services/evaluators/` | 리워드 평가 로직 확장성 (OCP 준수) |
| **Cache-Aside + Graceful Degradation** | Backend | `domains/character/core/cache.py` | 성능 최적화 + 장애 시에도 서비스 유지 |
| **Ambassador (ext-authz)** | Infra | `workloads/domains/ext-authz/` | API Gateway 레벨 인증 오프로딩 |
| **Service Mesh (Istio)** | Infra | `workloads/routing/*/base/virtual-service.yaml` | 트래픽 관리, mTLS, 라우팅 |
| **GitOps + ApplicationSet** | Infra | `clusters/dev/apps/40-apis-appset.yaml` | 선언적 배포, 환경별 자동화 |
| **Distributed Tracing** | Observability | `domains/*/core/tracing.py` | 서비스 간 요청 추적, 병목 분석 |
| **Structured Logging (ECS)** | Observability | `domains/*/core/logging.py` | 로그 파싱, 검색, 상관관계 분석 |

---

## 백엔드 레이어

| 패턴 | 적용 위치 | 설명 |
|------|----------|------|
| **Strategy** | `domains/character/services/evaluators/base.py`, `scan.py` | 보상 평가 로직 분리, OCP 준수 |
| **Circuit Breaker** | `domains/character/rpc/my_client.py` | 외부 서비스 장애 시 fail-fast (aiobreaker) |
| **Cache-Aside** | `domains/character/core/cache.py` | Redis 캐시 + Graceful Degradation |
| **Repository** | `domains/*/repositories/` (14개 파일) | 데이터 접근 추상화 (SQLAlchemy) |
| **Registry** | `domains/auth/services/providers/registry.py`, `domains/character/services/evaluators/registry.py` | Provider/Evaluator 등록 및 조회 |
| **Template Method** | `domains/auth/services/providers/base.py`, `domains/character/services/evaluators/base.py` | OAuth/평가 흐름 템플릿화 |
| **Singleton** | `domains/*/core/config.py` (`@lru_cache`), `domains/*/rpc/*_client.py` | 설정 및 gRPC 클라이언트 단일 인스턴스 |
| **Lazy Initialization** | `domains/character/core/cache.py`, `domains/character/rpc/my_client.py` | Redis client, gRPC channel 지연 초기화 |
| **Dependency Injection** | FastAPI `Depends()` | 서비스/리포지토리 주입 |
| **DTO (Data Transfer Object)** | `domains/*/schemas/` | Pydantic 모델로 계층 간 데이터 전달 |
| **Retry with Exponential Backoff** | `domains/character/rpc/my_client.py` | gRPC 재시도 + jitter (±25%) |
| **Graceful Degradation** | `domains/character/core/cache.py`, `domains/character/rpc/my_client.py` | 장애 시 기능 저하로 서비스 유지 |
| **Optimistic Locking** | `domains/character/services/character.py` | Race Condition 방지 (UniqueConstraint + IntegrityError) |
| **Factory Method** | `domains/*/main.py` (`create_app`), `domains/*/database/session.py` (`async_session_factory`) | 앱/세션 인스턴스 생성 캡슐화 |

---

## 인프라 레이어

| 패턴 | 적용 위치 | 설명 |
|------|----------|------|
| **Reconciliation Loop** | `clusters/dev/`, `clusters/prod/` (ArgoCD) | GitOps - Desired State와 Actual State 동기화 |
| **Sidecar** | Istio Proxy (자동 주입) | 서비스 메시 - 트래픽 관리, mTLS |
| **Ambassador** | `workloads/domains/ext-authz/`, `workloads/routing/gateway/base/authorization-policy.yaml` | API Gateway 레벨 인증/인가 오프로딩 |
| **Service Mesh** | `workloads/routing/*/base/virtual-service.yaml`, `workloads/domains/ext-authz/base/destination-rule.yaml` | 서비스 간 통신 관리, 트레이싱, 라우팅 |
| **External Configuration** | `workloads/secrets/external-secrets/dev/`, `workloads/secrets/external-secrets/prod/` | AWS Secrets Manager → K8s Secret 동기화 |
| **Zero Trust Network** | `workloads/network-policies/base/default-deny-all.yaml` | default-deny-all + 명시적 허용 (현재 비활성화) |
| **Horizontal Pod Autoscaler** | `workloads/domains/auth/base/hpa.yaml`, `workloads/domains/character/base/hpa.yaml`, `workloads/domains/ext-authz/base/hpa.yaml` | CPU 기반 자동 스케일링 |
| **Blue-Green / Canary** | `workloads/routing/*/base/virtual-service.yaml` | 트래픽 분할 배포 가능 (미적용, 구현 준비됨) |
| **GitOps** | `clusters/dev/apps/40-apis-appset.yaml`, `clusters/prod/apps/60-apis-appset.yaml` | 선언적 배포, 환경별 Kustomize overlay |
| **Phased Deployment** | `clusters/dev/apps/40-apis-appset.yaml` (phase 설정) | 서비스 배포 순서 제어 (auth→scan→character) |
| **Kustomize Overlay** | `workloads/domains/*/base/`, `workloads/domains/*/dev/`, `workloads/domains/*/prod/` | base + 환경별 패치로 DRY |
| **Health Check** | `workloads/domains/*/base/deployment.yaml` (`/health`, `/ready`) | Liveness/Readiness Probe |
| **Bulkhead** | `workloads/namespaces/base/namespaces.yaml` | 장애 격리 (auth, character, scan, my, location 등) |
| **Connection Pooling** | `workloads/domains/ext-authz/base/destination-rule.yaml` | 연결 재사용으로 리소스 효율화 |
| **DaemonSet** | `workloads/logging/base/fluent-bit.yaml` | 모든 노드에 로깅 에이전트 배포 |
| **Node Affinity + Tolerations** | `workloads/domains/*/base/deployment.yaml` | 도메인별 전용 노드 할당 |

---

## Observability 패턴

| 패턴 | 적용 위치 | 설명 |
|------|----------|------|
| **Distributed Tracing** | `domains/*/core/tracing.py` | 서비스 간 요청 추적, OTLP/gRPC 전송 (OpenTelemetry + Jaeger) |
| **Structured Logging** | `domains/*/core/logging.py` (`ECSJsonFormatter`) | ECS JSON Format, 로그 파싱 및 검색 용이 |
| **Metrics Collection** | `domains/*/metrics.py` (Counter, Histogram) | 메트릭 수집 및 알람 (Prometheus) |
| **Log Aggregation** | `workloads/logging/base/fluent-bit.yaml` | 중앙 집중식 로그 관리 (→ Elasticsearch) |
| **Correlation ID** | `domains/ext-authz/internal/constants/ecs.go`, `domains/*/core/constants.py` | 로그-트레이스 연결 (`trace.id`, `span.id`) |
| **Auto-instrumentation** | `domains/*/core/tracing.py` | 자동 계측 (FastAPI, SQLAlchemy, Redis, gRPC) |

---

## 추가 도입 검토 패턴

| 패턴 | 현재 상태 | 권장 |
|------|----------|------|
| **CQRS** | 미적용 | 조회/명령 분리 필요 시 검토 |
| **Event Sourcing** | 미적용 | 이벤트 기반 아키텍처 전환 시 검토 |
| **Saga** | 미적용 | 분산 트랜잭션 필요 시 검토 |
| **Outbox** | 미적용 | 메시지 발행 보장 필요 시 검토 |
| **API Gateway Aggregation** | 부분 적용 | BFF(Backend for Frontend) 검토 |

---

## Reference

### 클라우드 아키텍처 패턴
- [Circuit Breaker Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [Cache-Aside Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- [Sidecar Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/sidecar)
- [Ambassador Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/ambassador)
- [Bulkhead Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- [Retry Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/retry)

### Kubernetes & GitOps
- [ArgoCD ApplicationSet](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)
- [Kustomize](https://kustomize.io/)
- [Istio Service Mesh](https://istio.io/latest/docs/)
- [Calico Network Policy](https://docs.tigera.io/calico/latest/network-policy/)
- [External Secrets Operator](https://external-secrets.io/latest/)

### Observability
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)
- [Elastic Common Schema (ECS)](https://www.elastic.co/guide/en/ecs/current/index.html)
- [Jaeger Tracing](https://www.jaegertracing.io/docs/)
- [Fluent Bit](https://docs.fluentbit.io/manual/)
