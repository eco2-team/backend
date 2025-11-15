# 14-Node vs 초기 클러스터 리소스 비교 분석

> **작성일**: 2025-11-09  
> **목적**: EBS CSI Driver 외에 빠진 리소스 확인  
> **비교 대상**: 초기 Phase 1&2 (8-Node) vs 현재 14-Node

---

## 📋 **목차**

1. [Terraform 리소스 비교](#1-terraform-리소스-비교)
2. [Ansible Roles 비교](#2-ansible-roles-비교)
3. [Kubernetes Addons 비교](#3-kubernetes-addons-비교)
4. [빠진 리소스 요약](#4-빠진-리소스-요약)
5. [추가 필요한 작업](#5-추가-필요한-작업)

---

## 1️⃣ **Terraform 리소스 비교**

### **EC2 인스턴스 (✅ 완료)**

| 구분 | 초기 (8-Node) | 현재 (14-Node) | 상태 |
|-----|--------------|---------------|------|
| **Master** | 1 (t3.large, 8GB) | 1 (t3.large, 8GB) | ✅ |
| **API Nodes** | 5 (auth, my, scan, character, location) | 7 (+ info, chat) | ✅ |
| **Worker Nodes** | 0 | 2 (storage, ai) | ✅ |
| **PostgreSQL** | 1 (t3.medium, 4GB) | 1 (t3.medium, 4GB) | ✅ |
| **Redis** | 1 (t3.small, 2GB) | 1 (t3.small, 2GB) | ✅ |
| **RabbitMQ** | 0 | 1 (t3.small, 2GB) | ✅ |
| **Monitoring** | 0 (Master에 통합) | 1 (t3.medium, 4GB) | ✅ |
| **총계** | 8 nodes | 14 nodes | ✅ |

### **네트워크 리소스 (✅ 완료)**

| 리소스 | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **VPC** | ✅ | ✅ | 동일 |
| **Subnets (Public)** | ✅ 3개 | ✅ 3개 | 동일 |
| **Internet Gateway** | ✅ | ✅ | 동일 |
| **Route Tables** | ✅ | ✅ | 동일 |
| **Security Groups** | ✅ Master + Worker | ✅ Master + Worker | 동일 |
| **VXLAN (UDP 4789)** | ✅ | ✅ | 동일 |

### **IAM 리소스 (✅ 완료)**

| 리소스 | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **IAM Role (k8s-node-role)** | ✅ | ✅ | 동일 |
| **ECR Read Policy** | ✅ | ✅ | 동일 |
| **S3 Access Policy** | ✅ | ✅ | 동일 |
| **CloudWatch Policy** | ✅ | ✅ | 동일 |
| **EBS CSI Policy** | ❌ | ✅ | **추가됨** |
| **SSM Managed Instance** | ✅ | ✅ | 동일 |
| **ALB Controller Policy** | ✅ | ✅ | 동일 |

### **Route53 + ACM (✅ 완료)**

| 리소스 | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **Route53 Hosted Zone** | ✅ | ✅ | 동일 |
| **ACM Certificate** | ✅ | ✅ | 동일 |
| **ACM Validation** | ✅ | ✅ | 동일 |

### **S3 + CloudFront (✅ 완료)**

| 리소스 | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **S3 Bucket (Images)** | ✅ | ✅ | 동일 |
| **CloudFront Distribution** | ✅ | ✅ (조건부) | **개선됨** |
| **CloudFront OAI** | ✅ | ✅ (조건부) | **개선됨** |
| **ACM Certificate (us-east-1)** | ✅ | ✅ (조건부) | **개선됨** |

**개선 사항**: `enable_cloudfront` 변수로 CloudFront 활성화/비활성화 가능

---

## 2️⃣ **Ansible Roles 비교**

### **Common Roles (✅ 완료)**

| Role | 초기 | 현재 | 상태 |
|------|-----|------|------|
| **common** (OS 설정) | ✅ | ✅ | 동일 |
| **docker** | ✅ | ✅ | 동일 |
| **kubernetes** | ✅ | ✅ | **개선됨** |

**Kubernetes Role 개선**:
```yaml
# ansible/roles/kubernetes/tasks/main.yml
초기:
  - Kubernetes 패키지 설치

현재:
  - Kubernetes 패키지 설치
  + allow_downgrade: yes (버전 충돌 해결)
  + 기존 패키지 제거 로직 추가
```

### **Infrastructure Roles (✅ 완료)**

| Role | 초기 | 현재 | 상태 |
|------|-----|------|------|
| **postgresql** | ✅ | ✅ | 동일 |
| **redis** | ✅ | ✅ | 동일 |
| **rabbitmq** | ❌ | ✅ | **추가됨** |

### **Playbooks (✅ 완료)**

| Playbook | 초기 | 현재 | 상태 |
|----------|-----|------|------|
| **02-master-init.yml** | ✅ | ✅ | 동일 |
| **03-worker-join.yml** | ✅ | ✅ | 동일 |
| **03-1-set-provider-id.yml** | ✅ | ✅ | 동일 |
| **04-cni-install.yml** (Calico) | ✅ | ✅ | **개선됨** |
| **04-cni-install-vpc.yml** (AWS VPC CNI) | ✅ | ✅ | 동일 |
| **05-addons.yml** | ✅ | ✅ | 동일 |
| **05-1-ebs-csi-driver.yml** | ❌ | ✅ | **추가됨** |
| **label-nodes.yml** | ✅ | ✅ | **확장됨** |

**Calico CNI 개선**:
```yaml
# ansible/playbooks/04-cni-install.yml
초기:
  - EXPECTED_TOTAL_NODES=8

현재:
  - EXPECTED_TOTAL_NODES=14 (수정됨)
  - VXLAN 전용 모드
  - BGP 완전 비활성화
```

**Label Nodes 확장**:
```yaml
초기 (8-Node):
  - Master: 1
  - API Nodes: 5 (auth, my, scan, character, location)
  - PostgreSQL: 1
  - Redis: 1

현재 (14-Node):
  - Master: 1
  - API Nodes: 7 (+ info, chat)
  - Worker Nodes: 2 (storage, ai)
  - PostgreSQL: 1
  - Redis: 1
  - RabbitMQ: 1
  - Monitoring: 1
```

---

## 3️⃣ **Kubernetes Addons 비교**

### **Core Addons (✅ 완료)**

| Addon | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **Calico CNI** | ✅ | ✅ | 동일 |
| **CoreDNS** | ✅ | ✅ | 동일 |
| **kube-proxy** | ✅ | ✅ | 동일 |
| **Metrics Server** | ✅ | ✅ | 동일 |

### **Storage Addons (⚠️ 확인 필요)**

| Addon | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **EBS CSI Driver** | ❓ | ✅ | **추가됨** |
| **StorageClass (gp3)** | ❓ | ✅ | **추가됨** |

**확인 필요**: 초기 클러스터에서 EBS CSI Driver가 설치되어 있었는지 확인

### **Networking Addons (⚠️ 확인 필요)**

| Addon | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **AWS ALB Controller** | ✅ | ✅ | 동일 |
| **Cert-Manager** | ✅ | ✅ | 동일 |
| **Ingress-NGINX** | ❌ | ❌ | 미사용 (ALB 사용) |

### **Monitoring Addons (⚠️ 확인 필요)**

| Addon | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **Prometheus** | ✅ (Master 통합?) | ✅ (전용 노드) | **분리됨** |
| **Grafana** | ✅ (Master 통합?) | ✅ (전용 노드) | **분리됨** |
| **Node Exporter** | ✅ | ✅ | 동일 |
| **Prometheus Operator** | ❌ | ❌ | 미사용 |
| **ServiceMonitor CRD** | ❌ | ❌ | 미사용 |

### **GitOps Addons (✅ 완료)**

| Addon | 초기 | 현재 | 상태 |
|-------|-----|------|------|
| **ArgoCD** | ✅ | ✅ | **확장됨** |
| **ArgoCD Hooks** | ❌ | ✅ | **추가됨** |
| **ArgoCD ApplicationSet** | ❌ | ✅ | **추가됨** |
| **Atlantis** | ❌ | ✅ | **추가됨** |

---

## 4️⃣ **빠진 리소스 요약**

### **✅ 이미 추가된 리소스**

1. **EBS CSI Driver IAM 권한** ✅
   - `terraform/iam.tf`에 추가 완료
   - `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:DeleteVolume` 등

2. **EBS CSI Driver 설치** ✅
   - `ansible/playbooks/05-1-ebs-csi-driver.yml`
   - StorageClass `gp3` 생성

3. **RabbitMQ Role** ✅
   - `ansible/roles/rabbitmq/tasks/main.yml`

4. **Monitoring 전용 노드** ✅
   - `terraform/main.tf`: `module.monitoring`

5. **Worker Nodes** ✅
   - `terraform/main.tf`: `module.worker_storage`, `module.worker_ai`

6. **Phase 3 API Nodes** ✅
   - `terraform/main.tf`: `module.api_info`, `module.api_chat`

### **⚠️ 확인 필요한 리소스**

#### **1. Monitoring Stack 배포 스크립트**

```yaml
상태: ⚠️ 부분 완료
파일:
  - k8s/monitoring/prometheus-deployment.yaml (✅ 수정 완료)
  - k8s/monitoring/grafana-deployment.yaml (✅ 수정 완료)
  - k8s/monitoring/node-exporter.yaml (✅ 수정 완료)

확인 필요:
  - PVC → emptyDir 변경 완료
  - namespace: monitoring 수정 완료
  - nodeSelector/tolerations 수정 완료
  
  BUT: 아직 배포되지 않음 (IAM 권한 부족으로 중단됨)
```

#### **2. EBS CSI Driver 자동 설치**

```yaml
상태: ⚠️ Playbook 존재, 실행 여부 불확실
파일: ansible/playbooks/05-1-ebs-csi-driver.yml

확인 필요:
  - site.yml에 포함되어 있는가?
  - 자동 실행되는가?
  - 수동 설치가 필요한가?
```

#### **3. Infrastructure Roles 자동 실행**

```yaml
상태: ⚠️ Role 존재, 자동 실행 여부 불확실
Roles:
  - ansible/roles/postgresql/tasks/main.yml ✅
  - ansible/roles/redis/tasks/main.yml ✅
  - ansible/roles/rabbitmq/tasks/main.yml ✅

확인 필요:
  - site.yml에서 자동 실행되는가?
  - 수동으로 playbook 실행이 필요한가?
```

#### **4. ALB Controller 배포**

```yaml
상태: ⚠️ IAM Policy 존재, 설치 여부 불확실
파일:
  - terraform/alb-controller-iam.tf ✅
  - ansible/playbooks/07-alb-controller.yml ✅

확인 필요:
  - site.yml에 포함되어 있는가?
  - 자동 설치되는가?
```

### **❌ 완전히 빠진 리소스**

#### **1. Prometheus Operator (선택 사항)**

```yaml
상태: ❌ 없음
이유: ServiceMonitor CRD 미사용
대안: Static Config 사용

필요 여부:
  - 현재: Static Config로 충분
  - 향후: ServiceMonitor 사용 시 필요
```

#### **2. Cert-Manager Issuer**

```yaml
상태: ⚠️ Playbook 존재, 실행 여부 불확실
파일: ansible/playbooks/06-cert-manager-issuer.yml

확인 필요:
  - Cert-Manager 설치 완료?
  - Let's Encrypt Issuer 생성 완료?
```

#### **3. Ingress Resources**

```yaml
상태: ⚠️ 파일 존재, 배포 여부 불확실
파일:
  - k8s/ingress/14-nodes-ingress.yaml ✅
  - ansible/playbooks/07-ingress-resources.yml ✅

확인 필요:
  - ALB Controller 설치 완료?
  - Ingress 리소스 배포 완료?
```

#### **4. API Deployments**

```yaml
상태: ❌ K8s 매니페스트 없음
필요:
  - auth-api Deployment + Service
  - my-api Deployment + Service
  - scan-api Deployment + Service
  - character-api Deployment + Service
  - location-api Deployment + Service
  - info-api Deployment + Service
  - chat-api Deployment + Service

누락 원인:
  - API 코드가 아직 개발 중?
  - 매니페스트 생성 예정?
```

#### **5. Worker Deployments**

```yaml
상태: ❌ K8s 매니페스트 부분 완료
파일:
  - k8s/workers/worker-wal-deployments.yaml (WAL Worker만)

누락:
  - Storage Worker (Celery) Deployment
  - AI Worker (Celery) Deployment
```

---

## 5️⃣ **추가 필요한 작업**

### **우선순위 1: 즉시 필요 (재배포 시 자동 실행)**

```yaml
1. ✅ EBS CSI Driver IAM 권한
   - Status: 완료 (terraform/iam.tf)

2. ⚠️ site.yml 업데이트 확인
   - EBS CSI Driver 설치 포함 여부
   - Infrastructure Roles 실행 여부
   - ALB Controller 설치 여부
   
3. ⚠️ Monitoring Stack 배포 확인
   - PVC 바인딩 테스트
   - Pod 스케줄링 확인
```

### **우선순위 2: 클러스터 구성 후**

```yaml
1. ❌ API Deployments 생성
   - 7개 도메인별 Deployment + Service
   - NodeSelector 설정 (domain 라벨 기반)
   - Resource Requests/Limits

2. ❌ Worker Deployments 생성
   - Storage Worker (Celery)
   - AI Worker (Celery)
   - WAL Worker (기존 파일 수정)

3. ⚠️ Ingress 배포
   - ALB Controller 확인
   - 14-nodes-ingress.yaml 배포
   - DNS 설정 (Route53)
```

### **우선순위 3: 운영 고도화**

```yaml
1. ❌ Prometheus Operator 설치 (선택)
   - ServiceMonitor CRD
   - PodMonitor CRD
   - PrometheusRule CRD

2. ⚠️ Cert-Manager + Let's Encrypt
   - Issuer 생성
   - Certificate 자동 갱신

3. ❌ Horizontal Pod Autoscaler (HPA)
   - API Pods 자동 스케일링
   - Metrics Server 필수

4. ❌ Backup & Recovery
   - PostgreSQL 백업 (pg_dump)
   - etcd 백업 (etcdctl)
   - PVC 스냅샷 (EBS Snapshot)
```

---

## 📊 **site.yml 확인**

현재 `ansible/site.yml`을 확인해야 합니다:

```yaml
확인 필요:
  1. EBS CSI Driver 설치 포함?
     - include_tasks: playbooks/05-1-ebs-csi-driver.yml
  
  2. Infrastructure Roles 실행?
     - roles: postgresql
     - roles: redis
     - roles: rabbitmq
  
  3. ALB Controller 설치?
     - include_tasks: playbooks/07-alb-controller.yml
  
  4. Monitoring 배포?
     - include_tasks: playbooks/08-monitoring.yml
  
  5. Ingress 배포?
     - include_tasks: playbooks/07-ingress-resources.yml
```

---

## ✅ **검증 체크리스트**

### **재배포 전 확인**

- [x] Terraform IAM 권한 (EBS CSI) 추가
- [x] Monitoring 매니페스트 수정 (namespace, nodeSelector)
- [ ] site.yml에 모든 필수 playbook 포함 확인
- [ ] group_vars/all.yml 변수 확인

### **재배포 후 확인**

- [ ] EBS CSI Driver Pod 정상 작동
- [ ] StorageClass `gp3` 생성 확인
- [ ] PVC 바인딩 성공 (Prometheus, Grafana)
- [ ] PostgreSQL StatefulSet 정상 작동
- [ ] Redis StatefulSet 정상 작동
- [ ] RabbitMQ StatefulSet 정상 작동
- [ ] Prometheus/Grafana Pod Running
- [ ] Node Exporter DaemonSet Running (14/14)
- [ ] ALB Controller Pod Running
- [ ] Ingress 생성 및 ALB 프로비저닝

---

## 🎯 **다음 단계**

1. **site.yml 확인**
   ```bash
   cat ansible/site.yml
   ```

2. **인프라 재배포**
   ```bash
   cd terraform
   terraform apply -auto-approve
   ```

3. **클러스터 구성**
   ```bash
   cd ../scripts/cluster
   ./deploy.sh
   ```

4. **리소스 확인**
   ```bash
   ./scripts/utilities/ssh-master.sh
   kubectl get nodes -o wide
   kubectl get pods -A
   kubectl get pvc -A
   kubectl get storageclass
   ```

5. **누락 리소스 배포**
   - API Deployments (수동 생성 필요)
   - Worker Deployments (수동 생성 필요)

---

**작성**: AI Assistant  
**검증 대상**: 초기 8-Node vs 현재 14-Node  
**다음 작업**: site.yml 확인 및 인프라 재배포

