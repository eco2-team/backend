# RabbitMQ Quorum Queue → Classic Queue 마이그레이션

> **Date**: 2024-12-24  
> **Author**: Backend Team  
> **Status**: Resolved

## 환경 정보

| Component | Version |
|-----------|---------|
| RabbitMQ | 4.0.9 |
| Celery | 5.4.0 |
| kombu | 5.6.1 |
| amqp | 5.3.1 |
| Python | 3.11.14 |
| RabbitMQ Messaging Topology Operator | latest (rabbitmqoperator/messaging-topology-operator) |
| RabbitMQ Cluster Operator | latest (rabbitmqoperator/cluster-operator) |
| Kubernetes | v1.28.15 |

## 문제 상황

### 증상

Celery 워커들이 RabbitMQ에 연결 후 즉시 연결이 끊기고 무한 재시작하는 현상 발생:

```
[2025-12-24 00:03:34,585: INFO/MainProcess] Connected to amqp://admin:**@eco2-rabbitmq.rabbitmq.svc.cluster.local:5672/eco2
[2025-12-24 00:03:34,644: WARNING/MainProcess] consumer: Connection to broker lost. Trying to re-establish the connection...
```

### 에러 메시지

```python
amqp.exceptions.AMQPNotImplementedError: Basic.consume: (540) NOT_IMPLEMENTED - queue 'scan.vision' in vhost 'eco2' does not support global qos
```

### 영향 범위

- scan-worker
- character-worker
- character-match-worker
- my-worker

모든 Celery 워커가 정상 작동하지 않음.

## 근본 원인 분석

### 1. Quorum Queue와 Global QoS

RabbitMQ의 **Quorum Queue**는 고가용성과 내구성을 위한 큐 타입이지만, **Global QoS**를 지원하지 않습니다.

```
# Quorum Queue의 제한사항
- global QoS 미지원 (per-consumer QoS만 지원)
- Non-durable subscribers 미지원
- Queue exclusivity 미지원
- Message priorities 미지원
```

### 2. Celery/kombu의 Global QoS 사용

Celery(kombu)는 기본적으로 `basic_qos(global=True)`를 호출합니다:

```python
# kombu/transport/pyamqp.py
def basic_qos(self, prefetch_size=0, prefetch_count=0, apply_global=True):
    ...
```

### 3. 시도했지만 실패한 해결책

#### 시도 1: `broker_transport_options: {"global_qos": False}`

```python
# domains/_shared/celery/config.py
"broker_transport_options": {
    "global_qos": False,
},
```

**결과**: 실패. `celery_app.config_from_object(dict)` 방식에서는 `broker_transport_options`가 제대로 적용되지 않음.

#### 시도 2: `celery_app.conf.update(dict)` 방식으로 변경

```python
# 변경 전
celery_app.config_from_object(settings.get_celery_config())

# 변경 후  
celery_app.conf.update(settings.get_celery_config())
```

**결과**: 설정은 적용되었으나 여전히 global QoS 에러 발생.

```python
# Pod 내부에서 확인
>>> app.conf.broker_transport_options
{'global_qos': False, 'confirm_publish': True}
```

#### 시도 3: `--without-mingle --without-gossip` 옵션 추가

```yaml
# deployment.yaml
args:
  - --without-mingle
  - --without-gossip
```

**결과**: 실패. mingle/gossip은 워커 간 통신에 사용되며, global QoS 호출 경로와 무관.

#### 시도 4: `worker_prefetch_multiplier = 0`

```python
"worker_prefetch_multiplier": 0,  # QoS 비활성화 시도
```

**결과**: 미시도 (Classic Queue 전환으로 해결됨).

### 4. 왜 `global_qos: False`가 작동하지 않았나

kombu/Celery의 QoS 호출 경로를 분석한 결과:

1. `broker_transport_options`의 `global_qos` 설정은 **Connection 레벨**에서 적용됨
2. 하지만 실제 `basic_qos()` 호출은 **Channel 레벨**에서 발생
3. kombu 5.6.1에서 이 설정이 Channel까지 전파되지 않는 버그 또는 설계 문제 존재

## 해결책: Classic Queue로 전환

### 선택 이유

| Queue Type | Global QoS | 내구성 | 복제 | Celery 호환성 |
|------------|-----------|--------|------|---------------|
| Classic | ✅ 지원 | 단일 노드 | ❌ | ✅ 완벽 |
| Quorum | ❌ 미지원 | Raft 기반 | ✅ | ⚠️ 제한적 |
| Stream | ❌ 미지원 | Log 기반 | ✅ | ❌ |

**Celery + RabbitMQ 조합에서는 Classic Queue가 가장 호환성이 좋음.**

### 변경 내용

#### 1. RabbitMQ Topology CR (queues.yaml)

```yaml
# 변경 전
spec:
  name: scan.vision
  type: quorum  # ❌
  arguments:
    x-delivery-limit: 3  # Quorum 전용 옵션

# 변경 후
spec:
  name: scan.vision
  type: classic  # ✅
  arguments:
    # x-delivery-limit 제거 (Classic 미지원)
```

