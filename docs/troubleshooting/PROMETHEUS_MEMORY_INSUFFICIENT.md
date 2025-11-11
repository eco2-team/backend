# Prometheus 메모리 부족 문제 해결

## 📊 문제 상황

### 증상
```bash
kubectl get pods -n monitoring | grep prometheus
# prometheus-prometheus-kube-prometheus-prometheus-0   0/2     Pending   0          62m
```

### Pod Events
```bash
kubectl describe pod -n monitoring prometheus-prometheus-kube-prometheus-prometheus-0

# Events:
#   Type     Reason            Age                 From               Message
#   ----     ------            ----                ----               -------
#   Warning  FailedScheduling  70s (x15 over 62m)  default-scheduler  
#   0/14 nodes are available: 
#   1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 
#   4 node(s) had untolerated taint {node-role.kubernetes.io/infrastructure: true}, 
#   9 Insufficient memory. preemption: 0/14 nodes are available: 
#   5 Preemption is not helpful for scheduling, 
#   9 No preemption victims found for incoming pod.
```

**핵심 에러:** `9 Insufficient memory`

---

## 🔍 원인 분석

### 1. Prometheus 리소스 요청 확인

```bash
kubectl get pod -n monitoring prometheus-prometheus-kube-prometheus-prometheus-0 -o yaml | grep -A 5 "requests:"
```

**결과:**
```yaml
requests:
  cpu: 500m
  memory: 2Gi  # ← 2GB 메모리 요청
```

### 2. Monitoring 노드 리소스 확인

```bash
kubectl describe node k8s-monitoring | grep -A 5 "Allocatable:"
```

**결과:**
```
Allocatable:
  cpu:                2
  memory:             3826536Ki  # 약 3.7GB
```

### 3. Monitoring 노드에 스케줄링된 Pod 확인

```bash
kubectl get pods -n monitoring -o wide | grep k8s-monitoring
```

**결과:**
- `prometheus-prometheus-node-exporter-*` (DaemonSet)
- 기타 monitoring Pod들

### 4. 노드 리소스 사용량 확인

```bash
kubectl top nodes | grep monitoring
```

**결과:**
```
k8s-monitoring   52m   2%   794Mi   21%
```

### 5. 문제 식별

```
Prometheus 요청: 2Gi (2048Mi)
Monitoring 노드 Allocatable: 3826536Ki (약 3736Mi)
이미 사용 중: 약 794Mi
남은 메모리: 약 2942Mi

하지만:
- 시스템 예약 메모리
- 다른 Pod의 메모리 요청
- 메모리 fragmentation

→ 실제 사용 가능 메모리가 2Gi 미만!
```

---

## ✅ 해결 방법

### 옵션 1: Prometheus 리소스 요청 감소 (권장)

**Helm values 수정:**

```yaml
# values-14nodes.yaml 또는 values.yaml
prometheus:
  prometheusSpec:
    resources:
      requests:
        cpu: 500m
        memory: 1.5Gi  # 2Gi → 1.5Gi로 감소
      limits:
        cpu: 1000m
        memory: 2Gi
```

**적용:**
```bash
helm upgrade prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f values-14nodes.yaml
```

### 옵션 2: Monitoring 노드 인스턴스 타입 업그레이드

**Terraform 수정:**

```hcl
# terraform/modules/monitoring/main.tf
resource "aws_instance" "this" {
  instance_type = "t3.medium"  # t3.small → t3.medium (4GB RAM)
  # ...
}
```

**적용:**
```bash
cd terraform
terraform plan
terraform apply
```

### 옵션 3: Prometheus를 다른 노드로 스케줄링

**nodeSelector 제거 또는 수정:**

```yaml
# Prometheus CRD 수정
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: prometheus-kube-prometheus-prometheus
  namespace: monitoring
spec:
  # nodeSelector 제거 또는 다른 노드로 변경
  # nodeSelector:
  #   workload: monitoring
```

---

## 📋 즉시 적용 (현재 클러스터)

### Prometheus 리소스 요청 감소

```bash
# Prometheus CRD 수정
kubectl patch prometheus -n monitoring prometheus-kube-prometheus-prometheus --type merge -p '{
  "spec": {
    "resources": {
      "requests": {
        "cpu": "500m",
        "memory": "1.5Gi"
      },
      "limits": {
        "cpu": "1000m",
        "memory": "2Gi"
      }
    }
  }
}'

# 또는 Prometheus Operator가 관리하는 경우
# Helm values 수정 후 재배포
```

