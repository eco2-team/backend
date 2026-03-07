# OpenAI Python SDK Version Compatibility Guide

## SDK Version Timeline

| Version | Release Date | Milestone |
|---------|-------------|-----------|
| `1.0.0` | 2023-11 | Chat Completions API (v1 rewrite) |
| `1.66.0` | 2025-03-11 | **Responses API + Built-in Tools 도입** |
| `2.0.0` | 2025-09-30 | Breaking: `output` type 변경 |
| `2.7.2` | 2025-11-10 | Python 3.8 지원 중단 |
| `2.9.0` | 2025-12-04 | **Agents SDK 호환 최소 버전** |
| `2.11.0` | 2025-12-11 | GPT-5.2 지원 |
| `2.15.0` | 2026-01-09 | Latest stable |

---

## API Capability Matrix

| 기능 | Chat Completions | Responses API | Agents SDK |
|------|:---:|:---:|:---:|
| **Endpoint** | `/v1/chat/completions` | `/v1/responses` | Responses (default) |
| **최소 SDK 버전** | `>=1.0.0` | `>=1.66.0` | `>=2.9.0` |
| **텍스트 생성** | O | O | O |
| **스트리밍** | O | O | O |
| **Function Calling** | O | O | O |
| **Vision (이미지 입력)** | O | O | O |
| **Structured Output** | O | O | O |
| **Web Search** | X | O (`web_search_preview`) | O (`WebSearchTool`) |
| **File Search** | X | O (`file_search`) | O (`FileSearchTool`) |
| **Code Interpreter** | X | O (`code_interpreter`) | O (`CodeInterpreterTool`) |
| **Computer Use** | X | O (`computer_use_preview`) | O (local runtime) |
| **Image Generation** | X | O (`image_generation`) | O (`ImageGenerationTool`) |
| **MCP (Remote Tools)** | X | O (`mcp`) | O (`HostedMCPTool`) |
| **Multi-Agent** | X | X | O (Handoff/Manager) |
| **Guardrails** | X | X | O (Input/Output) |
| **Tracing** | X | X | O (Built-in) |
| **Multi-turn (stateful)** | 수동 관리 | `previous_response_id` | 자동 관리 |
| **Reasoning (o-series)** | O | O | O |

---

## 1. Chat Completions API

### 개요
- **Endpoint:** `POST /v1/chat/completions`
- **SDK:** `client.chat.completions.create(...)`
- **역할:** 범용 텍스트 생성 (대화, 분류, 요약 등)

### 지원 기능
- Streaming (`stream=True`)
- Function Calling / Tool Calls (`tools=[...]`)
- Vision (`{"type": "image_url", ...}`)
- Structured Output (`response_format={"type": "json_schema", ...}`)
- Logprobs, Seed, Stop sequences

### 한계
- Built-in tools 없음 (web search, file search 등 직접 구현 필요)
- Multi-turn 상태 관리 직접 구현 필요 (messages 배열 수동 관리)
- 외부 도구 호출 시 Function Calling → 결과 재전송 루프 직접 구현

### 사용 예시
```python
from openai import AsyncOpenAI

client = AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-5.2",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True,
)
```

---

## 2. Responses API

### 개요
- **Endpoint:** `POST /v1/responses`
- **SDK:** `client.responses.create(...)`
- **도입:** `openai>=1.66.0` (2025-03-11)
- **역할:** Built-in tools + Multi-turn 지원

### Built-in Tools

| Tool Type | 설명 | 주요 파라미터 |
|-----------|------|--------------|
| `web_search_preview` | 실시간 웹 검색 | `search_context_size`: low/medium/high |
| `file_search` | Vector Store 검색 | `vector_store_ids`, `max_num_results` |
| `code_interpreter` | 코드 실행 (샌드박스) | `container` |
| `computer_use_preview` | 컴퓨터 조작 | `display_width`, `display_height` |
| `image_generation` | 이미지 생성 | `quality`, `size` |
| `mcp` | Remote MCP 서버 도구 | `server_label`, `server_url` |

