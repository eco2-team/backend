# Blacklist Relay Worker 설계 문서

## 1. 개요

`auth-api`에서 RabbitMQ 메시지 발행이 실패한 경우, Redis Outbox에 적재된 이벤트를 재발행하는 Relay Worker입니다.

### 목적

```
┌─────────────────────────────────────────────────────────────┐
│                    메시지 발행 신뢰성 향상                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  현재 아키텍처 (Best Effort):                               │
│  auth-api → RabbitMQ (실패 시 메시지 손실)                  │
│                                                             │
│  개선 아키텍처 (Outbox Pattern):                            │
│  auth-api → Redis Outbox (실패 시) → Relay → RabbitMQ      │
│                                                             │
│  기대 효과:                                                 │
│  - 메시지 손실 0% 목표 (at-least-once 보장)                 │
│  - ext-authz 로컬 캐시 일관성 향상                          │
│  - 블랙리스트 토큰이 계속 유효한 보안 취약점 해소           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처

### 2.1 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    Blacklist Event Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User Logout                                                │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────┐                                        │
│  │    auth-api     │                                        │
│  │  (blacklist_    │                                        │
│  │   publisher)    │                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  ┌────────────────────────────────┐                         │
│  │  RabbitMQ 발행 시도 (1차)      │                         │
│  └────────────────┬───────────────┘                         │
│                   │                                         │
│       ┌───────────┴───────────┐                             │
│       │                       │                             │
│       ▼ 성공 (~99%)           ▼ 실패 (~1%)                  │
│  ┌─────────────┐        ┌─────────────────┐                 │
│  │  RabbitMQ   │        │  Redis Outbox   │                 │
│  │ (blacklist. │        │ (outbox:        │                 │
│  │   events)   │        │   blacklist)    │                 │
│  └──────┬──────┘        └────────┬────────┘                 │
│         │                        │                          │
│         │                        ▼                          │
│         │               ┌─────────────────┐                 │
│         │               │  auth-relay     │ ◄── 1초마다 폴링│
│         │               │  (Relay Worker) │                 │
│         │               └────────┬────────┘                 │
│         │                        │                          │
│         │                        ▼ 재발행                   │
│         │               ┌─────────────────┐                 │
│         └──────────────►│  RabbitMQ       │                 │
│                         │ (blacklist.     │                 │
│                         │   events)       │                 │
│                         └────────┬────────┘                 │
│                                  │                          │
│                                  ▼                          │
│                         ┌─────────────────┐                 │
│                         │   ext-authz     │                 │
│                         │ (local cache)   │                 │
│                         └─────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Redis Keys

| Key | Type | 설명 | TTL |
|-----|------|------|-----|
| `outbox:blacklist` | List | 실패한 이벤트 (FIFO) | 영구 |
| `outbox:blacklist:dlq` | List | 재발행도 실패한 이벤트 | 영구 |

---

## 3. 폴더 구조

```
domains/auth/
├── tasks/                        # 신규 디렉토리
│   ├── __init__.py
│   └── blacklist_relay.py        # Outbox Relay Worker
├── Dockerfile.relay              # Relay 전용 이미지
├── requirements-relay.txt        # 최소 의존성
└── services/
    └── blacklist_publisher.py    # 기존 (Outbox 적재 로직 추가)

workloads/domains/auth-relay/
├── base/
│   ├── deployment.yaml
│   ├── configmap.yaml
│   └── kustomization.yaml
├── dev/
│   └── kustomization.yaml
└── prod/
    └── kustomization.yaml
```

---

## 4. 구현 상세

### 4.1 `domains/auth/tasks/__init__.py`

```python
"""Auth domain background tasks.

Blacklist Relay: Redis Outbox → RabbitMQ 재발행
"""
```

### 4.2 `domains/auth/tasks/blacklist_relay.py`

```python
"""Blacklist Outbox Relay Worker.

Redis Outbox에서 실패한 블랙리스트 이벤트를 RabbitMQ로 재발행.

Architecture:
    auth-api (logout)
        │
        ├── 1차 시도: RabbitMQ 직접 발행 (성공률 ~99%)
        │
        └── 실패 시: Redis Outbox에 적재 (LPUSH)
                │
                └── Relay Worker (이 모듈)
                        │
                        └── RPOP → RabbitMQ 재발행

Redis Keys:
    - outbox:blacklist        # List: 실패한 이벤트 (FIFO)
    - outbox:blacklist:dlq    # List: 재발행도 실패한 이벤트 (수동 처리)

Run:
    python -m domains.auth.tasks.blacklist_relay
"""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime

