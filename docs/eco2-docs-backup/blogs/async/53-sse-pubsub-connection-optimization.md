# SSE Pub/Sub 연결 최적화: Master Service 분리와 Shard 기반 구독

> 이전 글: [Event Router 코드 분석](38-event-router-implementation.md)

## 개요

Redis Pub/Sub 기반 SSE HA 아키텍처에서 **이벤트 누락 문제**가 발생했다. Event Router가 이벤트를 정상 발행했지만 SSE Gateway가 수신하지 못하는 현상이었다. 원인 분석 결과 **Headless Service의 DNS round-robin**으로 인해 Pub/Sub publisher와 subscriber가 서로 다른 Redis replica에 연결되는 문제였다.

이 글에서는 문제 분석, 해결책, 그리고 추가 최적화(Shard 기반 Pub/Sub)를 다룬다.

---

## 1. 관측된 문제

### 1.1 증상

```bash
# Chat API에서 메시지 전송
curl -X POST "https://api.dev.growbin.app/api/v1/chat/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message": "오늘 날씨 어때?"}'

# SSE 스트림 연결
curl -N "https://api.dev.growbin.app/api/v1/chat/stream?job_id=$JOB_ID"
```

**예상 결과:**
```
event: intent_classified
event: weather_context
event: answer_start
event: answer_token (streaming...)
event: answer_complete
event: done
```

**실제 결과:**
```
event: intent_classified
(keepalive...)
(keepalive...)
(timeout)
```

→ **첫 이벤트 이후 모든 이벤트 누락**

### 1.2 추가 관측

- Redis Streams에는 모든 이벤트가 정상 저장됨
- Event Router 로그에서 `PUBLISH` 성공 확인
- SSE Gateway 로그에서 `Received: None` (메시지 없음)

---

## 2. 디버깅 과정

### 2.1 컴포넌트별 Pub/Sub 테스트

```bash
# Event Router Pod에서 테스트
kubectl exec -it event-router-xxx -n event-router -- python3 -c "
import redis
r = redis.Redis.from_url('redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0')
pubsub = r.pubsub()
pubsub.subscribe('test:channel')
r.publish('test:channel', 'hello')
msg = pubsub.get_message(timeout=2)
print(f'Received: {msg}')
"
# 결과: Received: {'type': 'message', 'data': b'hello', ...}
```

```bash
# SSE Gateway Pod에서 테스트
kubectl exec -it sse-gateway-xxx -n sse-consumer -- python3 -c "
import redis
r = redis.Redis.from_url('redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0')
pubsub = r.pubsub()
pubsub.subscribe('test:channel')
r.publish('test:channel', 'hello')
msg = pubsub.get_message(timeout=2)
print(f'Received: {msg}')
"
# 결과: Received: None
```

→ **같은 Pod 내에서는 수신, 다른 Pod에서는 수신 불가**

### 2.2 DNS 해석 확인

```bash
# Event Router Pod
kubectl exec -it event-router-xxx -n event-router -- \
  python3 -c "import socket; print(socket.gethostbyname('rfr-pubsub-redis.redis.svc.cluster.local'))"
# 결과: 192.168.236.6

# SSE Gateway Pod
kubectl exec -it sse-gateway-xxx -n sse-consumer -- \
  python3 -c "import socket; print(socket.gethostbyname('rfr-pubsub-redis.redis.svc.cluster.local'))"
# 결과: 192.168.236.7
```

→ **다른 IP 반환 (DNS round-robin)**

### 2.3 Redis Pod 확인

```bash
kubectl get pods -n redis -o wide | grep pubsub
# rfr-pubsub-redis-0   192.168.236.3   (master)
# rfr-pubsub-redis-1   192.168.236.6   (replica)
# rfr-pubsub-redis-2   192.168.236.7   (replica)
```

---

## 3. Root Cause

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Root Cause: Headless Service + Pub/Sub               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Headless Service (rfr-pubsub-redis)                                  │   │
│  │                                                                      │   │
│  │  DNS Query → [192.168.236.3, 192.168.236.6, 192.168.236.7]          │   │
│  │              (Round-robin 순서)                                      │   │
│  │                                                                      │   │
│  │  ⚠️ 문제: 클라이언트마다 다른 replica에 연결될 수 있음               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Redis Pub/Sub 특성                                                   │   │
│  │                                                                      │   │
│  │  • Pub/Sub 메시지는 replica 간에 복제되지 않음                       │   │
│  │  • PUBLISH → Master에서만 subscriber에게 전달                        │   │
│  │  • Replica에 PUBLISH → 해당 replica의 subscriber에게만 전달          │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐   │   │
│  │  │     Master                    Replica-1        Replica-2      │   │   │
│  │  │    ┌───────┐                 ┌───────┐        ┌───────┐      │   │   │
│  │  │    │Pub/Sub│ ─── 복제 ───▶  │  KV   │        │  KV   │      │   │   │
│  │  │    │  KV   │   (KV만!)      │       │        │       │      │   │   │
│  │  │    └───────┘                 └───────┘        └───────┘      │   │   │
│  │  │                                                               │   │   │
│  │  │  ❌ Pub/Sub 메시지는 복제 대상이 아님!                         │   │   │
│  │  └───────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 발생 시나리오                                                        │   │
│  │                                                                      │   │
│  │  Event Router          rfr-pubsub-redis           SSE Gateway       │   │
│  │  ┌──────────┐          (Headless)                 ┌──────────┐      │   │
│  │  │          │ ──DNS──▶ 192.168.236.6              │          │      │   │
│  │  │ PUBLISH  │          (Replica-1)                │SUBSCRIBE │      │   │
│  │  │          │                                     │          │      │   │
│  │  └──────────┘                                     └──────────┘      │   │
│  │                          ▲                             │            │   │
│  │                          │                             │            │   │
│  │                    다른 replica!              ──DNS──▶ 192.168.236.7│   │
│  │                                                       (Replica-2)   │   │
│  │                                                                      │   │
│  │  → Replica-1에 PUBLISH, Replica-2에 SUBSCRIBE                       │   │
│  │  → 메시지 전달 불가!                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**핵심 문제:**
1. `rfr-pubsub-redis`는 Headless Service로 모든 replica IP를 반환
2. Redis Pub/Sub는 replica 간 복제되지 않음
3. Publisher와 Subscriber가 다른 replica에 연결되면 메시지 누락

