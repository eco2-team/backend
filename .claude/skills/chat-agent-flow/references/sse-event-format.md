# SSE Event Format Reference

> **Last Updated**: 2026-01-19
> **검증됨**: E2E 테스트 완료 (223 token events)

## Overview

SSE Gateway에서 클라이언트로 전달되는 이벤트 형식 문서입니다.
Token streaming이 `stream_mode="messages"` 기반으로 구현되어 실시간 토큰 스트리밍이 가능합니다.

---

## Event Types

### 1. `token` - 토큰 스트리밍 이벤트

**실시간 LLM 토큰 스트리밍** - 가장 중요한 이벤트

```
event: token
data: {"content":"유","seq":1001,"node":"answer"}

event: token
data: {"content":"리","seq":1002,"node":"answer"}

event: token
data: {"content":"병","seq":1003,"node":"answer"}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `content` | string | 토큰 텍스트 (UTF-8 인코딩됨) |
| `seq` | number | 시퀀스 번호 (1001부터 시작, 연속 증가) |
| `node` | string | 생성 노드 ("answer") |

**특징**:
- `seq`는 1001부터 시작 (1000 이하는 stage 이벤트용)
- 토큰은 UTF-8 escape될 수 있음 (`\uXXXX` 형식)
- 빈 content는 전송되지 않음

---

### 2. `token_recovery` - 토큰 복구 이벤트

**늦게 구독한 클라이언트용 스냅샷** - SSE 연결이 늦어진 경우

```
event: token_recovery
data: {
  "stage": "token_recovery",
  "status": "snapshot",
  "accumulated": "무색 **음료/생수 페트병(PET)**이라면 **투명(무색) 페트병 전용 수거함**으로 분리배출하면 돼요 ♻️\n\n배출 방법은 이렇게 하면 깔끔해:\n1) **내용물 비우기** → 2) **라벨 떼기** → ...",
  "last_seq": 1175,
  "completed": true
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `stage` | string | "token_recovery" |
| `status` | string | "snapshot" |
| `accumulated` | string | 지금까지 누적된 전체 답변 텍스트 |
| `last_seq` | number | 마지막 토큰의 seq 번호 |
| `completed` | boolean | 답변 생성 완료 여부 |

**사용 시나리오**:
- 클라이언트가 SSE 연결을 늦게 시작한 경우
- 네트워크 끊김 후 재연결시
- `completed: true`면 추가 토큰 없음, `accumulated`로 전체 답변 표시

---

### 3. `intent` - Intent 분류 이벤트

```
event: intent
data: {
  "job_id": "79d0f98c-5b77-4455-96cd-2eb409620612",
  "stage": "intent",
  "status": "completed",
  "seq": 10,
  "ts": "1768800397.123456",
  "progress": 10,
  "result": {"intent": "waste", "confidence": 0.95},
  "message": "Intent 분류 완료"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `job_id` | string | 작업 ID (UUID) |
| `stage` | string | "intent" |
| `status` | string | "started" \| "completed" |
| `seq` | number | 시퀀스 번호 (< 1000) |
| `progress` | number | 진행률 (0-100) |
| `result` | object | Intent 분류 결과 |

---

### 4. `router` - 라우팅 이벤트

```
event: router
data: {
  "job_id": "79d0f98c-5b77-4455-96cd-2eb409620612",
  "stage": "router",
  "status": "completed",
  "seq": 991,
  "ts": "1768800397.281926",
  "progress": 20,
  "result": "",
  "message": "router completed"
}
```

---

### 5. `answer` - 답변 생성 이벤트

```
event: answer
data: {
  "job_id": "79d0f98c-5b77-4455-96cd-2eb409620612",
  "stage": "answer",
  "status": "started",
  "seq": 160,
  "ts": "1768800401.4270668",
  "progress": 75,
  "message": "답변을 생성하고 있습니다..."
}

event: answer
data: {
  "job_id": "79d0f98c-5b77-4455-96cd-2eb409620612",
  "stage": "answer",
  "status": "completed",
  "seq": 161,
  "ts": "1768800401.4288013",
  "progress": 95,
  "message": "답변 생성 완료"
}
```

---

### 6. `done` - 작업 완료 이벤트

**전체 파이프라인 완료** - 최종 결과 포함

```
event: done
data: {
  "job_id": "79d0f98c-5b77-4455-96cd-2eb409620612",
  "stage": "done",
  "status": "completed",
  "seq": 171,
  "ts": "1768800401.4457195",
  "progress": 100,
  "result": {
    "intent": "waste",
    "answer": "무색 **음료/생수 페트병(PET)**이라면...",
    "persistence": {
      "conversation_id": "96a34b5b-6462-477c-b907-71f87f49b7d4",
      "user_id": "8b8ec006-2d95-45aa-bdef-e08201f1bb82",
      "user_message": "플라스틱 페트병 분리배출 방법 알려줘",
      "assistant_message": "무색 **음료/생수 페트병(PET)**이라면..."
    }
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `result.intent` | string | 최종 intent |
| `result.answer` | string | 전체 답변 텍스트 |
| `result.persistence` | object | 저장된 메시지 정보 |

---

### 7. `keepalive` - 연결 유지

```
event: keepalive
data: {"timestamp": ""}
```

---

### 8. `ping` (Comment)

SSE 주석 형식의 ping:

```
: ping - 2026-01-19 05:28:52.965281+00:00
```

---

## Event Sequence (정상 흐름)

```
1. event: queued       (seq: ~1)      → 작업 대기열 등록
2. event: intent       (seq: ~10)     → Intent 분류
3. event: router       (seq: ~991)    → 라우팅 완료
4. event: answer       (seq: ~160)    → 답변 생성 시작
5. event: token        (seq: 1001+)   → 토큰 스트리밍 (실시간!)
   event: token        (seq: 1002)
   event: token        (seq: 1003)
   ...
   event: token        (seq: ~1175)
6. event: answer       (completed)    → 답변 생성 완료
7. event: done         (seq: ~171)    → 전체 완료 + 최종 결과
```

---

## Frontend Integration

### TypeScript Types

```typescript
// SSE 이벤트 타입
type SSEEventType =
  | 'token'           // 실시간 토큰 스트리밍
  | 'token_recovery'  // 늦은 구독자용 스냅샷
  | 'intent'          // Intent 분류
  | 'router'          // 라우팅
  | 'answer'          // 답변 생성 상태
  | 'done'            // 완료
  | 'error'           // 에러
  | 'keepalive';      // 연결 유지

// 토큰 이벤트
interface TokenEvent {
  content: string;    // 토큰 텍스트
  seq: number;        // 시퀀스 번호 (1001~)
  node: string;       // "answer"
}

// 토큰 복구 이벤트
interface TokenRecoveryEvent {
  stage: 'token_recovery';
  status: 'snapshot';
  accumulated: string;  // 누적된 전체 답변
  last_seq: number;     // 마지막 seq
  completed: boolean;   // 완료 여부
}

// Stage 이벤트 (intent, router, answer, done)
interface StageEvent {
  job_id: string;
  stage: string;
  status: 'started' | 'completed';
  seq: number;
  ts: string;
  progress: number;
  result: any;
  message: string;
}
```

### EventSource 사용 예시

```typescript
const eventSource = new EventSource(
  `${SSE_BASE_URL}/sse/conversations/${conversationId}/stream`,
  { withCredentials: true }
);

// 토큰 스트리밍 처리
eventSource.addEventListener('token', (event) => {
  const data: TokenEvent = JSON.parse(event.data);
  appendToMessage(data.content);  // 실시간 UI 업데이트
});

// 토큰 복구 (늦은 구독)
eventSource.addEventListener('token_recovery', (event) => {
  const data: TokenRecoveryEvent = JSON.parse(event.data);
  if (data.completed) {
    setMessage(data.accumulated);  // 전체 답변으로 대체
  }
});

// 완료 처리
eventSource.addEventListener('done', (event) => {
  const data: StageEvent = JSON.parse(event.data);
  finalizeMessage(data.result.answer);
  eventSource.close();
});

// 에러 처리
eventSource.addEventListener('error', (event) => {
  console.error('SSE Error:', event);
  eventSource.close();
});
```

---

## Sequence Number Rules

| Range | 용도 |
|-------|------|
| 1-999 | Stage 이벤트 (intent, router, answer, done) |
| 1001+ | Token 이벤트 (1001부터 연속 증가) |

---

## Stage별 프론트엔드 UI 메시지 가이드

각 stage 이벤트에 대응하는 프론트엔드 안내 메시지입니다.
ChatGPT 스타일의 "Thinking UI"에서 사용합니다.

### Stage → 안내 메시지 매핑

| Stage | Status | 안내 메시지 (한글) | result 활용 |
|-------|--------|-------------------|-------------|
| **queued** | started | "질문을 받았어요" | - |
| **intent** | started | "질문을 분석하고 있어요" | - |
| **intent** | completed | "{INTENT_LABEL}(으)로 판단했어요" | `result.intent` → INTENT_LABELS 매핑 |
| **router** | completed | "정보를 찾고 있어요" | - |
| **rag** | started | "관련 규정을 찾고 있어요" | - |
| **rag** | completed | "규정 {count}건을 찾았어요" | `result.count` |
| **vision** | started | "이미지를 분석하고 있어요" | - |
| **vision** | completed | "{major_category}(으)로 분석했어요" | `result.major_category` |
| **bulk_waste** | started | "대형폐기물 정보를 찾고 있어요" | - |
| **bulk_waste** | completed | "대형폐기물 정보를 찾았어요" | `result.has_fees` |
| **collection_point** | started | "수거함 위치를 찾고 있어요" | - |
| **collection_point** | completed | "수거함 {count}곳을 찾았어요" | `result.count` |
| **kakao_place** | started | "장소를 검색하고 있어요" | - |
| **kakao_place** | completed | "장소 {count}곳을 찾았어요" | `result.count` |
| **recyclable_price** | started | "재활용 시세를 확인하고 있어요" | - |
| **recyclable_price** | completed | "시세 정보를 찾았어요" | `result.found` |
| **web_search** | started | "웹에서 검색하고 있어요" | - |
| **web_search** | completed | "검색 결과 {count}건을 찾았어요" | `result.count` |
| **weather** | started | "날씨 정보를 확인하고 있어요" | - |
| **weather** | completed | "날씨 정보를 가져왔어요" | `result.temperature` |
| **location** | started | "위치를 확인하고 있어요" | - |
| **location** | completed | "위치를 확인했어요" | `result.found` |
| **image_generation** | started | "이미지를 생성하고 있어요" | - |
| **image_generation** | completed | "이미지를 생성했어요" | `result.image_url` |
| **aggregate** | completed | "정보를 취합하고 있어요" | `result.collected` |
| **feedback** | completed | (표시 안 함) | - |
| **answer** | started | "답변을 작성하고 있어요" | - |
| **answer** | completed | (토큰 스트리밍으로 대체) | - |
| **done** | completed | (완료 - UI 숨김) | `result.answer` |
| **error** | - | "문제가 발생했어요. 다시 시도해주세요" | `result.error` |

### Intent 라벨 매핑

```typescript
const INTENT_LABELS: Record<string, string> = {
  waste: '분리배출 안내',
  character: '캐릭터 정보',
  location: '위치 검색',
  bulk_waste: '대형폐기물 안내',
  recyclable_price: '시세 조회',
  collection_point: '수거함 위치',
  web_search: '웹 검색',
  image_generation: '이미지 생성',
  general: '일반 대화',
};
```

### 프론트엔드 구현 예시

```typescript
// Stage 이벤트 핸들러
function getStageMessage(stage: string, status: string, result?: any): string | null {
  const messages: Record<string, Record<string, string | ((r: any) => string)>> = {
    queued: { started: '질문을 받았어요' },
    intent: {
      started: '질문을 분석하고 있어요',
      completed: (r) => `${INTENT_LABELS[r?.intent] || '질문'}(으)로 판단했어요`,
    },
    router: { completed: '정보를 찾고 있어요' },
    rag: {
      started: '관련 규정을 찾고 있어요',
      completed: (r) => r?.count ? `규정 ${r.count}건을 찾았어요` : '규정을 찾았어요',
    },
    vision: {
      started: '이미지를 분석하고 있어요',
      completed: (r) => r?.major_category ? `${r.major_category}(으)로 분석했어요` : '분석 완료',
    },
    collection_point: {
      started: '수거함 위치를 찾고 있어요',
      completed: (r) => r?.count ? `수거함 ${r.count}곳을 찾았어요` : '수거함을 찾았어요',
    },
    answer: { started: '답변을 작성하고 있어요' },
    error: { '*': '문제가 발생했어요. 다시 시도해주세요' },
  };

  const stageMessages = messages[stage];
  if (!stageMessages) return null;

  const msgOrFn = stageMessages[status] || stageMessages['*'];
  if (!msgOrFn) return null;

  return typeof msgOrFn === 'function' ? msgOrFn(result) : msgOrFn;
}

// 사용 예시
eventSource.addEventListener('intent', (event) => {
  const data = JSON.parse(event.data);
  const message = getStageMessage(data.stage, data.status, data.result);
  if (message) setThinkingMessage(message);
});
```

### Thinking UI 상태 흐름

```
[사용자 메시지 전송]
     ↓
"질문을 받았어요"          ← queued.started
     ↓
"질문을 분석하고 있어요"    ← intent.started
     ↓
"분리배출 안내로 판단했어요" ← intent.completed (result.intent 활용)
     ↓
"관련 규정을 찾고 있어요"   ← rag.started
     ↓
"규정 3건을 찾았어요"      ← rag.completed (result.count 활용)
     ↓
"답변을 작성하고 있어요"    ← answer.started
     ↓
[토큰 스트리밍 시작]       ← token events (실시간 타이핑)
     ↓
[답변 완료]               ← done.completed
```

---

## Notes

1. **UTF-8 Encoding**: 토큰 content는 UTF-8로 인코딩됨 (`\uXXXX` escape)
2. **Token Recovery**: 늦게 연결해도 `accumulated`로 전체 내용 복구 가능
3. **Seq 연속성**: token seq가 건너뛰면 네트워크 손실 감지 가능
4. **done 이벤트**: 항상 마지막에 전체 결과 포함 (fallback용)
5. **token 필터링**: `node="answer"` 토큰만 사용자에게 표시 (intent 노드 토큰 무시)
