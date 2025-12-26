# Redis 3-Node 클러스터 프로비저닝 실측 로그

> **작업 일시**: 2025-12-26  
> **환경**: Dev (ap-northeast-2)  
> **용도**: 포스팅 보강 자료

---

## Phase 1: 초기 상태 확인

```bash
mango@mangoui-MacBookAir terraform % aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[Tags[?Key==`Name`].Value|[0],InstanceType,InstanceId]' \
  --output table
-------------------------------------------------------------
|                     DescribeInstances                     |
+----------------------+------------+-----------------------+
|  k8s-postgresql      |  t3.large  |  i-03772ad89c40d35d8  |
|  k8s-worker-ai       |  t3.medium |  i-072b17ccb5cee5003  |
|  k8s-master          |  t3.xlarge |  i-01e5bb9e310a7b35d  |
|  k8s-api-character   |  t3.small  |  i-0bdb5eaf1bcafbc2a  |
|  k8s-api-chat        |  t3.medium |  i-0254f4fc73e1ff161  |
|  k8s-api-auth        |  t3.small  |  i-037a9993d73431825  |
|  k8s-api-scan        |  t3.medium |  i-02cd8a146c249f2d0  |
|  k8s-api-image       |  t3.small  |  i-045113d6b9b039e2f  |
|  k8s-worker-storage  |  t3.medium |  i-0f9fecaba0dca7af7  |
|  k8s-logging         |  t3.large  |  i-08296b6ad4623fe76  |
|  k8s-api-my          |  t3.small  |  i-0b39625bbe5d63102  |
|  k8s-monitoring      |  t3.large  |  i-0fe5b69593723eeb0  |
|  k8s-rabbitmq        |  t3.medium |  i-063fd0a3e1bf1cad5  |
|  k8s-api-location    |  t3.small  |  i-07cd94d249678b6ca  |
|  k8s-redis-cache     |  t3.small  |  i-0e9a1d55b934e6990  |
|  k8s-redis-streams   |  t3.small  |  i-0d2620f00548d6e87  |
|  k8s-ingress-gateway |  t3.medium |  i-00a2d030d0be1d2de  |
+----------------------+------------+-----------------------+
```

### vCPU 현황 (정리 전)

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 6 | 2 | 12 |
| t3.small | 7 | 2 | 14 |
| **합계** | **17** | - | **36 vCPU** |

- **한계**: 43 vCPU
- **여유**: 7 vCPU

---

## Phase 2: 고아 인스턴스 삭제

이전 Terraform apply 실패로 생성된 중복 인스턴스 정리:

```bash
mango@mangoui-MacBookAir terraform % aws ec2 terminate-instances --instance-ids \
  i-0e9a1d55b934e6990 \
  i-0d2620f00548d6e87

{
    "TerminatingInstances": [
        {
            "InstanceId": "i-0e9a1d55b934e6990",
            "CurrentState": {
                "Code": 32,
                "Name": "shutting-down"
            },
            "PreviousState": {
                "Code": 16,
                "Name": "running"
            }
        },
        {
            "InstanceId": "i-0d2620f00548d6e87",
            "CurrentState": {
                "Code": 32,
                "Name": "shutting-down"
            },
            "PreviousState": {
                "Code": 16,
                "Name": "running"
            }
        }
    ]
}
```

### 삭제 대기

```bash
mango@mangoui-MacBookAir terraform % aws ec2 wait instance-terminated --instance-ids \
  i-0e9a1d55b934e6990 \
  i-0d2620f00548d6e87
# (완료, 출력 없음)
```

---

## Phase 3: Terraform State 정리

```bash
mango@mangoui-MacBookAir terraform % terraform state rm module.redis_cache.aws_instance.this

Removed module.redis_cache.aws_instance.this
Successfully removed 1 resource instance(s).

mango@mangoui-MacBookAir terraform % terraform state rm module.redis_streams.aws_instance.this

Removed module.redis_streams.aws_instance.this
Successfully removed 1 resource instance(s).
```

---

## Phase 4: Terraform Plan (Redis 3노드)

