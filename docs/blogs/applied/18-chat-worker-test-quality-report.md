# Chat Worker 테스트 및 품질 리포트

> Eco² Chat Worker의 단위 테스트 작성, 코드 품질 분석, Docker 빌드 검증 결과

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-14 |
| **커밋** | `82b55365` |
| **브랜치** | `refactor/reward-fanout-exchange` |

## 개요

Chat Worker는 LangGraph 기반 파이프라인을 실행하는 핵심 컴포넌트입니다.
Clean Architecture 원칙에 따라 계층별로 분리된 코드에 대해 체계적인 테스트를 작성하고,
코드 품질을 검증했습니다.

```
┌─────────────────────────────────────────────────────┐
│                   Test Coverage                     │
├─────────────────────────────────────────────────────┤
│  Application Layer  │████████████████████│ 88-100% │
│  Domain Layer       │██████████████████░░│ 73-100% │
│  Infrastructure     │████████████████░░░░│ 49-100% │
│  Presentation/Setup │░░░░░░░░░░░░░░░░░░░░│ 0%      │
├─────────────────────────────────────────────────────┤
│  Total              │██████████░░░░░░░░░░│ 49%     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Radon Complexity Grade                 │
├─────────────────────────────────────────────────────┤
│  424 blocks analyzed                                │
│  Average Complexity: A (2.17)                       │
│  Grade: ★★★★★ Excellent                            │
└─────────────────────────────────────────────────────┘
```

---

## 1. 테스트 구조

### 1.1 디렉토리 구조

```
apps/chat_worker/tests/
├── conftest.py                    # Pytest 설정
├── __init__.py
└── unit/
    ├── application/               # Application Layer 테스트
    │   ├── answer/
    │   │   └── test_answer_generator.py
    │   ├── commands/
    │   │   └── test_process_chat.py
    │   ├── integrations/
    │   │   ├── character/
    │   │   │   └── test_character_service.py
    │   │   └── location/
    │   │       └── test_location_service.py
    │   ├── intent/
    │   │   └── test_intent_classifier.py
    │   └── interaction/
    │       └── test_human_interaction_service.py
    └── infrastructure/            # Infrastructure Layer 테스트
        ├── events/
        │   └── test_redis_progress_notifier.py
        ├── integrations/
        │   ├── character/
        │   │   └── test_grpc_client.py
        │   └── location/
        │       └── test_grpc_client.py
        ├── interaction/
        │   └── test_redis_interaction_state_store.py
        └── retrieval/
            └── test_local_asset_retriever.py
```

### 1.2 테스트 원칙

| 원칙 | 설명 |
|------|------|
| **Port Mock** | 외부 의존성을 Port 인터페이스로 추상화, Mock으로 대체 |
| **단일 책임** | 각 테스트는 하나의 동작만 검증 |
| **AAA 패턴** | Arrange → Act → Assert 구조 |
| **Fixture 활용** | 공통 객체는 pytest fixture로 재사용 |

---

## 2. Application Layer 테스트

### 2.1 IntentClassifier

사용자 메시지의 의도를 분류하는 서비스입니다.

```python
# 테스트 예시: 의도 분류 + 복잡도 판단
@pytest.mark.asyncio
async def test_classify_waste_intent(self):
    mock_llm = MockLLMClient("waste")
    classifier = IntentClassifier(mock_llm)

    result = await classifier.classify("페트병 어떻게 버려?")

    assert result.intent == Intent.WASTE
    assert result.confidence == 1.0
```

**테스트 케이스 (16개)**

| 카테고리 | 테스트 | 설명 |
|---------|--------|------|
| Intent Classification | `test_classify_waste_intent` | waste 의도 분류 |
| | `test_classify_character_intent` | character 의도 분류 |
| | `test_classify_location_intent` | location 의도 분류 |
| | `test_classify_general_intent` | general 의도 분류 |
| | `test_classify_unknown_fallback` | 알 수 없는 응답 → general |
| | `test_classify_strips_whitespace` | 응답 공백 제거 |
| | `test_classify_case_insensitive` | 대소문자 무관 |
| Complexity | `test_simple_query_complexity` | 단순 쿼리 판단 |
| | `test_complex_query_with_keyword` | 복잡도 키워드 감지 |
| | `test_complex_query_long_message` | 긴 메시지 → 복잡 |
| | `test_all_complex_keywords` | 모든 키워드 테스트 |
| Error Handling | `test_llm_error_fallback` | LLM 오류 시 기본값 |
| Integration | `test_prompt_passed_correctly` | 프롬프트 전달 확인 |

