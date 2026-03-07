# Clean Architecture #13: Scan 도메인 마이그레이션 로드맵

> `domains/scan` → `apps/scan` + `apps/scan_worker` Clean Architecture 전환  
> **AI Assistant**: Claude Opus 4.5 (Anthropic)  
> **작업 일자**: 2026-01-05

---

## 1. 마이그레이션 목표

| 목표 | 설명 |
|------|------|
| **Clean Architecture** | 계층 분리로 테스트 용이성, 유지보수성 향상 |
| **책임 분리** | scan-api (가벼운 HTTP 인터페이스) ↔ scan-worker (무거운 AI 파이프라인) |
| **domains 삭제 대비** | `domains/_shared/waste_pipeline`을 `apps/scan_worker`로 이전 |
| **100% 동작 동일** | 기존 로직과 완벽히 동일한 동작 보장 |

---

## 2. 현재 구조 분석

### 2.1 디렉토리 구조

```
domains/
├── _shared/
│   ├── waste_pipeline/              # AI 파이프라인 핵심 로직 ★
│   │   ├── vision.py                # Vision LLM 분석
│   │   ├── answer.py                # Answer LLM 생성
│   │   ├── rag.py                   # 규정 검색 (RAG)
│   │   ├── text.py                  # 텍스트 분류
│   │   ├── pipeline.py              # 파이프라인 조합
│   │   ├── utils.py                 # 유틸리티
│   │   └── data/
│   │       ├── prompts/             # LLM 프롬프트
│   │       │   ├── vision_classification_prompt.txt
│   │       │   ├── answer_generation_prompt.txt
│   │       │   └── text_classification_prompt.txt
│   │       ├── item_class_list.yaml # 분류체계 (대/중/소분류)
│   │       ├── situation_tags.yaml  # 상황 태그
│   │       └── source/              # 규정 JSON (18개)
│   │           ├── 재활용폐기물_플라스틱류.json
│   │           ├── 재활용폐기물_종이.json
│   │           └── ...
│   │
│   ├── events/                      # Redis Streams 이벤트
│   │   ├── redis_client.py
│   │   └── redis_streams.py
│   │
│   ├── celery/                      # Celery 공통 설정
│   │   └── async_support.py
│   │
│   └── cache/                       # 캐시 관리
│       └── character_cache.py
│
└── scan/
    ├── api/v1/endpoints/
    │   ├── scan.py                  # POST /scan (비동기 Celery)
    │   ├── completion.py            # POST /completion (동기 SSE)
    │   ├── progress.py              # GET /progress/{task_id} (SSE)
    │   └── health.py
    ├── services/
    │   └── scan.py                  # ScanService (~460줄)
    ├── tasks/                       # Celery Chain (4단계)
    │   ├── vision.py                # Step 1: GPT Vision
    │   ├── rule.py                  # Step 2: RAG 규정 검색
    │   ├── answer.py                # Step 3: GPT 답변 생성
    │   └── reward.py                # Step 4: 캐릭터 보상 처리
    ├── celery_app.py
    └── schemas/
```

### 2.2 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Scan Pipeline (현재 domains 구조)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Client                                                                     │
│     │                                                                        │
│     ▼                                                                        │
│   scan-api (domains/scan)                                                   │
│     │                                                                        │
│     └── Celery Queue ──────▶ scan-worker (domains/scan/tasks)              │
│                                      │                                       │
│                                      ▼                                       │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│   │  vision  │─▶│   rule   │─▶│  answer  │─▶│  reward  │                   │
│   │  ~8초    │  │  ~0.1초  │  │  ~3초    │  │  ~1초    │                   │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │
│        │             │             │             │                          │
│        ▼             ▼             ▼             ▼                          │
│   waste_pipeline waste_pipeline waste_pipeline character                    │
│   /vision.py     /rag.py        /answer.py     gRPC/Celery                 │
│        │                             │                                       │
│        ▼                             ▼                                       │
│   OpenAI GPT                   OpenAI GPT                                   │
│                                                                              │
│   모든 태스크 ──▶ Redis Streams ──▶ SSE Gateway ──▶ Client                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 클라이언트 SSE 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Client → Server Flow                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: POST /api/v1/scan                                                  │
│  ┌─────────┐    {"image_url": "...", "user_input": "..."}                  │
│  │ Client  │ ────────────────────────────────────────────▶ [scan-api]      │
│  └─────────┘                                                                │
│       │      {"job_id": "abc-123",                                         │
│       │       "stream_url": "/api/v1/stream?job_id=abc-123"}               │
│       ◀────────────────────────────────────────────────────────────────────│
│       │                                                                     │
│  Step 2: GET /api/v1/stream?job_id=abc-123 (sse-gateway)                   │
│       │                                                                     │
│       │ ◀──── event: stage                                                 │
│       │       data: {"step":"vision","status":"started","progress":0}      │
│       │                                                                     │
│       │ ◀──── event: stage                                                 │
│       │       data: {"step":"vision","status":"completed","progress":25}   │
│       │                                                                     │
│       │ ◀──── event: stage                                                 │
│       │       data: {"step":"rule","status":"completed","progress":50}     │
│       │                                                                     │
│       │ ◀──── event: stage                                                 │
│       │       data: {"step":"answer","status":"completed","progress":75}   │
│       │                                                                     │
│       │ ◀──── event: stage                                                 │
│       │       data: {"step":"reward","status":"completed","progress":100}  │
│       │                                                                     │
│       │ ◀──── event: ready                                                 │
│       │       data: {"step":"done","result":{...}}                         │
│       │                                                                     │
│  Step 3: GET /api/v1/scan/result/abc-123 (Optional)                        │
│       │ ◀──── 200 OK: ClassificationResponse                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 마이그레이션 구조

