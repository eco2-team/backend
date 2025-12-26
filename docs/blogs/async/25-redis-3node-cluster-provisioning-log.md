# Redis 3-Node 클러스터 프로비저닝 실측 로그

> **작업 일시**: 2025-12-26  
> **환경**: AWS ap-northeast-2 (Development)  
> **도구**: Terraform + Ansible + kubeadm

이 문서는 단일 Redis 인스턴스를 용도별 3-Node 클러스터로 마이그레이션한 실제 작업 로그입니다.
트러블슈팅 과정과 교훈을 포함하여 유사한 작업 시 참고할 수 있도록 작성했습니다.

---

## Phase 1: 초기 상태 확인

```bash
$ aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[Tags[?Key==`Name`].Value|[0],InstanceType,InstanceId]' \
  --output table

+----------------------+------------+-----------------------+
|  k8s-postgresql      |  t3.large  |  i-xxxx...postgresql  |
|  k8s-worker-ai       |  t3.medium |  i-xxxx...worker-ai   |
|  k8s-master          |  t3.xlarge |  i-xxxx...master      |
|  k8s-api-character   |  t3.small  |  i-xxxx...character   |
|  k8s-api-chat        |  t3.medium |  i-xxxx...chat        |
|  k8s-api-auth        |  t3.small  |  i-xxxx...auth        |
|  k8s-api-scan        |  t3.medium |  i-xxxx...scan        |
|  k8s-api-image       |  t3.small  |  i-xxxx...image       |
|  k8s-worker-storage  |  t3.medium |  i-xxxx...storage     |
|  k8s-logging         |  t3.large  |  i-xxxx...logging     |
|  k8s-api-my          |  t3.small  |  i-xxxx...my          |
|  k8s-monitoring      |  t3.large  |  i-xxxx...monitoring  |
|  k8s-rabbitmq        |  t3.medium |  i-xxxx...rabbitmq    |
|  k8s-api-location    |  t3.small  |  i-xxxx...location    |
|  k8s-redis-cache     |  t3.small  |  i-xxxx...redis-cache |
|  k8s-redis-streams   |  t3.small  |  i-xxxx...redis-str   |
|  k8s-ingress-gateway |  t3.medium |  i-xxxx...gateway     |
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

- **한계**: 43 vCPU (AWS On-Demand 기본 Quota)
- **여유**: 7 vCPU

---

## Phase 2: 고아 인스턴스 정리

이전 Terraform apply 실패로 인해 생성된 중복 인스턴스를 정리합니다.

> ⚠️ **고아 인스턴스란?**: Terraform state에는 없지만 실제로 AWS에 존재하는 리소스.
> apply 실패/중단 시 발생할 수 있으며, 비용과 quota를 소모합니다.

```bash
# 중복 인스턴스 삭제
$ aws ec2 terminate-instances --instance-ids i-xxxx...cache i-xxxx...streams

# 삭제 완료 대기 (약 30초)
$ aws ec2 wait instance-terminated --instance-ids i-xxxx...cache i-xxxx...streams
```

---

## Phase 3: Terraform State 정리

State에서 삭제된 리소스 참조를 제거합니다.

```bash
$ terraform state rm module.redis_cache.aws_instance.this
Removed module.redis_cache.aws_instance.this
Successfully removed 1 resource instance(s).

$ terraform state rm module.redis_streams.aws_instance.this
Removed module.redis_streams.aws_instance.this
Successfully removed 1 resource instance(s).
```

---

## Phase 4: Terraform Plan

`-target` 옵션으로 Redis 모듈만 변경 범위를 제한합니다.

```bash
$ terraform plan \
  -var="dockerhub_password=$DOCKERHUB_TOKEN" \
  -target=module.redis_auth \
  -target=module.redis_streams \
  -target=module.redis_cache \
  -out=redis-3node.plan

Plan: 3 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + redis_auth_instance_id    = (known after apply)
  + redis_auth_private_ip     = (known after apply)
  + redis_auth_public_ip      = (known after apply)
  ~ redis_cache_instance_id   = "i-xxxx..." -> (known after apply)
  ~ redis_streams_instance_id = "i-xxxx..." -> (known after apply)
```

---

## Phase 5: Terraform Apply

```bash
$ terraform apply redis-3node.plan

module.redis_cache.aws_instance.this: Creating...
module.redis_streams.aws_instance.this: Creating...
module.redis_auth.aws_instance.this: Creating...
module.redis_streams.aws_instance.this: Creation complete after 13s
module.redis_auth.aws_instance.this: Creation complete after 13s
module.redis_cache.aws_instance.this: Creation complete after 13s

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

