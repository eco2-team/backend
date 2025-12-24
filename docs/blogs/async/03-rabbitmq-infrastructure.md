# 이코에코(Eco²) 비동기 전환 #3: RabbitMQ 인프라 구축

> 이전 글: [비동기 전환 #2: MQ 구현 상세](./02-mq-architecture-design.md)

---

## 개요

본 문서는 RabbitMQ를 Kubernetes 클러스터에 **ArgoCD App-of-Apps 패턴**으로 배포한 구축 과정을 기록한다.

### 목표

- RabbitMQ Cluster Operator + Messaging Topology Operator 배포
- RabbitmqCluster CR로 브로커 인스턴스 관리
- Vhost, Exchange, Queue, Binding을 Kubernetes CRD로 선언적 관리
- Istio Service Mesh 통합 (mTLS, Kiali 가시성)

### 선행 조건

| 구성 요소 | 버전 | 역할 |
|----------|------|------|
| Cert-Manager | v1.16.2 | Topology Operator Webhook TLS 인증서 |
| ArgoCD | v2.13+ | GitOps 배포 |
| k8s-rabbitmq 노드 | - | 전용 노드 (infra-type=rabbitmq) |

---

## 1. 아키텍처 설계

### 1.1 Sync Wave 설계

RabbitMQ 인프라는 4개의 ArgoCD Application으로 구성되며, 의존성 순서대로 배포된다:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ArgoCD Sync Wave 순서                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Wave 08: Cert-Manager ─────────────────────────────────────────────┐       │
│           (Webhook TLS 인증서 발급)                                   │       │
│                                                                     │       │
│  Wave 29: RabbitMQ Cluster Operator ────────────────────────────┐   │       │
│           (rabbitmq.com/v1beta1 CRD 설치)                        │   │       │
│                                                                  │   │       │
│  Wave 30: RabbitMQ Topology Operator ───────────────────────┐   │   │       │
│           (Exchange, Queue, Binding CRD 설치)                │   │   │       │
│                                                              ▼   ▼   ▼       │
│  Wave 31: RabbitmqCluster CR ─────────────────────────────────────────────  │
│           (eco2-rabbitmq Pod 생성)                                          │
│                                                              │               │
│  Wave 32: Topology CRs ──────────────────────────────────────┘               │
│           (Vhost, Exchange, Queue, Binding 생성)                            │
│                                                                             │
│  Wave 40: API Services ─────────────────────────────────────────────────────│
│           (scan-api, character-api 등)                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 노드 배치 전략

| 리소스 | 배치 노드 | 이유 |
|--------|----------|------|
| Cluster Operator | k8s-master (control-plane) | 컨트롤러는 관리 노드에 |
| Topology Operator | k8s-master (control-plane) | 컨트롤러는 관리 노드에 |
| RabbitmqCluster Pod | k8s-rabbitmq (integration) | 전용 데이터 노드 |

**노드 레이블/Taint 구성** (`terraform/main.tf`):

```hcl
"k8s-rabbitmq" = "--node-labels=role=infrastructure,domain=integration,infra-type=rabbitmq --register-with-taints=domain=integration:NoSchedule"
"k8s-master"   = "--node-labels=role=control-plane --register-with-taints=role=control-plane:NoSchedule"
```

---

## 2. 구현 상세

### 2.1 Cluster Operator (sync-wave 29)

RabbitMQ 공식 Cluster Operator를 ArgoCD로 배포한다.

**파일**: `clusters/dev/apps/29-rabbitmq-operator.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-rabbitmq-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: '29'
spec:
  source:
    repoURL: https://github.com/rabbitmq/cluster-operator
    targetRevision: v2.11.0
    path: config/installation  # CRD + RBAC + Deployment 포함
    kustomize:
      patches:
      # Control-plane 노드에 배치
      - target:
          kind: Deployment
          name: rabbitmq-cluster-operator
        patch: |
          - op: add
            path: /spec/template/spec/nodeSelector
            value:
              role: control-plane
          - op: add
            path: /spec/template/spec/tolerations
            value:
            - key: role
              operator: Equal
              value: control-plane
              effect: NoSchedule
            - key: node-role.kubernetes.io/control-plane
              operator: Exists
              effect: NoSchedule
  destination:
    namespace: rabbitmq-system
  syncPolicy:
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true  # CRD 충돌 방지
```

**핵심 포인트**:
- `config/installation` 경로 사용 (CRD, RBAC, Namespace 포함)
- `ServerSideApply=true`로 CRD 필드 충돌 방지
- Control-plane 노드 toleration 2개 필수

### 2.2 Topology Operator (sync-wave 30)

Messaging Topology Operator로 Exchange, Queue, Binding을 CRD로 관리한다.

**파일**: `clusters/dev/apps/30-rabbitmq-topology-operator.yaml`

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-rabbitmq-topology-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: '30'
spec:
  source:
    repoURL: https://github.com/rabbitmq/messaging-topology-operator
    targetRevision: v1.15.0
    path: config/installation/cert-manager  # cert-manager 통합 버전
    kustomize:
      patches:
      # Control-plane 노드에 배치
      - target:
          kind: Deployment
          name: messaging-topology-operator
        patch: |
          - op: add
            path: /spec/template/spec/nodeSelector
            value:
              role: control-plane
          - op: add
            path: /spec/template/spec/tolerations
            value:
            - key: role
              operator: Equal
              value: control-plane
              effect: NoSchedule
            - key: node-role.kubernetes.io/control-plane
              operator: Exists
              effect: NoSchedule
      # Namespace 중복 생성 방지 (Cluster Operator가 이미 생성)
      - target:
          kind: Namespace
          name: rabbitmq-system
        patch: |
          $patch: delete
          apiVersion: v1
          kind: Namespace
          metadata:
            name: rabbitmq-system
  destination:
    namespace: rabbitmq-system
  syncPolicy:
    syncOptions:
    - CreateNamespace=false  # Cluster Operator가 생성
    - ServerSideApply=true
```

**핵심 포인트**:
- `config/installation/cert-manager` 경로로 TLS 자동 구성
- Namespace `$patch: delete`로 중복 생성 방지
- `CreateNamespace=false` 설정

### 2.3 RabbitmqCluster CR (sync-wave 31)

실제 RabbitMQ 브로커 인스턴스를 정의한다.

**파일**: `workloads/rabbitmq/base/cluster.yaml`

```yaml
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: eco2-rabbitmq
  namespace: rabbitmq
spec:
  replicas: 1  # dev: 1, prod: 3 (kustomize overlay)

  image: rabbitmq:4.0-management

  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 1000m
      memory: 2Gi

  persistence:
    storageClassName: gp3
    storage: 10Gi

  rabbitmq:
    additionalConfig: |
      default_vhost = /
      tcp_listen_options.backlog = 128
      tcp_listen_options.nodelay = true
      vm_memory_high_watermark.relative = 0.7
      vm_memory_high_watermark_paging_ratio = 0.8
      cluster_formation.target_cluster_size_hint = 1
      queue_leader_locator = balanced

    additionalPlugins:
    - rabbitmq_management
    - rabbitmq_prometheus
    - rabbitmq_shovel
    - rabbitmq_shovel_management

  # 전용 노드 배치
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: infra-type
            operator: In
            values:
            - rabbitmq

  tolerations:
  - key: domain
    operator: Equal
    value: integration
    effect: NoSchedule
```

**Namespace 정의** (`workloads/rabbitmq/base/namespace.yaml`):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rabbitmq
  labels:
    tier: platform
    component: rabbitmq
    istio-injection: enabled  # mTLS + Kiali 가시성
```

**환경별 Kustomize Overlay** (`workloads/rabbitmq/dev/kustomization.yaml`):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: rabbitmq
resources:
- ../base
patches:
- patch: |
    - op: replace
      path: /spec/replicas
      value: 1
    - op: replace
      path: /spec/resources/limits/memory
      value: 2Gi
  target:
    kind: RabbitmqCluster
    name: eco2-rabbitmq
```

### 2.4 Topology CRs (sync-wave 32)

#### 2.4.1 Vhost

```yaml
# workloads/rabbitmq/base/topology/vhost.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Vhost
metadata:
  name: eco2-vhost
  namespace: rabbitmq
spec:
  name: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
    namespace: rabbitmq
```

#### 2.4.2 Exchanges (5개)

| Exchange | Type | 용도 |
|----------|------|------|
| `scan.direct` | direct | AI 파이프라인 Task 라우팅 |
| `reward.direct` | direct | 리워드 지급 Task |
| `dlx` | direct | Dead Letter Exchange |
| `authz.fanout` | fanout | ext-authz 블랙리스트 브로드캐스트 |
| `celery` | topic | Celery 기본 Exchange |

```yaml
# workloads/rabbitmq/base/topology/exchanges.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: scan-direct
  namespace: rabbitmq
spec:
  name: scan.direct
  type: direct
  durable: true
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
---
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: authz-fanout
  namespace: rabbitmq
spec:
  name: authz.fanout
  type: fanout  # 모든 인스턴스에 브로드캐스트
  durable: true
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
```

#### 2.4.3 Queues (10개)

**Main Queues (4개)**:

| Queue | Type | TTL | DLX | 용도 |
|-------|------|-----|-----|------|
| `scan.vision` | quorum | 1h | dlx | GPT Vision 호출 |
| `scan.rule` | quorum | 5m | dlx | Rule-based 분류 |
| `scan.answer` | quorum | 1h | dlx | GPT Answer 생성 |
| `reward.character` | quorum | 24h | dlx | 캐릭터 리워드 지급 |

**Dead Letter Queues (5개)**:
- `dlq.scan.vision`, `dlq.scan.rule`, `dlq.scan.answer`
- `dlq.reward`, `dlq.celery`
- TTL: 7일 (실패 메시지 보관)

```yaml
# workloads/rabbitmq/base/topology/queues.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-vision-queue
  namespace: rabbitmq
spec:
  name: scan.vision
  type: quorum  # 내구성 + 복제
  durable: true
  vhost: eco2
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.scan.vision
    x-message-ttl: 3600000      # 1시간
    x-delivery-limit: 3          # 최대 재시도
  rabbitmqClusterReference:
    name: eco2-rabbitmq
---
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: reward-queue
  namespace: rabbitmq
spec:
  name: reward.character
  type: quorum
  durable: true
  vhost: eco2
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.reward
    x-message-ttl: 86400000     # 24시간 (중요 작업)
    x-delivery-limit: 5          # 재시도 5회
  rabbitmqClusterReference:
    name: eco2-rabbitmq
```

#### 2.4.4 Bindings (10개)

Exchange와 Queue를 라우팅 키로 연결한다.

```yaml
# workloads/rabbitmq/base/topology/bindings.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: scan-vision-binding
  namespace: rabbitmq
spec:
  source: scan.direct
  destination: scan.vision
  destinationType: queue
  routingKey: scan.vision
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
---
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: dlq-scan-vision-binding
  namespace: rabbitmq
spec:
  source: dlx
  destination: dlq.scan.vision
  destinationType: queue
  routingKey: dlq.scan.vision
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
```

---

## 3. Network Policy

RabbitMQ 접근을 허용할 namespace를 명시적으로 정의한다.

**파일**: `workloads/network-policies/base/allow-rabbitmq-access.yaml`

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-rabbitmq-access
  namespace: rabbitmq
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: rabbitmq
  policyTypes:
  - Ingress
  ingress:
  # AMQP (5672) - API 서비스 + Celery Workers
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: scan
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: character
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: auth
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: chat
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: rabbitmq
    ports:
    - protocol: TCP
      port: 5672

  # Management UI (15672) - 모니터링 + Topology Operator
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: monitoring
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: istio-system
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: rabbitmq-system  # Topology Operator
    ports:
    - protocol: TCP
      port: 15672

  # Prometheus 메트릭 (15692)
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: monitoring
    ports:
    - protocol: TCP
      port: 15692

  # Erlang Distribution (25672, 4369) - 클러스터 내부 통신
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: rabbitmq
    ports:
    - protocol: TCP
      port: 25672
    - protocol: TCP
      port: 4369
```

---

## 4. 디렉토리 구조

```
backend/
├── clusters/dev/apps/
│   ├── 08-cert-manager.yaml          # TLS 인증서 관리
│   ├── 29-rabbitmq-operator.yaml     # Cluster Operator
│   ├── 30-rabbitmq-topology-operator.yaml  # Topology Operator
│   ├── 31-rabbitmq-cluster.yaml      # RabbitmqCluster CR
│   └── 32-rabbitmq-topology.yaml     # Vhost/Exchange/Queue/Binding
│
├── workloads/
│   ├── rabbitmq/
│   │   ├── base/
│   │   │   ├── kustomization.yaml
│   │   │   ├── namespace.yaml        # istio-injection: enabled
│   │   │   ├── cluster.yaml          # RabbitmqCluster
│   │   │   └── topology/
│   │   │       ├── kustomization.yaml
│   │   │       ├── vhost.yaml        # eco2
│   │   │       ├── exchanges.yaml    # 5개
│   │   │       ├── queues.yaml       # 10개
│   │   │       └── bindings.yaml     # 10개
│   │   ├── dev/
│   │   │   ├── kustomization.yaml    # replicas: 1
│   │   │   └── topology/
│   │   │       └── kustomization.yaml
│   │   └── prod/
│   │       ├── kustomization.yaml    # replicas: 3
│   │       └── topology/
│   │           └── kustomization.yaml
│   │
│   └── network-policies/base/
│       └── allow-rabbitmq-access.yaml
```

---

## 5. 검증 결과

### 5.1 ArgoCD Applications

```bash
$ kubectl get applications -n argocd | grep rabbitmq
dev-rabbitmq-operator           Synced   Healthy
dev-rabbitmq-topology-operator  Synced   Healthy
dev-rabbitmq-cluster            Synced   Healthy
dev-rabbitmq-topology           Synced   Healthy
```

### 5.2 Topology CRs 상태

```bash
$ kubectl get vhost,exchange,queue,binding -n rabbitmq
NAME                                   AGE   READY
vhost.rabbitmq.com/eco2-vhost          1h    True

NAME                                       AGE   READY
exchange.rabbitmq.com/scan-direct          1h    True
exchange.rabbitmq.com/reward-direct        1h    True
exchange.rabbitmq.com/dlx                  1h    True
exchange.rabbitmq.com/authz-fanout         1h    True
exchange.rabbitmq.com/celery-default       1h    True

NAME                                       AGE   READY
queue.rabbitmq.com/scan-vision-queue       1h    True
queue.rabbitmq.com/scan-rule-queue         1h    True
queue.rabbitmq.com/scan-answer-queue       1h    True
queue.rabbitmq.com/reward-queue            1h    True
queue.rabbitmq.com/celery-default-queue    1h    True
queue.rabbitmq.com/dlq-scan-vision         1h    True
queue.rabbitmq.com/dlq-scan-rule           1h    True
queue.rabbitmq.com/dlq-scan-answer         1h    True
queue.rabbitmq.com/dlq-reward              1h    True
queue.rabbitmq.com/dlq-celery              1h    True

NAME                                           AGE   READY
binding.rabbitmq.com/scan-vision-binding       1h    True
binding.rabbitmq.com/scan-rule-binding         1h    True
binding.rabbitmq.com/scan-answer-binding       1h    True
binding.rabbitmq.com/reward-character-binding  1h    True
binding.rabbitmq.com/celery-default-binding    1h    True
binding.rabbitmq.com/dlq-scan-vision-binding   1h    True
binding.rabbitmq.com/dlq-scan-rule-binding     1h    True
binding.rabbitmq.com/dlq-scan-answer-binding   1h    True
binding.rabbitmq.com/dlq-reward-binding        1h    True
binding.rabbitmq.com/dlq-celery-binding        1h    True
```

**총 26개 Topology CRs**: 1 Vhost + 5 Exchanges + 10 Queues + 10 Bindings

### 5.3 RabbitMQ 내부 검증

```bash
$ kubectl exec -it eco2-rabbitmq-server-0 -n rabbitmq -- rabbitmqctl list_queues -p eco2
Timeout: 60.0 seconds ...
Listing queues for vhost eco2 ...
name               messages
celery             0
dlq.celery         0
dlq.reward         0
dlq.scan.answer    0
dlq.scan.rule      0
dlq.scan.vision    0
reward.character   0
scan.answer        0
scan.rule          0
scan.vision        0
```

### 5.4 리소스 사용량

```bash
$ kubectl top pod -n rabbitmq
NAME                      CPU(cores)   MEMORY(bytes)
eco2-rabbitmq-server-0    45m          512Mi
```

- **예상**: 500m CPU, 1Gi Memory (requests)
- **실측**: 45m CPU, 512Mi Memory (idle 상태)
- **여유 공간**: Sidecar + 부하 증가 대응 가능

---

## 6. Management UI 외부 노출

### 6.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RabbitMQ Management UI 접근 경로                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Browser                                                                    │
│     │                                                                       │
│     │ https://rabbitmq.dev.growbin.app                                     │
│     ▼                                                                       │
│  Route53 (ExternalDNS)                                                     │
│     │                                                                       │
│     │ CNAME → ALB                                                          │
│     ▼                                                                       │
│  AWS ALB (Ingress)                                                         │
│     │                                                                       │
│     │ :443 → istio-ingressgateway:80                                       │
│     ▼                                                                       │
│  Istio Gateway                                                              │
│     │                                                                       │
│     │ VirtualService: rabbitmq.dev.growbin.app                             │
│     ▼                                                                       │
│  eco2-rabbitmq.rabbitmq.svc:15672                                          │
│     │                                                                       │
│     ▼                                                                       │
│  RabbitMQ Management UI                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 VirtualService

**파일**: `workloads/routing/rabbitmq/base/virtual-service.yaml`

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: rabbitmq-vs
  namespace: istio-system
spec:
  hosts:
  - rabbitmq.growbin.app
  gateways:
  - istio-system/eco2-gateway
  http:
  - match:
    - uri:
        prefix: /
    route:
    - destination:
        host: eco2-rabbitmq.rabbitmq.svc.cluster.local
        port:
          number: 15672
    timeout: 30s
    retries:
      attempts: 3
      perTryTimeout: 10s
      retryOn: connect-failure,reset,503  # retriable-4xx 제외 (401 인증 헤더 손실 방지)
```

**환경별 Patch** (`workloads/routing/rabbitmq/dev/patch-virtual-service.yaml`):

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: rabbitmq-vs
spec:
  hosts:
  - rabbitmq.dev.growbin.app  # dev 환경 도메인
```

### 6.3 Gateway 호스트 추가

**파일**: `workloads/routing/gateway/dev/patch-gateway.yaml`

```yaml
# hosts 배열에 추가
- rabbitmq.dev.growbin.app
```

### 6.4 ExternalDNS Annotation

**파일**: `workloads/routing/gateway/dev/patch-ingress.yaml`

```yaml
annotations:
  external-dns.alpha.kubernetes.io/hostname: >-
    api.dev.growbin.app,
    argocd.dev.growbin.app,
    grafana.dev.growbin.app,
    kiali.dev.growbin.app,
    jaeger.dev.growbin.app,
    kibana.dev.growbin.app,
    rabbitmq.dev.growbin.app  # 추가
```

### 6.5 ArgoCD ApplicationSet

**파일**: `clusters/dev/apps/50-istio-routes.yaml`

```yaml
generators:
- list:
    elements:
    # ... 기존 routes ...
    - name: rabbitmq
      namespace: istio-system
      path: workloads/routing/rabbitmq/dev
```

### 6.6 접속 정보

| 항목 | 값 |
|------|-----|
| **URL** | https://rabbitmq.dev.growbin.app |
| **Username** | `admin` |
| **Password** | `admin123` |

---

## 7. 다음 단계

| 순서 | 작업 | 상태 |
|------|------|------|
| 1 | RabbitMQ ServiceMonitor 추가 | 예정 |
| 2 | Grafana 대시보드 구성 | 예정 |
| 3 | Celery 공통 모듈 개발 | 예정 |
| 4 | scan-worker Deployment 작성 | 예정 |

---

## 참고

### 내부 문서
- [비동기 전환 #2: MQ 구현 상세](./02-mq-architecture-design.md)
- [비동기 전환 #4: RabbitMQ 트러블슈팅](./04-rabbitmq-troubleshooting.md)

### 외부 문서
- [RabbitMQ Cluster Operator](https://www.rabbitmq.com/kubernetes/operator/operator-overview)
- [Messaging Topology Operator](https://www.rabbitmq.com/kubernetes/operator/using-topology-operator)
- [RabbitMQ 4.0 Release Notes](https://www.rabbitmq.com/release-information)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-12-20 | 1.0 | 초안 작성 (ArgoCD 배포, Topology CRs, Network Policy) |
| 2025-12-22 | 1.1 | Management UI 외부 노출 (Istio VirtualService, ExternalDNS) |
