# ADR: Voice Integration with gpt-audio

> Chat Worker에 음성 입출력 기능 추가

**작성일**: 2026-01-17
**상태**: Draft
**관련 문서**:
- [LangGraph Native Streaming ADR](./langgraph-native-streaming-adr.md)
- [Chat Worker Production Architecture ADR](./chat-worker-production-architecture-adr.md)

---

## 1. 배경

### 1.1 현재 상태

Eco² Chat은 텍스트 기반 대화만 지원:

```
사용자 (텍스트) → Chat API → Chat Worker → 텍스트 응답
```

### 1.2 요구사항

- 음성 입력: 사용자가 음성으로 질문
- 음성 출력: 봇이 음성으로 응답
- 기존 기능 유지: RAG, 위치 검색, 날씨 등 Subagent 기능

### 1.3 목표

1. **음성 대화 지원**: Speech-to-Speech 기능
2. **기존 파이프라인 활용**: LangGraph + Subagent 로직 재사용
3. **점진적 도입**: 텍스트/음성 선택 가능

---

## 2. 모델 선택

### 2.1 OpenAI Audio 모델 비교

| 모델 | API | Input | Output | Tool Calling | 실시간 | 상태 |
|------|-----|-------|--------|--------------|--------|------|
| `gpt-audio` | Chat Completions | Text/Audio | Text/Audio | ✅ | ❌ | GA |
| `gpt-audio-mini` | Chat Completions | Text/Audio | Text/Audio | ✅ | ❌ | GA |
| `gpt-realtime` | Realtime (WebSocket) | Text/Audio | Text/Audio | ✅ | ✅ | GA |
| `gpt-4o-audio-preview` | Chat Completions | Text/Audio | Text/Audio | ✅ | ❌ | Preview |

### 2.2 선택: gpt-audio (또는 gpt-audio-mini)

**선택 이유**:

| 기준 | gpt-audio | gpt-realtime |
|------|-----------|--------------|
| **API 호환성** | Chat Completions (기존 코드 재사용) | WebSocket (새 인프라 필요) |
| **Tool Calling** | ✅ 지원 | ✅ 지원 |
| **구현 복잡도** | 낮음 | 높음 (WebSocket Gateway) |
| **지연 시간** | ~1-3초 (비동기) | ~300ms (실시간) |
| **비용** | 표준 | 높음 (연결 유지) |
| **안정성** | GA | GA |

**결론**: 초기 구현은 `gpt-audio`로 시작, 실시간 요구 시 `gpt-realtime` 추가 고려

### 2.3 가격 (2025년 기준)

| 타입 | Input | Output |
|------|-------|--------|
| Text | $5/1M tokens | $20/1M tokens |
| Audio | $100/1M tokens (~$0.06/분) | $200/1M tokens (~$0.24/분) |

---

## 3. 아키텍처 옵션

### 3.1 Option A: 기존 파이프라인 + Audio Modality

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Option A: LangGraph Pipeline 확장                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [Frontend]                                                              │
│      │                                                                   │
│      ├── text ───────────────────────────────────────┐                  │
│      │                                                │                  │
│      └── audio (base64) ─→ [Chat API]                │                  │
│                                 │                     │                  │
│                                 ▼                     │                  │
│                           [RabbitMQ]                  │                  │
│                                 │                     │                  │
│                                 ▼                     │                  │
│                         [Chat Worker]                 │                  │
│                                 │                     │                  │
│           ┌─────────────────────┼─────────────────────┘                  │
│           │                     │                                        │
│           ▼                     ▼                                        │
│      [STT Node]           [Intent Node]                                  │
│      (audio→text)              │                                         │
│           │                    ▼                                         │
│           └──────────→ [Subagent Nodes]                                  │
│                               │                                          │
│                               ▼                                          │
│                        [Answer Node]                                     │
│                     (gpt-audio with audio output)                        │
│                               │                                          │
│                        ┌──────┴──────┐                                   │
│                        │             │                                   │
│                      text         audio                                  │
│                        │             │                                   │
│                        ▼             ▼                                   │
│                   [Redis Streams]                                        │
│                        │                                                 │
│                   [SSE Gateway]                                          │
│                   (text + audio chunks)                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**장점**:
- 기존 LangGraph 파이프라인 재사용
- Intent 분류, Subagent 로직 유지
- 점진적 마이그레이션 가능

**단점**:
- STT → Intent → Subagents → Answer 순차 처리로 지연 증가
- Audio 스트리밍 구현 복잡

