# Scan Worker Clean Architecture 마이그레이션 계획서

## 1. 목표

- **Clean Architecture 구조로 마이그레이션**
- **domains와 100% 동일한 동작 보장**
- **domains 삭제 후에도 독립적으로 동작**

---

## 2. 현재 구조 분석

### 2.1 domains 구조

```
domains/
├── _shared/
│   ├── waste_pipeline/              # scan 파이프라인 핵심 로직
│   │   ├── vision.py                # Vision LLM 분석
│   │   ├── answer.py                # Answer LLM 생성
│   │   ├── rag.py                   # 규정 검색 (RAG)
│   │   ├── text.py                  # 텍스트 분류
│   │   ├── pipeline.py              # 파이프라인 조합
│   │   ├── utils.py                 # 유틸리티
│   │   └── data/
│   │       ├── prompts/             # LLM 프롬프트
│   │       ├── item_class_list.yaml # 분류체계
│   │       ├── situation_tags.yaml  # 상황 태그
│   │       └── source/*.json        # 규정 데이터 (18개)
│   │
│   ├── events/                      # Redis Streams 이벤트
│   │   ├── redis_client.py
│   │   └── redis_streams.py
│   │
│   ├── celery/                      # Celery 공통 설정
│   │   ├── config.py
│   │   ├── async_support.py
│   │   └── base_task.py
│   │
│   └── cache/                       # 캐시 관리
│       ├── character_cache.py
│       └── cache_consumer.py
│
└── scan/
    ├── tasks/
    │   ├── vision.py                # vision task
    │   ├── rule.py                  # rule task
    │   ├── answer.py                # answer task
    │   └── reward.py                # reward task
    └── ...
```

### 2.2 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Scan Pipeline 흐름                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   scan-api                                                                   │
│     │                                                                        │
│     └── Celery Queue ──▶ scan-worker                                        │
│                              │                                               │
│                              ▼                                               │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐                 │
│   │ vision  │───▶│  rule   │───▶│ answer  │───▶│ reward  │                 │
│   │  task   │    │  task   │    │  task   │    │  task   │                 │
│   └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘                 │
│        │              │              │              │                        │
│        ▼              ▼              ▼              ▼                        │
│   waste_pipeline  waste_pipeline  waste_pipeline  character                 │
│   /vision.py      /rag.py         /answer.py      gRPC/Celery               │
│        │                              │                                      │
│        ▼                              ▼                                      │
│   OpenAI gpt-5.1              OpenAI gpt-5.1                                │
│                                                                              │
│   모든 태스크 ──▶ Redis Streams ──▶ SSE Gateway ──▶ Client                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Clean Architecture 레이어 정의

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Celery Tasks (vision_task, rule_task, answer_task, reward_task)      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                         Application Layer                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │    Commands     │  │      Ports      │  │         DTOs                │ │
│  │  (Use Cases)    │  │  (Interfaces)   │  │  (Data Transfer)            │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│                        Infrastructure Layer                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  waste_pipeline/    # domains/_shared/waste_pipeline 전체 이전          ││
│  │  ├── vision.py, answer.py, rag.py, ...                                  ││
│  │  └── data/ (prompts, yaml, json)                                        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ Event Publisher │  │ Character Client│  │      Cache Manager          │ │
│  │ (Redis Streams) │  │ (Celery 위임)   │  │                             │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Domain Layer                                        │
│  ┌─────────────────┐  ┌─────────────────┐                                  │
│  │     Enums       │  │  Value Objects  │                                  │
│  │ (PipelineStage) │  │ (Classification)│                                  │
│  └─────────────────┘  └─────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 디렉토리 구조

