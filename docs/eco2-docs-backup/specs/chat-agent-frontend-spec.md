# Chat Agent API Specification (Frontend)

> 프론트엔드 에이전트를 위한 Chat Agent 통합 상세 스펙

| 항목 | 값 |
|-----|-----|
| **버전** | v1.0 |
| **작성일** | 2026-01-16 |
| **Base URL** | `https://api.eco2.kr/api/v1` |
| **SSE Gateway** | `https://sse.eco2.kr` |

---

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Chat Agent Architecture                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Frontend                                                                    │
│  ├── POST /chat/{id}/messages  →  Chat API  →  RabbitMQ  →  Chat Worker    │
│  │                                                                          │
│  └── SSE /events/{job_id}  ←  SSE Gateway  ←  Redis Pub/Sub  ←  Worker     │
│                                                                              │
│  Flow:                                                                       │
│  1. 메시지 전송 → job_id 수신                                               │
│  2. SSE 연결 (job_id)                                                       │
│  3. 실시간 이벤트 수신 (stage, token, done)                                 │
│  4. 답변 완료 시 연결 종료                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. REST API Endpoints

### 2.1 채팅 목록 조회

```http
GET /chat
Authorization: Bearer {token}
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | 조회 개수 (1-100) |
| `cursor` | string | null | 페이징 커서 |

**Response:** `200 OK`
```json
{
  "chats": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "페트병 분리배출",
      "preview": "페트병은 내용물을 비우고...",
      "message_count": 5,
      "last_message_at": "2026-01-16T10:30:00Z",
      "created_at": "2026-01-16T10:00:00Z"
    }
  ],
  "next_cursor": "eyJsYXN0X2lkIjogIjEyMyJ9"
}
```

### 2.2 새 채팅 생성

```http
POST /chat
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "새 대화"  // 선택
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "title": null,
  "created_at": "2026-01-16T11:00:00Z"
}
```

### 2.3 채팅 상세 조회 (메시지 포함)

```http
GET /chat/{chat_id}
Authorization: Bearer {token}
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | 메시지 조회 개수 (1-200) |
| `before` | string | null | 이 시간 이전 메시지 |

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "페트병 분리배출",
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": "페트병 어떻게 버려?",
      "intent": null,
      "metadata": null,
      "created_at": "2026-01-16T10:00:00Z"
    },
    {
      "id": "msg-002",
      "role": "assistant",
      "content": "페트병은 다음과 같이 분리배출하세요...",
      "intent": "waste",
      "metadata": {
        "classification": "플라스틱-페트",
        "confidence": 0.95
      },
      "created_at": "2026-01-16T10:00:05Z"
    }
  ],
  "has_more": false,
  "created_at": "2026-01-16T10:00:00Z"
}
```

### 2.4 메시지 전송 (핵심 API)

```http
POST /chat/{chat_id}/messages
Authorization: Bearer {token}
Content-Type: application/json

{
  "message": "페트병 어떻게 버려?",
  "image_url": "https://cdn.eco2.kr/uploads/pet-bottle.jpg",  // 선택
  "user_location": {                                           // 선택
    "latitude": 37.5665,
    "longitude": 126.9780
  },
  "model": "gpt-5.2"  // 선택, 기본값 사용 권장
}
```

**Response:** `200 OK`
```json
{
  "job_id": "job-abc123",
  "stream_url": "https://sse.eco2.kr/events/job-abc123",
  "status": "submitted"
}
```

**Important:**
- `job_id`를 사용하여 SSE 연결
- DB 저장은 Worker 완료 후 배치로 처리 (Eventual Consistency)

### 2.5 채팅 삭제

```http
DELETE /chat/{chat_id}
Authorization: Bearer {token}
```

**Response:** `200 OK`
```json
{
  "success": true
}
```

### 2.6 Human-in-the-Loop 입력 제출

```http
POST /chat/{job_id}/input
Content-Type: application/json

