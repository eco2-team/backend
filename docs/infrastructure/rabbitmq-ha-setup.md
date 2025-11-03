# 🐰 RabbitMQ HA 구성

> **Tier 3: Message Queue Middleware Layer**  
> **날짜**: 2025-10-31  
> **배포**: Storage Node (t3.large, 8GB)

## 📋 목차

1. [RabbitMQ 역할 (Tier 3)](#rabbitmq-역할-tier-3)
2. [HA Cluster 구성](#ha-cluster-구성)
3. [Queue 설정](#queue-설정)
4. [Kubernetes 배포](#kubernetes-배포)
5. [모니터링](#모니터링)

---

## 🎯 RabbitMQ 역할 (Tier 3)

### Tier 3 Message Queue Middleware

```
RabbitMQ 책임:
✅ Task 전달 (Producer → Consumer)
✅ Message Routing (라우팅 키 기반)
✅ Priority Management (우선순위 큐)
✅ Delivery Guarantee (메시지 보장)
✅ Dead Letter Handling (실패 처리)

❌ State Storage (상태 저장 - Redis가 담당)
❌ Progress Tracking (진행률 - Redis가 담당)

관심사:
└─ "메시지를 어떻게 안전하게 전달할 것인가?"

특성:
✅ Consume 후 메시지 삭제 (일회성)
✅ Exactly Once Delivery
✅ HA Cluster (3-node)
```

---

## 🏗️ HA Cluster 구성

### 3-Node Quorum Cluster

```
RabbitMQ HA 구성:
├─ rabbitmq-0 (Leader)
├─ rabbitmq-1 (Follower)
└─ rabbitmq-2 (Follower)

Quorum Queues:
✅ 모든 노드에 복제
✅ Leader 다운 시 자동 선출
✅ 데이터 손실 없음
✅ Raft Consensus Algorithm
```

---

## 📦 Queue 설정

### 5개 Queue

```python
from kombu import Exchange, Queue

# Topic Exchange
tasks_exchange = Exchange("tasks", type="topic")
dlx_exchange = Exchange("dlx", type="direct")

# q.ai (AI Vision)
Queue(
    "q.ai",
    tasks_exchange,
    routing_key="ai.*",
    queue_arguments={
        "x-queue-type": "quorum",  # HA
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq",
        "x-message-ttl": 300_000,  # 5분
        "x-max-length": 5_000,
        "x-max-priority": 10,
    },
),

# q.batch (배치 작업)
Queue(
    "q.batch",
    tasks_exchange,
    routing_key="batch.*",
    queue_arguments={
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq",
        "x-message-ttl": 3_600_000,  # 1시간
        "x-max-length": 1_000,
    },
),

# q.api (외부 API)
Queue(
    "q.api",
    tasks_exchange,
    routing_key="api.*",
    queue_arguments={
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq",
        "x-message-ttl": 300_000,
        "x-max-length": 2_000,
    },
),

# q.sched (예약 작업)
Queue(
    "q.sched",
    tasks_exchange,
    routing_key="sched.*",
    queue_arguments={
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": "dlx",
        "x-message-ttl": 3_600_000,
        "x-max-length": 500,
    },
),

# q.dlq (Dead Letter Queue)
Queue("q.dlq", dlx_exchange, routing_key="dlq"),
```

---

## 🚀 Kubernetes 배포

### StatefulSet (HA Cluster)

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: rabbitmq
  namespace: messaging
spec:
  serviceName: rabbitmq
  replicas: 3
  selector:
    matchLabels:
      app: rabbitmq
      tier: middleware
  template:
    metadata:
      labels:
        app: rabbitmq
        tier: middleware
    spec:
      nodeSelector:
        workload: storage
      containers:
      - name: rabbitmq
        image: rabbitmq:3.12-management-alpine
        env:
        - name: RABBITMQ_DEFAULT_USER
          value: admin
        - name: RABBITMQ_DEFAULT_PASS
          valueFrom:
            secretKeyRef:
              name: rabbitmq-secret
              key: password
        - name: RABBITMQ_ERLANG_COOKIE
          value: "secret-cookie-change-me"
        - name: RABBITMQ_DEFAULT_VHOST
          value: "/"
        ports:
        - containerPort: 5672   # AMQP
          name: amqp
        - containerPort: 15672  # Management UI
          name: management
        volumeMounts:
        - name: data
          mountPath: /var/lib/rabbitmq
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 2Gi
        livenessProbe:
          exec:
            command:
            - rabbitmq-diagnostics
            - ping
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - rabbitmq-diagnostics
            - check_port_connectivity
          initialDelaySeconds: 20
          periodSeconds: 10
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 20Gi
      storageClassName: gp3

---
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq
  namespace: messaging
spec:
  selector:
    app: rabbitmq
  ports:
  - port: 5672
    targetPort: 5672
    name: amqp
  - port: 15672
    targetPort: 15672
    name: management
  type: ClusterIP

---
# Headless Service (Cluster 용)
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq-headless
  namespace: messaging
spec:
  selector:
    app: rabbitmq
  ports:
  - port: 5672
    name: amqp
  clusterIP: None
```

---

## 📊 모니터링

### Prometheus Metrics

```yaml
# ServiceMonitor
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: rabbitmq
  namespace: messaging
spec:
  selector:
    matchLabels:
      app: rabbitmq
  endpoints:
  - port: management
    path: /metrics
    interval: 30s
```

### 주요 메트릭

```
Queue 메트릭:
├─ rabbitmq_queue_messages{queue="q.ai"}
├─ rabbitmq_queue_messages_ready{queue="q.ai"}
├─ rabbitmq_queue_consumers{queue="q.ai"}
└─ rabbitmq_queue_messages{queue="q.dlq"}  # ⚠️ 증가 주의

Cluster 메트릭:
├─ rabbitmq_cluster_status
├─ rabbitmq_node_mem_used
└─ rabbitmq_fd_used

알람:
├─ q.dlq 길이 > 100 → Critical
├─ q.ai 길이 > 1,000 → Warning
├─ Cluster 노드 다운 → Critical
└─ 메모리 > 80% → Warning
```

---

## 🔧 운영 가이드

### Cluster 상태 확인

```bash
# Cluster 상태
kubectl exec -n messaging rabbitmq-0 -- rabbitmqctl cluster_status

# Queue 목록
kubectl exec -n messaging rabbitmq-0 -- rabbitmqctl list_queues name messages consumers

# Exchange 확인
kubectl exec -n messaging rabbitmq-0 -- rabbitmqctl list_exchanges

# Binding 확인
kubectl exec -n messaging rabbitmq-0 -- rabbitmqctl list_bindings
```

### Management UI

```bash
# Port Forward
kubectl port-forward -n messaging svc/rabbitmq 15672:15672

# 접속: http://localhost:15672
# Username: admin
# Password: (Secret에서 확인)

# 확인 사항:
✅ Cluster: 3 nodes
✅ Queues: 5개 (q.ai, q.batch, q.api, q.sched, q.dlq)
✅ Exchanges: tasks (topic), dlx (direct)
✅ Connections: Celery Workers
```

---

## 📚 참고 문서

- [RabbitMQ 공식 - Quorum Queues](https://www.rabbitmq.com/quorum-queues.html)
- [RabbitMQ 공식 - Clustering](https://www.rabbitmq.com/clustering.html)
- [Task Queue 설계](../architecture/task-queue-design.md)

---

**작성일**: 2025-10-31  
**Tier**: 3 (Message Queue Middleware)  
**노드**: Storage (공유)  
**메모리**: ~3GB (총 8GB 중)  
**역할**: Task 전달 (일회성), State 저장 안 함