```
apps/scan_worker/
├── __init__.py
│
├── domain/                           # 핵심 도메인 (의존성 없음)
│   ├── __init__.py
│   ├── enums/
│   │   ├── __init__.py
│   │   └── pipeline_stage.py         # QUEUED, VISION, RULE, ANSWER, REWARD, DONE
│   └── value_objects/
│       ├── __init__.py
│       └── classification.py         # Classification VO (불변)
│
├── application/                      # 유스케이스 (Port 의존)
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── dto/
│   │   │   ├── __init__.py
│   │   │   └── pipeline_context.py   # 스테이지 간 전달 DTO
│   │   └── ports/
│   │       ├── __init__.py
│   │       ├── event_publisher.py    # 이벤트 발행 인터페이스
│   │       └── result_cache.py       # 결과 캐시 인터페이스
│   │
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── ports/
│   │   │   └── vision_analyzer.py    # Vision 분석 인터페이스
│   │   └── commands/
│   │       └── analyze_image.py      # Vision 분석 커맨드
│   │
│   ├── rule/
│   │   ├── __init__.py
│   │   ├── ports/
│   │   │   └── rule_repository.py    # 규정 검색 인터페이스
│   │   └── commands/
│   │       └── retrieve_rules.py     # 규정 검색 커맨드
│   │
│   ├── answer/
│   │   ├── __init__.py
│   │   ├── ports/
│   │   │   └── answer_generator.py   # 답변 생성 인터페이스
│   │   └── commands/
│   │       └── generate_answer.py    # 답변 생성 커맨드
│   │
│   └── reward/
│       ├── __init__.py
│       ├── ports/
│       │   └── character_client.py   # 캐릭터 서비스 인터페이스
│       └── commands/
│           └── process_reward.py     # 보상 처리 커맨드
│
├── infrastructure/                   # 외부 시스템 어댑터 (구현체)
│   ├── __init__.py
│   │
│   ├── waste_pipeline/               # domains/_shared/waste_pipeline 전체 이전
│   │   ├── __init__.py
│   │   ├── vision.py                 # Vision 분석 (OpenAI gpt-5.1)
│   │   ├── answer.py                 # Answer 생성 (OpenAI gpt-5.1)
│   │   ├── rag.py                    # 규정 검색 (JSON 기반)
│   │   ├── text.py                   # 텍스트 분류
│   │   ├── pipeline.py               # 파이프라인 조합
│   │   ├── utils.py                  # 유틸리티
│   │   └── data/
│   │       ├── prompts/
│   │       │   ├── vision_classification_prompt.txt
│   │       │   ├── answer_generation_prompt.txt
│   │       │   └── text_classification_prompt.txt
│   │       ├── item_class_list.yaml
│   │       ├── situation_tags.yaml
│   │       └── source/               # 규정 JSON (18개)
│   │           ├── 재활용폐기물_플라스틱류.json
│   │           ├── 재활용폐기물_종이.json
│   │           └── ...
│   │
│   ├── adapters/                     # Port 구현체
│   │   ├── __init__.py
│   │   ├── vision_analyzer_impl.py   # VisionAnalyzer 구현 (waste_pipeline 호출)
│   │   ├── answer_generator_impl.py  # AnswerGenerator 구현 (waste_pipeline 호출)
│   │   └── rule_repository_impl.py   # RuleRepository 구현 (waste_pipeline 호출)
│   │
│   ├── persistence_redis/            # Redis 관련
│   │   ├── __init__.py
│   │   ├── event_publisher_impl.py   # EventPublisher 구현
│   │   └── result_cache_impl.py      # ResultCache 구현
│   │
│   └── character_client/             # 캐릭터 서비스 연동
│       ├── __init__.py
│       └── celery_client_impl.py     # CharacterClient 구현 (Celery 위임)
│
├── presentation/                     # 진입점
│   ├── __init__.py
│   └── tasks/
│       ├── __init__.py
│       ├── vision_task.py
│       ├── rule_task.py
│       ├── answer_task.py
│       └── reward_task.py
│
├── setup/                            # 설정 및 DI
│   ├── __init__.py
│   ├── celery.py                     # Celery 앱 설정
│   ├── config.py                     # 환경변수 설정
│   └── dependencies.py               # DI Container
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   └── integration/
│
├── Dockerfile
├── main.py                           # Celery 진입점
└── requirements.txt
```

---

## 5. 코드 이전 매핑