{
  "type": "location",
  "data": {
    "latitude": 37.5665,
    "longitude": 126.9780
  }
}
```

**Input Types:**
| Type | Data | Description |
|------|------|-------------|
| `location` | `{latitude, longitude}` | 위치 정보 |
| `confirmation` | `{confirmed: boolean}` | 사용자 확인 |
| `cancel` | `null` | 작업 취소 |

**Response:** `200 OK`
```json
{
  "status": "received",
  "job_id": "job-abc123"
}
```

---

## 3. SSE Event Types

### 3.1 연결 방법

```javascript
const eventSource = new EventSource(
  `https://sse.eco2.kr/events/${jobId}`,
  { withCredentials: true }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleEvent(data);
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

### 3.2 이벤트 스키마

#### Stage Event (단계 진행)
```json
{
  "job_id": "job-abc123",
  "stage": "intent",
  "status": "completed",
  "seq": 11,
  "ts": "1705401600.123",
  "progress": 20,
  "message": "의도 분류 완료",
  "result": {
    "intent": "waste",
    "confidence": 0.95
  }
}
```

#### Token Event (답변 스트리밍)
```json
{
  "job_id": "job-abc123",
  "stage": "token",
  "status": "streaming",
  "seq": 1001,
  "ts": "1705401605.456",
  "content": "페트병"
}
```

#### Needs Input Event (Human-in-the-Loop)
```json
{
  "job_id": "job-abc123",
  "stage": "needs_input",
  "status": "waiting",
  "seq": 70,
  "ts": "1705401610.789",
  "message": "주변 분리수거 센터를 찾으려면 위치 정보가 필요합니다.",
  "result": {
    "input_type": "location",
    "timeout": 60
  }
}
```

#### Done Event (완료)
```json
{
  "job_id": "job-abc123",
  "stage": "done",
  "status": "completed",
  "seq": 61,
  "ts": "1705401620.000",
  "progress": 100,
  "message": "답변 생성 완료",
  "result": {
    "answer": "페트병은 다음과 같이 분리배출하세요...",
    "intent": "waste",
    "classification": "플라스틱-페트"
  }
}
```

### 3.3 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Pipeline Flow                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  queued → intent → [vision?] → [subagents...] → aggregate → answer → done   │
│                                     │                                        │
│                    ┌────────────────┼────────────────┐                      │
│                    │                │                │                      │
│              ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐               │
│              │   waste   │    │  location │    │  general  │               │
│              │  intent   │    │  intent   │    │  intent   │               │
│              └─────┬─────┘    └─────┬─────┘    └───────────┘               │
│                    │                │                                        │
│                   rag           location                                     │
│                    │            kakao_place                                  │
│                feedback          weather                                     │
│                    │                │                                        │
│                    └────────────────┘                                        │
│                            │                                                 │
│                        aggregate → answer → done                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**중요**: 모든 Stage가 항상 실행되는 것이 아닙니다!
- `vision`: 이미지 첨부 시에만 실행
- Subagents: intent 분류 결과에 따라 선택적/병렬 실행
- `feedback`: waste intent에서만 품질 평가

### 3.4 Stage 목록 (seq)

| Category | Stage | Base Seq | Description |
|----------|-------|----------|-------------|
| **Core** | `queued` | 0 | 작업 대기열 등록 |
| | `intent` | 10 | 의도 분류 |
| | `vision` | 20 | 이미지 분석 (첨부 시) |
| **Subagents** | `rag` | 30 | 폐기물 분류 RAG |
| | `character` | 40 | 캐릭터 정보 |
| | `location` | 50 | 센터 위치 (gRPC) |
| | `kakao_place` | 60 | 장소 검색 (Kakao) |
| | `bulk_waste` | 70 | 대형폐기물 정보 |
| | `weather` | 80 | 날씨 정보 |
| | `recyclable_price` | 90 | 재활용품 시세 |
| | `collection_point` | 100 | 수거함 위치 |
| | `web_search` | 110 | 웹 검색 |
| | `image_generation` | 120 | 이미지 생성 |
| **Final** | `aggregate` | 130 | 결과 병합 |
| | `feedback` | 140 | 품질 평가 |
| | `answer` | 150 | 답변 생성 |
| | `done` | 160 | 완료 |
| **Special** | `needs_input` | 170 | HITL 입력 대기 |
| | `token` | 1000+ | 토큰 스트리밍 |

---

## 4. 프론트엔드 구현 가이드

### 4.1 메시지 전송 플로우

```typescript
async function sendMessage(chatId: string, message: string) {
  // 1. 메시지 전송
  const response = await fetch(`/api/v1/chat/${chatId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });

  const { job_id, stream_url } = await response.json();

  // 2. SSE 연결
  const eventSource = new EventSource(stream_url);

  // 3. 이벤트 처리
  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.stage) {
      case 'intent':
        updateStatus('의도 분석 중...');
        break;

      case 'token':
        appendToAnswer(data.content);  // 실시간 텍스트 추가
        break;

      case 'needs_input':
        handleInputRequest(data);  // 위치 권한 요청 등
        break;

      case 'done':
        finalizeAnswer(data.result);
        eventSource.close();  // 연결 종료
        break;
    }
  };
}
```

### 4.2 Human-in-the-Loop 처리

```typescript
async function handleInputRequest(event: SSEEvent) {
  const { input_type, timeout } = event.result;

  if (input_type === 'location') {
    // 1. 위치 권한 요청 UI 표시
    showLocationPermissionDialog();

    // 2. Geolocation API 호출
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        timeout: timeout * 1000,
        enableHighAccuracy: true,
      });
    });

    // 3. 위치 정보 전송
    await fetch(`/api/v1/chat/${event.job_id}/input`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'location',
        data: {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        },
      }),
    });
  }
}
```

### 4.3 Multi-turn 대화

```typescript
// 채팅 상세 조회 시 이전 메시지 로드
async function loadChatHistory(chatId: string) {
  const response = await fetch(`/api/v1/chat/${chatId}?limit=50`);
  const { messages, has_more } = await response.json();

  // 메시지 렌더링
  messages.forEach(renderMessage);

  // 무한 스크롤 (더 있으면)
  if (has_more) {
    setupInfiniteScroll(chatId, messages[0].created_at);
  }
}