import pika
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("AUTH_REDIS_URL", "redis://localhost:6379/0")
AMQP_URL = os.getenv("AUTH_AMQP_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE_NAME = "blacklist.events"
OUTBOX_KEY = "outbox:blacklist"
DLQ_KEY = "outbox:blacklist:dlq"
POLL_INTERVAL = float(os.getenv("RELAY_POLL_INTERVAL", "1.0"))  # 초
BATCH_SIZE = int(os.getenv("RELAY_BATCH_SIZE", "10"))


class BlacklistRelay:
    """Redis Outbox → RabbitMQ Relay Worker."""

    def __init__(self):
        self._redis: Redis | None = None
        self._mq_connection: pika.BlockingConnection | None = None
        self._mq_channel: pika.channel.Channel | None = None
        self._shutdown = False

    async def start(self) -> None:
        """Worker 시작."""
        logger.info("Blacklist Relay starting...")

        # Redis 연결
        self._redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await self._redis.ping()
        logger.info("Redis connected", extra={"url": REDIS_URL[:20] + "..."})

        # RabbitMQ 연결
        self._connect_mq()

        # Graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Main loop
        await self._run()

    def _connect_mq(self) -> None:
        """RabbitMQ 연결."""
        params = pika.URLParameters(AMQP_URL)
        self._mq_connection = pika.BlockingConnection(params)
        self._mq_channel = self._mq_connection.channel()
        self._mq_channel.exchange_declare(
            exchange=EXCHANGE_NAME,
            exchange_type="fanout",
            durable=True,
        )
        logger.info("RabbitMQ connected", extra={"exchange": EXCHANGE_NAME})

    def _handle_shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutdown signal received")
        self._shutdown = True

    async def _run(self) -> None:
        """Main polling loop."""
        logger.info(
            "Relay loop started",
            extra={
                "poll_interval": POLL_INTERVAL,
                "batch_size": BATCH_SIZE,
            },
        )

        while not self._shutdown:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(POLL_INTERVAL)
            except Exception:
                logger.exception("Relay loop error")
                await asyncio.sleep(POLL_INTERVAL * 2)

        await self._cleanup()

    async def _process_batch(self) -> int:
        """Outbox에서 배치 처리."""
        processed = 0

        for _ in range(BATCH_SIZE):
            # RPOP: FIFO 순서 (LPUSH로 적재됨)
            event_json = await self._redis.rpop(OUTBOX_KEY)
            if not event_json:
                break

            try:
                event = json.loads(event_json)
                self._publish_to_mq(event)
                processed += 1
                logger.debug(
                    "Event relayed", extra={"jti": event.get("jti", "")[:8]}
                )
            except pika.exceptions.AMQPError:
                # MQ 실패 → 다시 Outbox에 (왼쪽에 재삽입)
                await self._redis.lpush(OUTBOX_KEY, event_json)
                logger.warning("MQ publish failed, re-queued")
                self._reconnect_mq()
                break
            except json.JSONDecodeError:
                # 파싱 불가 → DLQ
                await self._redis.lpush(DLQ_KEY, event_json)
                logger.error("Invalid JSON, moved to DLQ")
            except Exception:
                # 기타 오류 → DLQ
                await self._redis.lpush(DLQ_KEY, event_json)
                logger.exception("Unexpected error, moved to DLQ")

        return processed

    def _publish_to_mq(self, event: dict) -> None:
        """RabbitMQ로 발행."""
        body = json.dumps(event, ensure_ascii=False)
        self._mq_channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="",
            body=body.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )

    def _reconnect_mq(self) -> None:
        """RabbitMQ 재연결."""
        try:
            if self._mq_connection and not self._mq_connection.is_closed:
                self._mq_connection.close()
        except Exception:
            pass
        self._connect_mq()

    async def _cleanup(self) -> None:
        """리소스 정리."""
        if self._redis:
            await self._redis.close()
        if self._mq_connection and not self._mq_connection.is_closed:
            self._mq_connection.close()
        logger.info("Relay shutdown complete")


async def main():
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    relay = BlacklistRelay()
    await relay.start()


if __name__ == "__main__":
    asyncio.run(main())
```

### 4.3 `domains/auth/requirements-relay.txt`

```
# Blacklist Relay Worker - Minimal Dependencies
redis>=5.0.0
pika>=1.3.0
```

### 4.4 `domains/auth/Dockerfile.relay`

```dockerfile
# Blacklist Relay Worker
# 경량 이미지 (~50MB)

FROM python:3.11-slim

WORKDIR /app

# 최소 의존성만 설치
COPY domains/auth/requirements-relay.txt .
RUN pip install --no-cache-dir -r requirements-relay.txt

# 코드 복사
COPY domains/auth/tasks/ /app/domains/auth/tasks/

# 환경 변수 기본값
ENV PYTHONPATH=/app
ENV RELAY_POLL_INTERVAL=1.0
ENV RELAY_BATCH_SIZE=10

# Healthcheck (Redis ping)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import redis; redis.from_url('${AUTH_REDIS_URL}').ping()" || exit 1

# 실행
CMD ["python", "-m", "domains.auth.tasks.blacklist_relay"]
```

---

## 5. Kubernetes 매니페스트

### 5.1 `workloads/domains/auth-relay/base/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-relay
  namespace: auth
  labels:
    app: auth-relay
    tier: integration
    domain: auth
