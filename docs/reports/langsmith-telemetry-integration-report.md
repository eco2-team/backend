# LangSmith Telemetry Integration Report

**Date:** 2026-01-27 (Updated)
**Author:** Claude Code
**Status:** Completed

## Executive Summary

chat-worker의 LLM 호출 및 이미지 생성에 대한 LangSmith 기반 Observability 시스템을 구축했습니다. 토큰 사용량, 비용, 레이턴시를 자동 추적하며 LangSmith 대시보드에서 실시간 모니터링이 가능합니다.

## 1. 추적 대상

### 1.1 LLM 모델 (3개)

| 모델 | 용도 | Input ($/1M) | Output ($/1M) | 추적 위치 |
|------|------|--------------|---------------|-----------|
| `gpt-5.2` | 텍스트 생성 | $1.75 | $14.00 | `openai_client.py` |
| `gemini-3-flash-preview` | 텍스트 생성 | $0.50 | $3.00 | `gemini_client.py` |
| `gemini-3-pro-image-preview` | 이미지 생성 | $2.00 | $12.00 | `gemini_native.py` |

### 1.2 LangGraph 노드 (17개)

LangGraph가 `add_node()`로 등록된 모든 노드를 자동 추적합니다.

| # | 노드 | 기능 | 실행 조건 |
|---|------|------|-----------|
| 1 | `intent` | 의도 분류 | 항상 |
| 2 | `vision` | 이미지 분석 | 이미지 첨부 시 |
| 3 | `router` | 동적 라우팅 | 항상 |
| 4 | `waste_rag` | 분리배출 RAG | intent=waste |
| 5 | `feedback` | RAG 품질 평가 | waste_rag 후 |
| 6 | `answer` | 최종 답변 생성 | 항상 |
| 7 | `character` | 캐릭터 정보 | intent=character/greeting |
| 8 | `location` | 카카오맵 장소 | intent=location |
| 9 | `web_search` | 웹 검색 | intent=web_search |
| 10 | `bulk_waste` | 대형폐기물 | intent=bulk_waste |
| 11 | `recyclable_price` | 재활용자원 시세 | intent=recyclable_price |
| 12 | `weather` | 날씨 정보 | 병렬 실행 (waste, bulk_waste) |
| 13 | `collection_point` | 수거함 위치 | intent=collection_point |
| 14 | `image_generation` | 이미지 생성 | intent=image_generation |
| 15 | `general` | 일반 대화 | intent=general |
| 16 | `aggregator` | 병렬 결과 집계 | 병렬 노드 완료 후 |
| 17 | `summarize` | 대화 요약 | 토큰 임계치 초과 시 |

### 1.3 추적 메트릭

| 메트릭 | 설명 | 추적 방식 |
|--------|------|-----------|
| LLM Latency | LLM 호출당 지연 시간 (ms) | `track_token_usage()` |
| Cost per Trace | 트레이스당 예상 비용 ($) | `calculate_cost()` |
| Input Tokens | 입력 토큰 수 | LLM 응답 파싱 |
| Output Tokens | 출력 토큰 수 | LLM 응답 파싱 |
| Run Count by Node | 노드별 실행 횟수 | LangGraph 자동 |
| Median Latency by Node | 노드별 중앙값 지연 시간 | LangGraph 자동 |
| Error Rate by Node | 노드별 에러율 | LangGraph 자동 |
| Image Cost | 이미지 생성 비용 ($) | `calculate_image_cost()` |