```bash
mango@mangoui-MacBookAir terraform % terraform plan \
  -var="dockerhub_password=dckr_pat_xxx" \
  -target=module.redis_auth \
  -target=module.redis_streams \
  -target=module.redis_cache \
  -out=redis-fresh.plan

# ... (중간 생략) ...

Plan: 3 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + redis_auth_instance_id    = (known after apply)
  + redis_auth_private_ip     = (known after apply)
  + redis_auth_public_ip      = (known after apply)
  ~ redis_cache_instance_id   = "i-0e9a1d55b934e6990" -> (known after apply)
  ~ redis_cache_private_ip    = "10.0.2.40" -> (known after apply)
  ~ redis_cache_public_ip     = "3.38.161.53" -> (known after apply)
  ~ redis_streams_instance_id = "i-0d2620f00548d6e87" -> (known after apply)
  ~ redis_streams_private_ip  = "10.0.2.233" -> (known after apply)
  ~ redis_streams_public_ip   = "3.38.176.82" -> (known after apply)

Saved the plan to: redis-fresh.plan
```

---

## Phase 5: Terraform Apply

```bash
mango@mangoui-MacBookAir terraform % terraform apply redis-fresh.plan

module.redis_cache.aws_instance.this: Creating...
module.redis_streams.aws_instance.this: Creating...
module.redis_auth.aws_instance.this: Creating...
module.redis_cache.aws_instance.this: Still creating... [10s elapsed]
module.redis_auth.aws_instance.this: Still creating... [10s elapsed]
module.redis_streams.aws_instance.this: Still creating... [10s elapsed]
module.redis_streams.aws_instance.this: Creation complete after 13s [id=i-06963134608684348]
module.redis_auth.aws_instance.this: Creation complete after 13s [id=i-0763922bb112cf5d2]
module.redis_cache.aws_instance.this: Creation complete after 13s [id=i-02c15f544c75c13aa]

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

### 생성 시간

- **총 소요**: 13초
- **병렬 생성**: 3개 인스턴스 동시 생성

---

## Phase 6: 최종 결과

### 새로 생성된 Redis 노드

| 인스턴스 | ID | Private IP | Public IP | 타입 |
|----------|-----|------------|-----------|------|
| k8s-redis-auth | `i-0763922bb112cf5d2` | 10.0.2.43 | 3.34.128.200 | t3.medium |
| k8s-redis-streams | `i-06963134608684348` | 10.0.2.215 | 3.38.200.174 | t3.small |
| k8s-redis-cache | `i-02c15f544c75c13aa` | 10.0.2.202 | 15.165.200.60 | t3.small |

### Terraform Outputs (주요)

```hcl
redis_auth_instance_id    = "i-0763922bb112cf5d2"
redis_auth_private_ip     = "10.0.2.43"
redis_auth_public_ip      = "3.34.128.200"

redis_cache_instance_id   = "i-02c15f544c75c13aa"
redis_cache_private_ip    = "10.0.2.202"
redis_cache_public_ip     = "15.165.200.60"

redis_streams_instance_id = "i-06963134608684348"
redis_streams_private_ip  = "10.0.2.215"
redis_streams_public_ip   = "3.38.200.174"
```

### 전체 인스턴스 목록 (Ansible Inventory)

```ini
[redis]
k8s-redis-auth ansible_host=3.34.128.200 private_ip=10.0.2.43 workload=cache redis_cluster=auth instance_type=t3.medium phase=1
k8s-redis-streams ansible_host=3.38.200.174 private_ip=10.0.2.215 workload=cache redis_cluster=streams instance_type=t3.small phase=1
k8s-redis-cache ansible_host=15.165.200.60 private_ip=10.0.2.202 workload=cache redis_cluster=cache instance_type=t3.small phase=1
```

---

## Phase 7: vCPU 최종 현황

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 7 | 2 | 14 |
| t3.small | 7 | 2 | 14 |
| **합계** | **18** | - | **38 vCPU** |

- **한계**: 43 vCPU
- **사용**: 38 vCPU
- **여유**: 5 vCPU ✅

---

---

## Phase 8: Terraform Output 갱신 문제 해결

### 문제 발생

`-target` 옵션으로 apply 후 `terraform output -raw ansible_inventory`가 기존 값을 반환:

```bash
mango@mangoui-MacBookAir terraform % terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
mango@mangoui-MacBookAir terraform % grep -A5 "\[redis\]" ../ansible/inventory/hosts.ini

