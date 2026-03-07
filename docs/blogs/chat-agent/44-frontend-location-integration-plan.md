# Frontend 위치 정보 통합 계획

> **작성일**: 2026-01-19
> **상태**: 📋 계획됨 (Frontend 구현 필요)
> **우선순위**: Medium
> **관련 이슈**: Weather 서브에이전트 위치 정보 요구사항 (#43)

---

## 1. 개요

### 1.1. 배경

Weather 서브에이전트가 날씨 정보를 제공하려면 사용자 위치(`user_location`)가 필요함. 현재 Frontend에서 위치를 전송하지 않아 날씨 질문에 대해 "위치 정보가 필요해요"라는 응답만 생성됨.

### 1.2. 목표

Chat 화면 진입 시 사용자 위치를 수집하고, 모든 메시지 요청에 포함하여 전송.

---

## 2. 요구사항

### 2.1. 위치 수집 플로우

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Frontend 위치 수집 플로우                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. Chat 화면 진입                                                          │
│      ↓                                                                      │
│   2. Geolocation API 권한 확인                                               │
│      ├─ 이미 허용됨 → 위치 수집                                              │
│      ├─ 아직 요청 안함 → 권한 요청 팝업                                       │
│      └─ 거부됨 → 위치 없이 진행                                              │
│      ↓                                                                      │
│   3. 위치 수집 성공 시                                                       │
│      └─ localStorage/state에 저장                                           │
│      ↓                                                                      │
│   4. 메시지 전송 시                                                          │
│      ├─ 위치 있음 → user_location 포함                                       │
│      └─ 위치 없음 → user_location 없이 전송                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. API 요청 형식

**위치 있는 경우:**
```json
{
  "message": "오늘 날씨 어때?",
  "user_location": {
    "latitude": 37.5665,
    "longitude": 126.9780
  }
}
```

**위치 없는 경우:**
```json
{
  "message": "오늘 날씨 어때?"
}
```

---

## 3. 구현 가이드

### 3.1. Geolocation API 사용

```typescript
// 위치 수집 함수
async function getUserLocation(): Promise<UserLocation | null> {
  if (!navigator.geolocation) {
    console.log('Geolocation not supported');
    return null;
  }

  try {
    const position = await new Promise<GeolocationPosition>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,  // 배터리 절약
        timeout: 10000,             // 10초 타임아웃
        maximumAge: 300000,         // 5분 캐시
      });
    });

    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };
  } catch (error) {
    // 권한 거부 또는 타임아웃
    console.log('Failed to get location:', error);
    return null;
  }
}
```

### 3.2. 메시지 전송 시 위치 포함

```typescript
// 메시지 전송 함수
async function sendMessage(message: string) {
  const userLocation = await getUserLocation();

  const payload: SendMessageRequest = {
    message,
    ...(userLocation && { user_location: userLocation }),
  };

  return fetch(`/api/v1/chat/${chatId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
```

### 3.3. 권한 요청 UX

**권한 요청 시점:**
- Chat 화면 최초 진입 시
- 또는 날씨/위치 관련 질문 감지 시 (선택적)

**권한 요청 UI 예시:**
```
┌────────────────────────────────────────┐
│  📍 위치 정보 사용 동의                 │
├────────────────────────────────────────┤
│                                        │
│  날씨, 주변 분리수거함 등 위치 기반     │
│  서비스를 이용하려면 위치 정보가        │
│  필요합니다.                           │
│                                        │
│  [허용]  [나중에]                       │
│                                        │
└────────────────────────────────────────┘
```

---

## 4. 고려사항

### 4.1. 위치 정보 캐싱

- **캐시 시간**: 5분 (`maximumAge: 300000`)
- **저장 위치**: React state 또는 Context
- **갱신 시점**: Chat 화면 재진입 시

### 4.2. 권한 거부 시 처리

- 위치 없이 정상 동작 (날씨 외 기능은 문제없음)
- Weather 노드: "위치 정보가 필요해요" 안내 응답 생성
- 사용자가 원하면 수동으로 지역 입력 가능

### 4.3. 개인정보 보호

- 위치 정보는 요청 시에만 수집
- 서버에 영구 저장하지 않음 (세션 내 사용만)
- 명시적 동의 후 수집

---

## 5. 체크리스트

### 5.1. Frontend 구현

- [ ] Geolocation API 권한 요청 로직
- [ ] 위치 수집 및 state 저장
- [ ] 메시지 전송 시 `user_location` 포함
- [ ] 권한 거부 시 graceful 처리
- [ ] 위치 권한 상태 UI 표시 (선택적)

### 5.2. 테스트

- [ ] 위치 허용 → 날씨 질문 → 날씨 정보 응답 확인
- [ ] 위치 거부 → 날씨 질문 → 위치 필요 안내 확인
- [ ] 위치 허용 → 분리배출 질문 → 정상 동작 확인

---

## 6. 관련 문서

- [43-weather-subagent-location-requirement.md](./43-weather-subagent-location-requirement.md) - Weather 위치 요구사항
- [chat.py:126-141](../../../apps/chat/presentation/http/controllers/chat.py) - API 스키마