### 1.4 토큰 추적 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LangSmith Token Tracking Flow                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LangGraph Node                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  answer_node (스트리밍)                                              │   │
│  │  └── llm.generate_stream() / llm.get_langchain_llm().astream()      │   │
│  │      └── LangChainOpenAIRunnable._astream()                         │   │
│  │          └── stream_options: {"include_usage": True}                │   │
│  │          └── 마지막 청크: AIMessageChunk(usage_metadata={...})       │   │
│  │                                                                      │   │
│  │  weather_node, bulk_waste_node, etc. (Function Calling)             │   │
│  │  └── llm.generate_function_call()                                   │   │
│  │      └── client.chat.completions.create()                           │   │
│  │      └── track_token_usage(run_tree, model, input, output)          │   │
│  │                                                                      │   │
│  │  intent_node (비스트리밍)                                            │   │
│  │  └── llm.generate() / llm.ainvoke()                                 │   │
│  │      └── LangChainOpenAIRunnable._agenerate()                       │   │
│  │          └── AIMessage(usage_metadata={...})                        │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LangSmith SDK                                                       │   │
│  │  ├── usage_metadata → Total Tokens 집계                             │   │
│  │  ├── run_tree.extra["metrics"] → Custom 메트릭                      │   │
│  │  └── calculate_cost() → 비용 계산                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LangSmith Dashboard                                                 │   │
│  │  ├── Run Count: 43                                                  │   │
│  │  ├── Total Tokens: 12,345 / $0.15                                   │   │
│  │  └── Per-Run Token Breakdown                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**핵심 포인트:**
- `usage_metadata`: LangSmith가 읽는 표준 필드 (`input_tokens`, `output_tokens`, `total_tokens`)
- `stream_options.include_usage`: OpenAI 스트리밍에서 마지막 청크에 토큰 포함
- `track_token_usage()`: Function Calling 등 직접 API 호출 시 수동 보고

## 2. Kubernetes 배포 설정

### 2.1 chat-worker 환경변수

**파일:** `workloads/domains/chat-worker/base/deployment.yaml`

```yaml
env:
  # LangSmith Observability (LangGraph 노드 추적)
  - name: LANGCHAIN_TRACING_V2
    value: 'true'
  - name: LANGCHAIN_PROJECT
    value: eco2-chat-worker
```

### 2.2 External Secret (SSM)

**파일:** `workloads/secrets/external-secrets/dev/chat-worker-secrets.yaml`

```yaml
# SSM에서 LangSmith API Key 가져오기
- secretKey: langsmithApiKey
  remoteRef:
    key: /eco2/langsmith/api-key

# Secret Template
LANGCHAIN_API_KEY: '{{ .langsmithApiKey }}'
```

### 2.3 Istio ServiceEntry

**파일:** `workloads/routing/langgraph-studio/base/service-entry.yaml`

```yaml
# LangSmith API 접근 허용
apiVersion: networking.istio.io/v1alpha3
kind: ServiceEntry
metadata:
  name: langsmith-api
spec:
  hosts:
  - api.smith.langchain.com
  ports:
  - number: 443
    name: https
    protocol: HTTPS
  resolution: DNS
  location: MESH_EXTERNAL
```

## 3. 코드 구현

### 3.1 파일 변경 목록

```
apps/chat_worker/infrastructure/telemetry/langsmith.py               # 856 lines (메인 모듈)
apps/chat_worker/infrastructure/telemetry/__init__.py                # exports 추가
apps/chat_worker/infrastructure/llm/clients/langchain_runnable_wrapper.py  # 토큰 추적 (usage_metadata)
apps/chat_worker/infrastructure/llm/clients/langchain_adapter.py     # Function Calling 토큰 추적
apps/chat_worker/infrastructure/llm/clients/openai_client.py         # +22 lines
apps/chat_worker/infrastructure/llm/clients/gemini_client.py         # +21 lines
apps/chat_worker/infrastructure/llm/image_generator/gemini_native.py # +27 lines
workloads/domains/chat-worker/base/deployment.yaml                   # +5 lines
workloads/secrets/external-secrets/dev/chat-worker-secrets.yaml      # +5 lines
workloads/secrets/external-secrets/prod/chat-worker-secrets.yaml     # +5 lines
workloads/routing/langgraph-studio/base/service-entry.yaml           # +34 lines (신규)
```

### 3.2 LangChain Runnable 토큰 추적 (Primary)

**파일:** `apps/chat_worker/infrastructure/llm/clients/langchain_runnable_wrapper.py`

LangGraph 노드에서 사용하는 `LangChainOpenAIRunnable`에 `usage_metadata` 추가:

```python
# _agenerate() - 비스트리밍
message = AIMessage(
    content=content,
    usage_metadata={  # LangSmith가 읽는 표준 필드
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    },
    response_metadata={
        "model": self.model,
        "token_usage": token_usage,
    },
)

# _astream() - 스트리밍 (마지막 청크에 usage 포함)
create_params = {
    ...
    "stream_options": {"include_usage": True},  # OpenAI 스트리밍 토큰 포함
}

# 마지막 청크에서 usage_metadata 전달
message_chunk = AIMessageChunk(
    content="",
    usage_metadata={
        "input_tokens": chunk.usage.prompt_tokens,
        "output_tokens": chunk.usage.completion_tokens,
        "total_tokens": chunk.usage.total_tokens,
    },
)
```

