# Fanout Exchange Migration Troubleshooting

> 작성일: 2026-01-09
> 작업 시간: 14:00 ~ 18:30 KST (약 4.5시간)
> 관련 리포트: [51-rabbitmq-queue-strategy-report.md](./51-rabbitmq-queue-strategy-report.md)

## 개요

RabbitMQ Topology CR을 단일 소스로 일원화하고, `scan.reward` → `character.save_ownership` + `users.save_character` 1:N 라우팅을 구현하는 과정에서 발생한 트러블슈팅 기록.

**최종 결과**: Named Direct Exchange → **Fanout Exchange** 전환 ✅ E2E 검증 완료

---

## 타임라인 요약

| 시간 | Phase | 주요 작업 |
|------|-------|----------|
| 14:00 ~ 14:12 | 설계 | Exchange 전략 분석, Named Direct vs Fanout 검토 |
| 14:13 ~ 15:02 | Phase 1 | Celery Queue 선언 충돌 해결 (`no_declare=True`) |
| 15:29 ~ 16:11 | Phase 2 | Worker 설정, 캐시 초기화, POSTGRES_HOST 수정 |
| 16:40 ~ 17:46 | Phase 3 | Fanout Exchange 전환, kombu Producer 구현 |
| 18:00 ~ 18:30 | Phase 4 | DB 마이그레이션, gevent/asyncio 충돌 해결 |
| 18:30 ~ 18:35 | E2E Test | 4회 테스트, Fanout 브로드캐스트 검증 |

---

## Phase 1: Celery Queue 선언 충돌 (14:13 ~ 15:02)

### 문제 1: `PreconditionFailed` - x-message-ttl 불일치

```
amqp.exceptions.PreconditionFailed: Queue.declare: (406) PRECONDITION_FAILED
- inequivalent arg 'x-message-ttl' for queue 'character.match' in vhost 'eco2':
  received none but current is the value '30000' of type 'long'
```

**원인**: Celery가 `Queue("character.match")`를 선언할 때 arguments 없이 선언 → Topology CR의 TTL 설정과 충돌

**해결**: 
```python
# apps/character_worker/setup/celery.py
CHARACTER_TASK_QUEUES = [
    Queue("character.match", no_declare=True),  # Celery가 선언하지 않음
    Queue("character.save_ownership", no_declare=True),
    Queue("character.grant_default", no_declare=True),
]

celery_app.conf.update(
    task_queues=CHARACTER_TASK_QUEUES,
    task_create_missing_queues=False,  # 누락된 큐 자동 생성 방지
)
```

**PR**: #344, #345, #346

### 문제 2: `ImproperlyConfigured` - Queue 정의 누락

```
celery.exceptions.ImproperlyConfigured: Trying to select queue subset of
['character.match'], but queue 'character.match' isn't defined in the task_queues setting.
```

**원인**: `task_create_missing_queues=False` 설정 시 `-Q` 옵션에 지정된 큐가 `task_queues`에 없으면 에러

**해결**: `task_queues`에 모든 소비 큐 정의 (arguments 없이, `no_declare=True`)

**PR**: #347, #348

---

## Phase 2: Worker 설정 및 캐시 초기화 (15:29 ~ 16:11)

### 문제 3: Queue 바인딩이 Default Exchange가 아닌 `celery(direct)`로 표시

```
character.match exchange=celery(direct) key=character.match
```

**원인**: `Queue("name")` 정의 시 `exchange` 미지정 → Celery가 기본값 `celery` Exchange 사용

**해결**:
```python
Queue(
    "character.match",
    exchange="",           # AMQP Default Exchange 명시
    routing_key="character.match",
    no_declare=True,
)
```

**PR**: #349

### 문제 4: `Character cache not loaded` - Startup Probe 실패

```
Startup probe failed: command "celery -A character_worker.main:app inspect ping -t 15" timed out
```

**원인**: 
- `character-match-worker`는 `-P threads` pool 사용
- `worker_process_init` signal은 `prefork`/`gevent` pool에서만 호출
- `threads` pool에서는 캐시 초기화 안 됨

**해결**:
```python
from celery.signals import worker_process_init, worker_ready

@worker_process_init.connect
def init_worker_process(**kwargs):
    # prefork/gevent pool용
    _init_character_cache()

@worker_ready.connect
def init_worker_ready(**kwargs):
    # threads pool용 (MainProcess에서 호출)
    _init_character_cache()
```

