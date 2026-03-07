# Channel Separation + Priority Scheduling 코드 리뷰 리포트

> Date: 2026-01-19
> Reviewer: Claude Code
> Branch: `feat/channel-separation-priority-scheduling`
> PR: https://github.com/eco2-team/backend/pull/415
> Related: `docs/plans/langgraph-channel-separation-adr.md`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Files Created** | 4 (`priority.py`, `sequence.py`, `context_helper.py`, `test_priority.py`) |
| **Files Modified** | 18 (state.py, factory.py, dependencies.py, contracts.py, 14 nodes) |
| **Unit Tests** | 697 passed (+25 new tests) |
| **Critical Issues** | 0 |
| **Major Issues** | 0 (1 found, fixed) |
| **Minor Issues** | 0 (4 found, all fixed) |
| **Overall** | Approved |

---

## Architecture Review

### Channel Separation Pattern

**Before (문제)**:
```python
return {**state, "weather_context": output.weather_context}
```

**After (해결)**:
```python
return {
    "weather_context": create_context(
        data=output.weather_context,
        producer="weather",
        job_id=job_id,
    )
}
```

각 노드가 자신의 전용 채널만 반환하여 `InvalidUpdateError` 방지.

### Priority Scheduling Components

| Component | File | 역할 |
|-----------|------|------|
| `Priority` enum | `priority.py` | 정적 우선순위 레벨 (CRITICAL~BACKGROUND) |
| `NODE_PRIORITY` | `priority.py` | 노드별 우선순위 매핑 |
| `NODE_DEADLINE_MS` | `priority.py` | 노드별 SLA 기반 deadline 매핑 |
| `calculate_effective_priority` | `priority.py` | Aging 알고리즘 적용 |
| `LamportClock` | `sequence.py` | 논리적 시계 (Tie-breaker) |
| `create_context` | `context_helper.py` | 스케줄링 메타데이터 주입 (auto deadline) |
| `priority_preemptive_reducer` | `state.py` | Reducer 로직 |

### Reducer 우선순위 결정 로직

```
1. success 비교: true > false
2. priority 비교: 낮은 값이 승리 (CRITICAL=0 > LOW=75)
3. sequence 비교: 높은 값이 승리 (최신)
```

---

## Issues Found and Fixed

### :warning: Major Issues (1 Found → Fixed)

#### M1. contracts.py NODE_OUTPUT_FIELDS 불일치 ✅ FIXED

**파일**: `contracts.py:36`

```python
# Before (문제)
"image_generation": frozenset({"image_url", "image_description"}),

# After (수정)
"image_generation": frozenset({"image_generation_context"}),
```

---

### :bulb: Minor Issues (4 Found → All Fixed)

#### m1. web_search_node에 NodeExecutor 미적용 ✅ FIXED

**파일**: `web_search_node.py`

NodeExecutor 패턴 적용 완료:
```python
executor = NodeExecutor.get_instance()

async def web_search_node(state):
    return await executor.execute(
        node_name="web_search",
        node_func=_web_search_node_inner,
        state=state,
    )
```

---

#### m2. cleanup_sequence 미호출 ✅ FIXED

**파일**: `answer_node.py`

파이프라인 마지막 노드(answer_node)에서 cleanup 호출 추가:
```python
# 3. Lamport Clock 정리 (메모리 관리)
cleanup_sequence(job_id)

# 에러 발생 시에도 정리
except Exception as e:
    cleanup_sequence(job_id)
    ...
```

---

#### m3. deadline_ms 하드코딩 ✅ FIXED

**파일**: `priority.py`, `context_helper.py`

SLA 기반 노드별 deadline 매핑 추가:

```python
NODE_DEADLINE_MS: dict[str, int] = {
    # LLM/Image Generation: 느린 작업
    "image_generation": 30000,
    # gRPC Services: 내부 서비스
    "character": 5000,
    "location": 5000,
    # External APIs: 네트워크 의존
    "weather": 8000,
    "web_search": 10000,
    # RAG/Vector Search
    "waste_rag": 8000,
    # Domain APIs
    "bulk_waste": 8000,
    "collection_point": 8000,
    # Local Data
    "recyclable_price": 5000,
    # General LLM
    "general": 10000,
}
```

`create_context()`가 자동으로 producer 기반 deadline 적용:
```python
def create_context(
    data: dict[str, Any],
    producer: str,
    job_id: str,
    deadline_ms: int | None = None,  # None → 자동 결정
    ...
):
    effective_deadline_ms = deadline_ms if deadline_ms is not None else get_node_deadline(producer)
```

---

#### m4. Aging 알고리즘 단위 테스트 부재 ✅ FIXED

**파일**: `test_priority.py` (신규)

25개 테스트 케이스 추가:
- `TestPriorityEnum`: Priority enum 순서 및 값
- `TestNodePriority`: NODE_PRIORITY 매핑 검증
- `TestNodeDeadline`: NODE_DEADLINE_MS 매핑 검증
- `TestAgingAlgorithm`: Aging 알고리즘 전체 커버리지
  - Threshold 이내 (부스트 없음)
  - Threshold 초과 (부스트 시작)
  - Deadline 도달 (최대 부스트)
  - Deadline 초과 (부스트 유지)
  - Fallback 페널티
  - Aging + Fallback 복합
  - 범위 클램핑 (0~100)
  - 나눗셈 오류 방지 (deadline=0)
