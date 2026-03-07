# Chat Worker 코드 정제 리포트

> **작성일**: 2026-01-15  
> **대상**: `apps/chat_worker/`  
> **목표**: Clean Architecture + LangGraph 결합을 위한 코드 구조 개선

---

## 1. Layer-First 아키텍처 선택 배경

### 1.1 기존 구조의 문제점 (Feature-First)

기존 `application/` 계층은 기능별(feature-first) 폴더 구조를 사용했습니다:

```
application/
├── intent/
│   ├── services/intent_classifier.py
│   └── dto/...
├── answer/
│   ├── services/answer_generator.py
│   └── dto/answer_result.py
├── feedback/
│   ├── services/feedback_evaluator.py
│   └── dto/feedback_result.py
├── integrations/
│   ├── character/services/...
│   └── location/services/...
└── ports/
```

**문제점**:
1. **폴더 증식**: 새 기능 추가 시 `feature/services/`, `feature/dto/`, `feature/ports/` 반복 생성
2. **경로 복잡도**: `application.integrations.character.services.CharacterService` 같은 긴 경로
3. **중복 구조**: 각 feature 폴더가 동일한 하위 구조(`services/`, `dto/`) 반복
4. **일관성 부족**: 일부는 `usecases/`, 일부는 `services/` 사용

### 1.2 Layer-First 선택 이유

| 기준 | Feature-First | Layer-First |
|------|---------------|-------------|
| 폴더 수 | O(features × layers) | O(layers) |
| import 경로 | 길고 복잡 | 짧고 일관적 |
| 파일 위치 | feature 내에서 산발적 | layer 내에서 집중 |
| 신규 추가 | feature 폴더 전체 생성 | 해당 layer에 파일 추가 |
| Clean Architecture | 경계가 불명확 | 계층 경계 명확 |

**결정**: Chat Worker는 LangGraph 오케스트레이션이 핵심이고, 개별 feature보다 **계층 간 의존성 관리**가 중요하므로 Layer-First 선택.

### 1.3 최종 Application 구조

```
application/
├── commands/           # UseCase (정책/흐름)
│   ├── classify_intent_command.py
│   ├── generate_answer_command.py
│   ├── evaluate_feedback_command.py
│   ├── get_character_command.py
│   └── process_chat.py
├── services/           # 순수 비즈니스 로직
│   ├── intent_classifier.py
│   ├── answer_generator.py
│   ├── feedback_evaluator.py
│   ├── fallback_orchestrator.py
│   ├── character_service.py
│   ├── location_service.py
│   └── category_extractor.py
├── ports/              # 추상화 인터페이스
│   ├── llm.py
│   ├── cache.py
│   ├── events.py
│   ├── prompt_builder.py  # 신규
│   └── ...
└── dto/                # Data Transfer Objects
    ├── answer_context.py
    ├── answer_result.py
    ├── feedback_result.py
    └── ...
```

---

## 2. Infrastructure 계층 정제

### 2.1 삭제된 폴더

| 폴더 | 삭제 이유 |
|------|----------|
| `fallback/` | 빈 폴더 - Application의 FallbackOrchestrator가 코어 |
| `feedback/` | 단일 파일 → `llm/evaluators/`로 통합 |
| `orchestration/prompts/` | `assets/`로 이동 (리소스 접근 어댑터 성격) |

### 2.2 파일 이동

| 원본 | 이동 | 이유 |
|------|------|------|
| `feedback/llm_feedback_evaluator.py` | `llm/evaluators/feedback_evaluator.py` | LLM 관련 구현체 통합 |
| `orchestration/prompts/loader.py` | `assets/prompt_loader.py` | 리소스 로딩은 assets에서 |

### 2.3 최종 Infrastructure 구조

