# KEDA RabbitMQ 기반 이벤트 드리븐 오토스케일링 구현 및 트러블슈팅

## 개요

본 문서는 Kubernetes 환경에서 KEDA(Kubernetes Event-driven Autoscaling)를 활용하여 RabbitMQ 큐 길이 기반 Worker Pod 오토스케일링을 구현하는 과정에서 발생한 이슈와 해결 방법을 기술한다.

### 환경 정보

| 구성 요소 | 버전/사양 |
|-----------|-----------|
| Kubernetes | v1.28.15 (kubeadm) |
| KEDA | v2.16.0 |
| RabbitMQ | v3.13.x (RabbitMQ Operator) |
| ArgoCD | v2.13.x |
| CNI | Calico (NetworkPolicy 적용) |

### 목표

- CPU 기반 HPA의 한계를 극복하고 메시지 큐 길이 기반 오토스케일링 구현
- scan-worker의 동적 스케일링으로 부하 대응력 향상
- k6 부하 테스트 시 성공률 개선

---

## 1. 배경: CPU 기반 HPA의 한계

### 1.1 기존 구조

scan-worker는 Celery 기반 비동기 Worker로, RabbitMQ 큐에서 메시지를 소비하여 OpenAI API 호출 등 I/O 집약적 작업을 수행한다.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  scan-api   │────►│  RabbitMQ   │────►│ scan-worker │
│  (Producer) │     │  (Queue)    │     │ (Consumer)  │
└─────────────┘     └─────────────┘     └─────────────┘
                         │
                    scan.vision: 22
                    scan.answer: 16
                    scan.rule: 14
```

### 1.2 문제점

k6 부하 테스트(50 VUs, 3분) 결과:

| 지표 | 값 |
|------|-----|
| 총 요청 | 643 |
| 성공 | 452 (70.3%) |
| 실패 | 128 (19.9%) |
| 부분 완료 | 63 (9.8%) |

CPU 기반 HPA가 효과적이지 않은 이유:
- OpenAI API 호출 대기 시간이 대부분 (30-50초)
- CPU 사용률은 낮게 유지 (10-15%)
- 큐에 메시지가 쌓여도 스케일업 트리거 안 됨

### 1.3 해결 방안: KEDA 도입

KEDA는 외부 이벤트 소스(RabbitMQ, Kafka, Prometheus 등)를 기반으로 HPA를 생성하여 이벤트 드리븐 스케일링을 지원한다.

---

## 2. 초기 구현

### 2.1 ScaledObject 정의

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: scan-worker-scaledobject
  namespace: scan
spec:
  scaleTargetRef:
    name: scan-worker
    kind: Deployment
  minReplicaCount: 1
  maxReplicaCount: 5
  cooldownPeriod: 120
  pollingInterval: 15
  triggers:
  - type: rabbitmq
    metadata:
      protocol: amqp
      queueName: scan.vision
      mode: QueueLength
      value: '10'
    authenticationRef:
      name: rabbitmq-trigger-auth
```

### 2.2 TriggerAuthentication

```yaml
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: rabbitmq-trigger-auth
  namespace: scan
spec:
  secretTargetRef:
  - parameter: host
    name: scan-secret
    key: CELERY_BROKER_URL
```

---

## 3. Issue #1: 메트릭 수집 실패 (ScalerNotActive)

### 3.1 현상

ScaledObject 배포 후 ACTIVE 상태가 False로 유지:

```bash
$ kubectl get scaledobject -n scan -o wide
NAME                       SCALETARGETKIND      SCALETARGETNAME   MIN   MAX   READY   ACTIVE
scan-worker-scaledobject   apps/v1.Deployment   scan-worker       1     5     True    False
```

HPA 메트릭이 모두 0으로 표시:

```bash
$ kubectl describe hpa keda-hpa-scan-worker-scaledobject -n scan
Metrics:
  "s0-rabbitmq-scan-vision" (target average value): 0 / 10
  "s1-rabbitmq-scan-answer" (target average value): 0 / 10
  "s2-rabbitmq-scan-rule" (target average value): 0 / 20
```

### 3.2 원인 분석

