# 보상 판정과 Persistence 분리 구현

> 이전 글: [보상 판정과 DB 레이어 분리 설계 (1)](https://rooftopsnow.tistory.com/66)
>
> 관련 트러블슈팅: [Celery + RabbitMQ 트러블슈팅 가이드](./14-celery-rabbitmq-troubleshooting.md)

---

## 개요

본 문서는 **(1)편에서 설계한 보상 판정/저장 분리 아키텍처의 최종 구현**과 **로컬 캐시 기반 매칭**을 다룬다.

---

## 1. 설계 변경 요약

| 항목 | (1)편 설계 | 최종 구현 |
|------|------------|----------|
| Dispatcher | `persist_reward_task` (별도 task) | **제거** (scan.reward에서 직접) |
| 캐릭터 매칭 | DB 조회 | **로컬 캐시** |
| 매칭 호출 | 동일 Worker 내 | **별도 Worker 동기 호출** |
| Queue 구조 | reward.persist | character.match + character.reward |
| gRPC | my 도메인용 | **완전 제거** |

### 변경 이유

**persist_reward_task 제거**:

(1)편 설계에서 dispatcher task가 `delay()` 두 번만 수행. 불필요한 홉 제거:

```
# Before
scan.reward → persist_reward_task → save_ownership
                                 → save_my_character

# After
scan.reward → save_ownership
           → save_my_character
```

**gRPC 제거**:

gRPC는 동기 호출로 my-api 장애가 character-worker로 전파됨. 직접 DB INSERT로 단순화:

```
# Before
character-worker → gRPC → my-api → my DB

# After
my-worker → my DB (직접)
```

---

## 2. scan.reward Task 구현

### 2.1 처리 흐름

```python
@celery_app.task(name="scan.reward", queue="scan.reward")
def scan_reward_task(self, prev_result: dict) -> dict:
    """Chain 마지막 단계: 보상 판정 + dispatch."""
    
    # 1. 조건 검증
    if not _should_attempt_reward(classification_result, disposal_rules, final_answer):
        return {..., "reward": None}
    
    # 2. character.match 동기 호출 (10초 타임아웃)
    reward = _dispatch_character_match(user_id, classification_result, ...)
    
    # 3. DB 저장 task 발행 (Fire & Forget)
    if reward and reward.get("character_id"):
        _dispatch_save_tasks(user_id, reward)
    
    # 4. 클라이언트 응답 (내부 필드 제거)
    return {..., "reward": reward_response}
```

### 2.2 도메인 간 통신

`send_task()`로 import 없이 메시지만 전달:

```python
def _dispatch_character_match(user_id, classification_result, disposal_rules_present):
    async_result = celery_app.send_task(
        "character.match",
        kwargs={...},
        queue="character.match",
    )
    
    result = async_result.get(
        timeout=10,
        disable_sync_subtasks=False,  # 별도 Worker이므로 허용
    )
    
    return result
```

### 2.3 Fire&Forget 저장 발행

```python
def _dispatch_save_tasks(user_id: str, reward: dict):
    # character.save_ownership → character.reward 큐
    celery_app.send_task(
        "character.save_ownership",
        kwargs={"user_id": user_id, "character_id": reward["character_id"], ...},
        queue="character.reward",
    )
    
    # my.save_character → my.reward 큐
    celery_app.send_task(
        "my.save_character",
        kwargs={"user_id": user_id, "character_id": reward["character_id"], ...},
        queue="my.reward",
    )
```

---

## 3. character.match Task 구현

### 3.1 로컬 캐시 기반 매칭

```python
@celery_app.task(name="character.match", queue="character.match")
def match_character_task(self, user_id, classification_result, disposal_rules_present):
    """캐릭터 매칭 (캐시 전용, 단순 라벨 매칭)."""
    
    # 1. 로컬 캐시에서 조회 (DB 조회 없음)
    cache = get_character_cache()
    characters = cache.get_all()
    
    if not characters:
        return None
    
    # 2. 단순 라벨 매칭 (middle_category == match_label)
    classification = classification_result.get("classification", {})
    middle = classification.get("middle_category", "").strip()
    
    matched = next((c for c in characters if c.match_label == middle), None)
    
    if not matched:
        return None
    
    # 3. 결과 반환
    return {
        "name": matched.name,
        "dialog": matched.dialog,
        "match_reason": f"{middle}>{classification.get('minor_category', '')}",
        "type": matched.type_label,
        "character_id": str(matched.id),
        "character_code": matched.code,
        "received": True,
    }
```

---

## 4. Worker 분리 전략

### 4.1 동기 매칭과 Fire&Forget 분리

| 특성 | character.match | character.reward |
|------|-----------------|------------------|
| 응답 방식 | 동기 (10초 타임아웃) | Fire&Forget |
| 처리 시간 | ~10ms | ~5초 (배치) |
| 실패 영향 | 클라이언트 reward null | 나중에 재시도 |
| Concurrency | 4 | 2 |

배치 저장이 큐를 점유하면 동기 매칭이 밀려 타임아웃 발생. 큐 분리 필수.

---

## 5. 클라이언트 응답 vs 내부 데이터

### 5.1 필드 분리

`character.match`는 두 가지 용도로 데이터 반환:

| 용도 | 필드 |
|------|------|
| 클라이언트 표시 | name, dialog, match_reason, type |
| DB 저장 (내부) | character_id, character_code, received |

### 5.2 scan.reward에서 필터링

```python
reward_response = None
if reward:
    reward_response = {
        "name": reward.get("name"),
        "dialog": reward.get("dialog"),
        "match_reason": reward.get("match_reason"),
        "type": reward.get("type"),
        # 내부 필드 제외
    }

return {..., "reward": reward_response}
```

---

## 6. 성능 비교

### Before (persist_reward_task 사용)

```
0.0s  scan_reward_task 시작
0.05s 캐릭터 매칭 (DB 조회)
0.1s  persist_reward_task.delay()
0.1s  클라이언트 응답 (SSE)
```

### After (직접 dispatch)

```
0.0s  scan_reward_task 시작
0.01s character.match 동기 호출
0.02s Local Cache 매칭 완료 (~1ms)
0.03s save_ownership.delay(), save_character.delay()
0.03s 클라이언트 응답 (SSE)
```

**개선**: 100ms → **30ms**

---

## 7. Eventual Consistency

### 7.1 응답 시점 vs DB 상태

```
응답 (0.03s):  reward: {name: "페티", ...}
               DB: ❓ (아직 저장 안됨)

저장 (0.4s):   DB: ✅
```

### 7.2 수용 근거

- 사용자는 캐릭터를 "획득"한 경험을 즉시 수신
- 300ms 후 마이페이지에서 확인 가능
- 저장 실패 시 5회 재시도 + DLQ

**이점**:
- 응답 속도 70ms 개선
- DB 장애가 응답에 영향 없음
- 각 도메인 독립적 재시도

---

## 8. 관련 코드

| 파일 | 역할 |
|------|------|
| `domains/scan/tasks/reward.py` | scan.reward task |
| `domains/character/tasks/match.py` | character.match task |
| `domains/character/tasks/reward.py` | character.save_ownership task |
| `domains/my/tasks/sync_character.py` | my.save_character task |

---

## 9. Trade-off

| 선택 | 장점 | 단점 |
|------|------|------|
| persist_reward_task 제거 | 단순화, 10ms | 모니터링 포인트 감소 |
| 동기 매칭 분리 | 독립 스케일링 | Worker 추가 |
| 로컬 캐시 | 50ms → 1ms | 캐시 미스 가능성 |
| Fire&Forget | 빠른 응답 | Eventual Consistency |

---

## References

- [Life Beyond Distributed Transactions](https://www.cidrdb.org/cidr2007/papers/cidr07p15.pdf)
- [Celery Task Retries](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying)
