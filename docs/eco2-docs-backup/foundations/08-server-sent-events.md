# Server-Sent Events (SSE)

> SSE는 HTTP 기반의 단방향 서버→클라이언트 실시간 스트리밍 프로토콜입니다.  
> WebSocket보다 단순하고, 실시간 진행 상황 전달에 적합합니다.

---

## 공식 자료

### W3C/WHATWG 표준

| 문서 | URL | 내용 |
|------|-----|------|
| **HTML Living Standard - Server-sent events** | [html.spec.whatwg.org](https://html.spec.whatwg.org/multipage/server-sent-events.html) | 공식 스펙 |
| **EventSource API** | [MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/EventSource) | 클라이언트 API |

### HTTP 관련

| RFC | 제목 | 관련 내용 |
|-----|------|---------|
| RFC 7230 | HTTP/1.1 Message Syntax | Transfer-Encoding: chunked |
| RFC 9110 | HTTP Semantics | Content-Type, Cache-Control |

### 프레임워크 문서

| 프레임워크 | URL | 내용 |
|-----------|-----|------|
| **FastAPI** | [fastapi.tiangolo.com/.../streaming](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse) | StreamingResponse |
| **Starlette** | [starlette.io/.../responses](https://www.starlette.io/responses/#streamingresponse) | SSE 구현 |

---

## 핵심 개념

### 1. SSE vs WebSocket vs Polling

```
┌─────────────────────────────────────────────────────────────────┐
│  통신 방식 비교                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Polling:                                                        │
│  Client ──GET──→ Server                                          │
│  Client ──GET──→ Server   (주기적 반복)                          │
│  Client ──GET──→ Server                                          │
│  ✗ 불필요한 요청, 지연                                           │
│                                                                  │
│  Long Polling:                                                   │
│  Client ──GET──→ Server ──(대기)──→ Response                     │
│  Client ──GET──→ Server ──(대기)──→ Response                     │
│  △ 개선되었지만 여전히 비효율적                                   │
│                                                                  │
│  WebSocket:                                                      │
│  Client ←──────────→ Server  (양방향)                            │
│  ✓ 실시간, 양방향                                                │
│  ✗ 프록시/로드밸런서 호환성 이슈                                  │
│                                                                  │
│  SSE:                                                            │
│  Client ←─────────── Server  (단방향)                            │
│  ✓ HTTP 기반, 단순, 재연결 자동                                  │
│  ✓ 로드밸런서/프록시 호환                                        │
│  ✗ 단방향만 (클라이언트→서버는 별도 요청)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. SSE 선택 기준

| 요구사항 | SSE | WebSocket |
|---------|-----|-----------|
| 서버→클라이언트 단방향 | ✅ 최적 | ○ 가능 |
| 양방향 실시간 | ✗ | ✅ 최적 |
| HTTP 인프라 호환 | ✅ | △ 프록시 주의 |
| 자동 재연결 | ✅ 내장 | ✗ 직접 구현 |
| 바이너리 데이터 | ✗ 텍스트만 | ✅ |
| 브라우저 지원 | ✅ 네이티브 | ✅ |

**Eco² 선택**: SSE
- AI 파이프라인 진행 상황 = 서버→클라이언트 단방향
- OpenAI 스트리밍 API와 동일 패턴
- HTTP/ALB/Istio 호환

---

### 3. SSE 프로토콜 형식

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: stage
data: {"step": "vision", "status": "started", "progress": 0}

event: stage
data: {"step": "vision", "status": "completed", "progress": 25}

event: stage
data: {"step": "rule", "status": "started", "progress": 25}

: keepalive comment (클라이언트에 전달되지 않음)

event: ready
data: {"result_url": "/result/abc123"}
```

#### 필드 설명

| 필드 | 설명 | 예시 |
|------|------|------|
| `event:` | 이벤트 타입 (선택) | `event: stage` |
| `data:` | 이벤트 데이터 (필수) | `data: {"step": "vision"}` |
| `id:` | 이벤트 ID (재연결용) | `id: 1735123456789` |
| `retry:` | 재연결 간격 (ms) | `retry: 3000` |
| `:` | 주석 (keepalive) | `: keepalive` |

#### 이벤트 구분

```
이벤트는 빈 줄로 구분:

data: first event

data: second event

data: multiline
data: event
```

---

### 4. 클라이언트 구현

#### JavaScript (브라우저)

```javascript
const evtSource = new EventSource('/api/v1/scan/classify/completion', {
  // POST는 EventSource가 지원하지 않음
  // fetch + ReadableStream 사용
});

evtSource.addEventListener('stage', (event) => {
  const data = JSON.parse(event.data);
  console.log(`Stage: ${data.step}, Status: ${data.status}`);
  updateProgressBar(data.progress);
});

evtSource.addEventListener('ready', (event) => {
  const data = JSON.parse(event.data);
  console.log('Result:', data.result_url);
  evtSource.close();
});

evtSource.onerror = (err) => {
  console.error('SSE Error:', err);
  // 자동 재연결 시도됨
};
```

#### POST 요청 + SSE (fetch API)

```javascript
// EventSource는 GET만 지원
// POST가 필요하면 fetch + ReadableStream 사용

async function streamClassification(imageUrl) {
  const response = await fetch('/api/v1/scan/classify/completion', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_url: imageUrl }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    // SSE 파싱
    const lines = text.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        handleEvent(data);
      }
    }
  }
}
```

---

### 5. 서버 구현 (FastAPI)

#### 기본 패턴

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

def format_sse(data: dict, event: str = "message") -> str:
    """SSE 형식으로 변환."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@app.post("/stream")
async def stream_endpoint():
    async def generate():
        for i in range(5):
            yield format_sse({"progress": i * 25}, event="stage")
            await asyncio.sleep(1)
        
        yield format_sse({"result": "done"}, event="ready")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        },
    )
```

#### Keepalive 패턴

```python
async def generate_with_keepalive():
    """타임아웃 방지를 위한 keepalive."""
    async for event in event_source:
        if event is None:
            # 이벤트 없음 → keepalive 전송
            yield ": keepalive\n\n"
        else:
            yield format_sse(event)
```

---

## 인프라 고려사항

### 1. Nginx/로드밸런서 버퍼링

```nginx
# Nginx: 버퍼링 비활성화 필수
location /api/v1/scan/classify/completion {
    proxy_pass http://backend;
    proxy_buffering off;           # 버퍼링 비활성화
    proxy_cache off;               # 캐시 비활성화
    proxy_read_timeout 3600s;      # 긴 연결 허용
    proxy_http_version 1.1;        # HTTP/1.1 필수
    proxy_set_header Connection ""; 
}
```

### 2. Istio/Envoy 설정

```yaml
# VirtualService: 타임아웃 연장
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
spec:
  http:
    - match:
        - uri:
            prefix: /api/v1/scan/classify/completion
      route:
        - destination:
            host: scan-api
      timeout: 0s  # 무제한 (SSE)
```

### 3. AWS ALB

```yaml
# ALB 타겟 그룹 설정
DeregistrationDelay: 300
IdleTimeout: 4000  # SSE용 긴 타임아웃 (최대 4000초)
```

---

## Eco² SSE 패턴

### 파이프라인 진행 상황 스트리밍

```
┌─────────────────────────────────────────────────────────────────┐
│  Client UX                                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  POST /classify/completion                                       │
│       │                                                          │
│       ▼                                                          │
│  ┌────────────────────────────────────────┐                     │
│  │  🔍 찾는 중...                         │ ← vision started    │
│  │  ████░░░░░░░░░░░░░░░░  25%             │                     │
│  └────────────────────────────────────────┘                     │
│       │                                                          │
│       ▼ (vision completed)                                       │
│  ┌────────────────────────────────────────┐                     │
│  │  📚 규칙 확인 중...                     │ ← rule started     │
│  │  ████████░░░░░░░░░░░░  50%             │                     │
│  └────────────────────────────────────────┘                     │
│       │                                                          │
│       ▼ (rule completed)                                         │
│  ┌────────────────────────────────────────┐                     │
│  │  💭 정리 중...                          │ ← answer started   │
│  │  ████████████░░░░░░░░  75%             │                     │
│  └────────────────────────────────────────┘                     │
│       │                                                          │
│       ▼ (answer completed, reward completed)                     │
│  ┌────────────────────────────────────────┐                     │
│  │  ✅ 완료!                               │ ← ready event      │
│  │  ████████████████████  100%            │                     │
│  │  [결과 보기]                            │                     │
│  └────────────────────────────────────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 이벤트 타입

| event | 의미 | data 구조 |
|-------|------|---------|
| `stage` | 단계 시작/완료 | `{step, status, progress}` |
| `ready` | 파이프라인 완료 | `{result, result_url}` |
| `error` | 오류 발생 | `{error, message}` |

### OpenAI 스타일 매핑

| 내부 Stage | OpenAI 스타일 | 설명 |
|-----------|--------------|------|
| vision | Thinking... | 이미지 분석 |
| rule | Searching... | 규칙 검색 |
| answer | Writing... | 답변 생성 |
| reward | Finishing... | 보상 처리 |
| done | Done | 완료 |

---

## 연결 관리

### 1. 연결 수명 관리

```python
# 최대 연결 시간 제한
MAX_SSE_DURATION = 300  # 5분

async def generate():
    start_time = time.time()
    
    async for event in event_source:
        if time.time() - start_time > MAX_SSE_DURATION:
            yield format_sse({"error": "timeout"}, event="error")
            break
        
        yield format_sse(event)
```

### 2. 클라이언트 연결 해제 감지

```python
from starlette.requests import Request

@app.post("/stream")
async def stream(request: Request):
    async def generate():
        try:
            async for event in event_source:
                if await request.is_disconnected():
                    # 클라이언트 연결 해제됨
                    break
                yield format_sse(event)
        finally:
            # 정리 작업
            cleanup()
    
    return StreamingResponse(generate(), ...)
```

### 3. 연결 수 모니터링

```python
from prometheus_client import Gauge

SSE_CONNECTIONS_ACTIVE = Gauge(
    'sse_connections_active',
    'Number of active SSE connections',
    ['endpoint']
)

async def generate():
    SSE_CONNECTIONS_ACTIVE.labels(endpoint='/completion').inc()
    try:
        async for event in event_source:
            yield format_sse(event)
    finally:
        SSE_CONNECTIONS_ACTIVE.labels(endpoint='/completion').dec()
```

---

## 관련 문서

### Eco² 구현

- [#13 SSE 50 VU 병목 분석](../blogs/async/23-sse-bottleneck-analysis-50vu.md)
- [#14 Redis Streams SSE 전환](../blogs/async/24-redis-streams-sse-migration.md)
- [#11 SSE Performance Benchmark](../blogs/async/22-scan-sse-performance-benchmark.md)

### Foundations

- [07-redis-streams.md](./07-redis-streams.md) - 이벤트 소싱 백엔드
- [05-event-loop-fundamentals.md](./05-event-loop-fundamentals.md) - 비동기 I/O

### 외부 자료

- [HTML Standard - Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [MDN - EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

---

## 버전 정보

- 작성일: 2025-12-25
- 적용 대상: Eco² Scan SSE Pipeline

