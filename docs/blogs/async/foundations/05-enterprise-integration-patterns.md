# Enterprise Integration Patterns: 메시징 시스템의 설계 원칙

> **Part III: 메시징 패턴** | [← 03. CQRS](./03-cqrs-martin-fowler.md) | [인덱스](./00-index.md) | [06. Life Beyond →](./06-life-beyond-distributed-transactions.md)

> 원문: [Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/) - Gregor Hohpe, Bobby Woolf (2003)

---

## 들어가며

2003년에 출간된 이 책은 **메시징 기반 시스템 통합의 바이블**로 불린다. 20년이 지난 지금도 RabbitMQ, Kafka, AWS SQS/SNS 등 모든 현대 메시징 시스템의 설계에 영향을 미치고 있다.

이 책이 중요한 이유는 **65개의 패턴**을 정의하여 메시징 설계에 대한 **공통 언어**를 제공했기 때문이다. "Dead Letter Queue", "Pub/Sub", "Competing Consumers" 같은 용어들이 바로 이 책에서 나왔다.

모든 패턴을 다 알 필요는 없다. 실무에서 가장 자주 마주치는 핵심 패턴들을 중심으로 살펴보자.

---

## 메시징이 필요한 이유

### 시스템 통합의 네 가지 방법

서로 다른 시스템을 연결하는 방법은 크게 네 가지가 있다:

| 방식 | 설명 | 장단점 |
|------|------|--------|
| **파일 전송** | 파일로 내보내고 다른 시스템이 읽음 | 단순하지만 실시간성 없음 |
| **공유 데이터베이스** | 같은 DB를 여러 시스템이 사용 | 통합 쉽지만 강한 결합 |
| **원격 프로시저 호출 (RPC)** | 직접 API 호출 | 실시간이지만 결합도 높음 |
| **메시징** | 메시지 큐를 통해 통신 | 느슨한 결합, 비동기 |

각 방식에는 적합한 사용 사례가 있다. 하지만 **시스템 간 결합을 줄이면서도 실시간성을 유지**하려면 메시징이 가장 효과적이다.

### 메시징의 핵심 개념

```
┌─────────────────────────────────────────────────────────────┐
│                    메시징 기본 구조                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐     ┌─────────────┐     ┌──────────┐        │
│  │  Sender  │────▶│   Channel   │────▶│ Receiver │        │
│  │ (Producer)     │   (Queue)   │     │(Consumer)│        │
│  └──────────┘     └─────────────┘     └──────────┘        │
│       │                 │                   │              │
│       │                 │                   │              │
│   메시지 생성        메시지 전달          메시지 처리         │
│                   (비동기, 버퍼링)                          │
│                                                             │
│  핵심:                                                      │
│  • Sender와 Receiver가 직접 연결되지 않음                    │
│  • Channel이 중간에서 메시지 보관                            │
│  • Sender는 Receiver가 준비됐는지 신경 쓰지 않음             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 메시지 채널 패턴

채널(Channel)은 메시지가 전달되는 **논리적 경로**다. 채널의 종류에 따라 메시지가 전달되는 방식이 달라진다.

### Point-to-Point Channel

**하나의 메시지는 정확히 하나의 소비자에게만 전달**된다.

```
┌─────────────────────────────────────────────────────────────┐
│                  Point-to-Point Channel                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Producer                       Consumers                   │
│  ┌───────┐    ┌─────────┐      ┌───────────┐              │
│  │ App A │───▶│         │─────▶│ Worker 1  │              │
│  └───────┘    │  Queue  │      └───────────┘              │
│               │         │      ┌───────────┐              │
│               │  [M1]   │─────▶│ Worker 2  │              │
│               │  [M2]   │      └───────────┘              │
│               │  [M3]   │      ┌───────────┐              │
│               └─────────┘─────▶│ Worker 3  │              │
│                                └───────────┘              │
│                                                             │
│  메시지 분배:                                               │
│  • M1 → Worker 1 (또는 2 또는 3, 하나만!)                  │
│  • M2 → Worker 2 (또는 1 또는 3, 하나만!)                  │
│  • M3 → Worker 3 (또는 1 또는 2, 하나만!)                  │
│                                                             │
│  사용 사례: 작업 분배, 부하 분산                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**사용 사례:**
- 이미지 리사이징 작업 분배
- 이메일 발송 작업
- AI 분류 작업 (하나의 이미지당 하나의 워커가 처리)

