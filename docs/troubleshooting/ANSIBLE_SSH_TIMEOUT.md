# auto-rebuild.sh Ansible 타임아웃 문제 분석 (2025-11-09)

## 🔍 문제 상황

```yaml
증상:
  - Ansible SSH 연결 타임아웃 (301초)
  - 잘못된 IP로 연결 시도
  
에러 메시지:
  fatal: [k8s-master -> localhost]: FAILED!
  msg: Timeout when waiting for 13.124.53.173:22
  
실제 IP:
  k8s-master: 52.78.94.7 (Terraform output)
  
문제:
  Ansible inventory가 구버전 IP를 사용
```

---

## 🎯 근본 원인

### 1️⃣ Terraform과 Ansible Inventory 불일치

```yaml
시나리오:
  1. 이전 클러스터 삭제 (destroy)
  2. 새 클러스터 생성 (apply)
  3. 새 Public IP 할당 (52.78.94.7)
  4. Ansible inventory는 구버전 IP 참조 (13.124.53.173)
  
문제:
  - Terraform state는 최신
  - Ansible inventory는 구버전
  → SSH 연결 실패
```

### 2️⃣ auto-rebuild.sh의 문제점

```bash
# auto-rebuild.sh 현재 로직:
terraform apply -auto-approve
ansible-playbook site.yml  # ❌ Inventory 갱신 없이 바로 실행

# 문제:
1. terraform apply 후 output이 변경됨
2. Inventory는 이전 IP를 계속 참조
3. Ansible이 존재하지 않는 IP로 연결 시도
```

---

## ✅ 해결 방법

### 방법 1: Inventory 수동 재생성 (즉시 해결)

```bash
cd /Users/mango/workspace/SeSACTHON/backend/terraform

# Inventory 재생성
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

# 연결 확인
cd ../ansible
ansible all -m ping

# Playbook 실행
ansible-playbook playbooks/site.yml
```

**상태**: ✅ 완료 (방금 실행)

### 방법 2: auto-rebuild.sh 수정 (영구 해결)

`auto-rebuild.sh`에 Inventory 재생성 로직 추가:

```bash
# Terraform apply 후
echo "📦 Ansible Inventory 재생성 중..."
terraform output -raw ansible_inventory > "$ANSIBLE_DIR/inventory/hosts.ini"

if [ $? -ne 0 ]; then
    echo "❌ Inventory 재생성 실패"
    exit 1
fi

echo "✅ Inventory 재생성 완료"
echo ""

# 이후 Ansible playbook 실행
```

---

## 🔍 상세 분석

### Terraform Output (최신)

```bash
$ terraform output -raw ansible_inventory

[masters]
k8s-master ansible_host=52.78.94.7 private_ip=10.0.1.130 instance_type=t3.large

[api_nodes]
k8s-api-auth ansible_host=3.35.139.68 private_ip=10.0.1.97 domain=auth ...
k8s-api-my ansible_host=3.35.226.49 private_ip=10.0.2.108 domain=my ...
k8s-api-scan ansible_host=3.37.61.234 private_ip=10.0.3.164 domain=scan ...
k8s-api-character ansible_host=3.38.92.80 private_ip=10.0.1.50 domain=character ...
k8s-api-location ansible_host=16.184.18.161 private_ip=10.0.2.91 domain=location ...
k8s-api-info ansible_host=15.164.96.26 private_ip=10.0.3.100 domain=info ...
k8s-api-chat ansible_host=3.36.65.53 private_ip=10.0.1.248 domain=chat ...

[worker_nodes]
k8s-worker-storage ansible_host=43.202.53.99 private_ip=10.0.2.71 domain=storage ...
k8s-worker-ai ansible_host=3.39.248.5 private_ip=10.0.3.192 domain=ai ...

[infra_nodes]
k8s-postgresql ansible_host=3.34.46.171 private_ip=10.0.1.63 ...
k8s-redis ansible_host=3.36.68.244 private_ip=10.0.2.23 ...
k8s-rabbitmq ansible_host=3.34.120.239 private_ip=10.0.3.246 ...
k8s-monitoring ansible_host=13.125.21.48 private_ip=10.0.1.105 ...
```

✅ **14개 노드 모두 정상 생성**

### Ansible Ping 테스트 (재생성 후)

```bash
$ ansible all -m ping

k8s-master           | SUCCESS | ping: pong ✅
k8s-api-auth         | SUCCESS | ping: pong ✅
k8s-api-my           | SUCCESS | ping: pong ✅
k8s-api-character    | SUCCESS | ping: pong ✅
k8s-api-scan         | SUCCESS | ping: pong ✅
k8s-api-location     | SUCCESS | ping: pong ✅
k8s-api-chat         | SUCCESS | ping: pong ✅
k8s-api-info         | SUCCESS | ping: pong ✅
k8s-worker-storage   | SUCCESS | ping: pong ✅
k8s-worker-ai        | SUCCESS | ping: pong ✅
k8s-postgresql       | SUCCESS | ping: pong ✅
k8s-redis            | SUCCESS | ping: pong ✅
k8s-rabbitmq         | SUCCESS | ping: pong ✅
k8s-monitoring       | SUCCESS | ping: pong ✅
```

✅ **14개 노드 모두 SSH 연결 성공**

