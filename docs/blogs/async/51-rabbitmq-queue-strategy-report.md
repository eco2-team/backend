# RabbitMQ Queue Strategy Report

> 작성일: 2026-01-08
> 최종 수정: 2026-01-09
> 목적: Celery Worker Queue 전략 정립 및 Topology CR 일원화
> 관련 트러블슈팅: [52-fanout-exchange-migration-troubleshooting.md](./52-fanout-exchange-migration-troubleshooting.md)

## 1. 현황 분석

### 1.1 현재 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        현재 상태                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Python Celery 설정:                                            │
│    task_default_exchange = ""  (AMQP Default Exchange)          │
│                                                                 │
│  Topology CR:                                                   │
│    exchanges.yaml → Named Exchange 정의 (scan.direct 등)        │
│    bindings.yaml → Named Exchange Binding 정의                  │
│    queues.yaml   → Queue + DLX 설정                             │
│                                                                 │
│  ⚠️ 불일치: Python은 Default Exchange, CR은 Named Exchange      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Worker 목록

| Worker | 아키텍처 | Exchange | 소비 큐 |
|--------|----------|----------|---------|
| scan_worker | apps/ | Default (`""`) | scan.vision, scan.rule, scan.answer, scan.reward |
| character_worker | apps/ | Default (`""`) | character.match, character.save_ownership, character.grant_default |
| character-match-worker | apps/ | Default (`""`) | character.match |
| users_worker | apps/ | Default (`""`) | users.save_character |
| auth_worker | apps/ | Fanout (`blacklist.events`) | auth.blacklist |

### 1.3 문제점 식별

#### 문제 1: Exchange 설정 불일치
```yaml
# Topology CR (사용되지 않음)
exchanges.yaml:
  - scan.direct (Direct)
  - character.direct (Direct)
  - users.direct (Direct)

# Python (실제 사용)
task_default_exchange = ""  # AMQP Default Exchange
```

#### 문제 2: 이중 Publish
```python
# scan.reward 태스크에서 현재 구현
celery_app.send_task("character.save_ownership", args=[...])  # 1번째 publish
celery_app.send_task("users.save_character", args=[...])      # 2번째 publish

# 문제:
# - 동일 데이터를 2번 네트워크 전송
# - 원자성 미보장 (하나만 실패 가능)
# - 의도 불명확 (같은 이벤트인지 다른 이벤트인지)
```

---

## 2. Exchange 타입 비교

### 2.1 AMQP Default Exchange (`""`)

```
Producer
   │
   │ routing_key = "scan.vision"
   ▼
┌──────────────────┐
│ Default Exchange │  (암묵적 바인딩: routing_key = queue_name)
│       ""         │
└──────────────────┘
         │
         ▼
   ┌─────────────┐
   │ scan.vision │
   └─────────────┘
```

| 특성 | 설명 |
|------|------|
| Binding 필요 | ❌ 자동 (모든 큐가 자동 바인딩) |
| routing_key | 큐 이름과 동일해야 함 (강제) |
| 유연성 | 낮음 (1:1 고정) |
| 용도 | 단순한 point-to-point |

### 2.2 Named Direct Exchange

```
Producer
   │
   │ exchange="reward.direct", routing_key="reward.complete"
   ▼
┌──────────────────┐
│  reward.direct   │  (명시적 바인딩 필요)
└──────────────────┘
         │
         │  Binding #1: reward.complete → character.save_ownership
         │  Binding #2: reward.complete → users.save_character
         │
         ├───────────────────────────┐
         ▼                           ▼
┌─────────────────────┐   ┌─────────────────────┐
│character.save_owner │   │ users.save_character│
└─────────────────────┘   └─────────────────────┘
```

| 특성 | 설명 |
|------|------|
| Binding 필요 | ✅ 명시적 정의 |
| routing_key | 자유 정의 (큐 이름과 무관) |
| 유연성 | 높음 (1:N 가능) |
| 용도 | 도메인 분리, 다중 Consumer |

### 2.3 Fanout Exchange

