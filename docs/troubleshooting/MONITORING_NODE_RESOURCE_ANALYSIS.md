# Monitoring 노드 리소스 분석 (14-Node Architecture)

## 📊 현재 상태

### 인스턴스 타입
```yaml
Instance Type: t3.medium
  - vCPU: 2
  - RAM: 4GB
  - Allocatable: 약 3.7GB (시스템 예약 제외)
```

### Taint 설정
```yaml
Taint: node-role.kubernetes.io/infrastructure=true:NoSchedule
Effect: NoSchedule
```

**의미:** 일반 Pod는 스케줄링 불가, tolerations가 있는 Pod만 스케줄링 가능

---

## 📋 배포되어야 할 Pod 리소스 요청

### 1. Prometheus
```yaml
CPU: 500m
Memory: 1Gi
```

### 2. Grafana
```yaml
CPU: 500m
Memory: 512Mi
```

### 3. AlertManager
```yaml
CPU: 250m
Memory: 256Mi
```

### 4. Atlantis
```yaml
CPU: 250m
Memory: 512Mi
```

### 5. 기타 (시스템 Pod)
```yaml
Calico Node: 250m CPU
EBS CSI Node: 30m CPU, 120Mi Memory
kube-proxy: 리소스 요청 없음
Node Exporter: 리소스 요청 없음
```

---

## 🧮 리소스 요청 합계

### CPU
```
500m (Prometheus)
+ 500m (Grafana)
+ 250m (AlertManager)
+ 250m (Atlantis)
+ 280m (기타)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
= 1780m (1.78 cores)
```

**사용률:** 1780m / 2000m = **89%**

### Memory
```
1Gi (Prometheus)
+ 512Mi (Grafana)
+ 256Mi (AlertManager)
+ 512Mi (Atlantis)
+ 120Mi (기타)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
= 2.4Gi
```

**사용률:** 2.4Gi / 3.7GB = **65%**

---

## ✅ 리소스 여유

### CPU
```
Allocatable: 2000m
요청 합계: 1780m
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
여유: 220m (11%)
```

### Memory
```
Allocatable: 3.7GB (3826536Ki)
요청 합계: 2.4Gi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
여유: 1.3GB (35%)
```

---

## ⚠️ 현재 문제

### 1. Pod가 Monitoring 노드에 배포되지 않음

**현재 배포 위치:**
- Prometheus: `k8s-worker-storage`
- Grafana: `k8s-api-scan`
- AlertManager: `k8s-worker-ai`

**원인:**
- Monitoring 노드에 Taint가 있음: `node-role.kubernetes.io/infrastructure=true:NoSchedule`
- Prometheus/Grafana/AlertManager에 tolerations가 설정되지 않음

### 2. 해결 방법

**Ansible Helm values에 tolerations 추가:**

```yaml
--set prometheus.prometheusSpec.tolerations[0].key=node-role.kubernetes.io/infrastructure
--set prometheus.prometheusSpec.tolerations[0].operator=Equal
--set prometheus.prometheusSpec.tolerations[0].value="true"
--set prometheus.prometheusSpec.tolerations[0].effect=NoSchedule

--set grafana.tolerations[0].key=node-role.kubernetes.io/infrastructure
--set grafana.tolerations[0].operator=Equal
--set grafana.tolerations[0].value="true"
--set grafana.tolerations[0].effect=NoSchedule

--set alertmanager.alertmanagerSpec.tolerations[0].key=node-role.kubernetes.io/infrastructure
--set alertmanager.alertmanagerSpec.tolerations[0].operator=Equal
--set alertmanager.alertmanagerSpec.tolerations[0].value="true"
--set alertmanager.alertmanagerSpec.tolerations[0].effect=NoSchedule
```

---

## 📈 리소스 사용률 예측

### 정상 작동 시 (모든 Pod가 Monitoring 노드에 배포)

```
CPU 사용률: 89% (1780m / 2000m)
Memory 사용률: 65% (2.4Gi / 3.7GB)
```

**여유:**
- CPU: 220m (11%)
- Memory: 1.3GB (35%)

### 부하 증가 시나리오

