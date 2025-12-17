# EFK Logging Architecture Plan

## 1. 개요 (Overview)

본 문서는 Eco2 프로젝트의 분산된 마이크로서비스 로그를 중앙에서 효율적으로 수집, 저장, 분석하기 위한 **EFK (Elasticsearch + Fluent Bit + Kibana)** 스택 구축 계획입니다. 특히, 대용량 로그 처리에 따른 부하를 격리하기 위해 **별도의 로깅 전용 노드**를 활용하는 아키텍처를 정의합니다.

## 2. 아키텍처 구성 (Architecture)

### 2.1 구성 요소
- **Fluent Bit (Collector)**:
  - 경량 로그 수집기.
  - 모든 노드(Master, Worker, API)에 DaemonSet으로 배포되어 컨테이너 로그(`/var/log/containers/*.log`)를 수집.
  - 로그 필터링 및 파싱(JSON) 후 Elasticsearch로 전송.
- **Elasticsearch (Storage & Search Engine)**:
  - 로그 저장 및 검색 엔진.
  - **전용 로깅 노드**에 배치하여 I/O 및 메모리 부하 격리.
  - StatefulSet으로 배포되어 안정적인 스토리지(PVC) 사용.
- **Kibana (Visualization)**:
  - 로그 시각화 대시보드.
  - Elasticsearch 데이터를 조회하여 그래프 및 검색 UI 제공.

### 2.2 노드 구성 전략 (Dedicated Nodes)
로깅 시스템(특히 ES)은 메모리와 디스크 I/O를 많이 사용하므로, 비즈니스 로직(API)에 영향을 주지 않도록 물리적으로 격리합니다.

- **대상 노드**: `k8s-logging-node` (예시)
- **Node Label**: `infra-type=logging`
- **Taint**: `role=logging:NoSchedule` (로깅 파드 외에는 스케줄링되지 않도록 설정)

---

## 3. Kubernetes 리소스 명세 (Resource Specification)

### 3.1 Namespace & Metadata
모든 로깅 리소스는 별도의 네임스페이스에서 관리합니다.

- **Namespace**: `logging`
- **Common Labels**:
  - `tier: observability`
  - `role: logging`
  - `app.kubernetes.io/part-of: ecoeco-logging`

### 3.2 Elasticsearch (StatefulSet)
- **배포 방식**: Helm Chart (Bitnami 권장)
- **Node Placement**:
  ```yaml
  nodeSelector:
    infra-type: logging
  tolerations:
  - key: role
    operator: Equal
    value: logging
    effect: NoSchedule
  ```
- **Resources**:
  - Memory: 최소 4Gi 이상 권장 (Heap Size는 메모리의 50%).
  - Storage: GP3 Class, 50Gi+ (로그 보관 주기에 따라 산정).

### 3.3 Fluent Bit (DaemonSet)
- **배포 방식**: Helm Chart (Fluent Bit 공식)
- **Node Placement**:
  - 모든 노드에 배포되어야 하므로 `tolerations` 설정이 중요합니다.
  - Master 노드 및 로깅 노드를 포함한 모든 Taint를 허용해야 함.
  ```yaml
  tolerations:
  - operator: Exists  # 모든 Taint 허용
  ```
- **Configuration**:
  - `Input`: tail (path: `/var/log/containers/*.log`)
  - `Filter`: Kubernetes Metadata (Pod Name, Namespace 등 추가)
  - `Output`: Elasticsearch

### 3.4 Kibana (Deployment)
- **배포 방식**: Helm Chart
- **Node Placement**:
  - Elasticsearch와 동일하게 로깅 노드에 배치하거나, 일반 인프라 노드(`infra-type=monitoring`)에 배치 가능.
  - 여기서는 관리 편의성을 위해 로깅 노드 배치를 권장.

---

## 4. 인덱스 전략 (Index Strategy)

### 4.1 인덱스 분리 전략

업계 표준(Netflix, Uber, Google SRE, CNCF)을 참고한 인덱스 분리 전략입니다.

