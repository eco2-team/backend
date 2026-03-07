# Chat 세션 & 히스토리 API 스펙

> 프론트엔드 Chat 개편에 필요한 백엔드 API 요청 사항
> 관련 문서: `frontend/docs/plans/chat-agent-migration-plan.md`

---

## 1. 배경

프론트엔드 Chat UI를 ChatGPT 스타일로 개편 중입니다:
- 우측 사이드바에 세션 목록 (무한 스크롤)
- 대화 히스토리 위로 스크롤하며 조회
- 세션 제목은 첫 메시지 요약

현재 백엔드에는 세션/메시지 영속성이 없어 API 추가가 필요합니다.

---

## 2. 필요한 API 엔드포인트

### 2.1 세션 목록 조회

```
GET /api/v1/chat/sessions

Headers:
  X-User-ID: {user_id}  (Ext-Authz 주입)

Query Parameters:
  - cursor: string (선택) - 페이지네이션 커서
  - limit: int (선택, 기본 20, 최대 50)

Response 200:
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "페트병 분리배출 방법",
      "created_at": "2026-01-16T10:00:00Z",
      "updated_at": "2026-01-16T10:30:00Z",
      "message_count": 5,
      "preview": "페트병은 내용물을 비우고..."
    }
  ],
  "total": 50,
  "has_more": true,
  "next_cursor": "eyJpZCI6IjU1MGU4NDAw..."
}

정렬: updated_at DESC (최근 대화 먼저)
```

### 2.2 세션 생성

```
POST /api/v1/chat/sessions

Headers:
  X-User-ID: {user_id}

Request Body: (없음 또는 빈 객체)

Response 201:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "새 대화",
  "created_at": "2026-01-16T11:00:00Z",
  "updated_at": "2026-01-16T11:00:00Z",
  "message_count": 0
}
```

### 2.3 세션 삭제

```
DELETE /api/v1/chat/sessions/{session_id}

Headers:
  X-User-ID: {user_id}

Response 204: No Content

에러:
  - 404: 세션 없음
  - 403: 다른 사용자의 세션
```

### 2.4 메시지 히스토리 조회

```
GET /api/v1/chat/sessions/{session_id}/messages

Headers:
  X-User-ID: {user_id}

Query Parameters:
  - cursor: string (선택) - 페이지네이션 커서
  - limit: int (선택, 기본 50, 최대 100)

Response 200:
{
  "items": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "role": "user",
      "content": "페트병 어떻게 버려?",
      "type": "text",
      "image_url": null,
      "timestamp": "2026-01-16T10:00:00Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "role": "assistant",
      "content": "페트병은 내용물을 비우고 라벨을 제거한 후...",
      "type": "text",
      "image_url": null,
      "timestamp": "2026-01-16T10:00:05Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440003",
      "role": "user",
      "content": "",
      "type": "image",
      "image_url": "https://cdn.example.com/uploads/pet-bottle.jpg",
      "timestamp": "2026-01-16T10:01:00Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440004",
      "role": "assistant",
      "content": "분리배출 안내 이미지입니다.",
      "type": "generated_image",
      "image_url": "https://cdn.example.com/generated/guide-123.png",
      "timestamp": "2026-01-16T10:01:10Z"
    }
  ],
  "total": 100,
  "has_more": true,
  "next_cursor": "eyJ0cyI6IjIwMjYtMDEt..."
}

정렬: timestamp DESC (최신 먼저, 프론트에서 reverse)
용도: 위로 스크롤 시 이전 메시지 로드
```

---

## 3. 기존 API 수정

### 3.1 POST /api/v1/chat

```diff
Request Body:
{
+ "session_id": "550e8400-...",  // 필수 (신규)
  "message": "페트병 어떻게 버려?",
  "image_url": null,
  "user_location": null,
  "model": null
}

변경 사항:
1. session_id 필수 파라미터로 추가
2. 사용자 메시지를 chat.messages 테이블에 저장
3. sessions.updated_at, message_count 업데이트
```

### 3.2 SSE done 이벤트 시

```
Chat Worker에서 done 이벤트 발행 시:
1. 어시스턴트 응답을 chat.messages 테이블에 저장
2. sessions.updated_at, message_count 업데이트
3. (첫 메시지인 경우) 세션 title 자동 생성
```

### 3.3 SSE 이벤트 result 필드 요구사항 (Thinking UI용)

프론트엔드 Thinking UI 표시를 위해 각 stage 이벤트의 `result` 필드에 다음 데이터가 필요합니다.

#### intent:completed 이벤트