```
infrastructure/
├── assets/
│   ├── data/...
│   ├── prompts/
│   │   ├── classification/
│   │   ├── evaluation/      # 신규
│   │   ├── extraction/      # 신규
│   │   ├── global/
│   │   ├── local/
│   │   └── subagent/
│   └── prompt_loader.py     # 이동됨
├── llm/
│   ├── clients/
│   ├── evaluators/          # 신규
│   │   └── feedback_evaluator.py
│   ├── policies/
│   └── vision/
├── orchestration/
│   └── langgraph/
│       ├── nodes/
│       ├── factory.py
│       └── checkpointer.py
└── ...
```

### 2.4 Port 그룹 대응 원칙

Infrastructure 폴더는 Application의 Port 그룹과 1:1 대응:

| Application Port | Infrastructure Adapter |
|------------------|------------------------|
| `ports/llm.py` | `llm/clients/` |
| `ports/cache.py` | `cache/` |
| `ports/events.py` | `events/` |
| `ports/prompt_builder.py` | `assets/prompt_loader.py` |
| `ports/llm_evaluator.py` | `llm/evaluators/` |
| `ports/character_client.py` | `integrations/character/` |
| `ports/location_client.py` | `integrations/location/` |

---

## 3. Clean Architecture 위반 수정

### 3.1 발견된 위반

**문제**: `GenerateAnswerCommand`가 Infrastructure 구체 타입에 의존

```python
# Before (위반)
if TYPE_CHECKING:
    from chat_worker.infrastructure.assets.prompt_loader import PromptBuilder
```

**원칙 위반**: Application → Infrastructure 방향의 의존성

### 3.2 해결: Port 추상화

**새 파일**: `application/ports/prompt_builder.py`

```python
class PromptBuilderPort(ABC):
    @abstractmethod
    def build(self, intent: str) -> str: ...
    
    @abstractmethod
    def build_multi(self, intents: list[str]) -> str: ...
```

**수정 후**:

```python
# After (DIP 준수)
if TYPE_CHECKING:
    from chat_worker.application.ports.prompt_builder import PromptBuilderPort
```

**의존성 방향**:
```
Before: Application ─────────────> Infrastructure (위반)
After:  Application ──> Port <── Infrastructure   (DIP 준수)
```

---

## 4. 프롬프트 분리

### 4.1 하드코딩 프롬프트 식별

| 파일 | 상수명 | 문제 |
|------|--------|------|
| `feedback_evaluator.py` | `EVALUATION_PROMPT` | 185라인 파일 내 26라인 프롬프트 |
| `category_extractor.py` | `EXTRACT_CATEGORY_PROMPT` | 비즈니스 로직과 프롬프트 혼재 |
| `category_extractor.py` | `EXTRACT_CATEGORY_SYSTEM_PROMPT` | 동일 |

### 4.2 분리 결과

```
assets/prompts/
├── classification/      # 기존
│   ├── intent.txt
│   ├── text.txt
│   ├── vision.txt
│   ├── decompose.txt
│   └── multi_intent_detect.txt
├── evaluation/          # 신규
│   ├── feedback_evaluation.txt
│   └── answer_relevance.txt
├── extraction/          # 신규
│   ├── category.txt
│   └── category_system.txt
├── global/
│   └── eco_character.txt
├── local/
│   ├── waste_instruction.txt
│   ├── character_instruction.txt
│   ├── location_instruction.txt
│   ├── web_instruction.txt
│   └── general_instruction.txt
└── subagent/
    ├── character.txt
    └── location.txt
```

### 4.3 로딩 패턴

**LRU 캐싱 + 파일 기반 로드**:

```python
@lru_cache(maxsize=2)
def _load_prompt(name: str) -> str:
    """프롬프트 파일 로드 (LRU 캐싱)."""
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")
```

---

## 5. Domain/Presentation 검증

### 5.1 Domain 계층

**검증 결과**: ✅ Clean Architecture 준수

```
domain/
├── enums/
│   ├── fallback_reason.py
│   ├── feedback_quality.py
│   ├── input_type.py
│   ├── intent.py
│   └── query_complexity.py
└── value_objects/
    ├── chat_intent.py
    └── human_input.py
```