---

## 4. 해결: Master-only Service 생성

### 4.1 Spotahome Redis Operator 라벨 확인

```bash
kubectl get pods -n redis -l app.kubernetes.io/name=pubsub-redis --show-labels
# rfr-pubsub-redis-0   redisfailovers-role=master
# rfr-pubsub-redis-1   redisfailovers-role=slave
# rfr-pubsub-redis-2   redisfailovers-role=slave
```

### 4.2 Master-only Service 생성

```yaml
# workloads/redis/base/pubsub-redis-master-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: pubsub-redis-master
  namespace: redis
  labels:
    app: pubsub-redis
    tier: data
    purpose: pubsub-master
  annotations:
    description: |
      Redis Pub/Sub Master-only Service.
      Pub/Sub는 replica 간 복제되지 않으므로 모든 클라이언트가
      동일한 master에 연결해야 함.
spec:
  type: ClusterIP
  ports:
  - name: redis
    port: 6379
    targetPort: 6379
    protocol: TCP
  selector:
    app.kubernetes.io/name: pubsub-redis
    app.kubernetes.io/component: redis
    redisfailovers-role: master  # ← Master만 선택
```

### 4.3 서비스 비교

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Service 비교                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  서비스 이름                   │ 타입       │ 대상        │ 용도            │
│  ────────────────────────────┼───────────┼────────────┼───────────────── │
│  rfr-pubsub-redis            │ Headless  │ 모든 Pod    │ StatefulSet용    │
│  (사용 금지!)                 │           │ (RR)       │ (내부용)         │
│  ────────────────────────────┼───────────┼────────────┼───────────────── │
│  rfs-pubsub-redis            │ ClusterIP │ Sentinel   │ Sentinel 접속    │
│                              │ :26379    │            │                  │
│  ────────────────────────────┼───────────┼────────────┼───────────────── │
│  pubsub-redis-master         │ ClusterIP │ Master만   │ Pub/Sub 접속     │
│  (권장!)                     │ :6379     │            │ (모든 클라이언트)│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Deployment 환경변수 수정

```yaml
# 모든 Pub/Sub 사용 컴포넌트에 적용
env:
- name: REDIS_PUBSUB_URL
  # Before: redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0
  value: redis://pubsub-redis-master.redis.svc.cluster.local:6379/0
```

**수정 대상:**
- `workloads/domains/sse-gateway/base/deployment.yaml`
- `workloads/domains/sse-gateway/base/deployment-canary.yaml`
- `workloads/domains/event-router/base/deployment.yaml`
- `workloads/domains/chat/base/configmap.yaml`

### 4.5 적용 및 검증

```bash
# 적용
kubectl apply -f workloads/redis/base/pubsub-redis-master-service.yaml
kubectl rollout restart deployment -n event-router event-router
kubectl rollout restart deployment -n sse-consumer sse-gateway

# 검증
kubectl exec -it sse-gateway-xxx -n sse-consumer -- python3 -c "
import socket
print(socket.gethostbyname('pubsub-redis-master.redis.svc.cluster.local'))
"
# 192.168.236.3 (항상 Master IP)
```

---

## 5. 정리

### 해결된 문제

| 문제 | 원인 | 해결책 |
|------|------|--------|
| Pub/Sub 메시지 누락 | Headless Service로 다른 replica 연결 | Master-only Service 생성 |

### 수정된 파일

- `workloads/redis/base/pubsub-redis-master-service.yaml` (신규)
- `workloads/redis/base/pubsub-redis-failover.yaml` (주석 추가)
- `workloads/domains/sse-gateway/base/deployment.yaml`
- `workloads/domains/sse-gateway/base/deployment-canary.yaml`
- `workloads/domains/event-router/base/deployment.yaml`
- `workloads/domains/chat/base/configmap.yaml`

---

## 다음 단계

> **[54-sse-pubsub-shard-optimization.md](54-sse-pubsub-shard-optimization.md)**: Shard 기반 Pub/Sub 연결 최적화
>
> 연결 수를 O(N)에서 O(4)로 줄이는 추가 최적화를 다룹니다.

---

## 참고

- [Redis Pub/Sub Documentation](https://redis.io/docs/manual/pubsub/)
- [Spotahome Redis Operator](https://github.com/spotahome/redis-operator)
- [34-sse-HA-architecture.md](34-sse-HA-architecture.md)