### Publish-Subscribe Channel

**하나의 메시지가 모든 구독자에게 복사되어 전달**된다.

```
┌─────────────────────────────────────────────────────────────┐
│                Publish-Subscribe Channel                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Publisher                      Subscribers                  │
│  ┌───────┐    ┌─────────┐      ┌───────────┐              │
│  │ App A │───▶│         │─────▶│ Service X │              │
│  └───────┘    │  Topic  │      └───────────┘              │
│               │         │      ┌───────────┐              │
│               │  [M1]   │─────▶│ Service Y │              │
│               │  복사!  │      └───────────┘              │
│               │         │      ┌───────────┐              │
│               └─────────┘─────▶│ Service Z │              │
│                                └───────────┘              │
│                                                             │
│  메시지 분배:                                               │
│  • M1 → Service X (복사본)                                 │
│  • M1 → Service Y (복사본)                                 │
│  • M1 → Service Z (복사본)                                 │
│                                                             │
│  모두에게 같은 메시지가 전달됨!                              │
│                                                             │
│  사용 사례: 이벤트 브로드캐스트, 알림                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**사용 사례:**
- 사용자 가입 이벤트 → 여러 서비스가 각자 처리
- JWT 블랙리스트 갱신 → 모든 인증 서버에 브로드캐스트
- 가격 변경 → 여러 서비스에 동시 알림

### 두 패턴의 조합

실무에서는 이 두 패턴을 조합해서 사용한다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Pub/Sub + P2P 조합                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Publisher          Topic              Queues               │
│  ┌───────┐      ┌─────────┐       ┌─────────┐             │
│  │ Auth  │─────▶│         │──────▶│ Queue A │             │
│  │ API   │      │ logout  │       │ (ext-authz용)         │
│  └───────┘      │         │       │ [Pod1, Pod2, Pod3]    │
│                 │         │       └─────────┘             │
│                 │         │       ┌─────────┐             │
│                 │         │──────▶│ Queue B │             │
│                 └─────────┘       │ (분석 서비스용)        │
│                                   │ [Worker1]             │
│                                   └─────────┘             │
│                                                             │
│  동작 방식:                                                 │
│  1. Auth API가 "logout" 토픽에 이벤트 발행                  │
│  2. 토픽이 각 큐에 메시지 복사 (Pub/Sub)                    │
│  3. 각 큐 내에서는 하나의 소비자만 처리 (P2P)               │
│                                                             │
│  RabbitMQ: Exchange(fanout) + 여러 Queue                   │
│  Kafka: Topic + Consumer Groups                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 메시지 라우팅 패턴

메시지가 어디로 가야 할지 결정하는 패턴들이다.

### Content-Based Router

**메시지 내용에 따라 다른 채널로 라우팅**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                  Content-Based Router                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  들어오는 메시지:                                            │
│  ┌────────────────────────────────────┐                    │
│  │ { type: "scan", priority: "high" } │                    │
│  └────────────────┬───────────────────┘                    │
│                   │                                         │
│                   ▼                                         │
│           ┌───────────────┐                                │
│           │    Router     │                                │
│           │               │                                │
│           │ if type == "scan"                              │
│           │   → scan-queue                                 │
│           │ if type == "chat"                              │
│           │   → chat-queue                                 │
│           └───────┬───────┘                                │
│                   │                                         │
│       ┌───────────┴───────────┐                            │
│       ▼                       ▼                            │
│  ┌──────────┐          ┌──────────┐                       │
│  │scan-queue│          │chat-queue│                       │
│  └──────────┘          └──────────┘                       │
│                                                             │
│  RabbitMQ: Direct Exchange + Routing Key                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Message Filter

**특정 조건에 맞는 메시지만 통과**시킨다.

```
┌─────────────────────────────────────────────────────────────┐
│                     Message Filter                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  모든 이벤트     Filter              처리기                  │
│  ──────────▶  ┌─────────┐  ──────▶  ┌─────────┐            │
│  M1 (pass)    │         │  M1       │ VIP     │            │
│  M2 (reject)  │ VIP만!  │           │ Service │            │
│  M3 (pass)    │         │  M3       │         │            │
│  M4 (reject)  └─────────┘           └─────────┘            │
│                                                             │
│  예: user.level == "vip" 인 이벤트만 통과                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Recipient List

