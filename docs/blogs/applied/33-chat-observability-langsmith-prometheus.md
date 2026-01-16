# 이코에코(Eco²) Agent #19: Observability - LangSmith + Prometheus 통합

> Feature-level Observability: LangSmith로 노드별 분석, Prometheus로 부하테스트 메트릭

| 항목 | 값 |
|-----|-----|
| **작성일** | 2026-01-16 |
| **버전** | v1.0 |
| **시리즈** | Eco² Agent 시리즈 |
| **이전 포스팅** | [#18 LangGraph 네이티브 스트리밍](./32-langgraph-native-streaming.md) |
| **참조 가이드** | [Observability Setup Guide](../../guides/observability-setup.md) |

---

## 1. 배경: 왜 Observability가 필요한가?

### 1.1 LangGraph 파이프라인의 복잡성

Eco² Chat Worker는 **10개 이상의 서브에이전트**가 동적으로 라우팅되는 복잡한 파이프라인입니다.

```
사용자 질문
    │
    ▼
┌─────────┐
│ intent  │  → 9개 Intent 분류
└────┬────┘
     │
     ├─→ waste_rag      (RAG + Feedback)
     ├─→ character      (gRPC)
     ├─→ location       (Kakao API)
     ├─→ bulk_waste     (행정안전부 API)
     ├─→ weather        (기상청 API)
     ├─→ web_search     (DuckDuckGo)
     ├─→ collection_point (KECO API)
     ├─→ recyclable_price (KECO API)
     ├─→ image_generation (OpenAI Responses)
     └─→ general        (LLM Only)
           │
           ▼
     ┌──────────┐
     │ answer   │  → 최종 답변 생성
     └──────────┘
```

**질문**: 응답이 느릴 때, **어떤 노드가 병목**인지 어떻게 알 수 있을까요?

### 1.2 Observability 목표

| 목표 | 도구 | 제공 정보 |
|------|------|----------|
| **Feature-level 분석** | LangSmith | 노드별 Latency, 토큰 사용량, 에러 추적 |
| **부하테스트 메트릭** | Prometheus | 토큰 처리량, Redis 지연시간, 동시 스트림 수 |
| **실시간 모니터링** | Grafana | 대시보드, 알림 |

---

## 2. LangSmith 통합: Feature-level Observability

### 2.1 LangSmith란?

LangSmith는 LangChain/LangGraph의 **네이티브 Observability 플랫폼**입니다.

```
환경변수만 설정하면 자동 활성화:
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=lsv2_pt_xxxx
  LANGCHAIN_PROJECT=eco2-chat-worker
```

**자동 수집 메트릭**:

| 메트릭 | 설명 |
|--------|------|
| **Per-Node Latency** | intent, vision, waste_rag, answer 등 노드별 소요시간 |
| **Token Usage** | 노드별 input/output 토큰 수, 비용 추정 |
| **Run Timeline** | 병렬 실행 (Send API) 시각화 |
| **Error Tracking** | 노드별 에러율, 스택 트레이스 |
| **Feedback Loop** | RAG 품질 평가, Fallback 체인 추적 |

### 2.2 LangSmith OpenTelemetry 통합 (Jaeger 연동)

> **참조**: [End-to-End OpenTelemetry with LangSmith](https://blog.langchain.com/end-to-end-opentelemetry-langsmith/)

LangSmith는 OTEL 프로토콜을 지원하여 LangGraph 트레이스를 Jaeger로 전송할 수 있습니다.

```bash
# OTEL 모드 활성화
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-api-key>
export LANGSMITH_OTEL_ENABLED=true  # Jaeger로 전송

# 패키지 필요
pip install "langsmith[otel]"
```

**End-to-End Trace 구조** (Jaeger에서 확인):

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Jaeger Trace View                          │
├─────────────────────────────────────────────────────────────────────┤
│ chat-api (FastAPI)                                                   │
│ └── POST /api/v1/chat                                                │
│     └── chat-worker (aio-pika)                                       │
│         └── process_chat                                             │
│             └── LangGraph Pipeline (LangSmith OTEL)                  │
│                 ├── intent_node                                      │
│                 ├── waste_rag_node                                   │
│                 │   └── OpenAI Embeddings                            │
│                 ├── character_node (gRPC)                            │
│                 └── answer_node                                      │
│                     └── OpenAI Chat Completion (streaming)           │
└─────────────────────────────────────────────────────────────────────┘
```

**트레이싱 모드 비교**:

| 모드 | 설정 | 장점 | 단점 |
|------|------|------|------|
| **Native** | `LANGSMITH_OTEL_ENABLED=false` | 낮은 오버헤드, LangSmith 최적화 | Jaeger 연동 불가 |
| **OTEL** | `LANGSMITH_OTEL_ENABLED=true` | End-to-End 추적, Jaeger 통합 | 약간의 오버헤드 |

### 2.3 LangSmith 설정 모듈

```python
# infrastructure/telemetry/langsmith.py

LANGSMITH_ENABLED = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
LANGSMITH_API_KEY = os.environ.get("LANGCHAIN_API_KEY")
LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "eco2-chat-worker")

def is_langsmith_enabled() -> bool:
    """LangSmith 활성화 여부 확인."""
    return LANGSMITH_ENABLED and LANGSMITH_API_KEY is not None

def configure_langsmith() -> bool:
    """LangSmith 설정 적용 (앱 시작 시)."""
    if not LANGSMITH_ENABLED:
        logger.info("LangSmith tracing disabled")
        return False

    if not LANGSMITH_API_KEY:
        logger.warning("LANGCHAIN_API_KEY not set - traces will fail")
        return False

    logger.info(
        "LangSmith tracing enabled",
        extra={"project": LANGSMITH_PROJECT},
    )
    return True
```

### 2.3 Run Config 생성

```python
def get_run_config(
    job_id: str,
    session_id: str | None = None,
    user_id: str | None = None,
    intent: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LangGraph 실행을 위한 config 생성.

    LangSmith에서 필터링/분석에 사용할 메타데이터를 포함합니다.
    """
    # 방어적 복사: 원본 리스트 mutation 방지
    run_tags = list(tags) if tags else []

    if intent:
        run_tags.append(f"intent:{intent}")

    run_metadata = {
        "job_id": job_id,
        "user_id": user_id,
        "intent": intent,
    }

    if metadata:
        run_metadata.update(metadata)

    config: dict[str, Any] = {
        "run_name": f"chat:{job_id}",
        "tags": run_tags,
        "metadata": run_metadata,
        "configurable": {},
    }

    # 멀티턴 대화를 위한 thread_id
    if session_id:
        config["configurable"]["thread_id"] = session_id

    return config
```

### 2.4 LangSmith UI 필터링

```
# Intent별 필터
tags:intent:waste
tags:intent:character
tags:intent:bulk_waste

# Subagent별 필터
tags:subagent:waste_rag
tags:subagent:character
tags:subagent:location

# 환경별 필터
tags:env:production
tags:env:staging

# Metadata 필터
metadata.user_id = "user-123"
metadata.job_id = "job-456"
```

### 2.5 Intent-to-Feature 매핑

부하테스트 분석 시 Intent별 특성을 파악하기 위한 매핑입니다.

```python
INTENT_FEATURE_MAP = {
    "waste": {
        "feature": "rag",
        "subagents": ["waste_rag", "weather"],
        "has_feedback": True,
        "description": "분리배출 RAG 검색",
    },
    "bulk_waste": {
        "feature": "external_api",
        "subagents": ["bulk_waste", "weather"],
        "description": "대형폐기물 (행정안전부 API)",
    },
    "character": {
        "feature": "grpc",
        "subagents": ["character"],
        "description": "캐릭터 정보 (gRPC)",
    },
    "location": {
        "feature": "external_api",
        "subagents": ["location"],
        "description": "장소 검색 (카카오맵)",
    },
    # ...
}
```

---

## 3. Clean Architecture: TelemetryConfigPort

### 3.1 문제: Application → Infrastructure 의존

```python
# 기존 코드 (Clean Architecture 위반)
from chat_worker.infrastructure.telemetry.langsmith import get_run_config, is_langsmith_enabled

class ProcessChatCommand:
    async def execute(self, request):
        config = get_run_config(...)  # ❌ Infrastructure 직접 참조
```

### 3.2 해결: Port/Adapter 패턴

```python
# application/ports/telemetry.py
class TelemetryConfigPort(Protocol):
    """Telemetry 설정 생성 Port."""

    def is_enabled(self) -> bool:
        """Telemetry 활성화 여부."""
        ...

    def get_run_config(
        self,
        job_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        intent: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LangGraph 실행을 위한 config 생성."""
        ...


class NoOpTelemetryConfig:
    """NoOp Telemetry 설정 (테스트용)."""

    def is_enabled(self) -> bool:
        return False

    def get_run_config(self, job_id: str, **kwargs) -> dict[str, Any]:
        config: dict[str, Any] = {"configurable": {}}
        if kwargs.get("session_id"):
            config["configurable"]["thread_id"] = kwargs["session_id"]
        return config
```

```python
# infrastructure/telemetry/langsmith_adapter.py
class LangSmithTelemetryAdapter(TelemetryConfigPort):
    """LangSmith Telemetry 어댑터."""

    def __init__(self, default_tags: list[str] | None = None):
        self._default_tags = default_tags

    def is_enabled(self) -> bool:
        return is_langsmith_enabled()

    def get_run_config(self, job_id: str, **kwargs) -> dict[str, Any]:
        # 기본 태그와 요청별 태그 병합
        merged_tags: list[str] = []
        if self._default_tags:
            merged_tags.extend(self._default_tags)
        if kwargs.get("tags"):
            merged_tags.extend(kwargs["tags"])

        return get_run_config(
            job_id=job_id,
            tags=merged_tags if merged_tags else None,
            **kwargs,
        )
```

### 3.3 Composition Root에서 주입

```python
# main.py 또는 DI Container
telemetry = LangSmithTelemetryAdapter(default_tags=["env:production"])

command = ProcessChatCommand(
    pipeline=graph,
    progress_notifier=redis_notifier,
    metrics=prometheus_adapter,
    telemetry=telemetry,  # Port 주입
)
```

---

## 4. Prometheus 메트릭: Token Streaming

### 4.1 메트릭 정의

```python
# infrastructure/metrics/metrics.py

# ============================================================
# Token Streaming Metrics (부하테스트용)
# ============================================================

# 스트리밍 토큰 처리량
CHAT_STREAM_TOKENS_TOTAL = Counter(
    "chat_stream_tokens_total",
    "Total streaming tokens emitted",
    ["node", "status"],  # node: answer, summarize / status: success, error
)

# 토큰 스트림 요청 수
CHAT_STREAM_REQUESTS_TOTAL = Counter(
    "chat_stream_requests_total",
    "Total token stream requests",
    ["status"],  # status: success, error, recovered
)

# 토큰 발행 지연시간 (Redis XADD)
CHAT_STREAM_TOKEN_LATENCY = Histogram(
    "chat_stream_token_latency_seconds",
    "Token emission latency (Redis XADD)",
    ["node"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

# 토큰 간 간격 (LLM 스트리밍 속도)
CHAT_STREAM_TOKEN_INTERVAL = Histogram(
    "chat_stream_token_interval_seconds",
    "Interval between tokens (LLM streaming speed)",
    ["provider"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0],
)

# 전체 스트림 완료 시간
CHAT_STREAM_DURATION = Histogram(
    "chat_stream_duration_seconds",
    "Total token stream duration",
    ["node", "status"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

# 스트림당 토큰 수
CHAT_STREAM_TOKEN_COUNT = Histogram(
    "chat_stream_token_count",
    "Number of tokens per stream",
    ["node"],
    buckets=[10, 50, 100, 200, 500, 1000, 2000],
)

# Token 복구 메트릭
CHAT_STREAM_RECOVERY_TOTAL = Counter(
    "chat_stream_recovery_total",
    "Token stream recovery attempts",
    ["type", "status"],  # type: catch_up, snapshot / status: success, error
)

# 활성 스트림 수 (Gauge)
CHAT_STREAM_ACTIVE = Gauge(
    "chat_stream_active",
    "Number of active token streams",
)
```

### 4.2 Helper 함수

```python
def track_stream_token(
    node: str = "answer",
    status: str = "success",
    latency: float | None = None,
) -> None:
    """단일 토큰 발행 추적."""
    CHAT_STREAM_TOKENS_TOTAL.labels(node=node, status=status).inc()
    if latency is not None:
        CHAT_STREAM_TOKEN_LATENCY.labels(node=node).observe(latency)


def track_stream_recovery(
    recovery_type: str,
    status: str = "success",
) -> None:
    """토큰 복구 추적."""
    CHAT_STREAM_RECOVERY_TOTAL.labels(type=recovery_type, status=status).inc()


class StreamMetricsTracker:
    """토큰 스트림 메트릭 추적기.

    Usage:
        tracker = StreamMetricsTracker(node="answer", provider="openai")
        tracker.start()

        for token in stream:
            tracker.record_token()

        tracker.finish(status="success")
    """

    def __init__(self, node: str = "answer", provider: str = "openai") -> None:
        self.node = node
        self.provider = provider
        self._start_time: float | None = None
        self._last_token_time: float | None = None
        self._token_count: int = 0

    def start(self) -> None:
        """스트림 시작."""
        self._start_time = time.perf_counter()
        self._last_token_time = self._start_time
        self._token_count = 0
        CHAT_STREAM_ACTIVE.inc()

    def record_token(self, latency: float | None = None) -> None:
        """토큰 발행 기록."""
        current_time = time.perf_counter()
        self._token_count += 1

        CHAT_STREAM_TOKENS_TOTAL.labels(node=self.node, status="success").inc()

        # 토큰 간 간격
        if self._last_token_time is not None:
            interval = current_time - self._last_token_time
            CHAT_STREAM_TOKEN_INTERVAL.labels(provider=self.provider).observe(interval)

        # Redis 지연시간
        if latency is not None:
            CHAT_STREAM_TOKEN_LATENCY.labels(node=self.node).observe(latency)

        self._last_token_time = current_time

    def finish(self, status: str = "success") -> None:
        """스트림 완료."""
        CHAT_STREAM_ACTIVE.dec()

        if self._start_time is not None:
            duration = time.perf_counter() - self._start_time
            CHAT_STREAM_DURATION.labels(node=self.node, status=status).observe(duration)

        CHAT_STREAM_TOKEN_COUNT.labels(node=self.node).observe(self._token_count)
        CHAT_STREAM_REQUESTS_TOTAL.labels(status=status).inc()
```

### 4.3 메트릭 수집 위치

```python
# redis_progress_notifier.py

async def notify_token_v2(self, task_id: str, content: str, node: str | None = None) -> str:
    # ...

    # 첫 토큰: Active stream 증가
    if is_first_token:
        CHAT_STREAM_ACTIVE.inc()

    # Redis XADD 지연시간 측정
    xadd_start = time.perf_counter()
    result = await self._token_v2_script(...)
    xadd_latency = time.perf_counter() - xadd_start

    # 토큰 카운트 + 지연시간 기록
    track_stream_token(node=node or "answer", status="success", latency=xadd_latency)

    return token_msg_id


async def finalize_token_stream(self, task_id: str) -> None:
    # ...

    # Active stream 감소
    CHAT_STREAM_ACTIVE.dec()

    # Duration 기록
    if start_time is not None:
        duration = time.perf_counter() - start_time
        CHAT_STREAM_DURATION.labels(node=stream_node, status="success").observe(duration)

    # Token count 기록
    CHAT_STREAM_TOKEN_COUNT.labels(node=stream_node).observe(token_count)

    # Request 완료 기록
    CHAT_STREAM_REQUESTS_TOTAL.labels(status="success").inc()
```

---

## 5. MetricsPort: Clean Architecture

### 5.1 기존 메트릭 Port

```python
# application/ports/metrics/metrics_port.py
class MetricsPort(Protocol):
    """메트릭 수집 Port."""

    def track_request(
        self,
        intent: str,
        status: str,
        provider: str,
        duration: float,
    ) -> None:
        """요청 메트릭 기록."""
        ...

    def track_intent(self, intent: str) -> None:
        """Intent 분류 메트릭 기록."""
        ...

    def track_error(self, intent: str, error_type: str) -> None:
        """에러 메트릭 기록."""
        ...

    def track_subagent_call(
        self,
        subagent: str,
        status: str,
        duration: float,
    ) -> None:
        """서브에이전트 호출 메트릭 기록."""
        ...
```

### 5.2 PrometheusMetricsAdapter

```python
# infrastructure/metrics/prometheus_adapter.py
class PrometheusMetricsAdapter(MetricsPort):
    """Prometheus 메트릭 어댑터."""

    def track_request(
        self,
        intent: str,
        status: str,
        provider: str,
        duration: float,
    ) -> None:
        try:
            CHAT_REQUESTS_TOTAL.labels(
                intent=intent,
                status=status,
                provider=provider,
            ).inc()
            CHAT_REQUEST_DURATION.labels(
                intent=intent,
                provider=provider,
            ).observe(duration)
        except Exception as e:
            logger.warning("metrics_track_request_failed", extra={"error": str(e)})

    def track_subagent_call(
        self,
        subagent: str,
        status: str,
        duration: float,
    ) -> None:
        try:
            CHAT_SUBAGENT_CALLS.labels(
                subagent=subagent,
                status=status,
            ).inc()
            CHAT_SUBAGENT_DURATION.labels(
                subagent=subagent,
            ).observe(duration)
        except Exception as e:
            logger.warning("metrics_track_subagent_failed", extra={"error": str(e)})


class NoOpMetricsAdapter(MetricsPort):
    """NoOp 메트릭 어댑터 (테스트용)."""

    def track_request(self, **kwargs) -> None:
        pass

    def track_intent(self, intent: str) -> None:
        pass

    def track_error(self, **kwargs) -> None:
        pass
```

---

## 6. Grafana 대시보드

### 6.1 Token Streaming 패널

```promql
# 동시 처리 중인 스트림 수
chat_stream_active

# 초당 토큰 발행량 (node별)
rate(chat_stream_tokens_total[5m])

# Redis XADD 지연시간 P95
histogram_quantile(0.95, rate(chat_stream_token_latency_seconds_bucket[5m]))

# 전체 스트림 소요시간 P95
histogram_quantile(0.95, rate(chat_stream_duration_seconds_bucket[5m]))

# 스트림당 평균 토큰 수
histogram_quantile(0.5, rate(chat_stream_token_count_bucket[5m]))

# 복구 시도 횟수
rate(chat_stream_recovery_total[5m])
```

### 6.2 대시보드 레이아웃

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Chat Worker Token Streaming                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Active      │  │ Tokens/sec  │  │ P95 Latency │  │ P95 Duration│ │
│  │ Streams     │  │ (node별)    │  │ (XADD)      │  │ (전체)      │ │
│  │    3        │  │   150/s     │  │   12ms      │  │   8.5s      │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │          Token Emission Rate by Node (Time Series)             │  │
│  │  ▲                                                             │  │
│  │  │    ╭──╮                      ╭───╮                          │  │
│  │  │   ╱    ╲                    ╱     ╲                         │  │
│  │  │  ╱      ╲──────────────────╱       ╲                        │  │
│  │  │ ╱                                    ╲                      │  │
│  │  └──────────────────────────────────────────────────────▶      │  │
│  │       answer ─────  summarize ─────  feedback ─────            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │          Stream Duration Distribution (Histogram)              │  │
│  │  ▲                                                             │  │
│  │  │     ████                                                    │  │
│  │  │     ████  ███                                              │  │
│  │  │     ████  ███  ██                                          │  │
│  │  │ ██  ████  ███  ██  █   █                                   │  │
│  │  └──────────────────────────────────────────────────────▶      │  │
│  │    0.5s  1s   2s   5s  10s 20s 30s 60s                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. SLO 및 알림

### 7.1 피처별 성능 기준

| 피처 | P50 | P95 | P99 |
|------|-----|-----|-----|
| Intent 분류 | 100ms | 300ms | 500ms |
| RAG 검색 | 500ms | 1s | 2s |
| 전체 응답 (waste) | 2s | 5s | 10s |
| 전체 응답 (general) | 1s | 3s | 5s |
| Token 발행 지연 | 5ms | 25ms | 50ms |

### 7.2 알림 설정 (Prometheus Alertmanager)

```yaml
# alertmanager rules
groups:
  - name: chat_worker_streaming
    rules:
      - alert: HighTokenLatency
        expr: histogram_quantile(0.95, rate(chat_stream_token_latency_seconds_bucket[5m])) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Token latency P95 > 50ms"

      - alert: StreamDurationTooLong
        expr: histogram_quantile(0.95, rate(chat_stream_duration_seconds_bucket[5m])) > 30
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Stream duration P95 > 30s"

      - alert: TooManyActiveStreams
        expr: chat_stream_active > 100
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Active streams > 100"
```

---

## 8. 부하테스트 시나리오

### 8.1 Intent별 부하 분포

| Intent | 특성 | 예상 지연시간 |
|--------|------|---------------|
| `waste` | RAG + Feedback + Weather | 2-5s |
| `bulk_waste` | 외부 API (행정안전부) | 1-3s |
| `character` | gRPC | 50-200ms |
| `location` | 카카오맵 API | 200-500ms |
| `collection_point` | KECO API | 500ms-1s |
| `web_search` | DuckDuckGo/Tavily | 1-2s |
| `general` | LLM Only | 1-3s |

### 8.2 k6 부하테스트 예시

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 10 },  // Ramp up
    { duration: '5m', target: 50 },  // Sustain
    { duration: '1m', target: 0 },   // Ramp down
  ],
};

const INTENTS = ['waste', 'character', 'bulk_waste', 'general'];

export default function () {
  const intent = INTENTS[Math.floor(Math.random() * INTENTS.length)];
  const payload = JSON.stringify({
    message: getMessageForIntent(intent),
    session_id: `session-${__VU}-${__ITER}`,
  });

  const res = http.post('http://chat-api/chat/send', payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { intent: intent },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'job_id returned': (r) => r.json('job_id') !== undefined,
  });

  sleep(1);
}

function getMessageForIntent(intent) {
  const messages = {
    waste: '페트병 어떻게 버려?',
    character: '이코 소개해줘',
    bulk_waste: '소파 버리는 방법 알려줘',
    general: '안녕하세요',
  };
  return messages[intent] || '테스트 메시지';
}
```

---

## 9. 환경별 설정

### 9.1 개발 환경

```bash
# .env.development
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_xxx
LANGCHAIN_PROJECT=eco2-chat-worker-dev
```

### 9.2 Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: langsmith-credentials
  namespace: eco2
type: Opaque
stringData:
  LANGCHAIN_API_KEY: "lsv2_pt_xxxxxxxxxxxx"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-worker
spec:
  template:
    spec:
      containers:
        - name: chat-worker
          env:
            - name: LANGCHAIN_TRACING_V2
              value: "true"
            - name: LANGCHAIN_PROJECT
              value: "eco2-chat-worker"
            - name: LANGCHAIN_API_KEY
              valueFrom:
                secretKeyRef:
                  name: langsmith-credentials
                  key: LANGCHAIN_API_KEY
```

---

## 10. 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `infrastructure/metrics/metrics.py` | Token Streaming 메트릭 추가 (prometheus.py에서 rename) |
| `infrastructure/metrics/__init__.py` | Streaming 메트릭 export 추가 |
| `infrastructure/metrics/prometheus_adapter.py` | metrics.py import 수정 |
| `infrastructure/telemetry/langsmith.py` | **신규** - LangSmith 설정 및 config 생성 |
| `infrastructure/telemetry/langsmith_adapter.py` | **신규** - TelemetryConfigPort 구현 |
| `application/ports/telemetry.py` | **신규** - TelemetryConfigPort Protocol |
| `docs/guides/observability-setup.md` | 설정 가이드 |

---

## 11. 결과 요약

### LangSmith + Prometheus 역할 분담

| 도구 | 역할 | 장점 |
|------|------|------|
| **LangSmith** | Feature-level 분석 | 노드별 Latency, 토큰, 에러 자동 수집 |
| **Prometheus** | 부하테스트 메트릭 | 실시간 모니터링, 알림, 커스텀 메트릭 |
| **Grafana** | 시각화 | 대시보드, 시계열 분석 |

### Clean Architecture 준수

- **TelemetryConfigPort**: LangSmith 의존성을 Port로 추상화
- **PrometheusMetricsAdapter**: Prometheus 의존성을 Port로 추상화
- **NoOp 구현체**: 테스트 환경에서 메트릭 비활성화

### 핵심 메트릭

| 메트릭 | 용도 |
|--------|------|
| `chat_stream_active` | 동시 처리 스트림 수 (Capacity 모니터링) |
| `chat_stream_token_latency_seconds` | Redis XADD 지연시간 (인프라 병목 감지) |
| `chat_stream_duration_seconds` | 전체 스트림 소요시간 (SLO 추적) |
| `chat_stream_tokens_total` | 토큰 처리량 (처리량 추적) |

---

## 12. 참고 자료

### LangSmith
- [LangSmith Documentation](https://docs.smith.langchain.com/)
- [LangSmith Tracing](https://docs.smith.langchain.com/how_to_guides/tracing)

### Prometheus
- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Histogram Quantiles](https://prometheus.io/docs/practices/histograms/)

### Grafana
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)

---

*문서 버전: v1.0*
*최종 수정: 2026-01-16*
*커밋: `e6fd91e8` (feat: implement LangGraph native streaming with observability)*
