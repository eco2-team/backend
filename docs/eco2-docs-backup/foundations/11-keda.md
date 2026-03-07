# KEDA: Kubernetes Event-Driven Autoscaling

> [← 인덱스](./00-index.md) | [← 10. NUMA](./10-numa.md)

> **공식 문서**: [KEDA Documentation](https://keda.sh/docs/)
> **GitHub**: [kedacore/keda](https://github.com/kedacore/keda)
> **CNCF 프로젝트**: Graduated (2024)

---

## 개요

KEDA (Kubernetes Event-Driven Autoscaling)는 **이벤트 기반 워크로드에 대한 세밀한 오토스케일링**을 제공하는 Kubernetes 컴포넌트이다. 기존 HPA(Horizontal Pod Autoscaler)를 확장하여 외부 이벤트 소스(메시지 큐, 스트림, 데이터베이스 등)를 기반으로 스케일링할 수 있게 한다.

### KEDA의 핵심 기여

```
┌─────────────────────────────────────────────────────────────────┐
│                    KEDA의 핵심 기여                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 이벤트 기반 스케일링                                         │
│     → CPU/메모리가 아닌 큐 길이, 메시지 수 등으로 스케일링        │
│     → 워크로드 특성에 맞는 정밀한 스케일링                       │
│                                                                  │
│  2. Zero-to-N 스케일링                                           │
│     → 이벤트가 없으면 Pod 수를 0으로 축소 (비용 절감)            │
│     → 이벤트 발생 시 자동으로 Pod 생성                           │
│                                                                  │
│  3. 다양한 이벤트 소스 지원                                      │
│     → 60+ 스케일러: RabbitMQ, Redis, Kafka, AWS SQS 등          │
│     → 커스텀 메트릭 스케일러 지원                                │
│                                                                  │
│  4. HPA와의 원활한 통합                                          │
│     → 기존 HPA 인프라 활용                                       │
│     → External Metrics API 표준 준수                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### HPA의 한계와 KEDA의 등장 배경

```
┌─────────────────────────────────────────────────────────────────┐
│                 HPA의 한계                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  문제 1: 제한된 메트릭 소스                                      │
│  ────────────────────────                                        │
│  • HPA는 기본적으로 CPU/Memory 메트릭만 지원                     │
│  • Custom Metrics는 별도 어댑터 설치 필요                        │
│  • External Metrics 연동이 복잡                                  │
│                                                                  │
│  문제 2: 최소 1개 Pod 필요                                       │
│  ─────────────────────────                                       │
│  • HPA는 minReplicas ≥ 1 (0으로 스케일 불가)                    │
│  • 유휴 시간에도 리소스 비용 발생                                │
│                                                                  │
│  문제 3: 이벤트 기반 워크로드에 부적합                           │
│  ────────────────────────────────                                │
│  • 큐 기반 워크로드: CPU 사용률과 처리량이 비례하지 않음         │
│  • 버스트 트래픽: CPU 메트릭 지연으로 스케일링 늦음              │
│                                                                  │
│  해결: KEDA                                                      │
│  ────────────                                                    │
│  • 다양한 이벤트 소스를 External Metrics로 노출                  │
│  • ScaleToZero 지원으로 비용 최적화                              │
│  • 이벤트 발생량에 비례한 정확한 스케일링                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Kubernetes HPA 기초

KEDA를 이해하기 위해 먼저 HPA의 동작 원리를 이해해야 한다.

### 1. HPA 동작 원리 (Control Loop)

```
┌─────────────────────────────────────────────────────────────────┐
│                    HPA Control Loop                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   HPA Controller                            │ │
│  │  (kube-controller-manager 내부, 기본 15초 주기)             │ │
│  └─────────────────────────┬──────────────────────────────────┘ │
│                            │                                     │
│            ┌───────────────┼───────────────┐                     │
│            │               │               │                     │
│            ▼               ▼               ▼                     │
│     ┌──────────┐    ┌──────────┐    ┌──────────┐                │
│     │ Metrics  │    │ Custom   │    │ External │                │
│     │ Server   │    │ Metrics  │    │ Metrics  │                │
│     │(Resource)│    │  API     │    │   API    │                │
│     └──────────┘    └──────────┘    └──────────┘                │
│            │               │               │                     │
│            └───────────────┴───────────────┘                     │
│                            │                                     │
│                            ▼                                     │
│                  ┌─────────────────┐                            │
│                  │ 메트릭 수집 완료 │                            │
│                  └────────┬────────┘                            │
│                           │                                      │
│                           ▼                                      │
│                  ┌─────────────────┐                            │
│                  │ 목표 Replicas   │                            │
│                  │ 계산           │                             │
│                  └────────┬────────┘                            │
│                           │                                      │
│                           ▼                                      │
│                  ┌─────────────────┐                            │
│                  │ Deployment      │                            │
│                  │ Scale 조정      │                            │
│                  └─────────────────┘                            │
│                                                                  │
│  동작 주기: --horizontal-pod-autoscaler-sync-period (기본 15s)  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Kubernetes 메트릭 API 계층

| API 그룹 | 엔드포인트 | 제공자 | 용도 |
|---------|-----------|-------|------|
| **metrics.k8s.io** | `/apis/metrics.k8s.io/v1beta1` | Metrics Server | CPU, Memory (Resource) |
| **custom.metrics.k8s.io** | `/apis/custom.metrics.k8s.io/v1beta1` | Prometheus Adapter 등 | 클러스터 내부 커스텀 메트릭 |
| **external.metrics.k8s.io** | `/apis/external.metrics.k8s.io/v1beta1` | KEDA, Stackdriver 등 | 외부 시스템 메트릭 |

```
┌─────────────────────────────────────────────────────────────────┐
│              Kubernetes Metrics API 계층 구조                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    API Server                                ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           ││
│  │  │ metrics.    │ │ custom.     │ │ external.   │           ││
│  │  │ k8s.io      │ │ metrics.    │ │ metrics.    │           ││
│  │  │             │ │ k8s.io      │ │ k8s.io      │           ││
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘           ││
│  └─────────┼───────────────┼───────────────┼───────────────────┘│
│            │               │               │                     │
│            ▼               ▼               ▼                     │
│     ┌──────────┐    ┌──────────┐    ┌──────────┐                │
│     │ Metrics  │    │Prometheus│    │   KEDA   │                │
│     │ Server   │    │ Adapter  │    │  Metrics │                │
│     │          │    │          │    │  Server  │                │
│     └──────────┘    └──────────┘    └──────────┘                │
│            │               │               │                     │
│            ▼               ▼               ▼                     │
│     ┌──────────┐    ┌──────────┐    ┌──────────┐                │
│     │  kubelet │    │Prometheus│    │ RabbitMQ │                │
│     │ (cAdvisor)│   │          │    │  Redis   │                │
│     │          │    │          │    │  Kafka   │                │
│     └──────────┘    └──────────┘    └──────────┘                │
│                                                                  │
│  KEDA는 external.metrics.k8s.io API를 제공하여                  │
│  외부 시스템의 메트릭을 HPA에 노출                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. HPA 스케일링 알고리즘

HPA는 다음 수식으로 목표 레플리카 수를 계산한다:

**기본 수식:**

\[
\text{desiredReplicas} = \lceil \text{currentReplicas} \times \frac{\text{currentMetricValue}}{\text{desiredMetricValue}} \rceil
\]

**다중 메트릭 시:**

```
각 메트릭에 대해 desiredReplicas 계산 → 최댓값 선택
```

**예시:**

```
현재 상태:
  currentReplicas = 2
  currentMetricValue = 100 (큐 메시지 수)
  desiredMetricValue = 30 (목표: Pod당 30개)

계산:
  desiredReplicas = ceil(2 × 100/30)
                  = ceil(2 × 3.33)
                  = ceil(6.67)
                  = 7

결과: 7개 Pod로 스케일 아웃
```

---

## KEDA 아키텍처

### 1. 전체 구성 요소

```
┌─────────────────────────────────────────────────────────────────┐
│                    KEDA 아키텍처                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      keda namespace                          ││
│  │                                                              ││
│  │  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐ ││
│  │  │ KEDA Operator  │  │ KEDA Metrics   │  │   Admission   │ ││
│  │  │                │  │    Server      │  │   Webhooks    │ ││
│  │  │  ┌──────────┐  │  │                │  │               │ ││
│  │  │  │ Scaler   │  │  │ External       │  │ ScaledObject  │ ││
│  │  │  │ Handler  │  │  │ Metrics API    │  │ Validation    │ ││
│  │  │  └──────────┘  │  │                │  │               │ ││
│  │  └───────┬────────┘  └───────┬────────┘  └───────────────┘ ││
│  │          │                   │                              ││
│  └──────────┼───────────────────┼──────────────────────────────┘│
│             │                   │                                │
│             │                   │ external.metrics.k8s.io       │
│             │                   │                                │
│  ┌──────────┼───────────────────┼──────────────────────────────┐│
│  │          │                   │                              ││
│  │          ▼                   ▼                              ││
│  │  ┌────────────┐      ┌────────────┐                        ││
│  │  │ ScaledObject│      │    HPA     │                        ││
│  │  │ (CR)        │      │ (자동생성) │                        ││
│  │  └──────┬─────┘      └──────┬─────┘                        ││
│  │         │                   │                               ││
│  │         └───────────────────┤                               ││
│  │                             │                               ││
│  │                             ▼                               ││
│  │                      ┌────────────┐                         ││
│  │                      │ Deployment │                         ││
│  │                      │  / Job     │                         ││
│  │                      └────────────┘                         ││
│  │                                                              ││
│  │                    target namespace                          ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│                             │                                    │
│                             ▼                                    │
│                      ┌────────────┐                              │
│                      │ RabbitMQ   │                              │
│                      │ Redis      │                              │
│                      │ Kafka      │  외부 이벤트 소스            │
│                      └────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. KEDA Operator

**역할:**
- ScaledObject/ScaledJob CRD 감시
- 트리거에 해당하는 Scaler 인스턴스 생성
- HPA 객체 자동 생성/관리
- Scale-to-Zero 처리 (HPA 없이 직접 스케일링)

```
┌─────────────────────────────────────────────────────────────────┐
│                 KEDA Operator 동작 흐름                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. ScaledObject 생성 감지                                       │
│     │                                                            │
│     ▼                                                            │
│  2. 트리거 설정 파싱 (RabbitMQ, Redis 등)                        │
│     │                                                            │
│     ▼                                                            │
│  3. 해당 Scaler 인스턴스 생성                                    │
│     │                                                            │
│     ▼                                                            │
│  4. HPA 객체 생성 (minReplicas ≥ 1일 때)                        │
│     │                                                            │
│     └─── HPA가 스케일링 담당 (1 ↔ maxReplicas)                  │
│     │                                                            │
│     ▼                                                            │
│  5. Scale-to-Zero 처리 (minReplicas = 0일 때)                   │
│     │                                                            │
│     └─── Operator가 직접 스케일링 (0 ↔ 1)                       │
│          (HPA는 0으로 스케일 불가하므로)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. KEDA Metrics Server

**역할:**
- `external.metrics.k8s.io` API 구현
- HPA가 요청하는 메트릭 제공
- Scaler를 통해 외부 시스템에서 메트릭 조회

```
HPA ──► API Server ──► KEDA Metrics Server ──► Scaler ──► RabbitMQ
              │
              │ GET /apis/external.metrics.k8s.io/v1beta1/
              │     namespaces/*/s0-rabbitmq-queue-length
              ▼
        메트릭 값 반환: {value: 150}
```

### 4. CRD 종류

| CRD | 용도 |
|-----|------|
| **ScaledObject** | Deployment, StatefulSet 등 스케일링 |
| **ScaledJob** | Job 기반 스케일링 (완료 후 삭제) |
| **TriggerAuthentication** | 네임스페이스 범위 인증 정보 |
| **ClusterTriggerAuthentication** | 클러스터 범위 인증 정보 |

---

## External Metrics API 상세

### 1. API 구조

```yaml
# API 엔드포인트
GET /apis/external.metrics.k8s.io/v1beta1/namespaces/{namespace}/{metricName}

# 예시 요청
GET /apis/external.metrics.k8s.io/v1beta1/namespaces/scan/s0-rabbitmq-queue-length

# 응답 형식
{
  "kind": "ExternalMetricValueList",
  "apiVersion": "external.metrics.k8s.io/v1beta1",
  "metadata": {},
  "items": [
    {
      "metricName": "s0-rabbitmq-queue-length",
      "metricLabels": {},
      "timestamp": "2025-12-26T10:00:00Z",
      "value": "150"
    }
  ]
}
```

### 2. KEDA 메트릭 이름 규칙

KEDA는 ScaledObject의 트리거를 기반으로 메트릭 이름을 생성한다:

```
s{trigger-index}-{scaler-type}-{metric-name}

예시:
  s0-rabbitmq-scan_queue         # 첫 번째 트리거, RabbitMQ, queue 길이
  s1-prometheus-http_requests    # 두 번째 트리거, Prometheus
```

### 3. KEDA가 메트릭을 제공하는 과정

```
┌─────────────────────────────────────────────────────────────────┐
│            KEDA External Metrics 제공 과정                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. ScaledObject 생성                                            │
│     └─► KEDA Operator가 Scaler 인스턴스 생성                     │
│                                                                  │
│  2. HPA가 메트릭 요청 (15초 주기)                                │
│     │                                                            │
│     ├─► API Server가 KEDA Metrics Server로 라우팅               │
│     │                                                            │
│     └─► KEDA Metrics Server가 해당 Scaler 호출                  │
│                                                                  │
│  3. Scaler가 외부 시스템 조회                                    │
│     │                                                            │
│     ├─► RabbitMQ: Management API로 큐 길이 조회                 │
│     ├─► Redis: XPENDING으로 Pending 메시지 수 조회              │
│     └─► Kafka: Consumer Lag 조회                                │
│                                                                  │
│  4. 메트릭 값 반환                                               │
│     └─► HPA가 desiredReplicas 계산                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## ScaledObject 상세

### 1. 전체 구조

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: scan-worker-scaledobject
  namespace: scan
spec:
  # 1. 스케일링 대상
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: scan-worker
  
  # 2. 스케일링 범위
  minReplicaCount: 0         # 최소 (0 = scale-to-zero)
  maxReplicaCount: 10        # 최대
  
  # 3. 동작 설정
  pollingInterval: 15        # 메트릭 조회 주기 (초)
  cooldownPeriod: 300        # 스케일 다운 대기 시간 (초)
  
  # 4. 고급 설정
  advanced:
    restoreToOriginalReplicaCount: false
    horizontalPodAutoscalerConfig:
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 300
  
  # 5. Fallback 설정
  fallback:
    failureThreshold: 3
    replicas: 2
  
  # 6. 트리거 정의
  triggers:
  - type: rabbitmq
    metadata:
      queueName: scan_queue
      mode: QueueLength
      value: "5"
    authenticationRef:
      name: rabbitmq-auth
```

### 2. 주요 필드 상세

#### scaleTargetRef

```yaml
scaleTargetRef:
  apiVersion: apps/v1       # 대상 API 버전
  kind: Deployment          # Deployment, StatefulSet 등
  name: scan-worker         # 대상 이름
  # envSourceContainerName: worker  # 환경변수 소스 컨테이너 (선택)
```

#### 스케일링 범위

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `minReplicaCount` | 0 | 최소 레플리카 수 (0 = scale-to-zero) |
| `maxReplicaCount` | 100 | 최대 레플리카 수 |
| `idleReplicaCount` | - | 유휴 시 유지할 레플리카 수 (선택) |

```
┌─────────────────────────────────────────────────────────────────┐
│            minReplicaCount와 idleReplicaCount 관계               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  minReplicaCount: 0, idleReplicaCount: 미설정                   │
│  ────────────────────────────────────────                        │
│  이벤트 없음 → 0개 Pod                                           │
│  이벤트 있음 → 1~maxReplicas                                    │
│                                                                  │
│  minReplicaCount: 0, idleReplicaCount: 2                        │
│  ─────────────────────────────────────────                       │
│  이벤트 없음 → 2개 Pod (대기 상태)                               │
│  이벤트 있음 → 2~maxReplicas                                    │
│                                                                  │
│  용도: 콜드 스타트 지연 없이 빠른 응답 필요 시                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### 동작 설정

| 필드 | 기본값 | 설명 |
|------|--------|------|
| `pollingInterval` | 30 | 메트릭 조회 주기 (초) |
| `cooldownPeriod` | 300 | 마지막 트리거 활성화 후 스케일 다운 대기 (초) |

```
┌─────────────────────────────────────────────────────────────────┐
│              pollingInterval과 cooldownPeriod                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  시간 ────────────────────────────────────────────────────────► │
│                                                                  │
│  메시지 수   ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░        │
│              │              │                                    │
│              │              └─ 메시지 처리 완료 (0개)            │
│              │                                                   │
│              └─ 메시지 유입 (100개)                              │
│                                                                  │
│  Pod 수          ┌────────────────────────────────┐              │
│              ────┘                                └────          │
│                  │                                │              │
│                  │  ◄──── cooldownPeriod ────►   │              │
│                  │         (300초)                │              │
│                  │                                │              │
│                  스케일 아웃               스케일 다운            │
│                                                                  │
│  cooldownPeriod 동안 메트릭이 0이어도 스케일 다운하지 않음       │
│  → 일시적 부하 감소 시 불필요한 스케일 다운 방지                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Fallback 설정

메트릭 조회 실패 시 안전 장치:

```yaml
fallback:
  failureThreshold: 3    # 연속 실패 횟수
  replicas: 2            # 실패 시 유지할 레플리카 수
```

```
정상 ──► 메트릭 조회 실패 (1회) ──► 메트릭 조회 실패 (2회) ──► 
         메트릭 조회 실패 (3회) ──► Fallback 모드 (2 replicas 유지)
```

---

## RabbitMQ Scaler 상세

### 1. 동작 원리

```
┌─────────────────────────────────────────────────────────────────┐
│              RabbitMQ Scaler 동작 원리                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐                                            │
│  │ KEDA Scaler     │                                            │
│  │ (RabbitMQ)      │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           │ HTTP GET /api/queues/{vhost}/{queue}                │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ RabbitMQ        │                                            │
│  │ Management API  │  (포트 15672)                              │
│  └────────┬────────┘                                            │
│           │                                                      │
│           │ 응답:                                                │
│           │ {                                                    │
│           │   "messages": 150,          ← 큐에 있는 메시지 수   │
│           │   "messages_ready": 145,    ← 소비 가능한 메시지    │
│           │   "messages_unacked": 5,    ← 처리 중인 메시지      │
│           │   "consumers": 2,           ← 소비자 수             │
│           │   "message_stats": {...}                             │
│           │ }                                                    │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ 메트릭 계산     │                                            │
│  │                 │                                            │
│  │ mode에 따라:    │                                            │
│  │ • QueueLength   │ → messages 사용                            │
│  │ • MessageRate   │ → message_stats 사용                       │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ HPA에 메트릭    │                                            │
│  │ 제공            │                                            │
│  └─────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. ScaledObject 설정 예시

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: scan-worker-scaledobject
  namespace: scan
spec:
  scaleTargetRef:
    name: scan-worker
  minReplicaCount: 0
  maxReplicaCount: 10
  pollingInterval: 15
  cooldownPeriod: 300
  triggers:
  - type: rabbitmq
    metadata:
      # 필수 설정
      queueName: scan_queue
      
      # 모드 선택
      mode: QueueLength           # QueueLength 또는 MessageRate
      
      # 목표 값 (Pod당 처리할 메시지 수)
      value: "5"
      
      # RabbitMQ 연결 설정
      host: amqp://guest:guest@rabbitmq.rabbitmq.svc.cluster.local:5672/
      
      # 또는 hostFromEnv로 환경변수에서 가져오기
      # hostFromEnv: RABBITMQ_URL
      
      # vhost 설정 (기본값: /)
      vhostName: /
      
      # 큐가 없을 때 동작
      activationValue: "0"        # 0이면 스케일 다운
      
      # TLS 설정
      # unsafeSsl: "true"         # 인증서 검증 비활성화
      
    authenticationRef:
      name: rabbitmq-auth
```

### 3. TriggerAuthentication 설정

```yaml
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: rabbitmq-auth
  namespace: scan
spec:
  # 방법 1: Secret에서 직접 참조
  secretTargetRef:
  - parameter: host
    name: rabbitmq-secret
    key: connection-string
  
  # 방법 2: 개별 파라미터
  # secretTargetRef:
  # - parameter: username
  #   name: rabbitmq-secret
  #   key: username
  # - parameter: password
  #   name: rabbitmq-secret
  #   key: password
```

### 4. 스케일링 계산 예시

```
┌─────────────────────────────────────────────────────────────────┐
│              RabbitMQ 스케일링 계산 예시                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  설정:                                                           │
│    mode: QueueLength                                            │
│    value: 5 (Pod당 목표 메시지 수)                              │
│    minReplicaCount: 0                                           │
│    maxReplicaCount: 10                                          │
│                                                                  │
│  상황 1: 큐에 메시지 0개                                        │
│  ─────────────────────────                                       │
│    desiredReplicas = ceil(0 / 5) = 0                            │
│    결과: 0개 Pod (scale-to-zero)                                │
│                                                                  │
│  상황 2: 큐에 메시지 15개                                       │
│  ──────────────────────────                                      │
│    desiredReplicas = ceil(15 / 5) = 3                           │
│    결과: 3개 Pod                                                │
│                                                                  │
│  상황 3: 큐에 메시지 100개                                      │
│  ───────────────────────────                                     │
│    desiredReplicas = ceil(100 / 5) = 20                         │
│    결과: 10개 Pod (maxReplicaCount 제한)                        │
│                                                                  │
│  상황 4: 큐에 메시지 2개                                        │
│  ──────────────────────────                                      │
│    desiredReplicas = ceil(2 / 5) = 1                            │
│    결과: 1개 Pod (최소 1개, 메시지 있으므로)                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5. QueueLength vs MessageRate

| 모드 | 메트릭 | 용도 |
|------|--------|------|
| **QueueLength** | 큐에 쌓인 메시지 수 | 배치 처리, 백로그 처리 |
| **MessageRate** | 초당 메시지 발행/소비율 | 실시간 스트리밍, 일정한 처리율 유지 |

```yaml
# QueueLength 모드
triggers:
- type: rabbitmq
  metadata:
    mode: QueueLength
    value: "5"           # Pod당 5개 메시지 처리

# MessageRate 모드
triggers:
- type: rabbitmq
  metadata:
    mode: MessageRate
    value: "100"         # Pod당 초당 100개 메시지 처리
```

---

## 스케일링 알고리즘 상세

### 1. KEDA + HPA 통합 알고리즘

```
┌─────────────────────────────────────────────────────────────────┐
│              KEDA 스케일링 알고리즘                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1: 메트릭 수집 (pollingInterval 주기)                    │
│  ─────────────────────────────────────────                       │
│  각 트리거에서 메트릭 값 조회                                    │
│  예: rabbitmq.GetMetrics() → 150 (큐 길이)                      │
│                                                                  │
│  Phase 2: IsActive 판단                                          │
│  ──────────────────────                                          │
│  메트릭 > activationValue → true (스케일링 필요)                │
│  메트릭 ≤ activationValue → false (유휴 상태)                   │
│                                                                  │
│  Phase 3: Scale-to-Zero 처리 (Operator)                         │
│  ─────────────────────────────────────                           │
│  if (!IsActive && currentReplicas > 0) {                        │
│      cooldownPeriod 대기 후 replicas = 0                        │
│  }                                                               │
│  if (IsActive && currentReplicas == 0) {                        │
│      replicas = 1 (즉시)                                        │
│  }                                                               │
│                                                                  │
│  Phase 4: HPA 스케일링 (1 ↔ maxReplicas)                        │
│  ──────────────────────────────────────                          │
│  HPA가 external.metrics.k8s.io에서 메트릭 조회                  │
│  desiredReplicas = ceil(currentMetric / targetMetric)           │
│  Deployment.replicas 조정                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 수식 상세

**단일 트리거:**

\[
\text{desiredReplicas} = \lceil \frac{\text{currentMetricValue}}{\text{targetMetricValue}} \rceil
\]

**다중 트리거:**

\[
\text{desiredReplicas} = \max(\text{desiredReplicas}_1, \text{desiredReplicas}_2, ..., \text{desiredReplicas}_n)
\]

**예시 (다중 트리거):**

```yaml
triggers:
- type: rabbitmq
  metadata:
    queueName: scan_queue
    value: "5"              # 목표: Pod당 5개
- type: prometheus
  metadata:
    query: http_requests_total
    threshold: "100"        # 목표: Pod당 100 RPS
```

```
큐 메시지: 30개 → desiredReplicas_rabbitmq = ceil(30/5) = 6
HTTP RPS: 250   → desiredReplicas_prometheus = ceil(250/100) = 3

최종: max(6, 3) = 6 Pods
```

### 3. Stabilization Window

급격한 스케일 변동을 방지하기 위한 안정화 기간:

```yaml
advanced:
  horizontalPodAutoscalerConfig:
    behavior:
      scaleDown:
        stabilizationWindowSeconds: 300    # 5분
        policies:
        - type: Percent
          value: 10
          periodSeconds: 60                # 분당 최대 10% 감소
      scaleUp:
        stabilizationWindowSeconds: 0      # 즉시 스케일 업
        policies:
        - type: Pods
          value: 4
          periodSeconds: 60                # 분당 최대 4개 증가
```

```
┌─────────────────────────────────────────────────────────────────┐
│              Stabilization Window 동작                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  시간 ────────────────────────────────────────────────────────► │
│                                                                  │
│  계산된 replicas                                                 │
│                                                                  │
│       10  ──────┐                                                │
│                 │                                                │
│        6  ──────┼──────┐                                         │
│                 │      │                                         │
│        3  ──────┼──────┼──────────────────────────────────       │
│                 │      │                                         │
│                 │      │                                         │
│                 │◄────►│ stabilizationWindowSeconds             │
│                 │      │                                         │
│                 │      └─ 실제 스케일 다운 시점                   │
│                 │                                                │
│                 └─ 스케일 다운 요청 시점                          │
│                                                                  │
│  Window 기간 중 가장 높은 값으로 유지                            │
│  → 스파이크 후 급격한 스케일 다운 방지                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 운영 고려사항

### 1. Scale-to-Zero 동작

```
┌─────────────────────────────────────────────────────────────────┐
│              Scale-to-Zero 동작 상세                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    0 Replicas                                ││
│  │                        │                                     ││
│  │  이벤트 감지 ──────────┤                                     ││
│  │  (pollingInterval)    │                                     ││
│  │                        ▼                                     ││
│  │              ┌─────────────────┐                            ││
│  │              │ KEDA Operator가 │                            ││
│  │              │ replicas = 1    │                            ││
│  │              └────────┬────────┘                            ││
│  │                       │                                      ││
│  │                       ▼                                      ││
│  │              ┌─────────────────┐                            ││
│  │              │ Pod 생성 (콜드  │                            ││
│  │              │ 스타트 지연)    │                            ││
│  │              └────────┬────────┘                            ││
│  │                       │                                      ││
│  │                       ▼                                      ││
│  │              ┌─────────────────┐                            ││
│  │              │ HPA 활성화      │                            ││
│  │              │ (1↔maxReplicas) │                            ││
│  │              └─────────────────┘                            ││
│  │                                                              ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  주의사항:                                                       │
│  ─────────                                                       │
│  • 콜드 스타트 지연: Pod 생성 + 컨테이너 시작 + 초기화          │
│  • 지연 허용 불가 시: idleReplicaCount 또는 minReplicaCount ≥ 1│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 콜드 스타트 최적화

| 방법 | 설명 |
|------|------|
| `idleReplicaCount` | 유휴 시에도 지정 수 Pod 유지 |
| 이미지 프리풀 | 노드에 이미지 미리 캐시 |
| Init 컨테이너 최적화 | 의존성 초기화 시간 단축 |
| PodDisruptionBudget | 최소 가용 Pod 보장 |

### 3. 메트릭 지연 고려

```
┌─────────────────────────────────────────────────────────────────┐
│              메트릭 지연과 스케일링 타이밍                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  시간 흐름:                                                      │
│                                                                  │
│  T+0s   : 메시지 100개 유입                                     │
│  T+15s  : KEDA 메트릭 조회 (pollingInterval)                    │
│  T+15s  : HPA 메트릭 조회                                       │
│  T+16s  : HPA가 스케일 결정                                     │
│  T+20s  : 새 Pod 스케줄링                                       │
│  T+30s  : 컨테이너 시작                                         │
│  T+45s  : Pod Ready, 메시지 처리 시작                           │
│                                                                  │
│  총 지연: ~45초                                                  │
│                                                                  │
│  최적화:                                                         │
│  ─────────                                                       │
│  • pollingInterval 감소 (예: 5초)                               │
│  • 선제적 스케일링 (예: activationValue < threshold)            │
│  • idleReplicaCount로 워밍업된 Pod 유지                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Prometheus 메트릭 모니터링

KEDA가 노출하는 Prometheus 메트릭:

```yaml
# Operator 메트릭
keda_scaler_active{namespace, scaledObject, scaler}        # 스케일러 활성 상태
keda_scaler_metrics_value{namespace, scaledObject, scaler} # 현재 메트릭 값
keda_scaled_object_errors{namespace, scaledObject}         # 에러 횟수

# Metrics Server 메트릭
keda_metrics_adapter_scaler_metrics_value{...}             # 어댑터가 제공하는 메트릭

# 예시 쿼리
# 스케일러별 현재 메트릭 값
keda_scaler_metrics_value{namespace="scan", scaledObject="scan-worker-scaledobject"}

# 에러 발생 추이
rate(keda_scaled_object_errors[5m])
```

### 5. 트러블슈팅 체크리스트

```
┌─────────────────────────────────────────────────────────────────┐
│              KEDA 트러블슈팅 체크리스트                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ☐ ScaledObject 상태 확인                                       │
│     kubectl get scaledobject -n {namespace}                     │
│     kubectl describe scaledobject {name} -n {namespace}         │
│                                                                  │
│  ☐ HPA 자동 생성 확인                                           │
│     kubectl get hpa -n {namespace}                              │
│                                                                  │
│  ☐ KEDA Operator 로그 확인                                      │
│     kubectl logs -n keda deployment/keda-operator               │
│                                                                  │
│  ☐ Metrics Server 로그 확인                                     │
│     kubectl logs -n keda deployment/keda-metrics-apiserver      │
│                                                                  │
│  ☐ External Metrics API 직접 조회                               │
│     kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1/   │
│         namespaces/{ns}/{metric-name}"                          │
│                                                                  │
│  ☐ TriggerAuthentication 검증                                   │
│     kubectl get triggerauthentication -n {namespace}            │
│     kubectl describe triggerauthentication {name} -n {namespace}│
│                                                                  │
│  ☐ RabbitMQ Management API 직접 확인                            │
│     curl -u guest:guest http://rabbitmq:15672/api/queues        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 다른 스케일러 개요

KEDA는 60개 이상의 스케일러를 지원한다. 주요 스케일러:

| 스케일러 | 메트릭 | 용도 |
|---------|--------|------|
| **rabbitmq** | 큐 길이, 메시지율 | 메시지 큐 기반 워커 |
| **redis-streams** | Pending 메시지 수, Consumer Lag | 스트림 처리 |
| **kafka** | Consumer Lag | 이벤트 스트리밍 |
| **prometheus** | PromQL 쿼리 결과 | 커스텀 메트릭 |
| **aws-sqs** | ApproximateNumberOfMessages | AWS 메시지 큐 |
| **azure-servicebus** | 메시지 수 | Azure 메시지 큐 |
| **cron** | Cron 스케줄 | 시간 기반 스케일링 |
| **cpu/memory** | 리소스 사용률 | 기본 리소스 기반 |

---

## 참고 자료

### 공식 문서
- [KEDA Documentation](https://keda.sh/docs/)
- [KEDA Scalers](https://keda.sh/docs/scalers/)
- [RabbitMQ Scaler](https://keda.sh/docs/scalers/rabbitmq-queue/)

### Kubernetes 문서
- [Horizontal Pod Autoscaler](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [External Metrics API](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/#autoscaling-on-metrics-not-related-to-kubernetes-objects)
- [HPA Algorithm](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#algorithm-details)

### 관련 Foundations
- [03-amqp-protocol.md](./03-amqp-protocol.md) - RabbitMQ/AMQP 기초
- [07-redis-streams.md](./07-redis-streams.md) - Redis Streams 기반 스케일링

---

## 버전 정보

- 작성일: 2025-12-26
- KEDA 버전: 2.16.0
- Kubernetes 버전: 1.28+
- 대상: Kubernetes 오토스케일링 학습자