**메시지를 보낼 대상 목록을 동적으로 결정**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                     Recipient List                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  주문 완료 이벤트                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ order_id: 123, items: [...], notifications: [       │   │
│  │   "email", "sms", "push"                            │   │
│  │ ]                                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                         │                                   │
│                         ▼                                   │
│               ┌─────────────────┐                          │
│               │ Recipient List  │                          │
│               │                 │                          │
│               │ notifications   │                          │
│               │ 필드 확인       │                          │
│               └────────┬────────┘                          │
│                        │                                    │
│           ┌────────────┼────────────┐                      │
│           ▼            ▼            ▼                      │
│      ┌─────────┐ ┌─────────┐ ┌─────────┐                  │
│      │ Email   │ │  SMS    │ │  Push   │                  │
│      │ Service │ │ Service │ │ Service │                  │
│      └─────────┘ └─────────┘ └─────────┘                  │
│                                                             │
│  메시지 내용에 따라 받을 대상이 동적으로 결정됨               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 메시지 변환 패턴

### Message Translator

**메시지 형식을 변환**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                   Message Translator                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시스템 A (XML)                    시스템 B (JSON)          │
│  ┌─────────────┐  Translator  ┌─────────────┐             │
│  │ <user>      │             │ {           │             │
│  │   <name>    │  ────────▶  │   "name":   │             │
│  │     Kim     │             │     "Kim"   │             │
│  │   </name>   │             │ }           │             │
│  │ </user>     │             │             │             │
│  └─────────────┘             └─────────────┘             │
│                                                             │
│  사용 사례:                                                 │
│  • 레거시 시스템과 새 시스템 통합                            │
│  • 외부 API 응답을 내부 포맷으로 변환                        │
│  • 버전 간 호환성 유지                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Envelope Wrapper

**메시지에 메타데이터를 추가**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                    Envelope Wrapper                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  원본 메시지:                                                │
│  ┌───────────────────────────┐                             │
│  │ { "item": "plastic" }     │                             │
│  └───────────────────────────┘                             │
│                   │                                         │
│                   ▼ Wrap                                    │
│  ┌───────────────────────────────────────────────┐         │
│  │ {                                              │         │
│  │   "metadata": {                               │         │
│  │     "message_id": "abc-123",                  │         │
│  │     "timestamp": "2024-01-01T10:00:00Z",      │         │
│  │     "source": "scan-api",                     │         │
│  │     "trace_id": "xyz-789"                     │         │
│  │   },                                          │         │
│  │   "payload": { "item": "plastic" }            │         │
│  │ }                                              │         │
│  └───────────────────────────────────────────────┘         │
│                                                             │
│  추적, 로깅, 라우팅에 필요한 메타데이터 추가                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 메시지 처리 패턴

### Competing Consumers

**여러 소비자가 하나의 큐에서 경쟁적으로 메시지를 가져가** 처리한다.

```
┌─────────────────────────────────────────────────────────────┐
│                  Competing Consumers                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│               Queue                    Workers              │
│          ┌─────────────┐          ┌───────────┐           │
│          │ [M1][M2][M3]│─────────▶│ Worker 1  │           │
│          │ [M4][M5][M6]│─────────▶│ Worker 2  │           │
│          │ [M7][M8]... │─────────▶│ Worker 3  │           │
│          └─────────────┘          └───────────┘           │
│                                                             │
│  동작:                                                      │
│  • 각 워커가 큐에서 메시지를 "경쟁적으로" 가져감              │
│  • M1은 Worker 1이 가져가면 2, 3은 못 가져감                │
│  • 자동 부하 분산                                           │
│                                                             │
│  스케일링:                                                  │
│  • 워커 추가 → 처리량 증가                                  │
│  • 워커 제거 → 남은 워커가 처리                             │
│  • 큐가 버퍼 역할                                           │
│                                                             │
│  주의: 순서 보장 안 됨! (M2가 M1보다 먼저 처리될 수 있음)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Celery에서의 구현:**

```python
# 여러 워커가 같은 큐를 바라보면 자동으로 Competing Consumers
# 워커 3개 실행 = 3개의 Competing Consumers

