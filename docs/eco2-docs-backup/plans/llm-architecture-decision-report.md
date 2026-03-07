# Eco² LLM 아키텍처 의사결정 리포트

> **작성일**: 2026-01-05  
> **작성자**: AI Assistant (Claude Opus 4.5)  
> **상태**: Draft  
> **관련 서비스**: scan, scan-worker, chat, chat-worker

---

## 📋 Executive Summary

본 리포트는 Eco² 백엔드의 LLM 파이프라인 아키텍처에 대한 기술적 의사결정을 문서화합니다.

**핵심 결정사항:**
1. **Scan 파이프라인**: LangGraph 미도입, Stateless Reducer 패턴 적용
2. **Chat 파이프라인**: LangGraph 도입으로 분기 로직 구현
3. **공통**: LangChain 기반 DI(Dependency Injection)로 LLM 클라이언트 추상화

---

## 1. Scan 파이프라인: LangGraph 미도입 결정

### 1.1 현재 구조 분석

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Scan Pipeline 의존성 그래프                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Vision ──────▶ RAG ──────▶ Answer ──────▶ Reward                          │
│   (~3000ms)      (~3ms)      (~2500ms)      (~50ms)                         │
│                                                                              │
│   의존성:                                                                    │
│   - RAG: Vision.classification 필요                                         │
│   - Answer: Vision + RAG 결과 필요                                          │
│   - Reward: Vision + RAG + Answer.insufficiencies 필요                      │
│                                                                              │
│   총 소요시간: ~5.5초 (순차 실행 필수)                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 LangGraph 미도입 사유

| 평가 항목 | 현재 구조 | LangGraph 도입 시 | 판정 |
|----------|----------|-------------------|------|
| **조건부 분기** | 없음 (일직선) | 오버스펙 | ❌ 불필요 |
| **병렬 실행** | 불가능 (의존성) | 불가능 (의존성) | ❌ 효과 없음 |
| **상태 관리** | prev_result 전달 | StateGraph | ⚪ 동등 |
| **복잡도** | 낮음 | 증가 | ❌ 불리 |
| **러닝 커브** | 없음 | 학습 필요 | ❌ 불리 |
| **의존성** | 없음 | langgraph, langchain | ❌ 증가 |

**결론**: Scan 파이프라인은 단순 순차 실행이므로 LangGraph 도입은 **오버엔지니어링**

### 1.3 병렬화 불가능 분석

```
Vision ──▶ RAG ──▶ Answer ──▶ Reward
   │         │        │         │
   │         │        │         └── needs: classification + disposal + answer
   │         │        │
   │         │        └── needs: classification + disposal_rules
   │         │
   │         └── needs: classification.major_category, middle_category
   │
   └── 모든 것의 시작점

※ 엄격한 순차 의존성으로 병렬화 여지 없음
```

### 1.4 Scan 아키텍처 최종 결정

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Scan 최종 아키텍처                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [Client]                                                                  │
│       │                                                                      │
│       ├── POST /scan ──────────────────┐                                    │
│       │                                │                                    │
│       │   return task_id               ▼                                    │
│       │                           [scan-api]                                │
│       │                                │                                    │
│       │                                └── Celery Task 발행                 │
│       │                                         │                           │
│       │                                         ▼                           │
│       │                              [RabbitMQ Queue]                       │
│       │                                         │                           │
│       │                                         ▼                           │
│       │                              [scan-worker]                          │
│       │                                    │                                │
│       │                                    ├── vision_reducer()             │
│       │                                    ├── rag_reducer()                │
│       │                                    ├── answer_reducer()             │
│       │                                    └── reward_reducer()             │
│       │                                         │                           │
│       │                                         │ 각 단계 완료 시           │
│       │                                         ▼                           │
│       │                              [Redis Streams]                        │
│       │                              (이벤트 영구 저장)                     │
│       │                                         │                           │
│       │                                         ▼                           │
│       │                              [Event Router]                         │
│       │                              (Consumer Group)                       │
│       │                                    │    │                           │
│       │                                    │    └── State KV 업데이트       │
│       │                                    │        (복구용)                │
│       │                                    ▼                                │
│       │                              [Redis Pub/Sub]                        │
│       │                              (실시간 전달)                          │
│       │                                    │                                │
│       │                                    ▼                                │
│       └── GET /stream ──────────▶ [SSE Gateway] ──────▶ 실시간 이벤트       │
│           (task_id 구독)                                                    │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   기술 스택:                                                                 │
│   - Celery + RabbitMQ (Job 큐잉)                                            │
│   - Stateless Reducer 패턴 (LangGraph 없이)                                 │
│   - LangChain LLM Client (DI)                                               │
│   - Redis Streams (이벤트 소싱, 영구 저장)                                  │
│   - Event Router (Consumer Group, State KV 관리)                            │
│   - Redis Pub/Sub (실시간 전달)                                             │
│   - SSE Gateway (클라이언트 스트리밍)                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.5 LLM 모델 선택 위치 결정

> **결정**: Scan API에서 모델을 선택하고, Celery 메시지로 Worker에 전달한다.

#### 1.5.1 선택지 분석

| 위치 | 장점 | 단점 |
|------|------|------|
| **Scan API** | 클라이언트 모델 선택 가능, Rate limiting, 추적성 | Celery 메시지에 model 포함 필요 |
| **Scan Worker** | 단순 | 동적 선택 어려움, 유연성 부족 |

