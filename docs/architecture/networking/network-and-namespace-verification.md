# 네트워크 및 네임스페이스 구성 검증

> **작성일**: 2025-11-09  
> **대상**: 14-Node Kubernetes 클러스터  
> **목적**: VPC/SG/Calico VXLAN 네트워크 및 도메인별 네임스페이스 할당 검증

---

## 📋 **목차**

1. [VPC 및 네트워크 구성](#1-vpc-및-네트워크-구성)
2. [Security Group 설정](#2-security-group-설정)
3. [Calico VXLAN 네트워크](#3-calico-vxlan-네트워크)
4. [노드 라벨링 및 도메인 할당](#4-노드-라벨링-및-도메인-할당)
5. [네임스페이스 구조](#5-네임스페이스-구조)
6. [Ingress 및 라우팅](#6-ingress-및-라우팅)
7. [검증 체크리스트](#7-검증-체크리스트)

---

## 1️⃣ **VPC 및 네트워크 구성**

### **VPC 설정**
- **파일**: `terraform/modules/vpc/main.tf`
- **CIDR**: `10.0.0.0/16`
- **DNS Support**: Enabled
- **DNS Hostnames**: Enabled

### **서브넷 구성**
```yaml
Public Subnets (3개):
  - 10.0.1.0/24 (ap-northeast-2a)
  - 10.0.2.0/24 (ap-northeast-2b)
  - 10.0.3.0/24 (ap-northeast-2c)

Tags:
  - kubernetes.io/role/elb: "1"
  - kubernetes.io/cluster/prod-sesacthon: "shared"
```

### **Internet Gateway**
- 모든 Public Subnet은 IGW를 통해 외부 통신
- Route Table: `0.0.0.0/0 → IGW`

---

## 2️⃣ **Security Group 설정**

### **Master SG (`k8s-master-sg`)**

**파일**: `terraform/modules/security-groups/main.tf`

| 프로토콜 | 포트 | 소스 | 설명 |
|---------|------|------|------|
| TCP | 22 | Allowed CIDR | SSH |
| TCP | 6443 | 0.0.0.0/0 | Kubernetes API Server |
| TCP | 80, 443 | 0.0.0.0/0 | HTTP/HTTPS |
| TCP | 2379-2380 | Self | etcd |
| TCP | 10250 | Self | Kubelet API |
| TCP | 10257 | Self | kube-controller-manager |
| TCP | 10259 | Self | kube-scheduler |
| TCP | 30000-32767 | 0.0.0.0/0 | NodePort Services |
| **UDP** | **4789** | **Self** | **VXLAN (Calico)** ✅ |

### **Worker SG (`k8s-worker-sg`)**

| 프로토콜 | 포트 | 소스 | 설명 |
|---------|------|------|------|
| TCP | 22 | Allowed CIDR | SSH |
| TCP | 10250-10252 | Master SG | Kubelet API from Master |
| TCP | 30000-32767 | Master SG | NodePort from Master |
| TCP | 10256 | Self | kube-proxy health |
| All | 0-65535 | Self | Worker 간 통신 |
| **UDP** | **4789** | **Self** | **VXLAN (Calico)** ✅ |

### **Master ↔ Worker VXLAN 규칙**

```terraform
# Master → Worker VXLAN
resource "aws_security_group_rule" "master_to_worker_vxlan" {
  type                     = "ingress"
  from_port                = 4789
  to_port                  = 4789
  protocol                 = "udp"
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.master.id
  description              = "VXLAN from master (Calico)"
}

# Worker → Master VXLAN
resource "aws_security_group_rule" "worker_to_master_vxlan" {
  type                     = "ingress"
  from_port                = 4789
  to_port                  = 4789
  protocol                 = "udp"
  security_group_id        = aws_security_group.master.id
  source_security_group_id = aws_security_group.worker.id
  description              = "VXLAN from worker (Calico)"
}
```

✅ **검증됨**: UDP 4789 포트가 Master SG, Worker SG, 그리고 Master ↔ Worker 간 모두 열려 있음

---

## 3️⃣ **Calico VXLAN 네트워크**

### **설정 파일**
- **파일**: `ansible/playbooks/04-cni-install.yml`
- **모드**: VXLAN 전용 (BGP 완전 비활성화)

### **Calico 설정**

```yaml
# IP Pool - VXLAN 전용
kubectl patch ippool default-ipv4-ippool --type=merge --patch='
{
  "spec": {
    "ipipMode": "Never",          # IPIP 비활성화
    "vxlanMode": "Always",        # VXLAN 전용 ✅
    "natOutgoing": true           # NAT 활성화
  }
}'

# BGP 완전 비활성화
apiVersion: crd.projectcalico.org/v1
kind: BGPConfiguration
metadata:
  name: default
spec:
  nodeToNodeMeshEnabled: false    # BGP Mesh 비활성화 ✅
  asNumber: 64512

# Felix 설정
apiVersion: crd.projectcalico.org/v1
kind: FelixConfiguration
metadata:
  name: default
spec:
  bpfEnabled: false
  ipipEnabled: false
  vxlanEnabled: true              # VXLAN 활성화 ✅
```

### **VXLAN 동작 방식**

```
┌─────────────────────────────────────────────────────────────┐
│                    Calico VXLAN Overlay                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Master Node (10.0.1.173)                                   │
│  ├── Pod CIDR: 192.168.249.0/24                            │
│  └── VXLAN Interface: vxlan.calico (UDP 4789)              │
│                                                             │
│         UDP 4789 ↓↑ (SG Rule 허용)                         │
│                                                             │
│  Worker Node (10.0.1.94)                                    │
│  ├── Pod CIDR: 192.168.xxx.0/24                            │
│  └── VXLAN Interface: vxlan.calico (UDP 4789)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘

특징:
  ✅ Overlay Network: Pod IP는 Node IP와 분리
  ✅ Cross-AZ 통신: AZ 간 Pod 통신 가능
  ✅ NAT Outgoing: Pod → 외부 트래픽은 Node IP로 SNAT
  ✅ No BGP: AWS VPC 환경에서 BGP 불필요
```

### **검증 명령어**

```bash
# Master 노드에서
kubectl get ippool -o yaml
kubectl get bgpconfig -o yaml
kubectl get felixconfiguration -o yaml

# Calico Node 상태 확인
kubectl get pods -n kube-system -l k8s-app=calico-node -o wide

# VXLAN 인터페이스 확인
ssh master "ip -d link show vxlan.calico"
```

---

## 4️⃣ **노드 라벨링 및 도메인 할당**

### **라벨링 규칙**
- **파일**: `ansible/playbooks/label-nodes.yml`

### **Phase별 노드 구성**

#### **Phase 1: Core Services**
```yaml
k8s-api-auth:
  workload: api
  domain: auth
  phase: "1"
  node-role.kubernetes.io/api: auth

k8s-api-my:
  workload: api
  domain: my
  phase: "1"
  node-role.kubernetes.io/api: my

k8s-postgresql:
  workload: database
  phase: "1"
  node-role.kubernetes.io/infrastructure: postgresql
  Taint: node-role.kubernetes.io/infrastructure=true:NoSchedule

k8s-redis:
  workload: cache
  phase: "1"
  node-role.kubernetes.io/infrastructure: redis
  Taint: node-role.kubernetes.io/infrastructure=true:NoSchedule
```

#### **Phase 2: Extended APIs**
```yaml
k8s-api-scan:
  workload: api
  domain: scan
  phase: "2"
  node-role.kubernetes.io/api: scan

k8s-api-character:
  workload: api
  domain: character
  phase: "2"
  node-role.kubernetes.io/api: character

k8s-api-location:
  workload: api
  domain: location
  phase: "2"
  node-role.kubernetes.io/api: location
```

#### **Phase 3: Advanced APIs**
```yaml
k8s-api-info:
  workload: api
  domain: info
  phase: "3"
  node-role.kubernetes.io/api: info

k8s-api-chat:
  workload: api
  domain: chat
  phase: "3"
  node-role.kubernetes.io/api: chat
```

#### **Phase 4: Workers & Infrastructure**
```yaml
k8s-worker-storage:
  workload: worker-storage
  worker-type: io-bound
  pool-type: eventlet
  domain: scan
  phase: "4"
  node-role.kubernetes.io/worker: storage

k8s-worker-ai:
  workload: worker-ai
  worker-type: network-bound
  pool-type: prefork
  domain: ai
  phase: "4"
  node-role.kubernetes.io/worker: ai

k8s-rabbitmq:
  workload: message-queue
  phase: "4"
  node-role.kubernetes.io/infrastructure: rabbitmq
  Taint: node-role.kubernetes.io/infrastructure=true:NoSchedule

k8s-monitoring:
  workload: monitoring
  phase: "4"
  node-role.kubernetes.io/infrastructure: monitoring
  Taint: node-role.kubernetes.io/infrastructure=true:NoSchedule
```

### **노드 토폴로지 요약**

```
14-Node Cluster (32 vCPU, 38GB RAM)

┌─────────────────────────────────────────────────────────────┐
│ Master (t3.small, 2GB)                                       │
│   - 10.0.1.173                                              │
│   - Control Plane                                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ API Nodes (7x t3.small, 14GB)                               │
├─────────────────────────────────────────────────────────────┤
│ Phase 1: auth (10.0.1.47), my (10.0.2.190)                 │
│ Phase 2: scan (10.0.3.195), character (10.0.1.219),        │
│          location (10.0.2.114)                              │
│ Phase 3: info (10.0.3.11), chat (10.0.1.199)               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Worker Nodes (2x t3.small, 4GB)                             │
├─────────────────────────────────────────────────────────────┤
│ storage (10.0.3.177): I/O Bound, Eventlet                  │
│ ai (10.0.1.94): Network Bound, Prefork                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Infrastructure Nodes (4x t3.medium, 16GB)                   │
├─────────────────────────────────────────────────────────────┤
│ postgresql (10.0.1.51): Database                            │
│ redis (10.0.2.22): Cache                                    │
│ rabbitmq (10.0.2.191): Message Queue                        │
│ monitoring (10.0.2.205): Prometheus/Grafana                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 5️⃣ **네임스페이스 구조**

### **현재 구성**

| 네임스페이스 | 용도 | 배포 리소스 |
|------------|------|------------|
| `default` | API Deployments | auth-api, my-api, scan-api, character-api, location-api, info-api, chat-api |
| `monitoring` | Monitoring Stack | prometheus, grafana, node-exporter |
| `atlantis` | GitOps | atlantis |
| `kube-system` | Kubernetes Core | calico-node, coredns, kube-proxy, ebs-csi-controller |

### **권장 구조 (향후 개선)**

```yaml
# 도메인별 네임스페이스 분리 (향후)
auth:       auth-api, auth-worker
my:         my-api, my-worker
scan:       scan-api, scan-worker
character:  character-api, character-worker
location:   location-api, location-worker
info:       info-api, info-worker
chat:       chat-api, chat-worker

# Infrastructure
infrastructure:
  - postgresql
  - redis
  - rabbitmq

# Monitoring
monitoring:
  - prometheus
  - grafana
  - node-exporter

# GitOps
atlantis:
  - atlantis
```

**현재 상태**: 모든 API가 `default` 네임스페이스에 배포  
**개선 방향**: 도메인별 네임스페이스 분리 (Phase별 단계적 적용)

---

## 6️⃣ **Ingress 및 라우팅**

### **단일 ALB 통합 구성**
- **파일**: `k8s/ingress/14-nodes-ingress.yaml`
- **ALB Group**: `ecoeco-main`

### **라우팅 규칙**

```yaml
┌─────────────────────────────────────────────────────────────┐
│              ALB (ecoeco-main group)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. api.growbin.app                                         │
│     ├── /api/v1/auth → auth-api:8000 (domain=auth)         │
│     ├── /api/v1/my → my-api:8000 (domain=my)               │
│     ├── /api/v1/scan → scan-api:8000 (domain=scan)         │
│     ├── /api/v1/character → character-api:8000             │
│     ├── /api/v1/location → location-api:8000               │
│     ├── /api/v1/info → info-api:8000 (domain=info)         │
│     └── /api/v1/chat → chat-api:8000 (domain=chat)         │
│                                                             │
│  2. atlantis.growbin.app → atlantis:80                      │
│  3. grafana.growbin.app → grafana:3000                      │
│  4. prometheus.growbin.app → prometheus:9090                │
│                                                             │
└─────────────────────────────────────────────────────────────┘

특징:
  ✅ 단일 ALB로 통합 (비용 절감: ~$16/월)
  ✅ Path-based routing (도메인별 경로)
  ✅ HTTPS 리다이렉트 (ACM 인증서)
  ✅ Health Check 자동
```

### **Service → Pod 매핑**

```yaml
# API Services
auth-api (Service) → Pod on k8s-api-auth (NodeSelector: domain=auth)
my-api (Service) → Pod on k8s-api-my (NodeSelector: domain=my)
scan-api (Service) → Pod on k8s-api-scan (NodeSelector: domain=scan)
character-api (Service) → Pod on k8s-api-character (NodeSelector: domain=character)
location-api (Service) → Pod on k8s-api-location (NodeSelector: domain=location)
info-api (Service) → Pod on k8s-api-info (NodeSelector: domain=info)
chat-api (Service) → Pod on k8s-api-chat (NodeSelector: domain=chat)

# Monitoring Services
prometheus (Service) → Pod on k8s-monitoring (NodeSelector: workload=monitoring)
grafana (Service) → Pod on k8s-monitoring (NodeSelector: workload=monitoring)
node-exporter (DaemonSet) → All Nodes

# Infrastructure Services
postgresql → Pod on k8s-postgresql (with Taint toleration)
redis → Pod on k8s-redis (with Taint toleration)
rabbitmq → Pod on k8s-rabbitmq (with Taint toleration)
```

---

## 7️⃣ **검증 체크리스트**

### **네트워크 검증**

```bash
# ✅ 1. VPC 및 서브넷 확인
terraform output vpc_id
aws ec2 describe-subnets --filters "Name=vpc-id,Values=$(terraform output -raw vpc_id)"

# ✅ 2. Security Group 규칙 확인
aws ec2 describe-security-groups --group-ids $(terraform output -raw master_sg_id)
aws ec2 describe-security-groups --group-ids $(terraform output -raw worker_sg_id)

# ✅ 3. VXLAN 포트 확인 (UDP 4789)
aws ec2 describe-security-group-rules --filters \
  "Name=ip-protocol,Values=udp" \
  "Name=from-port,Values=4789" \
  "Name=to-port,Values=4789"
```

### **Calico 검증**

```bash
# Master 노드에서
ssh ubuntu@<master-ip>

# ✅ 1. Calico Pod 상태
kubectl get pods -n kube-system -l k8s-app=calico-node -o wide

# ✅ 2. IP Pool 설정 (VXLAN 전용)
kubectl get ippool -o yaml | grep -A 5 "vxlanMode"

# ✅ 3. BGP 비활성화 확인
kubectl get bgpconfig default -o yaml

# ✅ 4. Felix VXLAN 활성화 확인
kubectl get felixconfiguration default -o yaml | grep vxlanEnabled

# ✅ 5. VXLAN 인터페이스 확인
ip -d link show vxlan.calico
```

### **노드 라벨링 검증**

```bash
# ✅ 1. 모든 노드 라벨 확인
kubectl get nodes --show-labels

# ✅ 2. 도메인별 노드 확인
kubectl get nodes -l domain=auth
kubectl get nodes -l domain=scan
kubectl get nodes -l workload=monitoring

# ✅ 3. Infrastructure Taint 확인
kubectl describe node k8s-postgresql | grep Taints
kubectl describe node k8s-redis | grep Taints
kubectl describe node k8s-rabbitmq | grep Taints
kubectl describe node k8s-monitoring | grep Taints
```

### **Pod 통신 검증**

```bash
# ✅ 1. Cross-node Pod 통신 테스트
kubectl run test-pod-1 --image=busybox --restart=Never -- sleep 3600
kubectl run test-pod-2 --image=busybox --restart=Never -- sleep 3600

POD1_IP=$(kubectl get pod test-pod-1 -o jsonpath='{.status.podIP}')
POD2_IP=$(kubectl get pod test-pod-2 -o jsonpath='{.status.podIP}')

kubectl exec test-pod-1 -- ping -c 3 $POD2_IP
kubectl exec test-pod-2 -- ping -c 3 $POD1_IP

# ✅ 2. Service Discovery 테스트
kubectl exec test-pod-1 -- nslookup kubernetes.default.svc.cluster.local

# Cleanup
kubectl delete pod test-pod-1 test-pod-2
```

### **IAM 권한 검증**

```bash
# ✅ EBS CSI Driver 권한 확인
aws iam get-role --role-name k8s-node-role-prod
aws iam list-attached-role-policies --role-name k8s-node-role-prod
aws iam get-policy-version --policy-arn <ebs-csi-policy-arn> --version-id v1
```

---

## ✅ **검증 결과 요약**

| 항목 | 상태 | 비고 |
|-----|------|------|
| VPC 구성 | ✅ | 10.0.0.0/16, 3 AZs |
| Security Group (Master) | ✅ | UDP 4789 (VXLAN) 포함 |
| Security Group (Worker) | ✅ | UDP 4789 (VXLAN) 포함 |
| Master ↔ Worker VXLAN | ✅ | 양방향 UDP 4789 허용 |
| Calico VXLAN 모드 | ✅ | vxlanMode: Always |
| BGP 비활성화 | ✅ | nodeToNodeMeshEnabled: false |
| 노드 라벨링 (14 nodes) | ✅ | 도메인별 할당 완료 |
| Infrastructure Taint | ✅ | 4개 노드 Taint 적용 |
| EBS CSI IAM 권한 | ✅ | ec2:CreateVolume 권한 추가됨 |
| Ingress 라우팅 | ✅ | 단일 ALB, 도메인별 경로 |

---

## 📝 **다음 단계**

1. **인프라 재배포**
   ```bash
   cd terraform
   terraform apply -auto-approve
   ```

2. **클러스터 구성**
   ```bash
   cd ../scripts/cluster
   ./deploy.sh
   ```

3. **네트워크 검증**
   - VXLAN 인터페이스 확인
   - Pod 간 통신 테스트
   - Service Discovery 확인

4. **Monitoring 배포**
   - Prometheus, Grafana, Node Exporter
   - PVC → EBS Volume 바인딩 확인

5. **API 배포**
   - 7개 도메인별 API Deployment
   - Service 생성 및 Ingress 라우팅

---

**작성**: AI Assistant  
**검증 완료**: 2025-11-09  
**다음 검증**: 인프라 재배포 후

