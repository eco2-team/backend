# OpenAI Agents SDK Migration

> **Scan**: `openai>=1.10.0` — Chat Completions API (`/v1/chat/completions`) + `responses.parse()`
> **Chat (Gateway)**: `openai>=1.58.0` — Chat Completions API
> **Chat Worker (Before)**: `openai>=1.66.0` — Responses API (`/v1/responses`) raw 호출
> **Chat Worker (After)**: `openai>=2.9.0,<3` + `openai-agents>=0.7.0` — Agents SDK Primary, Function Calling Fallback

| 항목      | 값            |
| ------- | ------------ |
| **작성일** | 2026-01-24   |
| **범위**  | chat_worker 전체 서브에이전트 노드 (6개) |

---

## 1. 배경: 왜 마이그레이션이 필요했는가

### 1.1 기존 문제

```
web_search_node → llm.generate_with_tools(tools=["web_search"])
    ↓ llm = LangChainLLMAdapter (프로덕션, enable_token_streaming=True)
    ↓ LangChainLLMAdapter에 generate_with_tools() 없었음
    ↓ LLMClientPort 기본 구현 → generate_stream() 호출 (tools 무시)
    ↓ /v1/chat/completions (도구 없음)
    ↓ 모델: "웹 검색을 할 수 없습니다"
```

**근본 원인:** Responses API를 raw `client.responses.create()`로 직접 호출하면:
- OpenAI SDK 버전 의존성이 높아짐 (internal API 변경 시 깨짐)
- 도구 스키마를 수동으로 관리해야 함
- 에러 핸들링/재시도가 모두 자체 구현

### 1.2 OpenAI Agents SDK의 위치

```
┌──────────────────────────────────────────────────┐
│              Application Code                     │
│                                                   │
│  ┌────────────────────────────────────────────┐  │
│  │           Agents SDK (openai-agents)        │  │  ← 여기로 마이그레이션
│  │  - Agent, Runner, WebSearchTool            │  │
│  │  - @function_tool, RunContext              │  │
│  ├────────────────────────────────────────────┤  │
│  │           Responses API (raw)              │  │  ← Fallback으로 유지
│  │  - client.responses.create()               │  │
│  ├────────────────────────────────────────────┤  │
│  │         Chat Completions API               │  │  ← 다른 노드 (answer, etc.)
│  │  - client.chat.completions.create()        │  │
│  └────────────────────────────────────────────┘  │
│                                                   │
│  ┌────────────────────────────────────────────┐  │
│  │           OpenAI Python SDK (openai)        │  │
│  │  - httpx client, retry, auth               │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 2. 의사결정 과정

### 2.1 선택지 비교

| 방안 | 장점 | 단점 |
|------|------|------|
| A. Responses API raw 유지 | 변경 최소 | SDK 버전 취약, 수동 스키마 관리 |
| B. **Agents SDK Primary + FC Fallback** | 네이티브 도구, 자동 스키마, 확장성 | 새 의존성 추가 |
| C. Agents SDK Only | 가장 깔끔 | Fallback 없음, 장애 시 전면 실패 |

**결정: 방안 B** — Agents SDK를 Primary로 사용하되, `openai-agents` 패키지 미설치 환경이나 런타임 에러 시 Responses API (Function Calling)로 Fallback.

### 2.2 Fallback 전략의 핵심 결정

```python
_yielded = False
try:
    # === PRIMARY: Agents SDK ===
    result = Runner.run_streamed(agent, input=user_content)
    async for event in result.stream_events():
        if event.data.delta:
            _yielded = True
            yield event.data.delta
    return  # 성공 시 여기서 종료

except ImportError:
    logger.warning("openai-agents not installed, falling back")

except Exception as e:
    if _yielded:
        raise  # 이미 부분 데이터 전송 → 복구 불가
    logger.warning("Agents SDK failed, falling back")

# === FALLBACK: Function Calling (Responses API) ===
async for token in self._responses_api_fallback(...):
    yield token