### 3.2 Option B: gpt-audio + Tool Calling (단순화)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Option B: gpt-audio Direct + Tools                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [Frontend]                                                              │
│      │                                                                   │
│      └── audio (base64) ─→ [Chat API]                                   │
│                                 │                                        │
│                                 ▼                                        │
│                           [RabbitMQ]                                     │
│                                 │                                        │
│                                 ▼                                        │
│                    ┌────────────────────────┐                            │
│                    │      Chat Worker       │                            │
│                    │                        │                            │
│                    │   gpt-audio            │                            │
│                    │      │                 │                            │
│                    │      ├─→ tool_call: waste_rag(query)               │
│                    │      ├─→ tool_call: get_weather(loc)               │
│                    │      ├─→ tool_call: search_location(kw)            │
│                    │      ├─→ tool_call: get_collection_point(...)      │
│                    │      └─→ tool_call: get_character_info(...)        │
│                    │                        │                            │
│                    │   Tool Results ────────┘                            │
│                    │      │                                              │
│                    │      ▼                                              │
│                    │   Audio Response                                    │
│                    └────────────────────────┘                            │
│                                 │                                        │
│                          ┌──────┴──────┐                                 │
│                          │             │                                 │
│                        text         audio                                │
│                          │             │                                 │
│                          ▼             ▼                                 │
│                     [Redis Streams]                                      │
│                          │                                               │
│                     [SSE Gateway]                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**장점**:
- 단순한 구조
- gpt-audio가 Intent 분류 + 응답 생성 통합
- Tool Calling으로 기존 비즈니스 로직 재사용
- 빠른 PoC 가능

**단점**:
- LangGraph 파이프라인 우회
- 기존 Intent 분류 로직 마이그레이션 필요
- Tool 정의 및 관리 필요

### 3.3 Option C: Hybrid (텍스트/음성 분리)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Option C: Hybrid Approach                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [Frontend]                                                              │
│      │                                                                   │
│      ├── text ──→ [기존 Chat Pipeline] ──→ text response                │
│      │                                                                   │
│      └── audio ─→ [Voice Pipeline] ──→ audio response                   │
│                          │                                               │
│                          ▼                                               │
│                   [Voice Worker]                                         │
│                   (gpt-audio + Tools)                                    │
│                          │                                               │
│                   Tools: waste_rag, weather, location, ...              │
│                   (기존 Subagent 로직 공유)                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**장점**:
- 기존 텍스트 파이프라인 영향 없음
- 독립적인 Voice Worker
- A/B 테스트 용이

**단점**:
- 두 파이프라인 유지 필요
- 코드 중복 가능성

---

## 4. 권장 구현 방안

### 4.1 Phase 1: PoC (Option B)

빠른 검증을 위해 `gpt-audio + Tool Calling` 방식으로 시작:

```python
# apps/chat_worker/infrastructure/llm/voice_client.py

class VoiceClient:
    """gpt-audio 기반 음성 대화 클라이언트."""

    def __init__(self, tools: list[dict]):
        self.client = AsyncOpenAI()
        self.tools = tools
        self.model = "gpt-audio"  # 또는 gpt-audio-mini

    async def process_voice(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        voice: str = "alloy",
        system_prompt: str | None = None,
    ) -> VoiceResponse:
        """음성 입력 처리 및 음성 응답 생성."""

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Audio input
        messages.append({
            "role": "user",
            "content": [{
                "type": "input_audio",
                "input_audio": {
                    "data": base64.b64encode(audio_data).decode(),
                    "format": audio_format,
                }
            }]
        })

        # Initial request
        response = await self.client.chat.completions.create(
            model=self.model,
            modalities=["text", "audio"],
            audio={"voice": voice, "format": "mp3"},
            tools=self.tools,
            messages=messages,
        )

        # Tool calling loop
        while response.choices[0].message.tool_calls:
            tool_results = await self._execute_tools(
                response.choices[0].message.tool_calls
            )
            messages.append(response.choices[0].message)
            messages.extend(tool_results)

            response = await self.client.chat.completions.create(
                model=self.model,
                modalities=["text", "audio"],
                audio={"voice": voice, "format": "mp3"},
                tools=self.tools,
                messages=messages,
            )

        return VoiceResponse(
            text=response.choices[0].message.content,
            audio_data=base64.b64decode(response.choices[0].message.audio.data),
            audio_format="mp3",
        )
```

### 4.2 Phase 2: Tool 정의

기존 Subagent 로직을 Tool로 노출:

```python
# apps/chat_worker/infrastructure/tools/voice_tools.py

VOICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_waste_disposal",
            "description": "폐기물 분리배출 방법을 검색합니다. 재활용, 일반쓰레기, 음식물쓰레기 등의 올바른 버리는 방법을 안내합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색할 폐기물 이름 또는 질문"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "현재 날씨 정보를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "위치 (예: 서울, 강남구)"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_recycling_center",
            "description": "주변 재활용 센터나 분리수거함 위치를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "검색 위치"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["recycling_center", "collection_box", "all"],
                        "description": "시설 유형"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bulk_waste_info",
            "description": "대형폐기물 배출 방법과 수수료를 안내합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "대형폐기물 품목 (예: 소파, 냉장고)"
                    },
                    "district": {
                        "type": "string",
                        "description": "거주 지역 (구/군)"
                    }
                },
                "required": ["item"]
            }
        }
    }
]
```

### 4.3 Phase 3: SSE Audio Streaming