#### 1.5.2 결정: Scan API에서 모델 선택

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LLM 모델 선택 흐름                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [Client]                                                                  │
│       │                                                                      │
│       │ POST /scan { model_tier: "premium" }  (선택적)                      │
│       │                                                                      │
│       ▼                                                                      │
│   [Scan API]                                                                │
│       │                                                                      │
│       ├── 1. 모델 선택 (model_tier → 실제 모델명)                           │
│       │       - premium: gpt-4o                                             │
│       │       - standard: gpt-4o-mini                                       │
│       │       - economy: gemini-2.0-flash                                   │
│       │                                                                      │
│       └── 2. Celery Task 발행 (model 정보 포함)                             │
│               chain(vision, rule, answer, reward)                           │
│               args: [task_id, user_id, image_url, user_input, model]        │
│                         │                                                   │
│                         ▼                                                   │
│   [RabbitMQ] ─────▶ [Scan Worker]                                          │
│                         │                                                   │
│                         ├── 3. model 정보 추출                              │
│                         │                                                   │
│                         └── 4. 해당 모델로 LLM 호출                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 1.5.3 구현 설계

```python
# apps/scan/presentation/http/controllers/scan.py
@router.post("/scan")
async def submit_scan(
    request: ScanRequest,
    model_tier: str = Query("standard", enum=["premium", "standard", "economy"]),
    command: SubmitCommandDep,
):
    """Scan 요청 제출 - 모델 티어 선택 가능."""
    return await command.execute(
        SubmitClassificationRequest(
            user_id=request.user_id,
            image_url=request.image_url,
            user_input=request.user_input,
            model_tier=model_tier,  # 모델 티어 전달
        )
    )


# apps/scan/application/classify/commands/submit_classification.py
class SubmitClassificationCommand:
    MODEL_TIER_MAP = {
        "premium": "gpt-4o",
        "standard": "gpt-4o-mini",
        "economy": "gemini-2.0-flash",
    }
    
    async def execute(self, request: SubmitClassificationRequest):
        model = self.MODEL_TIER_MAP.get(request.model_tier, "gpt-4o-mini")
        
        pipeline = chain(
            self._celery_app.signature(
                "scan.vision",
                args=[job_id, request.user_id, request.image_url, user_input, model],
                #                                                            ↑ 모델 전달
                queue="scan.vision",
            ),
            # ... 나머지 chain
        )


# apps/scan_worker/presentation/tasks/vision_task.py
@celery_app.task(name="scan.vision")
def vision_task(
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None,
    model: str = "gpt-4o-mini",  # 기본값
) -> dict:
    """Vision Task - API에서 전달받은 모델 사용."""
    # model 정보를 waste_pipeline에 전달하거나
    # LangChain DI로 해당 모델 클라이언트 사용
    llm_client = get_llm_client(model)
    # ...
```

---

### 1.6 Stateless Reducer 패턴 적용

> **결정**: Scan 파이프라인에 Stateless Reducer 패턴을 적용한다.  
> **주의**: 성능상 이점은 없으며, 코드 품질(테스트/디버깅/유지보수) 향상만 기대한다.

#### 1.6.1 Stateless Reducer 패턴이란?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Stateless Reducer 패턴                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   정의:                                                                      │
│   "각 Vertex는 개별 상태를 가지지 않고, 업데이트로 처리해                   │
│    최대한 stateless로 만드는 접근이다."                                     │
│                                                                              │
│   핵심 원칙:                                                                 │
│   1. 각 노드는 자체 내부 상태를 유지하지 않음 (stateless)                   │
│   2. 노드는 전체 상태를 입력으로 받음                                       │
│   3. 노드는 변경분(delta)만 반환                                            │
│   4. 상태 병합은 외부(파이프라인 러너)가 담당                               │
│                                                                              │
│   코드 패턴:                                                                 │
│   def node(state: State) -> dict:      # 전체 State 입력                    │
│       result = process(state["input"])                                      │
│       return {"output": result}         # 업데이트만 반환                   │
│                                                                              │
│   # 파이프라인 러너가 병합                                                  │
│   new_state = {**old_state, **node_output}                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 1.6.2 성능 영향 분석

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    성능 영향: 없음                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Scan Pipeline 소요 시간:                                                   │
│   Vision ──────▶ RAG ──────▶ Answer ──────▶ Reward                          │
│   ~3000ms        ~3ms        ~2500ms        ~50ms                           │
│                                                                              │
│   병목 지점: LLM API 호출 (Vision 54%, Answer 45%)                          │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   성능 최적화 가능성:                                                        │
│                                                                              │
│   | 기법           | Stateless Reducer 적용 시 | Scan 파이프라인 |           │
│   |----------------|--------------------------|-----------------|           │
│   | 병렬 처리       | 독립 노드 병렬 실행 가능   | ❌ 의존성으로 불가 |         │
│   | 캐싱           | 순수 함수라 캐싱 용이     | 🔶 패턴 없이도 가능 |        │
│   | 메모리         | 업데이트만 전달           | ⚪ 미미한 차이     |         │
│   | CPU/I/O        | 변화 없음                | ⚪ 동일           |          │
│                                                                              │
│   결론: 엄격한 순차 의존성으로 성능 향상 없음                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 1.6.3 품질 향상 이점

