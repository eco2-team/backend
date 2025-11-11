# 🚀 14-Node 클러스터 배포/삭제 스크립트

> **Terraform + Ansible 기반 완전 자동화 스크립트 v2.0**

---

## 📋 스크립트 개요

### 🎯 주요 변경사항 (v2.0)

```yaml
이전 버전:
  ❌ 8-Node/13-Node 하드코딩
  ❌ 복잡한 로직 (1,200+ 라인)
  ❌ Inventory 재생성 누락
  ❌ 오류 처리 미흡

새 버전 (v2.0):
  ✅ 14-Node 자동 감지
  ✅ 간결한 로직 (400 라인)
  ✅ Inventory 자동 재생성
  ✅ 강력한 오류 처리
  ✅ 상세한 로그
  ✅ 단계별 진행 표시
```

---

## 🔧 스크립트 목록

### 1️⃣ `deploy.sh` - 클러스터 배포

**용도**: 14-Node 클러스터 완전 자동 배포

**단계**:
1. 사전 확인 (AWS 인증, vCPU 할당량, SSH 키)
2. Terraform 인프라 프로비저닝 (15-20분)
3. Ansible Inventory 생성
4. Ansible Playbook 실행 (15-20분)
5. Kubernetes 클러스터 확인
6. 배포 완료 정보 출력

**소요 시간**: 40-60분

### 2️⃣ `destroy.sh` - 클러스터 삭제

**용도**: 14-Node 클러스터 완전 삭제

**단계**:
1. Terraform 상태 확인
2. Kubernetes 리소스 정리 (선택적)
3. AWS 의존성 리소스 사전 정리
   - Load Balancer
   - Target Groups
   - CloudFront Distribution
   - S3 Bucket
4. Terraform Destroy (10-15분)
5. 잔여 리소스 확인

**소요 시간**: 15-25분

---

## 🚀 사용법

### 배포 (deploy.sh)

#### 기본 사용

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 배포 실행
./scripts/cluster/deploy.sh
```

#### 실행 전 확인사항

```bash
# 1. AWS 인증 확인
aws sts get-caller-identity

# 2. vCPU 할당량 확인 (32개 필요)
aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region ap-northeast-2

# 3. SSH 키 확인
ls -la ~/.ssh/sesacthon.pem
```

#### 배포 과정

```bash
🚀 14-Node 클러스터 완전 자동 배포
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ 사전 확인
   ✅ AWS 인증
   ✅ vCPU 할당량
   ✅ SSH 키
   ✅ 필수 도구 (terraform, ansible, kubectl, jq)

2️⃣ Terraform 인프라 프로비저닝 (15-20분)
   - terraform init
   - terraform plan
   - terraform apply
   → 14개 EC2 인스턴스 생성

3️⃣ Ansible Inventory 생성
   - terraform output → hosts.ini
   - SSH 연결 테스트 (최대 5회 재시도)

4️⃣ Ansible Playbook 실행 (15-20분)
   - site.yml (Bootstrap)
   - label-nodes.yml (노드 라벨링)

5️⃣ Kubernetes 클러스터 확인
   - kubeconfig 복사
   - kubectl get nodes
   - kubectl get pods -A

6️⃣ 배포 완료
   - 클러스터 정보 출력
   - 다음 단계 안내
```

#### 배포 완료 후

```bash
# kubeconfig 설정
export KUBECONFIG=/Users/mango/workspace/SeSACTHON/backend/kubeconfig.tmp

# 노드 확인
kubectl get nodes -o wide

# ArgoCD 배포
kubectl apply -f argocd/applications/ecoeco-14nodes-appset.yaml

# 모니터링 접속
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

---

### 삭제 (destroy.sh)

#### 기본 사용

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 삭제 실행
./scripts/cluster/destroy.sh
```

#### 자동 모드 (확인 없이 삭제)

```bash
AUTO_MODE=true ./scripts/cluster/destroy.sh
```

#### 삭제 과정

```bash
🗑️  14-Node 클러스터 완전 삭제
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  경고: 모든 리소스가 삭제됩니다!

삭제될 리소스:
  - 14개 EC2 인스턴스
  - VPC 및 네트워크 리소스
  - CloudFront Distribution
  - S3 Bucket (이미지 포함)
  - ACM Certificate
  - IAM Roles & Policies

