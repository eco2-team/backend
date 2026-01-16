# Chat Worker 코드 리뷰 수정 리포트

> Production Architecture P1 구현 이후 코드 리뷰에서 발견된 이슈와 수정 사항

**작성일**: 2026-01-16
**브랜치**: `refactor/reward-fanout-exchange`
**관련 커밋**:
- [`01f765f2`] refactor(chat_worker): implement Single Source of Truth for node contracts
- [`db51ab44`] fix(chat_worker): resolve race conditions and fallback execution bugs

---

## 목차

1. [코드 리뷰 발견 사항](#1-코드-리뷰-발견-사항)
2. [Issue 1: Circuit Breaker Race Condition](#2-issue-1-circuit-breaker-race-condition)
3. [Issue 2: FAIL_FALLBACK 미실행](#3-issue-2-fail_fallback-미실행)
4. [Issue 3: node_policy vs aggregator 불일치](#4-issue-3-node_policy-vs-aggregator-불일치)
5. [검증 방법](#5-검증-방법)
6. [결론](#6-결론)

---

## 1. 코드 리뷰 발견 사항

P1 Production Resilience 구현 후 코드 리뷰에서 다음 이슈가 발견되었습니다.

| 심각도 | 이슈 | 파일 | 상태 |
|--------|------|------|------|
| **Critical** | Circuit Breaker 싱글톤 race condition | `circuit_breaker.py` | ✅ 수정됨 |
| **High** | FAIL_FALLBACK fallback 함수 미실행 | `node_executor.py` | ✅ 수정됨 |
| **Medium** | node_policy/aggregator 필드 불일치 | 여러 파일 | ✅ 수정됨 |

---

## 2. Issue 1: Circuit Breaker Race Condition

### 2.1 문제 설명

`CircuitBreakerRegistry` 싱글톤 패턴에서 동시성 문제가 발견되었습니다.

**파일**: `apps/chat_worker/infrastructure/resilience/circuit_breaker.py`

#### 문제점 A: asyncio.Lock 클래스 변수

```python
# 수정 전
class CircuitBreakerRegistry:
    _lock = asyncio.Lock()  # ❌ 모듈 import 시점에 생성
```

**원인**:
- `asyncio.Lock()`은 생성 시 현재 이벤트 루프에 바인딩
- 모듈 import는 이벤트 루프 생성 전에 발생
- 런타임에 다른 루프에서 사용 시 `RuntimeError` 발생 가능

```
RuntimeError: Task <Task pending> attached to a different loop
```

#### 문제점 B: 싱글톤 생성 Race Condition

```python
# 수정 전
def __new__(cls):
    if cls._instance is None:      # check
        cls._instance = ...        # then act (non-atomic!)
    return cls._instance
```

**Race Condition 시나리오**:

```
시간   Thread A                    Thread B
────────────────────────────────────────────────────
t1    if _instance is None
t2    → True                      if _instance is None
t3    instance = new()            → True (아직 할당 안 됨)
t4    _instance = inst_A          instance = new()
t5                                _instance = inst_B  ← 덮어씀!
```

**결과**:
- Thread A는 `inst_A` 참조
- Thread B는 `inst_B` 참조
- 싱글톤 보장 실패 → 각 스레드가 다른 Registry 사용

#### 문제점 C: get() 메서드 Race Condition

```python
# 수정 전
def get(self, name, ...):
    if name not in self._breakers:     # check
        self._breakers[name] = CB()    # then act
    return self._breakers[name]
```

**결과**: 동일 이름으로 여러 CircuitBreaker 인스턴스 생성 가능
- 각 인스턴스가 독립적으로 failure count 관리
- Circuit Breaker 효과 무력화

### 2.2 해결 방법

#### 해결 A: threading.Lock 사용

```python
# 수정 후
class CircuitBreakerRegistry:
    _creation_lock = threading.Lock()  # ✅ 이벤트 루프 독립적
```

**선택 이유**:
- `__new__`와 `get()`은 동기 메서드
- `asyncio.Lock`은 `async with`만 가능
- `threading.Lock`은 동기/비동기 컨텍스트 모두 호환

#### 해결 B: Double-Checked Locking (DCL)

```python
# 수정 후
def __new__(cls):
    if cls._instance is None:           # 1차 체크 (lock-free)
        with cls._creation_lock:        # lock 획득
            if cls._instance is None:   # 2차 체크 (lock 내부)
                instance = super().__new__(cls)
                instance._breakers = {}
                instance._registry_lock = threading.Lock()
                cls._instance = instance
    return cls._instance
```

**DCL 동작 원리**:

```
시간   Thread A                         Thread B
─────────────────────────────────────────────────────────
t1    if _instance is None → True
t2    with _creation_lock: (획득)       if _instance is None → True
t3      if _instance is None → True    with _creation_lock: (대기)
t4      instance = new()               ...
t5      _instance = instance           ...
t6    (lock 해제)                       (lock 획득)
t7                                       if _instance is None → False
t8                                     (lock 해제)
t9    return _instance                 return _instance ← 동일 인스턴스
```

#### 해결 C: get() Fast Path + DCL

```python
# 수정 후
def get(self, name, ...):
    # Fast path: 대부분의 호출은 여기서 반환 (lock-free)
    if name in self._breakers:
        return self._breakers[name]

    # Slow path: 최초 생성 시에만 lock
    with self._registry_lock:
        if name not in self._breakers:  # DCL 2차 체크
            self._breakers[name] = CircuitBreaker(...)
        return self._breakers[name]
```

**Fast Path 필요성**:
- Python dict 읽기는 GIL로 원자적
- 대부분의 호출은 기존 CB 조회 (hot path)
- Lock 획득 비용 회피 → 성능 개선

#### 해결 D: 테스트 격리 지원

```python
# 수정 후
@classmethod
def reset_instance(cls):
    """싱글톤 인스턴스 리셋 (테스트용)."""
    with cls._creation_lock:
        cls._instance = None
```

**용도**: pytest fixture에서 테스트 간 격리

```python
@pytest.fixture(autouse=True)
def clean_circuit_breakers():
    yield
    CircuitBreakerRegistry.reset_instance()
```

### 2.3 수정 결과

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| Lock 타입 | `asyncio.Lock` (클래스 변수) | `threading.Lock` |
| 싱글톤 생성 | 단순 체크 | Double-Checked Locking |
| get() 메서드 | 단순 체크 | Fast Path + DCL |
| 테스트 격리 | 불가 | `reset_instance()` 제공 |

---

## 3. Issue 2: FAIL_FALLBACK 미실행

### 3.1 문제 설명

**파일**: `apps/chat_worker/infrastructure/orchestration/langgraph/nodes/node_executor.py`

`FAIL_FALLBACK` 모드에서 fallback 함수가 실제로 실행되지 않았습니다.

```python
# 수정 전
def _handle_failure(self, ...):  # ❌ 동기 메서드
    if policy.fail_mode == FailMode.FAIL_FALLBACK:
        if fallback_func:
            # Note: fallback_func는 async이므로 await 필요
            # 여기서는 상태만 반환하고, 실제 fallback은 호출자가 처리
            result_state = {
                **state,
                f"{node_name}_fallback_triggered": True,  # ❌ 플래그만 설정
            }
            return self._append_node_result(result_state, result)
```

**문제**:
- `_handle_failure`가 동기 메서드
- `fallback_func`는 async 함수
- 실제 호출 없이 플래그만 설정 → fallback 미실행

### 3.2 해결 방법

```python
# 수정 후
async def _handle_failure(self, ...):  # ✅ async로 변경
    if policy.fail_mode == FailMode.FAIL_FALLBACK:
        if fallback_func:
            try:
                # ✅ fallback 함수 실제 실행
                fallback_state = await fallback_func(state)

                result_with_fallback = NodeResult(
                    node_name=result.node_name,
                    status="fallback_success",  # ✅ 새 상태
                    ...
                )
                return self._append_node_result(fallback_state, result_with_fallback)
            except Exception as e:
                # fallback도 실패 시 graceful 처리
                logger.warning("Fallback function also failed", ...)
                return self._append_node_result(state, result)
```

**호출부 수정**:

```python
# 수정 전
return self._handle_failure(...)

# 수정 후
return await self._handle_failure(...)  # ✅ await 추가
```

### 3.3 수정 결과

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 메서드 타입 | `def` (동기) | `async def` (비동기) |
| Fallback 실행 | 플래그만 설정 | 실제 `await` 호출 |
| 결과 상태 | N/A | `fallback_success` |
| 에러 처리 | N/A | try/except로 graceful 처리 |

---

## 4. Issue 3: node_policy vs aggregator 불일치

### 4.1 문제 설명

`node_policy.py`와 `aggregator_node.py`에서 필수 컨텍스트 정의가 중복되어 불일치 위험이 있었습니다.

**node_policy.py**:
```python
REQUIRED_CONTEXTS = frozenset(
    policy.name for policy in NODE_POLICIES.values() if policy.is_required
)
# 결과: {"waste_rag", "bulk_waste", "location", "general"}
```

**aggregator_node.py**:
```python
INTENT_REQUIRED_CONTEXT_FIELDS = {
    "waste": frozenset({"disposal_rules"}),
    "bulk_waste": frozenset({"bulk_waste_context"}),
    # ... weather 누락!
}
```

**문제점**:
- 두 곳에서 독립적으로 정의 → 변경 시 동기화 필요
- `is_required`가 노드 단위 vs 필드 단위로 다른 개념
- Intent별 필수 필드가 다를 수 있음 (예: waste에서 character는 선택)

### 4.2 해결 방법: Single Source of Truth

**새 파일**: `apps/chat_worker/infrastructure/orchestration/langgraph/contracts.py`

```python
# 1. 노드 출력 계약 (노드가 생산하는 필드)
NODE_OUTPUT_FIELDS = {
    "waste_rag": frozenset({"disposal_rules"}),
    "character": frozenset({"character_context"}),
    ...
}

# 2. Intent 필수 필드 (Single Source of Truth)
INTENT_REQUIRED_FIELDS = {
    "waste": frozenset({"disposal_rules"}),
    "bulk_waste": frozenset({"bulk_waste_context"}),
    ...
}

# 3. 파생 함수 (is_required는 계산됨)
def is_node_required_for_intent(node_name: str, intent: str) -> bool:
    """is_required = (node outputs ∩ intent required fields) ≠ ∅"""
    node_outputs = NODE_OUTPUT_FIELDS.get(node_name, frozenset())
    required_fields = INTENT_REQUIRED_FIELDS.get(intent, frozenset())
    return bool(node_outputs & required_fields)

# 4. Import-time 검증
def validate_contracts():
    """모든 필수 필드가 생산 가능한지 정적 검증."""
    for intent, required_fields in INTENT_REQUIRED_FIELDS.items():
        for field in required_fields:
            if field not in FIELD_TO_NODES:
                errors.append(f"Intent '{intent}' requires '{field}' but no node produces it")
```

### 4.3 적용 결과

**aggregator_node.py 수정**:
```python
# 수정 전
required_fields = INTENT_REQUIRED_CONTEXT_FIELDS.get(intent, frozenset())

# 수정 후
from contracts import validate_missing_fields
missing_required, missing_optional = validate_missing_fields(intent, collected_fields)
```

**node_policy.py 수정**:
```python
# 수정 전
@dataclass
class NodePolicy:
    is_required: bool  # 하드코딩

# 수정 후
@dataclass
class NodePolicy:
    # is_required 제거, 메서드로 대체
    def is_required_for(self, intent: str) -> bool:
        return is_node_required_for_intent(self.name, intent)
```

### 4.4 검증 테스트

```python
# test_contracts.py
def test_validate_contracts_passes():
    """모든 필수 필드가 생산 가능해야 함."""
    result = validate_contracts()
    assert result.is_valid, f"Errors: {result.errors}"

def test_is_node_required_for_intent():
    assert is_node_required_for_intent("waste_rag", "waste") == True
    assert is_node_required_for_intent("waste_rag", "general") == False
    assert is_node_required_for_intent("character", "waste") == False
```

---

## 5. 검증 방법

### 5.1 단위 테스트

```bash
# Contract 검증
pytest apps/chat_worker/tests/unit/infrastructure/orchestration/langgraph/test_contracts.py -v

# Circuit Breaker 동시성 테스트 (향후 추가)
pytest apps/chat_worker/tests/unit/infrastructure/resilience/ -v
```

### 5.2 수동 검증

```python
# contracts.py 정적 검증 (import 시 자동 실행)
python -c "from chat_worker.infrastructure.orchestration.langgraph.contracts import validate_contracts; print(validate_contracts())"
# ContractValidationResult(is_valid=True, errors=())

# Circuit Breaker DCL 검증
python -c "
from chat_worker.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry
r1 = CircuitBreakerRegistry()
r2 = CircuitBreakerRegistry()
print(f'Same instance: {r1 is r2}')  # True
"
```

---

## 6. 결론

### 6.1 수정 요약

| 이슈 | 파일 | 수정 내용 |
|------|------|-----------|
| Race Condition | `circuit_breaker.py` | threading.Lock + DCL |
| Fallback 미실행 | `node_executor.py` | async 변환 + await |
| 필드 불일치 | `contracts.py` (신규) | Single Source of Truth |

### 6.2 아키텍처 개선

```
수정 전:
┌─────────────────┐     ┌──────────────────┐
│  node_policy.py │     │ aggregator_node  │
│  is_required    │     │ INTENT_REQUIRED  │
│  (하드코딩)      │     │ (하드코딩, 중복)  │
└─────────────────┘     └──────────────────┘

수정 후:
┌─────────────────────────────────────────┐
│           contracts.py                   │
│  INTENT_REQUIRED_FIELDS (Source)        │
│  NODE_OUTPUT_FIELDS (Contract)          │
│  is_node_required_for_intent() (Derive) │
└──────────────────┬──────────────────────┘
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
┌─────────────────┐     ┌──────────────────┐
│  node_policy.py │     │ aggregator_node  │
│  .is_required_  │     │ validate_missing │
│   for(intent)   │     │ _fields()        │
└─────────────────┘     └──────────────────┘
```

### 6.3 후속 작업

- [ ] Circuit Breaker 동시성 스트레스 테스트 추가
- [ ] Fallback 함수 구현체 작성 (현재 None 전달)
- [ ] Contract 변경 시 CI 검증 자동화