| 이점 | 설명 | Before | After |
|------|------|--------|-------|
| **테스트 용이성** | 각 reducer 독립 테스트 | 전체 파이프라인 테스트 필요 | 노드 단위 테스트 가능 |
| **디버깅** | 각 단계 입출력 스냅샷 | 중간 상태 추적 어려움 | 상태 변화 명확 |
| **재현성** | 동일 입력 → 동일 출력 | 부수 효과 가능성 | 순수 함수 보장 |
| **유지보수** | 단계 추가/제거 용이 | 함수 내부 수정 필요 | 노드 추가만 |
| **로깅** | 상태 변화 추적 용이 | 수동 로깅 | 자동 상태 diff |

#### 1.6.4 구현 설계

```python
# apps/scan_worker/application/pipeline/state.py
from typing import TypedDict

class ScanState(TypedDict):
    """Scan 파이프라인 상태 (불변 스냅샷)."""
    task_id: str
    user_id: str
    image_url: str
    user_input: str
    classification: dict | None
    rules: dict | None
    answer: dict | None
    reward: dict | None
    progress: int
    error: str | None
```

```python
# apps/scan_worker/application/pipeline/reducers/vision_reducer.py
from apps.scan_worker.application.ports.llm_client import LLMClient
from apps.scan_worker.application.pipeline.state import ScanState


def create_vision_reducer(llm_client: LLMClient):
    """Vision Reducer 팩토리 (DI + Stateless Reducer).
    
    ※ 노드는 자체 상태 없음 (stateless)
    ※ 전체 상태 입력 → 업데이트만 반환
    """
    
    async def vision_reducer(state: ScanState) -> dict:
        # 1. 입력에서 필요한 값만 추출
        image_url = state["image_url"]
        user_input = state["user_input"]
        
        # 2. 순수 로직 실행
        result = await llm_client.invoke_with_image(
            prompt=load_prompt("vision"),
            image_url=image_url,
        )
        
        # 3. 업데이트만 반환 (전체 상태 X)
        return {
            "classification": result,
            "progress": 25,
        }
    
    return vision_reducer
```

```python
# apps/scan_worker/application/pipeline/reducers/rag_reducer.py
def rag_reducer(state: ScanState) -> dict:
    """RAG Reducer (LLM 불필요, 파일 매칭).
    
    ※ 순수 함수: 동일 입력 → 동일 출력
    """
    classification = state["classification"]
    
    rules = get_disposal_rules(classification)
    
    return {
        "rules": rules,
        "progress": 50,
    }
```

```python
# apps/scan_worker/application/pipeline/runner.py
from apps.scan_worker.application.pipeline.state import ScanState


async def run_pipeline(
    initial_state: ScanState,
    reducers: list,
    event_publisher,
) -> ScanState:
    """Stateless Reducer 파이프라인 러너.
    
    1. 각 reducer 순차 실행
    2. 상태 병합 (불변 방식)
    3. 이벤트 발행
    """
    state = initial_state
    
    for reducer in reducers:
        try:
            # 1. Reducer 실행 (업데이트만 반환)
            update = await reducer(state)
            
            # 2. 상태 병합 (불변)
            state = {**state, **update}
            
            # 3. 이벤트 발행 (SSE)
            await event_publisher.publish(state["task_id"], {
                "stage": reducer.__name__,
                "progress": state["progress"],
            })
            
        except Exception as e:
            state = {**state, "error": str(e)}
            break
    
    return state
```

```python
# apps/scan_worker/presentation/tasks/scan_job.py
from apps.scan_worker.application.pipeline.runner import run_pipeline
from apps.scan_worker.application.pipeline.reducers import (
    create_vision_reducer,
    rag_reducer,
    create_answer_reducer,
    create_reward_reducer,
)
from apps.scan_worker.setup.llm_factory import get_llm_client


@celery_app.task(name="scan.job")
async def scan_job(task_id: str, user_id: str, image_url: str, user_input: str):
    """Scan Job - Stateless Reducer 패턴."""
    
    # DI: LLM 클라이언트 주입
    llm = get_llm_client("gpt-4o")
    
    # Reducers 구성 (DI 적용)
    reducers = [
        create_vision_reducer(llm),   # LLM Vision
        rag_reducer,                   # 파일 매칭 (LLM 없음)
        create_answer_reducer(llm),    # LLM 답변 생성
        create_reward_reducer(),       # 보상 계산 (LLM 없음)
    ]
    
    # 초기 상태
    initial_state: ScanState = {
        "task_id": task_id,
        "user_id": user_id,
        "image_url": image_url,
        "user_input": user_input,
        "classification": None,
        "rules": None,
        "answer": None,
        "reward": None,
        "progress": 0,
        "error": None,
    }
    
    # 파이프라인 실행
    result = await run_pipeline(initial_state, reducers, event_publisher)
    
    return result
```

#### 1.6.5 테스트 예시

