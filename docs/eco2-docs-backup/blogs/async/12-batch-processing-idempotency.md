# Celery Batches와 멱등성 처리

> 이전 글: [보상 판정과 Persistence 분리 구현](./11-reward-persistence-separation-part2.md)
>
> 관련 트러블슈팅: [Celery + RabbitMQ 트러블슈팅 가이드](./14-celery-rabbitmq-troubleshooting.md)

---

## 개요

본 문서는 **celery-batches 패키지를 활용한 배치 처리**와 **ON CONFLICT DO NOTHING 기반 멱등성 보장** 구현을 다룬다.

---

## 1. 배치 처리 필요성

### 1.1 개별 INSERT 문제

Fire&Forget으로 `save_ownership`, `save_my_character`를 발행하면 트래픽 증가 시:

```
요청 1 → DB 연결 → INSERT → 연결 반환
요청 2 → DB 연결 → INSERT → 연결 반환
...
```

**문제점**:
- 매 요청마다 DB 연결 생성/반환 오버헤드
- 트랜잭션 로그 write 횟수 증가
- DB 커넥션 풀 소진 위험

### 1.2 배치 처리 이점

```
요청 1~50 → 버퍼에 쌓음 → 50개 모이면 한 번에 처리
         → DB 연결 1회 → BULK INSERT → 연결 반환
```

- DB 연결 50분의 1
- 단일 트랜잭션 (효율적 write)
- INSERT 쿼리 1회 (50개 행)

---

## 2. celery-batches 적용

### 2.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      character-worker                            │
│                                                                  │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐  │
│  │   RabbitMQ   │───▶│   Batches Buffer  │───▶│  PostgreSQL  │  │
│  │   (Queue)    │    │   (In-Memory)     │    │   (Bulk)     │  │
│  └──────────────┘    └───────────────────┘    └──────────────┘  │
│         │                     │                      │          │
│         │           ┌─────────┴─────────┐            │          │
│         ▼           ▼                   ▼            ▼          │
│    message 1   flush_every=50     flush_interval=5  BULK INSERT │
│    message 2   (개수 도달)         (시간 경과)        50 rows     │
│    ...                                                           │
│    message 50                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 동작 방식

```python
from celery_batches import Batches

@celery_app.task(
    base=Batches,
    flush_every=50,     # 50개 모이면 flush
    flush_interval=5,   # 5초마다 flush (버퍼에 메시지 있으면)
)
def batch_task(requests: list):
    # requests: List[SimpleRequest]
    pass
```

**flush 트리거**:
- `flush_every` 개 도달 → 즉시 처리
- `flush_interval` 초 경과 → 버퍼에 있는 만큼 처리

### 2.3 Flush 조건 다이어그램

```
시간 ──────────────────────────────────────────────────▶

개수 기반 (flush_every=50)
├─ msg1 ─ msg2 ─ ... ─ msg50 ─┤ FLUSH!
                               ↓
                          batch_task(requests=[msg1..msg50])

시간 기반 (flush_interval=5초)
├─ msg1 ─ msg2 ─ msg3 ────────────────┤ 5초 경과, FLUSH!
                                       ↓
                                  batch_task(requests=[msg1..msg3])
```

---

## 3. character.save_ownership 구현

### 3.1 Task 정의

```python
@celery_app.task(
    base=Batches,
    name="character.save_ownership",
    queue="character.reward",
    flush_every=50,
    flush_interval=5,
    acks_late=True,
    max_retries=5,
)
def save_ownership_task(requests: list) -> dict:
    batch_data = []
    for req in requests:
        kwargs = req.kwargs or {}
        if kwargs:
            batch_data.append(kwargs)
    
    if not batch_data:
        return {"processed": 0}
    
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_save_ownership_batch_async(batch_data))
    finally:
        loop.close()
    
    return result
```

### 3.2 Bulk INSERT with ON CONFLICT

```python
async def _save_ownership_batch_async(batch_data: list[dict]) -> dict:
    async with async_session() as session:
        values = []
        params = {}
        for i, data in enumerate(batch_data):
            values.append(
                f"(:user_id_{i}, :character_id_{i}, :source_{i}, NOW(), NOW())"
            )
            params[f"user_id_{i}"] = UUID(data["user_id"])
            params[f"character_id_{i}"] = UUID(data["character_id"])
            params[f"source_{i}"] = data.get("source", "scan")
        
        sql = text(f"""
            INSERT INTO character_ownerships
                (user_id, character_id, source, created_at, updated_at)
            VALUES {", ".join(values)}
            ON CONFLICT (user_id, character_id) DO NOTHING
        """)
        
        result = await session.execute(sql, params)
        await session.commit()
        
        return {
            "processed": len(batch_data),
            "inserted": result.rowcount,
        }
```

---

## 4. 멱등성 처리

### 4.1 멱등성 정의

> **멱등성(Idempotency)**: 동일한 연산을 여러 번 수행해도 결과가 달라지지 않는 성질