```
Producer
   │
   │ (routing_key 무시)
   ▼
┌───────────────────┐
│ blacklist.events  │  (모든 바인딩 큐에 브로드캐스트)
│  (type: fanout)   │
└───────────────────┘
         │
   ┌─────┴─────┬─────────────┐
   ▼           ▼             ▼
┌────────┐ ┌────────┐ ┌────────┐
│ Pod 1  │ │ Pod 2  │ │ Pod 3  │
└────────┘ └────────┘ └────────┘
```

| 특성 | 설명 |
|------|------|
| Binding 필요 | ✅ (큐를 Exchange에 바인딩) |
| routing_key | 무시됨 |
| 메시지 전달 | 1:All (모든 바인딩 큐) |
| 용도 | 이벤트 브로드캐스트, 캐시 동기화 |

### 2.4 Topic Exchange

```
Producer
   │
   │ routing_key="scan.vision.high"
   ▼
┌───────────────────┐
│   scan.topic      │
└───────────────────┘
         │
         │  Binding: "scan.vision.*" → priority_queue
         │  Binding: "scan.#" → all_scan_queue
         │
         ├───────────────────────────┐
         ▼                           ▼
┌─────────────────┐       ┌─────────────────┐
│  priority_queue │       │  all_scan_queue │
└─────────────────┘       └─────────────────┘
```

| 특성 | 설명 |
|------|------|
| Binding 필요 | ✅ (패턴 기반) |
| routing_key | 와일드카드 지원 (`*`, `#`) |
| 유연성 | 매우 높음 |
| 용도 | 복잡한 라우팅 패턴 |

---

## 3. Exchange 선택 가이드

| 패턴 | 권장 Exchange | 예시 |
|------|---------------|------|
| Task → 1 Queue | Default (`""`) | 단순 백그라운드 작업 |
| Event → N Queues (고정) | **Fanout** ✅ | reward → character + users |
| Event → N Queues (패턴) | Topic | `scan.*` → 여러 큐 |
| Event → All Subscribers | Fanout | 캐시 무효화 브로드캐스트 |

> **2026-01-09 업데이트**: 초기 설계는 Named Direct Exchange였으나, 실제 구현 과정에서 **Fanout Exchange**로 전환.
> - Celery `send_task()`의 `exchange` 파라미터가 `task_routes` 설정에 의해 무시되는 문제 발견
> - Fanout은 `routing_key` 자체를 무시하므로 구현이 단순해짐

---

## 4. 권장 아키텍처

### 4.1 Exchange 구조 (2026-01-09 업데이트)

```
┌─────────────────────────────────────────────────────────────────┐
│                    최종 Exchange 구조                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ scan.direct │  │reward.events│  │ blacklist.  │             │
│  │  (Direct)   │  │  (Fanout)   │  │   events    │             │
│  │             │  │ ✅ 변경됨   │  │  (Fanout)   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         │                │                │                     │
│    ┌────┴────┐      ┌────┴────┐      ┌────┴────┐               │
│    │ 4 큐    │      │ 2 큐    │      │ N 큐    │               │
│    └─────────┘      └─────────┘      └─────────┘               │
│                                                                 │
│  ┌─────────────┐                                               │
│  │     dlx     │  Dead Letter Exchange                         │
│  │  (Direct)   │                                               │
│  └─────────────┘                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

> **변경 이유**: `reward.direct` (Direct) → `reward.events` (Fanout)
> - Direct Exchange는 routing_key 매칭 필요 → Celery의 exchange 파라미터 무시 문제
> - Fanout Exchange는 routing_key 무시 → kombu Producer로 직접 publish하면 확실히 동작

### 4.2 상세 Binding 맵 (2026-01-09 업데이트)

```yaml
# scan.direct Exchange (미사용 - Default Exchange로 처리)
# Celery가 task_default_exchange="" 사용

# reward.events Exchange (Fanout) ✅ 최종
reward.events:
  - → character.save_ownership  # routing_key 무시
  - → users.save_character      # 모든 바인딩 큐로 브로드캐스트

# blacklist.events Exchange (Fanout)
blacklist.events:
  - → auth.blacklist
  - → ext-authz-cache-* (미래 확장)

