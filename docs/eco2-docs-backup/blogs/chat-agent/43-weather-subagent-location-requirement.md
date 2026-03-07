# Weather 서브에이전트 위치 정보 요구사항 분석

> **작성일**: 2026-01-19
> **환경**: dev (ap-northeast-2)
> **상태**: 🟢 정상 동작 (설계된 동작)
> **목적**: Weather 서브에이전트가 날씨 정보를 반환하지 않은 원인 분석

---

## 1. 개요

### 1.1. 배경

Multi-Intent 테스트 중 "오늘 날씨 어때?" 질문에 대해 날씨 정보가 반환되지 않고, "오늘 날씨는 내가 실시간 확인은 못 해서 정확히는 잘 모르겠어요"라는 응답이 생성됨.

### 1.2. 결론 (요약)

**버그가 아닌 설계된 동작**. Weather API(기상청 초단기실황)는 위치 기반 API로, `user_location` 없이는 호출 불가.

---

## 2. 관측된 현상

### 2.1. 테스트 요청

```bash
curl -s -X POST "https://api.dev.growbin.app/api/v1/chat/$CHAT_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message": "플라스틱 분리배출하려는데, 1) 분리배출 방법 알려줘 2) 가까운 수거함 위치도 알려줘 3) 오늘 날씨 어때?"}'
```

→ **`user_location` 필드 누락**

### 2.2. 응답 내용

```
3) 오늘 날씨는 내가 실시간 확인은 못 해서 **정확히는 잘 모르겠어요** 😅
대신 **도시/구 + 지금 시간대** 알려주면, 네가 있는 지역 기준으로 확인하는 방법(앱/사이트) 빠르게 안내해줄게.
```

→ LLM이 날씨 정보 없이 graceful하게 응답

---

## 3. 데이터 흐름 분석

### 3.1. 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Weather 서브에이전트 데이터 흐름                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Frontend (curl)                                                           │
│   └─ POST /chat/{id}/messages                                               │
│      └─ body: {"message": "...", "user_location": null}  ← 위치 없음        │
│                                                                             │
│   Chat API (chat.py:382-387)                                                │
│   └─ user_location = None  ← payload.user_location is None                  │
│                                                                             │
│   Chat Worker (process_chat.py:236-243)                                     │
│   └─ initial_state["user_location"] = None                                  │
│                                                                             │
│   Weather Node (weather_node.py:102-109)                                    │
│   └─ user_location = state.get("user_location")  → None                     │
│   └─ lat, lon = None, None                                                  │
│                                                                             │
│   GetWeatherCommand (get_weather_command.py:101-109)                        │
│   └─ if lat is None or lon is None:                                         │
│      └─ return GetWeatherOutput(needs_location=True)  ← API 호출 스킵       │
│                                                                             │
│   KMA Weather API (kma_weather_http_client.py)                              │
│   └─ ❌ 호출되지 않음                                                       │
│                                                                             │
│   Answer Node                                                               │
│   └─ weather_context.needs_location = True                                  │
│   └─ LLM이 위치 필요 안내 응답 생성                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2. API 스키마 (SendMessageRequest)

**파일**: `apps/chat/presentation/http/controllers/chat.py:126-141`

```python
class SendMessageRequest(BaseModel):
    """메시지 전송 요청."""

    message: str = Field(description="사용자 메시지")
    image_url: HttpUrl | None = Field(
        default=None,
        description="첨부 이미지 URL",
    )
    user_location: UserLocation | None = Field(
        default=None,
        description="사용자 위치 (주변 검색용)",
    )
    model: str | None = Field(
        default=None,
        description="LLM 모델명 (미지정 시 기본값)",
    )
```

→ `user_location`은 **선택적 필드** (`default=None`)

### 3.3. Weather 노드 위치 추출 로직

**파일**: `apps/chat_worker/infrastructure/orchestration/langgraph/nodes/weather_node.py:102-109`

```python
user_location = state.get("user_location")
lat: float | None = None
lon: float | None = None

if isinstance(user_location, dict):
    lat = user_location.get("lat") or user_location.get("latitude")
    lon = user_location.get("lon") or user_location.get("longitude")
```