**PR**: #350, #351

### 문제 5: `POSTGRES_HOST` 잘못된 서비스 이름

```
psycopg2.OperationalError: could not translate host name
"postgresql.postgres.svc.cluster.local" to address: Name or service not known
```

**원인**: Deployment에서 `POSTGRES_HOST` 값이 잘못됨

**해결**:
```yaml
# workloads/domains/character-worker/base/deployment.yaml
env:
  - name: POSTGRES_HOST
    value: dev-postgresql.postgres.svc.cluster.local  # 수정
```

**PR**: #352

---

## Phase 3: Fanout Exchange 전환 (16:40 ~ 17:46)

### 문제 6: Celery `send_task()` exchange 파라미터 무시

```python
# 예상 동작
celery_app.send_task(
    "reward.character",
    exchange="reward.direct",      # ← 무시됨!
    routing_key="reward.character",
)

# 실제 동작: Default Exchange로 전송
```

**원인**: Celery의 `send_task()`는 `task_routes` 설정 우선 → `exchange` 파라미터 무시

**해결 시도 1**: `kombu.Producer` 직접 사용 (Direct Exchange)
```python
with Connection(broker_url) as conn:
    exchange = Exchange("reward.direct", type="direct")
    producer = Producer(conn, exchange=exchange)
    producer.publish(payload, routing_key="reward.character")
```

**문제**: Direct Exchange + 동일 routing_key → 1:N 바인딩 시 복잡성 증가

**최종 해결**: **Fanout Exchange** 전환
```python
# Fanout은 routing_key 무시 → 모든 바인딩 큐에 브로드캐스트
exchange = Exchange("reward.events", type="fanout", durable=True)
producer.publish(payload, exchange=exchange, routing_key="")  # routing_key 무시
```

**PR**: #353, #354, #355

### 문제 7: `struct.error` - kombu 직렬화 오류

```
struct.error: argument for 's' must be a bytes object
```

**원인**: `producer.publish()`에서 `content_type` + `serializer` 동시 지정 충돌

**해결**:
```python
producer.publish(
    payload,
    exchange=exchange,
    routing_key="",
    serializer="json",        # ← 이것만 사용
    # content_type 제거
)
```

**PR**: #356

---

## Phase 4: DB 마이그레이션 및 Worker 호환성 (18:00 ~ 18:30)

### 문제 8: `character_code` 컬럼 없음

```
asyncpg.exceptions.UndefinedColumnError: column "character_code"
of relation "character_ownerships" does not exist
```

**원인**: Migration 0002 미적용 상태

**해결**: SQL 직접 실행
```sql
-- 1. 컬럼 추가
ALTER TABLE character.character_ownerships 
ADD COLUMN IF NOT EXISTS character_code VARCHAR(64);

-- 2. 기존 데이터 마이그레이션
UPDATE character.character_ownerships co
SET character_code = c.code
FROM character.characters c
WHERE co.character_id = c.id AND co.character_code IS NULL;

-- 3. NOT NULL 제약
ALTER TABLE character.character_ownerships 
ALTER COLUMN character_code SET NOT NULL;

-- 4. UNIQUE 제약 변경
ALTER TABLE character.character_ownerships 
DROP CONSTRAINT IF EXISTS uq_character_ownership_user_character;
ALTER TABLE character.character_ownerships 
ADD CONSTRAINT uq_character_ownership_user_code UNIQUE (user_id, character_code);
```

### 문제 9: gevent pool + asyncio 충돌

```
RuntimeError: Task <Task pending> got Future attached to a different loop
```

**원인**: 
- `character-worker`는 `-P gevent` pool 사용
- `reward_event_task.py`에서 `asyncio.new_event_loop()` 사용
- gevent와 asyncio 이벤트 루프 충돌

**해결**: 동기 DB 세션으로 변경
```python
# Before (asyncio)
from character_worker.setup.database import async_session_factory

async def _save_ownership_batch_async(batch_data):
    async with async_session_factory() as session:
        result = await session.execute(sql, params)
        await session.commit()

# After (sync)
from character_worker.setup.database import sync_session_factory

def _save_ownership_batch_sync(batch_data):
    with sync_session_factory() as session:
        result = session.execute(sql, params)
        session.commit()
```

**PR**: #358