### 5.1 waste_pipeline 전체 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `_shared/waste_pipeline/vision.py` | `infrastructure/waste_pipeline/vision.py` |
| `_shared/waste_pipeline/answer.py` | `infrastructure/waste_pipeline/answer.py` |
| `_shared/waste_pipeline/rag.py` | `infrastructure/waste_pipeline/rag.py` |
| `_shared/waste_pipeline/text.py` | `infrastructure/waste_pipeline/text.py` |
| `_shared/waste_pipeline/pipeline.py` | `infrastructure/waste_pipeline/pipeline.py` |
| `_shared/waste_pipeline/utils.py` | `infrastructure/waste_pipeline/utils.py` |
| `_shared/waste_pipeline/data/*` | `infrastructure/waste_pipeline/data/*` |

### 5.2 이벤트/캐시 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `_shared/events/redis_streams.py` | `infrastructure/persistence_redis/event_publisher_impl.py` |
| `_shared/events/redis_client.py` | `infrastructure/persistence_redis/redis_client.py` |

### 5.3 Reward 로직 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `scan/tasks/reward.py` → `_dispatch_*` | `infrastructure/character_client/celery_client_impl.py` |

---

## 6. 의존성 방향 (DIP 준수)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          의존성 방향                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Presentation ──▶ Application ──▶ Domain                                   │
│        │               │                                                     │
│        │               ▼                                                     │
│        └────────▶ Infrastructure                                             │
│                                                                              │
│   [규칙]                                                                     │
│   - Domain: 어떤 레이어에도 의존하지 않음                                    │
│   - Application: Domain만 의존, Port(ABC)를 정의                            │
│   - Infrastructure: Application의 Port를 구현                               │
│   - Presentation: DI로 Infrastructure 주입받아 Command 호출                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. 작업 순서

### Phase 1: 기본 구조 생성 (0.5h)
1. 디렉토리 구조 생성
2. `__init__.py` 파일 생성
3. `setup/config.py` 환경변수 설정

### Phase 2: Domain Layer (0.5h)
1. `domain/enums/pipeline_stage.py` - 파이프라인 스테이지 열거형
2. `domain/value_objects/classification.py` - 분류 결과 VO

### Phase 3: Application Layer - Ports (1h)
1. `application/common/ports/event_publisher.py` - ABC 정의
2. `application/common/ports/result_cache.py` - ABC 정의
3. `application/vision/ports/vision_analyzer.py` - ABC 정의
4. `application/answer/ports/answer_generator.py` - ABC 정의
5. `application/rule/ports/rule_repository.py` - ABC 정의
6. `application/reward/ports/character_client.py` - ABC 정의

### Phase 4: Application Layer - Commands (1h)
1. `application/common/dto/pipeline_context.py` - 스테이지 간 전달 DTO
2. `application/vision/commands/analyze_image.py` - Vision 커맨드
3. `application/rule/commands/retrieve_rules.py` - Rule 커맨드
4. `application/answer/commands/generate_answer.py` - Answer 커맨드
5. `application/reward/commands/process_reward.py` - Reward 커맨드

### Phase 5: Infrastructure Layer - waste_pipeline 복사 (1h)
1. `domains/_shared/waste_pipeline/` → `infrastructure/waste_pipeline/` 전체 복사
2. import 경로 수정
3. 데이터 파일 경로 수정 (상대 경로)

### Phase 6: Infrastructure Layer - Adapters (1.5h)
1. `adapters/vision_analyzer_impl.py` - waste_pipeline/vision.py 호출
2. `adapters/answer_generator_impl.py` - waste_pipeline/answer.py 호출
3. `adapters/rule_repository_impl.py` - waste_pipeline/rag.py 호출
4. `persistence_redis/event_publisher_impl.py` - Redis Streams 발행
5. `persistence_redis/result_cache_impl.py` - 결과 캐싱
6. `character_client/celery_client_impl.py` - Celery 태스크 위임

### Phase 7: Presentation Layer (0.5h)
1. `presentation/tasks/vision_task.py` - DI 기반 Command 호출
2. `presentation/tasks/rule_task.py`
3. `presentation/tasks/answer_task.py`
4. `presentation/tasks/reward_task.py`