분산 시스템에서 멱등성이 필요한 이유:
- 네트워크 타임아웃으로 클라이언트가 재시도
- Message Queue의 at-least-once 전달 보장
- Celery 재시도 메커니즘
- Worker 장애 후 재처리

```
┌─────────────────────────────────────────────────────────────────┐
│  멱등성 미보장 시 문제                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Client ──▶ scan-api ──▶ RabbitMQ ──▶ Worker ──▶ DB             │
│     │                         │                                  │
│     │   ┌─ 타임아웃 ─┐       │                                  │
│     └───│  재시도    │───────┘                                  │
│         └────────────┘                                          │
│                                                                  │
│  결과: 동일 데이터가 2번 INSERT → Duplicate Key Error 또는       │
│        2개 행 생성 (잘못된 상태)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 PostgreSQL ON CONFLICT

| 전략 | SQL | 동작 | 사용 케이스 |
|------|-----|------|-------------|
| **DO NOTHING** | `ON CONFLICT DO NOTHING` | 중복 시 무시 | 불변 데이터 |
| DO UPDATE | `ON CONFLICT DO UPDATE SET ...` | 중복 시 업데이트 | 변경 가능 데이터 |

### 4.3 DO NOTHING 선택 근거

```
character_ownerships:
┌─────────────┬──────────────┬────────┬────────────┐
│   user_id   │ character_id │ source │ created_at │
├─────────────┼──────────────┼────────┼────────────┤
│ user-123    │ char-petty   │ scan   │ 2024-12-24 │  ← 한 번 생성되면
└─────────────┴──────────────┴────────┴────────────┘    변경될 이유 없음
```

소유권은 **불변 데이터**. DO UPDATE는 불필요한 연산:
- Row Lock 획득 (불필요)
- WAL 로그 write (불필요)
- Index 업데이트 (불필요)

```sql
-- ✅ DO NOTHING: 중복 시 아무것도 하지 않음
INSERT INTO character_ownerships (user_id, character_id, source, created_at)
VALUES ($1, $2, $3, NOW())
ON CONFLICT (user_id, character_id) DO NOTHING;

-- ❌ DO UPDATE: 불필요한 write 발생
INSERT INTO character_ownerships (...)
VALUES (...)
ON CONFLICT (user_id, character_id) 
DO UPDATE SET updated_at = NOW();  -- 변경 없어도 write 발생
```

### 4.4 멱등성 검증

```
시나리오: 같은 (user_id, character_id) 3회 발행

┌─────────┬────────────────────────────────┬──────────────┐
│  요청   │           동작                 │    결과      │
├─────────┼────────────────────────────────┼──────────────┤
│ Request 1 │ INSERT → 성공               │ inserted: 1  │
│ Request 2 │ INSERT → ON CONFLICT 감지    │ inserted: 0  │
│ Request 3 │ INSERT → ON CONFLICT 감지    │ inserted: 0  │
└─────────┴────────────────────────────────┴──────────────┘

최종 DB 상태: 1개 행만 존재 ✅
```

### 4.5 배치 내 중복 처리

```
동일 배치에 중복 데이터가 포함된 경우:

batch_data = [
    {user_id: "A", character_id: "X"},  ← 첫 번째
    {user_id: "B", character_id: "Y"},
    {user_id: "A", character_id: "X"},  ← 중복 (배치 내)
]

INSERT INTO character_ownerships VALUES
    ('A', 'X', ...),
    ('B', 'Y', ...),
    ('A', 'X', ...)   ← Unique 제약 위반!
ON CONFLICT DO NOTHING;

결과:
- 'A', 'X': 첫 번째만 INSERT
- 'B', 'Y': INSERT
- 'A', 'X' (두 번째): DO NOTHING으로 무시

inserted: 2 (중복 제외)
```

PostgreSQL은 단일 INSERT 문 내에서도 `ON CONFLICT DO NOTHING`을 각 행에 개별 적용.

---

## 5. 배치 처리 흐름

### 5.1 전체 흐름 시각화

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Batch Processing Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  scan-api                RabbitMQ                 character-worker           │
│     │                       │                          │                     │
│     │  save_ownership #1    │                          │                     │
│     │──────────────────────▶│ ┌───────────────────┐   │                     │
│     │  save_ownership #2    │ │                   │   │                     │
│     │──────────────────────▶│ │  character.reward │   │                     │
│     │  save_ownership #3    │ │      Queue        │──▶│                     │
│     │──────────────────────▶│ │                   │   │ ┌─────────────────┐ │
│     │         ...           │ │  [#1, #2, #3...]  │   │ │ Batches Buffer  │ │
│     │  save_ownership #50   │ │                   │   │ │ flush_every=50  │ │
│     │──────────────────────▶│ └───────────────────┘   │ │ flush_interval=5│ │
│     │                       │                          │ └────────┬────────┘ │
│     │                       │                          │          │          │
│     │                       │                          │          ▼          │
│     │                       │                          │ ┌─────────────────┐ │
│     │                       │                          │ │   PostgreSQL    │ │
│     │                       │                          │ │  BULK INSERT    │ │
│     │                       │                          │ │  50 rows        │ │
│     │                       │                          │ └─────────────────┘ │
│     │                       │                          │                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 시간 기반 Flush (낮은 트래픽)

```
시간축 ─────────────────────────────────────────────────────▶
        │                                               │
        0s                                              5s
        │                                               │
        ├─ msg1 ─ msg2 ─ msg3 ─────────────────────────┤
        │                                               │
        │  버퍼: [msg1, msg2, msg3]                     │
        │                                          FLUSH!
        │                                               │
        │                                               ▼
        │                                    batch_task([msg1, msg2, msg3])
        │                                               │
        │                                    BULK INSERT 3 rows