```

**핵심:** `_yielded` 플래그로 스트리밍 데이터 무결성 보장. 부분 전송 후 Fallback 시 중복 데이터 방지.

### 2.3 Strict Mode 결정

OpenAI Function Calling의 `"strict": true` 사용 결정:
- 모든 프로퍼티가 `required`에 포함되어야 함
- Optional 파라미터는 `anyOf: [{type: T}, {type: null}]` 패턴 사용
- 모델이 null을 명시적으로 전송 → 코드에서 `args.get("key") or default` 패턴으로 처리

---

## 3. 전체 노드 현황 및 마이그레이션 범위

| 노드 | 유형 | 마이그레이션 |
|------|------|:---:|
| `web_search_agent_node` | Hosted tool (`WebSearchTool`) | Done |
| `bulk_waste_agent_node` | `@function_tool` (`search_disposal_info`) | Done |
| `weather_agent_node` | `@function_tool` (`get_weather_info`) | Done |
| `recyclable_price_agent_node` | `@function_tool` (`get_price_trend`, `get_latest_prices`) | Done |
| `location_agent_node` | `@function_tool` (`search_places`, `search_category`) | Done |
| `collection_point_agent_node` | `@function_tool` (`search_collection_points`, `get_nearby_collection_points`) | Done |
| `kakao_place_node` | `generate_function_call()` (파라미터 추출) | 대상 제외 |
| `image_generation_node` | Responses API (이미지 생성) | 대상 아님 |
| `character_node` | gRPC 호출 (LLM 도구 없음) | 대상 아님 |
| `answer_node` | 텍스트 생성 (도구 없음) | 대상 아님 |
| `intent_node` | 분류 (도구 없음) | 대상 아님 |
| `vision_node` | 이미지 입력 (도구 없음) | 대상 아님 |

**제외 사유:**
- `kakao_place_node`: 단순 파라미터 추출용 Function Calling, 도구 실행 루프 불필요
- `image_generation_node`: Responses API의 `image_generation` built-in tool 사용 (Agent SDK `ImageGenerationTool`로 전환 가능하나 현재 안정적)
- 나머지: LLM 도구 호출 자체가 없는 노드

---

## 4. 코드 패턴

### 4.1 노드 구조 (Before → After)

**Before:** Responses API raw 호출
```python
async def _execute(self, state, config):
    result = await self._llm.generate_with_tools(
        prompt=query,
        tools=["web_search"],
        system_prompt=system_prompt,
    )
    # generate_with_tools()가 LLMClientPort에 없어서 실패
```

**After:** Agent SDK Primary + Function Calling Fallback
```python
# 1. Context 정의
class WeatherAgentContext:
    grpc_client: LocationServiceClient
    latitude: float
    longitude: float

# 2. @function_tool 정의 (strict_mode=True 자동)
@function_tool
async def get_weather_info(
    ctx: RunContextWrapper[WeatherAgentContext],
    latitude: float,
    longitude: float,
    waste_category: str | None = None,    # nullable → strict 호환
) -> str:
    ...

# 3. Agent 생성 + Runner 실행
agent = Agent(
    name="weather_agent",
    instructions=system_prompt,
    model=OpenAIResponsesModel(model=model_name, openai_client=client),
    tools=[get_weather_info],
)
result = await Runner.run(agent, input=query, context=ctx, max_turns=10)
```

### 4.2 Fallback Function Calling 패턴

```python
OPENAI_TOOLS = [{
    "type": "function",
    "name": "get_weather_info",
    "description": "...",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "waste_category": {
                "anyOf": [{"type": "string"}, {"type": "null"}],  # nullable
                "description": "...",
            },
        },
        "required": ["latitude", "longitude", "waste_category"],  # ALL required
        "additionalProperties": False,
    },
    "strict": True,
}]
```

### 4.3 Tool Executor (Fallback 실행기)

```python
async def _execute_tool(self, tool_name, args, context):
    if tool_name == "get_weather_info":
        lat = args.get("latitude") or context.latitude
        lon = args.get("longitude") or context.longitude
        waste_cat = args.get("waste_category")  # None 가능 (nullable)
        return await self._call_weather_api(lat, lon, waste_cat)
```

### 4.4 LLM Client (langchain_adapter / openai_client)

```python
async def generate_with_tools(self, prompt, tools, system_prompt, context):
    from agents import Agent, Runner, WebSearchTool, OpenAIResponsesModel

    agent_tools = []
    for tool in tools:
        if tool == "web_search":
            agent_tools.append(WebSearchTool(search_context_size="medium"))

    agent = Agent(
        name="web_search_agent",
        instructions=system_prompt or "",
        model=OpenAIResponsesModel(model=model_name, openai_client=client),
        tools=agent_tools,
    )

    _yielded = False
    try:
        result = Runner.run_streamed(agent, input=user_content)
        async for event in result.stream_events():
            if (event.type == "raw_response_event"
                and isinstance(event.data, ResponseTextDeltaEvent)):
                if event.data.delta:
                    _yielded = True
                    yield event.data.delta
        return
    except ImportError:
        ...  # Fallback
    except Exception as e:
        if _yielded:
            raise
        ...  # Fallback to Responses API