---

## 📋 auto-rebuild.sh 수정 필요 사항

### 현재 문제점

```yaml
1. Inventory 갱신 누락:
   - terraform apply 후 inventory 재생성 없음
   - 구버전 IP로 연결 시도

2. 노드 개수 하드코딩:
   - TARGET_COUNT=8 (14-node 미지원)
   - 인스턴스 상태 확인에서 8개만 확인

3. 14-Node 리소스 미지원:
   - Monitoring → Master 배포 (Phase 4 미반영)
   - Worker 노드 라벨링 누락
   - RabbitMQ, Monitoring 노드 설정 누락
```

### 필수 수정 사항

```yaml
1. Inventory 재생성 추가:
   terraform output -raw ansible_inventory > inventory/hosts.ini

2. 노드 개수 동적 확인:
   TARGET_COUNT=$(terraform state list | grep "aws_instance" | wc -l)

3. 14-Node 지원:
   - Phase 3 API 노드 (info, chat)
   - Phase 4 Worker 노드 (storage, ai)
   - Phase 4 Infrastructure (rabbitmq, monitoring)

4. Monitoring 배포 위치:
   - Master 노드 → Monitoring 노드
```

---

## 🚀 다음 단계

### 즉시 실행 가능 (Inventory 재생성 완료)

```bash
cd /Users/mango/workspace/SeSACTHON/backend/ansible

# 1. site.yml 실행 (Bootstrap)
ansible-playbook playbooks/site.yml

# 2. label-nodes.yml 실행 (Kubernetes 라벨링)
ansible-playbook playbooks/label-nodes.yml

# 3. Kubernetes 클러스터 상태 확인
ssh ubuntu@52.78.94.7 -i ~/.ssh/sesacthon.pem "kubectl get nodes -o wide"
```

### auto-rebuild.sh 수정 (영구 해결)

```yaml
작업:
  1. Inventory 재생성 로직 추가
  2. 노드 개수 동적 확인 (8→14)
  3. 14-Node 지원 추가
  4. Monitoring 배포 위치 변경

우선순위:
  - 즉시: Inventory 재생성 (✅ 완료)
  - 단기: Ansible playbook 실행 (다음 단계)
  - 중기: auto-rebuild.sh 수정 (별도 작업)
```

---

## 📊 검증 결과

### Terraform State

```yaml
리소스:
  ✅ 14 EC2 인스턴스
  ✅ VPC, Subnets, IGW, NAT Gateway
  ✅ Security Groups (14개)
  ✅ IAM Roles, Policies
  ✅ EIP (Master)
  ✅ CloudFront, ACM Certificate
  ✅ S3 Buckets

상태: 정상 (189KB state file)
```

### SSH 연결

```yaml
Master:
  ✅ 52.78.94.7:22 (정상)

API Nodes (7개):
  ✅ auth, my, scan, character, location, info, chat (모두 정상)

Worker Nodes (2개):
  ✅ storage, ai (모두 정상)

Infrastructure (4개):
  ✅ postgresql, redis, rabbitmq, monitoring (모두 정상)

총 14개 노드: 모두 SSH 연결 가능
```

---

## 💡 교훈

### 1. Terraform과 Ansible 동기화

```yaml
문제:
  Terraform state는 최신인데 Ansible inventory는 구버전

해결:
  terraform apply 직후 항상 inventory 재생성

자동화:
  auto-rebuild.sh에 로직 추가
```

### 2. IP 변경 시나리오

```yaml
발생 상황:
  - EC2 재생성 (destroy → apply)
  - EIP 미사용 노드 (API, Worker, Infra)
  - Public IP 자동 재할당

대응:
  - Terraform output을 Single Source of Truth로 사용
  - Ansible inventory는 항상 Terraform에서 생성
  - 수동 수정 금지
```

---

## 📝 체크리스트

### 즉시 해결 (완료)

- [x] ✅ Terraform state 확인 (14 인스턴스)
- [x] ✅ Inventory 재생성
- [x] ✅ SSH 연결 확인 (14 노드 모두 정상)
- [x] ✅ Ansible ping 테스트 (모두 SUCCESS)

### 다음 단계 (대기 중)

- [ ] 🔄 Ansible site.yml 실행
- [ ] 🔄 Ansible label-nodes.yml 실행
- [ ] 🔄 Kubernetes 클러스터 상태 확인
- [ ] 🔄 ArgoCD/Monitoring 배포

### 영구 해결 (별도 작업)

- [ ] 📝 auto-rebuild.sh 수정
- [ ] 📝 Inventory 재생성 로직 추가
- [ ] 📝 노드 개수 동적 확인
- [ ] 📝 14-Node 지원 추가

---

**최종 결론**:
- ✅ **문제 원인**: Terraform과 Ansible inventory 불일치 (IP 변경)
- ✅ **즉시 해결**: Inventory 재생성 완료
- ✅ **영구 해결**: auto-rebuild.sh 수정 필요 (별도 작업)
- ✅ **현재 상태**: 14개 노드 모두 SSH 연결 가능, Ansible 실행 준비 완료

---

**작성일**: 2025-11-09  
**상태**: ✅ Inventory 재생성 완료 (Ansible 실행 가능)  
**다음**: Ansible Playbook 실행