celery -A app worker --concurrency=4 -Q scan_tasks
# 4개 스레드 × N개 워커 = 동시 처리 가능한 작업 수
```

### Idempotent Receiver

**같은 메시지를 여러 번 받아도 결과가 같도록** 보장한다.

이것이 왜 중요한가? 분산 시스템에서 메시지는 **중복 전달될 수 있다**:
- 네트워크 장애로 ACK 유실 → 재전송
- 워커 장애로 처리 중 실패 → 재시도
- 일시적 오류로 재처리

```
┌─────────────────────────────────────────────────────────────┐
│                   Idempotent Receiver                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  문제 상황:                                                  │
│  1. "포인트 100점 지급" 메시지 수신                          │
│  2. 포인트 지급 (100 → 200점)                               │
│  3. ACK 보내기 전 워커 다운                                 │
│  4. 브로커가 재전송                                         │
│  5. 포인트 또 지급 (200 → 300점)  ← 이중 지급!              │
│                                                             │
│  해결책: 멱등성 키                                           │
│  ┌───────────────────────────────────────────────┐         │
│  │ {                                              │         │
│  │   "idempotency_key": "grant-user1-20240101",  │         │
│  │   "action": "grant_points",                   │         │
│  │   "amount": 100                               │         │
│  │ }                                              │         │
│  └───────────────────────────────────────────────┘         │
│                                                             │
│  처리 로직:                                                 │
│  if already_processed(idempotency_key):                    │
│      return  # 이미 처리됨, 무시                            │
│  else:                                                      │
│      process(message)                                       │
│      mark_as_processed(idempotency_key)                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**구현 예시:**

```python
@celery_app.task(bind=True, acks_late=True)
def grant_points(self, user_id: str, amount: int, idempotency_key: str):
    # 1. 이미 처리된 메시지인지 확인
    if redis.exists(f"processed:{idempotency_key}"):
        logger.info(f"Already processed: {idempotency_key}")
        return  # 무시
    
    # 2. 포인트 지급
    db.execute(
        "UPDATE users SET points = points + %s WHERE id = %s",
        (amount, user_id)
    )
    
    # 3. 처리 완료 기록 (TTL 24시간)
    redis.setex(f"processed:{idempotency_key}", 86400, "1")
```

---

## 오류 처리 패턴

### Dead Letter Channel

**처리에 실패한 메시지를 별도 채널로 보관**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                   Dead Letter Channel                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정상 흐름:                                                  │
│  Queue → Worker → 성공 → ACK                               │
│                                                             │
│  실패 흐름:                                                  │
│  Queue → Worker → 실패 → 재시도(3회) → 계속 실패            │
│                              │                              │
│                              ▼                              │
│                    ┌─────────────────┐                     │
│                    │ Dead Letter     │                     │
│                    │ Queue (DLQ)     │                     │
│                    │                 │                     │
│                    │ [실패한 M1]     │                     │
│                    │ [실패한 M5]     │                     │
│                    │ [실패한 M9]     │                     │
│                    └─────────────────┘                     │
│                              │                              │
│                              ▼                              │
│                    나중에 수동 분석 / 재처리                  │
│                                                             │
│  장점:                                                      │
│  • 실패 메시지 유실 방지                                    │
│  • 문제 메시지 분석 가능                                    │
│  • 메인 큐 막힘 방지                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Celery에서의 구현:**

```python
# 실패한 작업을 DLQ로 보내는 설정
celery_app.conf.task_routes = {
    'tasks.*': {
        'queue': 'default',
        'dead_letter_exchange': 'dlx',
        'dead_letter_routing_key': 'dlq'
    }
}

# 재시도 설정
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(TemporaryError,)
)
def risky_task(self, data):
    try:
        process(data)
    except PermanentError:
        # 영구적 오류는 재시도하지 않고 DLQ로
        raise Reject(requeue=False)
```