```python
# apps/scan_worker/tests/unit/reducers/test_vision_reducer.py
import pytest
from apps.scan_worker.application.pipeline.reducers.vision_reducer import create_vision_reducer
from apps.scan_worker.tests.fixtures.mock_llm import MockLLMClient


@pytest.mark.asyncio
async def test_vision_reducer_returns_only_update():
    """Vision Reducer가 업데이트만 반환하는지 테스트.
    
    Stateless Reducer 패턴 검증:
    - 전체 상태가 아닌 변경분만 반환
    - 입력 상태를 변경하지 않음
    """
    # Mock LLM
    mock_llm = MockLLMClient(responses={
        "vision": '{"major_category": "재활용폐기물", "middle_category": "플라스틱류"}'
    })
    
    # Reducer 생성 (DI)
    vision_reducer = create_vision_reducer(mock_llm)
    
    # 입력 상태
    input_state = {
        "task_id": "test-123",
        "image_url": "https://example.com/plastic.jpg",
        "user_input": "이거 뭐야?",
        "classification": None,  # 아직 없음
        "progress": 0,
    }
    
    # 실행
    update = await vision_reducer(input_state)
    
    # 검증: 업데이트만 반환
    assert "classification" in update
    assert "progress" in update
    assert update["progress"] == 25
    
    # 검증: 다른 필드는 포함하지 않음
    assert "task_id" not in update
    assert "image_url" not in update
    
    # 검증: 입력 상태 불변
    assert input_state["classification"] is None
    assert input_state["progress"] == 0
```

#### 1.6.6 결정 근거 요약

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Stateless Reducer 적용 결정 근거                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ✅ 적용하는 이유:                                                          │
│   ─────────────────                                                          │
│   - 테스트 용이성 향상 (각 reducer 독립 테스트)                             │
│   - 디버깅 용이성 향상 (상태 스냅샷, 변화 추적)                             │
│   - 재현 가능성 보장 (순수 함수, 동일 입력 → 동일 출력)                     │
│   - 유지보수 향상 (노드 추가/제거 용이)                                     │
│   - LangGraph 없이 패턴만 적용 (추가 의존성 없음)                           │
│                                                                              │
│   ⚠️ 주의사항:                                                               │
│   ─────────────                                                              │
│   - 성능 향상 없음 (순차 의존성으로 병렬화 불가)                            │
│   - 병목은 LLM API 호출 (Vision, Answer)                                   │
│   - 성능 최적화는 LLM 캐싱, 모델 변경 등 별도 접근 필요                     │
│                                                                              │
│   결론:                                                                      │
│   Stateless Reducer는 성능 도구가 아닌 품질 도구.                           │
│   테스트/디버깅/유지보수 향상을 위해 적용한다.                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Chat 파이프라인: LangGraph 도입 결정

### 2.1 Chat 요구사항 분석

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Chat Pipeline 요구사항                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   사용자 메시지 의도에 따른 분기 처리 필요:                                  │
│                                                                              │
│   "플라스틱 어떻게 버려?" ──────▶ 분리수거 Q&A (RAG)                        │
│   "환경 보호 팁 알려줘" ─────────▶ Eco Tips 생성                            │
│   "이코야 안녕!" ────────────────▶ 캐릭터 채팅 (페르소나)                   │
│   "오늘 날씨 어때?" ─────────────▶ 일반 대화                                │
│                                                                              │
│   ※ Scan과 달리 조건부 분기가 핵심 요구사항                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 LangGraph 도입 사유

| 평가 항목 | 순차 함수 호출 | LangGraph 도입 | 판정 |
|----------|---------------|----------------|------|
| **조건부 분기** | if-else 중첩 | 선언적 분기 | ✅ 유리 |
| **확장성** | 스파게티 위험 | 노드 추가만 | ✅ 유리 |
| **가시성** | 코드 읽어야 함 | 그래프 시각화 | ✅ 유리 |
| **테스트** | 분기별 테스트 어려움 | 노드 단위 테스트 | ✅ 유리 |
| **복잡도** | 단순 | 학습 필요 | ⚪ 동등 |

**결론**: Chat 파이프라인은 분기 로직이 핵심이므로 LangGraph 도입이 **적합**

### 2.3 Chat LangGraph 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Chat LangGraph StateGraph                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                         ┌─────────────────┐                                 │
│                         │  START          │                                 │
│                         └────────┬────────┘                                 │
│                                  │                                           │
│                                  ▼                                           │
│                         ┌─────────────────┐                                 │
│                         │ intent_classify │                                 │
│                         │ (의도 분류)      │                                 │
│                         └────────┬────────┘                                 │
│                                  │                                           │
│              ┌───────────────────┼───────────────────┐                      │
│              │                   │                   │                      │
│              ▼                   ▼                   ▼                      │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐              │
│   │ waste_qa_node   │ │ eco_tips_node   │ │ character_chat  │              │
│   │ (분리수거 Q&A)  │ │ (환경 팁)       │ │ (캐릭터 대화)   │              │
│   └────────┬────────┘ └────────┬────────┘ └────────┬────────┘              │
│            │                   │                   │                        │
│            └───────────────────┼───────────────────┘                        │
│                                │                                             │
│                                ▼                                             │
│                         ┌─────────────────┐                                 │
│                         │  response_node  │                                 │
│                         │ (응답 포맷팅)   │                                 │
│                         └────────┬────────┘                                 │
│                                  │                                           │
│                                  ▼                                           │
│                         ┌─────────────────┐                                 │
│                         │      END        │                                 │
│                         └─────────────────┘                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Chat 구현 예시

