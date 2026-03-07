# Distributed Tracing: OpenTelemetry로 분산 시스템 추적하기

> **Part VII: 운영과 품질** | [← 14. Idempotent Consumer](./14-idempotent-consumer-patterns.md) | [인덱스](./00-index.md)

> 참고: [OpenTelemetry Documentation](https://opentelemetry.io/docs/)  
> 참고: [W3C Trace Context](https://www.w3.org/TR/trace-context/)

---

## 들어가며

분산 시스템에서 **하나의 요청이 여러 서비스를 거쳐 처리**된다. 문제가 발생했을 때 "어디서 느려졌는지", "어디서 에러가 났는지" 찾기가 매우 어렵다.

```
┌─────────────────────────────────────────────────────────────┐
│               분산 시스템 디버깅의 어려움                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  사용자 요청: "스캔 결과가 안 와요"                         │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │ API GW   │──▶│ Scan API │──▶│ RabbitMQ │               │
│  └──────────┘   └──────────┘   └────┬─────┘               │
│                                      │                      │
│                                      ▼                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │  Kafka   │◀──│ Celery   │──▶│Vision API│               │
│  └────┬─────┘   │ Worker   │   └──────────┘               │
│       │         └──────────┘                                │
│       ▼                                                     │
│  ┌──────────┐   ┌──────────┐                               │
│  │Character │──▶│   My     │                               │
│  │ Consumer │   │ Consumer │                               │
│  └──────────┘   └──────────┘                               │
│                                                             │
│  문제:                                                      │
│  • 로그가 각 서비스에 흩어져 있음                          │
│  • 어떤 요청이 어디까지 갔는지 모름                        │
│  • 병목이 어디인지 찾기 어려움                             │
│  • "이 에러가 어떤 요청 때문인지?" 연결 불가               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Distributed Tracing**은 이 문제를 해결한다. 요청에 고유 ID를 부여하고, 모든 서비스가 이 ID를 전파하여 **전체 흐름을 하나의 타임라인으로 시각화**한다.

---

## 핵심 개념

### Trace, Span, Context

```
┌─────────────────────────────────────────────────────────────┐
│                Trace, Span, Context                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Trace: 하나의 요청 전체 흐름                               │
│  ─────────────────────────────                              │
│  trace_id: abc-123                                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Span A: API Gateway (parent=none)                  │   │
│  │  ├─────────────────────────────────────────────┤   │   │
│  │  │ 0ms                                    100ms│   │   │
│  │                                                     │   │
│  │    Span B: Scan API (parent=A)                      │   │
│  │    ├───────────────────────────────────┤           │   │
│  │    │ 10ms                          90ms│           │   │
│  │                                                     │   │
│  │      Span C: RabbitMQ Publish (parent=B)            │   │
│  │      ├─────────┤                                   │   │
│  │      │20ms 30ms│                                   │   │
│  │                                                     │   │
│  │      Span D: Celery Task (parent=B)                 │   │
│  │      ├─────────────────────────────┤               │   │
│  │      │ 30ms                    80ms│               │   │
│  │                                                     │   │
│  │        Span E: Vision API (parent=D)                │   │
│  │        ├───────────────┤                           │   │
│  │        │ 35ms      60ms│                           │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Span: 하나의 작업 단위                                     │
│  • span_id: 고유 식별자                                    │
│  • parent_span_id: 부모 Span                               │
│  • operation_name: 작업 이름                               │
│  • start_time, end_time: 시작/종료 시각                    │
│  • attributes: 추가 정보 (user_id, task_id 등)            │
│  • events: Span 내 이벤트 (로그)                           │
│  • status: OK, ERROR                                       │
│                                                             │
│  Context: trace_id + span_id + 전파 정보                   │
│  • 서비스 간 전달되는 메타데이터                           │
│  • HTTP Header, Kafka Header, Task Header로 전파           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### W3C Trace Context 표준

```
┌─────────────────────────────────────────────────────────────┐
│                W3C Trace Context                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  HTTP Header로 Context 전파:                                │
│                                                             │
│  traceparent: 00-{trace_id}-{span_id}-{flags}              │
│               │    │          │        │                   │
│               │    │          │        └─ 01=sampled       │
│               │    │          └─ 현재 span_id (16자리)     │
│               │    └─ trace_id (32자리)                    │
│               └─ version                                   │
│                                                             │
│  예시:                                                      │
│  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-         │
│               00f067aa0ba902b7-01                          │
│                                                             │
│  tracestate: vendor1=value1,vendor2=value2                 │
│  → 벤더별 추가 정보 (optional)                             │
│                                                             │
│  장점:                                                      │
│  • 업계 표준 (모든 벤더 지원)                              │
│  • 언어/프레임워크 독립적                                  │
│  • 자동 전파 라이브러리 풍부                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## OpenTelemetry 아키텍처

### 구성 요소

```
┌─────────────────────────────────────────────────────────────┐
│              OpenTelemetry Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Application                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│   │
│  │  │   Traces    │  │   Metrics   │  │    Logs     ││   │
│  │  │   (추적)    │  │   (지표)    │  │   (로그)    ││   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘│   │
│  │         │                │                │       │   │
│  │         └────────────────┼────────────────┘       │   │
│  │                          │                         │   │
│  │                          ▼                         │   │
│  │  ┌─────────────────────────────────────────────┐  │   │
│  │  │           OpenTelemetry SDK                  │  │   │
│  │  │                                              │  │   │
│  │  │  • Auto-instrumentation (자동 계측)         │  │   │
│  │  │  • Manual instrumentation (수동 계측)       │  │   │
│  │  │  • Context Propagation (컨텍스트 전파)      │  │   │
│  │  └──────────────────────┬──────────────────────┘  │   │
│  │                          │                         │   │
│  └──────────────────────────┼─────────────────────────┘   │
│                             │ OTLP                        │
│                             ▼                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              OpenTelemetry Collector                 │   │
│  │                                                     │   │
│  │  Receivers ──▶ Processors ──▶ Exporters            │   │
│  │  (수신)        (가공)         (내보내기)            │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       │                                     │
│       ┌───────────────┼───────────────┐                    │
│       ▼               ▼               ▼                    │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│  │  Jaeger │    │  Tempo  │    │Prometheus│                │
│  │ (Trace) │    │ (Trace) │    │(Metrics) │                │
│  └─────────┘    └─────────┘    └─────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### SDK vs Collector

| 구성 요소 | 역할 | 위치 |
|----------|------|------|
| **SDK** | 애플리케이션에서 데이터 수집 | 앱 내부 |
| **Collector** | 데이터 수신, 가공, 내보내기 | 별도 프로세스/사이드카 |

### Auto-Instrumentation

```python
# 자동 계측: 라이브러리 패치로 코드 수정 없이 추적

# 설치
# pip install opentelemetry-instrumentation-fastapi
# pip install opentelemetry-instrumentation-httpx
# pip install opentelemetry-instrumentation-celery
# pip install opentelemetry-instrumentation-kafka-python
# pip install opentelemetry-instrumentation-redis

# LLM API 계측
# pip install opentelemetry-instrumentation-openai-v2
# pip install opentelemetry-instrumentation-google-generativeai

# 자동 계측 활성화
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor

FastAPIInstrumentor.instrument()
CeleryInstrumentor.instrument()

# 이후 모든 FastAPI 요청, Celery Task가 자동으로 추적됨
```

### LLM API Instrumentation

```python
# LLM API 호출 추적 (OpenAI, Gemini)

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.instrumentation.google_generativeai import GoogleGenerativeAiInstrumentor

# OpenAI 계측 (Chat Completions, Embeddings, 스트리밍)
OpenAIInstrumentor().instrument()

# Gemini 계측 (generateContent, 스트리밍)
GoogleGenerativeAiInstrumentor().instrument()

# 추적되는 정보:
# - 요청/응답 지연시간
# - 토큰 사용량
# - 모델명, 프롬프트 (선택)
# - 에러 및 재시도
```

### LangGraph + OpenTelemetry (LangSmith OTEL)

```python
# LangGraph 파이프라인 트레이스를 Jaeger로 전송

# 환경변수 설정
# export LANGCHAIN_TRACING_V2=true
# export LANGCHAIN_API_KEY=<your-api-key>
# export LANGSMITH_OTEL_ENABLED=true  # OTEL 모드

# pip install "langsmith[otel]"

# 결과: LangGraph 각 노드가 Jaeger Span으로 표시됨
# → intent_node, waste_rag_node, answer_node 등
```

---

## 컨텍스트 전파 패턴

### HTTP → HTTP

```
┌─────────────────────────────────────────────────────────────┐
│                  HTTP → HTTP 전파                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Service A                        Service B                 │
│  ┌──────────────────┐            ┌──────────────────┐      │
│  │                  │            │                  │      │
│  │  # 자동 전파     │            │  # 자동 추출     │      │
│  │  response =      │            │  @app.get("/")   │      │
│  │    httpx.get(    │──Headers──▶│  def handler():  │      │
│  │      "http://b", │            │    # 자동으로    │      │
│  │    )             │            │    # trace 연결  │      │
│  │                  │            │                  │      │
│  └──────────────────┘            └──────────────────┘      │
│                                                             │
│  Headers:                                                   │
│  traceparent: 00-abc123...-def456...-01                    │
│                                                             │
│  OpenTelemetry SDK가 자동으로:                              │
│  • 요청 시: Header에 Context 주입                          │
│  • 수신 시: Header에서 Context 추출                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### HTTP → Kafka

```
┌─────────────────────────────────────────────────────────────┐
│                  HTTP → Kafka 전파                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API Server                                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                                                      │  │
│  │  from opentelemetry import trace                     │  │
│  │  from opentelemetry.propagate import inject          │  │
│  │                                                      │  │
│  │  @app.post("/scan")                                  │  │
│  │  async def create_scan():                            │  │
│  │      # 현재 Span의 Context를 Header로 변환           │  │
│  │      headers = {}                                    │  │
│  │      inject(headers)                                 │  │
│  │                                                      │  │
│  │      # Kafka 메시지 발행                             │  │
│  │      await producer.send(                            │  │
│  │          "scan.tasks",                               │  │
│  │          value={"task_id": "..."},                   │  │
│  │          headers=headers,  # ← Context 포함         │  │
│  │      )                                               │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Kafka Message Headers:                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ traceparent: 00-abc123...-def456...-01              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Consumer                                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                                                      │  │
│  │  from opentelemetry.propagate import extract         │  │
│  │                                                      │  │
│  │  async def consume(message):                         │  │
│  │      # Header에서 Context 추출                       │  │
│  │      context = extract(message.headers)              │  │
│  │                                                      │  │
│  │      # 추출한 Context를 부모로 새 Span 생성         │  │
│  │      with tracer.start_as_current_span(              │  │
│  │          "process_scan",                             │  │
│  │          context=context,                            │  │
│  │      ) as span:                                      │  │
│  │          await process(message)                      │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Kafka → Celery

```
┌─────────────────────────────────────────────────────────────┐
│                  Kafka → Celery 전파                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Kafka Consumer (Scan API)                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                                                      │  │
│  │  async def on_scan_request(message):                 │  │
│  │      context = extract(message.headers)              │  │
│  │                                                      │  │
│  │      with tracer.start_as_current_span(              │  │
│  │          "dispatch_ai_task", context=context         │  │
│  │      ):                                              │  │
│  │          # Celery Task에 Context 전달                │  │
│  │          headers = {}                                │  │
│  │          inject(headers)                             │  │
│  │                                                      │  │
│  │          process_image.apply_async(                  │  │
│  │              args=[task_id, image_url],              │  │
│  │              headers=headers,  # ← Context 포함     │  │
│  │          )                                           │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Celery Worker                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                                                      │  │
│  │  # CeleryInstrumentor가 자동으로 headers에서         │  │
│  │  # Context를 추출하여 Span 생성                      │  │
│  │                                                      │  │
│  │  @celery_app.task(bind=True)                         │  │
│  │  def process_image(self, task_id, image_url):        │  │
│  │      # 자동으로 부모 Span에 연결됨                   │  │
│  │      with tracer.start_as_current_span("vision_api"):│  │
│  │          result = call_vision_api(image_url)         │  │
│  │                                                      │  │
│  │      with tracer.start_as_current_span("llm_api"):   │  │
│  │          answer = call_llm_api(result)               │  │
│  │                                                      │  │
│  │      return answer                                   │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 구조화 로깅과 통합

### trace_id를 로그에 주입

```
┌─────────────────────────────────────────────────────────────┐
│              Trace-Log 상관관계                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  문제: 로그와 Trace가 분리되어 있음                        │
│  ─────                                                      │
│  Trace: task-123이 느림                                    │
│  → 해당 task의 상세 로그를 찾으려면?                       │
│  → trace_id로 검색해야 함                                  │
│                                                             │
│  해결: 모든 로그에 trace_id 포함                           │
│  ─────                                                      │
│                                                             │
│  import structlog                                           │
│  from opentelemetry import trace                            │
│                                                             │
│  def add_trace_context(logger, method, event_dict):         │
│      """로그에 trace_id, span_id 자동 추가"""              │
│      span = trace.get_current_span()                        │
│      if span:                                               │
│          ctx = span.get_span_context()                      │
│          event_dict["trace_id"] = format(ctx.trace_id, "032x")
│          event_dict["span_id"] = format(ctx.span_id, "016x")│
│      return event_dict                                      │
│                                                             │
│  structlog.configure(                                       │
│      processors=[                                           │
│          add_trace_context,  # ← 추가                      │
│          structlog.processors.JSONRenderer(),               │
│      ]                                                      │
│  )                                                          │
│                                                             │
│  결과 로그:                                                 │
│  {                                                          │
│    "event": "Processing scan",                             │
│    "task_id": "abc-123",                                   │
│    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",        │
│    "span_id": "00f067aa0ba902b7",                          │
│    "timestamp": "2025-12-19T10:00:00Z"                     │
│  }                                                          │
│                                                             │
│  → Grafana에서 trace_id로 로그 검색 가능                   │
│  → Trace 뷰에서 바로 관련 로그 확인 가능                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### EFK + Trace 연동

```
┌─────────────────────────────────────────────────────────────┐
│              EFK + Grafana Tempo 연동                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐                                           │
│  │ Application │                                           │
│  │             │                                           │
│  │ Logs ───────┼───▶ Fluentd ───▶ Elasticsearch           │
│  │ (trace_id)  │                        │                  │
│  │             │                        │                  │
│  │ Traces ─────┼───▶ OTel Collector ───▶ Grafana Tempo    │
│  │             │                        │                  │
│  └─────────────┘                        │                  │
│                                          ▼                  │
│                              ┌─────────────────────┐       │
│                              │      Grafana        │       │
│                              │                     │       │
│                              │ ┌─────────────────┐│       │
│                              │ │ Trace View      ││       │
│                              │ │                 ││       │
│                              │ │ Span A ─────────││       │
│                              │ │   Span B ───────││       │
│                              │ │     Span C ─────││       │
│                              │ │                 ││       │
│                              │ │ [View Logs] ────┼┼───┐   │
│                              │ └─────────────────┘│   │   │
│                              │                     │   │   │
│                              │ ┌─────────────────┐│   │   │
│                              │ │ Logs (ES)       │◀───┘   │
│                              │ │                 ││       │
│                              │ │ trace_id로 필터 ││       │
│                              │ └─────────────────┘│       │
│                              └─────────────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 시각화 도구

### Jaeger

```
┌─────────────────────────────────────────────────────────────┐
│                       Jaeger                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  특징:                                                      │
│  • CNCF 프로젝트 (졸업)                                    │
│  • 독립 실행형                                              │
│  • 자체 스토리지 (Cassandra, Elasticsearch)                │
│  • 분산 컨텍스트 전파                                      │
│                                                             │
│  Kubernetes 배포:                                           │
│  # Jaeger Operator 사용                                    │
│  apiVersion: jaegertracing.io/v1                           │
│  kind: Jaeger                                               │
│  metadata:                                                  │
│    name: eco2-jaeger                                       │
│  spec:                                                      │
│    strategy: production                                    │
│    storage:                                                 │
│      type: elasticsearch                                   │
│      options:                                               │
│        es:                                                  │
│          server-urls: http://elasticsearch:9200            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Grafana Tempo

```
┌─────────────────────────────────────────────────────────────┐
│                    Grafana Tempo                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  특징:                                                      │
│  • Grafana Labs 프로젝트                                   │
│  • 오브젝트 스토리지 기반 (S3, GCS, MinIO)                │
│  • 인덱싱 없음 → 비용 효율적                              │
│  • Grafana와 네이티브 통합                                 │
│  • Loki, Prometheus와 상관관계                             │
│                                                             │
│  Kubernetes 배포:                                           │
│  # Helm으로 설치                                           │
│  helm install tempo grafana/tempo \                        │
│    --set tempo.storage.trace.backend=s3 \                  │
│    --set tempo.storage.trace.s3.bucket=eco2-traces         │
│                                                             │
│  Grafana 연동:                                              │
│  • Tempo → Trace 시각화                                    │
│  • Loki → 로그 (trace_id 연결)                            │
│  • Prometheus → 메트릭                                     │
│  • 세 데이터 소스가 trace_id로 연결됨                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 비교

| 기준 | Jaeger | Grafana Tempo |
|------|--------|---------------|
| **스토리지** | Cassandra/ES | Object Storage |
| **인덱싱** | 있음 | 없음 |
| **비용** | 높음 (인덱싱) | 낮음 |
| **검색** | 다양한 필터 | trace_id만 |
| **Grafana 통합** | 플러그인 | 네이티브 |
| **권장** | 소규모, 독립 실행 | 대규모, Grafana 사용 중 |

---

## 참고 자료

- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Grafana Tempo](https://grafana.com/oss/tempo/)
- [Jaeger](https://www.jaegertracing.io/)

---

## 부록: Eco² 적용 포인트

### AI 파이프라인 전체 추적

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² AI Pipeline Tracing                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Trace: scan-request-abc                                    │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  │ POST /scan (50ms)                                       │
│  ├─ validate_request (5ms)                                 │
│  ├─ create_task (10ms)                                     │
│  ├─ publish_to_rabbitmq (5ms)                              │
│  │                                                         │
│  │ celery.process_image (5000ms)                           │
│  ├─ vision_scan (2000ms)                                   │
│  │  └─ gemini.generateContent (1900ms)   ← Gemini 추적   │
│  ├─ rule_match (500ms)                                     │
│  ├─ answer_gen (2500ms)                                    │
│  │  └─ openai.chat.completions (2400ms)  ← OpenAI 추적   │
│  │                                                         │
│  │ save_to_event_store (20ms)                              │
│  │                                                         │
│  │ kafka.publish (10ms)                                    │
│  │                                                         │
│  │ character.consumer (100ms)                              │
│  ├─ handle_scan_completed (50ms)                           │
│  │  └─ grant_reward (30ms)                                │
│  └─ publish_character_granted (10ms)                       │
│                                                             │
│  Total: 5180ms                                              │
│  Bottleneck: vision_api (39%), llm_api (46%)               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### OpenTelemetry 설정

```python
# domains/_shared/observability/tracing.py

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_tracing(service_name: str):
    """OpenTelemetry 초기화"""

    # 1. Resource 설정 (서비스 식별)
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "eco2",
        "deployment.environment": settings.ENVIRONMENT,
    })

    # 2. TracerProvider 설정
    provider = TracerProvider(resource=resource)

    # 3. Exporter 설정 (OTLP → Collector)
    exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_COLLECTOR_ENDPOINT,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    # 4. 전역 TracerProvider 설정
    trace.set_tracer_provider(provider)

    # 5. Auto-instrumentation (HTTP, MQ, Cache)
    FastAPIInstrumentor.instrument()
    CeleryInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()
    RedisInstrumentor().instrument()

    # 6. LLM API Instrumentation (OpenAI, Gemini)
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
        OpenAIInstrumentor().instrument()
    except ImportError:
        pass

    try:
        from opentelemetry.instrumentation.google_generativeai import GoogleGenerativeAiInstrumentor
        GoogleGenerativeAiInstrumentor().instrument()
    except ImportError:
        pass

    return trace.get_tracer(service_name)