```json
{
  "stage": "intent",
  "status": "completed",
  "result": {
    "intent": "waste",
    "complexity": "simple",
    "confidence": 0.98,
    "has_multi_intent": true,
    "additional_intents": ["location"],
    "decomposed_queries": ["페트병 어떻게 버려?", "근처 센터는?"]
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `intent` | string | 주 의도 (9가지 중 하나) |
| `complexity` | string | `simple` 또는 `complex` |
| `confidence` | float | 신뢰도 (0.0 ~ 1.0) |
| `has_multi_intent` | bool | 복합 의도 여부 |
| `additional_intents` | string[] | 추가 의도 목록 |
| `decomposed_queries` | string[] | 분해된 쿼리 (Multi-Intent 시) |

#### rag:completed 이벤트

```json
{
  "stage": "rag",
  "status": "completed",
  "result": {
    "found": true,
    "count": 2,
    "method": "keco_search"
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `found` | bool | 검색 결과 존재 여부 |
| `count` | int | 검색된 규정 수 |
| `method` | string | 검색 방법 |

#### location:completed 이벤트 (위치 검색 시)

```json
{
  "stage": "location",
  "status": "completed",
  "result": {
    "found": true,
    "count": 3,
    "source": "kakao_map"
  }
}
```

#### done:completed 이벤트

```json
{
  "stage": "done",
  "status": "completed",
  "result": {
    "intent": "waste",
    "answer": "페트병은 내용물을 비우고...",
    "generated_image_url": null
  }
}
```

**현재 상태**: 대부분 이미 구현됨. `decomposed_queries` 필드 전달 여부 확인 필요.

---

## 4. DB 스키마

### 4.1 세션 테이블

```sql
CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE chat.sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL DEFAULT '새 대화',  -- 표준 없음 → TEXT 사용
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 비정규화: 조회 성능을 위해 message_count 캐싱
    -- 실제 값은 messages 테이블 COUNT로 계산 가능
    message_count INT NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_user FOREIGN KEY (user_id)
        REFERENCES users.accounts(id) ON DELETE CASCADE
);

-- 인덱스: 세션 목록 조회 (user별 최신순, soft delete 제외)
CREATE INDEX idx_sessions_user_updated
    ON chat.sessions(user_id, updated_at DESC)
    WHERE is_deleted = FALSE;
```

### 4.2 메시지 테이블

```sql
CREATE TABLE chat.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    job_id UUID,  -- SSE job_id (디버깅/추적용)

    -- 메시지 메타데이터: CHECK 제약으로 값 검증
    role VARCHAR(10) NOT NULL,   -- 'user' | 'assistant'
    type VARCHAR(20) NOT NULL DEFAULT 'text',  -- 'text' | 'image' | 'generated_image'

    -- 메시지 내용
    content TEXT NOT NULL,
    image_url TEXT,  -- type이 'image' 또는 'generated_image'일 때만 사용

    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 제약조건
    CONSTRAINT fk_session FOREIGN KEY (session_id)
        REFERENCES chat.sessions(id) ON DELETE CASCADE,
    CONSTRAINT chk_role CHECK (role IN ('user', 'assistant')),
    CONSTRAINT chk_type CHECK (type IN ('text', 'image', 'generated_image'))
);

-- 인덱스: 히스토리 조회 (세션별 최신순)
CREATE INDEX idx_messages_session_ts
    ON chat.messages(session_id, timestamp DESC);
```

### 4.3 메시지 타입 설명

| type | role | 설명 |
|------|------|------|
| `text` | user | 사용자 텍스트 메시지 |
| `text` | assistant | AI 텍스트 응답 |
| `image` | user | 사용자가 업로드한 이미지 |
| `generated_image` | assistant | AI가 생성한 이미지 |

---

## 5. 세션 제목 자동 생성

### 요구사항

첫 사용자 메시지를 기반으로 세션 제목 자동 생성 (ChatGPT 스타일)

```
입력: "페트병 어떻게 버려요? 라벨은 떼야 하나요?"
출력: "페트병 분리배출 방법"

입력: "음식물 쓰레기 버리는 법 알려줘"
출력: "음식물 쓰레기 처리"
```

### 구현 옵션

| 옵션 | 방식 | 장점 | 단점 |
|------|------|------|------|
| A | Intent 분류 시 함께 생성 | 추가 LLM 호출 없음 | Intent 노드 수정 필요 |
| B | done 이벤트 후 비동기 생성 | 응답 지연 없음 | 별도 Worker 필요 |
| C | 단순 truncate (LLM 없이) | 구현 간단 | 품질 낮음 |

**추천**: 옵션 A 또는 C (초기에는 C로 시작, 추후 A로 개선)

```python
# 옵션 C: 단순 구현
def generate_title(first_message: str) -> str:
    # 첫 문장만 추출, 최대 30자
    title = first_message.split('.')[0].split('?')[0][:30]
    return title.strip() + ('...' if len(first_message) > 30 else '')
```

---

## 6. 작업 우선순위

| 순서 | 작업 | 예상 복잡도 | 의존성 |
|------|------|------------|--------|
| 1 | DB 스키마 생성 | 낮음 | 없음 |
| 2 | 메시지 저장 로직 (Chat API + Worker) | 중간 | 1 |
| 3 | `GET /sessions` | 낮음 | 1 |
| 4 | `GET /sessions/{id}/messages` | 낮음 | 1, 2 |
| 5 | `POST /sessions` | 낮음 | 1 |
| 6 | `DELETE /sessions/{id}` | 낮음 | 1 |
| 7 | 세션 제목 자동 생성 | 중간 | 2 |

---

## 7. 타입 정의 (참고)

```python
# apps/chat/application/chat/dto/session_dto.py

from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class ChatSessionResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    preview: str | None = None


class ChatSessionsResponse(BaseModel):
    items: list[ChatSessionResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str  # 'user' | 'assistant'
    content: str
    type: str  # 'text' | 'image' | 'generated_image'
    image_url: str | None = None  # type이 'image' 또는 'generated_image'일 때
    timestamp: datetime


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
    has_more: bool
    next_cursor: str | None = None
```

---

## 8. 질문 사항

프론트엔드 개발 진행을 위해 확인이 필요한 사항:

1. **커서 페이지네이션 vs 오프셋**: 커서 방식 괜찮은지?
2. **세션 제목 생성 방식**: 옵션 A/B/C 중 선호하는 방식?
3. **soft delete vs hard delete**: 세션 삭제 시 `is_deleted` 플래그 vs 실제 삭제?
4. **예상 일정**: 언제쯤 API 사용 가능할지?

---

**작성일**: 2026-01-16
**요청자**: 프론트엔드 팀
**관련 PR**: (추후 연결)