```python
# apps/chat_worker/application/pipeline/graph.py
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Literal

class ChatState(TypedDict):
    user_id: str
    message: str
    character_id: str | None
    intent: str | None
    context: list[str]
    response: str | None

def intent_classifier(state: ChatState) -> dict:
    """의도 분류 노드."""
    llm = get_llm_client("gpt-4o-mini")  # 빠른 모델
    
    prompt = f"""
    사용자 메시지: {state['message']}
    
    의도를 분류하세요:
    - waste_question: 분리수거/폐기물 질문
    - eco_tips: 환경 팁 요청
    - character_chat: 캐릭터와 대화
    - general: 기타
    """
    
    intent = llm.invoke(prompt)
    return {"intent": intent}

def route_by_intent(state: ChatState) -> Literal["waste_qa", "eco_tips", "character_chat", "general"]:
    """의도에 따른 라우팅."""
    return state["intent"]

# 그래프 구성
builder = StateGraph(ChatState)

builder.add_node("intent_classify", intent_classifier)
builder.add_node("waste_qa", waste_qa_node)
builder.add_node("eco_tips", eco_tips_node)
builder.add_node("character_chat", character_chat_node)
builder.add_node("general", general_node)
builder.add_node("response", response_node)

builder.add_edge(START, "intent_classify")
builder.add_conditional_edges("intent_classify", route_by_intent, {
    "waste_question": "waste_qa",
    "eco_tips": "eco_tips",
    "character_chat": "character_chat",
    "general": "general",
})
builder.add_edge(["waste_qa", "eco_tips", "character_chat", "general"], "response")
builder.add_edge("response", END)

chat_graph = builder.compile()
```

---

## 3. LangChain 기반 DI (Dependency Injection)

### 3.1 DI 아키텍처 (서비스 내부 구성)

> **원칙**: Port(ABC)와 Infrastructure 구현체 모두 **각 서비스 내부**에 위치.
> 코드 중복은 허용하되, Clean Architecture 경계를 유지.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  LangChain DI 아키텍처 (서비스별 구성)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   apps/scan_worker/                                                         │
│   ├── application/                                                          │
│   │   └── ports/                                                            │
│   │       └── llm_client.py        ← Port (ABC) 정의                       │
│   │                                                                          │
│   ├── infrastructure/                                                       │
│   │   └── llm/                                                              │
│   │       ├── langchain_openai.py  ← OpenAI 구현체                         │
│   │       ├── langchain_gemini.py  ← Gemini 구현체                         │
│   │       └── fallback_client.py   ← Fallback 래퍼                         │
│   │                                                                          │
│   └── setup/                                                                │
│       └── llm_factory.py           ← DI 팩토리                              │
│                                                                              │
│   apps/chat_worker/                                                         │
│   ├── application/                                                          │
│   │   └── ports/                                                            │
│   │       └── llm_client.py        ← Port (ABC) 정의 (중복 허용)           │
│   │                                                                          │
│   ├── infrastructure/                                                       │
│   │   └── llm/                                                              │
│   │       ├── langchain_openai.py  ← OpenAI 구현체 (중복 허용)             │
│   │       ├── langchain_gemini.py  ← Gemini 구현체 (중복 허용)             │
│   │       └── fallback_client.py   ← Fallback 래퍼 (중복 허용)             │
│   │                                                                          │
│   └── setup/                                                                │
│       └── llm_factory.py           ← DI 팩토리 (중복 허용)                  │
│                                                                              │
│   ※ 코드 중복 vs Clean Architecture: Clean 원칙 우선                        │
│   ※ 각 서비스가 독립적으로 LLM 구현체를 교체/수정 가능                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**왜 중복을 허용하는가?**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      중복 허용 vs Shared 통합                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ❌ Shared 통합 시 문제점:                                                  │
│   ─────────────────────────                                                  │
│   libs/shared/llm/langchain_openai.py                                       │
│        │                                                                     │
│        ├── scan_worker가 import                                             │
│        ├── chat_worker가 import                                             │
│        └── 변경 시 → 모든 서비스 영향 (강한 결합)                           │
│                                                                              │
│   ✅ 서비스별 구성 시 장점:                                                  │
│   ─────────────────────────                                                  │
│   apps/scan_worker/infrastructure/llm/langchain_openai.py                   │
│        └── scan_worker만 영향                                               │
│                                                                              │
│   apps/chat_worker/infrastructure/llm/langchain_openai.py                   │
│        └── chat_worker만 영향                                               │
│                                                                              │
│   - 독립 배포 가능                                                          │
│   - 서비스별 LLM 설정 커스터마이징 가능                                     │
│   - 테스트 격리                                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Port 정의 (Application Layer)

```python
# apps/scan_worker/application/ports/llm_client.py
# apps/chat_worker/application/ports/llm_client.py  ← 동일 코드, 각 서비스에 복사

from abc import ABC, abstractmethod
from typing import Any, TypeVar

T = TypeVar("T")

class LLMClient(ABC):
    """LLM 클라이언트 포트 (인터페이스).
    
    Clean Architecture의 DIP(Dependency Inversion Principle) 적용.
    Application Layer가 Infrastructure에 의존하지 않도록 추상화.
    
    ※ 각 서비스에서 동일한 Port를 정의 (중복 허용).
    ※ 서비스별로 메서드 추가/수정 가능 (독립성 유지).
    """
    
    @abstractmethod
    async def invoke(self, prompt: str) -> str:
        """텍스트 생성."""
        pass
    
    @abstractmethod
    async def invoke_with_image(self, prompt: str, image_url: str) -> str:
        """Vision: 이미지 + 텍스트 생성."""
        pass
    
    @abstractmethod
    async def invoke_structured(self, prompt: str, schema: type[T]) -> T:
        """구조화된 출력 (Pydantic 스키마)."""
        pass
    
    @abstractmethod
    async def stream(self, prompt: str):
        """스트리밍 출력 (SSE용)."""
        pass
```

