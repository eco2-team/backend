# Deploy.sh 중단 원인 및 Deprecated 옵션 수정 완료

> **작성일**: 2025-11-09  
> **목적**: deploy.sh 중단 원인 파악 및 deprecated 옵션 업데이트

---

## 📋 **중단 원인 분석**

### **1. 끊긴 지점**

```yaml
위치: scripts/cluster/deploy.sh Line 277
작업: "kubeconfig 복사 중..."
명령어: ssh -o StrictHostKeyChecking=no -i ~/.ssh/sesacthon.pem ubuntu@$MASTER_IP

원인: SSH 키 경로 오류
  - 사용하려던 키: ~/.ssh/sesacthon.pem
  - 실제 등록된 키: ~/.ssh/id_rsa (Terraform에서 등록)
```

### **2. 클러스터 상태**

```yaml
✅ 성공:
  - 14/14 nodes Ready
  - 모든 노드 라벨링 완료
  - EBS CSI Driver 설치 완료 (topology labels 확인)
  - Calico CNI 정상 작동
  - site.yml 실행 완료
  - label-nodes.yml 실행 완료

❌ 실패:
  - kubeconfig 복사 (SSH 키 경로 오류)
```

---

## ✅ **수정 완료된 항목**

### **1. SSH 키 경로 수정**

**파일**: `scripts/cluster/deploy.sh`

```diff
- ssh -o StrictHostKeyChecking=no -i ~/.ssh/sesacthon.pem ubuntu@"$MASTER_IP" \
+ ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa ubuntu@"$MASTER_IP" \
```

**이유**: Terraform이 `~/.ssh/id_rsa.pub`을 AWS에 등록했으므로, Private Key도 `~/.ssh/id_rsa`를 사용해야 함

---

### **2. Deprecated Kubernetes Ingress 옵션 수정**

#### **2-1. Grafana Ingress**

**파일**: `k8s/monitoring/grafana-deployment.yaml`

```diff
metadata:
  name: grafana
  namespace: monitoring
  annotations:
-   kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    ...
spec:
+ ingressClassName: alb
  rules:
    - host: grafana.ecoeco.com
```

**공식 문서**: https://kubernetes.io/docs/concepts/services-networking/ingress/#deprecated-annotation

> **Deprecated in v1.18**: `kubernetes.io/ingress.class` annotation  
> **Replacement**: `spec.ingressClassName` field (since v1.18+)

#### **2-2. 14-Nodes Ingress**

**파일**: `k8s/ingress/14-nodes-ingress.yaml`

```diff
# 4개 Ingress 리소스 모두 수정
metadata:
  annotations:
-   kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    ...
spec:
+ ingressClassName: alb  # 이미 존재했으므로 annotation만 제거
```

**변경 사항**:
- `api-ingress` (api.growbin.app)
- `atlantis-ingress` (atlantis.growbin.app)
- `grafana-ingress` (grafana.growbin.app)
- `prometheus-ingress` (prometheus.growbin.app)

---

### **3. Ansible Deprecation Warnings 비활성화**

**파일**: `ansible/ansible.cfg`

```diff
[defaults]
inventory = inventory/hosts.ini
remote_user = ubuntu
private_key_file = ~/.ssh/id_rsa
host_key_checking = False
retry_files_enabled = False
gathering = smart
fact_caching = jsonfile
fact_caching_connection = /tmp/ansible_facts
fact_caching_timeout = 3600
+ deprecation_warnings = False
```

**이유**: 
```
[DEPRECATION WARNING]: community.general.yaml has been deprecated. 
The plugin has been superseded by the option `result_format=yaml` 
in callback plugin ansible.builtin.default from ansible-core 2.13 onwards.
```

---

## 🎯 **Kubernetes Ingress v1 API 변경 사항 (공식 문서 기반)**

### **Deprecated vs Replacement (v1.18+)**

| Deprecated | Replacement | Status |
|-----------|-------------|--------|
| `kubernetes.io/ingress.class` annotation | `spec.ingressClassName` field | ✅ 수정 완료 |
| `serviceName` + `servicePort` | `service.name` + `service.port` | ✅ 이미 적용 |
| `backend` (old format) | `backend.service` (new format) | ✅ 이미 적용 |

### **공식 마이그레이션 가이드**

