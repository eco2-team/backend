# RabbitMQ Queue Strategy Architecture Decision Report

> **작성일**: 2026-01-09  
> **상태**: Implemented ✅  
> **관련 서비스**: scan_worker, character_worker, users_worker  
> **관련 문서**: [51-rabbitmq-queue-strategy-report.md](../blogs/async/51-rabbitmq-queue-strategy-report.md)

---

## 📋 Executive Summary

본 ADR은 Eco² 백엔드의 RabbitMQ 큐 전략에 대한 아키텍처 의사결정을 문서화합니다.

**핵심 결정사항:**
1. **1:N 이벤트 라우팅**: Named Direct Exchange → **Fanout Exchange** 전환
2. **Topology 관리**: Celery 선언 → **Kubernetes CR(Custom Resource)** 일원화
3. **Publish 방식**: Celery `send_task()` → **kombu Producer** 직접 사용

---

## 1. 배경

### 1.1 문제 상황

scan 파이프라인의 `reward` 단계 완료 시, 동일한 이벤트를 두 개의 서로 다른 Worker에 전달해야 하는 요구사항이 발생했습니다.

```
scan.reward 완료
      │
      ├── character_worker: 캐릭터 소유권 저장
      └── users_worker: 유저-캐릭터 연결 저장
```

### 1.2 기존 구현의 문제점

```python
# 기존 코드: 2번 publish (비권장)
celery_app.send_task("character.save_ownership", args=[...])  # 1번째
celery_app.send_task("users.save_character", args=[...])      # 2번째
```

| 문제 | 설명 |
|------|------|
| **네트워크 비효율** | 동일 데이터를 2번 전송 |
| **원자성 미보장** | 하나만 실패 가능 |
| **확장성 부족** | 새 Consumer 추가 시 코드 수정 필요 |
| **의도 불명확** | 동일 이벤트인지 다른 이벤트인지 불분명 |

---

## 2. 선택지 분석

### 2.1 Option A: AMQP Default Exchange (`""`)

```
Producer → Default Exchange → Queue (routing_key = queue_name)
```

| 장점 | 단점 |
|------|------|
| 설정 불필요 | 1:1 고정, 1:N 불가 |
| Celery 기본 동작 | 유연성 부족 |

**판정**: ❌ 1:N 요구사항 충족 불가

### 2.2 Option B: Named Direct Exchange

```
Producer → reward.direct → binding(routing_key) → Queue1, Queue2
```

| 장점 | 단점 |
|------|------|
| routing_key 기반 라우팅 | Celery `send_task()` exchange 파라미터 무시됨 |
| 표준 AMQP 패턴 | 구현 복잡도 증가 |

**판정**: ❌ Celery 호환 문제 발견

### 2.3 Option C: Fanout Exchange ✅ 선택

```
Producer → reward.events (Fanout) → Queue1, Queue2 (자동 복제)
```

| 장점 | 단점 |
|------|------|
| routing_key 무시 | Topic 패턴 라우팅 불가 |
| 구현 단순 | 모든 바인딩 큐로 브로드캐스트 |
| kombu로 확실한 제어 | - |

**판정**: ✅ 채택

---

## 3. 최종 아키텍처

### 3.1 Exchange 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    최종 Exchange 구조                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ dlx         │  │reward.events│  │ blacklist.  │             │
│  │ (Direct)    │  │  (Fanout)   │  │   events    │             │
│  │             │  │  ✅ 신규    │  │  (Fanout)   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│    Dead Letter      1:N 이벤트       캐시 무효화               │
│                          │                                      │
│                    ┌─────┴─────┐                               │
│                    ▼           ▼                               │
│              character   users                                 │
│              .save_own   .save_char                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 데이터 흐름

```
scan.reward 완료
      │
      │ kombu.Producer.publish(exchange='reward.events')
      │ (1번만 publish! routing_key 무시)
      ▼
┌─────────────────────┐
│   reward.events     │  Fanout Exchange
│                     │  모든 바인딩 큐에 브로드캐스트
└─────────────────────┘
      │
      │  자동 복제 (Fanout 특성)
      │
      ├───────────────────────────────────────────┐
      ▼                                           ▼
┌─────────────────────┐           ┌─────────────────────┐
│character.save_owner │           │ users.save_character│
│       ship 큐       │           │        큐           │
└─────────────────────┘           └─────────────────────┘
      │                                           │
      ▼                                           ▼
character_worker                           users_worker
(gevent pool, sync DB)                    (prefork pool, async DB)
```

### 3.3 구현 코드

