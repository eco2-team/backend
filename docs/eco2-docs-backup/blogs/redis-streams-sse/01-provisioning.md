# 이코에코(Eco²) Redis Streams for SSE #1: 3-Node Redis Cluster 리소스 프로비저닝

> **작성일**: 2025-12-26  
> **시리즈**: Redis Streams for SSE  
> **이전**: [#0 아키텍처 및 마이그레이션안](./00-architecture-migration.md)

---

## 개요

Kubernetes 클러스터에 Redis 3노드를 추가하는 인프라 프로비저닝 과정을 다룹니다.

### 목표

| 항목 | Before | After |
|------|--------|-------|
| 노드 수 | 1 (k8s-redis) | 3 (auth, streams, cache) |
| 인스턴스 | t3.medium ×1 | t3.medium ×1 + t3.small ×2 |
| vCPU | 2 | 6 |
| 메모리 | 4GB | 8GB |

---

## Phase 1: Terraform 변경

### 기존 모듈

```hcl
# terraform/main.tf (Before)
module "redis" {
  source        = "./modules/ec2"
  name          = "k8s-redis"
  instance_type = "t3.medium"
  # ...
}
```

### 3개 모듈로 분리

```hcl
# terraform/main.tf (After)
module "redis_auth" {
  source        = "./modules/ec2"
  name          = "k8s-redis-auth"
  instance_type = "t3.medium"  # JWT Blacklist 중요도 높음
  node_labels   = { "redis-cluster" = "auth" }
  # ...
}

module "redis_streams" {
  source        = "./modules/ec2"
  name          = "k8s-redis-streams"
  instance_type = "t3.small"
  node_labels   = { "redis-cluster" = "streams" }
  # ...
}

module "redis_cache" {
  source        = "./modules/ec2"
  name          = "k8s-redis-cache"
  instance_type = "t3.small"
  node_labels   = { "redis-cluster" = "cache" }
  # ...
}
```

### Ansible Inventory 템플릿

```ini
# terraform/templates/hosts.tpl
[redis]
k8s-redis-auth ansible_host=${redis_auth_public_ip} private_ip=${redis_auth_private_ip} redis_cluster=auth
k8s-redis-streams ansible_host=${redis_streams_public_ip} private_ip=${redis_streams_private_ip} redis_cluster=streams
k8s-redis-cache ansible_host=${redis_cache_public_ip} private_ip=${redis_cache_private_ip} redis_cluster=cache
```

---

## Phase 2: vCPU 한계 이슈

### 문제 발생

```bash
terraform apply redis-only.plan

Error: creating EC2 Instance: operation error EC2: RunInstances, 
api error VcpuLimitExceeded: You have requested more vCPU capacity 
than your current vCPU limit of 43 allows
```

### vCPU 현황 분석

```bash
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].InstanceType' \
  --output text | tr '\t' '\n' | sort | uniq -c
```

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 7 | 2 | 14 |
| t3.small | 9 | 2 | 18 |
| **합계** | **20** | - | **42 vCPU** |

**계산**: 42 + 6(새 Redis) = 48 > 43 (한계 초과)

### 고아 인스턴스 발견

이전 Terraform apply 실패로 생성된 중복 인스턴스:

```bash
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-redis-*" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0]]' \
  --output table
```

| Instance ID | Name | State | Terraform State |
|-------------|------|-------|-----------------|
| i-0e9a1d55b934e6990 | k8s-redis-cache | running | 없음 (고아) |
| i-0d2620f00548d6e87 | k8s-redis-streams | running | 없음 (고아) |

### 해결: 고아 인스턴스 정리

```bash
# 1. 고아 인스턴스 종료
aws ec2 terminate-instances --instance-ids \
  i-0e9a1d55b934e6990 \
  i-0d2620f00548d6e87

# 2. 종료 완료 대기
aws ec2 wait instance-terminated --instance-ids \
  i-0e9a1d55b934e6990 \
  i-0d2620f00548d6e87

# 3. Terraform State 정리 (필요시)
terraform state rm module.redis_cache.aws_instance.this
terraform state rm module.redis_streams.aws_instance.this
```

### 정리 후 vCPU

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 6 | 2 | 12 |
| t3.small | 7 | 2 | 14 |
| **합계** | **17** | - | **36 vCPU** |

**여유**: 43 - 36 = 7 vCPU > 6 vCPU (필요) ✅

---

## Phase 3: Terraform Apply

### Target 옵션으로 범위 제한

전체 plan 시 AMI 버전 변경으로 모든 노드가 replace 대상이 됨.
`-target` 옵션으로 Redis 모듈만 적용:

```bash
# Plan
terraform plan \
  -var="dockerhub_password=xxx" \
  -target=module.redis_auth \
  -target=module.redis_streams \
  -target=module.redis_cache \
  -out=redis-fresh.plan

# Apply
terraform apply redis-fresh.plan
```

### 결과

```
module.redis_auth.aws_instance.this: Creating...
module.redis_streams.aws_instance.this: Creating...
module.redis_cache.aws_instance.this: Creating...

module.redis_auth.aws_instance.this: Creation complete after 35s [id=i-xxx]
module.redis_streams.aws_instance.this: Creation complete after 36s [id=i-xxx]
module.redis_cache.aws_instance.this: Creation complete after 37s [id=i-xxx]

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

### Inventory 생성

```bash
# Terraform Output → Ansible Inventory
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

# 확인
grep -A5 "[redis]" ../ansible/inventory/hosts.ini
```

```ini
[redis]
k8s-redis-auth ansible_host=3.34.128.200 private_ip=10.0.2.43 redis_cluster=auth
k8s-redis-streams ansible_host=3.38.200.174 private_ip=10.0.2.215 redis_cluster=streams
k8s-redis-cache ansible_host=15.165.200.60 private_ip=10.0.2.202 redis_cluster=cache
```

---

## Phase 4: Ansible 설정

### SSH 연결 확인

```bash
cd ../ansible
ansible -i inventory/hosts.ini redis -m ping
```

```
k8s-redis-auth | SUCCESS => { "ping": "pong" }
k8s-redis-streams | SUCCESS => { "ping": "pong" }
k8s-redis-cache | SUCCESS => { "ping": "pong" }
```

### 새 노드 기본 설정

새로 생성된 EC2 인스턴스에는 Docker, containerd, kubeadm이 설치되어 있지 않음.
전용 playbook으로 초기 설정:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/setup-new-nodes.yml -l redis
```

```yaml
# ansible/playbooks/setup-new-nodes.yml
- name: Prerequisites - OS 설정
  hosts: all
  roles:
    - common  # 커널 모듈, sysctl, swap 비활성화

- name: Docker/Containerd 설치
  hosts: all
  roles:
    - docker  # containerd CRI 설정

- name: Kubernetes 패키지 설치
  hosts: all
  roles:
    - kubernetes  # kubeadm, kubelet, kubectl
```

### 결과

```
TASK [설치 상태 출력] ****
ok: [k8s-redis-auth] => 
  msg:
  - 'containerd: active'
  - 'kubeadm: v1.28.4'
  - 'kubelet: Kubernetes v1.28.4'
```

---

## Phase 5: 클러스터 조인

### Join Token 생성

```bash
ssh -i ~/.ssh/sesacthon.pem ubuntu@<master-ip> \
  "kubeadm token create --print-join-command" > /tmp/kubeadm_join_command.sh
```

### Worker Join

```bash
ansible-playbook -i inventory/hosts.ini playbooks/03-worker-join.yml \
  -l redis \
  -e kubectl_user=ubuntu
```

### 노드 라벨 적용

```bash
ansible-playbook -i inventory/hosts.ini playbooks/fix-node-labels.yml \
  -l redis \
  -e kubectl_user=ubuntu
```

### 최종 확인

```bash
kubectl get nodes -l 'redis-cluster' -o wide
```

```
NAME                STATUS   ROLES    AGE   VERSION   INTERNAL-IP
k8s-redis-auth      Ready    <none>   45m   v1.28.4   10.0.2.43
k8s-redis-streams   Ready    <none>   45m   v1.28.4   10.0.2.215
k8s-redis-cache     Ready    <none>   45m   v1.28.4   10.0.2.202
```

---

## 교훈 및 Best Practices

### 1. AMI Lifecycle 관리

```hcl
resource "aws_instance" "this" {
  lifecycle {
    ignore_changes = [ami]  # AMI 변경 무시
  }
}
```

### 2. vCPU 한계 사전 확인

```bash
# 프로비저닝 전 확인 스크립트
CURRENT=$(aws ec2 describe-instances ... | wc -l)
LIMIT=$(aws service-quotas get-service-quota ... | jq '.Quota.Value')
NEEDED=6

if [ $((CURRENT + NEEDED)) -gt $LIMIT ]; then
  echo "⚠️ vCPU 한계 초과 예상"
fi
```

### 3. Target 옵션 활용

```bash
# 영향 범위 제한
terraform plan -target=module.specific_module
```

### 4. State 불일치 복구

```bash
# 고아 리소스 정리
terraform state rm <resource>

# 또는 import
terraform import module.xxx.aws_instance.this <instance-id>
```

---

## 참고 자료

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest)
- [kubeadm join](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/)
- [Ansible Playbook](https://docs.ansible.com/ansible/latest/user_guide/playbooks.html)

---

## 다음 단계

→ [#2: 선언적 배포 (GitOps)](./02-gitops-deployment.md)

