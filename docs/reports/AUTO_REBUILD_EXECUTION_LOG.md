# auto-rebuild.sh 실행 기록 재현

## 실행 순서

`auto-rebuild.sh` 실행 시 다음 순서로 진행됩니다:

```
auto-rebuild.sh
  ├── 1. cleanup.sh (destroy-with-cleanup.sh)
  │   ├── Kubernetes 리소스 정리
  │   ├── AWS 리소스 정리
  │   └── Terraform destroy
  │
  └── 2. build-cluster.sh
      ├── Terraform init & apply
      ├── Ansible inventory 생성
      └── Ansible playbook 실행
```

---

## 1단계: cleanup.sh 실행

### 1.1 Kubernetes 리소스 정리

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧹 인프라 및 구성요소 삭제 (Cleanup)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 자동 모드로 실행 중...
   확인 프롬프트 없이 자동 삭제합니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Kubernetes 리소스 정리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 클러스터 정보:
  Kubernetes control plane is running at https://...

🗑️  Ingress 리소스 삭제 중...
🗑️  LoadBalancer 타입 Service 삭제 중...
🗑️  PVC 삭제 중...
🗑️  Helm Release 삭제 중...
  - Monitoring (Prometheus, Grafana) 삭제 중...
  - RabbitMQ Cluster CR 삭제 중...
  - ArgoCD 삭제 중...
  - AWS Load Balancer Controller 삭제 중...
  - 기타 Helm Release 삭제 중...

⏳ Kubernetes 리소스 정리 대기 (30초)...
```

### 1.2 AWS 리소스 정리

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2️⃣ AWS 리소스 확인 및 정리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 VPC ID: vpc-xxxxx

🔍 Kubernetes가 생성한 AWS 리소스 확인 중...

💾 EBS 볼륨 확인...
  ✅ EBS 볼륨 없음
  또는
  ⚠️  남은 EBS 볼륨 발견:
    - 삭제: vol-xxxxx (20GB)

🔒 Kubernetes 생성 보안 그룹 확인...
  ✅ Kubernetes 보안 그룹 없음
  또는
  ⚠️  Kubernetes 생성 보안 그룹 발견:
    - 삭제 시도: sg-xxxxx (k8s-xxxxx)
      ✅ 삭제 성공

⚖️  Load Balancer 확인...
  ✅ Load Balancer 없음
  또는
  ⚠️  남은 Load Balancer 발견 (Kubernetes Ingress):
    - 삭제: arn:aws:elasticloadbalancing:...

🌐 ENI 확인...
  ✅ 남은 ENI 없음

⏳ AWS 리소스 정리 완료 대기 (60초)...
   (AWS API 비동기 처리 완료 대기)
```

### 1.3 Terraform 인프라 삭제

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3️⃣ Terraform 인프라 삭제
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 현재 Terraform 리소스 개수: XX

🗑️  Terraform destroy 실행...

terraform destroy -auto-approve

Destroy complete! Resources: XX destroyed.

✅ Terraform 인프라 삭제 완료!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 완전 삭제 완료!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 2단계: build-cluster.sh 실행

### 2.1 Terraform 초기화 및 Apply

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 Kubernetes 클러스터 구축
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 자동 모드로 실행 중...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ Terraform Apply - 새 인프라 생성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 Terraform 초기화...
terraform init -migrate-state -upgrade

Initializing the backend...
Initializing provider plugins...
Terraform has been successfully initialized!

🚀 Terraform apply 실행...
terraform apply -auto-approve

Plan: XX to add, 0 to change, 0 to destroy.

Apply complete! Resources: XX added, 0 changed, 0 destroyed.

✅ 새 인프라 생성 완료
```

### 2.2 Ansible Inventory 생성

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2️⃣ Ansible Inventory 생성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Terraform output에서 인벤토리 생성...
✅ Ansible inventory 생성 완료: ansible/inventory/hosts.ini
```

### 2.3 SSH 연결 테스트

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3️⃣ SSH 연결 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Ansible ping 테스트...
[WARNING]: Found duplicate mapping key 'domain_name'.

k8s-worker-2 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
k8s-worker-1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
k8s-storage | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
k8s-master | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

### 2.4 Ansible Playbook 실행

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
4️⃣ Ansible Playbook 실행 (Kubernetes 설치)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Terraform output 추출 중...
🔧 Terraform state 새로고침 중...
  VPC ID: vpc-xxxxx
  ACM ARN: arn:aws:acm:ap-northeast-2:xxxxx:certificate/xxxxx

🤖 자동으로 Ansible playbook 실행...

PLAY [Prerequisites - OS 설정] ******************************************
TASK [common : Swap 비활성화] *******************************************
TASK [common : 커널 파라미터 설정] **************************************

PLAY [Docker 설치] ******************************************************
TASK [docker : Docker 설치] **********************************************

PLAY [Kubernetes 패키지 설치] ******************************************
TASK [kubernetes : Kubernetes 패키지 설치] *****************************