#### 왜 도메인별 인덱스가 아닌가?

| 문제 | 설명 |
|------|------|
| **샤드 오버헤드** | 인덱스당 최소 1 primary + 1 replica 샤드 필요 |
| **리소스 낭비** | 소규모 서비스도 동일 샤드 할당 |
| **Cross-service 검색** | 분산 트랜잭션 추적 시 다중 인덱스 조인 필요 |
| **ILM 복잡도** | 인덱스별 lifecycle policy 관리 필요 |

#### 권장 전략: 앱/인프라 분리 + 필드 기반 필터링

```
┌─────────────────────────────────────────────────────────┐
│                    인덱스 패턴                           │
├─────────────────────────────────────────────────────────┤
│  logs-app-{env}-{YYYY.MM.DD}                           │
│  logs-infra-{env}-{YYYY.MM.DD}                         │
│                                                         │
│  예시:                                                  │
│  - logs-app-dev-2024.12.17                             │
│  - logs-infra-dev-2024.12.17                           │
└─────────────────────────────────────────────────────────┘
```

#### 앱 vs 인프라 분류

| 분류 | 네임스페이스 | 설명 |
|------|-------------|------|
| **App** | auth, character, chat, scan, my, location, image | 비즈니스 로직 서비스 |
| **Infra** | kube-system, istio-system, logging, monitoring, argocd | 플랫폼/인프라 서비스 |

#### 필드 기반 서비스 구분

도메인별 인덱스 대신 ECS 필드로 서비스를 구분합니다:

```json
{
  "service.name": "auth-api",
  "service.version": "1.0.7",
  "kubernetes.namespace_name": "auth",
  "kubernetes.pod_name": "auth-api-xxx",
  "environment": "dev"
}
```

#### Kibana 쿼리 예시

```
# 특정 서비스 에러 로그
service.name: "auth-api" AND log.level: "error"

# Cross-service 트랜잭션 추적
trace.id: "abc123*"

# 특정 네임스페이스
kubernetes.namespace_name: "auth"
```

### 4.2 수명 주기 관리 (ILM)

| 인덱스 | Hot | Warm | Delete |
|--------|-----|------|--------|
| logs-app-dev-* | 3일 | 7일 | 14일 |
| logs-app-prod-* | 7일 | 30일 | 90일 |
| logs-infra-* | 1일 | 3일 | 7일 |

### 4.3 참고 자료

- Netflix: 단일 인덱스 + Kafka 파이프라인
- Uber: ELK → ClickHouse 전환 (샤드 폭발 문제 해결)
- Google SRE: 로그 레벨별/환경별 분리
- CNCF: 중앙화 로깅 + 구조화 로그 + 상관 ID

## 5. 네트워크 및 보안

- **Service Discovery**:
  - `elasticsearch.logging.svc.cluster.local`: Fluent Bit 및 Kibana가 접근.
  - `kibana.logging.svc.cluster.local`: Ingress를 통해 외부 노출.
- **Access Control**:
  - Kibana 접근 시 Ingress 레벨의 Basic Auth 또는 OAuth2 인증 적용 필수.
  - (선택 사항) Elasticsearch 내부 통신 TLS 암호화.

---

## 6. 마이그레이션 및 실행 계획

1.  **노드 준비 (Terraform)**:
    - `infra-type=logging` 레이블과 Taint가 적용된 EC2 인스턴스 프로비저닝.
2.  **Namespace 생성**:
    - `kubectl create ns logging`
3.  **Elasticsearch 배포**:
    - `clusters/dev/apps/22-elasticsearch.yaml` (ArgoCD) 작성.
    - Node Affinity 설정 적용.
4.  **Fluent Bit 배포**:
    - `clusters/dev/apps/23-fluent-bit.yaml` 작성.
    - ES 연결 정보 설정.
5.  **Kibana 배포**:
    - `clusters/dev/apps/24-kibana.yaml` 작성.
6.  **검증**:
    - Kibana 접속 및 `Discover` 탭에서 로그 유입 확인.