정말로 삭제하시겠습니까? (yes 입력): yes

1️⃣ Terraform 상태 확인
   - terraform state list
   - VPC ID, Region 확인

2️⃣ Kubernetes 리소스 정리 (선택적)
   - Ingress 삭제
   - PVC 삭제
   - LoadBalancer Service 삭제

3️⃣ AWS 의존성 리소스 사전 정리
   - Load Balancer 삭제
   - Target Groups 삭제
   - CloudFront Distribution Disable & Delete
   - S3 Bucket 정리

4️⃣ Terraform Destroy (10-15분)
   - terraform destroy -auto-approve
   → NAT Gateway 대기 (5분)

5️⃣ 잔여 리소스 확인
   - VPC 삭제 확인
   - EC2 인스턴스 확인
   - ACM Certificate 확인

6️⃣ 삭제 완료
```

---

## 📊 소요 시간

### 배포 (deploy.sh)

| 단계 | 예상 시간 | 설명 |
|------|----------|------|
| 사전 확인 | 1-2분 | AWS 인증, 도구 확인 |
| Terraform apply | 15-20분 | CloudFront 생성 (10-15분) |
| Inventory 생성 | 1-2분 | SSH 연결 테스트 포함 |
| Ansible Bootstrap | 12-15분 | Docker, K8s 설치 |
| Ansible Labeling | 2-3분 | 노드 라벨링 |
| 클러스터 확인 | 1-2분 | kubectl 명령 |
| **총합** | **40-60분** | CloudFront에 따라 변동 |

### 삭제 (destroy.sh)

| 단계 | 예상 시간 | 설명 |
|------|----------|------|
| 사전 확인 | 1분 | State 확인 |
| K8s 리소스 정리 | 1-2분 | 선택적 |
| AWS 의존성 정리 | 5-10분 | CloudFront, ALB, S3 |
| Terraform destroy | 10-15분 | NAT Gateway 대기 |
| 잔여 확인 | 1분 | 리소스 확인 |
| **총합** | **15-25분** | CloudFront에 따라 변동 |

---

## 📝 로그 파일

### 위치

```bash
logs/
├── deploy-20251109-101234.log    # 배포 로그
├── deploy-20251109-153456.log
├── destroy-20251109-180912.log   # 삭제 로그
└── ...
```

### 로그 확인

```bash
# 최신 배포 로그
tail -f logs/deploy-*.log | tail -1

# 최신 삭제 로그
tail -f logs/destroy-*.log | tail -1

# 특정 로그 확인
cat logs/deploy-20251109-101234.log
```

---

## 🔍 문제 해결

### 배포 (deploy.sh) 트러블슈팅

#### 1. SSH 연결 실패

```yaml
증상:
  SSH 연결 타임아웃 (5회 재시도 후 실패)

원인:
  - EC2 인스턴스 부팅 지연
  - Security Group 설정 오류
  - SSH 키 권한 문제

해결:
  1. EC2 인스턴스 상태 확인
     aws ec2 describe-instances --region ap-northeast-2 \
       --filters "Name=tag:Project,Values=sesacthon"
  
  2. Security Group 확인
     - Port 22 (SSH) 허용 확인
  
  3. SSH 키 권한 확인
     chmod 600 ~/.ssh/sesacthon.pem
  
  4. 수동 SSH 테스트
     ssh -i ~/.ssh/sesacthon.pem ubuntu@<MASTER_IP>
```

#### 2. Terraform apply 실패

```yaml
증상:
  Terraform apply 중 에러

원인:
  - vCPU 할당량 부족
  - IAM 권한 부족
  - Resource 중복

해결:
  1. vCPU 할당량 확인
     aws service-quotas get-service-quota \
       --service-code ec2 \
       --quota-code L-1216C47A \
       --region ap-northeast-2
  
  2. 기존 리소스 확인
     terraform state list
  
  3. 수동 정리 후 재시도
     ./scripts/cluster/destroy.sh
     ./scripts/cluster/deploy.sh
```

#### 3. Ansible playbook 실패

```yaml
증상:
  site.yml 또는 label-nodes.yml 실패

원인:
  - Inventory IP 불일치
  - SSH 키 경로 오류
  - Python 버전 불일치