spec:
  replicas: 1
  selector:
    matchLabels:
      app: auth-relay
  template:
    metadata:
      labels:
        app: auth-relay
        tier: integration
        domain: auth
      annotations:
        sidecar.istio.io/inject: "false"  # 내부 통신만, Istio 불필요
    spec:
      nodeSelector:
        workload-type: storage  # worker-storage 노드에 배치
      tolerations:
        - key: workload-type
          operator: Equal
          value: storage
          effect: NoSchedule
      containers:
        - name: relay
          image: mng990/eco2:auth-relay-latest
          imagePullPolicy: Always
          resources:
            requests:
              cpu: 10m
              memory: 32Mi
            limits:
              cpu: 100m
              memory: 64Mi
          envFrom:
            - secretRef:
                name: auth-secret
          env:
            - name: RELAY_POLL_INTERVAL
              value: "1.0"
            - name: RELAY_BATCH_SIZE
              value: "10"
            - name: LOG_LEVEL
              value: INFO
      imagePullSecrets:
        - name: dockerhub-secret
```

### 5.2 `workloads/domains/auth-relay/base/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: auth-relay-config
  namespace: auth
  labels:
    app: auth-relay
data:
  RELAY_POLL_INTERVAL: "1.0"
  RELAY_BATCH_SIZE: "10"
  LOG_LEVEL: "INFO"
```

### 5.3 `workloads/domains/auth-relay/base/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: auth

resources:
  - deployment.yaml
  - configmap.yaml

commonLabels:
  app.kubernetes.io/name: auth-relay
  app.kubernetes.io/component: relay
  app.kubernetes.io/part-of: auth
```

---

## 6. `blacklist_publisher.py` 수정 (Outbox 적재 로직)

```python
def publish_add(self, jti: str, expires_at: datetime) -> bool:
    """블랙리스트 추가 이벤트 발행.

    1차 시도: RabbitMQ 직접 발행
    실패 시: Redis Outbox에 적재 (Relay가 재처리)
    """
    event = {
        "type": "add",
        "jti": jti,
        "expires_at": expires_at.isoformat(),
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        # 1차 시도: 직접 발행
        self._publish(event)
        return True
    except Exception as e:
        logger.warning(
            "MQ publish failed, queueing to outbox",
            extra={"jti": jti[:8], "error": str(e)},
        )
        # Outbox에 적재 (Relay가 처리)
        self._queue_to_outbox(event)
        return False  # 발행 실패했지만 Outbox에 저장됨


def _queue_to_outbox(self, event: dict) -> None:
    """Redis Outbox에 이벤트 적재."""
    import redis

    redis_url = os.getenv("AUTH_REDIS_URL")
    if not redis_url:
        logger.error("AUTH_REDIS_URL not set, event lost")
        return

    try:
        r = redis.from_url(redis_url)
        r.lpush("outbox:blacklist", json.dumps(event))
        logger.info("Event queued to outbox", extra={"jti": event["jti"][:8]})
    except Exception:
        logger.exception("Failed to queue to outbox, event lost")
```

---

## 7. CI/CD

### 7.1 `.github/workflows/ci-services.yml` 수정

```yaml
# paths에 추가
- "domains/auth/tasks/**"
- "domains/auth/Dockerfile.relay"
- "domains/auth/requirements-relay.txt"

# services 배열에 추가
- name: auth-relay
  dockerfile: domains/auth/Dockerfile.relay
  context: .
```

### 7.2 `clusters/dev/apps/60-apis-appset.yaml` 수정

```yaml
services:
  # ... 기존 서비스들 ...
  - name: auth-relay
    namespace: auth
    path: workloads/domains/auth-relay
```

---

## 8. 노드 배치

```
┌─────────────────────────────────────────────────────────────┐
│                    worker-storage 노드                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  현재 배치:                                                 │
│  ├── PostgreSQL (dev-postgresql-0)                         │
│  ├── RabbitMQ (eco2-rabbitmq-server-0)                    │
│  ├── Celery Beat                                           │
│  └── Prometheus/Grafana                                    │
│                                                             │
│  추가 예정:                                                 │
│  └── auth-relay (~10m CPU, ~32MB Mem)                      │
│                                                             │
│  장점:                                                       │
│  - 기존 인프라 활용 (Redis, RabbitMQ 동일 노드)            │
│  - 네트워크 지연 최소화                                     │
│  - 별도 노드 프로비저닝 불필요                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 모니터링

### 9.1 Prometheus 메트릭 (추후 구현)

```python
# 추가할 메트릭
relay_events_total = Counter(
    "auth_relay_events_total",
    "Total events processed by relay",
    ["status"],  # success, failed, dlq
)
relay_queue_depth = Gauge(
    "auth_relay_queue_depth",
    "Current outbox queue depth",
)
relay_processing_time = Histogram(
    "auth_relay_processing_seconds",
    "Time to process a batch",
)
```

### 9.2 알림 규칙

```yaml
# DLQ에 이벤트가 쌓이면 알림
- alert: AuthRelayDLQNotEmpty
  expr: auth_relay_queue_depth{key="dlq"} > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Auth Relay DLQ has {{ $value }} events"
```

---

## 10. 다음 단계

1. **Phase 1**: `auth-api` Publisher에 Outbox 적재 로직 추가
2. **Phase 2**: Relay Worker 구현 및 배포
3. **Phase 3**: 모니터링 메트릭 추가
4. **Phase 4**: 부하 테스트 및 튜닝