### Retry Pattern

**일시적 오류는 재시도**로 해결한다.

```
┌─────────────────────────────────────────────────────────────┐
│                      Retry Pattern                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  지수 백오프 (Exponential Backoff):                          │
│                                                             │
│  시도 1: 즉시 → 실패                                        │
│  시도 2: 1초 후 → 실패                                      │
│  시도 3: 2초 후 → 실패                                      │
│  시도 4: 4초 후 → 실패                                      │
│  시도 5: 8초 후 → 성공!                                     │
│                                                             │
│  왜 지수 백오프?                                             │
│  • 서버가 과부하 상태일 때 바로 재시도하면 상황 악화          │
│  • 점점 늦게 재시도하여 서버 회복 시간 확보                  │
│  • 일시적 오류는 대부분 시간이 지나면 해결됨                 │
│                                                             │
│  Jitter (무작위성) 추가:                                     │
│  • 여러 클라이언트가 동시에 재시도하면 또 과부하             │
│  • 재시도 시간에 랜덤 요소 추가하여 분산                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**구현 예시:**

```python
@celery_app.task(
    bind=True,
    autoretry_for=(TemporaryError, TimeoutError),
    retry_backoff=True,  # 지수 백오프 활성화
    retry_backoff_max=600,  # 최대 10분
    retry_jitter=True,  # 랜덤 지터 추가
    max_retries=5
)
def call_external_api(self, data):
    response = requests.post("https://api.example.com", json=data, timeout=30)
    response.raise_for_status()
    return response.json()
```

---

## 시스템 관리 패턴

### Message Store

**모든 메시지를 저장**하여 감사 추적과 디버깅에 활용한다.

```
┌─────────────────────────────────────────────────────────────┐
│                     Message Store                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Producer → Queue → Consumer                                │
│              │                                              │
│              │ 복사                                         │
│              ▼                                              │
│        ┌──────────────┐                                    │
│        │ Message Store │                                    │
│        │              │                                    │
│        │ 모든 메시지   │                                    │
│        │ 영구 저장    │                                    │
│        └──────────────┘                                    │
│                                                             │
│  활용:                                                      │
│  • "1월 15일 이 주문 메시지 어떻게 처리됐지?"               │
│  • "이 이벤트가 언제 발행됐지?"                             │
│  • 문제 발생 시 전체 흐름 추적                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Wire Tap

**메시지 흐름을 방해하지 않고 모니터링**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                       Wire Tap                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ┌───────────────┐                       │
│                    │   Wire Tap    │                       │
│                    │  (모니터링)   │                       │
│                    └───────┬───────┘                       │
│                            │ 복사                          │
│  Producer ─────────────────┼─────────────────▶ Consumer    │
│                            │                               │
│                    원본은 그대로 전달                       │
│                    복사본만 Wire Tap으로                    │
│                                                             │
│  사용 사례:                                                 │
│  • 메시지 처리량 모니터링                                   │
│  • 특정 패턴 메시지 로깅                                    │
│  • 실시간 분석                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 패턴 조합: 실전 예시

실제 시스템에서는 여러 패턴을 조합해서 사용한다:

```
┌─────────────────────────────────────────────────────────────┐
│              AI 분류 작업 처리 시스템                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 요청 수신                                               │
│  ┌──────────┐                                              │
│  │ Scan API │── Message ──▶ [Envelope Wrapper]            │
│  └──────────┘              메타데이터 추가                 │
│                                  │                         │
│  2. 라우팅                        ▼                         │
│                          [Content-Based Router]            │
│                         /         │         \              │
│                        ▼          ▼          ▼             │
│                   high-pri    normal     low-pri           │
│                    queue      queue       queue            │
│                                                             │
│  3. 처리                                                    │
│                          [Competing Consumers]             │
│                    Worker1, Worker2, Worker3               │
│                                  │                         │
│  4. 오류 처리                     ▼                         │
│                 성공 ◀───── [Idempotent Receiver]          │
│                                  │                         │
│                          실패 (3회 재시도 후)              │
│                                  │                         │
│                                  ▼                         │
│                          [Dead Letter Queue]               │
│                                                             │
│  5. 결과 브로드캐스트                                       │
│                          [Publish-Subscribe]               │
│                         /         │         \              │
│                        ▼          ▼          ▼             │
│                   Analytics   Rewards   Notification       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 패턴 정리

| 카테고리 | 패턴 | 설명 | 사용 사례 |
|----------|------|------|----------|
| **채널** | Point-to-Point | 하나의 소비자에게 전달 | 작업 분배 |
| | Publish-Subscribe | 모든 구독자에게 복사 | 이벤트 브로드캐스트 |
| **라우팅** | Content-Based Router | 내용 기반 라우팅 | 우선순위 큐 |
| | Recipient List | 동적 수신자 결정 | 알림 서비스 |
| **처리** | Competing Consumers | 경쟁적 소비 | 부하 분산 |
| | Idempotent Receiver | 중복 처리 방지 | 모든 중요 작업 |
| **오류** | Dead Letter Channel | 실패 메시지 보관 | 오류 분석 |
| | Retry | 재시도 | 일시적 오류 처리 |

---

## 더 읽을 자료

- [Enterprise Integration Patterns 웹사이트](https://www.enterpriseintegrationpatterns.com/)
- [RabbitMQ Tutorials](https://www.rabbitmq.com/getstarted.html) - 패턴 구현 예제
- [Celery Task Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)

---

## 부록: Eco² 적용 포인트

### 전환 계획: gRPC → Command-Event Separation

Eco²는 EIP 패턴을 **Command-Event Separation** 아키텍처에 적용한다.

```
┌─────────────────────────────────────────────────────────────┐
│         Eco² Command-Event Separation + EIP 패턴            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Command (RabbitMQ)              Event (Kafka)              │
│  ──────────────────              ─────────────              │
│                                                             │
│  • Point-to-Point Channel        • Pub/Sub Channel          │
│  • Competing Consumers           • Message Store (영구)     │
│  • Content-Based Router          • Wire Tap (모니터링)      │
│  • Dead Letter Channel           • Idempotent Receiver      │
│  • Retry Pattern                 • Envelope Wrapper         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Scan Request                      │   │
│  │                         │                            │   │
│  │    ┌────────────────────┼────────────────────┐      │   │
│  │    │ Envelope Wrapper   │                    │      │   │
│  │    │ (trace_id, user_id)                     │      │   │
│  │    └────────────────────┼────────────────────┘      │   │
│  │                         │                            │   │
│  │    ┌────────────────────▼────────────────────┐      │   │
│  │    │           Content-Based Router          │      │   │
│  │    │              (우선순위 분류)            │      │   │
│  │    └──────┬─────────────┬─────────────┬──────┘      │   │
│  │           ▼             ▼             ▼             │   │
│  │    high-priority   normal-queue   low-priority      │   │
│  │           │             │             │             │   │
│  │           └─────────────┼─────────────┘             │   │
│  │                         ▼                           │   │
│  │    ┌────────────────────────────────────────┐      │   │
│  │    │         Competing Consumers            │      │   │
│  │    │     (Celery Workers × N)               │      │   │
│  │    └────────────────────┬───────────────────┘      │   │
│  │                         │                           │   │
│  │    실패 시              │ 성공 시                   │   │
│  │    ┌──────────┐         ▼                           │   │
│  │    │   DLQ    │    Event Store + Outbox            │   │
│  │    │ (Retry)  │         │                           │   │
│  │    └──────────┘         │ CDC                       │   │
│  │                         ▼                           │   │
│  │    ┌────────────────────────────────────────┐      │   │
│  │    │      Kafka (Pub/Sub + Message Store)   │      │   │
│  │    └──────────────────┬─────────────────────┘      │   │
│  │                       │                             │   │
│  │       ┌───────────────┼───────────────┐            │   │
│  │       ▼               ▼               ▼            │   │
│  │  Character       My Service       Analytics        │   │
│  │  Consumer        Consumer         Consumer         │   │
│  │  (Idempotent)    (Projection)    (Wire Tap)       │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### EIP 패턴별 적용 위치