### 3.3 Adapter 구현 (Infrastructure Layer)

```python
# apps/scan_worker/infrastructure/llm/langchain_openai.py
# apps/chat_worker/infrastructure/llm/langchain_openai.py  ← 동일 코드, 각 서비스에 복사

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from apps.scan_worker.application.ports.llm_client import LLMClient  # 서비스 내부 import


class LangChainOpenAIClient(LLMClient):
    """OpenAI LangChain 구현체.
    
    ※ 각 서비스에서 동일한 구현체를 정의 (중복 허용).
    ※ 서비스별로 설정/동작 커스터마이징 가능.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            request_timeout=timeout,
        )
        self.model = model
    
    async def invoke(self, prompt: str) -> str:
        response = await self.llm.ainvoke(prompt)
        return response.content
    
    async def invoke_with_image(self, prompt: str, image_url: str) -> str:
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
            ]
        )
        response = await self.llm.ainvoke([message])
        return response.content
    
    async def invoke_structured(self, prompt: str, schema: type) -> Any:
        structured_llm = self.llm.with_structured_output(schema)
        return await structured_llm.ainvoke(prompt)
    
    async def stream(self, prompt: str):
        async for chunk in self.llm.astream(prompt):
            yield chunk.content
```

```python
# apps/scan_worker/infrastructure/llm/langchain_gemini.py
# apps/chat_worker/infrastructure/llm/langchain_gemini.py  ← 동일 코드, 각 서비스에 복사

from langchain_google_genai import ChatGoogleGenerativeAI

from apps.scan_worker.application.ports.llm_client import LLMClient  # 서비스 내부 import


class LangChainGeminiClient(LLMClient):
    """Google Gemini LangChain 구현체."""
    
    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.0,
    ):
        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
        )
        self.model = model
    
    async def invoke(self, prompt: str) -> str:
        response = await self.llm.ainvoke(prompt)
        return response.content
    
    # ... (OpenAI와 동일한 인터페이스)
```

### 3.4 Fallback 구현

```python
# apps/scan_worker/infrastructure/llm/fallback_client.py
# apps/chat_worker/infrastructure/llm/fallback_client.py  ← 동일 코드, 각 서비스에 복사

import logging
from apps.scan_worker.application.ports.llm_client import LLMClient  # 서비스 내부 import

logger = logging.getLogger(__name__)


class FallbackLLMClient(LLMClient):
    """Fallback을 지원하는 LLM 클라이언트.
    
    Primary 실패 시 Fallback 모델로 자동 전환.
    
    ※ 각 서비스에서 동일한 Fallback 로직 정의 (중복 허용).
    ※ 서비스별로 Fallback 전략 커스터마이징 가능.
    """
    
    def __init__(self, primary: LLMClient, fallback: LLMClient):
        self.primary = primary
        self.fallback = fallback
    
    async def invoke(self, prompt: str) -> str:
        try:
            return await self.primary.invoke(prompt)
        except Exception as e:
            logger.warning(f"Primary LLM failed ({self.primary.model}): {e}")
            logger.info(f"Falling back to {self.fallback.model}")
            return await self.fallback.invoke(prompt)
    
    async def invoke_with_image(self, prompt: str, image_url: str) -> str:
        try:
            return await self.primary.invoke_with_image(prompt, image_url)
        except Exception as e:
            logger.warning(f"Primary Vision failed: {e}")
            return await self.fallback.invoke_with_image(prompt, image_url)
    
    # ... (다른 메서드도 동일 패턴)
```

### 3.5 DI 팩토리 (Composition Root)

```python
# apps/scan_worker/setup/llm_factory.py
# apps/chat_worker/setup/llm_factory.py  ← 동일 코드, 각 서비스에 복사

from functools import lru_cache
from typing import Literal

# 서비스 내부 import (각 서비스별 경로)
from apps.scan_worker.application.ports.llm_client import LLMClient
from apps.scan_worker.infrastructure.llm.langchain_openai import LangChainOpenAIClient
from apps.scan_worker.infrastructure.llm.langchain_gemini import LangChainGeminiClient
from apps.scan_worker.infrastructure.llm.fallback_client import FallbackLLMClient


ModelType = Literal["gpt-4o", "gpt-4o-mini", "gemini-2.0-flash", "gemini-2.0-pro"]


@lru_cache(maxsize=10)
def get_llm_client(
    model: ModelType = "gpt-4o",
    with_fallback: bool = True,
) -> LLMClient:
    """LLM 클라이언트 팩토리 (서비스 내부).
    
    ※ 각 서비스에서 동일한 팩토리 정의 (중복 허용).
    ※ 서비스별로 기본 모델, Fallback 전략 커스터마이징 가능.
    
    Args:
        model: 사용할 모델명
        with_fallback: Fallback 활성화 여부
    
    Returns:
        LLMClient 구현체
    
    Usage:
        llm = get_llm_client("gpt-4o")
        result = await llm.invoke("Hello")
    """
    if model.startswith("gpt"):
        primary = LangChainOpenAIClient(model=model)
        if with_fallback:
            fallback = LangChainGeminiClient(model="gemini-2.0-flash")
            return FallbackLLMClient(primary, fallback)
        return primary
    
    elif model.startswith("gemini"):
        primary = LangChainGeminiClient(model=model)
        if with_fallback:
            fallback = LangChainOpenAIClient(model="gpt-4o-mini")
            return FallbackLLMClient(primary, fallback)
        return primary
    
    else:
        raise ValueError(f"Unknown model: {model}")


# 테스트용 Mock (각 서비스 tests/ 디렉토리에 위치)
class MockLLMClient(LLMClient):
    """테스트용 Mock 클라이언트.
    
    ※ tests/conftest.py 또는 tests/fixtures/ 에 위치 권장.
    """
    
    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_history: list[str] = []
    
    async def invoke(self, prompt: str) -> str:
        self.call_history.append(prompt)
        return self.responses.get("default", "Mock response")
    
    async def invoke_with_image(self, prompt: str, image_url: str) -> str:
        self.call_history.append(f"{prompt}|{image_url}")
        return self.responses.get("vision", '{"category": "recyclable"}')
    
    async def invoke_structured(self, prompt: str, schema: type):
        self.call_history.append(prompt)
        return schema.model_validate_json(self.responses.get("structured", "{}"))
    
    async def stream(self, prompt: str):
        self.call_history.append(prompt)
        for word in self.responses.get("stream", "Mock stream").split():
            yield word + " "
```