해결:
  1. Inventory 재생성
     cd terraform
     terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
  
  2. Ansible ping 테스트
     cd ../ansible
     ansible all -m ping -i inventory/hosts.ini
  
  3. Playbook 재실행
     ansible-playbook playbooks/site.yml -i inventory/hosts.ini
```

### 삭제 (destroy.sh) 트러블슈팅

#### 1. VPC 삭제 실패

```yaml
증상:
  VPC 삭제 시 의존성 에러

원인:
  - NAT Gateway가 아직 삭제 중
  - ENI (Elastic Network Interface) 남아있음
  - Security Group 의존성

해결:
  1. NAT Gateway 확인
     aws ec2 describe-nat-gateways \
       --filter "Name=vpc-id,Values=<VPC_ID>" \
       --region ap-northeast-2
  
  2. ENI 확인 및 삭제
     aws ec2 describe-network-interfaces \
       --filters "Name=vpc-id,Values=<VPC_ID>" \
       --region ap-northeast-2
  
  3. 5-10분 대기 후 재시도
     ./scripts/cluster/destroy.sh
```

#### 2. CloudFront 삭제 지연

```yaml
증상:
  CloudFront Distribution 삭제 실패

원인:
  - Distribution이 아직 InProgress 상태
  - Deployed 상태 전환 대기 필요

해결:
  1. Status 확인
     aws cloudfront get-distribution \
       --id <DISTRIBUTION_ID> \
       --query 'Distribution.Status'
  
  2. 5-10분 대기 후 수동 삭제
     aws cloudfront delete-distribution \
       --id <DISTRIBUTION_ID> \
       --if-match <ETAG>
  
  참고: docs/troubleshooting/CLOUDFRONT_ACM_CERTIFICATE_STUCK.md
```

#### 3. ACM Certificate 삭제 실패

```yaml
증상:
  ACM Certificate가 삭제되지 않음

원인:
  - CloudFront가 아직 Certificate 사용 중

해결:
  1. CloudFront 삭제 확인
     aws cloudfront list-distributions
  
  2. CloudFront 완전 삭제 대기 (5-10분)
  
  3. ACM Certificate 자동 삭제 확인
     aws acm list-certificates --region us-east-1
```

---

## 🎯 주요 개선 사항 (v2.0)

### 1. 간결한 로직

```yaml
Before:
  - auto-rebuild.sh: 1,200+ 라인
  - force-destroy-all.sh: 1,280 라인
  → 복잡한 로직, 유지보수 어려움

After:
  - deploy.sh: 400 라인
  - destroy.sh: 450 라인
  → 간결하고 명확한 로직
```

### 2. Inventory 자동 재생성

```yaml
Before:
  ❌ Inventory 재생성 누락
  → SSH 연결 실패 (IP 불일치)

After:
  ✅ terraform output → hosts.ini 자동 생성
  ✅ SSH 연결 재시도 (최대 5회)
  → 안정적인 연결
```

### 3. 강력한 오류 처리

```yaml
Before:
  ⚠️  에러 무시 (|| true)
  → 실패 원인 파악 어려움

After:
  ✅ 각 단계별 에러 체크
  ✅ 상세한 로그 출력
  ✅ 재시도 로직
  → 명확한 에러 메시지
```

### 4. 단계별 진행 표시

```yaml
Before:
  - 진행 상황 불명확
  - 예상 시간 불명

After:
  ✅ 헤더로 단계 구분
  ✅ 예상 시간 표시
  ✅ 로그 파일 생성
  → 명확한 진행 상황
```

---

## 📚 관련 문서

- [AUTO_REBUILD_GUIDE.md](../../docs/deployment/AUTO_REBUILD_GUIDE.md) - 상세 배포 가이드
- [14-node-completion-summary.md](../../docs/deployment/14-node-completion-summary.md) - 14-Node 완료 요약
- [ANSIBLE_SSH_TIMEOUT.md](../../docs/troubleshooting/ANSIBLE_SSH_TIMEOUT.md) - SSH 타임아웃 해결
- [CLOUDFRONT_ACM_CERTIFICATE_STUCK.md](../../docs/troubleshooting/CLOUDFRONT_ACM_CERTIFICATE_STUCK.md) - CloudFront 삭제 지연

---

**Last Updated**: 2025-11-09  
**Version**: 2.0  
**Status**: ✅ Production Ready  
**기존 스크립트**: ❌ Deprecated (삭제됨)