[redis]
k8s-redis ansible_host=16.184.30.58 private_ip=10.0.2.235 workload=cache instance_type=t3.small phase=1
# ❌ 기존 삭제된 노드 IP가 출력됨
```

### 원인 분석

1. **개별 output 확인**: 정상
   ```bash
   terraform output redis_auth_public_ip
   # "3.34.128.200" ✅
   ```

2. **Terraform state 확인**: 정상
   ```bash
   terraform state list | grep redis
   # module.redis_auth.aws_instance.this ✅
   # module.redis_cache.aws_instance.this ✅
   # module.redis_streams.aws_instance.this ✅
   ```

3. **원인**: `-target` 옵션으로 apply하면 **output이 완전히 갱신되지 않음**

### 해결

```bash
# -refresh-only로 state 갱신 (리소스 변경 없이)
terraform apply -refresh-only \
  -var="dockerhub_password=dckr_pat_xxx" \
  -auto-approve

# 이후 output 정상 출력
terraform output -raw ansible_inventory | grep -A5 "\[redis\]"
# [redis]
# k8s-redis-auth ansible_host=3.34.128.200 ... ✅
# k8s-redis-streams ansible_host=3.38.200.174 ... ✅
# k8s-redis-cache ansible_host=15.165.200.60 ... ✅
```

### 교훈

> **`-target` 사용 후에는 반드시 `-refresh-only`로 output을 갱신해야 한다.**

---

## Phase 9: Ansible SSH 테스트

```bash
mango@mangoui-MacBookAir terraform % terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

mango@mangoui-MacBookAir terraform % grep -A5 "\[redis\]" ../ansible/inventory/hosts.ini

[redis]
k8s-redis-auth ansible_host=3.34.128.200 private_ip=10.0.2.43 workload=cache redis_cluster=auth instance_type=t3.medium phase=1
k8s-redis-streams ansible_host=3.38.200.174 private_ip=10.0.2.215 workload=cache redis_cluster=streams instance_type=t3.small phase=1
k8s-redis-cache ansible_host=15.165.200.60 private_ip=10.0.2.202 workload=cache redis_cluster=cache instance_type=t3.small phase=1

# RabbitMQ (Phase 4: 2025-11-08 활성화)

mango@mangoui-MacBookAir terraform % cd ../ansible
ansible -i inventory/hosts.ini redis -m ping

k8s-redis-streams | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
k8s-redis-auth | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
k8s-redis-cache | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

### 결과

| 노드 | SSH | 상태 |
|------|-----|------|
| k8s-redis-auth | ✅ SUCCESS | pong |
| k8s-redis-streams | ✅ SUCCESS | pong |
| k8s-redis-cache | ✅ SUCCESS | pong |

---

---

## Phase 10: Redis 노드 기본 설정 (containerd, kubeadm)

새 노드에 Kubernetes 런타임이 없어서 `setup-new-nodes.yml` 플레이북 생성 후 실행:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/setup-new-nodes.yml -l redis
```

### 설치 결과

| 노드 | containerd | kubeadm | kubelet |
|------|------------|---------|---------|
| k8s-redis-auth | active ✅ | v1.28.4 | v1.28.4 |
| k8s-redis-streams | active ✅ | v1.28.4 | v1.28.4 |
| k8s-redis-cache | active ✅ | v1.28.4 | v1.28.4 |

```
PLAY RECAP
k8s-redis-auth    : ok=38  changed=18  unreachable=0  failed=0
k8s-redis-streams : ok=37  changed=18  unreachable=0  failed=0
k8s-redis-cache   : ok=37  changed=18  unreachable=0  failed=0
```

---

## Phase 11: Worker Join 성공

```bash
ansible-playbook -i inventory/hosts.ini playbooks/03-worker-join.yml \
  -l redis \
  -e kubectl_user=ubuntu