RabbitMQ 큐 상태를 직접 조회한 결과:

```bash
$ kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
    rabbitmqctl list_queues name messages_ready messages_unacknowledged -p eco2

QUEUE           READY   UNACKED
scan.vision     0       22
scan.answer     0       16
scan.rule       0       14
scan.reward     0       9
```

**핵심 발견**: `messages_ready=0`, `messages_unacknowledged=N`

Celery Worker 설정:
```python
# domains/_shared/celery/config.py
worker_prefetch_multiplier = 1  # greenlet당 1개 prefetch
task_acks_late = True
```

Worker는 gevent pool(100 greenlets)을 사용하며, 메시지를 prefetch하여 처리한다. 이로 인해 모든 메시지가 `unacked` 상태로 전환된다.

### 3.3 KEDA RabbitMQ Scaler 동작 분석

KEDA의 AMQP 프로토콜 스케일러 동작:

```go
// KEDA 소스 코드 참고
func (s *rabbitMQScaler) GetQueueInfo() (int, error) {
    // pika.BlockingConnection 사용
    // channel.queue_declare(passive=True) 호출
    // → messages_ready만 반환
}
```

| 프로토콜 | 측정 대상 | 사용 API |
|----------|-----------|----------|
| AMQP | `messages_ready` | queue_declare (passive) |
| HTTP | `messages` (ready + unacked) | Management API |

### 3.4 해결책: HTTP 프로토콜 전환

```yaml
triggers:
- type: rabbitmq
  metadata:
    protocol: http
    host: http://admin:***@eco2-rabbitmq.rabbitmq.svc.cluster.local:15672
    queueName: scan.vision
    vhostName: eco2
    mode: QueueLength
    value: '10'
```

HTTP Management API 응답 예시:
```json
{
  "name": "scan.vision",
  "messages": 22,
  "messages_ready": 0,
  "messages_unacknowledged": 22,
  "consumers": 1
}
```

### 3.5 결과

```bash
$ kubectl describe hpa keda-hpa-scan-worker-scaledobject -n scan
Metrics:
  "s0-rabbitmq-scan-vision" (target average value): 22 / 10  ✓
  "s1-rabbitmq-scan-answer" (target average value): 16 / 10  ✓
  "s2-rabbitmq-scan-rule" (target average value): 14 / 20
```

**커밋**: `c6245e99 fix(keda): switch to HTTP protocol for RabbitMQ metrics`

---

## 4. Issue #2: KEDA 내부 gRPC 통신 타임아웃

### 4.1 현상

HTTP 프로토콜 전환 후에도 메트릭 수집이 간헐적으로 실패:

```bash
$ kubectl logs -n keda deployment/keda-operator-metrics-apiserver --tail=20
E1226 10:15:00 provider.go:90] "timeout" 
  "error"="timeout while waiting to establish gRPC connection to KEDA Metrics Service server"
  "server"="keda-operator.keda.svc.cluster.local:9666"

W1226 10:15:02 logging.go:55] grpc: addrConn.createTransport failed to connect to 
  {Addr: "10.103.57.99:9666"...}
  Err: dial tcp 10.103.57.99:9666: i/o timeout
```

### 4.2 KEDA 아키텍처

KEDA는 2개의 주요 컴포넌트로 구성된다:

```
┌─────────────────────────────────────────────────────────────────┐
│                        KEDA Namespace                            │
│                                                                  │
│  ┌────────────────────────┐         ┌────────────────────────┐  │
│  │   keda-operator        │◄──gRPC──│ keda-metrics-apiserver │  │
│  │                        │  :9666  │                        │  │
│  │ - ScaledObject 감시    │         │ - External Metrics API │  │
│  │ - Scaler 실행          │         │ - HPA 메트릭 제공      │  │
│  │ - RabbitMQ HTTP 호출   │         │                        │  │
│  └───────────┬────────────┘         └────────────────────────┘  │
│              │                                                   │
│              │ HTTP :15672                                       │
│              ▼                                                   │
└──────────────┼──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RabbitMQ Namespace                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ eco2-rabbitmq:15672 (Management API)                    │    │
│  │ eco2-rabbitmq:5672  (AMQP)                              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 원인 분석

기존 NetworkPolicy 설정:

```yaml
# allow-keda-egress.yaml (수정 전)
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: rabbitmq
    ports:
    - port: 5672   # AMQP
    - port: 15672  # HTTP Management API