**Prometheus 데이터 축적:**
- 초기: 1Gi 요청, 실제 사용: 500Mi~1Gi
- 7일 후: 실제 사용: 1.5Gi~2Gi (제한: 1.5Gi)
- **문제 없음** (제한 내)

**Grafana 대시보드 증가:**
- 초기: 512Mi 요청, 실제 사용: 200Mi~400Mi
- 대시보드 증가 시: 실제 사용: 400Mi~600Mi
- **문제 없음** (충분한 여유)

**Atlantis Terraform 실행:**
- 요청: 512Mi, 제한: 2Gi
- Terraform plan/apply 시: 실제 사용: 1Gi~1.5Gi
- **문제 없음** (제한 내)

---

## 🎯 결론

### 리소스 충분성

✅ **CPU:** 충분함 (여유 11%)
✅ **Memory:** 충분함 (여유 35%)

### 주의사항

⚠️ **CPU 여유가 적음 (11%)**
- Prometheus 스크랩 부하 증가 시 주의
- Atlantis Terraform 실행 시 일시적 부하 증가 가능
- 하지만 제한(limits)이 설정되어 있어 안전

✅ **Memory 여유 충분 (35%)**
- Prometheus 데이터 축적에도 여유 있음
- Grafana 대시보드 증가에도 문제 없음

### 권장사항

1. **현재 설정 유지 (t3.medium)**
   - 리소스가 충분함
   - 비용 효율적

2. **모니터링 강화**
   - CPU 사용률 90% 이상 지속 시 경고
   - Memory 사용률 80% 이상 지속 시 경고

3. **향후 확장 시**
   - CPU 부하 증가 시: t3.large (2 vCPU → 2 vCPU, 하지만 더 높은 baseline)
   - Memory 부하 증가 시: t3.medium → t3.large (4GB → 8GB)

---

## 🔧 즉시 조치 사항

### 1. Tolerations 추가 (필수)

Ansible playbook에 tolerations 추가하여 Prometheus/Grafana/AlertManager가 Monitoring 노드에 배포되도록 수정

### 2. Pod 재배포

```bash
# Helm upgrade로 tolerations 적용
helm upgrade prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring \
  --reuse-values \
  --set prometheus.prometheusSpec.tolerations[0].key=node-role.kubernetes.io/infrastructure \
  --set prometheus.prometheusSpec.tolerations[0].operator=Equal \
  --set prometheus.prometheusSpec.tolerations[0].value="true" \
  --set prometheus.prometheusSpec.tolerations[0].effect=NoSchedule \
  --set grafana.tolerations[0].key=node-role.kubernetes.io/infrastructure \
  --set grafana.tolerations[0].operator=Equal \
  --set grafana.tolerations[0].value="true" \
  --set grafana.tolerations[0].effect=NoSchedule \
  --set alertmanager.alertmanagerSpec.tolerations[0].key=node-role.kubernetes.io/infrastructure \
  --set alertmanager.alertmanagerSpec.tolerations[0].operator=Equal \
  --set alertmanager.alertmanagerSpec.tolerations[0].value="true" \
  --set alertmanager.alertmanagerSpec.tolerations[0].effect=NoSchedule
```

---

## 📊 인스턴스 타입 비교

| 인스턴스 타입 | vCPU | RAM | Allocatable RAM | CPU 여유 (89% 사용 시) | Memory 여유 (65% 사용 시) | 월 비용 (예상) |
|--------------|------|-----|-----------------|----------------------|-------------------------|--------------|
| **t3.medium** | 2    | 4GB | 3.7GB           | 220m (11%)           | 1.3GB (35%)             | $0.0416/시간 |
| t3.large     | 2    | 8GB | 7.7GB           | 220m (11%)           | 5.3GB (69%)             | $0.0832/시간 |
| t3.xlarge    | 4    | 16GB| 15.7GB          | 2220m (111%)          | 13.3GB (85%)            | $0.1664/시간 |

**권장:** t3.medium 유지 (리소스 충분, 비용 효율적)

---

**작성일:** 2025-11-09  
**클러스터:** 14-Node Architecture  
**상태:** 리소스 충분, tolerations 추가 필요