# character.cache Exchange (Fanout)
character.cache:
  - → character-match-worker 캐시 동기화
```

### 4.3 데이터 흐름 (2026-01-09 업데이트)

```
┌────────────────────────────────────────────────────────────────────┐
│                       Reward 처리 흐름                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  scan.reward 태스크 완료                                           │
│       │                                                            │
│       │ kombu.Producer.publish()                                   │
│       │ (Celery send_task 대신 직접 publish)                       │
│       ▼                                                            │
│  ┌─────────────────┐                                              │
│  │  reward.events  │  Fanout Exchange                             │
│  │ (type: fanout)  │  routing_key 무시!                           │
│  └─────────────────┘                                              │
│       │                                                            │
│       │  자동 복제 (Fanout 특성)                                  │
│       │                                                            │
│       ├───────────────────────────────────────────┐                │
│       ▼                                           ▼                │
│  ┌─────────────────────┐           ┌─────────────────────┐        │
│  │character.save_owner │           │ users.save_character│        │
│  │       ship 큐       │           │        큐           │        │
│  └─────────────────────┘           └─────────────────────┘        │
│       │                                           │                │
│       ▼                                           ▼                │
│  character-worker                           users-worker           │
│  @task(name="reward.character")            @task(name="reward.character")
│  (gevent pool, sync DB)                    (prefork pool, async DB)│
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 5. Topology CR 변경 사항 (2026-01-09 최종)

### 5.1 exchanges.yaml 수정

```yaml
# 최종 구성
- dlx (Direct)           # Dead Letter Exchange
- blacklist.events (Fanout)  # 인증 캐시 브로드캐스트
- character.cache (Fanout)   # 캐릭터 캐시 동기화
- reward.events (Fanout)     # ✅ 신규 (Direct → Fanout 전환)

# 삭제 (사용 안 함)
- scan.direct    # Celery는 Default Exchange 사용
- character.direct  # Celery는 Default Exchange 사용
- users.direct      # reward.events로 대체
- reward.direct     # reward.events로 대체 (Fanout 전환)
- celery (Topic)    # Default Exchange 사용
```

### 5.2 bindings.yaml 수정

```yaml
# reward.events (Fanout) → 다중 큐
# ⚠️ Fanout은 routingKey 무시
---
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: reward-to-character-ownership
  namespace: rabbitmq
spec:
  source: reward.events       # Fanout Exchange
  destination: character.save_ownership
  destinationType: queue
  # routingKey 없음 - Fanout은 무시
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
    namespace: rabbitmq
---
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: reward-to-users-save-character
  namespace: rabbitmq
spec:
  source: reward.events       # Fanout Exchange
  destination: users.save_character
  destinationType: queue
  # routingKey 없음 - Fanout은 무시
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
    namespace: rabbitmq
```

### 5.3 Python 코드 변경

```python
# 기존 (2번 publish - 비권장)
celery_app.send_task("character.save_ownership", args=[...])
celery_app.send_task("users.save_character", args=[...])

# ❌ 시도했으나 실패 (Celery exchange 파라미터 무시됨)
celery_app.send_task(
    "reward.character",
    exchange="reward.direct",  # task_routes에 의해 무시됨!
    routing_key="reward.character",
)

# ✅ 최종 구현 (kombu Producer + Fanout)
from kombu import Connection, Exchange, Producer
from kombu.pools import producers

def _dispatch_save_tasks(user_id: str, reward: dict) -> None:
    with Connection(celery_app.broker_connection().as_uri()) as conn:
        exchange = Exchange("reward.events", type="fanout", durable=True)
        with producers[conn].acquire(block=True) as producer:
            producer.publish(
                {
                    "user_id": user_id,
                    "character_id": reward["character_id"],
                    "character_code": reward.get("character_code", ""),
                    "character_name": reward.get("name", ""),
                    "source": "scan",
                },
                exchange=exchange,
                routing_key="",  # Fanout은 무시
                serializer="json",
            )
```

### 5.4 왜 Named Direct가 아닌 Fanout인가?

