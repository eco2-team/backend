# Scan Worker Clean Architecture 마이그레이션

> **작성일**: 2026-01-05  
> **최종 수정**: 2026-01-06  
> **상태**: Implemented  
> **관련 문서**: [Stateless Reducer + 체크포인팅 상세](./scan-worker-stateless-reducer.md)

---

## 1. 마이그레이션 배경

### 1.1 기존 구조의 한계

`domains/scan`과 `domains/_shared/waste_pipeline`은 빠른 프로토타이핑에 적합했으나, 서비스가 성장하면서 다음과 같은 문제가 드러났다.

**첫째, 레이어 경계가 모호했다.** Vision API 호출, 프롬프트 로딩, 파이프라인 조합이 모두 한 디렉토리에 뒤섞여 있었다. 새로운 팀원이 "Scan이 무슨 일을 하는지" 파악하려면 infrastructure 깊숙이 들어가야 했고, 이는 온보딩 비용을 높였다.

**둘째, 모델 확장이 어려웠다.** OpenAI만 사용하던 초기와 달리, Gemini 등 멀티벤더 지원이 필요해졌다. 기존 구조에서는 새 모델을 추가할 때마다 파이프라인 코드 전체를 수정해야 했다.

**셋째, 테스트가 무거웠다.** 순수 로직을 테스트하려 해도 Redis, 파일 시스템, API 키가 모두 필요했다. Mock 설정만으로도 수십 줄이 소요되었다.

### 1.2 마이그레이션 목표

| 목표 | 설명 |
|------|------|
| Clean Architecture 적용 | Application/Infrastructure 레이어 분리 |
| LLM DI | 모델명 기반 런타임 어댑터 선택 |
| Stateless Reducer | Step을 순수 함수로 설계 |
| 체크포인팅 | 실패 시 마지막 성공 지점부터 재시작 |
| SSE 동등성 | 기존 Redis Streams + SSE Gateway 연동 유지 |

---

## 2. 핵심 의사결정

### 2.1 Pipeline은 Application Layer

마이그레이션 초기, `waste_pipeline`을 어느 레이어에 배치할지 논의가 있었다. 

Domain Layer 지지측은 "분리배출 규칙은 비즈니스 핵심"이라고 주장했다. 그러나 실제 코드를 분석해보니, `pipeline.py`의 대부분은 **순서 조합, fallback, retry 정책**이었다. "플라스틱은 재활용"이라는 도메인 규칙이 아니라, "Vision 실패 시 2초 후 재시도"라는 운영 정책이 주를 이뤘다.

**결론**: `waste_pipeline`은 유스케이스 오케스트레이션이므로 **Application Layer**에 배치한다.

```
Domain Layer: "플라스틱 → 재활용" (불변식, 거의 변경 없음)
Application Layer: "Vision → Rule → Answer 순서, retry 3회" (자주 변경)
```

### 2.2 Port/Adapter로 LLM 추상화

OpenAI SDK를 직접 호출하던 코드를 `VisionModelPort`, `LLMPort` 인터페이스로 추상화했다. 이제 Gemini든 Claude든, 새 어댑터만 구현하면 파이프라인 코드 수정 없이 모델을 교체할 수 있다.

```python
# 클라이언트 요청
POST /scan { "model": "gemini-2.5-flash" }

# DI Factory에서 자동 선택
provider = MODEL_PROVIDER_MAP["gemini-2.5-flash"]  # → "gemini"
adapter = GeminiVisionAdapter(model="gemini-2.5-flash")
```

**명시적 매핑 정책**을 채택했다. prefix 기반 추론(`gemini-*` → `gemini`)은 오분류 위험이 있어, 지원 모델을 딕셔너리로 명시했다.

| 모델 | Provider |
|------|----------|
| `gpt-5.2`, `gpt-5.1`, `gpt-5-mini` 등 | `gpt` |
| `gemini-2.5-pro`, `gemini-2.0-flash` 등 | `gemini` |

### 2.3 디렉토리 네이밍