```

### 결과

```
This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.
```

| 노드 | Join | Provider ID | kubelet |
|------|------|-------------|---------|
| k8s-redis-auth | ✅ | aws:///ap-northeast-2a/... | ok |
| k8s-redis-streams | ✅ | aws:///ap-northeast-2b/... | ok |
| k8s-redis-cache | ✅ | aws:///ap-northeast-2c/... | ok |

```
PLAY RECAP
k8s-redis-auth    : ok=16  changed=6  unreachable=0  failed=0
k8s-redis-streams : ok=15  changed=6  unreachable=0  failed=0
k8s-redis-cache   : ok=15  changed=6  unreachable=0  failed=0
```

---

## Phase 12: 노드 라벨/테인트 적용

```bash
ansible-playbook -i inventory/hosts.ini playbooks/fix-node-labels.yml \
  -l redis \
  -e kubectl_user=ubuntu
```

### 라벨 확인

```bash
kubectl get nodes --show-labels | grep redis-cluster
```

| 노드 | redis-cluster | infra-type | workload | tier | STATUS |
|------|---------------|------------|----------|------|--------|
| k8s-redis-auth | auth | redis-auth | cache | data | Ready ✅ |
| k8s-redis-streams | streams | redis-streams | cache | data | Ready ✅ |
| k8s-redis-cache | cache | redis-cache | cache | data | Ready ✅ |

### 기존 노드 상태

```
k8s-redis  NotReady  <none>  29d  v1.28.4  10.0.2.235  (삭제된 인스턴스)
```

> ⚠️ 기존 `k8s-redis` 노드는 EC2가 삭제되어 `NotReady`
> Kubernetes에서 수동 삭제 필요: `kubectl delete node k8s-redis`

---

---

## Phase 13: Git Push

```bash
git checkout -b feat/redis-3node-cluster
git add -A
git commit -m "feat: Redis 3-node cluster + Redis Streams SSE migration"
git push -u origin feat/redis-3node-cluster
```

### Pre-commit Hooks 실행

첫 커밋 시도에서 pre-commit hooks가 파일을 자동 수정:

```
black....................................................................Passed
ruff.....................................................................Failed (unused variable 제거)
trim trailing whitespace.................................................Failed (자동 수정)
fix end of files.........................................................Failed (자동 수정)
Pretty format YAML.......................................................Failed (자동 수정)
```

**수정된 항목:**
- `first_event_sent` 미사용 변수 제거 (`completion.py`)
- YAML 파일 포맷팅 (RedisFailover CRs, ArgoCD Apps)
- 파일 끝 개행 추가

### 커밋 내용

- **39 files changed**, 1912 insertions(+), 689 deletions(-)
- **PR #225**: https://github.com/eco2-team/backend/pull/225
- **Labels**: infrastructure, terraform, ansible, kubernetes, gitops, redis

---

## Phase 14: CI 파이프라인

### Terraform Validation 실패

```
terraform fmt -check -recursive
outputs.tf
Error: Terraform exited with code 3.
```

### 수정 및 재Push

```bash
terraform fmt outputs.tf
git add terraform/outputs.tf
git commit -m "style: terraform fmt outputs.tf"
git push
```

- 들여쓰기 수정: 36 insertions(+), 36 deletions(-)

---

## Phase 15: CI 수정

### Redis 연결 에러

```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379
```

**원인**: `domains/_shared/events/` 모듈이 테스트 시 Redis 연결을 시도

### 수정 1: Redis 서비스 추가

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - 6379:6379
```

### 수정 2: shared_triggers 추가

```python
shared_triggers = {
    "domains/_shared/events": ["scan"],  # Redis Streams SSE
}
```

### 수정 3: Changed files 필터

```yaml
files: |
  domains/_shared/events/**
```

---

## 체크리스트

### Infrastructure Provisioning
- [x] Terraform Apply 완료 (3-node Redis cluster)
- [x] Ansible Inventory 갱신 (`terraform output -raw ansible_inventory`)
- [x] SSH 테스트 성공 (3 nodes ping pong)
- [x] 기본 설정 (containerd, kubeadm v1.28.4)
- [x] Worker Join 성공
- [x] 노드 라벨/테인트 적용 (redis-cluster=auth/streams/cache)
- [x] 기존 NotReady 노드 정리 (`kubectl delete node k8s-redis`)

