# Token Streaming 트러블슈팅 리포트

> **검증 일시**: 2026-01-19 12:30 UTC
> **검증 환경**: k8s-master (13.209.44.249)
> **검증 결과**: ❌ **토큰 스트리밍 미작동**

---

## 1. 문제 요약

### 1.1 증상

SSE 엔드포인트에서 **토큰 이벤트(`stage: "token"`)가 수신되지 않음**.
답변이 `done` 이벤트의 `result.answer`에 **전체 텍스트로 한 번에** 전달됨.

### 1.2 테스트 세션

| 항목 | 값 |
|------|-----|
| Session ID | `f8d57c29-b802-4cc4-aad1-fb4bf9b946e5` |
| Job ID | `444f81d5-8826-4a5d-978c-ebbb5e125f05` |
| Message | "페트병 어떻게 버려?" |

### 1.3 수신된 SSE 이벤트

```
queued (started) → intent (waste) → waste_rag → weather → aggregator → answer → done
```

**기대**: `answer` 이후 다수의 `token` 이벤트
**실제**: `token` 이벤트 0개

---

## 2. 근본 원인 분석

### 2.1 아키텍처 검토

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Token Streaming Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ProcessChatCommand._execute_streaming()                                     │
│  │                                                                           │
│  ├── pipeline.astream_events(version="v2")                                  │
│  │       │                                                                   │
│  │       ├── on_chain_start → _handle_chain_start() → notify_stage()       │
│  │       ├── on_chain_end   → _handle_chain_end()   → notify_stage()       │
│  │       └── on_llm_stream  → _handle_llm_stream()  → notify_token_v2() ❌  │
│  │                                                                           │
│  └── answer_node()                                                          │
│          │                                                                   │
│          └── GenerateAnswerCommand.execute()                                │
│                  │                                                           │
│                  └── OpenAILLMClient.generate_stream() ← 여기서 토큰 발생   │
│                          │                                                   │
│                          └── OpenAI SDK (stream=True)                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 문제

**LangGraph의 `on_llm_stream` 이벤트는 LangChain LLM 호출에서만 발생**.

현재 구현:
- `OpenAILLMClient`는 **순수 OpenAI SDK** 사용 (`AsyncOpenAI`)
- LangChain의 `ChatOpenAI`가 아님
- LangGraph가 LLM 호출을 감지하지 못함

### 2.3 코드 경로 분석

#### `process_chat.py:393-394`
```python
elif event_type == "on_llm_stream":
    await self._handle_llm_stream(event, job_id)  # 호출되지 않음
```

#### `openai_client.py:118-126`
```python
stream = await self._client.chat.completions.create(
    model=self._model,
    messages=messages,
    stream=True,  # OpenAI SDK 스트리밍
)

async for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        yield chunk.choices[0].delta.content  # 토큰 yield
```

**문제**: 토큰은 `yield`되지만 LangGraph의 `astream_events`에서 감지되지 않음.

### 2.4 chat-worker 로그 증거

```log
[03:23:47] Executing task chat.process with ID: 444f81d5-...
[03:23:47] Chat task received
[03:23:47] OpenAILLMClient initialized
[03:23:47] Built multi-intent prompt for intents=['waste']
[03:23:48] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
[03:23:56] Answer generated  ← 8초 후 전체 답변 완성
[03:23:56] ProcessChatCommand completed
```

**`on_llm_stream`, `token`, `notify_token_v2` 관련 로그 없음**.

---

## 3. 영향 범위

| 기능 | 상태 | 설명 |
|------|------|------|
| Stage 이벤트 | ✅ 정상 | queued, intent, answer, done 등 |
| 토큰 스트리밍 | ❌ 미작동 | `on_llm_stream` 이벤트 미발생 |
| 최종 답변 | ✅ 정상 | `done` 이벤트에 전체 답변 포함 |
| 멀티턴 맥락 | ✅ 정상 | 체크포인터 정상 작동 |

**사용자 체감**: 답변이 토큰 단위로 스트리밍되지 않고, 전체 답변이 한 번에 표시됨.

---

## 4. 해결 방안

### 4.1 방안 A: stream_mode="messages" 사용 (권장) ⭐

LangGraph 1.0+에서 권장하는 **네이티브 메시지 스트리밍** 방식.

> 참고: https://docs.langchain.com/oss/python/langgraph/streaming#messages