```

### 5.3 개수 기반 Flush (높은 트래픽)

```
시간축 ─────────────────────────────────────────────────────▶
        │                          │
        0s                        0.4s
        │                          │
        ├─ msg1..msg50 (빠르게 도착)│
        │                          │
        │  버퍼 크기: 50         FLUSH!
        │                          │
        │                          ▼
        │               batch_task([msg1..msg50])
        │                          │
        │               BULK INSERT 50 rows
```

---

## 6. 성능 비교

### 6.1 개별 vs 배치

```
개별 INSERT (50개 요청)
┌─────────────────────────────────────────────────────────────┐
│ req1 ──▶ connect ──▶ INSERT ──▶ commit ──▶ close  (~10ms)  │
│ req2 ──▶ connect ──▶ INSERT ──▶ commit ──▶ close  (~10ms)  │
│ ...                                                         │
│ req50 ──▶ connect ──▶ INSERT ──▶ commit ──▶ close (~10ms)  │
├─────────────────────────────────────────────────────────────┤
│ 총 시간: ~500ms                                              │
└─────────────────────────────────────────────────────────────┘

Batch INSERT (50개 요청)
┌─────────────────────────────────────────────────────────────┐
│ req1..50 ──▶ connect ──▶ BULK INSERT 50 rows ──▶ commit    │
│                                                              │
│ 총 시간: ~10ms                                               │
└─────────────────────────────────────────────────────────────┘
```

| 항목 | 개별 INSERT (50개) | Batch INSERT (50개) |
|------|-------------------|---------------------|
| DB 연결 | 50회 | 1회 |
| 쿼리 실행 | 50회 | 1회 |
| 트랜잭션 | 50개 | 1개 |
| 총 시간 | ~500ms | **~10ms** |

### 6.2 처리량 비교

```
개별 INSERT:                    Batch INSERT:
    │                               │
    ▼                               ▼
┌───────┐                       ┌───────┐
│ 10ms  │ × 50 = 500ms          │ 10ms  │ for 50 requests
└───────┘                       └───────┘
    │                               │
    ▼                               ▼
~100 req/s                      ~5000 req/s

                개선율: ~50x
```

---

## 7. 에러 처리

### 7.1 재시도 전략

```python
@celery_app.task(
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=300,
)
```

**재시도 간격**:
```
1회 실패: ~60초 대기
2회 실패: ~120초 대기
3회 실패: ~240초 대기
4회 실패: ~300초 대기
5회 실패: DLQ로 이동
```

### 7.2 DLQ 재처리

5회 실패 후 DLQ로 이동. Celery Beat가 5분마다 DLQ에서 꺼내 재처리.

---

## 8. 모니터링

### 8.1 로그 출력

```python
logger.info(
    "Save ownership batch completed",
    extra={
        "batch_size": len(batch_data),
        "processed": result["processed"],
        "inserted": result["inserted"],
        "skipped": result["processed"] - result["inserted"],
    },
)
```

### 8.2 메트릭 해석

```
10:00:00 | batch_size=50, processed=50, inserted=48, skipped=2
10:00:05 | batch_size=50, processed=50, inserted=50, skipped=0
```

`skipped`가 높으면 중복 발행이 많다는 신호. 네트워크 이슈나 클라이언트 재시도 패턴 확인 필요.

---

## 9. 설정 가이드

| 트래픽 | flush_every | flush_interval |
|--------|-------------|----------------|
| 낮음 (~10 req/s) | 10 | 10초 |
| 중간 (~100 req/s) | 50 | 5초 |
| 높음 (~1000 req/s) | 100 | 2초 |

---

## 10. 관련 코드

| 파일 | 역할 |
|------|------|
| `domains/character/tasks/reward.py` | character.save_ownership batch task |
| `domains/my/tasks/sync_character.py` | my.save_character batch task |
| `domains/_shared/celery/config.py` | Celery 설정 |

---

## 11. Trade-off

| 선택 | 장점 | 단점 |
|------|------|------|
| Batch INSERT | DB 부하 ~50배 감소 | flush_interval 동안 지연 |
| ON CONFLICT DO NOTHING | 멱등성 보장 | 업데이트 불가 |
| acks_late | 메시지 손실 방지 | 중복 처리 가능성 |

---

## References

- [celery-batches Documentation](https://github.com/clokep/celery-batches)
- [PostgreSQL ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html#SQL-ON-CONFLICT)
- [Idempotent Consumer Pattern](https://www.enterpriseintegrationpatterns.com/IdempotentReceiver.html)
