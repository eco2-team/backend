# AMQP Protocol

> [← 02. Python GIL](./02-python-gil.md) | [인덱스](./00-index.md) | [04. Concurrency Patterns →](./04-concurrency-patterns.md)

> **공식 스펙**: [AMQP 0-9-1 Complete Reference](https://www.rabbitmq.com/amqp-0-9-1-reference.html)
> **구현체**: [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
> **Python 클라이언트**: [aio-pika Documentation](https://aio-pika.readthedocs.io/)

---

## 개요

AMQP(Advanced Message Queuing Protocol)는 **메시지 지향 미들웨어**를 위한 **개방형 표준 프로토콜**이다.

```
이코에코 사용 버전:
• AMQP 0-9-1 (RabbitMQ 기본)
• RabbitMQ 4.0
• aio-pika 9.3.1
```

### 프로토콜 버전

| 버전 | 상태 | 특징 |
|------|------|------|
| **AMQP 0-9-1** | RabbitMQ 기본 | Exchange, Queue, Binding 모델 |
| **AMQP 1.0** | ISO/IEC 19464:2014 | 링크 기반 모델, Azure Service Bus |

> 이 문서는 **AMQP 0-9-1**에 집중합니다 (RabbitMQ/Celery 호환).

---

## AMQP 0-9-1 핵심 개념

> 출처: [AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts.html)

### 메시징 모델

```
┌─────────────────────────────────────────────────────────────┐
│                  AMQP 0-9-1 메시징 모델                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Publisher                                       Consumer   │
│  ┌───────┐                                      ┌───────┐  │
│  │ App A │                                      │ App B │  │
│  └───┬───┘                                      └───▲───┘  │
│      │                                              │       │
│      │ AMQP                                    AMQP │       │
│      │ Connection                          Connection       │
│      ▼                                              │       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Broker                           │   │
│  │                                                     │   │
│  │  ┌──────────┐   Binding   ┌──────────┐             │   │
│  │  │ Exchange │────────────▶│  Queue   │─────────────┼───┘
│  │  │          │ routing_key │          │             │   │
│  │  └──────────┘             │ [msg][msg]│             │   │
│  │                           └──────────┘             │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  핵심 컴포넌트:                                             │
│  • Exchange: 메시지 라우팅 규칙 정의                        │
│  • Queue: 메시지 저장                                       │
│  • Binding: Exchange와 Queue 연결                          │
│  • Routing Key: 메시지 분류 기준                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Exchange Types

```
┌─────────────────────────────────────────────────────────────┐
│                    Exchange Types                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Direct Exchange                                         │
│  ──────────────────                                         │
│  routing_key가 정확히 일치하는 Queue로 라우팅               │
│                                                             │
│  Publisher ─▶ Exchange ─▶ routing_key="scan.vision"        │
│                        ─▶ Queue: scan.vision               │
│                                                             │
│  Celery 기본 방식: 각 Task가 자신의 Queue로 라우팅          │
│                                                             │
│  2. Topic Exchange                                          │
│  ─────────────────                                          │
│  패턴 매칭 (*: 단일 단어, #: 0개 이상 단어)                 │
│                                                             │
│  Publisher ─▶ Exchange ─▶ "scan.completed.success"         │
│                        ─▶ Binding: "scan.completed.*"      │
│                        ─▶ Binding: "scan.#"                │
│                                                             │
│  3. Fanout Exchange                                         │
│  ──────────────────                                         │
│  모든 바인딩된 Queue에 복사 (브로드캐스트)                  │
│                                                             │
│  Publisher ─▶ Exchange ─▶ Queue A                          │
│                        ─▶ Queue B                          │
│                        ─▶ Queue C                          │
│                                                             │
│  이코에코 사용: authz.fanout (캐시 무효화 브로드캐스트)     │
│                                                             │
│  4. Headers Exchange                                        │
│  ───────────────────                                        │
│  메시지 헤더 속성으로 라우팅 (routing_key 무시)             │
│                                                             │
│  Publisher ─▶ Exchange ─▶ x-match: all, type: scan         │
│                        ─▶ Matching Queue                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Channel Multiplexing

> 출처: [AMQP 0-9-1 Complete Reference - Channels](https://www.rabbitmq.com/amqp-0-9-1-reference.html#channel)

### 개념

```
┌─────────────────────────────────────────────────────────────┐
│                  Channel Multiplexing                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Connection (TCP Socket)                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Channel 1 ────▶ [msg] [msg] [msg]                 │   │
│  │                                                     │   │
│  │  Channel 2 ────▶ [msg] [msg]                       │   │
│  │                                                     │   │
│  │  Channel 3 ────▶ [msg] [msg] [msg] [msg]           │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  특징:                                                      │
│  • 하나의 TCP 연결에 여러 Channel 멀티플렉싱                │
│  • Channel은 가벼운 논리적 연결                             │
│  • 각 Channel은 독립적인 작업 수행                          │
│  • Connection 생성 비용 절감                                │
│                                                             │
│  권장 사항:                                                 │
│  • 스레드당 하나의 Channel 사용                             │
│  • Connection은 애플리케이션당 1-2개                        │
│  • Channel은 필요에 따라 생성/폐기                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### aio-pika에서의 구현

```python
import aio_pika

async def main():
    # Connection 생성 (TCP 연결)
    connection = await aio_pika.connect_robust(
        "amqp://guest:guest@localhost/"
    )
    
    # Channel 생성 (가벼운 논리적 연결)
    channel = await connection.channel()
    
    # 같은 Connection에서 여러 Channel 가능
    channel2 = await connection.channel()
    
    # 각 Channel은 독립적으로 작업
    await channel.declare_queue("queue1")
    await channel2.declare_queue("queue2")
```

---

## QoS (Quality of Service)

> 출처: [Consumer Prefetch](https://www.rabbitmq.com/consumer-prefetch.html)

### Prefetch Count

```
┌─────────────────────────────────────────────────────────────┐
│                    Prefetch Count                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  prefetch_count = 1 (Fair Dispatch)                         │
│  ──────────────────────────────────                         │
│                                                             │
│  Broker                        Consumer                     │
│    │                              │                         │
│    │──── msg1 ──────────────────▶│ (unacked: 1)            │
│    │                              │                         │
│    │ 대기 (msg2 전송 안함)        │ 처리 중...              │
│    │                              │                         │
│    │◀──────────── ack ───────────│ (unacked: 0)            │
│    │                              │                         │
│    │──── msg2 ──────────────────▶│ (unacked: 1)            │
│    │                              │                         │
│                                                             │
│  장점: 느린 Consumer에게 메시지 몰리지 않음                 │
│  단점: 처리량 감소 (네트워크 왕복 대기)                     │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  prefetch_count = 10 (Batch Prefetch)                       │
│  ────────────────────────────────────                       │
│                                                             │
│  Broker                        Consumer                     │
│    │                              │                         │
│    │──── msg1~10 ───────────────▶│ (unacked: 10)           │
│    │                              │                         │
│    │                              │ 순차 처리              │
│    │◀──────────── ack ───────────│ (msg1 완료)            │
│    │                              │                         │
│    │──── msg11 ─────────────────▶│ (unacked: 10 유지)     │
│    │                              │                         │
│                                                             │
│  장점: 처리량 증가 (버퍼링)                                 │
│  단점: 느린 Consumer에게 메시지 쌓임                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 이코에코 설정

```python
# domains/_shared/celery/config.py

class CelerySettings(BaseSettings):
    # Worker settings
    worker_prefetch_multiplier: int = Field(
        1,  # Fair dispatch (긴 작업에 적합)
        description="Number of tasks to prefetch per worker",
    )
```

### Global vs Per-Channel QoS

```
┌─────────────────────────────────────────────────────────────┐
│              Global vs Per-Channel QoS                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Per-Channel QoS (global=False, 기본값)                     │
│  ──────────────────────────────────────                     │
│  • 각 Consumer가 독립적인 prefetch_count                    │
│  • Consumer 1: prefetch=5, Consumer 2: prefetch=10          │
│                                                             │
│  Global QoS (global=True)                                   │
│  ─────────────────────────                                  │
│  • Channel의 모든 Consumer가 prefetch_count 공유            │
│  • 총합이 prefetch_count를 넘지 않음                        │
│                                                             │
│  ⚠️ Celery 주의:                                            │
│  • Celery는 Global QoS 사용                                 │
│  • Quorum Queue는 Global QoS 미지원                         │
│  • 이코에코는 Classic Queue 사용 (호환성)                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Message Acknowledgement

> 출처: [Consumer Acknowledgements](https://www.rabbitmq.com/confirms.html)

### Ack 종류

```
┌─────────────────────────────────────────────────────────────┐
│                  Acknowledgement 종류                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. basic.ack (확인)                                        │
│  ───────────────────                                        │
│  • 메시지 처리 완료                                         │
│  • Broker가 메시지 삭제                                     │
│                                                             │
│  channel.basic_ack(delivery_tag=tag)                        │
│                                                             │
│  2. basic.nack (부정 확인)                                  │
│  ─────────────────────────                                  │
│  • 메시지 처리 실패                                         │
│  • requeue=True: 큐에 다시 넣음                            │
│  • requeue=False: 버리거나 DLX로 이동                      │
│                                                             │
│  channel.basic_nack(delivery_tag=tag, requeue=False)        │
│                                                             │
│  3. basic.reject (거부)                                     │
│  ──────────────────────                                     │
│  • nack와 유사하나 단일 메시지만                            │
│  • AMQP 0-9-1 원래 스펙                                     │
│                                                             │
│  channel.basic_reject(delivery_tag=tag, requeue=False)      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Ack 모드

```python
# auto_ack=True (위험!)
# 메시지 전송 즉시 삭제, Consumer 크래시 시 메시지 손실

# auto_ack=False (권장)
# 명시적 ack 후에만 삭제

# 이코에코 설정
class CelerySettings(BaseSettings):
    task_acks_late: bool = True  # 처리 완료 후 ACK
    task_reject_on_worker_lost: bool = True  # Worker 종료 시 재큐잉
```

---

## aio-pika 비동기 패턴

> 출처: [aio-pika Documentation](https://aio-pika.readthedocs.io/)

### 기본 사용법

```python
import aio_pika
import asyncio

async def main():
    # Robust Connection (자동 재연결)
    connection = await aio_pika.connect_robust(
        "amqp://guest:guest@localhost/",
        loop=asyncio.get_event_loop(),
    )
    
    async with connection:
        # Channel 생성
        channel = await connection.channel()
        
        # QoS 설정
        await channel.set_qos(prefetch_count=10)
        
        # Queue 선언
        queue = await channel.declare_queue(
            "my_queue",
            durable=True,
        )
        
        # 메시지 발행
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=b"Hello World",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="my_queue",
        )
        
        # 메시지 소비
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    print(f"Received: {message.body}")
```

### Connection Pool 패턴

```python
from aio_pika.pool import Pool

async def get_connection():
    return await aio_pika.connect_robust("amqp://localhost/")

async def get_channel(connection):
    return await connection.channel()

# Connection Pool
connection_pool: Pool = Pool(get_connection, max_size=2)

# Channel Pool
channel_pool: Pool = Pool(get_channel, max_size=10)

async def publish_message(message: bytes):
    async with channel_pool.acquire() as channel:
        await channel.default_exchange.publish(
            aio_pika.Message(body=message),
            routing_key="my_queue",
        )
```

### RPC 패턴

```python
import uuid

async def rpc_call(channel, routing_key: str, body: bytes) -> bytes:
    # 임시 응답 큐 생성
    callback_queue = await channel.declare_queue(exclusive=True)
    correlation_id = str(uuid.uuid4())
    
    # 요청 발행
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=body,
            correlation_id=correlation_id,
            reply_to=callback_queue.name,
        ),
        routing_key=routing_key,
    )
    
    # 응답 대기
    async with callback_queue.iterator() as queue_iter:
        async for message in queue_iter:
            if message.correlation_id == correlation_id:
                return message.body
```

---

## AMQP 1.0 vs 0-9-1

> 출처: [OASIS AMQP 1.0](https://www.amqp.org/specification/1.0/amqp-org-download) (ISO/IEC 19464:2014)

### 주요 차이점

```
┌─────────────────────────────────────────────────────────────┐
│                AMQP 1.0 vs AMQP 0-9-1                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AMQP 0-9-1 (RabbitMQ, Celery)                             │
│  ─────────────────────────────                              │
│  • Exchange, Queue, Binding 모델                            │
│  • 메시징 패턴이 Broker에 내장                              │
│  • RabbitMQ의 기본 프로토콜                                 │
│                                                             │
│  AMQP 1.0 (Azure Service Bus, ActiveMQ)                    │
│  ──────────────────────────────────────                     │
│  • 링크 기반 모델 (더 유연)                                 │
│  • 메시징 패턴을 애플리케이션이 구현                        │
│  • ISO/IEC 19464:2014 국제 표준                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                     비교                             │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  항목         │ AMQP 0-9-1      │ AMQP 1.0          │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  라우팅       │ Broker가 수행   │ 애플리케이션 구현 │  │
│  │  연결 모델    │ Exchange/Queue  │ Link 기반         │  │
│  │  표준화       │ RabbitMQ 주도   │ ISO/IEC 표준      │  │
│  │  호환성       │ RabbitMQ 중심   │ 다양한 벤더       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  이코에코 선택: AMQP 0-9-1                                  │
│  • Celery 호환성                                            │
│  • RabbitMQ 기본 지원                                       │
│  • Exchange/Queue 모델의 명확성                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 이코에코 AMQP 구성

### 토폴로지

```yaml
# workloads/rabbitmq/base/topology/exchanges.yaml

# 1. Scan Pipeline (Direct)
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
spec:
  name: scan.direct
  type: direct
  durable: true
  vhost: eco2

---
# 2. Auth Blacklist (Fanout) - 캐시 동기화
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
spec:
  name: authz.fanout
  type: fanout
  durable: true
  vhost: eco2
```

### Queue 설계

```yaml
# workloads/rabbitmq/base/topology/queues.yaml

# AI 파이프라인 큐 (Classic Queue - Celery 호환)
apiVersion: rabbitmq.com/v1beta1
kind: Queue
spec:
  name: scan.vision
  type: classic  # Quorum 대신 Classic (Celery global QoS 호환)
  durable: true
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.scan.vision
    x-message-ttl: 3600000  # 1시간
```

### Celery 연동

```python
# domains/_shared/celery/config.py

CELERY_QUEUES = (
    Queue(
        "scan.vision",
        default_exchange,
        routing_key="scan.vision",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.scan.vision",
            "x-message-ttl": 3600000,
        },
    ),
    # ... more queues
)

celery_config = {
    "broker_url": "amqp://user:pass@rabbitmq:5672/eco2",
    "task_routes": {
        "scan.vision": {"queue": "scan.vision"},
        "scan.rule": {"queue": "scan.rule"},
        "scan.answer": {"queue": "scan.answer"},
    },
    "task_queues": CELERY_QUEUES,
}
```

---

## 요약

| 개념 | 설명 |
|------|------|
| **Exchange** | 메시지 라우팅 규칙 (Direct, Topic, Fanout, Headers) |
| **Queue** | 메시지 저장소 |
| **Binding** | Exchange-Queue 연결 |
| **Channel** | 경량 논리적 연결 (Connection 멀티플렉싱) |
| **QoS** | prefetch_count로 Consumer 부하 조절 |
| **Ack** | 메시지 처리 확인 (auto_ack=False 권장) |

---

## 참고 자료

### 공식 스펙
- [AMQP 0-9-1 Complete Reference](https://www.rabbitmq.com/amqp-0-9-1-reference.html)
- [AMQP 0-9-1 Model Explained](https://www.rabbitmq.com/tutorials/amqp-concepts.html)
- [OASIS AMQP 1.0](https://www.amqp.org/specification/1.0/amqp-org-download)

### RabbitMQ
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [Consumer Prefetch](https://www.rabbitmq.com/consumer-prefetch.html)
- [Consumer Acknowledgements](https://www.rabbitmq.com/confirms.html)

### Python 클라이언트
- [aio-pika Documentation](https://aio-pika.readthedocs.io/)
- [pika Documentation](https://pika.readthedocs.io/)

### 관련 Foundation
- [11-amqp-rabbitmq.md](../blogs/async/foundations/11-amqp-rabbitmq.md) - RabbitMQ 실전 패턴
- [04-concurrency-patterns.md](./04-concurrency-patterns.md) - Celery + RabbitMQ