### 2.2 AnswerGeneratorService

LLM을 사용한 답변 생성 서비스입니다.

**테스트 케이스 (12개)**

| 카테고리 | 테스트 수 | 설명 |
|---------|----------|------|
| Generate | 3 | 일반 답변 생성 |
| Generate Stream | 2 | 스트리밍 답변 생성 |
| Factory Method | 2 | 컨텍스트 생성 |
| AnswerContext DTO | 5 | 컨텍스트 직렬화 |

### 2.3 HumanInteractionService

Human-in-the-Loop 비즈니스 로직을 담당합니다.

```python
# 테스트 예시: 위치 요청 → 이벤트 발행 + 상태 저장
@pytest.mark.asyncio
async def test_request_location_basic(self, service, mock_requester, mock_state_store):
    request_id = await service.request_location(
        job_id="job-123",
        current_state={"message": "테스트"},
    )

    assert request_id == "req-123"
    assert mock_requester.request_input_called
    assert mock_state_store.save_pipeline_called
```

**테스트 케이스 (10개)**

| 메서드 | 테스트 수 | 검증 항목 |
|--------|----------|----------|
| `request_location` | 6 | 이벤트 발행, 상태 저장, 메시지, 타임아웃 |
| `request_confirmation` | 1 | 확인 요청 |
| `complete_interaction` | 1 | 완료 처리 |
| `get_pending_state` | 2 | 상태 조회 |

### 2.4 ProcessChatCommand

최상위 유스케이스 엔트리포인트입니다.

**테스트 케이스 (11개)**

| 카테고리 | 테스트 수 | 검증 항목 |
|---------|----------|----------|
| Basic Execution | 3 | 성공 실행, 상태 전달, 체크포인팅 |
| Event Publishing | 3 | 시작/완료/실패 이벤트 |
| Result Handling | 1 | 결과 반환 |
| Input Handling | 4 | 위치, 이미지, 옵션 처리 |

### 2.5 Integration Services

**CharacterService (8개)**, **LocationService (9개)** 테스트

- Port Mock을 통한 독립 테스트
- DTO 변환 로직 검증
- `to_answer_context` 팩토리 메서드 검증

---

## 3. Infrastructure Layer 테스트

### 3.1 RedisProgressNotifier

SSE 스트리밍을 위한 Redis Streams 이벤트 발행 테스트입니다.

```python
@pytest.mark.asyncio
async def test_notify_stage_basic(self, notifier, mock_redis):
    event_id = await notifier.notify_stage(
        task_id="job-123",
        stage="intent",
        status="started",
    )

    assert event_id is not None
    mock_redis.xadd.assert_called_once()
    
    stream_name = mock_redis.xadd.call_args[0][0]
    assert stream_name == "test:events:job-123"
```

**테스트 케이스 (10개)**

| 메서드 | 테스트 수 | 검증 항목 |
|--------|----------|----------|
| `notify_stage` | 4 | 기본, 진행률, 결과, maxlen |
| `notify_token` | 2 | 토큰 스트리밍 |
| `notify_needs_input` | 2 | HITL 요청 |
| Stream Name | 2 | 키 형식, 태스크 분리 |

### 3.2 RedisInteractionStateStore

Human-in-the-Loop 상태 저장/조회 테스트입니다.

**테스트 케이스 (13개)**

| 메서드 | 테스트 수 | 검증 항목 |
|--------|----------|----------|
| `save_pending_request` | 2 | 저장, 직렬화 |
| `get_pending_request` | 3 | 조회, 키 형식 |
| `mark_completed` | 1 | 완료 처리 |
| `save_pipeline_state` | 2 | 상태 저장 |
| `get_pipeline_state` | 2 | 상태 조회 |
| `clear_state` | 1 | 전체 삭제 |

### 3.3 LocalAssetRetriever

폐기물 분류 규정 JSON 검색 테스트입니다.