---

## PR 목록 요약

| PR | 제목 | 주요 변경 |
|----|------|----------|
| #344 | `fix(celery): Queue에 no_declare=True 추가` | Topology CR과 충돌 방지 |
| #345-346 | `fix(scan-api): Queue 설정 간소화` | Producer 역할에 맞게 설정 |
| #347-348 | `fix(scan-worker): celery/character.match 큐 추가` | task_queues 정의 |
| #349 | `fix(workers): AMQP Default Exchange 명시` | exchange="" 명시 |
| #350 | `fix(workers): 캐시 초기화 및 LogRecord 충돌` | threads pool 지원 |
| #351 | `fix(character-worker): lazy loading` | 캐시 초기화 예외 처리 |
| #352 | `fix(workloads): POSTGRES_HOST 수정` | 서비스 이름 수정 |
| #353 | `refactor(rabbitmq): Fanout 전환` | reward.direct → reward.events |
| #354 | `fix(workers): autodiscover 누락` | __init__.py import 추가 |
| #355 | `fix(scan-worker): kombu Producer 사용` | send_task → Producer |
| #356 | `fix(scan-worker): 직렬화 에러` | serializer='json' 명시 |
| #357 | `fix(secrets): dockerhub-secret` | users namespace 추가 |
| #358 | `fix(character-worker): 동기 DB` | gevent 호환 |

---

## 최종 아키텍처

```
scan.reward 완료 (재활용폐기물 + character match 성공)
      │
      │ kombu.Producer.publish(exchange='reward.events')
      ▼
┌─────────────────────┐
│   reward.events     │  Fanout Exchange
│  (type: fanout)     │
└─────────────────────┘
      │
      ├── character.save_ownership 큐 → character-worker (gevent, sync DB)
      └── users.save_character 큐 → users-worker (prefork, async DB)
```

---

## E2E 테스트 결과 (18:30)

### 테스트 환경
- **API**: `POST https://api.dev.growbin.app/api/v1/scan`
- **이미지**: 에어팟 케이스 (`images.dev.growbin.app/scan/13435e8e99b6490e8f2452f4cbbc8e7a.png`)
- **테스트 횟수**: 4회

### 결과

| Job ID | scan 파이프라인 | character.match | reward.character |
|--------|----------------|-----------------|------------------|
| `d44e4c6e...` | ✅ 완료 | ✅ 일렉 매칭 | ✅ 발행 |
| `35cf1a1d...` | ✅ 완료 | ❌ (일반폐기물) | ❌ |
| `11a89162...` | ✅ 완료 | ❌ (일반폐기물) | ❌ |
| `7ac9923d...` | ✅ 완료 | ❌ (일반폐기물) | ❌ |

### 검증 포인트

1. **Fanout 브로드캐스트 동작 확인**
   ```
   character-worker: reward.character batch completed ✅
   users-worker: reward.character batch completed ✅
   ```

2. **1:N 라우팅 성공**
   - `reward.events` (Fanout) → `character.save_ownership` 큐
   - `reward.events` (Fanout) → `users.save_character` 큐

3. **LLM 분류 가변성**
   - 동일 이미지도 LLM 응답에 따라 `전기전자제품` or `일반종량제폐기물`로 분류
   - 캐릭터 매칭은 재활용 가능 품목일 때만 발생 (정상 동작)

---

## 교훈

1. **Celery의 `send_task()` exchange 파라미터는 신뢰하지 말 것** - `task_routes` 우선
2. **Worker Pool과 비동기 라이브러리 호환성 확인** - gevent ↔ asyncio 충돌
3. **Topology CR을 SSOT로 유지** - `no_declare=True`로 Celery 선언 방지
4. **Fanout Exchange는 1:N 브로드캐스트에 가장 단순** - routing_key 고민 불필요
5. **E2E 테스트는 필수** - 단위 테스트로는 Exchange 라우팅 검증 불가

---

## 참고 자료

- [Celery Task Routing - Exchange 우선순위](https://docs.celeryq.dev/en/stable/userguide/routing.html)
- [kombu Producer API](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.html#producer)
- [RabbitMQ Exchange Types](https://www.rabbitmq.com/tutorials/amqp-concepts.html#exchanges)
- [gevent + asyncio 호환성](https://www.gevent.org/api/gevent.html#gevent.monkey.patch_all)