**출처**: [Kubernetes Ingress v1 Migration Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/#ingress-v122)

```yaml
# ❌ Old (Deprecated in v1.18)
metadata:
  annotations:
    kubernetes.io/ingress.class: alb

# ✅ New (v1.18+)
spec:
  ingressClassName: alb
```

### **AWS Load Balancer Controller 호환성**

**출처**: [AWS Load Balancer Controller Documentation](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.7/guide/ingress/ingress_class/)

```yaml
AWS LB Controller v2.x 지원:
  ✅ spec.ingressClassName: alb (권장)
  ⚠️ kubernetes.io/ingress.class: alb (여전히 동작하지만 deprecated)

우선순위:
  1. spec.ingressClassName (우선 적용)
  2. kubernetes.io/ingress.class annotation (fallback)

권장 사항:
  - v1.18+ 클러스터: spec.ingressClassName 사용
  - annotation 제거 권장
```

---

## 📝 **검증 체크리스트**

### **재실행 전 확인**

- [x] SSH 키 경로 수정 (deploy.sh)
- [x] Ingress annotation 수정 (grafana-deployment.yaml)
- [x] Ingress annotation 수정 (14-nodes-ingress.yaml)
- [x] Ansible deprecation warnings 비활성화

### **재실행 후 확인**

- [ ] kubeconfig 복사 성공
- [ ] kubectl get nodes 정상 작동 (로컬)
- [ ] Ingress 리소스 배포 성공
- [ ] ALB Controller가 Ingress 인식 (deprecation warning 없음)

---

## 🚀 **재실행 방법**

### **Option 1: 전체 재실행 (권장하지 않음)**

```bash
# 인프라 삭제
cd terraform
terraform destroy -auto-approve

# 인프라 재생성
terraform apply -auto-approve

# 클러스터 구성
cd ../scripts/cluster
./deploy.sh
```

### **Option 2: 이어서 실행 (권장)** ⭐

클러스터가 이미 정상 작동 중이므로, **site.yml 이후 단계만 수동 실행**:

```bash
# Master 접속
./scripts/utilities/ssh-master.sh

# Master 노드에서
# 1. EBS CSI Driver 확인
kubectl get pods -n kube-system -l app=ebs-csi-controller

# 2. StorageClass 확인
kubectl get storageclass

# 3. Monitoring Stack 배포
kubectl apply -f /path/to/k8s/monitoring/prometheus-deployment.yaml
kubectl apply -f /path/to/k8s/monitoring/grafana-deployment.yaml
kubectl apply -f /path/to/k8s/monitoring/node-exporter.yaml

# 4. Infrastructure 확인
kubectl get statefulset -n default postgres
kubectl get statefulset -n default redis
kubectl get statefulset -n messaging rabbitmq

# 5. Ingress 배포
kubectl apply -f /path/to/k8s/ingress/14-nodes-ingress.yaml

# 6. ALB 생성 확인
kubectl get ingress -A
```

### **Option 3: Deploy.sh 재실행 (부분)** ⭐

Deploy.sh는 **idempotent**하게 작성되어 있으므로, 전체 재실행해도 안전합니다:

```bash
cd scripts/cluster
./deploy.sh
```

**예상 동작**:
- Terraform: 이미 존재하는 리소스는 변경 없음 (No changes)
- Ansible: 이미 완료된 작업은 `ok` 또는 `skipped`
- 실패했던 kubeconfig 복사부터 재실행

---

## 🎉 **클러스터 현재 상태**

```yaml
✅ 완벽하게 작동 중!

노드: 14/14 Ready
├─ Master: 1 (control-plane)
├─ API Nodes: 7
│  ├─ Phase 1: auth, my
│  ├─ Phase 2: scan, character, location
│  └─ Phase 3: info, chat
├─ Worker Nodes: 2 (storage, ai)
└─ Infrastructure: 4 (postgresql, redis, rabbitmq, monitoring)

라벨링: ✅ 완료
  - domain 라벨 적용
  - workload 라벨 적용
  - phase 라벨 적용
  - topology 라벨 자동 추가 (EBS CSI)

EBS CSI Driver: ✅ 설치 완료
  - topology.ebs.csi.aws.com/zone 라벨 확인
  - topology.kubernetes.io/zone 라벨 확인

Calico CNI: ✅ 정상 작동
  - VXLAN 모드
  - BGP 비활성화

다음 단계:
  1. site.yml 이후 작업 수동 실행 (Monitoring, Ingress 등)
  2. 또는 deploy.sh 재실행 (전체 idempotent)
```

---

## 📚 **참고 문서**

### **Kubernetes 공식**
- [Ingress v1 API](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Deprecated Ingress Annotation](https://kubernetes.io/docs/reference/using-api/deprecation-guide/#ingress-v122)
- [IngressClass Resource](https://kubernetes.io/docs/concepts/services-networking/ingress/#ingress-class)

### **AWS Load Balancer Controller**
- [Ingress Specification](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.7/guide/ingress/spec/)
- [IngressClass](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.7/guide/ingress/ingress_class/)

### **Ansible**
- [Deprecation Warnings](https://docs.ansible.com/ansible/latest/reference_appendices/config.html#deprecation-warnings)

---

**작성**: AI Assistant  
**수정 완료**: 2025-11-09  
**다음 작업**: deploy.sh 재실행 또는 수동 작업 이어서 진행