- `TestMappingConsistency`: NODE_PRIORITY ↔ NODE_DEADLINE_MS 일관성

---

## SLA-Driven Deadline Configuration

### Best Practices 적용

**References**:
- [SLA-driven timeouts](https://www.contentful.com/blog/the-two-friends-of-a-distributed-systems-engineer-timeouts-and-retries/)
- [Timeout strategies](https://www.geeksforgeeks.org/system-design/timeout-strategies-in-microservices-architecture/)
- [LangGraph retry handling](https://forum.langchain.com/t/the-best-way-in-langgraph-to-control-flow-after-retries-exhausted/1574)

### Deadline 설계 원칙

| 서비스 타입 | Deadline | 근거 |
|------------|----------|------|
| **LLM/Image** | 30s | 느린 작업, retry 고려 |
| **External API** | 8-10s | 네트워크 왕복 + API 처리 |
| **gRPC Internal** | 5s | 내부 서비스, 빠른 응답 기대 |
| **Local Data** | 5s | 로컬 조회, 빠른 응답 |

### Aging 효과

```
예: weather 노드 (deadline=8000ms, priority=LOW=75)

0~6.4s (0-80%): priority = 75 (부스트 없음)
6.4~8s (80-100%): priority = 75 → 55 (점진적 부스트)
8s+ (100%+): priority = 55 (최대 부스트 유지)
```

---

## NodeExecutor 사용 현황 (All Consistent)

| Node | NodeExecutor | FAIL_OPEN |
|------|-------------|-----------|
| weather_node | O | O |
| character_node | O | O |
| location_node | O | O |
| collection_point_node | O | O |
| bulk_waste_node | O | O |
| rag_node | O | O |
| recyclable_price_node | O | O |
| image_generation_node | O | O |
| **web_search_node** | **O** ✅ | O |

---

## Mapping Consistency (All Synced)

### contracts.py vs priority.py

| Node | contracts.py | NODE_PRIORITY | NODE_DEADLINE_MS | Sync |
|------|-------------|---------------|------------------|------|
| waste_rag | O | CRITICAL | 8000 | O |
| bulk_waste | O | CRITICAL | 8000 | O |
| location | O | CRITICAL | 5000 | O |
| collection_point | O | CRITICAL | 8000 | O |
| character | O | HIGH | 5000 | O |
| general | O | HIGH | 10000 | O |
| web_search | O | HIGH | 10000 | O |
| recyclable_price | O | NORMAL | 5000 | O |
| image_generation | O | NORMAL | 30000 | O |
| weather | O | LOW | 8000 | O |

---

## :star: Positive Highlights

1. **Clean Architecture 준수**: Node → Command → Service 계층 분리 일관
2. **Docstring 품질**: 모든 모듈에 목적, 사용법, 예시 포함
3. **Channel Separation 완벽 적용**: 15개 노드 모두 적용
4. **OS 스케줄링 개념 적용**: Priority, Aging, Lamport Clock 등 이론적 근거 명확
5. **Thread-safety**: LamportClock에 Lock 적용
6. **Typing**: 모든 함수에 type hints 적용
7. **SLA-driven Deadline**: 서비스 타입별 deadline 자동 적용
8. **Comprehensive Tests**: Aging 알고리즘 전체 커버리지

---

## Test Results

```
============================= 697 passed in 0.92s ==============================
```

| Test Suite | Count |
|------------|-------|
| 기존 테스트 | 672 |
| Priority 테스트 (신규) | 25 |
| **Total** | **697** |

---

## Files Changed Summary

### New Files (4)
- `priority.py` - Priority enum, NODE_PRIORITY, NODE_DEADLINE_MS, Aging
- `sequence.py` - LamportClock
- `context_helper.py` - create_context, create_error_context
- `test_priority.py` - 25 test cases

### Modified Files (18)
- `state.py` - ChatState, priority_preemptive_reducer
- `factory.py` - StateGraph(ChatState)
- `dependencies.py` - enable_dynamic_routing=True
- `contracts.py` - image_generation field fix
- `answer_node.py` - cleanup_sequence
- `web_search_node.py` - NodeExecutor 추가
- 12 other nodes - Channel Separation pattern

---

## Conclusion

Channel Separation + Priority Scheduling 구현이 성공적으로 완료되었습니다.

- **InvalidUpdateError 해결**: `StateGraph(ChatState)` + Annotated Reducer
- **Dynamic Routing 재활성화**: `enable_dynamic_routing=True`
- **SLA-driven Deadline**: 노드 특성별 자동 적용
- **메모리 관리**: cleanup_sequence 호출
- **일관성 확보**: 모든 노드 NodeExecutor 적용
- **테스트 커버리지**: 697개 테스트 전체 통과

**Overall Assessment**: :white_check_mark: Approved (All issues fixed)