```

**누락된 설정**: KEDA 내부 컴포넌트 간 gRPC 통신(port 9666)

### 4.4 해결책

```yaml
# allow-keda-egress.yaml (수정 후)
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  # KEDA 내부 gRPC 통신
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: keda
    ports:
    - protocol: TCP
      port: 9666  # gRPC metrics service
    - protocol: TCP
      port: 8080  # Prometheus metrics
  # RabbitMQ 접근
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: rabbitmq
    ports:
    - protocol: TCP
      port: 5672
    - protocol: TCP
      port: 15672
```

### 4.5 결과

```bash
$ kubectl get scaledobject -n scan -o wide
NAME                       SCALETARGETKIND      SCALETARGETNAME   MIN   MAX   READY   ACTIVE
scan-worker-scaledobject   apps/v1.Deployment   scan-worker       1     5     True    True  ✓
```

**커밋**: `81c0adde fix(network-policy): allow KEDA internal gRPC communication (9666)`

---

## 5. Issue #3: ArgoCD selfHeal과 KEDA 스케일링 충돌

### 5.1 현상

메트릭 수집 성공 후 스케일업이 발생하지만, 즉시 스케일다운:

```bash
$ kubectl get events -n scan --sort-by=.lastTimestamp | grep -i scaled
28s  Normal   SuccessfulRescale  New size: 3; reason: s0-rabbitmq-scan-vision above target
28s  Normal   ScalingReplicaSet  Scaled up replica set scan-worker to 3 from 1
27s  Normal   ScalingReplicaSet  Scaled down replica set scan-worker to 1 from 3
```

스케일업 후 1초 만에 스케일다운 발생. HPA의 `stabilizationWindowSeconds: 300` 설정이 무시됨.

### 5.2 원인 분석

ArgoCD Application 설정 확인:

```bash
$ kubectl get application dev-scan-worker -n argocd -o jsonpath="{.spec.syncPolicy}" | jq
{
  "automated": {
    "prune": true,
    "selfHeal": true
  }
}
```

ArgoCD 동작 시퀀스:

```
Timeline
────────────────────────────────────────────────────────────────────
T+0s   KEDA HPA: replicas 1 → 3 (메트릭 기반 스케일업)
T+1s   ArgoCD: Drift 감지 (클러스터 상태 ≠ Git 상태)
       - 클러스터: replicas=3
       - Git: replicas=1 (workloads/domains/scan-worker/base/deployment.yaml)
T+1s   ArgoCD: selfHeal=true → 자동 동기화 실행
T+2s   Deployment: replicas 3 → 1 (Git 상태로 복원)
────────────────────────────────────────────────────────────────────
```

### 5.3 해결책: ignoreDifferences 설정

ArgoCD ApplicationSet에 `ignoreDifferences` 추가:

```yaml
# clusters/dev/apps/41-workers-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  template:
    spec:
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
        - CreateNamespace=false
      ignoreDifferences:
      - group: apps
        kind: Deployment
        jsonPointers:
        - /spec/replicas
```

### 5.4 주의사항

ApplicationSet은 기존 Application을 자동으로 업데이트하지 않는다. 기존 Application에 수동 패치 필요:

```bash
kubectl patch application dev-scan-worker -n argocd --type=json \
  -p '[{
    "op": "add",
    "path": "/spec/ignoreDifferences",
    "value": [{
      "group": "apps",
      "kind": "Deployment", 
      "jsonPointers": ["/spec/replicas"]
    }]
  }]'
```

### 5.5 결과

```bash
$ kubectl get pods -n scan -l app=scan-worker
NAME                           READY   STATUS    RESTARTS   AGE
scan-worker-69ff8ccc9d-djfps   2/2     Running   0          87s
scan-worker-69ff8ccc9d-jnj9z   2/2     Running   0          34m
scan-worker-69ff8ccc9d-mshx4   2/2     Running   0          87s

$ kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
    rabbitmqctl list_queues name consumers -p eco2 | grep scan
scan.vision   3
scan.answer   3
scan.rule     3
scan.reward   3
```

3개의 Worker Pod가 안정적으로 유지되며, 각 큐에 3개의 Consumer가 연결됨.

**커밋**: 
- `40824966 fix(argocd): ignore replicas field for KEDA/HPA management`
- `4f33e9ef fix(argocd): ignore replicas for worker deployments (KEDA/HPA)`

---

## 6. Issue #4: 노드 리소스 용량 초과 (maxReplicas 설정 오류)

### 6.1 현상

KEDA 스케일링 시 노드 리소스 용량을 초과하는 Pod 배치 시도로 인해 Pending 또는 CrashLoopBackOff 발생 가능성:

```bash
$ kubectl describe node k8s-worker-ai | grep -A5 'Allocated resources:'
Allocated resources:
  Resource           Requests     Limits
  cpu                755m (37%)   3500m (175%)
  memory             952Mi (25%)  3456Mi (92%)
```

### 6.2 원인 분석

기존 설정에서 maxReplicaCount=5로 설정되었으나, 노드 용량 기반 계산이 누락됨:

| 노드 | 스펙 | Allocatable | 시스템 Pod | 가용 리소스 |
|------|------|-------------|------------|-------------|
| k8s-worker-ai | t3.small | 2000m / 3826Mi | ~405m / ~330Mi | ~1595m / ~3496Mi |
| k8s-sse-gateway | t3.small | 2000m / 1854Mi | ~330m / ~200Mi | ~1670m / ~1654Mi |

### 6.3 리소스 계산

**scan-worker (k8s-worker-ai 노드)**:

```
┌─────────────────────────────────────────────────────────────┐
│ 노드: k8s-worker-ai (t3.small: 2 vCPU, 4GB)                │
├─────────────────────────────────────────────────────────────┤
│ Allocatable:      2000m CPU │ 3826Mi Memory                │
│ 시스템 DaemonSets:                                          │
│   - calico-node:    250m   │                               │
│   - ebs-csi-node:    30m   │  120Mi                        │
│   - fluent-bit:      50m   │   64Mi                        │
│   - kube-proxy:       0m   │    0Mi                        │
│   - node-exporter:    0m   │    0Mi                        │
│ 기타 Pods:                                                  │
│   - cert-manager:    75m   │  128Mi                        │
├─────────────────────────────────────────────────────────────┤
│ 가용 리소스:      1595m CPU │ 3514Mi Memory                │
├─────────────────────────────────────────────────────────────┤
│ scan-worker 1 Pod:                                          │
│   - app container:  250m   │  512Mi                        │
│   - istio-proxy:    100m   │  128Mi                        │
│   - 합계:           350m   │  640Mi                        │
├─────────────────────────────────────────────────────────────┤
│ 최대 Pod 수:                                                │
│   CPU 기준: 1595 / 350 = 4.5 → 4개                         │
│   Memory 기준: 3514 / 640 = 5.5 → 5개                      │
│   **결과: min(4, 5) = 4개**                                 │
└─────────────────────────────────────────────────────────────┘
```

**sse-gateway (k8s-sse-gateway 노드)**:

```
┌─────────────────────────────────────────────────────────────┐
│ 노드: k8s-sse-gateway (t3.small: 2 vCPU, 2GB)              │
├─────────────────────────────────────────────────────────────┤
│ Allocatable:      2000m CPU │ 1854Mi Memory                │
│ 시스템 DaemonSets:  ~330m   │  ~200Mi                      │
├─────────────────────────────────────────────────────────────┤
│ 가용 리소스:      1670m CPU │ 1654Mi Memory                │
├─────────────────────────────────────────────────────────────┤
│ sse-gateway 1 Pod:                                          │
│   - app container:  100m   │  256Mi                        │
│   - istio-proxy:    100m   │  128Mi                        │
│   - 합계:           200m   │  384Mi                        │
├─────────────────────────────────────────────────────────────┤
│ 최대 Pod 수:                                                │
│   CPU 기준: 1670 / 200 = 8.3 → 8개                         │
│   Memory 기준: 1654 / 384 = 4.3 → 4개                      │
│   **결과: min(8, 4) = 4개**                                 │
└─────────────────────────────────────────────────────────────┘
```

### 6.4 해결책

maxReplicaCount를 노드 용량에 맞게 조정:

```yaml
# scan-worker ScaledObject
spec:
  maxReplicaCount: 4  # 5 → 4 (노드 리소스 용량 기반)