```

---

## 5. 코드 리뷰 결과

마이그레이션 완료 후 공식 문서 기반 코드 리뷰에서 5개 이슈 발견 및 수정:

### 5.1 [CRITICAL] Strict Mode Schema 위반

**문제:** `"strict": True`인데 optional 파라미터가 `required`에 누락
```python
# BEFORE (위반)
"properties": {"region": {"type": "string"}},
"required": ["item_name"],  # region 누락 → API 거부
```

**수정:** 모든 프로퍼티 required + nullable 패턴
```python
# AFTER (준수)
"properties": {"region": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
"required": ["item_name", "region"],  # 모두 포함
```

**영향 파일:** weather, recyclable_price, location, collection_point 노드

### 5.2 [HIGH] 스트리밍 Fallback 데이터 중복

**문제:** 부분 스트리밍 후 에러 → Fallback → 동일 내용 재전송
```python
# BEFORE
try:
    async for event in result.stream_events():
        yield event.data.delta  # 일부 전송됨
except Exception:
    # Fallback 실행 → 처음부터 다시 전송 (중복!)
    async for token in self._fallback(...):
        yield token
```

**수정:** `_yielded` 플래그로 부분 전송 감지 시 raise
```python
# AFTER
if _yielded:
    raise  # 부분 데이터 전송됨, 복구 불가
```

### 5.3 [LOW] @function_tool Default 값 처리

**문제:** `str = ""` 또는 `float = 5000` → strict mode에서 default 무시됨, 모델은 빈 문자열이나 숫자를 전송

**수정:** `str | None = None` + 로직에서 `or default` 처리
```python
# BEFORE
async def search_places(query: str, radius: int = 5000): ...

# AFTER
async def search_places(query: str, radius: int | None = None):
    effective_radius = min(radius or 5000, 20000)
```

### 5.4 [LOW] Import 경로 비표준

**문제:** `from agents.models.openai_responses import OpenAIResponsesModel`

**수정:** `from agents import OpenAIResponsesModel` (공식 top-level export)

### 5.5 [LOW] max_turns 미지정

**문제:** `Runner.run()` 기본 max_turns가 높아 무한 루프 가능

**수정:** 모든 Runner 호출에 `max_turns=10` 명시

### 5.6 [HIGH] Agents SDK Tracing 미비활성화

**문제:** `Runner.run_streamed()` 호출 시 tracing이 기본 활성화되어 OpenAI 대시보드로 데이터 전송 시도 → 프로덕션 환경에서 불필요한 외부 통신 및 잠재적 지연

**수정:** `RunConfig(tracing_disabled=True)` 적용
```python
# BEFORE
result = Runner.run_streamed(agent, input=user_content)

# AFTER
from agents import RunConfig
run_config = RunConfig(tracing_disabled=True)
result = Runner.run_streamed(agent, input=user_content, run_config=run_config)
```

**영향 파일:** `langchain_adapter.py`, `openai_client.py`

### 5.7 [HIGH] generate_function_call() Deprecated API 사용

**문제:** `generate_function_call()`이 deprecated `functions`/`function_call` API 파라미터 사용 중. `openai>=2.0.0`부터 `tools`/`tool_choice`가 표준이며 deprecated params는 향후 제거 예정.

**호출 노드:** weather, recyclable_price, kakao_place, bulk_waste, collection_point (모두 forced call 패턴)

**수정:** Port 인터페이스 시그니처 유지, 구현체에서 modern API로 변환
```python
# BEFORE (deprecated)
response = await self._client.chat.completions.create(
    model=self._model,
    messages=messages,
    functions=functions,        # deprecated
    function_call=function_call,  # deprecated
)
if hasattr(message, "function_call") and message.function_call:
    func_name = message.function_call.name

# AFTER (modern)
tools = [{"type": "function", "function": func} for func in functions]
tool_choice = {"type": "function", "function": {"name": function_call["name"]}}

response = await self._client.chat.completions.create(
    model=self._model,
    messages=messages,
    tools=tools,
    tool_choice=tool_choice,
)
if message.tool_calls:
    func_name = message.tool_calls[0].function.name
```

**영향 파일:** `openai_client.py`

---

## 6. 이점

### 6.1 기능적 이점

| 항목 | Before (Responses API raw) | After (Agents SDK) |
|------|:---:|:---:|
| Web Search | `client.responses.create()` 수동 | `WebSearchTool()` 네이티브 |
| 도구 스키마 관리 | JSON 수동 작성 | `@function_tool` 자동 생성 |
| 도구 호출 루프 | 수동 while 루프 | `Runner.run()` 내장 |
| 에러 핸들링 | 자체 try/except | SDK 내장 재시도 |
| 스트리밍 | `stream=True` 파싱 | `stream_events()` 이벤트 |
| 타입 안전성 | dict 기반 | `RunContextWrapper[T]` 제네릭 |
| 확장성 | 도구 추가 시 대규모 변경 | `tools=[...]` 리스트에 추가 |

### 6.2 아키텍처 이점

1. **Fallback 안전성**: Agents SDK 장애 시에도 Function Calling으로 서비스 지속
2. **테스트 용이성**: `@function_tool` 함수는 단독 단위 테스트 가능
3. **모델 독립성**: `OpenAIResponsesModel(model=...)` 변경만으로 모델 교체
4. **Observability**: Agents SDK 내장 tracing → LangSmith/OTEL 연동 가능

### 6.3 운영 이점

- **SDK 업그레이드 안전**: `openai-agents`가 내부 API 차이를 흡수
- **스키마 검증**: strict mode로 잘못된 도구 호출 원천 차단
- **디버깅**: `Runner.run()` 결과에 전체 호출 히스토리 포함

---

## 7. 확장 가능 지점

### 7.1 Multi-Agent (Handoff)

```python
# 현재: 단일 Agent per 노드
agent = Agent(name="weather_agent", tools=[get_weather_info])

# 확장: Agent 간 위임
triage_agent = Agent(
    name="triage",
    handoffs=[weather_agent, location_agent, bulk_waste_agent],
)
```

### 7.2 Guardrails (Input/Output 검증)

```python
from agents import InputGuardrail, OutputGuardrail

agent = Agent(
    name="weather_agent",
    input_guardrails=[InputGuardrail(guardrail_function=check_pii)],
    output_guardrails=[OutputGuardrail(guardrail_function=check_hallucination)],
)
```

### 7.3 추가 Hosted Tools

```python
from agents import FileSearchTool, CodeInterpreterTool, HostedMCPTool

agent = Agent(
    tools=[
        WebSearchTool(),
        FileSearchTool(vector_store_ids=["vs_xxx"]),
        CodeInterpreterTool(),
        HostedMCPTool(server_url="https://mcp.example.com"),
    ],
)
```

### 7.4 Tracing 통합

```python
from agents import set_tracing_export_api_key, enable_verbose_stdout_logging

set_tracing_export_api_key("ls_xxx")  # LangSmith로 trace 전송
```

---

## 8. 수정 파일 목록

| 파일 | 변경 요약 |
|------|-----------|
| `requirements.txt` | `openai>=2.9.0,<3`, `openai-agents>=0.7.0` 추가 |
| `infrastructure/llm/clients/langchain_adapter.py` | `generate_with_tools()` Agent SDK 구현 + `_yielded` 안전장치 + tracing disable |
| `infrastructure/llm/clients/openai_client.py` | `generate_with_tools()` Agent SDK + tracing disable, `generate_function_call()` → `tools`/`tool_choice` 마이그레이션 |
| `infrastructure/orchestration/langgraph/nodes/web_search_agent_node.py` | Agent SDK primary 구조 |
| `infrastructure/orchestration/langgraph/nodes/bulk_waste_agent_node.py` | `@function_tool` + strict FC fallback |
| `infrastructure/orchestration/langgraph/nodes/weather_agent_node.py` | nullable 파라미터 + `max_turns=10` |
| `infrastructure/orchestration/langgraph/nodes/recyclable_price_agent_node.py` | 2개 도구, nullable region |
| `infrastructure/orchestration/langgraph/nodes/location_agent_node.py` | nullable lat/lon/radius + `is not None` 검사 |
| `infrastructure/orchestration/langgraph/nodes/collection_point_agent_node.py` | nullable keywords/radius |

---

## 9. 테스트 결과

```
tests/unit/.../test_bulk_waste_function_calling.py          18 passed
tests/unit/.../test_weather_function_calling.py             10 passed
tests/unit/.../test_recyclable_price_function_calling.py    15 passed
tests/unit/.../test_collection_point_function_calling.py    13 passed
tests/unit/.../test_kakao_place_function_calling.py         13 passed (*)
tests/unit/.../test_web_search_node.py                      12 passed
tests/unit/infrastructure/llm/test_openai_client_function_calling.py  5 skipped (respx 미도입)
──────────────────────────────────────────────────────────────
Function Calling 노드: 56 passed, 5 skipped
전체 유닛 테스트: 757 passed, 5 skipped, 0 failures

(*) kakao_place, collection_point 노드도 Port 인터페이스를 통해 호출하므로
    openai_client.py 내부 변경에 영향 없음 — 테스트 통과 확인
```

---

## 10. 의존성 요약

```
openai>=2.9.0,<3          # Responses API + Agents SDK 호환 최소 버전
openai-agents>=0.7.0      # Agents SDK (WebSearchTool, @function_tool, Runner)
```

**호환성 매트릭스:**

| Python | openai | openai-agents | 상태 |
|--------|--------|---------------|:---:|
| 3.10+  | 2.9.0+ | 0.7.0+        | Supported |
| 3.9    | 2.9.0+ | 0.7.0+        | Untested |
| < 3.9  | -      | -             | Not supported |