### 3.1 핵심 아이디어: 책임 분리

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         책임 분리 (Clean Architecture)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   apps/scan/ (scan-api)              apps/scan_worker/ (scan-worker)        │
│   ───────────────────────            ────────────────────────────           │
│   • HTTP 요청 수신                   • 실제 AI 로직 (waste_pipeline)        │
│   • Celery 태스크 발행만             • LLM API 호출                         │
│   • SSE 레거시 호환                  • Redis Streams 이벤트 발행            │
│   • 결과 조회                        • 결과 캐싱                            │
│                                                                              │
│   waste_pipeline ❌ 없음             waste_pipeline ✅ 전체 보유            │
│   가벼운 Docker 이미지               무거운 Docker 이미지                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 apps/scan/ (scan-api) - 가벼운 HTTP 인터페이스

```
apps/scan/
├── domain/
│   └── enums/
│       └── scan_status.py                 # QUEUED, PROCESSING, COMPLETED, FAILED
│
├── application/
│   ├── commands/
│   │   └── start_scan.py                  # StartScanCommand → Celery 발행
│   ├── queries/
│   │   └── get_result.py                  # GetResultQuery → Redis 캐시 조회
│   └── ports/
│       ├── scan_pipeline_client.py        # 파이프라인 호출 Port (ABC)
│       └── result_cache.py                # 결과 캐시 Port (ABC)
│
├── infrastructure/
│   ├── scan_worker_client/
│   │   └── celery_client.py               # Celery 태스크 발행 Adapter
│   └── persistence_redis/
│       └── result_cache_impl.py           # Redis 결과 조회 Adapter
│
└── presentation/
    ├── http/
    │   └── controllers/
    │       ├── scan.py                    # POST /scan
    │       ├── result.py                  # GET /scan/result/{task_id}
    │       └── categories.py              # GET /scan/categories
    └── sse/
        └── controllers/
            ├── completion.py              # POST /classify/completion (레거시)
            └── progress.py                # GET /{task_id}/progress (레거시)
```

### 3.3 apps/scan_worker/ (scan-worker) - 무거운 AI 파이프라인