PLAY [Master 초기화] ****************************************************
TASK [kubeadm init] *****************************************************

PLAY [Workers 조인] ******************************************************
TASK [kubeadm join] *****************************************************

PLAY [CNI 플러그인 설치 및 클러스터 검증] ******************************
TASK [Calico CNI 설치] **************************************************

PLAY [노드 레이블 지정] **************************************************
TASK [Label nodes] ******************************************************

PLAY [Add-ons 설치] ******************************************************
TASK [Cert-manager 설치] ***********************************************
TASK [EBS CSI Driver 설치] *********************************************

PLAY [AWS Load Balancer Controller 설치] *******************************
TASK [ALB Controller 설치] *********************************************

PLAY [ArgoCD 설치] ******************************************************
TASK [argocd : ArgoCD Helm 설치] ***************************************

PLAY [Monitoring 설치] **************************************************
TASK [Prometheus Stack 설치] *******************************************

PLAY [RabbitMQ 설치] ****************************************************
TASK [rabbitmq : RabbitMQ Operator 설치] ******************************
TASK [rabbitmq : RabbitmqCluster CR 생성] *****************************

PLAY [Redis 설치] *******************************************************
TASK [redis : Redis Deployment 생성] ***********************************

PLAY [Ingress 리소스 생성] **********************************************
TASK [Ingress 리소스 생성] *********************************************

PLAY [etcd 백업 설정] ***************************************************
TASK [etcd 백업 설정] ***************************************************

PLAY [클러스터 정보 출력] **********************************************
TASK [Display nodes] ****************************************************
TASK [Display ArgoCD info] *********************************************

PLAY RECAP **************************************************************
k8s-master                 : ok=154  changed=68   unreachable=0    failed=0    skipped=8    rescued=0    ignored=1   
k8s-storage                : ok=40   changed=21   unreachable=0    failed=0    skipped=2    rescued=0    ignored=0   
k8s-worker-1               : ok=40   changed=21   unreachable=0    failed=0    skipped=2    rescued=0    ignored=0   
k8s-worker-2               : ok=40   changed=21   unreachable=0    failed=0    skipped=2    rescued=0    ignored=0   

✅ 클러스터 구축 완료!
```

### 2.5 최종 완료 메시지

```bash
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 자동 재구축 완료!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 다음 단계:
  1. 클러스터 접속:
     ./scripts/connect-ssh.sh master

  2. 노드 확인:
     kubectl get nodes -o wide

  3. Pod 확인:
     kubectl get pods -A

  4. 도메인 확인:
     https://growbin.app
     https://api.growbin.app
```

---

## 주요 단계 요약

### cleanup.sh (destroy-with-cleanup.sh)

1. **Kubernetes 리소스 정리** (약 30초 대기)
   - Ingress 삭제
   - LoadBalancer Service 삭제
   - PVC 삭제
   - Helm Release 삭제 (Prometheus, ArgoCD, ALB Controller)
   - RabbitMQ Cluster CR 삭제

2. **AWS 리소스 정리** (약 60초 대기)
   - EBS 볼륨 삭제
   - 보안 그룹 삭제 (k8s-* 패턴)
   - Load Balancer 삭제
   - ENI 삭제

3. **Terraform 인프라 삭제**
   - `terraform destroy -auto-approve`
   - 모든 AWS 리소스 삭제 (EC2, VPC, S3, EIP 등)

### build-cluster.sh

1. **Terraform Apply** (약 5-10분)
   - Terraform init
   - Terraform apply (EC2, VPC, S3, IAM 등 생성)

2. **Ansible Inventory 생성** (약 1분)
   - Terraform output에서 인벤토리 자동 생성

3. **Ansible Playbook 실행** (약 15-20분)
   - OS 설정
   - Docker 설치
   - Kubernetes 설치
   - Master 초기화
   - Worker 조인
   - CNI 설치 (Calico)
   - Add-ons 설치 (Cert-manager, EBS CSI Driver)
   - ALB Controller 설치
   - 애플리케이션 설치 (ArgoCD, Prometheus, RabbitMQ, Redis)
   - Ingress 리소스 생성

---

## 총 소요 시간

- **cleanup.sh**: 약 3-5분
- **build-cluster.sh**: 약 20-30분
- **총 시간**: 약 25-35분

---

## 주의사항

1. **AUTO_MODE=true**로 실행되면 확인 프롬프트 없이 자동 진행
2. cleanup.sh 실패해도 build-cluster.sh는 계속 진행됨 (`set +e` 처리)
3. 각 단계에서 대기 시간이 필요함 (AWS API 비동기 처리)
4. Terraform destroy는 VPC 삭제까지 시간이 오래 걸릴 수 있음

---

## 로그 저장 방법 (향후 개선)

실제 실행 로그를 저장하려면 다음 명령어 사용:

```bash
./scripts/auto-rebuild.sh 2>&1 | tee rebuild-$(date +%Y%m%d-%H%M%S).log
```

또는 스크립트에 로깅 기능 추가:

```bash
LOG_FILE="rebuild-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1
```