**소요 시간**: 13초 (3개 인스턴스 병렬 생성)

---

## Phase 6: 프로비저닝 결과

### 새로 생성된 Redis 노드

| 인스턴스 | 타입 | Private IP | 용도 |
|----------|------|------------|------|
| k8s-redis-auth | t3.medium | 10.0.2.x | JWT Blacklist, OAuth State |
| k8s-redis-streams | t3.small | 10.0.2.x | SSE 이벤트 스트림 |
| k8s-redis-cache | t3.small | 10.0.2.x | Celery 결과, 이미지 캐시 |

### vCPU 최종 현황

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 7 | 2 | 14 |
| t3.small | 7 | 2 | 14 |
| **합계** | **18** | - | **38 vCPU** |

- **여유**: 5 vCPU ✅

---

## Phase 7: Terraform Output 갱신 문제

### 문제 발생

`-target` 옵션으로 apply 후 `terraform output`이 기존 값을 반환:

```bash
$ terraform output -raw ansible_inventory > hosts.ini
$ grep -A3 "\[redis\]" hosts.ini

[redis]
k8s-redis ansible_host=<OLD_IP>  # ❌ 삭제된 노드 IP
```

### 원인 분석

```bash
# 개별 output은 정상
$ terraform output redis_auth_public_ip
"<NEW_IP>" ✅

# State도 정상
$ terraform state list | grep redis
module.redis_auth.aws_instance.this ✅
module.redis_cache.aws_instance.this ✅
module.redis_streams.aws_instance.this ✅
```

**원인**: `-target` 옵션으로 apply하면 **대상 외 output이 갱신되지 않음**

### 해결

```bash
# -refresh-only로 전체 state 갱신 (리소스 변경 없이)
$ terraform apply -refresh-only -var="dockerhub_password=$TOKEN" -auto-approve

# 이후 output 정상 출력
$ terraform output -raw ansible_inventory | grep -A3 "\[redis\]"
[redis]
k8s-redis-auth ansible_host=<NEW_IP> ✅
k8s-redis-streams ansible_host=<NEW_IP> ✅
k8s-redis-cache ansible_host=<NEW_IP> ✅
```

> 💡 **교훈**: `-target` 사용 후에는 반드시 `-refresh-only`로 output을 갱신해야 한다.

---

## Phase 8: Ansible SSH 테스트

```bash
$ ansible -i inventory/hosts.ini redis -m ping

k8s-redis-auth | SUCCESS => {"ping": "pong"}
k8s-redis-streams | SUCCESS => {"ping": "pong"}
k8s-redis-cache | SUCCESS => {"ping": "pong"}
```

| 노드 | SSH | 상태 |
|------|-----|------|
| k8s-redis-auth | ✅ SUCCESS | pong |
| k8s-redis-streams | ✅ SUCCESS | pong |
| k8s-redis-cache | ✅ SUCCESS | pong |

---

## Phase 9: Kubernetes 런타임 설치

새 EC2 인스턴스에는 containerd, kubeadm이 없으므로 별도 플레이북 실행:

```bash
$ ansible-playbook -i inventory/hosts.ini playbooks/setup-new-nodes.yml -l redis
```

### 설치 결과

| 노드 | containerd | kubeadm | kubelet |
|------|------------|---------|---------|
| k8s-redis-auth | active ✅ | v1.28.4 | v1.28.4 |
| k8s-redis-streams | active ✅ | v1.28.4 | v1.28.4 |
| k8s-redis-cache | active ✅ | v1.28.4 | v1.28.4 |

```
PLAY RECAP
k8s-redis-auth    : ok=38  changed=18  failed=0
k8s-redis-streams : ok=37  changed=18  failed=0
k8s-redis-cache   : ok=37  changed=18  failed=0
```

---

## Phase 10: Worker Join

```bash
$ ansible-playbook -i inventory/hosts.ini playbooks/03-worker-join.yml \
  -l redis -e kubectl_user=ubuntu
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

---

## Phase 11: 노드 라벨 적용

```bash
$ ansible-playbook -i inventory/hosts.ini playbooks/fix-node-labels.yml \
  -l redis -e kubectl_user=ubuntu