→ `user_location`이 None이면 lat/lon도 None

### 3.4. GetWeatherCommand 분기 로직

**파일**: `apps/chat_worker/application/commands/get_weather_command.py:101-109`

```python
if input_dto.lat is None or input_dto.lon is None:
    events.append("location_required")
    return GetWeatherOutput(
        success=True,
        weather_context={"type": "no_location", "context": None},
        needs_location=True,
        events=events,
    )
```

→ 위치 없으면 **API 호출 스킵** + `needs_location=True` 반환

---

## 4. 기상청 API 요구사항

### 4.1. KMA 초단기실황 API

**파일**: `apps/chat_worker/infrastructure/integrations/kma/kma_weather_http_client.py`

```python
BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

async def get_current_weather(self, nx: int, ny: int) -> dict[str, Any]:
    """초단기실황 조회.

    Args:
        nx: 기상청 격자 X 좌표
        ny: 기상청 격자 Y 좌표
    """
    params = {
        "serviceKey": self._api_key,
        "pageNo": "1",
        "numOfRows": "10",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": str(nx),
        "ny": str(ny),
    }
    return await self._request("/getUltraSrtNcst", params)
```

**필수 파라미터:**
- `nx`, `ny`: 기상청 격자 좌표 (위도/경도 → 격자 변환 필요)
- `base_date`, `base_time`: 기준 시각

→ **위도/경도 없이는 API 호출 자체가 불가능**

---

## 5. 설계 의도

### 5.1. 왜 위치를 필수로 요구하는가?

1. **기상청 API 특성**: 격자 기반 API로, 위치 없이 "한국 전체 날씨" 조회 불가
2. **정확성**: 서울과 부산의 날씨가 다름. 위치 없이 날씨 안내는 무의미
3. **개인정보**: 위치는 민감 정보. 명시적 동의 없이 수집하지 않음

### 5.2. Human-in-the-Loop 지원

위치가 필요한 경우 Frontend에서 수집 후 `/chat/{job_id}/input` 엔드포인트로 전송 가능:

```json
{
  "type": "location",
  "data": {
    "latitude": 37.5665,
    "longitude": 126.9780
  }
}
```

---

## 6. 올바른 테스트 방법

### 6.1. 위치 포함 요청

```bash
curl -s -X POST "https://api.dev.growbin.app/api/v1/chat/$CHAT_ID/messages" \
  -H "Content-Type: application/json" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{
    "message": "오늘 날씨 어때?",
    "user_location": {
      "latitude": 37.5665,
      "longitude": 126.9780
    }
  }'
```

### 6.2. 예상 응답

```
오늘 서울(종로구) 날씨는 맑음이에요! ☀️
현재 기온 15°C, 습도 45%입니다.
자외선 지수가 높으니 외출 시 선크림 챙기세요!
```

---

## 7. 결론

### 7.1. 근본 원인

| 구분 | 내용 |
|------|------|
| 현상 | Weather 서브에이전트가 날씨 정보 미반환 |
| 원인 | 테스트 요청에 `user_location` 누락 |
| 상태 | **정상 동작** (설계된 동작) |

### 7.2. Weather 노드 동작 정리

| 조건 | 동작 |
|------|------|
| `user_location` 존재 | KMA API 호출 → 날씨 정보 반환 |
| `user_location` 없음 | `needs_location=True` 반환 → LLM이 안내 응답 생성 |

### 7.3. 관련 코드 경로

```
Frontend Request
    ↓
chat.py:382-387 (user_location 추출)
    ↓
process_chat.py:236-243 (initial_state 구성)
    ↓
weather_node.py:102-109 (lat/lon 추출)
    ↓
get_weather_command.py:101-109 (위치 체크, API 호출 분기)
    ↓
kma_weather_http_client.py:get_current_weather() (KMA API 호출)
```

---

## 8. 관련 문서

- [41-multi-intent-verification-report.md](./41-multi-intent-verification-report.md) - Multi-Intent 테스트
- [SKILL.md: chat-agent-flow](../../.claude/skills/chat-agent-flow/SKILL.md) - Chat Agent 아키텍처