# 사용
tracer = setup_tracing("scan-api")
```

### Kafka Context 전파

```python
# domains/_shared/messaging/kafka_tracing.py

from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

propagator = TraceContextTextMapPropagator()

class TracedKafkaProducer:
    """Context를 전파하는 Kafka Producer"""
    
    def __init__(self, producer):
        self.producer = producer
        self.tracer = trace.get_tracer(__name__)
    
    async def send(self, topic: str, value: dict, key: str = None):
        with self.tracer.start_as_current_span(
            f"kafka.produce.{topic}",
            kind=trace.SpanKind.PRODUCER,
        ) as span:
            # Span에 메타데이터 추가
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            
            # Header에 Context 주입
            headers = {}
            inject(headers)
            
            # 메시지 발행
            await self.producer.send(
                topic,
                value=json.dumps(value).encode(),
                key=key.encode() if key else None,
                headers=[(k, v.encode()) for k, v in headers.items()],
            )


class TracedKafkaConsumer:
    """Context를 추출하는 Kafka Consumer"""
    
    def __init__(self, consumer):
        self.consumer = consumer
        self.tracer = trace.get_tracer(__name__)
    
    async def handle(self, message):
        # Header에서 Context 추출
        headers = {k: v.decode() for k, v in message.headers or []}
        context = extract(headers)
        
        # 부모 Context를 연결하여 Span 생성
        with self.tracer.start_as_current_span(
            f"kafka.consume.{message.topic}",
            context=context,
            kind=trace.SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", message.topic)
            
            # 비즈니스 로직
            await self.process(message)
```

### Celery Task Tracing

```python
# domains/scan/tasks/ai_pipeline.py

from opentelemetry import trace
from opentelemetry.propagate import inject, extract

tracer = trace.get_tracer(__name__)

@celery_app.task(bind=True, max_retries=3)
def process_image(self, task_id: str, image_url: str):
    """AI 파이프라인 (추적 포함)"""
    
    # Celery headers에서 Context 추출 (CeleryInstrumentor가 자동 처리)
    # 수동으로 하려면:
    # context = extract(self.request.headers or {})
    
    with tracer.start_as_current_span("vision_scan") as span:
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.step", "vision")
        
        result = vision_api.analyze(image_url)
        span.set_attribute("vision.category", result["category"])
    
    with tracer.start_as_current_span("rule_match") as span:
        span.set_attribute("task.step", "rule")
        
        rules = rule_engine.match(result)
    
    with tracer.start_as_current_span("answer_gen") as span:
        span.set_attribute("task.step", "answer")
        
        answer = llm_api.generate({"vision": result, "rules": rules})
    
    return {"classification": result, "answer": answer}
```

### scan_id ↔ trace_id 매핑

```python
# API 응답에 trace_id 포함

from opentelemetry import trace

@app.post("/scan")
async def create_scan(request: ScanRequest):
    span = trace.get_current_span()
    trace_id = format(span.get_span_context().trace_id, "032x")
    
    task = await scan_service.create(request)
    
    return {
        "task_id": task.id,
        "status": "processing",
        "trace_id": trace_id,  # ← 디버깅용
    }

# 클라이언트가 trace_id를 받아 Grafana에서 조회 가능
```

### AS-IS vs TO-BE

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-----------------------------------|
| **추적 범위** | gRPC 호출 단위 | 전체 요청 흐름 |
| **Context 전파** | gRPC Metadata | W3C Trace Context |
| **로그 연결** | 수동 (request_id) | 자동 (trace_id) |
| **비동기 추적** | 불가 | Kafka/Celery 전파 |
| **시각화** | 없음 | Grafana Tempo |
| **병목 분석** | 로그 분석 | Span 타임라인 |