// 새 메시지 전송 (동일 chat_id 사용)
async function continueConversation(chatId: string, message: string) {
  // chat_id가 동일하면 서버에서 자동으로 컨텍스트 유지
  await sendMessage(chatId, message);
}
```

---

## 5. 에러 처리

### 5.1 HTTP 에러 코드

| Code | Description | Action |
|------|-------------|--------|
| `400` | Bad Request | 요청 데이터 검증 |
| `401` | Unauthorized | 로그인 페이지로 이동 |
| `403` | Forbidden | 권한 없음 (다른 사용자의 채팅) |
| `404` | Not Found | 채팅을 찾을 수 없음 |
| `429` | Too Many Requests | Rate Limit, 잠시 후 재시도 |
| `500` | Server Error | 에러 메시지 표시, 재시도 버튼 |

### 5.2 SSE 에러 이벤트

```json
{
  "job_id": "job-abc123",
  "stage": "intent",
  "status": "failed",
  "seq": 12,
  "message": "의도 분류 실패",
  "result": {
    "error": "LLM timeout"
  }
}
```

### 5.3 재연결 전략

```typescript
function connectSSE(jobId: string, retries = 3) {
  const eventSource = new EventSource(`/events/${jobId}`);

  eventSource.onerror = () => {
    eventSource.close();

    if (retries > 0) {
      setTimeout(() => {
        connectSSE(jobId, retries - 1);
      }, 1000 * (4 - retries));  // 1s, 2s, 3s 백오프
    } else {
      showErrorMessage('연결이 끊어졌습니다. 새로고침해주세요.');
    }
  };
}
```

---

## 6. 지원 기능

### 6.1 Intent Types & Stage 매핑

| Intent | Description | 실행되는 Stages |
|--------|-------------|-----------------|
| `waste` | 폐기물 분리배출 | `rag` → `feedback` |
| `bulk_waste` | 대형폐기물 | `bulk_waste` |
| `location` | 센터/수거함 위치 | `location` |
| `place_search` | 일반 장소 검색 | `kakao_place` |
| `collection_point` | 수거함 위치 | `collection_point` |
| `weather` | 날씨 기반 팁 | `weather` |
| `price` | 재활용품 시세 | `recyclable_price` |
| `web_search` | 웹 검색 | `web_search` |
| `image` | 이미지 생성 | `image_generation` |
| `greeting` | 인사/캐릭터 | `character` |
| `general` | 일반 질문 | (passthrough) |

**Multi-Intent 예시:**
- "페트병 버리는 곳 알려줘" → `waste` + `location`
- "오늘 날씨에 분리수거 해도 돼?" → `waste` + `weather`

Multi-intent의 경우 여러 Subagent가 **병렬**로 실행되며, `aggregate`에서 결과가 병합됩니다.

### 6.2 이미지 첨부

```typescript
// 이미지 업로드 후 URL 획득
const imageUrl = await uploadImage(file);

// 메시지와 함께 전송
await sendMessage(chatId, '이거 어떻게 버려?', {
  image_url: imageUrl,
});
```

**지원 형식:** JPEG, PNG, WebP
**최대 크기:** 10MB
**Vision 분석:** 자동 수행 (이미지 기반 폐기물 분류)

### 6.3 위치 기반 기능

위치 정보 제공 시 추가 기능:
- 주변 분리수거 센터 검색
- 주변 폐전자제품 수거함 검색
- 지역별 대형폐기물 수수료 안내
- 날씨 기반 분리배출 팁

---

## 7. 성능 권장사항

### 7.1 SSE 연결

- `done` 이벤트 수신 후 즉시 연결 종료
- 페이지 이탈 시 연결 정리 (`beforeunload`)
- 연결 타임아웃: 5분 (서버 설정)

### 7.2 토큰 스트리밍

- `requestAnimationFrame`으로 배치 렌더링
- 토큰 10개 이상 누적 시 한 번에 렌더링
- 입력 중 자동 스크롤

### 7.3 채팅 목록

- 커서 기반 페이지네이션 사용
- 캐시: 5분 TTL
- 새 메시지 도착 시 목록 상단으로 이동

---

## 8. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-01-16 | 최초 작성 |

---

*문서 버전: v1.0*
*최종 수정: 2026-01-16*