- 다른 계층에 의존하지 않음
- 순수 도메인 로직만 포함

### 5.2 Presentation 계층

**검증 결과**: ✅ Clean Architecture 준수

```
presentation/
└── amqp/
    └── process_task.py
```

- `application.commands`만 import
- Infrastructure 직접 의존 없음

---

## 6. 변경 파일 요약

### 6.1 신규 생성

| 파일 | 역할 |
|------|------|
| `application/ports/prompt_builder.py` | PromptBuilderPort 정의 |
| `infrastructure/llm/evaluators/__init__.py` | evaluators 패키지 |
| `infrastructure/llm/evaluators/feedback_evaluator.py` | LLMFeedbackEvaluator |
| `prompts/evaluation/feedback_evaluation.txt` | RAG 품질 평가 프롬프트 |
| `prompts/evaluation/answer_relevance.txt` | 답변 관련성 평가 프롬프트 |
| `prompts/extraction/category.txt` | 카테고리 추출 프롬프트 |
| `prompts/extraction/category_system.txt` | 카테고리 시스템 프롬프트 |
| `tests/unit/infrastructure/assets/test_prompt_loader.py` | 프롬프트 로더 테스트 |

### 6.2 수정

| 파일 | 변경 내용 |
|------|----------|
| `application/ports/__init__.py` | PromptBuilderPort 추가 |
| `application/commands/generate_answer_command.py` | Port 타입 사용 |
| `infrastructure/assets/prompt_loader.py` | PromptBuilderPort 구현 |
| `infrastructure/llm/__init__.py` | evaluators 추가 |
| `infrastructure/orchestration/langgraph/nodes/answer_node.py` | import 경로 변경 |
| `application/services/category_extractor.py` | 파일 기반 프롬프트 로드 |

### 6.3 삭제

| 파일/폴더 | 이유 |
|-----------|------|
| `infrastructure/fallback/` | 빈 폴더 |
| `infrastructure/feedback/` | llm/evaluators/로 이동 |
| `infrastructure/orchestration/prompts/` | assets/로 이동 |

---

## 7. 아키텍처 최종 검증

### 7.1 의존성 방향

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation                         │
│                  (amqp/process_task.py)                │
└─────────────────────────┬───────────────────────────────┘
                          │ depends on
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     Application                         │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│   │ commands │  │ services │  │   dto    │            │
│   └────┬─────┘  └────┬─────┘  └──────────┘            │
│        │             │                                 │
│        ▼             ▼                                 │
│   ┌────────────────────────────────────────┐          │
│   │               ports                     │          │
│   │ (LLMClientPort, PromptBuilderPort, ...) │          │
│   └────────────────────────────────────────┘          │
└─────────────────────────┬───────────────────────────────┘
                          │ implements
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Infrastructure                       │
│   ┌─────────┐  ┌──────────────┐  ┌─────────────┐      │
│   │   llm   │  │ orchestration │  │   assets    │      │
│   └─────────┘  └──────────────┘  └─────────────┘      │
└─────────────────────────────────────────────────────────┘
                          │ uses
                          ▼
┌─────────────────────────────────────────────────────────┐
│                      Domain                             │
│            (enums, value_objects)                       │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Clean Architecture 체크리스트

| 규칙 | 상태 |
|------|------|
| Domain은 다른 계층에 의존하지 않음 | ✅ |
| Application은 Infrastructure에 직접 의존하지 않음 | ✅ |
| Application → Port ← Infrastructure (DIP) | ✅ |
| Presentation은 Application만 알고 있음 | ✅ |
| Infrastructure는 Port를 구현함 | ✅ |

---

## 8. 참고 문서

- [LangGraph Best Practices](https://langchain.com/docs/langgraph)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [arxiv:2504.20355 - Local Prompt Optimization](https://arxiv.org/abs/2504.20355)
- [arxiv:2411.14252 - Chain-of-Intent](https://arxiv.org/abs/2411.14252)