```python
# apps/chat_worker/application/ports/events/progress_notifier.py

class ProgressNotifierPort(Protocol):
    # 기존 메서드...

    async def notify_audio_chunk(
        self,
        task_id: str,
        chunk: bytes,
        format: str = "mp3",
        seq: int = 0,
    ) -> None:
        """오디오 청크 이벤트 발행."""
        ...

    async def notify_audio_complete(
        self,
        task_id: str,
        total_duration_ms: int,
    ) -> None:
        """오디오 스트리밍 완료 이벤트."""
        ...
```

### 4.4 Phase 4: API 확장

```python
# apps/chat/api/v1/voice.py

@router.post("/voice")
async def process_voice(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    voice: str = Form(default="alloy"),
) -> VoiceJobResponse:
    """음성 입력 처리 엔드포인트."""

    audio_data = await file.read()
    job_id = str(uuid.uuid4())

    # RabbitMQ로 Voice Task 발행
    await voice_task.kiq(
        job_id=job_id,
        session_id=session_id,
        audio_data=base64.b64encode(audio_data).decode(),
        audio_format=file.content_type.split("/")[-1],
        voice=voice,
    )

    return VoiceJobResponse(
        job_id=job_id,
        stream_url=f"/api/v1/voice/{job_id}/events",
    )
```

---

## 5. 데이터 흐름

### 5.1 Voice Request Flow

```
1. Frontend: 음성 녹음 → base64 인코딩
2. Chat API: POST /voice (audio file + session_id)
3. RabbitMQ: voice.process 큐에 발행
4. Voice Worker:
   a. gpt-audio 호출 (audio input)
   b. Tool calling (필요시)
   c. Tool 결과로 재호출
   d. 최종 응답 (text + audio)
5. Redis Streams: audio_chunk 이벤트 발행
6. SSE Gateway: audio 스트리밍
7. Frontend: 오디오 재생
```

### 5.2 Event Types

```typescript
// SSE 이벤트 타입
interface VoiceEvents {
  // 텍스트 응답 (기존)
  token: { content: string; seq: number };

  // 오디오 응답 (신규)
  audio_chunk: {
    data: string;      // base64 encoded
    format: "mp3";
    seq: number;
    duration_ms: number;
  };

  audio_complete: {
    total_duration_ms: number;
    text_transcript: string;  // 음성의 텍스트 버전
  };
}
```

---

## 6. 리소스 요구사항

### 6.1 인프라

| 컴포넌트 | 변경 |
|----------|------|
| **Chat API** | `/voice` 엔드포인트 추가 |
| **RabbitMQ** | `voice.process` 큐 추가 |
| **Chat Worker** | VoiceClient, Tool Executor 추가 |
| **SSE Gateway** | audio_chunk 이벤트 처리 |
| **Redis Streams** | audio 이벤트 스키마 추가 |

### 6.2 비용 예측 (월간)

| 시나리오 | 일일 요청 | 평균 길이 | 월 비용 |
|----------|-----------|-----------|---------|
| **낮음** | 100 | 30초 | ~$15 |
| **중간** | 1,000 | 30초 | ~$150 |
| **높음** | 10,000 | 30초 | ~$1,500 |

*계산: (audio_input $0.06/분 + audio_output $0.24/분) × 0.5분 × 요청수 × 30일*

---

## 7. 구현 일정

| Phase | 내용 | 예상 작업 |
|-------|------|-----------|
| **Phase 1** | VoiceClient + Tool 정의 | 신규 파일 3-4개 |
| **Phase 2** | Chat API /voice 엔드포인트 | API 1개 |
| **Phase 3** | RabbitMQ Topology (voice.process) | 매니페스트 수정 |
| **Phase 4** | SSE Audio Streaming | Notifier 확장 |
| **Phase 5** | E2E 테스트 | 테스트 코드 |

---

## 8. 롤백 계획

- Voice 기능은 별도 엔드포인트 (`/voice`)로 분리
- 기존 텍스트 Chat (`/chat`) 영향 없음
- Feature flag로 Voice 기능 ON/OFF 제어

---

## 9. 향후 고려사항

### 9.1 실시간 음성 (gpt-realtime)

현재 구현 후 실시간 요구 시:

```
[Frontend] ←──WebSocket──→ [Voice Gateway] ←──WebSocket──→ [OpenAI Realtime API]
```

### 9.2 다국어 음성

- gpt-audio는 다국어 지원
- 음성 언어 자동 감지 가능
- 응답 언어 제어 (system prompt)

### 9.3 Voice Persona

```python
# 캐릭터별 음성 설정
CHARACTER_VOICES = {
    "eco": "alloy",      # 기본 캐릭터
    "sunny": "nova",     # 밝은 캐릭터
    "wise": "onyx",      # 차분한 캐릭터
}
```

---

## 10. 참고 자료

- [gpt-audio Model | OpenAI API](https://platform.openai.com/docs/models/gpt-audio)
- [Audio and speech | OpenAI API](https://platform.openai.com/docs/guides/audio)
- [Updates for developers building with voice](https://developers.openai.com/blog/updates-audio-models)
- [Chat Worker Production Architecture ADR](./chat-worker-production-architecture-adr.md)