# sse-gateway HPA
spec:
  maxReplicas: 4  # 5 → 4 (노드 리소스 용량 기반)
```

### 6.5 실측 데이터 (kubectl describe node)

```bash
# k8s-worker-ai 현재 상태
$ kubectl describe node k8s-worker-ai | grep -A10 'Allocated resources:'
Allocated resources:
  Resource           Requests     Limits
  cpu                755m (37%)   3500m (175%)
  memory             952Mi (25%)  3456Mi (92%)

# k8s-sse-gateway 현재 상태
$ kubectl describe node k8s-sse-gateway | grep -A10 'Allocated resources:'
Allocated resources:
  cpu                2
  memory:            1853984Ki
```

### 6.6 스케일링 계층 분리 원칙

| 계층 | 스케일링 방식 | 대상 | 비고 |
|------|---------------|------|------|
| **SSE Gateway** | HPA (CPU/Memory) | 연결 수 기반 | KEDA 불필요 |
| **Celery Workers** | KEDA (Queue Length) | 메시지 큐 기반 | HPA 비효율적 |

```
                    ┌──────────────────────────────────────────┐
                    │            Scaling Strategy              │
                    └──────────────────────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
    ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
    │  SSE Gateway  │          │  scan-worker  │          │ char-worker   │
    │   (HPA)       │          │   (KEDA)      │          │   (Static)    │
    │               │          │               │          │               │
    │ CPU/Memory    │          │ RabbitMQ      │          │ DB 의존성     │
    │ 기반 스케일링 │          │ Queue Length  │          │ 고정 replicas │
    └───────────────┘          └───────────────┘          └───────────────┘
```

**커밋**: `10cc75ab fix(scaling): 노드 리소스 용량 기반 maxReplicas 조정`

---

## 7. 최종 구성

### 7.1 ScaledObject 최종 설정

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: scan-worker-scaledobject
  namespace: scan
spec:
  scaleTargetRef:
    name: scan-worker
    kind: Deployment
  minReplicaCount: 2
  maxReplicaCount: 4  # 노드 용량 기반 (t3.small: 최대 4 Pod)
  cooldownPeriod: 300
  pollingInterval: 30
  fallback:
    failureThreshold: 3
    replicas: 2
  advanced:
    horizontalPodAutoscalerConfig:
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 300
          policies:
          - type: Percent
            value: 50
            periodSeconds: 60
        scaleUp:
          stabilizationWindowSeconds: 0
          policies:
          - type: Pods
            value: 2
            periodSeconds: 30
  triggers:
  - type: rabbitmq
    metadata:
      protocol: http
      host: http://admin:***@eco2-rabbitmq.rabbitmq.svc.cluster.local:15672
      queueName: scan.vision
      vhostName: eco2
      mode: QueueLength
      value: '10'
```

### 7.2 설정값 설명

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| minReplicaCount | 2 | 최소 Worker 수 (baseline) |
| maxReplicaCount | 4 | 최대 Worker 수 (노드 용량 기반) |
| cooldownPeriod | 300s | 스케일다운 전 대기 시간 |
| pollingInterval | 30s | 메트릭 수집 주기 |
| fallback.replicas | 2 | 메트릭 수집 실패 시 유지할 replicas |
| stabilizationWindowSeconds | 300s | 스케일다운 안정화 기간 |
| value | 10 | Pod당 처리할 메시지 수 기준 |

---

## 8. 검증 결과

### 8.1 스케일링 동작 확인

부하 발생 시:
```bash
$ kubectl get hpa -n scan -o wide
NAME                                REFERENCE                TARGETS                      REPLICAS
keda-hpa-scan-worker-scaledobject   Deployment/scan-worker   22/10, 16/10, 14/20         3
```

