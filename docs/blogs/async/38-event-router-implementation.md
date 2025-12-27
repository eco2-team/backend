# 38. SSE HA Architecture #7: Event Router 구현기

## TL;DR

[이전 포스팅](https://rooftopsnow.tistory.com/101)에서 Fan-out 계층의 필요성을 도출했습니다. 이번 포스팅에서는 **Event Router**의 실제 구현 과정, Redis Streams Consumer Group 기반 이벤트 소비, Pub/Sub 발행, 멱등성 보장을 위한 Lua Script, 그리고 배포 과정에서 마주친 트러블슈팅을 기록합니다.

---

## 1. Event Router의 역할

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Event Router: Streams → Pub/Sub 브릿지                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Redis Streams                               │   │
│  │  scan:events:0   scan:events:1   scan:events:2   scan:events:3  │   │
│  └────────────────────────────────────▲────────────────────────────┘   │
│                                       │                                 │
│                              XREADGROUP (Consumer Group)                │
│                                       │                                 │
│  ┌────────────────────────────────────┴────────────────────────────┐   │
│  │                      Event Router                                │   │
│  │                                                                  │   │
│  │  1. XREADGROUP: 모든 shard에서 이벤트 소비                       │   │
│  │  2. Lua Script: 멱등성 체크 + State KV 업데이트                  │   │
│  │  3. PUBLISH: job_id별 채널로 발행                                │   │
│  │  4. XACK: 처리 완료 확인                                         │   │
│  │  5. XAUTOCLAIM: 장애 복구 (Pending 메시지 재처리)                │   │
│  │                                                                  │   │
│  └────────────────────────────────────┬────────────────────────────┘   │
│                                       │                                 │
│                                  PUBLISH                                │
│                                       ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Redis Pub/Sub                               │   │
│  │  sse:events:job-123    sse:events:job-456    sse:events:job-789 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 핵심 책임

| 책임 | 설명 |
|------|------|
| **이벤트 소비** | Redis Streams 4개 shard에서 Consumer Group으로 이벤트 읽기 |
| **State 관리** | `scan:state:{job_id}` KV에 최신 상태 스냅샷 저장 |
| **실시간 발행** | `sse:events:{job_id}` 채널로 Pub/Sub 발행 |
| **멱등성 보장** | 중복 이벤트 발행 방지 (Lua Script) |
| **장애 복구** | XAUTOCLAIM으로 Pending 메시지 재처리 |

---

## 2. 아키텍처: 2-Redis 분리

초기 설계에서는 단일 Redis를 사용했으나, **역할 분리**의 중요성을 깨닫고 2-Redis 구조로 전환했습니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 2-Redis 분리 아키텍처                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────┐│
│  │  Redis Streams (rfr-streams)    │  │  Redis Pub/Sub (rfr-pubsub) ││
│  │  ════════════════════════════   │  │  ════════════════════════   ││
│  │  • 내구성 (AOF/Replica)         │  │  • 휘발성 (emptyDir)        ││
│  │  • Streams: scan:events:{shard} │  │  • Pub/Sub 채널만 사용      ││
│  │  • State KV: scan:state:{job_id}│  │  • sse:events:{job_id}      ││
│  │  • 발행 마킹: published:{...}   │  │                              ││
│  └──────────────────────────────────┘  └──────────────────────────────┘│
│                                                                         │
│  왜 분리했나?                                                           │
│  ─────────────                                                          │
│  1. State KV는 "복구용" → 내구성 필요 → Streams Redis에 저장            │
│  2. Pub/Sub는 "실시간 전달용" → 내구성 불필요 → 별도 Redis로 격리        │
│  3. 장애 격리: Pub/Sub 트래픽이 Streams 성능에 영향주지 않음             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Config 분리

```python
# domains/event-router/config.py
class Settings(BaseSettings):
    # Redis Streams + State KV (내구성 저장소)
    redis_streams_url: str  # rfr-streams-redis.redis.svc.cluster.local:6379

    # Redis Pub/Sub (실시간 전달용)
    redis_pubsub_url: str   # rfr-pubsub-redis.redis.svc.cluster.local:6379
```

---

## 3. Consumer Group 기반 이벤트 소비

### 3.1 XREADGROUP vs XREAD

| 방식 | 특징 | 문제점 |
|------|------|--------|
| **XREAD** | 단순 읽기, last_id 메모리 저장 | Pod 재시작 시 last_id 유실, 중복 소비 |
| **XREADGROUP** | Consumer Group, ACK 기반 | ✅ 장애 복구, 분산 소비, 정확히 한 번 처리 |

### 3.2 Consumer Loop 구현

```python
# domains/event-router/core/consumer.py
async def start_consumer_loop(
    redis_client: aioredis.Redis,
    processor: EventProcessor,
    settings: Settings,
) -> None:
    """4개 shard를 Consumer Group으로 소비"""
    streams = {
        f"{settings.stream_prefix}:{i}": ">"  # ">" = 새 메시지만
        for i in range(settings.shard_count)
    }

    while True:
        try:
            # XREADGROUP: 블로킹 읽기
            results = await redis_client.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams=streams,
                count=settings.xread_count,
                block=settings.xread_block_ms,
            )

            for stream_name, messages in results:
                for msg_id, fields in messages:
                    # 이벤트 처리
                    success = await processor.process_event(fields)
                    if success:
                        # ACK: 처리 완료
                        await redis_client.xack(
                            stream_name,
                            settings.consumer_group,
                            msg_id,
                        )
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            await asyncio.sleep(1)
```

### 3.3 Pending Message Reclaimer

Consumer가 크래시되면 메시지가 Pending 상태로 남습니다. `XAUTOCLAIM`으로 복구합니다.

```python
# domains/event-router/core/reclaimer.py
async def start_reclaimer_loop(
    redis_client: aioredis.Redis,
    processor: EventProcessor,
    settings: Settings,
) -> None:
    """Pending 메시지 주기적 재처리"""
    while True:
        await asyncio.sleep(settings.reclaim_interval_seconds)

        for shard in range(settings.shard_count):
            stream_key = f"{settings.stream_prefix}:{shard}"
            try:
                # XAUTOCLAIM: min_idle_time 이상 Pending된 메시지 가져오기
                _, messages, _ = await redis_client.xautoclaim(
                    name=stream_key,
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    min_idle_time=settings.reclaim_min_idle_ms,
                    start_id="0-0",
                    count=settings.batch_size,
                )

                for msg_id, fields in messages:
                    if fields:
                        success = await processor.process_event(fields)
                        if success:
                            await redis_client.xack(
                                stream_key,
                                settings.consumer_group,
                                msg_id,
                            )
            except Exception as e:
                logger.error(f"Reclaimer error for shard {shard}: {e}")
```

---

## 4. 멱등성 보장: Lua Script

### 4.1 문제: 중복 발행 가능성

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 중복 발행 시나리오                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Event Router가 이벤트 처리 중 크래시                                │
│  2. XACK 전에 종료됨                                                    │
│  3. 다른 Consumer가 같은 이벤트를 다시 처리                              │
│  4. 결과: 같은 이벤트가 2번 Pub/Sub로 발행됨                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 해결: Atomic Lua Script

```lua
-- domains/event-router/core/processor.py
UPDATE_STATE_SCRIPT = """
local state_key = KEYS[1]      -- scan:state:{job_id}
local publish_key = KEYS[2]    -- router:published:{job_id}:{seq}

local new_seq = tonumber(ARGV[1])
local state_json = ARGV[2]
local state_ttl = tonumber(ARGV[3])
local publish_ttl = tonumber(ARGV[4])

-- 이미 발행했는지 체크
if redis.call('EXISTS', publish_key) == 1 then
    return 0  -- 이미 처리됨, 스킵
end

-- 현재 state 확인
local current_state = redis.call('GET', state_key)
if current_state then
    local current = cjson.decode(current_state)
    local current_seq = tonumber(current.seq or 0)
    -- 더 오래된 이벤트면 스킵
    if new_seq <= current_seq then
        return 0
    end
end

-- State 업데이트
redis.call('SETEX', state_key, state_ttl, state_json)

-- 발행 마킹 (TTL: 2시간)
redis.call('SETEX', publish_key, publish_ttl, '1')

return 1  -- 새로 처리됨
"""
```

### 4.3 처리 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 멱등성 보장 처리 흐름                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Lua Script 실행 (Streams Redis)                                    │
│     ├── EXISTS router:published:{job_id}:{seq}                         │
│     │   └── 있으면 → return 0 (스킵)                                   │
│     ├── GET scan:state:{job_id}                                        │
│     │   └── 현재 seq >= 새 seq → return 0 (스킵)                       │
│     ├── SETEX scan:state:{job_id} (상태 저장)                          │
│     └── SETEX router:published:{job_id}:{seq} (발행 마킹)              │
│                                                                         │
│  2. Script 결과 = 1이면                                                 │
│     └── PUBLISH sse:events:{job_id} (Pub/Sub Redis)                    │
│                                                                         │
│  3. XACK (Streams Redis)                                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 배포 아키텍처

### 5.1 전용 노드 프로비저닝

Event Router와 Redis Pub/Sub를 위해 별도 노드를 프로비저닝했습니다.

```hcl
# terraform/main.tf
module "event_router" {
  source        = "./modules/ec2"
  instance_name = "k8s-event-router"
  instance_type = "t3.small"  # 2GB
  # ...
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-event-router"
    kubelet_extra_args = "--node-labels=domain=event-router --register-with-taints=domain=event-router:NoSchedule"
  })
}

module "redis_pubsub" {
  source        = "./modules/ec2"
  instance_name = "k8s-redis-pubsub"
  instance_type = "t3.small"  # 2GB
  # ...
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-redis-pubsub"
    kubelet_extra_args = "--node-labels=redis-cluster=pubsub --register-with-taints=domain=data:NoSchedule"
  })
}
```

### 5.2 Kubernetes 배포

```yaml
# workloads/domains/event-router/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: event-router
  namespace: event-router
spec:
  replicas: 1
  template:
    spec:
      nodeSelector:
        domain: event-router
      tolerations:
      - key: domain
        operator: Equal
        value: event-router
        effect: NoSchedule
      containers:
      - name: event-router
        image: docker.io/mng990/eco2:event-router-dev-latest
        env:
        - name: REDIS_STREAMS_URL
          value: redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
        - name: REDIS_PUBSUB_URL
          value: redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0
```

---

## 6. CI/CD 파이프라인 분리

### 6.1 문제: 이미지 태그 불일치

기존 `ci-services.yml`에서 API 서비스는 `-api` suffix가 붙었습니다:
- `auth` → `auth-api-dev-latest`
- `event-router` → `event-router-api-dev-latest` ❌

하지만 Kustomization에서는:
- `newTag: event-router-dev-latest` ✅

**결과**: `ImagePullBackOff` - 이미지를 찾을 수 없음

### 6.2 해결: SSE 컴포넌트 전용 CI 분리

```yaml
# .github/workflows/ci-sse-components.yml
name: CI SSE Components

on:
  push:
    paths:
      - "domains/sse-gateway/**"
      - "domains/event-router/**"
      - "domains/_shared/events/**"
      # ...

jobs:
  build-push:
    steps:
      - name: Prepare image tags
        run: |
          # SSE 컴포넌트는 -api suffix 없이 빌드
          COMPONENT_SLUG="${COMPONENT}"  # event-router → event-router
          DEV_LATEST_TAG="${COMPONENT_SLUG}-dev-latest"
```

---

## 7. 트러블슈팅: KEDA ScaledObject Degraded

### 7.1 증상

```bash
$ kubectl get scaledobject -n event-router
NAME                        SCALETARGETKIND   READY   ACTIVE   AGE
event-router-scaledobject   Deployment        False   False    1h
```

### 7.2 원인 1: Prometheus 주소 오류

```bash
# KEDA 로그
ERROR  prometheus_scaler  error executing prometheus query
  error: dial tcp: lookup prometheus-server.monitoring.svc.cluster.local: no such host
```

**해결**: Prometheus 서비스 주소 수정

```yaml
# Before
serverAddress: http://prometheus-server.monitoring.svc.cluster.local:80

# After
serverAddress: http://kube-prometheus-stack-prometheus.prometheus.svc.cluster.local:9090
```

### 7.3 원인 2: NetworkPolicy Egress 누락

```bash
# KEDA 로그
ERROR  prometheus_scaler  error executing prometheus query
  error: context deadline exceeded (Client.Timeout exceeded)
```

**분석**: KEDA → Prometheus 네트워크 연결이 NetworkPolicy에 의해 차단됨

```yaml
# workloads/network-policies/base/allow-keda-egress.yaml
# Before: Prometheus egress 규칙 없음

# After: 추가
- to:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: prometheus
  ports:
  - protocol: TCP
    port: 9090  # Prometheus API
```

### 7.4 결과

```bash
$ kubectl get scaledobject -n event-router -o jsonpath='{.items[0].status.conditions}'
[
  {"type": "Ready", "status": "True", "reason": "ScaledObjectReady"},  # ✅
  {"type": "Active", "status": "False", "reason": "ScalerNotActive"}   # 정상 (threshold 미만)
]
```

---

## 8. 현재 클러스터 상태

```
┌─────────────────────────────────────────────────────────────────────────┐
│ SSE HA Architecture - 노드 배치                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  k8s-redis-streams (t3.small)                                          │
│  └── rfr-streams-redis (3 replicas + 3 sentinels)                      │
│      ├── Redis Streams: scan:events:{0-3}                              │
│      └── State KV: scan:state:{job_id}                                 │
│                                                                         │
│  k8s-redis-pubsub (t3.small)                                           │
│  └── rfr-pubsub-redis (3 replicas + 3 sentinels)                       │
│      └── Pub/Sub: sse:events:{job_id}                                  │
│                                                                         │
│  k8s-event-router (t3.small)                                           │
│  └── event-router (1 replica, KEDA managed)                            │
│      └── Consumer Group: eventrouter                                   │
│                                                                         │
│  k8s-sse-gateway (t3.small)                                            │
│  └── sse-gateway (1-3 replicas, KEDA managed)                          │
│      └── Pub/Sub SUBSCRIBE + State 복구                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 9. 실측 로그

### 9.1 Event Router Startup

```log
INFO:     Started server process [1]
INFO:     Waiting for application startup.
2025-12-27 11:11:45,307 INFO main: event_router_starting
2025-12-27 11:11:45,332 INFO core.consumer: consumer_group_created
2025-12-27 11:11:45,334 INFO core.consumer: consumer_group_created
2025-12-27 11:11:45,336 INFO core.consumer: consumer_group_created
2025-12-27 11:11:45,338 INFO core.consumer: consumer_group_created
2025-12-27 11:11:45,338 INFO main: event_router_started
2025-12-27 11:11:45,338 INFO core.consumer: consumer_started
2025-12-27 11:11:45,338 INFO core.reclaimer: reclaimer_started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**확인 사항**:
- ✅ Consumer Group 4개 shard 모두 생성 (`consumer_group_created` x4)
- ✅ Consumer 루프 시작 (`consumer_started`)
- ✅ Reclaimer 루프 시작 (`reclaimer_started`)

### 9.2 SSE-Gateway Startup

```log
INFO:     Started server process [1]
INFO:     Waiting for application startup.
2025-12-27 11:28:02,032 - main - INFO - sse_gateway_starting
2025-12-27 11:28:02,296 - core.broadcast_manager - INFO - broadcast_manager_redis_connected
2025-12-27 11:28:02,296 - core.broadcast_manager - INFO - broadcast_manager_initialized
2025-12-27 11:28:02,296 - main - INFO - sse_gateway_started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**확인 사항**:
- ✅ Redis 연결 성공 (`broadcast_manager_redis_connected`)
- ✅ BroadcastManager 초기화 완료 (`broadcast_manager_initialized`)

### 9.3 Pod 배치 현황

```bash
$ kubectl get pods -n event-router -o wide
NAME                            READY   STATUS    RESTARTS   AGE   IP              NODE
event-router-6c7c68bbff-hpshk   1/1     Running   0          13m   192.168.202.5   k8s-event-router

$ kubectl get pods -n sse-consumer -o wide
NAME                           READY   STATUS    RESTARTS   AGE   IP               NODE
sse-gateway-5dfc8f8ddb-79j4j   2/2     Running   0          85m   192.168.25.160   k8s-sse-gateway

$ kubectl get pods -n redis -l app=pubsub-redis -o wide
NAME                                READY   STATUS    RESTARTS   AGE    IP               NODE
rfr-pubsub-redis-0                  3/3     Running   0          117m   192.168.236.3    k8s-redis-pubsub
rfr-pubsub-redis-1                  3/3     Running   0          117m   192.168.236.6    k8s-redis-pubsub
rfr-pubsub-redis-2                  3/3     Running   0          117m   192.168.236.7    k8s-redis-pubsub
rfs-pubsub-redis-668574d5c7-kdxws   2/2     Running   0          105m   192.168.236.11   k8s-redis-pubsub
rfs-pubsub-redis-668574d5c7-lxcbl   2/2     Running   0          106m   192.168.236.10   k8s-redis-pubsub
rfs-pubsub-redis-668574d5c7-pc6tn   2/2     Running   0          107m   192.168.236.9    k8s-redis-pubsub
```

**노드별 배치**:
- `k8s-event-router`: Event Router Pod (nodeSelector + toleration)
- `k8s-sse-gateway`: SSE-Gateway Pod
- `k8s-redis-pubsub`: Redis Pub/Sub 클러스터 (3 masters + 3 sentinels)

### 9.4 KEDA ScaledObject 상태

```bash
$ kubectl get scaledobject -n event-router -o jsonpath='{.items[0].status.conditions}'
[
  {"type": "Ready", "status": "True", "reason": "ScaledObjectReady"},
  {"type": "Active", "status": "False", "reason": "ScalerNotActive"}
]
```

- ✅ `Ready: True` - Prometheus 연결 성공
- ℹ️ `Active: False` - Pending 메시지가 threshold(100) 미만이라 스케일업 조건 아님 (정상)

---

## 10. 결론

| 단계 | 내용 | 결과 |
|------|------|------|
| **Fan-out 분리** | Event Router 별도 컴포넌트로 구현 | ✅ SSE Gateway Stateless화 |
| **2-Redis 분리** | Streams(내구성) + Pub/Sub(실시간) | ✅ 역할별 장애 격리 |
| **Consumer Group** | XREADGROUP + XAUTOCLAIM | ✅ 정확히 한 번 처리, 장애 복구 |
| **멱등성 보장** | Lua Script로 중복 발행 방지 | ✅ seq 기반 상태 업데이트 |
| **CI/CD 분리** | ci-sse-components.yml | ✅ 이미지 태그 정합성 |
| **NetworkPolicy** | KEDA → Prometheus egress 허용 | ✅ ScaledObject Ready |

다음 포스팅에서는 SSE Gateway의 Pub/Sub 구독 구현과 E2E 테스트를 기록할 예정입니다.

---

## 참고 자료

- [Redis Streams Consumer Groups](https://redis.io/docs/data-types/streams-tutorial/#consumer-groups)
- [KEDA Prometheus Scaler](https://keda.sh/docs/scalers/prometheus/)
- [이전 포스팅: Fan-out Layer 설계](https://rooftopsnow.tistory.com/101)