### 3.6 DI 사용 예시

```python
# apps/scan_worker/application/pipeline/nodes/vision_node.py

# 서비스 내부 import (경계 유지)
from apps.scan_worker.application.ports.llm_client import LLMClient
from apps.scan_worker.domain.models.classification import ClassificationResult


def create_vision_node(llm_client: LLMClient):
    """Vision 노드 팩토리 (DI로 LLM 클라이언트 주입).
    
    ※ Application Layer는 Port(ABC)에만 의존.
    ※ 구체적인 LangChain 구현체는 알지 못함 (DIP).
    """
    
    async def vision_node(state: dict) -> dict:
        prompt = load_prompt("vision_classification_prompt.txt")
        
        # DI로 주입받은 LLM 클라이언트 사용
        result = await llm_client.invoke_structured(
            prompt=prompt,
            schema=ClassificationResult,
        )
        
        return {"classification_result": result.model_dump(), "progress": 25}
    
    return vision_node


# 조립 (Composition Root)
# apps/scan_worker/presentation/tasks/scan_job.py

# 서비스 내부 import (경계 유지)
from apps.scan_worker.setup.llm_factory import get_llm_client

@celery_app.task(name="scan.job")
def scan_job(task_id: str, image_url: str, model: str = "gpt-4o"):
    # DI: 모델명에 따라 적절한 클라이언트 주입
    # ※ Composition Root(setup/)에서만 구체적 구현체 결정
    llm_client = get_llm_client(model)
    
    # 노드 생성 (의존성 주입)
    vision_node = create_vision_node(llm_client)
    answer_node = create_answer_node(llm_client)
    
    # 파이프라인 실행
    # ...
```

---

## 4. LangChain DI 도입 이점

### 4.1 기능별 이점

| 기능 | 직접 구현 | LangChain DI | 이점 |
|------|----------|--------------|------|
| **재시도** | try-except + backoff | 내장 (max_retries) | 보일러플레이트 제거 |
| **캐싱** | Redis 로직 직접 구현 | RedisCache 한 줄 설정 | 동일 요청 비용 0원 |
| **비용 추적** | 토큰 계산 로직 | get_openai_callback() | 실시간 비용 모니터링 |
| **스트리밍** | SSE 통합 직접 구현 | astream() async generator | Chat 실시간 타이핑 |
| **배치 처리** | asyncio.gather | abatch(max_concurrency) | 다중 요청 병렬화 |
| **구조화 출력** | JSON 파싱 + 검증 | with_structured_output() | 타입 안전성 |
| **Rate Limiting** | 토큰 버킷 직접 구현 | InMemoryRateLimiter | API 제한 자동 준수 |
| **Fallback** | try-except 중첩 | with_fallbacks() | 고가용성 |

### 4.2 테스트 용이성

```python
# apps/scan_worker/tests/unit/test_vision_node.py

import pytest

# 테스트용 Mock은 tests/conftest.py 또는 tests/fixtures/에 위치
from apps.scan_worker.tests.fixtures.mock_llm import MockLLMClient
from apps.scan_worker.application.pipeline.nodes.vision_node import create_vision_node


@pytest.mark.asyncio
async def test_vision_node_classifies_plastic():
    """Vision 노드가 플라스틱을 올바르게 분류하는지 테스트.
    
    ※ Mock LLM 클라이언트로 API 호출 없이 테스트.
    ※ 서비스 내부에서 독립적으로 테스트 가능.
    """
    
    # Mock LLM 클라이언트 (DI)
    mock_llm = MockLLMClient(responses={
        "structured": '{"major_category": "재활용폐기물", "middle_category": "플라스틱류"}'
    })
    
    # 노드 생성 (의존성 주입)
    vision_node = create_vision_node(mock_llm)
    
    # 실행
    state = {"image_url": "https://example.com/plastic.jpg", "user_input": "이거 뭐야?"}
    result = await vision_node(state)
    
    # 검증
    assert result["classification_result"]["major_category"] == "재활용폐기물"
    assert result["classification_result"]["middle_category"] == "플라스틱류"
    assert len(mock_llm.call_history) == 1  # LLM 호출 확인
```