| 변경 전 | 변경 후 | 이유 |
|---------|---------|------|
| `resources/` | `assets/` | "정적 에셋"이 목적을 명확히 전달 |
| `llm/openai/` | `llm/gpt/` | Provider가 아닌 모델 패밀리 기준 (확장성) |

---

## 3. 최종 디렉토리 구조

```
apps/scan_worker/
├── domain/enums/                    # 불변 열거형 (WasteCategory, PipelineStage)
│
├── application/
│   ├── classify/
│   │   ├── commands/                # 오케스트레이션
│   │   │   └── execute_pipeline.py  # ClassifyPipeline, CheckpointingStepRunner
│   │   ├── steps/                   # 순수 Step (Port만 의존)
│   │   │   ├── vision_step.py
│   │   │   ├── rule_step.py
│   │   │   ├── answer_step.py
│   │   │   └── reward_step.py
│   │   ├── ports/                   # ABC 인터페이스
│   │   └── dto/                     # ClassifyContext
│   └── common/
│       └── step_interface.py        # Step ABC
│
├── infrastructure/
│   ├── llm/                         # LLM Adapter (모델 패밀리별)
│   │   ├── gpt/
│   │   │   ├── vision.py            # GPTVisionAdapter
│   │   │   └── llm.py               # GPTLLMAdapter
│   │   └── gemini/
│   │       ├── vision.py            # GeminiVisionAdapter
│   │       └── llm.py               # GeminiLLMAdapter
│   ├── assets/                      # 정적 에셋
│   │   ├── prompts/                 # 프롬프트 템플릿 (.txt)
│   │   └── data/                    # 분류체계, 규정 JSON
│   ├── asset_loader/                # 에셋 로딩 캡슐화
│   ├── retrievers/                  # RAG (JsonRegulationRetriever)
│   └── persistence_redis/           # Redis (Event, Cache, Checkpoint)
│
├── presentation/tasks/              # Celery Task 진입점
└── setup/                           # DI Factory, Config
```

---

## 4. Port/Adapter 설계

### 4.1 Port 목록

인프라 의존성을 추상화한 7개 Port를 정의했다.

| Port | 역할 | 구현체 |
|------|------|--------|
| `VisionModelPort` | 이미지 분석 | GPTVisionAdapter, GeminiVisionAdapter |
| `LLMPort` | 텍스트 생성 | GPTLLMAdapter, GeminiLLMAdapter |
| `RetrieverPort` | 규정 검색 (RAG) | JsonRegulationRetriever |
| `PromptRepositoryPort` | 프롬프트/스키마 로딩 | FilePromptRepository |
| `EventPublisherPort` | Redis Streams 발행 | RedisEventPublisher |
| `ResultCachePort` | 결과 캐시 | RedisResultCache |
| `ContextStorePort` | 체크포인팅 | RedisContextStore |

### 4.2 DI Factory

`setup/dependencies.py`가 Composition Root 역할을 한다. Celery Task에서는 Factory 함수만 호출하면 된다.

```python
# presentation/tasks/vision_task.py
step = get_vision_step(model)           # DI Factory가 적절한 어댑터 주입
runner = get_checkpointing_step_runner()
ctx = runner.run_step(step, "vision", ctx)
```

싱글톤 인스턴스(`@lru_cache`)와 요청별 인스턴스를 구분했다.

- **싱글톤**: `PromptRepository`, `Retriever`, `EventPublisher` (상태 없음)
- **요청별**: `VisionModel`, `LLM` (모델명에 따라 다른 인스턴스)

---

## 5. Stateless Reducer + 체크포인팅

> 📖 상세 내용은 [별도 문서](./scan-worker-stateless-reducer.md) 참조

### 요약

**Stateless Reducer**는 각 Step을 순수 함수로 설계하는 패턴이다. Side effect(이벤트 발행, 체크포인트 저장)는 Runner가 외부에서 처리한다.

**체크포인팅**은 Step 완료 시 Context를 Redis에 저장하여, 실패 시 마지막 성공 지점부터 재시작할 수 있게 한다. LLM 재호출 비용을 절감한다.