```

### 라벨 확인

| 노드 | redis-cluster | infra-type | STATUS |
|------|---------------|------------|--------|
| k8s-redis-auth | auth | redis-auth | Ready ✅ |
| k8s-redis-streams | streams | redis-streams | Ready ✅ |
| k8s-redis-cache | cache | redis-cache | Ready ✅ |

### 기존 노드 정리

```bash
# 삭제된 EC2에 해당하는 NotReady 노드 제거
$ kubectl delete node k8s-redis
```

---

## Phase 12: CI/CD 파이프라인 조정

### 1. Terraform fmt 실패

```
terraform fmt -check -recursive
outputs.tf
Error: Terraform exited with code 3.
```

**해결**: `terraform fmt outputs.tf` 후 재push

### 2. Redis 연결 에러

```
redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379
```

**원인**: `domains/_shared/events/` 모듈이 테스트 시 Redis 연결 시도

**해결**: GitHub Actions에 Redis 서비스 추가

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - 6379:6379
```

### 3. shared_triggers 누락

**해결**: CI 매트릭스에 공유 모듈 트리거 추가

```python
shared_triggers = {
    "domains/_shared/events": ["scan"],
}
```

---

## Phase 13: Redis Cluster 배포 완료

### ArgoCD Application 상태

```bash
$ kubectl get applications -n argocd | grep redis

NAME                   SYNC STATUS   HEALTH STATUS
dev-redis-cluster      Synced        Healthy
dev-redis-operator     Synced        Healthy
```

### RedisFailover CRs

```bash
$ kubectl get redisfailover -n redis

NAME            REDIS   SENTINELS   AGE
auth-redis      1       1           20m
cache-redis     1       1           20m
streams-redis   1       1           20m
```

### Redis Pods

```bash
$ kubectl get pods -n redis -o wide

NAME                       READY   STATUS    NODE
rfr-auth-redis-0           3/3     Running   k8s-redis-auth
rfr-cache-redis-0          3/3     Running   k8s-redis-cache
rfr-streams-redis-0        3/3     Running   k8s-redis-streams
rfs-auth-redis-xxx         2/2     Running   k8s-redis-auth
rfs-cache-redis-xxx        2/2     Running   k8s-redis-cache
rfs-streams-redis-xxx      2/2     Running   k8s-redis-streams
```

### Redis 설정 확인

| Instance | Used Memory | maxmemory-policy |
|----------|-------------|------------------|
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
# Redis Streams 연결 테스트
$ kubectl exec -n scan deployment/scan-worker -- python3 -c "
import redis
r = redis.from_url('redis://rfr-streams-redis.redis.svc.cluster.local:6379/0')
print('Streams Redis:', r.ping())
"
# Streams Redis: True
```

---

## 체크리스트

### Infrastructure Provisioning
- [x] Terraform Apply (3-node Redis cluster)
- [x] Ansible Inventory 갱신
- [x] SSH 테스트 성공
- [x] containerd, kubeadm v1.28.4 설치
- [x] Worker Join 성공
- [x] 노드 라벨 적용 (redis-cluster=auth/streams/cache)
- [x] 기존 NotReady 노드 정리

### Code & CI/CD
- [x] Git 브랜치 분리 (`feat/redis-3node-cluster`)
- [x] Pre-commit hooks 통과
- [x] Terraform fmt 수정
- [x] CI Redis 서비스 추가
- [x] shared_triggers 추가
- [x] CI 파이프라인 통과
- [x] PR Merge → develop

### Deployment
- [x] ArgoCD Sync (Redis Operator)
- [x] ArgoCD Sync (RedisFailover CRs)
- [x] Redis Pod 정상 기동 (6 Pods)
- [x] 환경변수 전파 확인
- [ ] k6 부하 테스트 (50 VU)

---

## 주요 교훈

1. **`-target` 사용 후 `-refresh-only` 필수**
   - 일부 모듈만 apply하면 output이 갱신되지 않음

2. **고아 인스턴스 주의**
   - apply 실패 시 AWS Console에서 직접 확인 필요
   - vCPU quota 소모 원인이 될 수 있음

3. **새 노드에는 런타임이 없음**
   - EC2 생성 후 containerd, kubeadm 설치 필요
   - 별도 플레이북 준비 권장

4. **공유 모듈 변경 시 CI 트리거 확인**
   - `_shared/` 변경이 의존 서비스 테스트를 트리거하는지 확인

---

## 참고 자료

- [Terraform -target 옵션 문서](https://developer.hashicorp.com/terraform/cli/commands/plan#target)
- [AWS EC2 vCPU Quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html#ec2-on-demand-instances-limits)
- [kubeadm join 문서](https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-join/)