### 4.3 환경별 모델 설정

```python
# apps/scan_worker/setup/config.py
# apps/chat_worker/setup/config.py  ← 서비스별 다른 기본 설정 가능

import os

def get_default_model() -> str:
    """환경별 기본 모델 설정.
    
    ※ 각 서비스에서 독립적으로 기본 모델 설정 가능.
    ※ Scan: Vision 품질 중요 → gpt-4o 우선
    ※ Chat: 빠른 응답 중요 → gpt-4o-mini 우선 가능
    """
    env = os.getenv("ENVIRONMENT", "dev")
    
    if env == "prod":
        return "gpt-4o"  # 프로덕션: 최고 품질
    elif env == "staging":
        return "gpt-4o-mini"  # 스테이징: 비용 절감
    else:
        return "gpt-4o-mini"  # 개발: 비용 절감

# 사용
from apps.scan_worker.setup.llm_factory import get_llm_client

llm = get_llm_client(get_default_model())
```

---

## 5. 최종 아키텍처 요약

### 5.1 Shared Kernel 원칙

> **Clean Architecture에서 shared는 "순수하고 안정적인 공용 개념"만 담아야 한다.**

| ✅ Shared에 허용 | ❌ Shared에 금지 |
|-----------------|-----------------|
| Result, Error 타입 | HTTP DTO |
| Clock, IdGenerator 인터페이스 | SQLAlchemy 모델 |
| Pagination, OutboxEvent 스키마 | Redis/Kafka 클라이언트 |
| 순수 Python + 도메인 개념 | **LangChain 구현체 (Infrastructure)** |

### 5.2 수정된 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         최종 아키텍처 요약                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                  Shared Kernel (libs/shared)                         │   │
│   │                                                                      │   │
│   │   ✅ result.py        (Result[T, E] 타입)                           │   │
│   │   ✅ errors.py        (AppError 베이스)                             │   │
│   │   ✅ pagination.py    (PageRequest, PageResponse)                   │   │
│   │   ✅ clock.py         (Clock ABC - 테스트용 시간 추상화)            │   │
│   │   ✅ id_generator.py  (IdGenerator ABC)                             │   │
│   │                                                                      │   │
│   │   ❌ LangChain 구현체 (Infrastructure 의존)                         │   │
│   │   ❌ Redis/Kafka 클라이언트                                         │   │
│   │   ❌ 특정 도메인 DTO                                                │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       Scan Worker                                    │   │
│   │                                                                      │   │
│   │   application/                                                       │   │
│   │   ├── ports/llm_client.py      ← Port (ABC) - 각 서비스 내부 정의   │   │
│   │   └── pipeline/                ← 순차 파이프라인 로직               │   │
│   │                                                                      │   │
│   │   infrastructure/                                                    │   │
│   │   └── llm/                     ← LangChain 구현체 (서비스 내부)     │   │
│   │       ├── langchain_openai.py                                       │   │
│   │       ├── langchain_gemini.py                                       │   │
│   │       └── fallback_client.py                                        │   │
│   │                                                                      │   │
│   │   setup/                                                             │   │
│   │   └── llm_factory.py           ← DI 팩토리 (서비스 내부)            │   │
│   │                                                                      │   │
│   │   - LangGraph: ❌ (순차 의존성)                                      │   │
│   │   - LangChain DI: ✅ (서비스 내부)                                   │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       Chat Worker                                    │   │
│   │                                                                      │   │
│   │   application/                                                       │   │
│   │   ├── ports/llm_client.py      ← Port (ABC) - 각 서비스 내부 정의   │   │
│   │   └── pipeline/                ← LangGraph StateGraph               │   │
│   │       └── graph.py                                                  │   │
│   │                                                                      │   │
│   │   infrastructure/                                                    │   │
│   │   └── llm/                     ← LangChain 구현체 (서비스 내부)     │   │
│   │       ├── langchain_openai.py  (Scan과 코드 중복 허용)              │   │
│   │       ├── langchain_gemini.py                                       │   │
│   │       └── fallback_client.py                                        │   │
│   │                                                                      │   │
│   │   setup/                                                             │   │
│   │   └── llm_factory.py           ← DI 팩토리 (서비스 내부)            │   │
│   │                                                                      │   │
│   │   - LangGraph: ✅ (의도 분기)                                        │   │
│   │   - LangChain DI: ✅ (서비스 내부)                                   │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   공통 인프라 (K8s):                                                         │
│   - Celery + RabbitMQ (Job 큐잉)                                            │
│   - Redis Streams + Pub/Sub (SSE 이벤트)                                    │
│   - Redis State KV (복구용)                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 코드 중복 vs Clean Architecture

| 관점 | 코드 중복 허용 | Shared로 통합 |
|------|---------------|---------------|
| **Clean Architecture** | ✅ 경계 명확 | ❌ 인프라 결합 |
| **변경 이유** | 서비스별 독립 | 전체 영향 |
| **테스트** | 서비스별 독립 | 공유 모의 필요 |
| **배포** | 서비스별 독립 | 전체 재배포 위험 |

**결론**: LangChain 구현체 코드 중복은 허용. Clean Architecture 원칙이 DRY보다 우선.

---

## 6. References

- [LangChain Documentation](https://python.langchain.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Eco² Clean Architecture 시리즈](https://rooftopsnow.tistory.com/)|