| 관점 | Named Direct | Fanout |
|------|--------------|--------|
| routing_key | 필수 (매칭 기반) | 무시됨 |
| Celery 호환 | ❌ `send_task()` exchange 무시 | ✅ kombu 직접 사용 |
| 바인딩 | routing_key 별로 지정 | 큐만 바인딩 |
| 구현 복잡도 | 높음 (routing_key 관리) | 낮음 |
| 확장성 | routing_key 추가 필요 | 바인딩만 추가 |

**결론**: Celery의 `send_task()`가 `exchange` 파라미터를 무시하는 문제로 인해, `kombu.Producer`로 직접 publish + **Fanout Exchange**가 가장 단순하고 확실한 해결책.

---

## 6. 책임 분리 원칙

### 6.1 현재 (권장)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Topology CR (Source of Truth)                │
│              workloads/rabbitmq/base/topology/                  │
├─────────────────────────────────────────────────────────────────┤
│  exchanges.yaml  │  Exchange 정의 (타입, durability)            │
│  queues.yaml     │  Queue 정의 (TTL, DLX, arguments)            │
│  bindings.yaml   │  Exchange → Queue 바인딩                     │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Python Celery 설정                           │
├─────────────────────────────────────────────────────────────────┤
│  task_routes     │  Task → Queue 매핑 (애플리케이션 레벨)       │
│                  │  ⚠️ CR로 위임 불가 (Python 코드 필수)        │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 왜 task_routes는 CR로 위임 불가?

```python
# task_routes는 Python 함수와 큐를 연결
@celery_app.task(name="scan.vision")
def process_vision(image_data):
    ...

# 이 매핑은 Python 코드에서만 가능
TASK_ROUTES = {
    "scan.vision": {"queue": "scan.vision"},  # 함수 → 큐
}
```

**Celery 동작 방식:**
1. `@task` 데코레이터로 함수를 태스크로 등록
2. `task_routes`로 태스크 이름 → 큐 매핑
3. `send_task()` 시 routing_key 결정

**CR이 할 수 있는 것:**
- Exchange 생성
- Queue 생성 (arguments 포함)
- Exchange → Queue 바인딩

**CR이 할 수 없는 것:**
- Python 함수와 큐 연결 (애플리케이션 레벨)

---

## 7. 마이그레이션 계획

### Phase 1: CR 정리 (Low Risk) ✅ 완료
- [x] 사용하지 않는 Exchange 제거 (celery topic)
- [x] users.direct → reward.direct로 변경
- [x] Binding 정리

### Phase 2: reward.direct 도입 (Medium Risk) ✅ 완료 → ❌ 롤백
- [x] reward.direct Exchange CR 추가
- [x] Binding CR 추가 (reward.character → 2개 큐)
- [x] Python 코드 변경 (1번 publish)
- ❌ **문제 발견**: Celery `send_task()`의 `exchange` 파라미터가 `task_routes`에 의해 무시됨

### Phase 3: Fanout 전환 (Medium Risk) ✅ 완료
- [x] reward.direct → reward.events (Fanout) 전환
- [x] routingKey 제거한 Binding CR 재생성
- [x] `kombu.Producer` 직접 사용으로 코드 변경
- [x] Worker에 `reward.character` task 추가 (`reward_event_task.py`)
- [x] E2E 테스트 완료

### Phase 4: 전체 Named Exchange 마이그레이션 (Optional) - 보류
- [ ] scan 파이프라인도 Named Exchange 사용
- [ ] Default Exchange 의존성 제거
- **상태**: 현재 Default Exchange로 정상 동작 중, 불필요한 복잡성 회피

---

## 8. 구현 결과

### 8.1 변경된 파일 (2026-01-09 최종)