```
apps/scan_worker/
├── domain/
│   ├── enums/
│   │   └── pipeline_stage.py              # QUEUED, VISION, RULE, ANSWER, REWARD, DONE
│   └── value_objects/
│       └── classification.py              # Classification VO (불변)
│
├── application/
│   ├── common/
│   │   ├── dto/
│   │   │   └── pipeline_context.py        # 스테이지 간 전달 DTO
│   │   └── ports/
│   │       ├── event_publisher.py         # 이벤트 발행 Port (ABC)
│   │       └── result_cache.py            # 결과 캐시 Port (ABC)
│   │
│   ├── vision/
│   │   ├── ports/
│   │   │   └── vision_analyzer.py         # Vision 분석 Port (ABC)
│   │   └── commands/
│   │       └── analyze_image.py           # AnalyzeImageCommand
│   │
│   ├── rule/
│   │   ├── ports/
│   │   │   └── rule_repository.py         # 규정 검색 Port (ABC)
│   │   └── commands/
│   │       └── retrieve_rules.py          # RetrieveRulesCommand
│   │
│   ├── answer/
│   │   ├── ports/
│   │   │   └── answer_generator.py        # 답변 생성 Port (ABC)
│   │   └── commands/
│   │       └── generate_answer.py         # GenerateAnswerCommand
│   │
│   └── reward/
│       ├── ports/
│       │   └── character_client.py        # 캐릭터 서비스 Port (ABC)
│       └── commands/
│           └── process_reward.py          # ProcessRewardCommand
│
├── infrastructure/
│   │
│   ├── waste_pipeline/                    # ★ domains/_shared/waste_pipeline 전체 이전
│   │   ├── __init__.py
│   │   ├── vision.py                      # Vision 분석 (OpenAI GPT)
│   │   ├── answer.py                      # Answer 생성 (OpenAI GPT)
│   │   ├── rag.py                         # 규정 검색 (JSON 기반)
│   │   ├── text.py                        # 텍스트 분류
│   │   ├── pipeline.py                    # 파이프라인 조합
│   │   ├── utils.py                       # 유틸리티
│   │   └── data/
│   │       ├── prompts/
│   │       │   ├── vision_classification_prompt.txt
│   │       │   ├── answer_generation_prompt.txt
│   │       │   └── text_classification_prompt.txt
│   │       ├── item_class_list.yaml       # 분류체계
│   │       ├── situation_tags.yaml        # 상황 태그
│   │       └── source/                    # 규정 JSON (18개)
│   │           ├── 재활용폐기물_플라스틱류.json
│   │           ├── 재활용폐기물_종이.json
│   │           └── ...
│   │
│   ├── adapters/                          # Port → waste_pipeline 연결
│   │   ├── vision_analyzer_impl.py        # VisionAnalyzer 구현
│   │   ├── answer_generator_impl.py       # AnswerGenerator 구현
│   │   └── rule_repository_impl.py        # RuleRepository 구현
│   │
│   ├── persistence_redis/
│   │   ├── event_publisher_impl.py        # Redis Streams 발행
│   │   └── result_cache_impl.py           # 결과 캐싱
│   │
│   └── character_client/
│       └── celery_client_impl.py          # 캐릭터 서비스 Celery 위임
│
├── presentation/
│   └── tasks/                             # Celery 태스크 (진입점)
│       ├── vision_task.py
│       ├── rule_task.py
│       ├── answer_task.py
│       └── reward_task.py
│
├── setup/
│   ├── celery.py                          # Celery 앱 설정
│   ├── config.py                          # 환경변수 설정
│   └── dependencies.py                    # DI Container
│
├── Dockerfile
├── main.py                                # Celery 진입점
└── requirements.txt
```

---

## 4. 코드 이전 매핑

### 4.1 waste_pipeline 전체 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `_shared/waste_pipeline/vision.py` | `infrastructure/waste_pipeline/vision.py` |
| `_shared/waste_pipeline/answer.py` | `infrastructure/waste_pipeline/answer.py` |
| `_shared/waste_pipeline/rag.py` | `infrastructure/waste_pipeline/rag.py` |
| `_shared/waste_pipeline/text.py` | `infrastructure/waste_pipeline/text.py` |
| `_shared/waste_pipeline/pipeline.py` | `infrastructure/waste_pipeline/pipeline.py` |
| `_shared/waste_pipeline/utils.py` | `infrastructure/waste_pipeline/utils.py` |
| `_shared/waste_pipeline/data/*` | `infrastructure/waste_pipeline/data/*` |

### 4.2 이벤트/캐시 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `_shared/events/redis_streams.py` | `infrastructure/persistence_redis/event_publisher_impl.py` |
| `_shared/events/redis_client.py` | `infrastructure/persistence_redis/redis_client.py` |

### 4.3 Reward 로직 복사

| 원본 (domains) | 대상 (apps/scan_worker) |
|---------------|------------------------|
| `scan/tasks/reward.py` 헬퍼 함수 | `infrastructure/character_client/celery_client_impl.py` |

---

## 5. 의존성 방향 (DIP)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          의존성 방향 (Dependency Rule)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Presentation ──▶ Application ──▶ Domain                                   │
│        │               │                                                     │
│        │               ▼ (Port 정의)                                        │
│        │          ┌─────────┐                                               │
│        │          │  ABC    │ ◀────────────────────────┐                   │
│        │          │  Port   │                          │                    │
│        │          └─────────┘                          │                    │
│        │                                               │ (구현)              │
│        └────────────────────────────────▶ Infrastructure                    │
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

