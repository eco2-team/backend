# AMQP와 RabbitMQ: 메시지 브로커의 표준

> **Part III: 메시징 패턴** | [← 10. DDD Aggregate](./10-ddd-aggregate-eric-evans.md) | [인덱스](./00-index.md) | [12. Celery →](./12-celery-distributed-task-queue.md)

> 원문: [AMQP 0-9-1 Specification](https://www.amqp.org/specification/0-9-1/amqp-org-download) (2006)
> RabbitMQ: [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)

---

## 들어가며

AMQP(Advanced Message Queuing Protocol)는 **메시지 지향 미들웨어의 개방형 표준 프로토콜**이다. 2003년 JPMorgan Chase에서 시작되어 2006년에 AMQP 0-9-1로 표준화되었다.

RabbitMQ는 AMQP 0-9-1의 **가장 널리 사용되는 구현체**로, Erlang으로 작성되어 높은 안정성과 분산 처리 능력을 제공한다.

Kafka가 "로그"라면, RabbitMQ는 "우체국"이다:
- **Kafka**: 메시지를 로그처럼 영구 저장, Consumer가 원하는 위치에서 읽음
- **RabbitMQ**: 메시지를 큐에 저장, Consumer에게 전달 후 삭제

---

## AMQP 탄생 배경

### 금융권의 문제

2000년대 초, 금융 기관들은 심각한 문제에 직면했다:

```
┌─────────────────────────────────────────────────────────────┐
│                  2003년 금융권 현실                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Trading System A ──────────▶ IBM MQ ◀──────── Risk System  │
│  (Java)                     (비쌈!)           (C++)         │
│                                                             │
│  Settlement ──────────────▶ TIBCO ◀────────── Reporting    │
│  (C#)                      (더 비쌈!)         (Python)      │
│                                                             │
│  문제:                                                      │
│  • 벤더 종속 (Lock-in)                                      │
│  • 라이선스 비용 수백만 달러/년                              │
│  • 시스템 간 통합 어려움 (프로토콜 비호환)                  │
│  • 각 벤더마다 다른 API                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### AMQP의 목표

JPMorgan의 John O'Hara가 주도하여 개방형 표준 개발:

| 목표 | 설명 |
|------|------|
| **상호운용성** | 벤더에 관계없이 메시지 교환 |
| **개방형 표준** | 누구나 구현 가능 |
| **다양한 언어** | Java, C++, Python, Ruby 등 |
| **엔터프라이즈 기능** | 트랜잭션, 라우팅, QoS |

---

## AMQP 핵심 개념

### 메시징 모델

```
┌─────────────────────────────────────────────────────────────┐
│                    AMQP 메시징 모델                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Producer                                       Consumer    │
│  ┌───────┐                                     ┌───────┐   │
│  │ App A │                                     │ App B │   │
│  └───┬───┘                                     └───▲───┘   │
│      │                                             │        │
│      │ publish                              consume│        │
│      ▼                                             │        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Broker (RabbitMQ)                 │   │
│  │                                                     │   │
│  │  ┌──────────┐    Binding    ┌──────────┐           │   │
│  │  │ Exchange │──────────────▶│  Queue   │           │   │
│  │  │          │  routing_key  │          │           │   │
│  │  │  direct  │               │ [msg][msg]│           │   │
│  │  │  topic   │               │          │           │   │
│  │  │  fanout  │               └──────────┘           │   │
│  │  │  headers │                                       │   │
│  │  └──────────┘                                       │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  핵심 개념:                                                 │
│  • Exchange: 메시지 라우팅 (우체국)                        │
│  • Queue: 메시지 저장 (우편함)                             │
│  • Binding: Exchange-Queue 연결 규칙                       │
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
│  1. Direct Exchange (정확한 매칭)                           │
│  ───────────────────────────────                            │
│                                                             │
│  Producer ─▶ Exchange ─▶ routing_key="error" ─▶ Error Queue │
│                       ─▶ routing_key="info"  ─▶ Info Queue  │
│                                                             │
│  2. Topic Exchange (패턴 매칭)                              │
│  ────────────────────────────                               │
│                                                             │
│  Producer ─▶ Exchange ─▶ "scan.completed" ─▶ scan.* Queue   │
│                       ─▶ "scan.failed"    ─▶ *.failed Queue │
│                                                             │
│  • *: 정확히 하나의 단어                                    │
│  • #: 0개 이상의 단어                                       │
│                                                             │
│  3. Fanout Exchange (브로드캐스트)                          │
│  ─────────────────────────────────                          │
│                                                             │
│  Producer ─▶ Exchange ─▶ Queue A                            │
│                       ─▶ Queue B                            │
│                       ─▶ Queue C                            │
│                                                             │
│  (모든 바인딩된 큐에 복사)                                  │
│                                                             │
│  4. Headers Exchange (헤더 기반)                            │
│  ──────────────────────────────                             │
│                                                             │
│  Producer ─▶ Exchange ─▶ x-match: all, type: scan ─▶ Queue  │
│                                                             │
│  (routing_key 대신 헤더로 매칭)                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 메시지 신뢰성

### Message Acknowledgement

```
┌─────────────────────────────────────────────────────────────┐
│                  Message Acknowledgement                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Broker                             Consumer                │
│    │                                   │                    │
│    │   1. Deliver (message)            │                    │
│    │ ────────────────────────────────▶ │                    │
│    │                                   │                    │
│    │                                   │ 2. Process         │
│    │                                   │                    │
│    │   3. Basic.Ack                    │                    │
│    │ ◀──────────────────────────────── │                    │
│    │                                   │                    │
│    │   4. 메시지 삭제                  │                    │
│    │                                   │                    │
│                                                             │
│  Ack 종류:                                                  │
│  • auto_ack=True: 전송 즉시 삭제 (위험!)                   │
│  • auto_ack=False: Consumer가 명시적으로 Ack               │
│  • basic.nack: 처리 실패, 재큐잉                           │
│  • basic.reject: 처리 거부                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Publisher Confirms

```python
# Producer 측 신뢰성 보장

channel.confirm_delivery()  # Publisher Confirms 활성화

try:
    channel.basic_publish(
        exchange='scan',
        routing_key='task',
        body=json.dumps(message),
        properties=pika.BasicProperties(
            delivery_mode=2,  # Persistent
        ),
    )
    print("Message confirmed")
except pika.exceptions.UnroutableError:
    print("Message was returned")
```

### 메시지 지속성 (Durability)

```
┌─────────────────────────────────────────────────────────────┐
│                  Durability 설정                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Durable Queue                                           │
│  ─────────────────                                          │
│  channel.queue_declare(queue='tasks', durable=True)         │
│  → Broker 재시작 후에도 큐 유지                             │
│                                                             │
│  2. Persistent Message                                      │
│  ────────────────────                                       │
│  properties=pika.BasicProperties(delivery_mode=2)           │
│  → 메시지를 디스크에 저장                                   │
│                                                             │
│  3. Publisher Confirms                                      │
│  ────────────────────                                       │
│  channel.confirm_delivery()                                 │
│  → Broker가 메시지 수신 확인                                │
│                                                             │
│  ⚠️ 모든 설정을 해야 완전한 신뢰성 보장!                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## RabbitMQ 확장 기능

### Quorum Queue (고가용성)

```
┌─────────────────────────────────────────────────────────────┐
│                    Quorum Queue                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  기존 Mirrored Queue 문제:                                  │
│  • Split-brain 발생 가능                                    │
│  • 동기화 중 성능 저하                                      │
│                                                             │
│  Quorum Queue (RabbitMQ 3.8+):                              │
│  • Raft 합의 알고리즘 사용                                  │
│  • 과반수 노드 동의 필요                                    │
│  • 데이터 손실 방지                                         │
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │
│  │ Node 1  │  │ Node 2  │  │ Node 3  │                     │
│  │ Leader  │  │Follower │  │Follower │                     │
│  │   ✓     │──│   ✓     │──│   ✓     │                     │
│  └─────────┘  └─────────┘  └─────────┘                     │
│                                                             │
│  설정:                                                      │
│  channel.queue_declare(                                     │
│      queue='tasks',                                         │
│      arguments={'x-queue-type': 'quorum'}                   │
│  )                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Dead Letter Exchange (DLX)

```
┌─────────────────────────────────────────────────────────────┐
│                  Dead Letter Exchange                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  메시지가 DLX로 이동하는 경우:                              │
│  • Consumer가 basic.reject/nack (requeue=false)            │
│  • 메시지 TTL 만료                                          │
│  • 큐 최대 길이 초과                                        │
│                                                             │
│  ┌─────────────┐           ┌─────────────┐                 │
│  │ Main Queue  │──reject──▶│  DLX Queue  │                 │
│  │             │           │             │                 │
│  │ x-dead-     │           │ (수동 검토  │                 │
│  │ letter-     │           │  또는 재처리)│                 │
│  │ exchange    │           │             │                 │
│  └─────────────┘           └─────────────┘                 │
│                                                             │
│  설정:                                                      │
│  channel.queue_declare(                                     │
│      queue='tasks',                                         │
│      arguments={                                            │
│          'x-dead-letter-exchange': 'dlx',                   │
│          'x-dead-letter-routing-key': 'tasks.dlq',          │
│      }                                                      │
│  )                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 실전 패턴

### Priority Queue

긴급 작업을 먼저 처리해야 할 때:

```
┌─────────────────────────────────────────────────────────────┐
│                    Priority Queue                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  메시지 도착 순서:  [A:1] [B:5] [C:3] [D:10] [E:2]         │
│  (숫자 = 우선순위)                                          │
│                                                             │
│  처리 순서:         [D:10] → [B:5] → [C:3] → [E:2] → [A:1] │
│                                                             │
│  설정:                                                      │
│  channel.queue_declare(                                     │
│      queue='tasks',                                         │
│      arguments={'x-max-priority': 10}  # 0-10 우선순위     │
│  )                                                          │
│                                                             │
│  발행:                                                      │
│  channel.basic_publish(                                     │
│      exchange='',                                           │
│      routing_key='tasks',                                   │
│      body=message,                                          │
│      properties=pika.BasicProperties(priority=5)           │
│  )                                                          │
│                                                             │
│  Eco² 적용: VIP 사용자 스캔 우선 처리                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Delayed Message (지연 메시지)

일정 시간 후 처리가 필요할 때:

```
┌─────────────────────────────────────────────────────────────┐
│                   Delayed Message Exchange                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  사용 사례:                                                 │
│  • 30분 후 알림 발송                                        │
│  • 24시간 후 미완료 주문 취소                               │
│  • 재시도 지연 (1분 → 5분 → 15분)                          │
│                                                             │
│  rabbitmq-delayed-message-exchange 플러그인 필요:          │
│                                                             │
│  Producer ──▶ Delayed Exchange ──(10초 후)──▶ Queue        │
│                                                             │
│  channel.exchange_declare(                                  │
│      exchange='delayed',                                    │
│      exchange_type='x-delayed-message',                    │
│      arguments={'x-delayed-type': 'direct'}                │
│  )                                                          │
│                                                             │
│  channel.basic_publish(                                     │
│      exchange='delayed',                                    │
│      routing_key='tasks',                                   │
│      body=message,                                          │
│      properties=pika.BasicProperties(                       │
│          headers={'x-delay': 60000}  # 60초 지연           │
│      )                                                      │
│  )                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Lazy Queue (대용량 큐)

메모리를 절약하며 대량 메시지를 처리할 때:

```
┌─────────────────────────────────────────────────────────────┐
│                      Lazy Queue                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  일반 Queue:                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Memory: [msg][msg][msg][msg][msg][msg]...          │   │
│  │  → 메시지가 쌓이면 메모리 부족                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Lazy Queue:                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Memory: [pointer] ───▶ Disk: [msg][msg][msg]...    │   │
│  │  → 메시지를 바로 디스크에 저장                      │   │
│  │  → 메모리 사용량 최소화                             │   │
│  │  → Consumer 요청 시 디스크에서 로드                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  설정:                                                      │
│  channel.queue_declare(                                     │
│      queue='batch_tasks',                                   │
│      arguments={'x-queue-mode': 'lazy'}                    │
│  )                                                          │
│                                                             │
│  사용 사례: 배치 작업, 트래픽 스파이크 대응                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## RabbitMQ Streams (3.9+)

### Kafka 스타일의 로그 기반 큐

RabbitMQ 3.9부터 **Streams** 기능이 추가되어 Kafka와 유사한 패턴을 지원한다:

```
┌─────────────────────────────────────────────────────────────┐
│                    RabbitMQ Streams                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  기존 Queue:                                                │
│  • 소비 후 삭제                                             │
│  • 한 번만 읽기 가능                                        │
│  • Push 모델                                                │
│                                                             │
│  Streams (Kafka 스타일):                                    │
│  • 영구 보존 (설정 기간)                                    │
│  • 여러 Consumer가 독립적으로 읽기                          │
│  • Offset 기반 재처리 가능                                  │
│  • 초당 수백만 메시지 처리                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Stream Log: [0][1][2][3][4][5][6][7][8][9]...      │   │
│  │                    ▲           ▲                    │   │
│  │                    │           │                    │   │
│  │              Consumer A   Consumer B                │   │
│  │              (offset=3)   (offset=7)                │   │
│  │                                                     │   │
│  │  • 메시지 삭제 안 함                                │   │
│  │  • 각 Consumer가 자신의 Offset 관리                 │   │
│  │  • 같은 메시지를 여러 번 읽기 가능                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Super Streams (파티셔닝)

Kafka의 파티션과 유사한 수평 확장:

```
┌─────────────────────────────────────────────────────────────┐
│                    Super Streams                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  하나의 논리적 Stream을 여러 파티션으로 분할:              │
│                                                             │
│  Super Stream: "events"                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ┌──────────────┐                                  │   │
│  │  │ events-0     │ ◀── partition_key % 3 == 0       │   │
│  │  │ [A][D][G]... │                                  │   │
│  │  └──────────────┘                                  │   │
│  │                                                     │   │
│  │  ┌──────────────┐                                  │   │
│  │  │ events-1     │ ◀── partition_key % 3 == 1       │   │
│  │  │ [B][E][H]... │                                  │   │
│  │  └──────────────┘                                  │   │
│  │                                                     │   │
│  │  ┌──────────────┐                                  │   │
│  │  │ events-2     │ ◀── partition_key % 3 == 2       │   │
│  │  │ [C][F][I]... │                                  │   │
│  │  └──────────────┘                                  │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  • 같은 키의 메시지는 같은 파티션으로                      │
│  • Consumer Group으로 병렬 처리                            │
│  • Kafka 없이 이벤트 스트리밍 가능                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Streams vs Classic Queue

| 특성 | Classic Queue | Streams |
|------|---------------|---------|
| **메시지 수명** | 소비 후 삭제 | 보존 기간까지 유지 |
| **재처리** | 불가능 | Offset으로 가능 |
| **처리량** | 수만/초 | 수백만/초 |
| **Consumer 패턴** | Competing | Independent |
| **사용 사례** | Task Queue | Event Log |

---

## 운영 베스트 프랙티스

### 모니터링

```
┌─────────────────────────────────────────────────────────────┐
│                  RabbitMQ 모니터링 스택                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  RabbitMQ    │───▶│  Prometheus  │───▶│   Grafana    │ │
│  │  Exporter    │    │              │    │              │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│                                                             │
│  핵심 메트릭:                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Queue 메트릭:                                      │   │
│  │  • rabbitmq_queue_messages         (큐 길이)       │   │
│  │  • rabbitmq_queue_messages_ready   (대기 메시지)   │   │
│  │  • rabbitmq_queue_consumers        (Consumer 수)   │   │
│  │                                                     │   │
│  │  처리량 메트릭:                                     │   │
│  │  • rabbitmq_channel_messages_published (발행률)    │   │
│  │  • rabbitmq_channel_messages_delivered (소비율)    │   │
│  │  • rabbitmq_channel_messages_acked     (Ack율)     │   │
│  │                                                     │   │
│  │  리소스 메트릭:                                     │   │
│  │  • rabbitmq_node_mem_used          (메모리)        │   │
│  │  • rabbitmq_node_disk_free         (디스크)        │   │
│  │  • rabbitmq_connections            (연결 수)       │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  알람 설정:                                                 │
│  • Queue 길이 > 10,000: Warning                           │
│  • Consumer 수 = 0: Critical                              │
│  • 메모리 > 80%: Warning                                  │
│  • 디스크 < 20%: Critical                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 클러스터링 권장 구성

```
┌─────────────────────────────────────────────────────────────┐
│                  Production 클러스터 구성                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  권장: 홀수 노드 (3, 5, 7)                                  │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Node 1    │  │   Node 2    │  │   Node 3    │        │
│  │   (disc)    │──│   (disc)    │──│   (disc)    │        │
│  │   Leader    │  │  Follower   │  │  Follower   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│  Quorum Queue 복제:                                        │
│  • 메시지가 과반수 노드에 복제되어야 Ack                   │
│  • 1개 노드 장애 시에도 서비스 유지                        │
│  • 2개 노드 장애 시 쓰기 불가 (읽기는 가능)               │
│                                                             │
│  partition_handling: pause_minority                        │
│  • 네트워크 분리 시 소수 파티션 일시 중지                  │
│  • Split-brain 방지                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 성능 튜닝

```
┌─────────────────────────────────────────────────────────────┐
│                    성능 튜닝 체크리스트                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 연결 관리                                               │
│  ─────────────                                              │
│  • Connection Pooling 사용 (매번 연결 X)                   │
│  • Channel 재사용 (Connection당 Channel 제한)              │
│  • Heartbeat 설정 (기본 60초 권장)                         │
│                                                             │
│  2. 메시지 배치                                             │
│  ─────────────                                              │
│  • basic_publish → batch publish (Publisher Confirms)      │
│  • prefetch_count 조절 (기본 1, 작업 특성에 따라 조정)     │
│                                                             │
│  3. 리소스 설정                                             │
│  ─────────────                                              │
│  • vm_memory_high_watermark: 0.4 (기본) → 0.6 (조정 가능) │
│  • disk_free_limit: 최소 2GB                               │
│  • Erlang VM 설정 (+K true +A 128)                         │
│                                                             │
│  4. 큐 설정                                                 │
│  ─────────────                                              │
│  • x-max-length: 큐 최대 길이 제한                        │
│  • x-message-ttl: 메시지 만료 시간                        │
│  • x-expires: 사용 안 하는 큐 자동 삭제                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 보안 설정

```
┌─────────────────────────────────────────────────────────────┐
│                    보안 체크리스트                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. TLS 암호화                                              │
│  ───────────────                                            │
│  listeners.ssl.default = 5671                               │
│  ssl_options.cacertfile = /path/to/ca.pem                  │
│  ssl_options.certfile = /path/to/server.pem                │
│  ssl_options.keyfile = /path/to/server.key                 │
│  ssl_options.verify = verify_peer                          │
│                                                             │
│  2. 사용자 권한                                             │
│  ───────────────                                            │
│  • guest 사용자 비활성화 또는 localhost 제한               │
│  • 최소 권한 원칙 (read/write/configure 분리)             │
│  • vhost로 테넌트 분리                                     │
│                                                             │
│  3. 네트워크                                                │
│  ───────────────                                            │
│  • Management UI: 내부 네트워크만 접근                     │
│  • epmd: 공개 인터넷 노출 금지                             │
│  • Firewall: 5672, 5671, 15672, 25672 포트 제한           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Kafka와의 비교

### 핵심 차이점

```
┌─────────────────────────────────────────────────────────────┐
│                  RabbitMQ vs Kafka                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ (Smart Broker)        Kafka (Dumb Broker)         │
│  ───────────────────────        ─────────────────────       │
│                                                             │
│  • 메시지 라우팅 (Exchange)     • 단순 로그 저장            │
│  • 소비 후 삭제                 • 영구 보존                 │
│  • Push 모델                    • Pull 모델                 │
│  • 복잡한 라우팅 가능           • 토픽 기반만               │
│  • Ack 후 삭제                  • Offset 관리               │
│                                                             │
│  ┌─────────────────────┐       ┌─────────────────────┐     │
│  │     Queue           │       │      Log            │     │
│  │  ┌───┬───┬───┐     │       │  [0][1][2][3][4]... │     │
│  │  │ A │ B │ C │     │       │                     │     │
│  │  └───┴───┴───┘     │       │  Consumer Offset ▲  │     │
│  │       ↓            │       │                     │     │
│  │  (삭제)            │       │  (영구 보존)        │     │
│  └─────────────────────┘       └─────────────────────┘     │
│                                                             │
│  ⚠️ RabbitMQ Streams로 Kafka 스타일도 가능해짐!             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 선택 기준 (2025년 업데이트)

| 기준 | RabbitMQ | Kafka |
|------|----------|-------|
| **메시지 패턴** | Task Queue, RPC | Event Streaming |
| **메시지 수명** | 소비 후 삭제 (Streams: 보존) | 설정 기간 보존 |
| **라우팅** | 복잡한 라우팅 가능 | 토픽 기반만 |
| **재처리** | Streams로 가능 | Offset 변경으로 가능 |
| **처리량** | Queue: 수만/초, Streams: 수백만/초 | 수백만/초 |
| **지연 시간** | 수 ms | 수십 ms |
| **프로토콜** | AMQP, MQTT, STOMP | Kafka 전용 |
| **사용 사례** | 작업 분배, RPC, IoT | 이벤트 소싱, 로그 |
| **운영 복잡도** | 상대적 단순 | ZK/KRaft 필요 |

### 언제 무엇을 선택하나?

```
┌─────────────────────────────────────────────────────────────┐
│                    선택 가이드                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ를 선택하는 경우:                                  │
│  ✅ 복잡한 라우팅이 필요한 경우 (Topic, Headers Exchange)  │
│  ✅ 낮은 지연 시간이 중요한 경우 (ms 단위)                 │
│  ✅ 다양한 프로토콜 지원 필요 (MQTT, STOMP)                │
│  ✅ 기존 AMQP 생태계와 통합                                 │
│  ✅ 상대적으로 단순한 운영 원할 때                          │
│                                                             │
│  Kafka를 선택하는 경우:                                     │
│  ✅ 이벤트 소싱 / Event Replay 필수                        │
│  ✅ 초대용량 처리 (수백만 msg/초)                          │
│  ✅ 장기 데이터 보존 필요                                   │
│  ✅ Kafka Connect 에코시스템 활용                           │
│  ✅ CDC (Debezium) 연동                                     │
│                                                             │
│  Eco² 선택:                                                 │
│  • RabbitMQ: AI 파이프라인 (Task Queue)                    │
│  • Kafka: 도메인 이벤트 (Event Sourcing + CDC)             │
│  → 각자의 강점을 활용하는 Command-Event Separation         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 참고 자료

### 원문
- [AMQP 0-9-1 Complete Reference](https://www.rabbitmq.com/amqp-0-9-1-reference.html)
- [RabbitMQ Tutorials](https://www.rabbitmq.com/getstarted.html)
- [Quorum Queues](https://www.rabbitmq.com/quorum-queues.html)
- [RabbitMQ Streams Overview](https://www.rabbitmq.com/blog/2021/07/13/rabbitmq-streams-overview) - Streams 소개
- [Super Streams](https://www.rabbitmq.com/blog/2022/07/13/rabbitmq-3-11-feature-preview-super-streams) - 파티셔닝
- [Production Checklist](https://www.rabbitmq.com/docs/production-checklist) - 운영 체크리스트

### 관련 Foundation
- [01-the-log-jay-kreps.md](./01-the-log-jay-kreps.md) - Kafka와의 비교
- [05-enterprise-integration-patterns.md](./05-enterprise-integration-patterns.md) - 메시징 패턴
- [12-celery-distributed-task-queue.md](./12-celery-distributed-task-queue.md) - RabbitMQ + Celery

---

## 부록: Eco² 적용 포인트

### RabbitMQ의 역할 (Command-Event Separation)

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² RabbitMQ 사용 범위                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ 사용 (Command/Task)       Kafka 사용 (Event)      │
│  ──────────────────────────────     ─────────────────       │
│                                                             │
│  ✅ AI 파이프라인                   ✅ 도메인 이벤트        │
│     • vision_scan Task                 • ScanCompleted      │
│     • rule_match Task                  • CharacterGranted   │
│     • answer_gen Task                                       │
│                                     ✅ CDC                  │
│  ✅ 외부 API 호출                      • Outbox → Kafka     │
│     • 이메일 발송                                           │
│     • 푸시 알림                     ✅ Event Sourcing       │
│     • SMS 발송                         • Aggregate Replay   │
│                                                             │
│  ✅ 배치 작업                                               │
│     • 리포트 생성                                           │
│     • 데이터 정리                                           │
│                                                             │
│  ✅ Retry/DLQ                                               │
│     • Celery 내장 기능                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Queue 설계

```yaml
# workloads/rabbitmq/base/topology/queues.yaml

# AI 파이프라인 큐
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-ai-pipeline
spec:
  name: scan.ai.pipeline
  vhost: celery
  type: quorum
  durable: true
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: scan.ai.dlq
  rabbitmqClusterReference:
    name: eco2-rabbitmq

---
# DLQ
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-ai-dlq
spec:
  name: scan.ai.dlq
  vhost: celery
  type: quorum
  durable: true
  rabbitmqClusterReference:
    name: eco2-rabbitmq
```

### Celery 연동

```python
# domains/_shared/taskqueue/config.py

from celery import Celery

celery_app = Celery(
    'eco2',
    broker='amqp://guest:guest@eco2-rabbitmq.rabbitmq.svc.cluster.local:5672/celery',
    backend='redis://eco2-redis.redis.svc.cluster.local:6379/0',
)

celery_app.conf.update(
    task_routes={
        'scan.tasks.*': {'queue': 'scan.ai.pipeline'},
        'notification.tasks.*': {'queue': 'notification'},
    },
    task_acks_late=True,  # 처리 완료 후 Ack
    task_reject_on_worker_lost=True,  # Worker 종료 시 재큐잉
    worker_prefetch_multiplier=1,  # 공정한 분배
)
```

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-------------------|
| **메시지 브로커** | 없음 | RabbitMQ (Task) + Kafka (Event) |
| **AI 파이프라인** | gRPC 블로킹 | RabbitMQ Celery Task |
| **라우팅** | gRPC Interceptor | Exchange + Routing Key |
| **신뢰성** | Circuit Breaker | Publisher Confirms + Ack |
| **실패 처리** | 재시도 후 포기 | DLQ + 수동 복구 |
| **고가용성** | gRPC LB | Quorum Queue |
