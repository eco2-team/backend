# Observability Setup Guide

> Chat Worker 부하테스트 및 피처별 성능 분석을 위한 Observability 설정 가이드

## 1. Prometheus Metrics (Token Streaming)

### 설정 필요 없음

Prometheus 메트릭은 자동으로 활성화됩니다. `/metrics` 엔드포인트에서 수집 가능합니다.

### 수집되는 메트릭

| 메트릭 | 타입 | 용도 |
|--------|------|------|
| `chat_stream_active` | Gauge | 동시 처리 중인 스트림 수 |
| `chat_stream_tokens_total` | Counter | 발행된 토큰 수 (node, status) |
| `chat_stream_requests_total` | Counter | 스트림 요청 수 (status) |
| `chat_stream_token_latency_seconds` | Histogram | Redis XADD 지연시간 (node) |
| `chat_stream_token_interval_seconds` | Histogram | 토큰 간 간격, LLM 속도 (provider) |
| `chat_stream_duration_seconds` | Histogram | 전체 스트림 소요시간 (node, status) |
| `chat_stream_token_count` | Histogram | 스트림당 토큰 수 (node) |
| `chat_stream_recovery_total` | Counter | 복구 시도 횟수 (type, status) |

### Grafana 대시보드

```bash
# 대시보드 파일 위치
docs/dashboards/chat-worker-token-streaming.json
```

Grafana UI에서 Import → Upload JSON file로 대시보드를 추가합니다.

---

## 2. LangSmith (LangGraph Native Observability)

### 환경변수 설정

```bash
# 필수
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-langsmith-api-key>

# 선택 (기본값: eco2-chat-worker)
export LANGCHAIN_PROJECT=eco2-chat-worker
export LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

### API Key 발급

1. https://smith.langchain.com 접속
2. Settings → API Keys → Create API Key
3. 환경변수에 설정

### Kubernetes Secret

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

### LangSmith 제공 메트릭

| 메트릭 | 설명 |
|--------|------|
| **Per-Node Latency** | intent, vision, waste_rag, character, answer 등 노드별 소요시간 |
| **Token Usage** | 노드별 input/output 토큰 수, 비용 추정 |
| **Run Timeline** | 병렬 실행 (Send API) 시각화 |
| **Error Tracking** | 노드별 에러율, 스택 트레이스 |
| **Feedback Loop** | RAG 품질 평가, Fallback 체인 추적 |

### LangSmith UI에서 필터링

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

---

## 3. OpenTelemetry (분산 추적)

### 환경변수 설정

```bash
# OTLP Exporter
export OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
export OTEL_SERVICE_NAME=chat-worker

# 또는 비활성화 (기본값)
# OTEL_EXPORTER_OTLP_ENDPOINT가 없으면 NoopTracer 사용
```

### LLM API 트레이싱 (OpenAI/Gemini)

LLM API 호출을 Jaeger에서 추적할 수 있습니다.

```bash
# chat_worker, scan_worker에서 자동 활성화
# 패키지 필요:
pip install opentelemetry-instrumentation-openai-v2
pip install opentelemetry-instrumentation-google-generativeai
```

**추적되는 정보**:
- Chat Completions (스트리밍 포함)
- Embeddings
- 토큰 사용량 메트릭
- 요청/응답 지연시간

### LangSmith → Jaeger 통합 (LangGraph 노드 추적)

LangGraph 파이프라인 트레이스를 Jaeger로 전송할 수 있습니다.

```bash
# LangSmith OTEL 모드 활성화
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY=<your-api-key>
export LANGSMITH_OTEL_ENABLED=true  # Jaeger로 전송

# 패키지 필요:
pip install "langsmith[otel]"
```

**End-to-End Trace 구조** (Jaeger에서 확인):
```
┌─────────────────────────────────────────────────────────────┐
│ chat-api (FastAPI)                                          │
│ └── POST /api/v1/chat                                       │
│     └── chat-worker (aio-pika)                              │
│         └── process_chat                                    │
│             └── LangGraph Pipeline (LangSmith OTEL)         │
│                 ├── intent_node                             │
│                 ├── waste_rag_node                          │
│                 │   └── OpenAI Embeddings                   │
│                 ├── character_node                          │
│                 └── answer_node                             │
│                     └── OpenAI Chat Completion (streaming)  │
└─────────────────────────────────────────────────────────────┘
```

### Jaeger UI

```
http://jaeger:16686
```

---

## 4. 부하테스트 시나리오

### Intent별 부하 분포

| Intent | 특성 | 예상 지연시간 |
|--------|------|---------------|
| `waste` | RAG + Feedback + Weather | 2-5s |
| `bulk_waste` | 외부 API (행정안전부) | 1-3s |
| `character` | gRPC | 50-200ms |
| `location` | 카카오맵 API | 200-500ms |
| `collection_point` | KECO API | 500ms-1s |
| `web_search` | DuckDuckGo/Tavily | 1-2s |
| `general` | LLM Only | 1-3s |

### k6 부하테스트 예시

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

### Grafana에서 확인

1. **Token Streaming Dashboard**: 실시간 토큰 처리량, 지연시간
2. **LangSmith Dashboard**: 노드별 상세 분석, 에러 추적
3. **k6 + Grafana**: 부하테스트 결과 시각화

---

## 5. 피처별 성능 기준 (SLO)

| 피처 | P50 | P95 | P99 |
|------|-----|-----|-----|
| Intent 분류 | 100ms | 300ms | 500ms |
| RAG 검색 | 500ms | 1s | 2s |
| 전체 응답 (waste) | 2s | 5s | 10s |
| 전체 응답 (general) | 1s | 3s | 5s |
| Token 발행 지연 | 5ms | 25ms | 50ms |

---

## 6. 체크리스트

### 개발 환경

- [ ] `prometheus_client` 설치 확인
- [ ] LangSmith API Key 발급
- [ ] 환경변수 설정

### 스테이징 환경

- [ ] Prometheus 연동 확인 (`/metrics`)
- [ ] LangSmith 트레이스 확인
- [ ] Grafana 대시보드 Import

### 프로덕션 환경

- [ ] Secret 관리 (LangSmith API Key)
- [ ] 알림 설정 (Prometheus Alertmanager)
- [ ] SLO 모니터링 설정