## 6. Adapter 구현 패턴

### 6.1 VisionAnalyzerImpl (waste_pipeline 직접 호출)

```python
# infrastructure/adapters/vision_analyzer_impl.py
from apps.scan_worker.application.vision.ports.vision_analyzer import VisionAnalyzer
from apps.scan_worker.infrastructure.waste_pipeline.vision import analyze_images


class VisionAnalyzerImpl(VisionAnalyzer):
    """VisionAnalyzer 구현체 - waste_pipeline/vision.py 직접 호출.
    
    domains/_shared/waste_pipeline/vision.py의 analyze_images를 그대로 호출하여
    프롬프트, 분류체계, API 호출 방식 모두 기존과 동일하게 동작.
    """
    
    def analyze(self, user_input: str, image_url: str) -> dict:
        """이미지 분석.
        
        Args:
            user_input: 사용자 입력 (질문)
            image_url: 분석할 이미지 URL
        
        Returns:
            분류 결과 딕셔너리 (classification_result)
        """
        return analyze_images(user_input, image_url, save_result=False)
```

### 6.2 Task에서 Command 호출

```python
# presentation/tasks/vision_task.py
from apps.scan_worker.setup.dependencies import get_vision_command_handler
from apps.scan_worker.setup.celery import celery_app


@celery_app.task(
    bind=True,
    name="scan.vision",
    queue="scan.vision",
    max_retries=2,
)
def vision_task(
    self,
    task_id: str,
    user_id: str,
    image_url: str,
    user_input: str | None = None,
):
    """Vision 분석 태스크 (Stage 1).
    
    DI로 Command Handler를 획득하여 Clean Architecture 원칙 준수.
    """
    # DI Container에서 Handler 획득
    handler = get_vision_command_handler()
    
    # Command 실행
    result = handler.execute(
        task_id=task_id,
        user_id=user_id,
        image_url=image_url,
        user_input=user_input or "이 폐기물을 어떻게 분리배출해야 하나요?",
    )
    
    return result
```

---

## 7. 마이그레이션 단계

### Phase 1: 기본 구조 생성 (0.5h)

```bash
# 디렉토리 생성
mkdir -p apps/scan/{domain,application,infrastructure,presentation,setup}
mkdir -p apps/scan_worker/{domain,application,infrastructure,presentation,setup}
```

### Phase 2: Domain Layer (0.5h)

| 파일 | 내용 |
|------|------|
| `domain/enums/scan_status.py` | QUEUED, PROCESSING, COMPLETED, FAILED |
| `domain/enums/pipeline_stage.py` | VISION, RULE, ANSWER, REWARD, DONE |
| `domain/value_objects/classification.py` | Classification VO (불변) |

### Phase 3: Application Layer - Ports (1h)

| 파일 | 역할 |
|------|------|
| `application/common/ports/event_publisher.py` | Redis Streams 발행 인터페이스 |
| `application/common/ports/result_cache.py` | 결과 캐시 인터페이스 |
| `application/vision/ports/vision_analyzer.py` | Vision 분석 인터페이스 |
| `application/answer/ports/answer_generator.py` | 답변 생성 인터페이스 |
| `application/rule/ports/rule_repository.py` | 규정 검색 인터페이스 |
| `application/reward/ports/character_client.py` | 캐릭터 서비스 인터페이스 |

### Phase 4: Application Layer - Commands (1h)

| 파일 | 역할 |
|------|------|
| `application/common/dto/pipeline_context.py` | 스테이지 간 전달 DTO |
| `application/vision/commands/analyze_image.py` | Vision 분석 커맨드 |
| `application/rule/commands/retrieve_rules.py` | 규정 검색 커맨드 |
| `application/answer/commands/generate_answer.py` | 답변 생성 커맨드 |
| `application/reward/commands/process_reward.py` | 보상 처리 커맨드 |

### Phase 5: Infrastructure - waste_pipeline 복사 (1h)

```bash
# waste_pipeline 전체 복사
cp -r domains/_shared/waste_pipeline apps/scan_worker/infrastructure/

# import 경로 수정 (sed 또는 수동)
# from domains._shared.waste_pipeline → from apps.scan_worker.infrastructure.waste_pipeline
```

### Phase 6: Infrastructure - Adapters (1.5h)