| 패턴 | RabbitMQ (Command) | Kafka (Event) |
|------|-------------------|---------------|
| **Point-to-Point** | AI Task 분배 | - |
| **Pub/Sub** | - | 도메인 이벤트 브로드캐스트 |
| **Competing Consumers** | Celery Workers | Consumer Groups |
| **Content-Based Router** | Exchange Routing | - |
| **Dead Letter Channel** | RabbitMQ DLQ | Kafka DLQ Topic |
| **Idempotent Receiver** | Celery acks_late | Event ID 체크 |
| **Envelope Wrapper** | Celery Task headers | Kafka headers |
| **Message Store** | - | Event Store (영구 보존) |
| **Wire Tap** | - | Analytics Consumer |
| **Retry Pattern** | Celery retry | Kafka Offset 재처리 |

### AI 파이프라인 EIP 패턴 조합

```python
# domains/scan/tasks/ai_pipeline.py

# 1. Envelope Wrapper - 메타데이터 포함
@celery_app.task(
    bind=True,
    max_retries=3,  # 3. Retry Pattern
    acks_late=True,  # 4. Idempotent Receiver 준비
)
def process_image(self, task_id: str, image_url: str, 
                  trace_id: str, user_id: str):  # Envelope
    """
    EIP 패턴 적용:
    - Point-to-Point: 하나의 Worker가 처리
    - Competing Consumers: 여러 Worker 중 하나가 선택
    - Envelope Wrapper: trace_id, user_id 전달
    - Retry Pattern: 실패 시 지수 백오프 재시도
    - Dead Letter: 최종 실패 시 DLQ로 이동
    """
    try:
        # 2. Content-Based Router 결과 처리
        classification = vision_api.analyze(image_url)
        answer = llm_api.generate(classification)
        
        # 5. Event Store (Message Store 패턴)
        async with db.begin():
            await event_store.append(ScanCompleted(
                task_id=task_id,
                user_id=user_id,
                trace_id=trace_id,  # Envelope 유지
                classification=classification,
                answer=answer,
            ))
        
        # → CDC → Kafka → Pub/Sub 패턴으로 브로드캐스트
        
    except Exception as exc:
        # Dead Letter Channel로 이동 (max_retries 초과 시)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### Kafka Consumer EIP 패턴 적용

```python
# domains/character/consumers/event_consumer.py

class CharacterEventConsumer:
    """
    EIP 패턴 적용:
    - Pub/Sub: Kafka Topic 구독
    - Competing Consumers: Consumer Group 내 분배
    - Idempotent Receiver: event_id 중복 체크
    - Envelope Wrapper: trace_id로 분산 추적
    """
    
    async def handle(self, message: KafkaMessage):
        # Envelope Wrapper에서 메타데이터 추출
        event_id = message.headers.get('event_id')
        trace_id = message.headers.get('trace_id')
        
        # Idempotent Receiver
        if await self.is_processed(event_id):
            logger.info(f"Already processed: {event_id}")
            return
        
        # OpenTelemetry 컨텍스트 복원 (Envelope)
        with tracer.start_span(f"consume", trace_id=trace_id):
            event = self.deserialize(message)
            await self.grant_reward(event)
            await self.mark_processed(event_id)
```

### AS-IS vs TO-BE

| 패턴 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-----------------------------------|
| **Point-to-Point** | gRPC 직접 호출 | RabbitMQ Task Queue |
| **Pub/Sub** | 없음 | Kafka Topic (브로드캐스트) |
| **Competing Consumers** | gRPC LB | Celery Workers + Kafka Consumer Groups |
| **Content-Based Router** | gRPC Interceptor | RabbitMQ Exchange Routing |
| **Dead Letter** | 에러 로깅만 | RabbitMQ DLQ + Kafka DLQ Topic |
| **Idempotent Receiver** | Redis TTL | Event ID + DB 기록 |
| **Envelope Wrapper** | gRPC Metadata | Task headers + Kafka headers |
| **Message Store** | 없음 | Event Store + Kafka (영구 보존) |
| **Retry Pattern** | Circuit Breaker | Celery retry + Kafka Offset |
