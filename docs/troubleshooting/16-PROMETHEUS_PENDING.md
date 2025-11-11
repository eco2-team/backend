# Prometheus Pod Pending 문제 해결

## 📊 문제 상황

### 증상
```
kubectl get pods -n monitoring

NAME                                                      READY   STATUS    RESTARTS   AGE
prometheus-prometheus-kube-prometheus-prometheus-0        0/2     Pending   0          14h
```

### 에러 메시지
```
kubectl describe pod prometheus-prometheus-kube-prometheus-prometheus-0 -n monitoring

Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  14h   default-scheduler  0/7 nodes are available: 
    1 Insufficient cpu, 
    1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: }, 
    5 node(s) didn't match Pod's node affinity/selector.
```

---

## 🔍 원인 분석

### 1. 노드 리소스 확인

**k8s-monitoring 노드 (t3.large: 2 vCPU = 2000m)**

```bash
kubectl describe node k8s-monitoring | grep -A10 "Allocated resources:"
```

**결과:**
```
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                1130m (56%)   0 (0%)
  memory             1088Mi (14%)  768Mi (9%)
```

### 2. Pod별 CPU 사용량

```bash
kubectl get pods --all-namespaces --field-selector spec.nodeName=k8s-monitoring \
  -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,CPU_REQUEST:.spec.containers[*].resources.requests.cpu
```

**결과:**
| Pod | CPU 요청 |
|-----|----------|
| calico-node | 250m |
| ebs-csi-node (x3 containers) | 30m |
| metrics-server | 100m |
| alertmanager | 250m |
| **grafana** | **500m** |
| **합계** | **1130m** |

### 3. Prometheus 요청량

```bash
kubectl get prometheus prometheus-kube-prometheus-prometheus -n monitoring \
  -o jsonpath='{.spec.resources.requests.cpu}'
```

**결과:** `1000m`

### 4. 계산

```
현재 사용: 1130m
Prometheus: 1000m
━━━━━━━━━━━━━━━━
총 필요:   2130m > 2000m (노드 용량) ❌
```

---

## ✅ 해결 방법

### Option 1: Prometheus CPU 요청 낮추기 (채택)

#### 이유
- Prometheus는 CPU 버스트 가능 (limits 설정 없음)
- 500m은 최소 보장, 필요 시 더 사용 가능
- 현재 클러스터 규모 (7 노드)에는 500m도 충분
- 간단하고 빠른 해결

#### 즉시 적용 (현재 클러스터)

```bash
kubectl patch prometheus prometheus-kube-prometheus-prometheus -n monitoring --type merge -p '{
  "spec": {
    "resources": {
      "requests": {
        "cpu": "500m",
        "memory": "2Gi"
      },
      "limits": {
        "memory": "4Gi"
      }
    }
  }
}'
```

#### Ansible 설정 업데이트

**파일:** `ansible/playbooks/08-monitoring.yml`

**변경 전:**
```yaml
--set prometheus.prometheusSpec.resources.requests.cpu=1000m
```

**변경 후:**
```yaml
--set prometheus.prometheusSpec.resources.requests.cpu=500m
```

**변경 위치:** Line 25

---

### Option 2: Grafana를 다른 노드로 이동

```bash
# Grafana를 Worker 노드로 이동
kubectl patch deployment prometheus-grafana -n monitoring --type merge -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "workload": "application"
        }
      }
    }
  }
}'
```

**장점:**
- Prometheus 1000m 그대로 유지
- 노드 간 워크로드 분산

**단점:**
- Grafana와 Prometheus가 다른 노드에 위치
- 네트워크 오버헤드 소폭 증가

---

### Option 3: 노드 업그레이드

**현재:** t3.large (2 vCPU, 8GB)  
**업그레이드:** t3.xlarge (4 vCPU, 16GB)

**Terraform 수정:**
```terraform
# terraform/main.tf

module "monitoring" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-monitoring"
  instance_type         = "t3.xlarge"  # t3.large → t3.xlarge
  # ...
}
```

**장점:**
- 충분한 리소스 여유
- 향후 확장 가능

**단점:**
- 비용 증가: ~$60/month → ~$120/month
- 클러스터 재구축 필요

---

## 📋 검증

### 1. Pod 상태 확인

```bash
kubectl get pods -n monitoring | grep prometheus

# 예상 결과:
# prometheus-prometheus-kube-prometheus-prometheus-0   2/2   Running   0   2m
```

### 2. 노드 리소스 재확인

```bash
kubectl describe node k8s-monitoring | grep -A10 "Allocated resources:"

# 예상 결과:
# cpu   1630m (81%)  ← 2000m 이내
```

### 3. Prometheus 접속 테스트

```bash
# Port-forward
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090

# 브라우저: http://localhost:9090
```

---

## 📊 리소스 계산 (수정 후)

| 구성 요소 | CPU 요청 |
|----------|---------|
| Calico | 250m |
| EBS CSI | 30m |
| Metrics Server | 100m |
| Alertmanager | 250m |
| Grafana | 500m |
| **Prometheus** | **500m** ← 수정 |
| **합계** | **1630m (81%)** ✅ |

**여유 CPU:** 370m (18%)

---

## 🔗 관련 문서

- [Prometheus 리소스 가이드](https://prometheus.io/docs/prometheus/latest/storage/)
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Prometheus Operator Configuration](https://prometheus-operator.dev/docs/operator/api/#monitoring.coreos.com/v1.PrometheusSpec)

---

## 📝 교훈

1. **노드 사이징 시 고려사항:**
   - 시스템 Pod (Calico, kube-proxy, CSI 등) 약 500-700m 예약
   - 워크로드별 최소 20% 여유 유지

2. **모니터링 리소스 설정:**
   - 초기 설정은 보수적으로 (500m)
   - 메트릭 증가 시 점진적 증가
   - CPU limits는 설정하지 않아 버스트 허용

3. **t3.large 권장 워크로드:**
   - Prometheus (500m) + Grafana (500m) + Alertmanager (250m) + 시스템 Pod
   - 총 1600-1800m 수준까지 안정적

---

**작성일:** 2025-11-04  
**적용 버전:** Prometheus v3.7.3, Prometheus Operator v0.86.1  
**클러스터:** k8s-monitoring (t3.large, 2 vCPU)