### Code & CI/CD
- [x] Git 브랜치 분리 (`feat/redis-3node-cluster`)
- [x] Pre-commit hooks 통과 (black, ruff, yaml)
- [x] PR 생성 (#225)
- [x] Terraform fmt 수정
- [x] CI Redis 서비스 추가
- [x] shared_triggers 추가 (`domains/_shared/events`)
- [x] CI 파이프라인 통과
- [x] PR Merge → develop
- [x] Celery 버전 통일 (5.3.4 → 5.4.0)
- [x] celery-beat 이미지 변경 (scan-api → scan-worker)

### Deployment
- [x] ArgoCD Sync (Redis Operator) - `dev-redis-operator` Synced/Healthy
- [x] ArgoCD Sync (RedisFailover CRs) - `dev-redis-cluster` Synced/Healthy
- [x] Redis Pod 정상 기동 확인 (6 Pods Running)
- [x] 환경변수 전파 확인
- [ ] k6 부하 테스트 (50 VU)

---

## Phase 16: Redis Cluster 배포 완료

### ArgoCD Application 상태

```bash
kubectl get applications -n argocd | grep redis

NAME                   SYNC STATUS   HEALTH STATUS
dev-redis-cluster      Synced        Healthy
dev-redis-operator     Synced        Healthy
```

### RedisFailover CRs

```bash
kubectl get redisfailover -n redis

NAME            REDIS   SENTINELS   AGE
auth-redis      1       1           20m
cache-redis     1       1           20m
streams-redis   1       1           20m
```

### Redis Pods

```bash
kubectl get pods -n redis -o wide

NAME                                 READY   STATUS    NODE
rfr-auth-redis-0                     3/3     Running   k8s-redis-auth
rfr-cache-redis-0                    3/3     Running   k8s-redis-cache
rfr-streams-redis-0                  3/3     Running   k8s-redis-streams
rfs-auth-redis-66bf8f9657-dzp7v      2/2     Running   k8s-redis-auth
rfs-cache-redis-7845fbdd47-l27dr     2/2     Running   k8s-redis-cache
rfs-streams-redis-7d9c9986d9-twjdx   2/2     Running   k8s-redis-streams
```

### Redis 메모리 사용량

| Instance | Used Memory | Policy |
|----------|-------------|--------|
| auth-redis | 872.66K | noeviction |
| streams-redis | 893.45K | noeviction |
| cache-redis | 926.23K | allkeys-lru |

### 앱 연결 상태

| Service | Redis Instance | Status |
|---------|---------------|--------|
| scan-worker | rfr-streams-redis | ✅ Connected |
| scan-worker | rfr-cache-redis | ✅ Connected |
| ext-authz | rfr-auth-redis | ✅ Running (2 replicas) |

```bash
# Scan Worker Redis Streams 연결 테스트
kubectl exec -n scan deployment/scan-worker -- python3 -c "
import redis
r = redis.from_url('redis://rfr-streams-redis.redis.svc.cluster.local:6379/0')
print('Streams Redis:', r.ping())
"
# Streams Redis: True
```

---

## 참고: SSH 접속 명령어

```bash
# Redis Auth
ssh -i ~/.ssh/sesacthon.pem ubuntu@3.34.128.200

# Redis Streams
ssh -i ~/.ssh/sesacthon.pem ubuntu@3.38.200.174

# Redis Cache
ssh -i ~/.ssh/sesacthon.pem ubuntu@15.165.200.60
```

---

## 참고: 기존 Redis 인스턴스 (삭제됨)

| 인스턴스 | ID | 상태 |
|----------|-----|------|
| k8s-redis | `i-03efa79ec352774fe` | 이미 삭제됨 (Phase 1에서) |
| k8s-redis-cache (고아) | `i-0e9a1d55b934e6990` | 삭제됨 |
| k8s-redis-streams (고아) | `i-0d2620f00548d6e87` | 삭제됨 |