```
vision ──✅──▶ rule ──✅──▶ answer ──❌(실패)
                              ↓
              resume_from_checkpoint("task-123")
                              ↓
              rule 체크포인트에서 ctx 복원
                              ↓
              answer부터 재시작 (vision, rule 스킵)
```

---

## 6. 큐 라우팅

태스크명과 큐명을 1:1로 통일했다. 기존 `my.save_character`는 제거하고 `users.save_character`로 대체했다.

| 태스크 | 큐 | 비고 |
|--------|-----|------|
| `scan.vision` | `scan.vision` | Vision 분석 |
| `scan.rule` | `scan.rule` | 규정 검색 |
| `scan.answer` | `scan.answer` | 답변 생성 |
| `scan.reward` | `scan.reward` | 보상 처리 |
| `character.match` | `character.match` | 캐릭터 매칭 (동기 대기) |
| `character.save_ownership` | `character.save_ownership` | 소유권 저장 |
| `users.save_character` | `users.save_character` | 사용자 캐릭터 저장 |
| ~~`my.save_character`~~ | - | **제거됨** |

---

## 7. SSE + Event Relay 동등성

기존 SSE 연동을 그대로 유지했다. Step 시작/완료 시 Redis Streams에 이벤트를 발행하고, Event Router가 이를 Pub/Sub으로 브로드캐스트한다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             이벤트 흐름                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   CheckpointingStepRunner                                                   │
│        │                                                                     │
│        ├── publish_stage_event("vision", "started")                         │
│        │        ↓                                                            │
│        │   Redis Streams: scan:events:{shard}                               │
│        │        ↓                                                            │
│        │   Event Router (consumer)                                          │
│        │        ↓                                                            │
│        │   Redis Pub/Sub: scan:events:{job_id}                              │
│        │        ↓                                                            │
│        │   SSE Gateway → Client                                             │
│        │                                                                     │
│        ├── step.run(ctx)                                                    │
│        │                                                                     │
│        ├── save_checkpoint("vision", ctx)                                   │
│        │                                                                     │
│        └── publish_stage_event("vision", "completed")                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 최종 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Scan Worker 아키텍처                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [Presentation]  Celery Task                                               │
│        │                                                                     │
│        │  model: "gpt-5.2"                                                  │
│        ▼                                                                     │
│   [Application]  CheckpointingStepRunner                                    │
│        │                                                                     │
│        ├── VisionStep ──▶ VisionModelPort ──▶ GPT/Gemini Vision            │
│        │                        ↓                                            │
│        │              ✅ checkpoint:vision                                   │
│        │                                                                     │
│        ├── RuleStep ────▶ RetrieverPort ────▶ JsonRegulationRetriever      │
│        │                        ↓                                            │
│        │              ✅ checkpoint:rule                                     │
│        │                                                                     │
│        ├── AnswerStep ──▶ LLMPort ──────────▶ GPT/Gemini LLM               │
│        │                        ↓                                            │
│        │              ✅ checkpoint:answer                                   │
│        │                                                                     │
│        └── RewardStep ──▶ Celery Tasks                                      │
│                              ├── character.save_ownership                   │
│                              └── users.save_character                       │
│                                                                              │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│   EventPublisherPort → Redis Streams → Event Router → SSE Gateway          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. 설정 외부화

하드코딩을 지양하고, 환경별로 다를 수 있는 값은 외부에서 주입한다.

| 항목 | 권장 방식 | 예시 |
|------|----------|------|
| 지원 모델 목록 | `MODEL_PROVIDER_MAP` 코드 상수 | 모델 추가 시 코드 수정 필요 |
| 내부 서비스 주소 | env/ConfigMap | dev: `localhost`, prod: `k8s-service.namespace` |
| CORS, allowed hosts | env/ConfigMap | 운영 정책 변경 시 재배포 없이 반영 |
| API Key | `SecretStr` + K8s Secret | 로깅에서 마스킹 |

---

## References

- [LLM 파이프라인 의사결정 리포트](https://rooftopsnow.tistory.com/142)
- [Stateless Reducer Pattern](https://rooftopsnow.tistory.com/141)
- [Redis Streams SSE 마이그레이션](https://rooftopsnow.tistory.com/69)
