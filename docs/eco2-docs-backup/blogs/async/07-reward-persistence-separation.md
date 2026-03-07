# 이코에코(Eco2) 비동기 전환 #7: 보상 판정/저장 분리와 Eventual Consistency

> 이전 글: [비동기 전환 #6: Celery Chain + Events 구현](./06-celery-chain-events.md)

---

## 개요

본 문서는 **보상(Reward) 판정과 DB 저장 로직의 분리**, **병렬 저장을 통한 gRPC 제거**, 그리고 **Eventual Consistency 전략**에 대해 기록한다.

### 목표

- 클라이언트 응답 속도 개선 (판정 즉시 응답)
- DB 저장 실패가 응답에 영향 주지 않도록 격리
- 두 DB(character, my) 저장을 병렬로 처리
- gRPC 의존성 제거 (네트워크 오버헤드 감소)

### 핵심 성과

| 항목 | Before | After |
|------|--------|-------|
| **클라이언트 응답** | 판정 + DB 저장 완료 후 | 판정 즉시 |
| **DB 저장** | 순차 (character → my gRPC) | 병렬 (Fire & Forget) |
| **my 도메인 연동** | gRPC 호출 | 직접 DB INSERT |
| **실패 시 영향** | 전체 실패 | 각자 독립 재시도 |

---

## 1. 문제 정의

### 1.1 기존 구조의 문제점

```
scan_reward_task (Chain 마지막 단계)
    │
    ├── 1. 캐릭터 매칭 (판정)
    ├── 2. character_ownerships INSERT + COMMIT
    ├── 3. sync_to_my_task.delay() → gRPC 호출
    │
    └── 4. 클라이언트 응답 (SSE)  ← 여기까지 대기
```

**문제점**:
1. **응답 지연**: DB 저장 완료까지 클라이언트가 대기
2. **단일 실패점**: DB 장애 시 전체 실패
3. **gRPC 오버헤드**: 네트워크 호출로 인한 지연 + 장애 전파
4. **순차 처리**: character DB → my DB 직렬 실행

### 1.2 개선 목표

```
클라이언트 응답 시간:  Before: ~500ms  →  After: ~100ms
DB 저장 실패 영향:    Before: 전체 실패 →  After: 응답은 성공
my 동기화 방식:       Before: gRPC     →  After: 직접 DB
저장 병렬화:          Before: 순차     →  After: 병렬
```

---

## 2. 새로운 아키텍처

### 2.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  Celery Chain (마지막 단계)                                                  │
│                                                                             │
│  scan_reward_task (판정만)                                                   │
│       │                                                                     │
│       ├── 1. 캐릭터 매칭 (DB 조회만, 저장 X)                                 │
│       ├── 2. 즉시 응답 (SSE) ✅                                              │
│       │                                                                     │
│       └── 3. persist_reward_task.delay() ──────────────────────────────┐    │
│                                                                        │    │
│                                                                        ▼    │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  persist_reward_task (dispatcher)                                       ││
│  │       │                                                                 ││
│  │       ├── save_ownership_task.delay()    ──→ [reward.persist 큐]        ││
│  │       │        └── character.character_ownerships INSERT                ││
│  │       │                                                                 ││
│  │       └── save_my_character_task.delay() ──→ [my.sync 큐]               ││
│  │                └── my.user_characters INSERT (직접)                     ││
│  │                                                                         ││
│  │       (둘 다 Fire & Forget, 각자 독립 재시도)                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Task 책임 분리

| Task | 책임 | 큐 | 재시도 |
|------|------|-----|--------|
| `scan_reward_task` | 캐릭터 매칭 판정만 | reward.character | 3회 |
| `persist_reward_task` | 저장 task 발행 (dispatcher) | reward.persist | 3회 |
| `save_ownership_task` | character DB 저장 | reward.persist | 5회 |
| `save_my_character_task` | my DB 저장 (직접) | my.sync | 5회 |

---

## 3. 구현 상세

### 3.1 scan_reward_task (판정만)

```python
# domains/character/consumers/reward.py

@celery_app.task(
    name="scan.reward",
    queue="reward.character",
    max_retries=3,
)
def scan_reward_task(self, prev_result: dict) -> dict:
    """Step 4: Reward Evaluation (Chain 마지막 단계)
    
    보상 **판정만** 수행하고 즉시 클라이언트에게 응답.
    DB 저장은 별도 task에서 비동기로 처리.
    """
    # 1. 조건 확인
    if _should_attempt_reward(prev_result):
        # 2. 판정만 수행 (DB 저장 X)
        reward = _evaluate_reward_decision(...)
        
        # 3. DB 저장 task 발행 (Fire & Forget)
        if reward and reward.get("received"):
            persist_reward_task.delay(
                user_id=user_id,
                character_id=reward["character_id"],
                character_code=reward["character_code"],
                character_name=reward["name"],
                # ... 기타 필드
            )
    
    # 4. 즉시 응답 (SSE로 클라이언트에게 전달)
    return {
        **prev_result,
        "reward": reward_response,  # character_id 제외
    }
```

**핵심 포인트**:
- DB 저장 없이 판정만 수행
- `persist_reward_task.delay()`로 비동기 발행 후 즉시 반환
- 클라이언트 응답에는 `character_id` 등 내부 필드 제외

### 3.2 persist_reward_task (dispatcher)

```python
@celery_app.task(
    name="character.persist_reward",
    queue="reward.persist",
    soft_time_limit=10,  # 짧은 타임아웃 (발행만)
)
def persist_reward_task(
    self,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
    task_id: str | None = None,
) -> dict:
    """저장 task 발행 (dispatcher)
    
    2개의 저장 task를 동시에 발행 (Fire & Forget).
    """
    dispatched = {"ownership": False, "my_character": False}
    
    # 1. character_ownerships 저장 task 발행
    try:
        save_ownership_task.delay(
            user_id=user_id,
            character_id=character_id,
            source=source,
        )
        dispatched["ownership"] = True
    except Exception:
        logger.exception("Failed to dispatch save_ownership_task")
    
    # 2. my.user_characters 저장 task 발행
    try:
        save_my_character_task.delay(
            user_id=user_id,
            character_id=character_id,
            character_code=character_code,
            character_name=character_name,
            character_type=character_type,
            character_dialog=character_dialog,
            source=source,
        )
        dispatched["my_character"] = True
    except Exception:
        logger.exception("Failed to dispatch save_my_character_task")
    
    return {"dispatched": dispatched}
```

**핵심 포인트**:
- 발행만 하고 결과 대기 X
- 하나가 실패해도 다른 하나는 발행됨
- 짧은 타임아웃 (10초)

### 3.3 save_ownership_task (character DB)

```python
@celery_app.task(
    name="character.save_ownership",
    queue="reward.persist",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def save_ownership_task(
    self,
    user_id: str,
    character_id: str,
    source: str,
) -> dict:
    """character.character_ownerships 저장
    
    Idempotent: 이미 소유한 경우 skip.
    """
    result = asyncio.run(_save_ownership_async(...))
    return result


async def _save_ownership_async(...) -> dict:
    async with async_session() as session:
        # 이미 소유 여부 확인
        existing = await ownership_repo.get_by_user_and_character(...)
        if existing:
            return {"saved": False, "reason": "already_owned"}
        
        # 소유권 저장
        try:
            await ownership_repo.insert_owned(...)
            await session.commit()
            return {"saved": True}
        except IntegrityError:
            # Race condition 처리
            return {"saved": False, "reason": "concurrent_insert"}
```

### 3.4 save_my_character_task (my DB 직접)

```python
@celery_app.task(
    name="character.save_my_character",
    queue="my.sync",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def save_my_character_task(
    self,
    user_id: str,
    character_id: str,
    character_code: str,
    character_name: str,
    character_type: str | None,
    character_dialog: str | None,
    source: str,
) -> dict:
    """my.user_characters 저장 (gRPC 대신 직접 INSERT)
    
    Idempotent: upsert 로직.
    """
    result = asyncio.run(_save_my_character_async(...))
    return result


async def _save_my_character_async(...) -> dict:
    # my 도메인 DB URL (환경변수에서)
    my_db_url = os.getenv("MY_DATABASE_URL", "...")
    engine = create_async_engine(my_db_url)
    
    async with async_session() as session:
        repo = UserCharacterRepository(session)
        
        # upsert: 이미 소유한 경우 상태 업데이트
        user_char = await repo.grant_character(
            user_id=UUID(user_id),
            character_id=UUID(character_id),
            # ... 기타 필드
        )
        await session.commit()
        
        return {"saved": True, "user_character_id": str(user_char.id)}
```

**gRPC 대신 직접 DB 접근의 장점**:
- 네트워크 오버헤드 제거
- gRPC 서버 장애 영향 없음
- 더 단순한 재시도 로직

---

## 4. Celery 라우팅 설정

```python
# domains/_shared/celery/config.py

"task_routes": {
    # Scan Chain (scan-worker)
    "scan.vision": {"queue": "scan.vision"},
    "scan.rule": {"queue": "scan.rule"},
    "scan.answer": {"queue": "scan.answer"},
    
    # Reward (character-worker)
    "scan.reward": {"queue": "reward.character"},      # 판정
    "character.persist_reward": {"queue": "reward.persist"},  # dispatcher
    "character.save_ownership": {"queue": "reward.persist"},  # character DB
    "character.save_my_character": {"queue": "my.sync"},      # my DB
    
    # Legacy
    "character.sync_to_my": {"queue": "my.sync"},  # deprecated
}
```

---

## 5. RabbitMQ Queue 추가

```yaml
# workloads/rabbitmq/base/topology/queues.yaml

# Reward Persist Queue (DB 저장 전담)
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: reward-persist-queue
  namespace: rabbitmq
spec:
  name: reward.persist
  type: quorum
  durable: true
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.reward.persist
    x-message-ttl: 86400000  # 24시간
    x-delivery-limit: 5      # 재시도 5회
```

---

## 6. Worker 설정

```yaml
# workloads/domains/character-worker/base/deployment.yaml

spec:
  template:
    spec:
      containers:
      - name: character-worker
        args:
        - "-A"
        - "domains.character.consumers"
        - "worker"
        - "-Q"
        - "reward.character,reward.persist,my.sync"  # 3개 큐 처리
        
        env:
        - name: CELERY_BROKER_URL
          valueFrom:
            secretKeyRef:
              name: character-secret
              key: CELERY_BROKER_URL
        # my 도메인 DB 직접 접근용
        - name: MY_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: character-secret
              key: MY_DATABASE_URL
```

---

## 7. Eventual Consistency 전략

### 7.1 현재 구조에서의 Eventual Consistency

```
클라이언트 응답 (즉시)     DB 상태 (비동기)
━━━━━━━━━━━━━━━━━━━━━     ━━━━━━━━━━━━━━━━━━━
reward.received: true  →  character DB: ❓
                          my DB: ❓
                          
        (시간 경과 후)
                          
                          character DB: ✅
                          my DB: ✅
```

### 7.2 불일치 시나리오와 해결

| 시나리오 | character DB | my DB | 해결 방법 |
|---------|--------------|-------|-----------|
| A. 둘 다 성공 | ✅ | ✅ | 정상 |
| B. ownership만 성공 | ✅ | ❌ | my task 재시도 |
| C. my만 성공 | ❌ | ✅ | ownership task 재시도 |
| D. 둘 다 실패 | ❌ | ❌ | DLQ → 재처리 |

### 7.3 현재 보장 수준 (Phase 1)

```
실패 → 자동 재시도 5회 (exponential backoff)
     → 최종 실패 시 DLQ에 보관
     → 주기적으로 DLQ 재처리 (celery-beat)
```

**장점**:
- 구현 단순
- Celery가 자동 처리
- DLQ로 메시지 유실 방지

**단점**:
- 불일치 기간 동안 사용자 경험 이슈 가능
- 트랜잭션 보장 없음

### 7.4 향후 강화 방안 (Phase 2)

#### Option A: Reconciliation Job

```python
# 매 5분마다 불일치 체크 및 복구
@celery_app.task(name="reconcile.character_ownership")
def reconcile_character_ownership():
    """character_ownerships에 있는데 user_characters에 없는 레코드 복구"""
    
    # 불일치 조회
    query = """
        SELECT co.user_id, co.character_id, co.created_at
        FROM character.character_ownerships co
        LEFT JOIN user_profile.user_characters uc
          ON co.user_id = uc.user_id AND co.character_id = uc.character_id
        WHERE uc.id IS NULL
          AND co.created_at < NOW() - INTERVAL '5 minutes'
    """
    
    # 누락된 레코드에 대해 save_my_character_task 발행
    for row in missing_records:
        save_my_character_task.delay(...)
```

#### Option B: Outbox Pattern (Kafka 도입 시)

```
트랜잭션 {
  1. character_ownerships INSERT
  2. outbox 테이블에 이벤트 INSERT
} COMMIT

Debezium CDC:
  outbox 변경 감지 → Kafka 발행 → my consumer가 처리
```

---

## 8. 테스트 전략

### 8.1 단위 테스트

```python
# domains/scan/tests/unit/test_reward_chain.py

class TestPersistRewardDispatcher:
    """persist_reward_task 로직 테스트"""
    
    def test_dispatches_both_tasks_logic(self):
        """2개의 저장 task를 동시에 발행하는 로직 검증."""
        ...
    
    def test_one_failure_does_not_block_other_logic(self):
        """하나가 실패해도 다른 하나는 발행되는 로직 검증."""
        ...


class TestSaveOwnershipTask:
    """save_ownership_task 로직 테스트"""
    
    def test_save_ownership_result_structure_already_owned(self):
        """이미 소유한 경우 반환 구조 검증."""
        ...
    
    def test_handles_concurrent_insert(self):
        """동시 요청으로 인한 IntegrityError 처리."""
        ...


class TestParallelSaveArchitecture:
    """병렬 저장 아키텍처 검증"""
    
    def test_task_routing_config(self):
        """task routing 설정 검증."""
        ...
    
    def test_no_grpc_in_save_my_character(self):
        """gRPC 의존성 없음 검증."""
        ...
```

### 8.2 테스트 결과

```
scan/tests/unit/test_reward_chain.py    25 passed
scan/tests/unit/ 전체                    81 passed
character/tests/ 전체                    64 passed
```

---

## 9. 타임라인 비교

### Before (판정 + 저장 동시)

```
0.0s  scan_reward_task 시작
0.1s  캐릭터 매칭 (판정)
0.2s  character_ownerships INSERT
0.3s  session.commit()
0.4s  sync_to_my_task.delay()
0.4s  gRPC 호출 시작
0.6s  gRPC 응답 수신
0.6s  클라이언트 응답 (SSE)  ← 600ms 소요
```

### After (판정/저장 분리)

```
0.0s  scan_reward_task 시작
0.1s  캐릭터 매칭 (판정)
0.1s  persist_reward_task.delay()  (Fire & Forget)
0.1s  클라이언트 응답 (SSE)  ← 100ms 소요

      (비동기, 클라이언트 응답과 무관)
0.2s  save_ownership_task 실행
0.3s  save_my_character_task 실행
0.5s  양쪽 DB 저장 완료
```

**개선 효과**: 응답 시간 **~83% 감소** (600ms → 100ms)

---

## 10. 결론

### 10.1 달성 사항

- ✅ 판정/저장 분리로 클라이언트 응답 속도 개선
- ✅ 병렬 저장으로 DB 장애 격리
- ✅ gRPC 제거로 네트워크 오버헤드 감소
- ✅ 각 task 독립적인 재시도 (5회, exponential backoff)
- ✅ Eventual Consistency 기본 보장 (재시도 + DLQ)

### 10.2 Trade-off

| 항목 | 장점 | 단점 |
|------|------|------|
| **판정/저장 분리** | 빠른 응답, 장애 격리 | 복잡도 증가 |
| **병렬 저장** | 독립적 재시도 | 불일치 가능성 |
| **gRPC 제거** | 단순화, 성능 | 도메인 경계 희미 |
| **Eventual Consistency** | 장애 내성 | 일시적 불일치 |

### 10.3 향후 계획

- [ ] Reconciliation Job 추가 (불일치 자동 복구)
- [ ] Kafka Outbox Pattern 검토 (강한 일관성 필요 시)
- [ ] 불일치 모니터링 대시보드

---

## 참고 자료

- [Life Beyond Distributed Transactions: 분산 트랜잭션 없이 살아가기](https://rooftopsnow.tistory.com/43)
- [Transactional Outbox: 이중 쓰기 문제의 해결](https://rooftopsnow.tistory.com/45)
- [Enterprise Integration Patterns: 메시징 시스템의 설계 원칙](https://rooftopsnow.tistory.com/41)
- [Celery Task Retries](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2024-12-22 | 1.0 | 초안 작성 |