```python
# apps/scan_worker/application/classify/steps/reward_step.py
from kombu import Connection, Exchange, Producer
from kombu.pools import producers

def _dispatch_save_tasks(user_id: str, reward: dict) -> None:
    """Fanout Exchange로 1:N 이벤트 발행."""
    with Connection(celery_app.broker_connection().as_uri()) as conn:
        exchange = Exchange("reward.events", type="fanout", durable=True)
        with producers[conn].acquire(block=True) as producer:
            producer.publish(
                {
                    "user_id": user_id,
                    "character_id": reward["character_id"],
                    "character_code": reward.get("character_code", ""),
                    "source": "scan",
                },
                exchange=exchange,
                routing_key="",  # Fanout은 무시
                serializer="json",
            )
```

---

## 4. Topology CR 일원화

### 4.1 책임 분리

| 레이어 | 책임 | 관리 방식 |
|--------|------|----------|
| **Kubernetes CR** | Exchange, Queue, Binding 생성 | GitOps (ArgoCD) |
| **Python Celery** | Task → Queue 매핑 | 코드 (`task_routes`) |

### 4.2 Topology CR 예시

```yaml
# workloads/rabbitmq/base/topology/exchanges.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: reward-events
  namespace: rabbitmq
spec:
  name: reward.events
  type: fanout
  durable: true
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
    namespace: rabbitmq
```

```yaml
# workloads/rabbitmq/base/topology/bindings.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Binding
metadata:
  name: reward-to-character-ownership
  namespace: rabbitmq
spec:
  source: reward.events
  destination: character.save_ownership
  destinationType: queue
  # routingKey 없음 - Fanout은 무시
  vhost: eco2
  rabbitmqClusterReference:
    name: eco2-rabbitmq
    namespace: rabbitmq
```

---

## 5. 왜 Named Direct가 아닌 Fanout인가?

### 5.1 Celery `send_task()` 문제

```python
# ❌ 실패: exchange 파라미터가 task_routes에 의해 무시됨
celery_app.send_task(
    "reward.character",
    exchange="reward.direct",  # task_routes에 의해 무시됨!
    routing_key="reward.character",
)
```

**Celery 내부 동작:**
1. `task_routes`에서 태스크 이름 검색
2. 없으면 `task_default_exchange=""` (AMQP Default) 사용
3. `exchange` 파라미터 무시 → Default Exchange로 전송

### 5.2 Fanout 해결책

```python
# ✅ 성공: kombu Producer로 직접 제어
from kombu import Exchange, Producer

exchange = Exchange("reward.events", type="fanout", durable=True)
producer.publish(payload, exchange=exchange, routing_key="")
```

| 관점 | Named Direct | Fanout |
|------|--------------|--------|
| routing_key | 필수 (매칭 기반) | 무시됨 |
| Celery 호환 | ❌ `send_task()` 무시 | ✅ kombu 직접 사용 |
| 바인딩 | routing_key 별로 지정 | 큐만 바인딩 |
| 확장성 | routing_key 추가 필요 | Binding CR만 추가 |

---

## 6. 핵심 패턴: 동일 Task 이름, 다른 구현

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

- **동일한 task 이름** (`reward.character`)
- **각 Worker가 자신의 큐에서만 소비**
- **RabbitMQ Binding이 메시지 복제 담당**

---

## 7. 기대 효과

| 측면 | Before | After |
|------|--------|-------|
| **네트워크** | 2번 publish | 1번 publish |
| **원자성** | 보장 안 됨 | RabbitMQ가 보장 |
| **확장성** | 코드 수정 필요 | Binding CR만 추가 |
| **운영** | 모니터링 불가 | Exchange별 트래픽 분리 |
| **의도** | 불명확 | "이벤트 → 다중 서비스" 패턴 명시 |

---

## 8. 결론

### 8.1 핵심 의사결정

| 항목 | 초기 결정 | 최종 결정 | 변경 이유 |
|------|----------|----------|----------|
| Exchange 타입 | Named Direct | **Fanout** | Celery `send_task()` exchange 무시 문제 |
| Publish 방식 | `send_task()` | **kombu Producer** | Named Exchange 직접 제어 필요 |
| Topology 관리 | Celery 선언 | **K8s CR** | GitOps 일원화, 인프라 코드 분리 |

### 8.2 적용 범위

- `scan_worker` → `character_worker` + `users_worker` 이벤트 라우팅
- `blacklist.events` 캐시 무효화 브로드캐스트 (기존)
- 향후 1:N 이벤트 라우팅 패턴 표준화

---

## 참고 자료

- [RabbitMQ Messaging Topology Operator](https://github.com/rabbitmq/messaging-topology-operator)
- [Celery Task Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)
- [kombu Producer API](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.html#producer)
- [52-fanout-exchange-migration-troubleshooting.md](../blogs/async/52-fanout-exchange-migration-troubleshooting.md)