```python
# 변경 전 (현재) - astream_events 사용
async for event in pipeline.astream_events(state, config=config, version="v2"):
    if event.get("event") == "on_llm_stream":
        # LangChain LLM이 아니면 이벤트 미발생 ❌
        await self._handle_llm_stream(event, job_id)

# 변경 후 (권장) - stream_mode="messages" 사용
async for chunk, metadata in pipeline.astream(
    state,
    config=config,
    stream_mode="messages"
):
    # 모든 LLM 호출의 토큰이 자동 캡처 ✅
    if chunk.content:
        await progress_notifier.notify_token_v2(
            task_id=job_id,
            content=chunk.content,
            node=metadata.get("langgraph_node", ""),
        )
```

**장점**:
- LangGraph 네이티브 기능, LangChain LLM 불필요
- 기존 `OpenAILLMClient` (순수 SDK) 유지 가능
- 노드, 서브그래프, 도구 내 어디서든 LLM 토큰 캡처
- `.invoke()` 사용 시에도 메시지 이벤트 발생

**단점**:
- `astream_events` 기반 stage 이벤트 로직 재구성 필요

**핵심 변경점**:
- `_execute_streaming()` 메서드에서 `astream_events` → `astream(stream_mode=["messages", "updates"])` 변경
- `on_chain_start/end` 이벤트는 `stream_mode="updates"`로 처리

### 4.2 방안 B: LangChain LLM 사용

`OpenAILLMClient` 대신 LangChain의 `ChatOpenAI` 사용.

```python
# 변경 후
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o", streaming=True)
# LangGraph astream_events가 on_llm_stream 이벤트 자동 캡처
```

**장점**: 기존 `astream_events` 코드 유지
**단점**: `langchain-openai` 의존성 추가, LLM 클라이언트 교체 필요

### 4.3 방안 C: 노드 내부에서 직접 토큰 발행

`answer_node`에서 직접 `notify_token_v2` 호출.

```python
async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
    async for token in command.execute(input_dto):
        await progress_notifier.notify_token_v2(task_id=job_id, content=token)
```

**장점**: 변경 최소화
**단점**: 노드에 ProgressNotifier 의존성 추가, Clean Architecture 위반

---

## 5. 권장 사항

### 5.1 선택: 방안 A (stream_mode="messages")

**이유**:
1. LangGraph 1.0+ 공식 권장 방식
2. 기존 LLM 클라이언트 (OpenAI SDK) 유지 가능
3. 추가 의존성 없음
4. 향후 LangGraph 업데이트와 호환성 보장

### 5.2 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `process_chat.py` | `_execute_streaming()` 메서드 재구성 |
| `process_chat.py` | `stream_mode=["messages", "updates"]` 사용 |

### 5.3 구현 전략

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    stream_mode="messages" 아키텍처                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ProcessChatCommand._execute_streaming()                                     │
│  │                                                                           │
│  └── pipeline.astream(state, stream_mode=["messages", "updates"])           │
│          │                                                                   │
│          ├── messages → (AIMessageChunk, metadata)                          │
│          │       │                                                           │
│          │       └── notify_token_v2(content=chunk.content) ✅              │
│          │                                                                   │
│          └── updates → {"node_name": state_update}                          │
│                  │                                                           │
│                  └── notify_stage(stage=node_name, status=...) ✅           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 검증 방법

토큰 스트리밍 수정 후 검증:

```bash
# 1. 세션 생성 및 메시지 전송
curl -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message":"페트병 어떻게 버려?"}'

# 2. SSE 스트림 수신 (토큰 이벤트 확인)
curl -sN "https://api.dev.growbin.app/api/v1/chat/$JOB_ID/events" \
  -H "Accept: text/event-stream" \
  -H "Cookie: s_access=$TOKEN" | grep '"stage":"token"'

# 기대 출력:
# data: {"stage":"token","content":"무","seq":1001}
# data: {"stage":"token","content":"색","seq":1002}
# ...
```

---

## 부록: 관련 파일

| 파일 | 역할 |
|------|------|
| `process_chat.py:393` | `on_llm_stream` 이벤트 핸들러 |
| `process_chat.py:514` | `_handle_llm_stream()` 메서드 |
| `openai_client.py:100` | `generate_stream()` 메서드 |
| `redis_progress_notifier.py:550` | `notify_token_v2()` 메서드 |
| `answer_node.py:148` | 토큰 수집 루프 |