| 파일 | 변경 내용 |
|------|----------|
| `workloads/rabbitmq/base/topology/exchanges.yaml` | `reward.events` (Fanout) 추가, 레거시 삭제 |
| `workloads/rabbitmq/base/topology/bindings.yaml` | `reward.events` → 2개 큐 바인딩 (routingKey 없음) |
| `workloads/rabbitmq/base/topology/queues.yaml` | `celery-default-queue` 추가 |
| `apps/scan_worker/application/classify/steps/reward_step.py` | `kombu.Producer`로 Fanout publish |
| `apps/scan_worker/setup/celery.py` | `task_queues` 정의, `no_declare=True` |
| `apps/character_worker/presentation/tasks/reward_event_task.py` | `reward.character` 핸들러 (신규, sync DB) |
| `apps/character_worker/setup/celery.py` | `reward.character` route, `worker_ready` signal |
| `apps/users_worker/presentation/tasks/reward_event_task.py` | `reward.character` 핸들러 (신규, async DB) |
| `apps/users_worker/setup/celery.py` | `reward.character` route, `no_declare=True` |
| `workloads/domains/*/base/deployment.yaml` | `POSTGRES_HOST` 수정, Celery 명령어 업데이트 |

### 8.2 최종 아키텍처 (2026-01-09 업데이트: Fanout 전환)

```
scan.reward 완료 (재활용폐기물 + character match 성공)
      │
      │ kombu.Producer.publish(exchange='reward.events')
      │ (1번만 publish! routing_key 무시)
      ▼
┌─────────────────────┐
│   reward.events     │  Fanout Exchange (type: fanout)
│                     │  모든 바인딩 큐에 브로드캐스트
└─────────────────────┘
      │
      │  Binding #1: → character.save_ownership
      │  Binding #2: → users.save_character
      │  (routing_key 무시, 자동 복제)
      │
      ├───────────────────────────────────────────┐
      ▼                                           ▼
┌─────────────────────┐            ┌─────────────────────┐
│character.save_owner │            │ users.save_character│
│       ship 큐       │            │        큐           │
└─────────────────────┘            └─────────────────────┘
      │                                           │
      ▼                                           ▼
character_worker                           users_worker
@task(name="reward.character")            @task(name="reward.character")
→ character.character_ownerships          → users.user_characters
  (동기 DB: gevent pool 호환)               (비동기 DB: prefork pool)
```

**왜 Fanout인가?**
- Direct Exchange는 `routing_key` 기반 라우팅 → 1:N 시 동일 key로 다중 바인딩 필요
- Fanout Exchange는 `routing_key` 무시 → 바인딩만으로 1:N 브로드캐스트
- 구현 단순성: Celery `send_task()`의 `exchange` 파라미터 무시 이슈 우회

### 8.3 핵심 패턴: 동일 Task 이름, 다른 구현

```python
# character_worker/presentation/tasks/reward_event_task.py
@celery_app.task(name="reward.character", queue="character.save_ownership")
def reward_character_task(requests):
    # character DB 저장 로직

# users_worker/presentation/tasks/reward_event_task.py
@celery_app.task(name="reward.character", queue="users.save_character")
def reward_character_task(requests):
    # users DB 저장 로직
```

- 동일한 task 이름 (`reward.character`)
- 각 Worker가 자신의 큐에서만 메시지 수신
- RabbitMQ Binding이 메시지 복제 담당

---

## 9. 결론

### 9.1 핵심 결정 (2026-01-09 최종)

| 항목 | 초기 결정 | 최종 결정 | 변경 이유 |
|------|----------|----------|----------|
| 큐 생성 | Topology CR | Topology CR | 인프라 일원화, GitOps |
| Exchange 생성 | Topology CR | Topology CR | 인프라 일원화 |
| Binding | Topology CR | Topology CR | 1:N 라우팅 지원 |
| task_routes | Python | Python | 애플리케이션 레벨, CR 불가 |
| 다중 Consumer 패턴 | **Named Direct** | **Fanout** ✅ | Celery `send_task()` exchange 무시 문제 |
| Publish 방식 | Celery `send_task()` | **kombu Producer** ✅ | Named Exchange 직접 제어 필요 |