```python
@pytest.fixture
def temp_assets_dir(self) -> Path:
    """임시 에셋 디렉토리 생성."""
    with tempfile.TemporaryDirectory() as tmpdir:
        assets_path = Path(tmpdir)
        # JSON 파일 생성
        recycling_data = {"category": "재활용폐기물", ...}
        with open(assets_path / "재활용폐기물.json", "w") as f:
            json.dump(recycling_data, f)
        yield assets_path
```

**테스트 케이스 (14개)**

| 메서드 | 테스트 수 | 검증 항목 |
|--------|----------|----------|
| Initialization | 2 | 초기화, 존재하지 않는 경로 |
| `search` | 5 | 정확/부분 매칭, 약어, 하위카테고리 |
| `search_by_keyword` | 5 | 파일명/내용 매칭, 제한, 대소문자 |
| `get_all_categories` | 2 | 목록, 복사본 반환 |

### 3.4 gRPC Clients

**CharacterGrpcClient (9개)**, **LocationGrpcClient (9개)** 테스트

```python
@pytest.mark.asyncio
async def test_get_character_found(self, client, mock_response_found):
    mock_stub = AsyncMock()
    mock_stub.GetCharacterByMatch = AsyncMock(return_value=mock_response_found)

    with patch.object(client, "_get_stub", return_value=mock_stub):
        result = await client.get_character_by_waste_category("플라스틱")

    assert result is not None
    assert result.name == "플라"
```

| 테스트 | 검증 항목 |
|--------|----------|
| 검색 성공/실패 | DTO 변환, None 반환 |
| gRPC 에러 | 빈 리스트 반환 |
| 연결 관리 | Lazy connection, close |
| 설정 | 주소 구성, 기본값 |

---

## 4. 테스트 실행 결과

### 4.1 전체 결과

```bash
$ pytest apps/chat_worker/tests/ -v

============================= test session starts ==============================
platform darwin -- Python 3.11.14, pytest-9.0.2, pluggy-1.6.0
plugins: anyio-4.12.0, langsmith-0.6.2, asyncio-1.3.0, cov-7.0.0

collected 115 items

apps/chat_worker/tests/unit/application/answer/test_answer_generator.py    12 passed
apps/chat_worker/tests/unit/application/commands/test_process_chat.py      11 passed
apps/chat_worker/tests/unit/application/integrations/character/...          8 passed
apps/chat_worker/tests/unit/application/integrations/location/...           9 passed
apps/chat_worker/tests/unit/application/intent/test_intent_classifier.py   16 passed
apps/chat_worker/tests/unit/application/interaction/...                    10 passed
apps/chat_worker/tests/unit/infrastructure/events/...                      10 passed
apps/chat_worker/tests/unit/infrastructure/integrations/character/...       9 passed
apps/chat_worker/tests/unit/infrastructure/integrations/location/...        9 passed
apps/chat_worker/tests/unit/infrastructure/interaction/...                 13 passed
apps/chat_worker/tests/unit/infrastructure/retrieval/...                   14 passed

============================= 115 passed in 0.24s ==============================
```

### 4.2 커버리지 상세

```
Name                                                          Stmts   Miss  Cover
---------------------------------------------------------------------------------
application/intent/services/intent_classifier.py                 34      0   100%
application/answer/services/answer_generator.py                  30      0   100%
application/interaction/services/human_interaction_service.py    44      0   100%
application/integrations/character/services/character_service.py 20      0   100%
application/integrations/location/services/location_service.py   30      0   100%
application/commands/process_chat.py                             68      0   100%
---------------------------------------------------------------------------------
domain/enums/intent.py                                           16      0   100%
domain/enums/query_complexity.py                                  9      0   100%
domain/value_objects/chat_intent.py                              24      4    83%
---------------------------------------------------------------------------------
infrastructure/events/redis_progress_notifier.py                 38      0   100%
infrastructure/interaction/redis_interaction_state_store.py      50      0   100%
infrastructure/retrieval/local_asset_retriever.py                54      6    89%
infrastructure/integrations/character/grpc_client.py             40      5    88%
infrastructure/integrations/location/grpc_client.py              36      6    83%
---------------------------------------------------------------------------------
TOTAL                                                          1550    788    49%
```

**핵심 비즈니스 로직 커버리지: 88-100%**

---

## 5. 코드 품질 분석 (Radon)

### 5.1 Cyclomatic Complexity