### 3.3 Function Calling 토큰 추적

**파일:** `apps/chat_worker/infrastructure/llm/clients/langchain_adapter.py`

Function Calling 노드 (weather, bulk_waste, collection_point 등)에서 토큰 추적:

```python
# generate_function_call() 내부
if is_langsmith_enabled() and response.usage:
    try:
        from langsmith.run_helpers import get_current_run_tree

        run_tree = get_current_run_tree()
        if run_tree:
            track_token_usage(
                run_tree=run_tree,
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )
    except ImportError:
        pass
```

### 3.4 OpenAI 클라이언트 토큰 추적 (Legacy)

**파일:** `apps/chat_worker/infrastructure/llm/clients/openai_client.py:117-131`

```python
# LangSmith 토큰 추적
if is_langsmith_enabled() and response.usage:
    try:
        from langsmith.run_helpers import get_current_run_tree

        run_tree = get_current_run_tree()
        if run_tree:
            track_token_usage(
                run_tree=run_tree,
                model=self._model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )
    except Exception as e:
        logger.debug("Failed to track token usage: %s", e)
```

### 3.5 Gemini 클라이언트 토큰 추적

**파일:** `apps/chat_worker/infrastructure/llm/clients/gemini_client.py:102-116`

```python
# LangSmith 토큰 추적
if is_langsmith_enabled() and response.usage_metadata:
    try:
        from langsmith.run_helpers import get_current_run_tree

        run_tree = get_current_run_tree()
        if run_tree:
            track_token_usage(
                run_tree=run_tree,
                model=self._model,
                input_tokens=response.usage_metadata.prompt_token_count,
                output_tokens=response.usage_metadata.candidates_token_count,
            )
    except Exception as e:
        logger.debug("Failed to track token usage: %s", e)
```

### 3.6 이미지 생성 비용 추적

**파일:** `apps/chat_worker/infrastructure/llm/image_generator/gemini_native.py:341-360`

```python
# LangSmith 이미지 생성 비용 추적
if is_langsmith_enabled():
    try:
        from langsmith.run_helpers import get_current_run_tree

        run_tree = get_current_run_tree()
        if run_tree:
            cost = calculate_image_cost(
                model=self._model,
                size=image_size or "default",
                count=1,
            )
            run_tree.metadata = run_tree.metadata or {}
            run_tree.metadata.update({
                "image_model": self._model,
                "image_size": image_size or "default",
                "image_cost_usd": cost,
                "aspect_ratio": aspect_ratio,
            })
    except Exception as e:
        logger.debug("Failed to track image generation cost: %s", e)
```

## 4. 추적 데코레이터

### 4.1 @traceable_llm

LLM 호출에 대한 자동 추적 데코레이터:

```python
@traceable_llm(model="gpt-5.2")
async def generate_answer(prompt: str) -> str:
    response = await client.chat.completions.create(...)
    return response
```

**추적 항목:** `latency_ms`, `input_tokens`, `output_tokens`, `total_tokens`, `cost_usd`

### 4.2 @traceable_tool

도구/노드 호출 추적 데코레이터:

```python
@traceable_tool(name="weather_api")
async def get_weather(location: str) -> dict:
    ...
```

**추적 항목:** `latency_ms`, `error`

### 4.3 @traceable_image

이미지 생성 추적 데코레이터:

```python
@traceable_image(model="gemini-3-pro-image-preview")
async def generate_character_image(prompt: str) -> ImageGenerationResult:
    ...
```

**추적 항목:** `latency_ms`, `cost_usd`, `image_count`, `image_size`, `error`

## 5. Intent-Feature 매핑

LangSmith에서 피처별 분석을 위한 매핑:

| Intent | Feature | Subagents | 병렬 실행 |
|--------|---------|-----------|-----------|
| waste | rag | waste_rag, weather | Yes |
| bulk_waste | external_api | bulk_waste, weather | Yes |
| character | grpc | character | No |
| location | external_api | location | No |
| web_search | external_api | web_search | No |
| recyclable_price | external_api | recyclable_price | No |
| collection_point | external_api | collection_point | No |
| image_generation | llm_generation | image_generation | No |
| general | llm_generation | general | No |
| greeting | llm_generation | character | No |

## 6. LangSmith 대시보드 활용

### 6.1 필터링 예시

```
# Intent별 필터
metadata.intent = "waste"

# 노드별 필터
name = "waste_rag"

# 에러만 필터
status = "error"

# 특정 job_id
metadata.job_id = "job-123"

# 병렬 실행 노드
tags contains "execution:parallel"
```

### 6.2 분석 가능 항목

1. **Per-Node Latency**: 17개 노드별 소요시간 분포
2. **Token Usage**: 노드별 input/output 토큰 수, 비용 추정
3. **Run Timeline**: 병렬 실행 (Send API) 시각화
4. **Error Tracking**: 노드별 에러율, 스택 트레이스
5. **Cost Analysis**: 트레이스당/일별/모델별 비용
6. **Feedback Loop**: RAG 품질 평가, Fallback 체인 추적

## 7. Git 커밋 히스토리

```
05c56dd3 fix(chat-worker): LangSmith 토큰 추적을 위해 usage_metadata 사용
dfed05f9 fix(chat-worker): generate_function_call() 토큰 추적 추가
6243ac0c fix(chat-worker): LangSmith 토큰 추적 누락 수정
6fa2e417 fix(langgraph-studio): use gemini-3-flash-preview model
aabe0e04 fix(istio): add ServiceEntry for LangSmith API access
4b9a64c5 feat(observability): enable LangSmith tracing for chat-worker
1c3ba1a7 feat(telemetry): add LangSmith token/cost tracking to LLM clients
688bd27a feat(telemetry): add image generation cost tracking
4efa148b fix(telemetry): add gemini-3-pro-preview pricing and update studio defaults
61480312 feat(telemetry): update model pricing for gpt-5.2 and gemini-3
e3d2193d feat(telemetry): add LangSmith metrics tracking decorators
b4955bde feat(observability): implement E2E distributed tracing for chat flow (#421)
```

## 8. 테스트 결과

```
======================== 787 passed, 5 skipped in 4.11s ========================
```

모든 단위 테스트 통과 확인.

## 9. 배포 체크리스트

```bash
# 1. External Secret sync (LANGCHAIN_API_KEY)
argocd app sync argocd/external-secrets-dev --prune

# 2. chat-worker sync (LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT)
argocd app sync argocd/chat-worker --prune

# 3. LangGraph Studio routing sync (ServiceEntry)
argocd app sync argocd/routing-langgraph-studio --prune

# 4. 확인
kubectl get pods -n chat -l app=chat-worker
kubectl logs -n chat -l app=chat-worker | grep LANGCHAIN
```

## 10. 제한사항

1. **부하테스트**: LangSmith는 Observability 도구로, 부하테스트는 Locust/k6 등 별도 도구 필요
2. **실시간 알림**: LangSmith 자체 알림 기능은 제한적, PagerDuty/Slack 연동 권장
3. **비용 정확도**: 모델 가격은 API 문서 기준이며, 실제 청구와 차이 있을 수 있음
4. **Agents SDK**: `generate_with_tools()` (WebSearchTool) 경로는 토큰 추적 미지원 (Agents SDK 내부 처리)

## 11. 향후 개선 사항

1. ~~**Streaming 토큰 추적**~~: ✅ 완료 - `stream_options.include_usage=True`로 마지막 청크에서 추적
2. **Custom Metrics**: 비즈니스 메트릭 (DAU, 질문 유형 분포 등) 추가
3. **A/B 테스트**: 프롬프트 버전별 성능 비교 자동화
4. **Cost Alert**: 일일/월간 비용 임계치 알림
5. **OpenTelemetry 통합**: Jaeger와 LangSmith 트레이스 연결
6. **Agents SDK 토큰 추적**: WebSearchTool 등 Agents SDK 경로 토큰 추적

---

**LangSmith Dashboard:** https://smith.langchain.com
**Project:** eco2-chat-worker
**SSM Path:** /eco2/langsmith/api-key