#### 2. Celery Config (config.py)

```python
# 변경 전
Queue(
    "scan.vision",
    queue_arguments={
        "x-queue-type": "quorum",  # ❌
        "x-delivery-limit": 3,      # ❌
        ...
    },
)

# 변경 후
Queue(
    "scan.vision",
    queue_arguments={
        # x-queue-type 생략 (classic이 기본값)
        # x-delivery-limit 제거
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.scan.vision",
        "x-message-ttl": 3600000,
    },
)
```

#### 3. Worker Deployment

```yaml
# 변경 전
args:
  - --without-mingle   # ❌ 제거
  - --without-gossip   # ❌ 제거

# 변경 후
args:
  # mingle/gossip 옵션 제거 (Classic에서는 불필요)
```

#### 4. Celery broker_transport_options

```python
# 변경 전
"broker_transport_options": {
    "global_qos": False,  # ❌ 제거 (Classic은 global QoS 지원)
    "confirm_publish": True,
},

# 변경 후
"broker_transport_options": {
    "confirm_publish": True,
},
```

### 마이그레이션 절차

1. **모든 워커 스케일 다운**
   ```bash
   kubectl scale deployment/scan-worker -n scan --replicas=0
   kubectl scale deployment/character-worker -n character --replicas=0
   kubectl scale deployment/character-match-worker -n character --replicas=0
   kubectl scale deployment/my-worker -n my --replicas=0
   ```

2. **기존 Quorum 큐 삭제**
   ```bash
   kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
     rabbitmqctl delete_queue scan.vision -p eco2
   # ... 모든 큐에 대해 반복
   ```

3. **Queue CR 삭제** (Topology Operator가 재생성하지 못하도록)
   ```bash
   kubectl delete queue --all -n rabbitmq
   ```

4. **Git push & ArgoCD Sync**
   ```bash
   git push origin develop
   kubectl -n argocd patch application dev-rabbitmq-topology \
     --type merge -p '{"operation":{"sync":{"prune":true}}}'
   ```

5. **Classic 타입으로 Queue CR 재생성 확인**
   ```bash
   kubectl get queue -n rabbitmq -o custom-columns='NAME:.metadata.name,TYPE:.spec.type'
   ```

6. **RabbitMQ에서 Classic 큐 생성 확인**
   ```bash
   kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
     rabbitmqctl list_queues -p eco2 name type
   ```

7. **워커 스케일 업**
   ```bash
   kubectl scale deployment/scan-worker -n scan --replicas=1
   # ... 모든 워커에 대해 반복
   ```

### 주의사항: Webhook Validation

Queue CR의 `type` 필드는 immutable입니다:

```
admission webhook "vqueue.kb.io" denied the request: 
[spec.type: Invalid value: "classic": queue type cannot be updated]
```

따라서 **Queue CR 삭제 → 재생성** 절차가 필수입니다.

## 결과

### 성공 로그

```
[2025-12-24 00:12:55,171: INFO/MainProcess] celery@scan-worker-xxx ready.
```

### 최종 큐 상태

```
name              type
scan.vision       classic
scan.rule         classic
scan.answer       classic
scan.reward       classic
character.match   classic
character.reward  classic
my.reward         classic
celery            classic
```

## 교훈 및 권장사항

### 1. Queue Type 선택 가이드

| 사용 사례 | 권장 Queue Type |
|----------|----------------|
| Celery 태스크 큐 | **Classic** |
| 이벤트 스트리밍 (Kafka 대체) | Stream |
| 금융/트랜잭션 (메시지 손실 불가) | Quorum |
| 일반 Pub/Sub | Classic |

### 2. Celery + Quorum Queue를 사용해야 하는 경우

Celery 5.5.0+에서 개선된 Quorum Queue 지원이 있지만, 여전히 제한사항 존재:
- `task_acks_late = True` 필수
- `worker_prefetch_multiplier = 1` 권장
- ETA/countdown 태스크 주의

### 3. 버전 호환성 매트릭스

| Celery | kombu | RabbitMQ | Quorum Queue |
|--------|-------|----------|--------------|
| < 5.3 | < 5.3 | any | ❌ 지원 안 함 |
| 5.3+ | 5.3+ | 3.10+ | ⚠️ 제한적 |
| 5.5+ | 5.6+ | 4.0+ | ⚠️ 개선됨 (여전히 global QoS 이슈) |

### 4. 모니터링 권장 사항

```bash
# 큐 타입 확인
rabbitmqctl list_queues name type -p eco2

# Celery 워커 상태
celery -A app inspect ping

# 연결 상태
rabbitmqctl list_connections
```

## 관련 문서

- [RabbitMQ Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Celery + RabbitMQ Configuration](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/rabbitmq.html)
- [kombu Transport Options](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.transport.pyamqp.html)

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2024-12-24 | 문서 작성, Quorum → Classic 마이그레이션 완료 |