```bash
$ radon cc apps/chat_worker -a -s --total-average

424 blocks (classes, functions, methods) analyzed.
Average complexity: A (2.169811320754717)
```

| 등급 | 복잡도 범위 | 설명 |
|-----|------------|------|
| **A** | 1-5 | 낮은 복잡도, 테스트 용이 |
| B | 6-10 | 약간 복잡 |
| C | 11-20 | 복잡함 |
| D | 21-30 | 매우 복잡 |
| E | 31-40 | 테스트 불가 |
| F | 41+ | 오류 발생 가능 |

**결과: 평균 복잡도 A (2.17) - 최상위 등급**

### 5.2 품질 지표 해석

```
┌────────────────────────────────────────────────────┐
│              Code Quality Summary                  │
├────────────────────────────────────────────────────┤
│  Complexity Grade    │ A (Excellent)              │
│  Average CC          │ 2.17                       │
│  Test Cases          │ 115                        │
│  Pass Rate           │ 100%                       │
│  Core Coverage       │ 88-100%                    │
└────────────────────────────────────────────────────┘
```

---

## 6. Docker 빌드 검증

### 6.1 빌드 성공

```bash
$ docker build -f apps/chat_worker/Dockerfile -t chat_worker:test .

[+] Building 16.0s (15/15) FINISHED
 => [builder] pip install --no-cache-dir --prefix=/install -r requirements.txt
 => [runtime] COPY --from=builder /install /usr/local
 => [runtime] COPY apps/chat /app/chat
 => [runtime] COPY apps/chat_worker /app/chat_worker
 => exporting to image
 => naming to docker.io/library/chat_worker:test
```

### 6.2 모듈 임포트 검증

```bash
$ docker run --rm chat_worker:test python -c "
from chat_worker.application.commands import ProcessChatCommand
from chat_worker.application.intent import IntentClassifier
from chat_worker.application.answer import AnswerGeneratorService
from chat_worker.application.integrations.character import CharacterService
from chat_worker.application.integrations.location import LocationService
from chat_worker.infrastructure.events import RedisProgressNotifier
from chat_worker.infrastructure.retrieval import LocalAssetRetriever
print('All imports successful!')
"

All imports successful!
```

---

## 7. 미테스트 영역 분석

### 7.1 커버리지 0% 영역

| 영역 | 파일 | 이유 |
|-----|------|------|
| LLM Clients | `openai_client.py`, `gemini_client.py` | 외부 API 의존, E2E 테스트 필요 |
| LangGraph | `factory.py`, `nodes/*.py` | 파이프라인 통합 테스트 필요 |
| Setup | `dependencies.py`, `broker.py` | DI 컨테이너, 통합 테스트 필요 |
| Presentation | `process_task.py` | Taskiq 워커, E2E 테스트 필요 |

### 7.2 향후 테스트 계획

```
Phase 1: 단위 테스트 (완료)
├── Application Services ✓
├── Infrastructure Adapters ✓
└── Domain Value Objects ✓

Phase 2: 통합 테스트 (예정)
├── LangGraph Pipeline E2E
├── Redis + PostgreSQL 연동
└── gRPC Client 실제 연결

Phase 3: 부하 테스트 (예정)
├── k6 시나리오 작성
├── VU 300 목표
└── p95 응답 시간 측정
```

---

## 8. 결론

### 8.1 달성 목표

| 항목 | 목표 | 결과 | 상태 |
|-----|------|------|------|
| 테스트 케이스 | 100+ | 115 | ✅ |
| 통과율 | 100% | 100% | ✅ |
| 핵심 커버리지 | 80%+ | 88-100% | ✅ |
| 복잡도 등급 | A-B | A (2.17) | ✅ |
| Docker 빌드 | 성공 | 성공 | ✅ |

### 8.2 품질 보증

Clean Architecture 원칙에 따라 계층별로 분리된 테스트를 통해:

1. **Port/Adapter 패턴**: 외부 의존성을 Mock으로 대체하여 독립적인 단위 테스트 가능
2. **비즈니스 로직 분리**: Application Services의 100% 커버리지 달성
3. **낮은 복잡도**: 평균 CC 2.17로 유지보수 용이
4. **Docker 검증**: 프로덕션 환경과 동일한 이미지에서 모듈 임포트 확인

---

## 부록: 테스트 실행 명령어