| 파일 | 역할 |
|------|------|
| `adapters/vision_analyzer_impl.py` | waste_pipeline/vision.py 호출 |
| `adapters/answer_generator_impl.py` | waste_pipeline/answer.py 호출 |
| `adapters/rule_repository_impl.py` | waste_pipeline/rag.py 호출 |
| `persistence_redis/event_publisher_impl.py` | Redis Streams 발행 |
| `persistence_redis/result_cache_impl.py` | 결과 캐싱 |
| `character_client/celery_client_impl.py` | Celery 태스크 위임 |

### Phase 7: Presentation - Tasks (0.5h)

| 파일 | 역할 |
|------|------|
| `tasks/vision_task.py` | DI 기반 Vision Command 호출 |
| `tasks/rule_task.py` | DI 기반 Rule Command 호출 |
| `tasks/answer_task.py` | DI 기반 Answer Command 호출 |
| `tasks/reward_task.py` | DI 기반 Reward Command 호출 |

### Phase 8: Setup & DI (0.5h)

| 파일 | 역할 |
|------|------|
| `setup/celery.py` | Celery 앱 설정 |
| `setup/config.py` | 환경변수 (Settings) |
| `setup/dependencies.py` | DI Container |

### Phase 9: 테스트 (1h)

| 유형 | 범위 |
|------|------|
| Unit Tests | Adapter, Command Handler |
| Integration Tests | Celery Chain |
| E2E Tests | Full Pipeline |

---

## 8. 정합성 체크리스트

| 항목 | 검증 방법 |
|------|----------|
| **Vision 프롬프트 동일** | `diff` prompts/vision_classification_prompt.txt |
| **Vision API 호출 동일** | OpenAI client, `responses.parse`, 스키마 동일 |
| **분류체계 YAML 동일** | `diff` item_class_list.yaml, situation_tags.yaml |
| **Rule 검색 로직 동일** | JSON 파일 매칭 로직 검증 |
| **Answer 프롬프트 동일** | `diff` prompts/answer_generation_prompt.txt |
| **Answer API 호출 동일** | `chat.completions.parse`, 스키마 동일 |
| **Event 발행 동일** | Redis Streams, MD5 샤딩, Lua Script |
| **필드명 동일** | `task_id`, `user_id`, `classification_result`, ... |
| **결과 스키마 동일** | `classification_result`, `disposal_rules`, `final_answer` |
| **Reward 로직 동일** | `_should_attempt_reward`, 3개 task 발행 |
| **결과 캐싱 동일** | Redis, TTL, 키 형식 |

---

## 9. 배포 전략

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            배포 전략                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Phase A: Canary 배포 (10% 트래픽)                                          │
│   ────────────────────────────────                                           │
│   - apps/scan, apps/scan_worker 배포                                        │
│   - domains/scan과 병행 운영                                                 │
│   - 결과 비교 모니터링 (정합성 검증)                                         │
│                                                                              │
│   Phase B: Stable 배포 (100% 트래픽)                                         │
│   ─────────────────────────────────                                          │
│   - 정합성 확인 후 전체 전환                                                 │
│   - domains/scan 트래픽 0%                                                   │
│                                                                              │
│   Phase C: domains 삭제                                                      │
│   ─────────────────────                                                      │
│   - domains/_shared/waste_pipeline 삭제                                      │
│   - domains/scan 삭제                                                        │
│   - domains/_shared/events 삭제                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. 예상 소요 시간

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

## 11. 엔드포인트 매핑

| Legacy (domains/scan) | Clean (apps/scan) | 설명 |
|----------------------|-------------------|------|
| `POST /scan` | `POST /scan` | 메인 - 비동기 제출 |
| `GET /scan/result/{job_id}` | `GET /scan/result/{job_id}` | 결과 조회 |
| `GET /scan/categories` | `GET /scan/categories` | 카테고리 목록 |
| `POST /classify/completion` | `POST /classify/completion` | SSE 스트리밍 (레거시) |
| `GET /{task_id}/progress` | `GET /{task_id}/progress` | SSE 진행상황 (레거시) |
| `GET /stream?job_id=xxx` | `GET /stream?job_id=xxx` | **별도 서비스** (sse-gateway) |

---

## 12. References

- [Clean Architecture #11: Character 마이그레이션](https://rooftopsnow.tistory.com/135)
- [Celery Chain + Events](https://rooftopsnow.tistory.com/68)
- [Redis Streams SSE 마이그레이션](https://rooftopsnow.tistory.com/69)
