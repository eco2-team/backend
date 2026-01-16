# 이코에코(Eco²) Agent #18: LangGraph 네이티브 스트리밍 구현

> `ainvoke` → `astream_events` 전환으로 실시간 토큰 스트리밍과 복구 가능한 Token Stream 구현

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-16 |
| **버전** | v1.0 |
| **시리즈** | Eco² Agent 시리즈 |
| **이전 포스팅** | [#17 동적 컨텍스트 압축](./31-chat-dynamic-context-compression.md) |
| **참조 ADR** | [LangGraph Native Streaming ADR](../../plans/langgraph-native-streaming-adr.md) |
| **참조 ADR** | [Token Streaming Improvement ADR](../../plans/token-streaming-improvement-adr.md) |

---

## 1. 배경: 수동 토큰 스트리밍의 한계

### 1.1 기존 구현 방식

기존 Chat Worker는 `ainvoke`로 파이프라인을 실행하고, 각 노드에서 이벤트를 **수동으로 발행**했습니다.

```python
# 기존 방식 (answer_node.py)
async def answer_node(state: dict) -> dict:
    job_id = state["job_id"]

    # 수동 토큰 발행
    async for token in command.execute(input_dto):
        await event_publisher.notify_token(
            task_id=job_id,
            content=token,  # 토큰만 전달, 메타데이터 없음
        )
        answer_parts.append(token)

    return {**state, "answer": "".join(answer_parts)}
```

**문제점**:

| 문제 | 영향 |
|------|------|
| `ainvoke` 사용 | 파이프라인 완료까지 단일 응답, 중간 이벤트 없음 |
| 수동 토큰 발행 | 각 노드에서 `notify_token` 직접 호출 필요 |
| 이벤트 발행 분산 | 토큰 발행 로직이 모든 노드에 중복 |
| 메타데이터 부재 | 어떤 노드에서 발생한 토큰인지 알 수 없음 |
| 복구 불가 | 네트워크 오류 시 토큰 유실 |

### 1.2 목표

1. **LangGraph 네이티브 스트리밍**: `astream_events`로 통합 이벤트 처리
2. **메타데이터 활용**: 어떤 노드에서 발생한 토큰인지 추적
3. **토큰 복구**: Token Stream + State로 재연결 시 복구
4. **코드 간소화**: 각 노드의 이벤트 발행 로직 제거

---

## 2. LangGraph 1.0+ 네이티브 스트리밍

### 2.1 astream_events API

LangGraph 1.0+의 `astream_events`는 파이프라인 실행 중 발생하는 **모든 이벤트를 실시간으로 스트리밍**합니다.

```python
async for event in graph.astream_events(state, version="v2"):
    event_type = event.get("event")

    if event_type == "on_chain_start":
        # 노드 시작
        ...
    elif event_type == "on_chain_end":
        # 노드 완료
        ...
    elif event_type == "on_llm_stream":
        # LLM 토큰 스트리밍 ★
        chunk = event.get("data", {}).get("chunk")
        if chunk and chunk.content:
            print(chunk.content, end="", flush=True)
```

### 2.2 이벤트 타입 및 메타데이터

```python
# astream_events (v2) 이벤트 구조
event = {
    "event": "on_llm_stream",
    "name": "ChatOpenAI",
    "run_id": "uuid...",
    "metadata": {
        "langgraph_node": "answer",      # 현재 노드명 ★
        "langgraph_step": 5,             # 그래프 스텝
        "langgraph_triggers": ["aggregator"],
        "thread_id": "session-123",      # config에서 전달됨
    },
    "data": {
        "chunk": AIMessageChunk(content="플")  # 토큰 내용
    }
}
```

**핵심**: `metadata.langgraph_node`로 토큰이 **어떤 노드에서 발생했는지** 자동으로 알 수 있습니다.

### 2.3 이벤트 타입 정리

| 이벤트 | 설명 | 활용 |
|--------|------|------|
| `on_chain_start` | 노드 시작 | Progress UI |
| `on_chain_end` | 노드 완료 | Progress UI, 결과 수집 |
| `on_llm_stream` | LLM 토큰 | **실시간 답변 스트리밍** |
| `on_llm_end` | LLM 완료 | 전체 응답 확인 |
| `on_retriever_start/end` | 검색 시작/완료 | RAG 진행률 |
| `on_tool_start/end` | 도구 시작/완료 | 서브에이전트 진행률 |

---

## 3. 동적 Progress 추적기

### 3.1 문제: Send API 병렬 실행

LangGraph Send API로 서브에이전트를 **병렬 실행**하면, 기존 순차적 Progress 맵이 동작하지 않습니다.

```python
# 기존 설계 (문제점)
PROGRESS_MAP = {
    "rag_started": 25,      # waste_rag만 있다고 가정
    "rag_completed": 35,
}
# → 실제로는 waste_rag, character, location, weather가 병렬 실행!
# → character만 먼저 끝나면? 진행률이 어떻게 되어야 하나?
```

### 3.2 해결: DynamicProgressTracker

**Phase 기반 Progress**와 **동적 계산**으로 병렬 실행을 지원합니다.

```python
# progress_tracker.py

PHASE_PROGRESS = {
    "queued": (0, 0),
    "intent": (5, 15),
    "vision": (15, 20),
    "subagents": (20, 55),    # 동적 계산 ★
    "aggregator": (55, 65),
    "summarize": (65, 75),
    "answer": (75, 95),
    "done": (100, 100),
}

SUBAGENT_NODES = {
    "waste_rag", "character", "location", "bulk_waste",
    "weather", "web_search", "collection_point",
    "recyclable_price", "image_generation", "general", "feedback",
}

class DynamicProgressTracker:
    """동적 라우팅 환경의 Progress 추적기."""

    def __init__(self):
        self._activated_subagents: set[str] = set()
        self._completed_subagents: set[str] = set()

    def on_subagent_start(self, node: str) -> None:
        """서브에이전트 시작 추적."""
        if node in SUBAGENT_NODES:
            self._activated_subagents.add(node)

    def on_subagent_end(self, node: str) -> None:
        """서브에이전트 완료 추적."""
        if node in SUBAGENT_NODES:
            self._completed_subagents.add(node)

    def calculate_progress(self, phase: str, status: str) -> int:
        """Phase와 상태에 따른 Progress 계산."""
        if phase == "subagents":
            return self._calculate_subagent_progress()

        phase_range = PHASE_PROGRESS.get(phase, (0, 0))
        return phase_range[0] if status == "started" else phase_range[1]

    def _calculate_subagent_progress(self) -> int:
        """서브에이전트 병렬 실행 진행률.

        공식: base + (completed / total) * range
        예: 3개 활성화, 1개 완료 → 20 + (1/3) * 35 = 32%
        """
        total = len(self._activated_subagents)
        completed = len(self._completed_subagents)

        if total == 0:
            return 55  # subagents 종료

        start, end = PHASE_PROGRESS["subagents"]
        return start + int((completed / total) * (end - start))
```

### 3.3 Progress 시나리오 예시

```
┌─────────────────────────────────────────────────────────────────┐
│  Scenario: intent=waste (2개 노드: waste_rag, weather)         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  queued_started     → 0%                                       │
│  intent_started     → 5%                                       │
│  intent_completed   → 15%                                      │
│  router             → 20% (subagents 시작)                     │
│  waste_rag_started  → 20% (2개 중 0개 완료)                   │
│  weather_started    → 20%                                      │
│  weather_completed  → 37% (2개 중 1개: 20 + 0.5*35)          │
│  waste_rag_completed→ 55% (2개 중 2개 완료)                   │
│  aggregator_started → 55%                                      │
│  aggregator_completed→ 65%                                     │
│  answer_started     → 75%                                      │
│  answer_completed   → 95%                                      │
│  done               → 100%                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. ProcessChatCommand 네이티브 스트리밍

### 4.1 ChatPipelinePort 확장

```python
class ChatPipelinePort(Protocol):
    """Chat 파이프라인 Port."""

    async def ainvoke(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """동기 실행 (기존)."""
        ...

    def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any] | None = None,
        version: str = "v2",
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """이벤트 스트리밍 (신규)."""
        ...
```

### 4.2 ProcessChatCommand 구현

```python
class ProcessChatCommand:
    def __init__(
        self,
        pipeline: ChatPipelinePort,
        progress_notifier: "ProgressNotifierPort",
        metrics: "MetricsPort | None" = None,
        telemetry: "TelemetryConfigPort | None" = None,  # Clean Architecture
        enable_native_streaming: bool = True,
    ):
        self._pipeline = pipeline
        self._progress_notifier = progress_notifier
        self._metrics = metrics
        self._telemetry = telemetry
        self._enable_native_streaming = enable_native_streaming

    async def execute(self, request: ProcessChatRequest) -> ProcessChatResponse:
        # Progress Tracker (요청별 로컬 인스턴스)
        progress_tracker = DynamicProgressTracker()

        # 1. 작업 시작 이벤트
        await self._progress_notifier.notify_stage(
            task_id=request.job_id,
            stage="queued",
            status="started",
            progress=0,
        )

        # 2. Telemetry 설정 (Clean Architecture: Port 통해 주입)
        config: dict[str, Any] = {"configurable": {}}
        if request.session_id:
            config["configurable"]["thread_id"] = request.session_id

        if self._telemetry:
            config = self._telemetry.get_run_config(
                job_id=request.job_id,
                session_id=request.session_id,
                user_id=request.user_id,
            )

        # 3. 네이티브 스트리밍 실행
        if self._enable_native_streaming:
            result = await self._execute_streaming(
                initial_state, config, request.job_id, progress_tracker
            )
        else:
            result = await self._pipeline.ainvoke(initial_state, config=config)

        # 4. 토큰 스트림 완료 처리
        await self._progress_notifier.finalize_token_stream(request.job_id)

        # 5. 작업 완료 이벤트
        await self._progress_notifier.notify_stage(
            task_id=request.job_id,
            stage="done",
            status="completed",
            progress=100,
            result={"intent": intent, "answer": answer},
        )

        return ProcessChatResponse(...)
```

### 4.3 이벤트 핸들러

```python
async def _execute_streaming(
    self,
    state: dict[str, Any],
    config: dict[str, Any],
    job_id: str,
    progress_tracker: DynamicProgressTracker,
) -> dict[str, Any]:
    """astream_events를 사용한 스트리밍 파이프라인 실행."""
    final_result: dict[str, Any] = {}

    async for event in self._pipeline.astream_events(
        state, config=config, version="v2"
    ):
        event_type = event.get("event")

        if event_type == "on_chain_start":
            await self._handle_chain_start(event, job_id, progress_tracker)

        elif event_type == "on_chain_end":
            final_result = await self._handle_chain_end(
                event, job_id, final_result, progress_tracker
            )

        elif event_type == "on_llm_stream":
            await self._handle_llm_stream(event, job_id)

    return final_result

async def _handle_llm_stream(self, event: dict[str, Any], job_id: str) -> None:
    """LLM 토큰 스트리밍 처리."""
    chunk = event.get("data", {}).get("chunk")
    if not chunk:
        return

    content = getattr(chunk, "content", None)
    if not content:
        return

    # 발생 노드 추출 (answer, summarize 등)
    metadata = event.get("metadata", {})
    node = metadata.get("langgraph_node", "")

    # Token v2로 발행 (복구 가능)
    await self._progress_notifier.notify_token_v2(
        task_id=job_id,
        content=content,
        node=node,  # 메타데이터로 노드명 전달 ★
    )
```

---

## 5. Token v2: 복구 가능한 토큰 스트리밍

### 5.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Token v2 스트리밍 아키텍처                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ProcessChatCommand                                                     │
│       │ on_llm_stream 이벤트                                           │
│       ▼                                                                 │
│  RedisProgressNotifier.notify_token_v2()                               │
│       │                                                                 │
│       ├─── Token Stream (chat:tokens:{job_id})                         │
│       │    - 모든 토큰 저장                                            │
│       │    - 재연결 시 catch-up 지원                                   │
│       │                                                                 │
│       ├─── Token State (chat:token_state:{job_id})                     │
│       │    - 10 토큰마다 누적 텍스트 스냅샷                            │
│       │    - 즉시 복구 지원                                            │
│       │                                                                 │
│       └─── Stage Stream (chat:events:{shard})                          │
│            - 기존 호환성 유지                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 ProgressNotifierPort 확장

```python
class ProgressNotifierPort(Protocol):
    """진행 상황 알림 Port."""

    async def notify_stage(...) -> str:
        """단계 이벤트 발행."""
        ...

    async def notify_token(self, task_id: str, content: str) -> str:
        """토큰 이벤트 발행 (기존)."""
        ...

    async def notify_token_v2(
        self,
        task_id: str,
        content: str,
        node: str | None = None,  # 발생 노드명 ★
    ) -> str:
        """토큰 이벤트 발행 (복구 가능)."""
        ...

    async def finalize_token_stream(self, task_id: str) -> None:
        """토큰 스트림 완료 처리."""
        ...

    def clear_token_counter(self, task_id: str) -> None:
        """토큰 카운터 정리."""
        ...
```

### 5.3 RedisProgressNotifier.notify_token_v2

```python
async def notify_token_v2(
    self,
    task_id: str,
    content: str,
    node: str | None = None,
) -> str:
    """토큰 스트리밍 이벤트 발행 (복구 가능)."""
    await self._ensure_scripts()

    # 누적 텍스트 계산
    is_first_token = task_id not in self._accumulated
    if is_first_token:
        self._accumulated[task_id] = ""
        self._token_count[task_id] = 0
        self._stream_start_time[task_id] = time.perf_counter()
        CHAT_STREAM_ACTIVE.inc()  # Metrics

    self._accumulated[task_id] += content
    self._token_count[task_id] += 1

    # State 저장 여부 (10 토큰마다)
    save_state = 1 if self._token_count[task_id] % 10 == 0 else 0

    # Lua Script로 원자적 실행
    # 1. Token Stream에 추가 (chat:tokens:{job_id})
    # 2. 주기적으로 State 저장 (chat:token_state:{job_id})
    # 3. Stage Stream에도 발행 (chat:events:{shard})
    result = await self._token_v2_script(
        keys=[token_stream_key, token_state_key, stage_stream_key],
        args=[task_id, seq, content, ts, accumulated, save_state, ttl, maxlen, node],
    )

    # Metrics 기록
    track_stream_token(node=node or "answer", status="success", latency=xadd_latency)

    return token_msg_id
```

### 5.4 finalize_token_stream

```python
async def finalize_token_stream(self, task_id: str) -> None:
    """토큰 스트림 완료 처리."""
    if task_id not in self._accumulated:
        return

    accumulated = self._accumulated[task_id]
    token_count = self._token_count.get(task_id, 0)
    start_time = self._stream_start_time.get(task_id)

    # Metrics
    CHAT_STREAM_ACTIVE.dec()
    if start_time:
        duration = time.perf_counter() - start_time
        CHAT_STREAM_DURATION.labels(node=stream_node, status="success").observe(duration)
    CHAT_STREAM_TOKEN_COUNT.labels(node=stream_node).observe(token_count)
    CHAT_STREAM_REQUESTS_TOTAL.labels(status="success").inc()

    # 최종 State 저장 (completed 플래그)
    state = {
        "last_seq": seq,
        "accumulated": accumulated,
        "accumulated_len": len(accumulated),
        "completed": True,
        "updated_at": time.time(),
    }
    await self._redis.setex(token_state_key, TTL, json.dumps(state))

    # 메모리 정리
    self.clear_token_counter(task_id)
```

---

## 6. Answer Node 간소화

네이티브 스트리밍으로 전환하면서 Answer Node에서 **토큰 직접 발행을 제거**했습니다.

```python
# Before: Answer Node에서 직접 토큰 발행
async def answer_node(state: dict) -> dict:
    async for token in command.execute(input_dto):
        await event_publisher.notify_token(task_id=job_id, content=token)  # ❌ 제거
        answer_parts.append(token)
    return {**state, "answer": "".join(answer_parts)}

# After: ProcessChatCommand에서 통합 처리
async def answer_node(state: dict) -> dict:
    answer_parts = []
    async for token in command.execute(input_dto):
        # LangGraph가 on_llm_stream 이벤트로 자동 발행 ✅
        answer_parts.append(token)
    return {**state, "answer": "".join(answer_parts)}
```

**장점**:
- 각 노드의 책임이 명확해짐 (토큰 발행은 상위 레벨에서)
- 코드 중복 제거
- 메타데이터 자동 포함 (node, step 등)

---

## 7. Clean Architecture 준수

### 7.1 문제: Infrastructure 직접 의존

```python
# Before (위반)
from chat_worker.infrastructure.telemetry.langsmith import get_run_config, is_langsmith_enabled

class ProcessChatCommand:
    async def execute(self, request):
        config = get_run_config(...)  # ❌ Application → Infrastructure 의존
```

### 7.2 해결: TelemetryConfigPort

```python
# application/ports/telemetry.py
class TelemetryConfigPort(Protocol):
    """Telemetry 설정 생성 Port."""

    def is_enabled(self) -> bool:
        ...

    def get_run_config(
        self,
        job_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        ...

# infrastructure/telemetry/langsmith_adapter.py
class LangSmithTelemetryAdapter(TelemetryConfigPort):
    """LangSmith Telemetry 어댑터."""

    def is_enabled(self) -> bool:
        return is_langsmith_enabled()

    def get_run_config(self, job_id: str, **kwargs) -> dict[str, Any]:
        return get_run_config(job_id=job_id, **kwargs)
```

```python
# After (Clean Architecture 준수)
class ProcessChatCommand:
    def __init__(
        self,
        pipeline: ChatPipelinePort,
        progress_notifier: "ProgressNotifierPort",
        telemetry: "TelemetryConfigPort | None" = None,  # ✅ Port 주입
    ):
        self._telemetry = telemetry

    async def execute(self, request):
        if self._telemetry:
            config = self._telemetry.get_run_config(...)  # ✅ Port 사용
```

---

## 8. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `application/ports/events/progress_notifier.py` | `notify_token_v2`, `finalize_token_stream` 추가 |
| `application/ports/telemetry.py` | **신규** - TelemetryConfigPort, NoOpTelemetryConfig |
| `application/services/progress_tracker.py` | **신규** - DynamicProgressTracker, Phase 기반 Progress |
| `application/commands/process_chat.py` | `astream_events` 전환, Telemetry Port 주입 |
| `infrastructure/events/redis_progress_notifier.py` | Token Stream + State 구현 |
| `infrastructure/telemetry/langsmith_adapter.py` | **신규** - LangSmithTelemetryAdapter |
| `infrastructure/orchestration/langgraph/nodes/answer_node.py` | `notify_token` 제거 |

---

## 9. 결과 요약

### Before vs After

| 항목 | Before (ainvoke) | After (astream_events) |
|------|------------------|------------------------|
| 파이프라인 실행 | 전체 완료 대기 | 실시간 이벤트 스트림 |
| 토큰 발행 위치 | 각 노드에서 수동 | ProcessChatCommand에서 통합 |
| 메타데이터 | 없음 | node, step, triggers 포함 |
| Progress 계산 | 순차적 고정값 | Phase 기반 동적 계산 |
| 토큰 복구 | 불가 | Token Stream + State |
| Clean Architecture | 위반 (Infrastructure 직접 import) | 준수 (Port/Adapter) |

### 핵심 개선

1. **LangGraph 네이티브 스트리밍**: `astream_events`로 모든 이벤트 통합 처리
2. **동적 Progress**: 병렬 서브에이전트 실행에 맞는 진행률 계산
3. **Token v2**: 복구 가능한 토큰 스트리밍 (Stream + State)
4. **Clean Architecture**: TelemetryConfigPort로 의존성 역전

---

## 10. 참고 자료

### LangGraph
- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/how-tos/streaming-tokens/)
- [LangGraph astream_events](https://langchain-ai.github.io/langgraph/how-tos/streaming-events-from-within-tools/)

### Token Streaming
- [Upstash: Resumable LLM Streams](https://upstash.com/blog/resumable-llm-streams)
- [OpenCode session/index.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/index.ts)

### Clean Architecture
- [Clean Architecture - Uncle Bob](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Ports and Adapters](https://alistair.cockburn.us/hexagonal-architecture/)

---

*문서 버전: v1.0*
*최종 수정: 2026-01-16*
*커밋: `e6fd91e8` (feat: implement LangGraph native streaming with observability)*
