# HA Event Architecture 노드 프로비저닝 실측 로그

> **작업 일시**: 2025-12-27
> **환경**: AWS ap-northeast-2 (Development)
> **도구**: Terraform + Ansible + kubeadm
> **참고**: [Redis 3-Node 클러스터 프로비저닝](https://rooftopsnow.tistory.com/90)

이 문서는 SSE HA Architecture 구현을 위해 Event Router와 Redis Pub/Sub 노드를 프로비저닝한 실측 로그입니다.

---

## 개요

기존 18-Node 클러스터에 2개의 새 노드를 추가:
- `k8s-event-router` (t3.small) - Redis Streams → Pub/Sub Bridge
- `k8s-redis-pubsub` (t3.small) - Realtime Event Broadcast

### 아키텍처 배경

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SSE HA Architecture (Full)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐                                                                │
│  │  Client  │ ◄────────────────────────────────────────────────────┐        │
│  └────┬─────┘                                                       │        │
│       │ POST /scan                                                  │ SSE    │
│       ▼                                                             │        │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐                   │        │
│  │ Scan API │───►│ RabbitMQ  │───►│ Worker     │                   │        │
│  │ (HPA)    │    │ (Cluster) │    │ (KEDA)     │                   │        │
│  └──────────┘    └───────────┘    └─────┬──────┘                   │        │
│                                         │ XADD (멱등)               │        │
│                                         ▼                           │        │
│  ┌───────────────────────────────────────────────────────────────┐ │        │
│  │              Redis Streams (k8s-redis-streams)                │ │        │
│  │  scan:events:0, scan:events:1, scan:events:2, scan:events:3   │ │        │
│  └───────────────────────────────────────────────────────────────┘ │        │
│                                         │ XREADGROUP                │        │
│                                         ▼                           │        │
│  ┌───────────────────────────────────────────────────────────────┐ │        │
│  │     Event Router (k8s-event-router) [NEW - Phase 6]           │ │        │
│  │  • Consumer Group: XREADGROUP + XACK                          │ │        │
│  │  • State Update: scan:state:{job_id}                          │ │        │
│  │  • XPENDING Reclaim: 장애 복구                                 │ │        │
│  └───────────────────────────────────────────────────────────────┘ │        │
│                                         │ PUBLISH                   │        │
│                                         ▼                           │        │
│  ┌───────────────────────────────────────────────────────────────┐ │        │
│  │     Redis Pub/Sub (k8s-redis-pubsub) [NEW - Phase 6]          │ │        │
│  │  • Channels: sse:events:{job_id}                              │ │        │
│  │  • Fire & Forget (구독자 없으면 drop)                          │ │        │
│  └───────────────────────────────────────────────────────────────┘ │        │
│                                         │ SUBSCRIBE                 │        │
│                                         ▼                           │        │
│  ┌───────────────────────────────────────────────────────────────┐ │        │
│  │       SSE Gateway (k8s-sse-gateway) [Existing]                │─┘        │
│  │  • Pub/Sub 구독: sse:events:{job_id}                          │          │
│  │  • State 복구: scan:state:{job_id}                            │          │
│  │  • seq 기반 중복 필터링                                        │          │
│  │  • HPA: 수평 확장 (Consistent Hash 불필요)                     │          │
│  └───────────────────────────────────────────────────────────────┘          │
│                                                                              │
│  ▶ 신규 노드: k8s-event-router, k8s-redis-pubsub                            │
│  ▶ 기존 노드: k8s-sse-gateway (Pub/Sub 구독 방식으로 전환)                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 컴포넌트별 역할

| 컴포넌트 | 노드 | 역할 |
|---------|------|------|
| Redis Streams | k8s-redis-streams | 이벤트 원장 (내구성) |
| Event Router | **k8s-event-router** (NEW) | Streams→Pub/Sub 브릿지 |
| Redis Pub/Sub | **k8s-redis-pubsub** (NEW) | 실시간 브로드캐스트 |
| SSE Gateway | k8s-sse-gateway | 클라이언트 연결 + Fan-out |

---

## Phase 1: 사전 상태 확인

### 기존 vCPU 현황

```bash
$ terraform output cluster_info
{
  "total_nodes" = 18
  "total_vcpu" = 40
  "phase" = "Phase 1-5 Complete - 18-Node Architecture"
}
```

### 추가 예정 리소스

| 노드 | 인스턴스 타입 | vCPU | 메모리 | 용도 |
|------|-------------|------|--------|------|
| k8s-event-router | t3.small | 2 | 2GB | XREADGROUP → PUBLISH |
| k8s-redis-pubsub | t3.small | 2 | 2GB | Pub/Sub Broadcast |

---

## Phase 2: Terraform 구성

### 2.1 kubelet_profiles 추가

```hcl
# main.tf - locals.kubelet_profiles에 추가
"k8s-event-router" = "--node-labels=role=event-router,domain=event-router,service=event-router,workload=event-router,tier=integration,phase=5 --register-with-taints=domain=event-router:NoSchedule"
"k8s-redis-pubsub" = "--node-labels=role=infrastructure,domain=data,infra-type=redis-pubsub,redis-cluster=pubsub,workload=cache,tier=data,phase=1 --register-with-taints=domain=data:NoSchedule"
```

### 2.2 EC2 모듈 정의

```hcl
# main.tf - Phase 6: HA Event Architecture

# Event Router Node
module "event_router" {
  source = "./modules/ec2"

  instance_name        = "k8s-event-router"
  instance_type        = "t3.small"
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[2]  # AZ-c
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-event-router"
    kubelet_extra_args = local.kubelet_profiles["k8s-event-router"]
  })

  tags = {
    Role     = "worker"
    Workload = "event-router"
    Domain   = "event-router"
    Phase    = "6"
  }
}

# Redis Pub/Sub Node
module "redis_pubsub" {
  source = "./modules/ec2"

  instance_name        = "k8s-redis-pubsub"
  instance_type        = "t3.small"
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]  # AZ-a
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 10  # Pub/Sub only, no persistence
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-redis-pubsub"
    kubelet_extra_args = local.kubelet_profiles["k8s-redis-pubsub"]
  })

  tags = {
    Role         = "worker"
    Workload     = "cache"
    RedisCluster = "pubsub"
    Phase        = "6"
  }
}
```

---

## Phase 3: Terraform Plan (-target 사용)

> ⚠️ **중요**: `-target` 옵션으로 범위를 제한하여 기존 인프라에 영향 없이 진행

```bash
$ terraform plan \
  -var="dockerhub_password=${DOCKERHUB_TOKEN:-dummy}" \
  -target=module.event_router \
  -target=module.redis_pubsub \
  -out=ha-event-nodes.plan

Plan: 2 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + event_router_instance_id  = (known after apply)
  + event_router_private_ip   = (known after apply)
  + event_router_public_ip    = (known after apply)
  + redis_pubsub_instance_id  = (known after apply)
  + redis_pubsub_private_ip   = (known after apply)
  + redis_pubsub_public_ip    = (known after apply)
```

**검증 포인트**:
- ✅ `2 to add` - 새 노드 2개만 추가
- ✅ `0 to change` - 기존 리소스 변경 없음
- ✅ `0 to destroy` - 삭제 없음

---

## Phase 4: Terraform Apply

```bash
$ terraform apply "ha-event-nodes.plan"

module.redis_pubsub.aws_instance.this: Creating...
module.event_router.aws_instance.this: Creating...
module.redis_pubsub.aws_instance.this: Still creating... [10s elapsed]
module.event_router.aws_instance.this: Still creating... [10s elapsed]
module.redis_pubsub.aws_instance.this: Creation complete after 13s [id=i-0f70d6b9ac5dde237]
module.event_router.aws_instance.this: Creation complete after 13s [id=i-091c54e48fca2b4f4]

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**소요 시간**: 13초 (2개 인스턴스 병렬 생성)

### 생성된 인스턴스

| 노드 | Instance ID | Public IP | Private IP |
|------|-------------|-----------|------------|
| k8s-event-router | i-091c54e48fca2b4f4 | 3.39.195.102 | 10.0.3.14 |
| k8s-redis-pubsub | i-0f70d6b9ac5dde237 | 43.201.54.31 | 10.0.1.248 |

---

## Phase 5: Output 갱신 (-refresh-only)

> ⚠️ **주의**: `-target` 사용 후에는 outputs가 완전히 갱신되지 않음

### 문제 증상

Apply 직후 `cluster_info` 출력:
```hcl
"total_nodes" = 17   # 예상: 20
"total_vcpu" = 38    # 예상: 44
"phase" = "Phase 1-4 Complete - 17-Node..."  # 갱신 안됨
```

### 해결

```bash
$ terraform apply -refresh-only -auto-approve -var="dockerhub_password=dummy"
```

### 갱신 후 확인

```hcl
cluster_info = {
  "total_nodes" = 20
  "total_vcpu" = 44
  "total_memory_gb" = 60
  "phase" = "Phase 1-6 Complete - 20-Node HA Architecture"
}

node_roles = {
  ...
  "event_router" = "Event Router - Streams→Pub/Sub Bridge (t3.small, 2GB) - Phase 6"
  "redis_pubsub" = "Redis Pub/Sub - Realtime Broadcast (t3.small, 2GB) - Phase 6"
  ...
}
```

---

## Phase 6: SSH 연결 확인

```bash
$ ssh -i ~/.ssh/sesacthon.pem ubuntu@3.39.195.102 "hostname && uptime"
k8s-event-router
 18:16:50 up 2 min,  0 users,  load average: 0.16, 0.11, 0.04

$ ssh -i ~/.ssh/sesacthon.pem ubuntu@43.201.54.31 "hostname && uptime"
k8s-redis-pubsub
 18:16:52 up 2 min,  0 users,  load average: 0.12, 0.13, 0.05
```

---

## Phase 7: Ansible - 노드 설정

### Inventory 업데이트

```bash
$ terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
```

### containerd, kubeadm 설치

```bash
$ cd ansible && ansible-playbook -i inventory/hosts.ini \
  playbooks/setup-new-nodes.yml -l "event_router,redis_pubsub"

PLAY RECAP *********************************************************************
k8s-event-router  : ok=37   changed=18   unreachable=0   failed=0
k8s-redis-pubsub  : ok=38   changed=18   unreachable=0   failed=0
```

### 설치 결과

```
k8s-event-router:
  - containerd: active
  - kubeadm: v1.28.4
  - kubelet: Kubernetes v1.28.4

k8s-redis-pubsub:
  - containerd: active
  - kubeadm: v1.28.4
  - kubelet: Kubernetes v1.28.4
```

---

## Phase 8: Worker Join

### Join Token 생성

```bash
$ ssh ubuntu@13.209.44.249 "kubeadm token create --print-join-command"
kubeadm join 10.0.1.21:6443 --token l5b0yw.kja4c9un8t015qv6 \
  --discovery-token-ca-cert-hash sha256:3dbda1db23abe18e97d7e7a0d20b57acd0f7751fdb56844575c52cc13bd95d9e
```

### 노드 Join 실행

```bash
# Event Router
$ ssh ubuntu@3.39.195.102 "sudo kubeadm join 10.0.1.21:6443 ..."
This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

# Redis Pub/Sub
$ ssh ubuntu@43.201.54.31 "sudo kubeadm join 10.0.1.21:6443 ..."
This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.
```

---

## Phase 9: 노드 상태 확인

### Ready 상태 전환

```bash
$ kubectl get nodes k8s-event-router k8s-redis-pubsub
NAME               STATUS   ROLES    AGE   VERSION
k8s-event-router   Ready    <none>   57s   v1.28.4
k8s-redis-pubsub   Ready    <none>   53s   v1.28.4
```

### 라벨 확인

```bash
$ kubectl get nodes k8s-event-router --show-labels
LABELS:
  domain=event-router
  role=event-router
  service=event-router
  tier=integration
  workload=event-router

$ kubectl get nodes k8s-redis-pubsub --show-labels
LABELS:
  domain=data
  infra-type=redis-pubsub
  redis-cluster=pubsub
  role=infrastructure
  tier=data
```

### Taint 확인

```bash
$ kubectl describe nodes k8s-event-router k8s-redis-pubsub | grep -A1 Taints
k8s-event-router:
  Taints: domain=event-router:NoSchedule

k8s-redis-pubsub:
  Taints: domain=data:NoSchedule
```

---

## 최종 클러스터 현황

```bash
$ kubectl get nodes -o wide
NAME                  STATUS   ROLES           AGE   VERSION   INTERNAL-IP
k8s-api-auth          Ready    <none>          21h   v1.28.4   10.0.1.53
k8s-api-character     Ready    <none>          21h   v1.28.4   10.0.1.244
k8s-api-chat          Ready    <none>          21h   v1.28.4   10.0.1.49
k8s-api-image         Ready    <none>          21h   v1.28.4   10.0.3.183
k8s-api-location      Ready    <none>          21h   v1.28.4   10.0.2.236
k8s-api-my            Ready    <none>          21h   v1.28.4   10.0.2.56
k8s-api-scan          Ready    <none>          30d   v1.28.4   10.0.3.219
k8s-event-router      Ready    <none>          57s   v1.28.4   10.0.3.14      # NEW
k8s-ingress-gateway   Ready    <none>          21h   v1.28.4   10.0.1.150
k8s-logging           Ready    <none>          10d   v1.28.4   10.0.3.59
k8s-master            Ready    control-plane   30d   v1.28.4   10.0.1.21
k8s-monitoring        Ready    <none>          21h   v1.28.4   10.0.2.84
k8s-postgresql        Ready    <none>          30d   v1.28.4   10.0.1.211
k8s-rabbitmq          Ready    <none>          21h   v1.28.4   10.0.2.148
k8s-redis-auth        Ready    <none>          29h   v1.28.4   10.0.2.43
k8s-redis-cache       Ready    <none>          29h   v1.28.4   10.0.2.202
k8s-redis-pubsub      Ready    <none>          53s   v1.28.4   10.0.1.248     # NEW
k8s-redis-streams     Ready    <none>          29h   v1.28.4   10.0.2.215
k8s-sse-gateway       Ready    <none>          18h   v1.28.4   10.0.2.195
k8s-worker-ai         Ready    <none>          21h   v1.28.4   10.0.1.127
k8s-worker-storage    Ready    <none>          30d   v1.28.4   10.0.3.246
```

**총 노드 수**: 21개 (Master 1 + Workers 20)

### SSE HA Architecture 관련 노드

| 역할 | 노드 | 상태 |
|------|------|------|
| Redis Streams | k8s-redis-streams | ✅ 기존 |
| Event Router | **k8s-event-router** | ✅ 신규 |
| Redis Pub/Sub | **k8s-redis-pubsub** | ✅ 신규 |
| SSE Gateway | k8s-sse-gateway | ✅ 기존 |

---

## vCPU 현황

| 인스턴스 타입 | 개수 | vCPU/개 | 총 vCPU |
|--------------|------|---------|---------|
| t3.xlarge | 2 | 4 | 8 |
| t3.large | 2 | 2 | 4 |
| t3.medium | 6 | 2 | 12 |
| t3.small | 11 | 2 | 22 |
| **합계** | **21** | - | **46 vCPU** |

---

## 주요 교훈

1. **`-target` 사용 후 `-refresh-only` 필수**
   - 일부 모듈만 apply하면 output이 갱신되지 않음
   - 반드시 `-refresh-only`로 전체 상태 동기화 필요

2. **kubelet_extra_args로 라벨/Taint 자동 적용**
   - Terraform user-data에서 설정하면 Join 시 자동 적용
   - 수동 라벨링 작업 불필요

3. **병렬 인스턴스 생성**
   - 2개 인스턴스가 13초 내 병렬 생성됨
   - 순차 생성 대비 시간 절약

4. **CNI 자동 배포**
   - 기존 클러스터에 CNI가 설치되어 있으면
   - 새 노드 Join 후 자동으로 Ready 상태 전환

---

---

## Phase 10: Redis Pub/Sub 배포

### RedisFailover CR 생성

```bash
$ kubectl apply -f workloads/redis/base/pubsub-redis-failover.yaml
redisfailover.databases.spotahome.com/pubsub-redis created
```

### Pod 배포 현황 (60초 후)

```bash
$ kubectl get pods -n redis -o wide | grep pubsub
NAME                                 READY   STATUS    RESTARTS   AGE     NODE
rfr-pubsub-redis-0                   3/3     Running   0          2m18s   k8s-redis-pubsub
rfr-pubsub-redis-1                   3/3     Running   0          2m17s   k8s-redis-pubsub
rfr-pubsub-redis-2                   3/3     Running   0          2m17s   k8s-redis-pubsub
rfs-pubsub-redis-559f7789f9-j2sff    2/2     Running   0          2m16s   k8s-redis-pubsub
rfs-pubsub-redis-559f7789f9-s7r2m    2/2     Running   0          2m18s   k8s-redis-pubsub
rfs-pubsub-redis-559f7789f9-wlmpx    2/2     Running   0          2m17s   k8s-redis-pubsub
```

### 배포 결과

| 구분 | Replicas | 상태 | 노드 |
|------|----------|------|------|
| Redis Master (rfr-*) | 3 | ✅ Running | k8s-redis-pubsub |
| Sentinel (rfs-*) | 3 | ✅ Running | k8s-redis-pubsub |

### Service 정보

```bash
$ kubectl get svc -n redis | grep pubsub
NAME               TYPE        CLUSTER-IP    PORT(S)
rfr-pubsub-redis   ClusterIP   None          9121/TCP      # Redis (Headless)
rfs-pubsub-redis   ClusterIP   10.102.2.2    26379/TCP     # Sentinel
```

### 연결 테스트

```bash
$ kubectl run redis-test --rm -it --image=redis:7-alpine -- \
  redis-cli -h rfr-pubsub-redis.redis.svc.cluster.local ping
PONG
```

### 환경변수 설정

```bash
REDIS_PUBSUB_URL=redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0
```

---

## Redis 4-Node Cluster 현황

프로비저닝 완료 후 Redis 클러스터 전체 구성:

| 클러스터 | 노드 | 용도 | Replicas | 상태 |
|---------|------|------|----------|------|
| auth-redis | k8s-redis-auth | Blacklist + OAuth | 1+1 | ✅ |
| streams-redis | k8s-redis-streams | SSE 이벤트 원장 | 1+1 | ✅ |
| cache-redis | k8s-redis-cache | Celery + Cache | 1+1 | ✅ |
| **pubsub-redis** | **k8s-redis-pubsub** | Realtime Broadcast | **3+3** | ✅ |

### RedisFailover 상태

```bash
$ kubectl get redisfailover -n redis
NAME            REDIS   SENTINELS   AGE
auth-redis      1       1           28h
cache-redis     1       1           28h
pubsub-redis    3       3           2m      # NEW
streams-redis   1       1           28h
```

---

## 다음 단계

| # | 작업 | 컴포넌트 | 내용 | 상태 |
|---|------|---------|------|------|
| 1 | Redis Pub/Sub 배포 | k8s-redis-pubsub | RedisFailover CR | ✅ 완료 |
| 2 | Event Router 배포 | k8s-event-router | Deployment + KEDA | ⏳ 대기 |
| 3 | SSE-Gateway 변경 | k8s-sse-gateway | Pub/Sub 구독 전환 | ⏳ 대기 |
| 4 | E2E 테스트 | 전체 | 파이프라인 검증 | ⏳ 대기 |

### 2. Event Router 배포 상세

```yaml
# 구현해야 할 내용
- Deployment: replicas=1 (KEDA 스케일링)
- KEDA ScaledObject: Redis Streams pending 기반
- Consumer Group: XREADGROUP + XACK
- Reclaimer: XAUTOCLAIM (장애 복구)
- 환경변수:
  - REDIS_STREAMS_URL
  - REDIS_PUBSUB_URL
  - REDIS_CACHE_URL (State)
```

### 3. SSE-Gateway 변경 상세

```yaml
# 변경해야 할 내용
- XREAD 직접 읽기 → Pub/Sub SUBSCRIBE
- State 복구 로직 추가
- seq 기반 중복 필터링
- Consistent Hash 제거 (HPA 자유 확장)
```

---

## 참고 자료

- [Redis 3-Node 클러스터 프로비저닝](https://rooftopsnow.tistory.com/90)
- [SSE HA Implementation Roadmap](./35-sse-ha-implementation-roadmap.md)
- [SSE HA Architecture](./34-sse-HA-architecture.md)