### 확인

```bash
# Pod 상태 확인
kubectl get pods -n monitoring | grep prometheus

# Pod Events 확인
kubectl describe pod -n monitoring prometheus-prometheus-kube-prometheus-prometheus-0

# 노드 리소스 확인
kubectl describe node k8s-monitoring | grep -A 10 "Allocated resources"
```

---

## 🔍 진단 과정

### 1. Pod 상태 확인
```bash
kubectl get pods -n monitoring | grep prometheus
```

### 2. Pod Events 확인
```bash
kubectl describe pod -n monitoring prometheus-prometheus-kube-prometheus-prometheus-0 | grep -A 10 "Events:"
```

### 3. 리소스 요청 확인
```bash
kubectl get pod -n monitoring prometheus-prometheus-kube-prometheus-prometheus-0 -o jsonpath='{.spec.containers[*].resources}'
```

### 4. 노드 리소스 확인
```bash
kubectl describe node k8s-monitoring | grep -A 5 "Allocatable:"
kubectl top nodes | grep monitoring
```

### 5. 스케줄링 가능한 노드 확인
```bash
kubectl get nodes -o json | jq -r '.items[] | select(.spec.taints == null or (.spec.taints | length == 0)) | "\(.metadata.name): CPU=\(.status.allocatable.cpu), Memory=\(.status.allocatable.memory)"'
```

---

## 📊 리소스 요청 비교

### 현재 설정 (문제)
```yaml
Prometheus:
  requests:
    cpu: 500m
    memory: 2Gi  # ← 문제!
```

### Monitoring 노드
```
Allocatable:
  cpu: 2
  memory: 3826536Ki (약 3.7GB)
```

### 권장 설정
```yaml
Prometheus:
  requests:
    cpu: 500m
    memory: 1.5Gi  # ← 감소
  limits:
    cpu: 1000m
    memory: 2Gi
```

---

## 🎯 핵심 교훈

### 1. 리소스 요청 vs 실제 사용량

- **요청(Requests):** 스케줄링 시 필요한 최소 리소스
- **제한(Limits):** Pod가 사용할 수 있는 최대 리소스
- **실제 사용량:** 실제로 사용하는 리소스 (일반적으로 요청보다 적음)

**Prometheus의 경우:**
- 요청: 2Gi
- 실제 사용량: 초기에는 500Mi~1Gi 정도
- 시간이 지나면서 데이터 축적으로 증가

### 2. 노드 리소스 계획

**14-Node Architecture:**
- Monitoring 노드: t3.small (2 vCPU, 2GB RAM)
- Allocatable: 약 3.7GB (시스템 예약 제외)

**권장:**
- Monitoring 노드: t3.medium (2 vCPU, 4GB RAM)
- 또는 Prometheus 리소스 요청 감소

### 3. 메모리 fragmentation

Kubernetes는 메모리 fragmentation을 고려하지 않으므로:
- 요청 합계가 Allocatable보다 작아도 스케줄링 실패 가능
- 여유 메모리를 충분히 확보해야 함

---

## 🔗 관련 문서

- [Prometheus Resource Requirements](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)

---

## 📝 추가 참고

### Monitoring 노드 인스턴스 타입 비교

| 인스턴스 타입 | vCPU | RAM | Allocatable RAM (예상) |
|--------------|------|-----|----------------------|
| t3.small     | 2    | 2GB | 약 3.7GB |
| t3.medium    | 2    | 4GB | 약 7.7GB |
| t3.large     | 2    | 8GB | 약 15.7GB |

**권장:** t3.medium (4GB RAM) 이상

### Prometheus 메모리 사용 패턴

- **초기:** 500Mi~1Gi
- **7일 retention:** 1.5Gi~2Gi
- **30일 retention:** 3Gi~4Gi

**권장 설정:**
- Retention: 7일
- 메모리 요청: 1.5Gi
- 메모리 제한: 2Gi

---

**작성일:** 2025-11-09  
**적용 버전:** Prometheus v3.7.3  
**클러스터:** 14-Node Architecture