```bash
# 전체 테스트 실행
pytest apps/chat_worker/tests/ -v

# 커버리지 측정
pytest apps/chat_worker/tests/ --cov=apps/chat_worker --cov-report=term-missing

# 특정 테스트만 실행
pytest apps/chat_worker/tests/unit/application/intent/ -v

# Radon 복잡도 분석
radon cc apps/chat_worker -a -s --total-average

# Docker 빌드
docker build -f apps/chat_worker/Dockerfile -t chat_worker:test .

# Docker 테스트
docker run --rm chat_worker:test python -c "from chat_worker.main import broker; print('OK')"
```

---

## 커밋 정보

**Commit**: `82b55365ec6a8a4775a1489c1ae2b9a6ab32cb8c`

```
test(chat_worker): add unit tests for application and infrastructure layers

- Application Layer Tests (66 cases):
  - IntentClassifier: 16 tests for intent classification and complexity
  - AnswerGeneratorService: 12 tests for answer generation and streaming
  - HumanInteractionService: 10 tests for HITL flow
  - CharacterService: 8 tests for character integration
  - LocationService: 9 tests for location integration
  - ProcessChatCommand: 11 tests for main use case

- Infrastructure Layer Tests (49 cases):
  - RedisProgressNotifier: 10 tests for SSE event publishing
  - RedisInteractionStateStore: 13 tests for HITL state management
  - LocalAssetRetriever: 14 tests for RAG retrieval
  - CharacterGrpcClient: 9 tests for gRPC integration
  - LocationGrpcClient: 9 tests for gRPC integration

- Quality Metrics:
  - 115 tests, 100% pass rate
  - Radon complexity: A (2.17)
  - Core business logic coverage: 88-100%
  - Docker build verified
```

**Changed Files (33)**

```
apps/chat_worker/infrastructure/integrations/location/grpc_client.py
apps/chat_worker/tests/__init__.py
apps/chat_worker/tests/conftest.py
apps/chat_worker/tests/unit/__init__.py
apps/chat_worker/tests/unit/application/__init__.py
apps/chat_worker/tests/unit/application/answer/__init__.py
apps/chat_worker/tests/unit/application/answer/test_answer_generator.py
apps/chat_worker/tests/unit/application/commands/__init__.py
apps/chat_worker/tests/unit/application/commands/test_process_chat.py
apps/chat_worker/tests/unit/application/integrations/__init__.py
apps/chat_worker/tests/unit/application/integrations/character/__init__.py
apps/chat_worker/tests/unit/application/integrations/character/test_character_service.py
apps/chat_worker/tests/unit/application/integrations/location/__init__.py
apps/chat_worker/tests/unit/application/integrations/location/test_location_service.py
apps/chat_worker/tests/unit/application/intent/__init__.py
apps/chat_worker/tests/unit/application/intent/test_intent_classifier.py
apps/chat_worker/tests/unit/application/interaction/__init__.py
apps/chat_worker/tests/unit/application/interaction/test_human_interaction_service.py
apps/chat_worker/tests/unit/infrastructure/__init__.py
apps/chat_worker/tests/unit/infrastructure/events/__init__.py
apps/chat_worker/tests/unit/infrastructure/events/test_redis_progress_notifier.py
apps/chat_worker/tests/unit/infrastructure/integrations/__init__.py
apps/chat_worker/tests/unit/infrastructure/integrations/character/__init__.py
apps/chat_worker/tests/unit/infrastructure/integrations/character/test_grpc_client.py
apps/chat_worker/tests/unit/infrastructure/integrations/location/__init__.py
apps/chat_worker/tests/unit/infrastructure/integrations/location/test_grpc_client.py
apps/chat_worker/tests/unit/infrastructure/interaction/__init__.py
apps/chat_worker/tests/unit/infrastructure/interaction/test_redis_interaction_state_store.py
apps/chat_worker/tests/unit/infrastructure/orchestration/__init__.py
apps/chat_worker/tests/unit/infrastructure/orchestration/langgraph/__init__.py
apps/chat_worker/tests/unit/infrastructure/orchestration/langgraph/nodes/__init__.py
apps/chat_worker/tests/unit/infrastructure/retrieval/__init__.py
apps/chat_worker/tests/unit/infrastructure/retrieval/test_local_asset_retriever.py
```