### Phase 8: Setup & DI (0.5h)
1. `setup/celery.py` - Celery 앱 설정
2. `setup/dependencies.py` - 의존성 주입 설정

### Phase 9: 테스트 (1h)
1. Unit Tests
2. Integration Tests
3. domains와 결과 비교 테스트

---

## 8. 정합성 체크리스트

| 항목 | 검증 방법 |
|------|----------|
| Vision 프롬프트 동일 | `diff` prompts |
| Vision API 호출 동일 | `gpt-5.1`, `responses.parse`, 스키마 동일 |
| 분류체계 YAML 동일 | `diff` YAML 파일 |
| Rule 검색 로직 동일 | JSON 파일 매칭 로직 동일 |
| Answer 프롬프트 동일 | `diff` prompts |
| Answer API 호출 동일 | `gpt-5.1`, `chat.completions.parse`, 스키마 동일 |
| Event 발행 동일 | Redis Streams, MD5 샤딩, Lua Script |
| 필드명 동일 | `task_id`, `user_id`, `classification_result`, ... |
| 결과 스키마 동일 | `classification_result`, `disposal_rules`, `final_answer` |
| Reward 로직 동일 | `_should_attempt_reward`, 3개 task 발행 |
| 결과 캐싱 동일 | Redis, TTL, 키 형식 |

---

## 9. 예상 소요 시간

| Phase | 작업 내용 | 시간 |
|-------|----------|------|
| Phase 1 | 기본 구조 생성 | 0.5h |
| Phase 2 | Domain Layer | 0.5h |
| Phase 3 | Application Ports | 1h |
| Phase 4 | Application Commands | 1h |
| Phase 5 | waste_pipeline 복사 | 1h |
| Phase 6 | Infrastructure Adapters | 1.5h |
| Phase 7 | Presentation Tasks | 0.5h |
| Phase 8 | Setup & DI | 0.5h |
| Phase 9 | 테스트 | 1h |
| **총계** | | **7.5h** |

---

## 10. Adapter 구현 예시

### VisionAnalyzerImpl (waste_pipeline 호출)

```python
# infrastructure/adapters/vision_analyzer_impl.py
from apps.scan_worker.application.vision.ports.vision_analyzer import VisionAnalyzer
from apps.scan_worker.infrastructure.waste_pipeline.vision import analyze_images

class VisionAnalyzerImpl(VisionAnalyzer):
    """VisionAnalyzer 구현체 - waste_pipeline/vision.py 호출."""
    
    def analyze(self, user_input: str, image_url: str) -> dict:
        """이미지 분석.
        
        domains/_shared/waste_pipeline/vision.py의 analyze_images를 그대로 호출.
        """
        return analyze_images(user_input, image_url, save_result=False)
```

### Task에서 Command 호출

```python
# presentation/tasks/vision_task.py
from apps.scan_worker.setup.dependencies import get_vision_command_handler

@celery_app.task(bind=True, name="scan.vision", queue="scan.vision")
def vision_task(self, task_id: str, user_id: str, image_url: str, user_input: str | None = None):
    """Vision 분석 태스크."""
    
    # DI로 Command Handler 획득
    handler = get_vision_command_handler()
    
    # Command 실행
    result = handler.execute(
        task_id=task_id,
        user_id=user_id,
        image_url=image_url,
        user_input=user_input,
    )
    
    # 다음 태스크 호출
    rule_task.delay(result)
    
    return result
```

---

## 11. 배포 전략

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          배포 전략                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1. Phase A: Canary 배포 (10% 트래픽)                                       │
│      - apps/scan_worker 배포                                                │
│      - domains/scan과 병행 운영                                              │
│      - 결과 비교 모니터링                                                    │
│                                                                              │
│   2. Phase B: Stable 배포 (100% 트래픽)                                      │
│      - 정합성 확인 후 전체 전환                                              │
│      - domains/scan 트래픽 0%                                                │
│                                                                              │
│   3. Phase C: domains 삭제                                                   │
│      - domains/_shared/waste_pipeline 삭제                                   │
│      - domains/scan 삭제                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. 승인 후 진행

이 계획서가 승인되면 Phase 1부터 순차적으로 진행합니다.