### 9.2 왜 Named Direct → Fanout?

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Named Direct 실패 원인                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  celery_app.send_task(                                              │
│      "reward.character",                                            │
│      exchange="reward.direct",  ← task_routes에 의해 무시됨!        │
│      routing_key="reward.character",                                │
│  )                                                                  │
│                                                                     │
│  Celery 내부 동작:                                                  │
│  1. task_routes에서 "reward.character" 검색                         │
│  2. 없으면 task_default_exchange="" (AMQP Default) 사용            │
│  3. exchange 파라미터 무시 → Default Exchange로 전송               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    Fanout 해결책                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  from kombu import Exchange, Producer                               │
│  from kombu.pools import producers                                  │
│                                                                     │
│  exchange = Exchange("reward.events", type="fanout", durable=True)  │
│  with producers[conn].acquire(block=True) as producer:              │
│      producer.publish(payload, exchange=exchange, routing_key="")   │
│                                                                     │
│  장점:                                                              │
│  1. Celery 우회 → exchange 파라미터 직접 제어                       │
│  2. Fanout은 routing_key 무시 → 바인딩만으로 1:N 브로드캐스트       │
│  3. 구현 단순 → 새 Consumer 추가 시 Binding CR만 추가               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.3 기대 효과

| 측면 | Before | After |
|------|--------|-------|
| 네트워크 효율 | 2번 publish | 1번 publish |
| 원자성 | 보장 안 됨 | RabbitMQ가 보장 |
| 의도 명확성 | 불명확 | "이벤트 → 다중 서비스" 패턴 명시 |
| 확장성 | 코드 수정 필요 | Binding CR만 추가 |
| 운영 | Exchange별 모니터링 불가 | Fanout Exchange로 트래픽 분리 |
| Celery 호환 | ❌ exchange 무시 | ✅ kombu 직접 사용 |

---

## 10. 참고 자료

- [RabbitMQ Messaging Topology Operator](https://github.com/rabbitmq/messaging-topology-operator)
- [Celery Task Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)
- [AMQP Exchange Types](https://www.rabbitmq.com/tutorials/amqp-concepts.html#exchanges)
- [kombu Producer API](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.html#producer)
- [CloudAMQP - RabbitMQ for Beginners](https://www.cloudamqp.com/blog/part1-rabbitmq-for-beginners-what-is-rabbitmq.html)

---

## 부록 A: E2E 테스트 결과 (2026-01-09 18:30)

### 테스트 조건
- **엔드포인트**: `POST https://api.dev.growbin.app/api/v1/scan`
- **이미지**: 에어팟 케이스
- **테스트 횟수**: 4회

### 결과

| # | scan 파이프라인 | character.match | reward.character (Fanout) |
|---|----------------|-----------------|---------------------------|
| 1 | ✅ 완료 | ✅ 일렉 매칭 | ✅ character-worker + users-worker |
| 2 | ✅ 완료 | ❌ (일반폐기물 분류) | ❌ |
| 3 | ✅ 완료 | ❌ (일반폐기물 분류) | ❌ |
| 4 | ✅ 완료 | ❌ (일반폐기물 분류) | ❌ |

### 검증 완료

```
✅ scan.vision → scan.rule → scan.answer → scan.reward (4/4 성공)
✅ character.match (재활용 품목일 때만 매칭, 정상 동작)
✅ reward.events (Fanout) → character.save_ownership + users.save_character (1:N 브로드캐스트)
```

---

## 부록 B: 트러블슈팅 기록

상세 트러블슈팅 내용은 [52-fanout-exchange-migration-troubleshooting.md](./52-fanout-exchange-migration-troubleshooting.md) 참조.

| Phase | 문제 | 해결 |
|-------|------|------|
| 1 | `PreconditionFailed` x-message-ttl | `no_declare=True` |
| 1 | `ImproperlyConfigured` Queue 누락 | `task_queues` 정의 |
| 2 | Queue 바인딩이 `celery(direct)` | `exchange=""` 명시 |
| 2 | `Character cache not loaded` | `worker_ready` signal 추가 |
| 2 | `POSTGRES_HOST` 잘못된 서비스 이름 | 서비스 이름 수정 |
| 3 | Celery `exchange` 파라미터 무시 | kombu Producer 직접 사용 |
| 3 | `struct.error` 직렬화 오류 | `serializer="json"` 명시 |
| 4 | `character_code` 컬럼 없음 | Migration 수동 적용 |
| 4 | gevent + asyncio 충돌 | sync DB로 변경 |

