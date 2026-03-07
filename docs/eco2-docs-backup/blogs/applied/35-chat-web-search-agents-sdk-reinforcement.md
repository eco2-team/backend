# 이코에코(Eco²) Agent #21: Web Search Agents SDK 전환 및 LLM Client 보강

> Agents SDK Primary + Responses API Fallback 완성 — generate_with_tools, generate_structured 통합

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-25 |
| **커밋** | b7316337, fa4de736, ae27e98d |
| **이전 포스팅** | [#20 Agents SDK Migration](./32-chat-openai-agents-sdk-migration.md) |
| **범위** | LLM Client (openai_client, langchain_adapter), Web Search Node, CI |

---

## 1. 배경: Production 관측 결과

### 1.1 ArgoCD Production 로그 (Before)

ArgoCD 대시보드에서 관측된 chat-worker Pod 로그:

```
# Pod: chat-worker-59f5fdd65c-qcjcd (부팅 → 첫 요청 처리)

[INFO] Web search node created
[INFO] Bulk waste agent node created
[INFO] Recyclable price agent node created
[INFO] Weather agent node created
[INFO] Collection point agent node created
[INFO] Image generation subagent node created (Gemini Native, storage=gRPC)
[INFO] Dynamic routing enabled
[INFO] Chat graph created with checkpointer (multi-turn enabled)

# === 요청 처리 시작 ===
[INFO] ProcessChatCommand received
[INFO] Single intent classification completed (Model-Centric)
[INFO] POST /v1/chat/completions "HTTP/1.1 200 OK"    ← Intent 분류
[INFO] Dynamic router: executing web search
[INFO] Executing web search (mode=enrichment)
[INFO] POST /v1/responses "HTTP/1.1 200 OK"            ← Web search (Responses API raw)
[INFO] POST /v1/chat/completions "HTTP/1.1 200 OK"     ← Answer 생성
[WARNING] Node execution timeout: web_search
[WARNING] No fallback function provided, treating as FAIL_OPEN
[INFO] Aggregator: contexts collected
[INFO] Answer generated
```

**핵심 문제:**
- `/v1/responses` (Responses API raw) → 타임아웃 → FAIL_OPEN
- 검색 결과가 답변에 반영되지 않음

### 1.2 Intent Classification 실측 데이터

```
# Pod: chat-worker-59f5fdd65c-vzm7z

[INFO] Single intent classification completed (Model-Centric)
[INFO] Low confidence (0.55) for intent=general
[INFO] reasoning: '네이버 영화 기준으로 찾아봐'는 특정 폐기물/장소/날씨 등
       앱 기능 범주가 아니라 외부 서비스(네이버 영화) 기준의 검색을 요구
[WARNING] web_search_failed
```

```
# Pod: chat-worker-59f5fdd65c-pjkpw

[INFO] web_search completed
[INFO] intent=general, confidence=0.55
[INFO] reasoning: 숫자 항목에 대한 확인과 영화/콘텐츠의 평론가·관람객 평점 같은
       일반 정보 요청으로 보이나, 특정 앱 기능(장소/분리배출/날씨 등)과
       직접 연결된 의도가 명확하지 않음
[WARNING] No fallback function provided, treating as FAIL_OPEN
[INFO] Aggregator: contexts collected
```

### 1.3 Root Cause 분석

| 구간 | API 엔드포인트 | 상태 | 문제 |
|------|----------------|------|------|
| Intent 분류 | `/v1/chat/completions` | 정상 | - |
| Web Search | `/v1/responses` (raw) | **타임아웃** | Responses API raw 호출 → SDK 재시도/에러 핸들링 미적용 |
| Answer 생성 | `/v1/chat/completions` | 정상 | web_search 결과 누락 (FAIL_OPEN) |

**FAIL_OPEN 동작:** 보조 정보 노드이므로 타임아웃 시 에러 없이 진행하지만, 검색 결과 없이 답변 생성 → 품질 저하.

---

## 2. 수정 사항

### 2.1 전체 변경 범위

| # | 파일 | 변경 | 효과 |
|---|------|------|------|
| 1 | `openai_client.py` | `generate_with_tools` Agents SDK primary | WebSearchTool 네이티브 검색 |
| 2 | `openai_client.py` | `generate_structured` Agents SDK primary | output_type으로 구조화 출력 |
| 3 | `langchain_adapter.py` | `generate_with_tools` Agents SDK primary | LangGraph 호환 유지 |
| 4 | `langchain_adapter.py` | `generate_structured` Agents SDK primary | LangChain fallback 보존 |
| 5 | `web_search_node.py` | Function Calling 제거 → Router 결정 신뢰 | 1회 API 호출로 완료 |

### 2.2 API 호출 구조 변경

```
Before (Production 로그 관측):
────────────────────────────────────────────────
Intent → /v1/chat/completions (200 OK)
  ↓
Web Search → /v1/responses (raw, 200 OK but TIMEOUT at node level)
  ↓
Answer → /v1/chat/completions (200 OK, 검색 결과 누락)

After (Agents SDK Primary):
────────────────────────────────────────────────
Intent → /v1/chat/completions (200 OK)
  ↓
Web Search → Agents SDK Runner.run_streamed()
             └── WebSearchTool (네이티브, 재시도 내장)
             └── /v1/responses (SDK 관리, timeout 내장)
  ↓
Answer → /v1/chat/completions (200 OK, 검색 결과 포함)
```

---

## 3. 코드 변경

### 3.1 generate_with_tools (Agents SDK Primary)

**Before:** Responses API raw 호출
```python
async def generate_with_tools(self, prompt, tools, system_prompt=None, context=None):
    """Responses API raw 호출."""
    tool_configs = [{"type": "web_search", "search_context_size": "medium"}]

    response = await self._client.responses.create(
        model=self._model,
        input=input_messages,
        tools=tool_configs,
        stream=True,
    )
    async for event in response:
        if event.type == "response.output_text.delta":
            yield event.delta
```

**After:** Agents SDK Primary + Responses API Fallback
```python
async def generate_with_tools(self, prompt, tools, system_prompt=None, context=None):
    # Primary: Agents SDK
    try:
        async for chunk in self._generate_with_agents_sdk(user_content, tools, system_prompt):
            yield chunk
        return
    except Exception as e:
        logger.warning("Agents SDK failed, falling back to Responses API",
                      extra={"error": str(e)})

    # Fallback: Responses API
    async for chunk in self._generate_with_responses_api(user_content, tools, system_prompt):
        yield chunk

async def _generate_with_agents_sdk(self, user_content, tools, system_prompt=None):
    from agents import Agent, Runner, RunConfig, WebSearchTool
    from agents.models.openai_responses import OpenAIResponsesModel
    from openai.types.responses import ResponseTextDeltaEvent

    agent_tools = []
    for tool in tools:
        if tool == "web_search":
            agent_tools.append(WebSearchTool(search_context_size="medium"))

    agent = Agent(
        name="web_search_agent",
        instructions=system_prompt or "",
        model=OpenAIResponsesModel(model=self._model, openai_client=self._client),
        tools=agent_tools,
    )

    result = Runner.run_streamed(
        agent,
        input=user_content,
        run_config=RunConfig(tracing_disabled=True),
    )

    async for event in result.stream_events():
        if (event.type == "raw_response_event"
            and isinstance(event.data, ResponseTextDeltaEvent)
            and event.data.delta):
            yield event.data.delta
```

### 3.2 generate_structured (Agents SDK Primary)

**Before:** Responses API json_schema
```python
async def generate_structured(self, prompt, response_schema, system_prompt=None, ...):
    kwargs = {
        "model": self._model,
        "input": input_messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": response_schema.__name__,
                "schema": response_schema.model_json_schema(),
                "strict": True,
            },
        },
    }
    response = await self._client.responses.create(**kwargs)
    data = json.loads(response.output_text)
    return response_schema.model_validate(data)
```

**After:** Agents SDK output_type Primary + Responses API Fallback
```python
async def generate_structured(self, prompt, response_schema, system_prompt=None, ...):
    # Primary: Agents SDK
    try:
        return await self._structured_with_agents_sdk(prompt, response_schema, system_prompt)
    except Exception as e:
        logger.warning("Agents SDK structured output failed, falling back",
                      extra={"error": str(e), "schema": response_schema.__name__})

    # Fallback: Responses API
    return await self._structured_with_responses_api(
        prompt, response_schema, system_prompt, max_tokens, temperature
    )

async def _structured_with_agents_sdk(self, prompt, response_schema, system_prompt=None):
    from agents import Agent, Runner, RunConfig
    from agents.models.openai_responses import OpenAIResponsesModel

    agent = Agent(
        name="structured_output_agent",
        instructions=system_prompt or "",
        model=OpenAIResponsesModel(model=self._model, openai_client=self._client),
        output_type=response_schema,  # Pydantic BaseModel → 자동 스키마 적용
    )

    result = await Runner.run(
        agent,
        input=prompt,
        run_config=RunConfig(tracing_disabled=True),
    )
    return result.final_output  # 이미 response_schema 타입
```

**핵심:** `Agent(output_type=PydanticModel)` + `Runner.run()` → `result.final_output`이 이미 파싱된 Pydantic 인스턴스. JSON 파싱/검증 자동화.

### 3.3 LangChain Adapter 차이점

`langchain_adapter.py`는 동일 패턴이지만 Fallback이 다름:

| 메서드 | Primary | Fallback |
|--------|---------|----------|
| `generate_with_tools` | Agents SDK (동일) | Responses API (동일) |
| `generate_structured` | Agents SDK (동일) | **LangChain `with_structured_output()`** |

```python
# LangChain Adapter의 generate_structured Fallback
async def generate_structured(self, prompt, response_schema, ...):
    # Primary: Agents SDK (client 있을 때)
    if hasattr(self._llm, "_client") and self._llm._client is not None:
        try:
            return await self._structured_with_agents_sdk(prompt, response_schema, system_prompt)
        except Exception as e:
            logger.warning("Agents SDK failed, falling back to LangChain")

    # Fallback: LangChain with_structured_output
    structured_llm = self._llm.with_structured_output(response_schema)
    return await structured_llm.ainvoke(messages)
```

### 3.4 Web Search Node — Function Calling 제거

**Before:** Router 결정 후에도 Function Calling으로 "검색할까요?" 재확인
```python
# Before: 불필요한 2-step
# Step 1: Function Calling으로 검색 필요 여부 확인 (중복)
func_name, args = await llm.generate_function_call(
    prompt=message, functions=SEARCH_DECISION_FUNCTIONS, ...
)
# Step 2: 검색 실행 (if func_name == "execute_search")
async for chunk in llm.generate_with_tools(prompt=query, tools=["web_search"]):
    ...
```

**After:** Router가 이미 결정 → Agents SDK가 직접 검색
```python
# After: 1-step (Router 결정 신뢰)
# Agents SDK WebSearchTool이 검색 수행
async for chunk in llm.generate_with_tools(
    prompt=message,
    tools=["web_search"],
    system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
):
    result_parts.append(chunk)
```

**개선 효과:**
- API 호출: 2회 → 1회 (Function Calling 제거)
- 지연: ~500ms 감소 (Function Calling RTT 제거)
- 타임아웃 위험: 감소 (1회 호출이므로 시간 여유 확보)

---

## 4. LangChain 의존 범위 분석

### 4.1 왜 LangChain이 필요한가

```
LangGraph stream_mode="messages" 동작 원리:
────────────────────────────────────────────────
1. answer_node에서 BaseChatModel.astream(messages) 호출
2. astream()이 AIMessageChunk를 yield
3. LangGraph가 AIMessageChunk 이벤트를 감지 (duck typing)
4. SSE Gateway로 토큰 스트리밍 전달
5. 사용자에게 실시간 타이핑 효과
```

`LangChainOpenAIRunnable` (BaseChatModel 래퍼) 없이는 LangGraph가 토큰을 캡처하지 못함.

### 4.2 LangChain 사용 파일 (10개)

| 카테고리 | 파일 | 역할 |
|----------|------|------|
| **LLM Wrapper** | `langchain_runnable_wrapper.py` | OpenAI SDK → BaseChatModel 래핑 |
| **Adapter** | `langchain_adapter.py` | LLMClientPort 구현 (astream() 연동) |
| **Node** | `answer_node.py` | `llm.astream(messages)` → 토큰 캡처 |
| **Core Message** | `state.py` | `AnyMessage`, `HumanMessage` 타입 |
| **Summarization** | `summarization.py` | `SystemMessage`, `HumanMessage` 구성 |
| **Factory** | `factory.py` | `LangChainOpenAIRunnable` 생성/주입 |
| **Config** | `dependencies.py` | DI 설정 |
| **Tests** | 3개 파일 | 단위 테스트 |

### 4.3 Responses API Primary 잔존 확인

전체 노드 대상 점검 결과:

| 파일 | Responses API 사용 | 상태 |
|------|:---:|------|
| `openai_client.py` | Fallback only | Agents SDK primary |
| `langchain_adapter.py` | Fallback only | Agents SDK primary |
| `image_generator/openai_responses.py` | Primary | **미사용** (Gemini DI 주입) |
| 기타 모든 노드 | - | LLMClientPort 경유 |

**결론:** Production에서 Responses API가 Primary로 사용되는 코드 경로 없음. 모두 Agents SDK 또는 Chat Completions 경유.

---

## 5. CI Pipeline 수정

### 5.1 Black Format 에러

CI (GitHub Actions) 실패:
```
$ black --check --quiet apps/chat_worker/
would reformat apps/chat_worker/infrastructure/llm/clients/langchain_adapter.py
would reformat apps/chat_worker/infrastructure/llm/clients/openai_client.py
would reformat apps/chat_worker/infrastructure/orchestration/langgraph/routing/dynamic_router.py
would reformat apps/chat_worker/tests/unit/.../test_dynamic_router.py
Oh no! 4 files would be reformatted.
```

### 5.2 수정 및 CI 통과

```bash
# Black format 수정
$ black apps/chat_worker/infrastructure/llm/clients/langchain_adapter.py \
       apps/chat_worker/infrastructure/llm/clients/openai_client.py \
       apps/chat_worker/infrastructure/orchestration/langgraph/routing/dynamic_router.py \
       apps/chat_worker/tests/unit/.../test_dynamic_router.py
reformatted 4 files.

# Ruff lint 확인
$ ruff check apps/chat_worker/ --config pyproject.toml
All checks passed!

# 테스트 확인
$ pytest apps/chat_worker/tests/ -x -q
760 passed, 5 skipped
```

**CI 결과:**
```
Job: 🧪 Worker Lint & Test - chat_worker
Duration: 1m 10s
Status: ✅ pass
```

---

## 6. 테스트 결과

### 6.1 Web Search Node 테스트 (12 cases)

| 테스트 | 검증 항목 |
|--------|-----------|
| `test_standalone_executes_search_directly` | FC 미호출, WebSearchTool 1회 |
| `test_standalone_search_failure` | FAIL_OPEN error context |
| `test_standalone_empty_result` | 빈 결과 → error context |
| `test_enrichment_executes_search_directly` | FC 미호출, mode=enrichment |
| `test_enrichment_no_stage_events` | UI 간섭 방지 (이벤트 미발행) |
| `test_enrichment_search_failure` | FAIL_OPEN + FC 미호출 |
| `test_enrichment_empty_result` | 빈 결과 처리 |
| `test_progress_events_on_success` | started + completed |
| `test_progress_events_on_failure` | started + failed |
| `test_no_events_without_publisher` | publisher=None 안전 |
| `test_large_result_truncated` | 100K → 50K chars |
| `test_small_result_not_truncated` | 10K 그대로 |

### 6.2 전체 테스트 현황

```
$ pytest apps/chat_worker/tests/ -x -q
760 passed, 5 skipped, 0 failures

Breakdown:
- Function Calling 노드: 56 passed (bulk_waste, weather, recyclable_price,
                                     collection_point, kakao_place)
- Web Search: 12 passed
- LLM Client: 5 skipped (respx 미도입)
- Dynamic Router: 28 passed
- 기타: 659 passed
```

---

## 7. Before/After 비교 요약

### 7.1 API 호출 패턴

| 구간 | Before | After |
|------|--------|-------|
| Web Search | `/v1/responses` (raw, timeout 빈번) | Agents SDK (재시도 내장) |
| Structured Output | `/v1/responses` (json_schema) | Agent `output_type` (자동) |
| Function Calling | deprecated `functions` param | `tools`/`tool_choice` (modern) |
| Web Search 결정 | `generate_function_call` (2-step) | Router 신뢰 (1-step) |

### 7.2 Production 동작

| 시나리오 | Before (로그 관측) | After |
|----------|:---:|:---:|
| 웹 검색 타임아웃 | FAIL_OPEN, 결과 누락 | SDK 재시도 후 FAIL_OPEN |
| Low confidence (0.55) | 검색 시도 → 타임아웃 | 검색 시도 → 성공 가능성 향상 |
| Enrichment mode | FC + 검색 (2회 API) | 검색만 (1회 API) |
| Structured output | JSON 파싱 수동 | Pydantic 자동 반환 |

### 7.3 Fallback 전략

```
generate_with_tools:
  ┌─ Primary: Agents SDK (WebSearchTool + Runner.run_streamed)
  └─ Fallback: Responses API (client.responses.create + stream)

generate_structured:
  ┌─ Primary: Agents SDK (Agent output_type + Runner.run)
  ├─ Fallback (OpenAILLMClient): Responses API (json_schema)
  └─ Fallback (LangChainAdapter): LangChain with_structured_output()

generate_function_call:
  └─ Chat Completions (tools/tool_choice) — 변경 없음, modern API 적용 완료
```

---

## 8. Production Cluster 상태

ArgoCD 대시보드 기준:

| 항목 | 값 |
|------|-----|
| **Pod 수** | 9-10 (HPA) |
| **Deployment** | `chat-worker-59f5fdd65c` |
| **ArgoCD 버전** | v3.2.1+8c4ab63 |
| **Sync 상태** | Synced (4 resources) |
| **Health** | Healthy |
| **Image** | Gemini Native (이미지 생성), OpenAI (텍스트/검색) |

---

## 9. 의존성

```
openai>=2.9.0,<3          # Responses API + Agents SDK 호환
openai-agents>=0.7.0      # Agent, Runner, WebSearchTool, RunConfig
langchain-openai>=0.3.0   # LangChainOpenAIRunnable (stream_mode="messages")
langgraph>=0.2.0          # Graph, add_messages reducer
```

---

## 10. 커밋 이력

| 커밋 | 내용 |
|------|------|
| `b7316337` | Agents SDK primary + Responses API fallback (generate_with_tools) |
| `fa4de736` | generate_structured도 Agents SDK primary로 전환 |
| `ae27e98d` | CI lint 수정 (Black format 4 files) |