### Chat Completions 대비 차이점
- 도구 호출 → 결과 수신 루프를 **서버가 자동 처리**
- `previous_response_id`로 Multi-turn 상태 서버 관리
- `input` (Responses) vs `messages` (Chat Completions)
- `"role": "developer"` (Responses) vs `"role": "system"` (Chat Completions)

### 사용 예시
```python
response = await client.responses.create(
    model="gpt-5.2",
    input=[{"role": "user", "content": "최신 환경 정책 알려줘"}],
    tools=[{
        "type": "web_search_preview",
        "search_context_size": "medium",
    }],
    stream=True,
)
```

---

## 3. Agents SDK (`openai-agents`)

### 개요
- **패키지:** `pip install openai-agents`
- **최신 버전:** `0.7.0` (2026-01-23)
- **요구사항:** `openai>=2.9.0,<3`, Python `>=3.9`
- **역할:** Multi-agent orchestration framework

### 핵심 컴포넌트

| 컴포넌트 | 설명 |
|----------|------|
| `Agent` | LLM + instructions + tools 조합 |
| `Runner` | Agent 실행 엔진 (동기/비동기/스트리밍) |
| `Handoff` | Agent 간 제어권 전환 |
| `Guardrail` | Input/Output 검증 |
| `Tracing` | 실행 추적 (OpenAI Dashboard 연동) |

### Model Provider

| Provider | 클래스 | API |
|----------|--------|-----|
| OpenAI (default) | `OpenAIResponsesModel` | Responses API |
| OpenAI (legacy) | `OpenAIChatCompletionsModel` | Chat Completions |
| 기타 (100+) | LiteLLM integration | Chat Completions |

### Hosted Tools (Responses API 전용)

```python
from agents import Agent, WebSearchTool, FileSearchTool

agent = Agent(
    name="research_agent",
    instructions="최신 정보를 검색하여 답변합니다.",
    model="gpt-5.2",
    tools=[
        WebSearchTool(search_context_size="medium"),
        FileSearchTool(vector_store_ids=["vs_xxx"]),
    ],
)
```

### Multi-Agent 패턴

```python
# Manager Pattern
manager = Agent(
    name="manager",
    instructions="적절한 전문 에이전트에게 위임합니다.",
    tools=[search_agent.as_tool(), analysis_agent.as_tool()],
)

# Handoff Pattern
triage = Agent(
    name="triage",
    handoffs=[search_agent, analysis_agent],
)
```

---

## Version Constraint 결정 기준

### 현재 프로젝트 요구사항

| 사용 기능 | 필요 최소 버전 |
|-----------|---------------|
| Chat Completions (의도 분류, 답변 생성) | `>=1.0.0` |
| Responses API (웹 검색) | `>=1.66.0` |
| GPT-5.2 모델 지원 | `>=2.11.0` |
| Agents SDK 호환 | `>=2.9.0` |
| **종합** | **`>=2.9.0,<3`** |

### Breaking Change (v2.0.0)

`ResponseFunctionToolCallOutputItem.output` 타입이 `string` → `string | Array<...>`로 변경.
현재 코드베이스에서 이 타입을 직접 참조하지 않으므로 영향 없음.

---

## 공식 문서

- [Chat Completions API](https://platform.openai.com/docs/guides/chat-completions)
- [Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Responses vs Chat Completions 마이그레이션](https://platform.openai.com/docs/guides/migrate-to-responses)
- [Web Search Tool](https://platform.openai.com/docs/guides/tools-web-search)
- [Agents SDK 문서](https://openai.github.io/openai-agents-python/)
- [Agents SDK GitHub](https://github.com/openai/openai-agents-python)
- [Agents SDK PyPI](https://pypi.org/project/openai-agents/)
- [openai-python CHANGELOG](https://github.com/openai/openai-python/blob/main/CHANGELOG.md)
