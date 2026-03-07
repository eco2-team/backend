# Stateless Reducer Pattern + 체크포인팅

> **작성일**: 2026-01-06  
> **관련 문서**: [Scan Worker 마이그레이션 로드맵](./scan-worker-migration-roadmap.md)  
> **참조**: [Stateless Reducer Pattern 이론](https://rooftopsnow.tistory.com/141)

---

## 1. 도입 배경

### 1.1 기존 파이프라인의 문제

Scan Worker의 4단계 파이프라인(Vision → Rule → Answer → Reward)은 Celery Chain으로 구현되어 있었다. 각 Task가 직접 이벤트를 발행하고, 에러를 처리하고, 다음 Task로 데이터를 전달했다.

```python
# 기존 방식 (문제점)
@celery_app.task
def vision_task(task_id, image_url, ...):
    try:
        publish_event("vision", "started")  # Side effect 1
        result = openai.chat.completions.create(...)  # 외부 호출
        publish_event("vision", "completed")  # Side effect 2
        return result  # 다음 Task로 전달
    except Exception as e:
        publish_event("vision", "failed")  # Side effect 3
        raise
```

**문제점:**

1. **테스트 어려움**: 이벤트 발행, API 호출이 뒤섞여 순수 로직 테스트 불가
2. **디버깅 어려움**: 실패 시 어느 시점의 데이터로 재현할지 불분명
3. **복구 어려움**: 중간 실패 시 처음부터 재시작 (LLM 비용 낭비)
4. **코드 중복**: 모든 Task에 동일한 이벤트 발행 보일러플레이트

### 1.2 Stateless Reducer란

**Stateless Reducer**는 함수형 프로그래밍의 Reducer 개념을 파이프라인에 적용한 패턴이다.

```
Reducer: (state, action) → newState
Step:    (ctx) → newCtx
```

핵심 원칙:
1. **순수 함수**: Step은 입력 Context만 받아 새 Context를 반환
2. **Side effect 분리**: 이벤트 발행, 로깅, 체크포인팅은 Runner가 외부에서 처리
3. **불변성**: Context는 복사 후 수정 (원본 보존)

---

## 2. 패턴 적용

### 2.1 Step 인터페이스

모든 Step은 동일한 인터페이스를 구현한다.

```python
class Step(ABC):
    """파이프라인 Step 인터페이스.
    
    Stateless Reducer 패턴:
    - 입력 Context → 처리 → 업데이트된 Context 반환
    - 외부 상태 변경 없음 (이벤트 발행, 로깅 제외)
    """
    
    @abstractmethod
    def run(self, ctx: ClassifyContext) -> ClassifyContext:
        pass
```

### 2.2 Context: 상태 캐리어

`ClassifyContext`는 파이프라인 전체에서 공유되는 상태 객체다.

```python
@dataclass
class ClassifyContext:
    # 입력 (불변)
    task_id: str
    user_id: str
    image_url: str
    
    # Step 결과 (각 Step이 채움)
    classification: dict | None = None
    disposal_rules: dict | None = None
    final_answer: dict | None = None
    reward: dict | None = None
    
    # 메타데이터
    latencies: dict = field(default_factory=dict)
    progress: int = 0
    error: str | None = None
```

**직렬화 지원**: `to_dict()`, `from_dict()`로 Celery Task 간 전달, 체크포인트 저장 가능

```python
# Task 종료 시
return ctx.to_dict()

# 다음 Task 시작 시
ctx = ClassifyContext.from_dict(prev_result)
```

### 2.3 Step 구현 예시

VisionStep은 `VisionModelPort`만 의존한다. Redis, Celery, 로깅은 모른다.

```python
class VisionStep(Step):
    def __init__(
        self,
        vision_model: VisionModelPort,      # 외부 의존성은 Port로 주입
        prompt_repository: PromptRepositoryPort,
    ):
        self._vision = vision_model
        self._prompts = prompt_repository
    
    def run(self, ctx: ClassifyContext) -> ClassifyContext:
        start = time.perf_counter()
        
        # 1. 프롬프트 준비 (순수)
        prompt = self._prompts.get_prompt("vision_classification_prompt")
        schema = self._prompts.get_classification_schema()
        
        # 2. Vision API 호출 (Port 통해 추상화)
        result = self._vision.analyze_image(
            prompt=prompt,
            image_url=ctx.image_url,
        )
        
        # 3. Context 업데이트
        ctx.classification = result
        ctx.latencies["duration_vision_ms"] = (time.perf_counter() - start) * 1000
        ctx.progress = 25
        
        return ctx  # Side effect 없이 ctx만 반환
```

### 2.4 Runner: Side Effect 담당

`SingleStepRunner`는 Step 실행 전후로 이벤트를 발행한다. Step은 순수하게 유지된다.

```python
class SingleStepRunner:
    def __init__(self, event_publisher: EventPublisherPort):
        self._events = event_publisher
    
    def run_step(self, step: Step, step_name: str, ctx: ClassifyContext):
        try:
            # 1. 시작 이벤트 (Side effect)
            self._events.publish_stage_event(ctx.task_id, step_name, "started")
            
            # 2. Step 실행 (순수)
            ctx = step.run(ctx)
            
            # 3. 완료 이벤트 (Side effect)
            self._events.publish_stage_event(ctx.task_id, step_name, "completed")
            
        except Exception as e:
            # 4. 실패 이벤트 (Side effect)
            self._events.publish_stage_event(ctx.task_id, step_name, "failed")
            raise
        
        return ctx
```

---

## 3. 체크포인팅

### 3.1 문제: 실패 시 재시작 비용

기존 Celery Chain은 실패 시 해당 Task만 재시도한다. 그러나 max\_retries를 초과하면 전체 Chain이 중단된다. 수동으로 재시작하려면 처음(Vision)부터 다시 시작해야 한다.

```
vision ──✅──▶ rule ──✅──▶ answer ──❌(3회 실패)
                              ↓
              수동 재시작 시 vision부터 다시 (LLM 비용 ×2)
```

**비용 문제**: Vision과 Answer는 LLM API를 호출한다. 이미 성공한 Vision을 다시 호출하면 불필요한 비용이 발생한다.

### 3.2 해결: CheckpointingStepRunner

`CheckpointingStepRunner`는 Step 완료 시 Context를 Redis에 저장한다.

```python
class CheckpointingStepRunner:
    def __init__(
        self,
        event_publisher: EventPublisherPort,
        context_store: ContextStorePort,  # 체크포인팅 Port
        skip_completed: bool = True,
    ):
        self._events = event_publisher
        self._store = context_store
        self._skip_completed = skip_completed
    
    def run_step(self, step: Step, step_name: str, ctx: ClassifyContext):
        # 1. 이미 완료된 Step인지 확인
        if self._skip_completed:
            checkpoint = self._store.get_checkpoint(ctx.task_id, step_name)
            if checkpoint:
                logger.info(f"Skipping {step_name} - checkpoint exists")
                return ClassifyContext.from_dict(checkpoint)
        
        try:
            # 2. 시작 이벤트
            self._events.publish_stage_event(ctx.task_id, step_name, "started")
            
            # 3. Step 실행
            ctx = step.run(ctx)
            
            # 4. ✅ 체크포인트 저장
            self._store.save_checkpoint(ctx.task_id, step_name, ctx.to_dict())
            
            # 5. 완료 이벤트
            self._events.publish_stage_event(ctx.task_id, step_name, "completed")
            
        except Exception as e:
            self._events.publish_stage_event(ctx.task_id, step_name, "failed")
            raise
        
        return ctx
```

### 3.3 체크포인트 저장소

`RedisContextStore`는 체크포인트를 Redis에 저장한다. TTL은 1시간으로, 파이프라인 완료 전 실패 복구 윈도우를 제공한다.

```python
class RedisContextStore(ContextStorePort):
    def save_checkpoint(self, task_id: str, step_name: str, context: dict):
        key = f"scan:checkpoint:{task_id}:{step_name}"
        self._redis.setex(key, 3600, json.dumps(context))
    
    def get_checkpoint(self, task_id: str, step_name: str) -> dict | None:
        key = f"scan:checkpoint:{task_id}:{step_name}"
        data = self._redis.get(key)
        return json.loads(data) if data else None
    
    def get_latest_checkpoint(self, task_id: str) -> tuple[str, dict] | None:
        """가장 마지막 성공 체크포인트 반환."""
        # Step 순서: vision(1) → rule(2) → answer(3) → reward(4)
        for step in ["reward", "answer", "rule", "vision"]:
            checkpoint = self.get_checkpoint(task_id, step)
            if checkpoint:
                return (step, checkpoint)
        return None
```

### 3.4 복구 흐름

Answer에서 실패 후 수동 재시작하는 시나리오:

```
1. answer_task max_retries 초과로 실패

2. 운영자가 복구 스크립트 실행:
   runner = get_checkpointing_step_runner()
   ctx = runner.resume_from_checkpoint("task-123")
   # → rule 체크포인트에서 ctx 복원 (vision, rule 결과 포함)

3. answer부터 재시작:
   ctx = runner.run_step(get_answer_step(), "answer", ctx)
   ctx = runner.run_step(get_reward_step(), "reward", ctx)
   
4. 결과:
   - vision LLM 호출: 0회 (체크포인트 사용)
   - rule 조회: 0회 (체크포인트 사용)
   - answer LLM 호출: 1회 (재시작)
   - 비용 절감!
```

---

## 4. Celery Chain과의 관계

### 4.1 기존 Chain 구조 유지

체크포인팅을 도입했지만, Celery Chain 구조는 그대로 유지한다. 각 Task는 `CheckpointingStepRunner`를 사용한다.

```python
# vision_task.py
@celery_app.task(bind=True, max_retries=2)
def vision_task(self, task_id, user_id, image_url, model=None):
    ctx = create_context(task_id, user_id, image_url, model=model)
    
    step = get_vision_step(model)
    runner = get_checkpointing_step_runner()  # ✅ 체크포인팅 적용
    
    ctx = runner.run_step(step, "vision", ctx)
    
    return ctx.to_dict()  # 다음 Task로 전달
```

### 4.2 자동 복구 vs 수동 복구

| 시나리오 | 복구 방식 |
|----------|----------|
| Task 내 일시적 실패 | Celery `self.retry()` (자동) |
| max_retries 초과 | 체크포인트에서 수동 재시작 |
| Worker 크래시 | 체크포인트에서 수동 재시작 |

**Note**: 자동 복구(retry) 시에도 체크포인트를 확인한다. 이미 완료된 Step은 스킵하므로 LLM 중복 호출이 방지된다.

---

## 5. 이점 정리

### 5.1 테스트 용이성

Step이 순수 함수이므로, Mock Port만 주입하면 API 호출 없이 테스트 가능하다.

```python
def test_vision_step():
    step = VisionStep(
        vision_model=MockVisionModel(),      # API 호출 없음
        prompt_repository=MockPromptRepository(),
    )
    
    ctx = ClassifyContext(task_id="test", user_id="user", image_url="http://...")
    result = step.run(ctx)
    
    assert result.classification is not None
    assert result.progress == 25
```

### 5.2 디버깅 재현성

Context를 저장해두면, 나중에 같은 시작점에서 재실행 가능하다.

```python
# 프로덕션에서 실패한 ctx 덤프
failed_ctx = redis.get("scan:checkpoint:task-123:rule")

# 로컬에서 재현
ctx = ClassifyContext.from_dict(json.loads(failed_ctx))
step = get_answer_step("gpt-5.2")
result = step.run(ctx)  # 동일 입력으로 디버깅
```

### 5.3 비용 절감

체크포인팅으로 LLM 재호출을 방지한다.

| 시나리오 | 체크포인팅 없음 | 체크포인팅 있음 |
|----------|---------------|----------------|
| Vision ✅ → Rule ✅ → Answer ❌ | Vision 재호출 | 체크포인트 사용 |
| 복구 시 LLM 호출 | 2회 (Vision, Answer) | 1회 (Answer) |

---

## 6. LangGraph와의 비교

LangGraph는 체크포인팅을 내장 지원하며, 조건부 분기(Conditional Edge)에 강점이 있다. Scan 파이프라인은 순차 실행이므로 LangGraph 도입 대신 경량 구현을 선택했다.

| 항목 | Scan Worker (직접 구현) | LangGraph |
|------|------------------------|-----------|
| 체크포인팅 | `CheckpointingStepRunner` | 내장 `MemorySaver` |
| 조건부 분기 | 미지원 (순차 전용) | `add_conditional_edges` |
| 의존성 | 없음 | `langgraph` 패키지 |
| 적용 대상 | Scan (순차) | Chat (분기 필요) |

**향후 계획**: Chat 파이프라인은 사용자 응답에 따른 분기가 필요하므로 LangGraph 도입을 검토 중이다.

---

## 7. 구현 체크리스트

- [x] `Step` ABC 정의 (`application/common/step_interface.py`)
- [x] `ClassifyContext` 직렬화 (`to_dict`, `from_dict`)
- [x] `SingleStepRunner` 구현
- [x] `ContextStorePort` 정의
- [x] `RedisContextStore` 구현
- [x] `CheckpointingStepRunner` 구현
- [x] 모든 Task에 체크포인팅 적용
- [ ] 복구 스크립트/CLI 도구 (선택)

---

## References

- [Stateless Reducer Pattern 이론](https://rooftopsnow.tistory.com/141)
- [LangGraph Checkpointing](https://langchain-ai.github.io/langgraph/concepts/persistence/)
- [함수형 프로그래밍의 Reducer](https://redux.js.org/tutorials/fundamentals/part-3-state-actions-reducers)