### 8.2 개선 지표

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| Worker replicas | 1 (고정) | 2-5 (동적) |
| Consumer/queue | 1 | 3+ |
| 메트릭 수집 | 실패 | 정상 (실시간) |
| 스케일업 유지 | 1초 만에 롤백 | 5분 안정화 |
| HPA 트리거 | CPU (비효율적) | Queue Length (효율적) |

---

## 9. 핵심 교훈

### 9.1 KEDA RabbitMQ Scaler

- AMQP 프로토콜은 `messages_ready`만 측정하므로 prefetch 환경에서는 HTTP 프로토콜 필수
- `mode: QueueLength`는 프로토콜에 따라 측정 대상이 다름
- TriggerAuthentication에서 vhost 설정 주의 (vhostName 파라미터)

### 9.2 NetworkPolicy

- KEDA는 operator와 metrics-apiserver 2개 컴포넌트로 구성
- 내부 gRPC 통신(port 9666)이 필수이며, 이에 대한 egress 정책 필요
- Egress 정책에서 자기 자신(namespace) 통신도 명시적으로 허용 필요

### 9.3 ArgoCD와 HPA/KEDA 공존

- `selfHeal: true`는 HPA/KEDA의 replicas 변경을 되돌림
- `ignoreDifferences`로 `/spec/replicas` 필드를 동기화에서 제외
- ApplicationSet 변경 시 기존 Application은 자동 업데이트되지 않음

### 9.4 노드 리소스 기반 maxReplicas 설정

- maxReplicaCount는 반드시 노드 리소스 용량을 기준으로 계산
- 계산식: `min(가용CPU ÷ Pod_CPU_Request, 가용Memory ÷ Pod_Memory_Request)`
- Istio sidecar 리소스(~100m CPU, ~128Mi Memory)를 반드시 포함
- DaemonSet 리소스(calico, ebs-csi, fluent-bit 등)를 가용 리소스에서 차감

### 9.5 디버깅 체크리스트

1. `kubectl describe hpa` - 메트릭 값 확인
2. `kubectl get scaledobject -o wide` - ACTIVE 상태 확인
3. `kubectl logs -n keda deployment/keda-operator` - Scaler 로그
4. `kubectl logs -n keda deployment/keda-operator-metrics-apiserver` - 메트릭 서버 로그
5. `kubectl get events --sort-by=.lastTimestamp` - 스케일링 이벤트 추적

---

## 10. 관련 리소스

### 10.1 변경 파일

| 파일 | 설명 |
|------|------|
| `workloads/scaling/base/scan-worker-scaledobject.yaml` | KEDA ScaledObject |
| `workloads/network-policies/base/allow-keda-egress.yaml` | NetworkPolicy |
| `clusters/dev/apps/41-workers-appset.yaml` | ArgoCD ApplicationSet |

### 10.2 관련 커밋

| 커밋 해시 | 설명 |
|-----------|------|
| `c6245e99` | AMQP → HTTP 프로토콜 전환 |
| `81c0adde` | KEDA 내부 gRPC 통신 허용 (NetworkPolicy) |
| `227231f6` | KEDA 안정화 설정 (fallback, cooldown) |
| `40824966` | ArgoCD ignoreDifferences (APIs) |
| `4f33e9ef` | ArgoCD ignoreDifferences (Workers) |
| `10cc75ab` | 노드 리소스 용량 기반 maxReplicas 조정 |

---

## 11. 참고 자료

- [KEDA Documentation - RabbitMQ Scaler](https://keda.sh/docs/2.16/scalers/rabbitmq-queue/)
- [AWS Blog - Autoscaling Kubernetes workloads with KEDA](https://aws.amazon.com/ko/blogs/tech/autoscaling-kubernetes-workloads-with-keda-using-amazon-managed-service-for-prometheus-metrics/)
- [여기어때 기술블로그 - KEDA 도입기](https://techblog.gccompany.co.kr/keda-16204b60a388)
- [ArgoCD Documentation - Diffing Customization](https://argo-cd.readthedocs.io/en/stable/user-guide/diffing/)
- [Kubernetes HPA Behavior](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#configurable-scaling-behavior)
