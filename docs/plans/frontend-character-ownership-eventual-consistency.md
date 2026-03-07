# 프론트엔드 캐릭터 보유 확인 - Eventual Consistency 대응 계획

> 상태: **Updated** (Frontend-only 접근법으로 변경)
> 최종 수정: 2026-01-09

## 1. 현황 분석

### 1.1 백엔드 응답 구조 (현재)

```python
# apps/scan_worker/application/classify/steps/reward_step.py:94-99
reward_response = {
    "name": reward.get("name"),
    "dialog": reward.get("dialog"),
    "match_reason": reward.get("match_reason"),
    "type": reward.get("type"),
}
# ⚠️ received, already_owned, character_id 등이 클라이언트 응답에 포함되지 않음
```

### 1.2 프론트엔드 타입 정의 (현재)

```typescript
// src/api/services/scan/scan.type.ts:34-40
reward?: {
  received: string;        // ⚠️ 백엔드에서 제공하지 않음
  already_owned: boolean;  // ⚠️ 백엔드에서 제공하지 않음
  name: string;
  dialog: string;
  match_reason: string;
};
```

### 1.3 프론트엔드 축하 효과 로직 (현재)

```typescript
// src/pages/Camera/Answer.tsx:29-32
useEffect(() => {
  if (resultStatus === 'good' && reward?.received) {  // ⚠️ reward.received가 undefined
    setShowCelebration(true);
  }
}, [resultStatus, reward?.received]);
```

### 1.4 캐릭터 보유 확인 로직 (현재)

```typescript
// src/pages/Home/CharacterCollection.tsx:69-77
useEffect(() => {
  const getAcquiredCharacter = async () => {
    const { data } = await api.get('/api/v1/users/me/characters');
    // ...
    setAcquiredList(names);
  };
  getAcquiredCharacter();
}, []);
```

---

## 2. 발견된 문제점

### 2.1 🔴 Critical: Celebration Effect 버그

| 항목 | 설명 |
|:---|:---|
| **증상** | 캐릭터 획득 시 축하 효과가 표시되지 않음 |
| **원인** | `reward.received`가 undefined (백엔드 미제공) |
| **영향** | 모든 신규 캐릭터 획득 시 축하 화면 미노출 |

```
Frontend 기대값:    { received: "true", name: "일렉", ... }
Backend 실제 응답: { name: "일렉", dialog: "...", ... }
                   ↑ received 필드 없음!
```

### 2.2 🟡 Eventual Consistency 문제

| 항목 | 설명 |
|:---|:---|
| **증상** | 캐릭터 획득 직후 컬렉션에 미표시 |
| **원인** | Fanout 비동기 저장 → DB 반영 지연 |
| **영향** | 홈 화면 진입 시 방금 획득한 캐릭터가 안 보일 수 있음 |

```
Timeline:
┌─────────────────────────────────────────────────────────────────────────┐
│ Scan API 응답          Character Worker      Users Worker               │
│       │                      │                    │                     │
│ t=0   │◄─ "reward: 일렉"     │                    │                     │
│       │                      │                    │                     │
│ t=50ms│ 프론트: /home 이동   │                    │                     │
│       │ API: /users/me/chars │                    │                     │
│       │      ↓               │                    │                     │
│ t=100ms│ "characters: []" ❌ │◄─ save ownership  │                      │
│       │                      │                    │                     │
│ t=200ms│                     │ DB 저장 완료       │◄─ save character    │
│       │                      │                    │                     │
│ t=300ms│ 새로고침 필요!      │                    │ DB 저장 완료        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 해결 방안

### ~~3.1 Option A: 백엔드에서 `received`, `already_owned` 추가~~ (기각)

> ⚠️ **기각 사유:** 프론트엔드가 이미 `/api/v1/users/me/characters`로 보유 캐릭터 목록을 가지고 있으므로, 클라이언트 측에서 `already_owned` 체크 가능. 백엔드 변경 불필요.

---

### ~~3.2 Option B: 프론트엔드 Optimistic Update만~~ (기각)

> ⚠️ **기각 사유:** Option D가 더 단순하고 완전한 해결책.

---

### ~~3.3 Option C: Hybrid~~ (기각)

> ⚠️ **기각 사유:** 백엔드 변경이 불필요해졌으므로 기각.

---

### 3.4 Option D: Frontend-only 솔루션 (✅ 채택)

**핵심 아이디어:**
- 프론트엔드가 이미 보유 캐릭터 목록을 API로 조회함
- 해당 목록을 **localStorage에 캐싱**
- 스캔 결과의 `reward.name`이 캐시에 없으면 → 신규 캐릭터 → 축하 효과 표시
- **백엔드 변경 불필요**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 변경 전: 백엔드가 already_owned 제공 필요                                │
├─────────────────────────────────────────────────────────────────────────┤
│ Backend → { received, already_owned, name, ... }                        │
│ Frontend → if (!already_owned) showCelebration()                        │
└─────────────────────────────────────────────────────────────────────────┘

                              ↓ 변경

┌─────────────────────────────────────────────────────────────────────────┐
│ 변경 후: 프론트엔드가 직접 체크 (백엔드 변경 없음)                        │
├─────────────────────────────────────────────────────────────────────────┤
│ Backend → { name, dialog, ... }  (기존 그대로)                          │
│ Frontend → const isNew = !ownedCache.includes(reward.name)              │
│            if (isNew) showCelebration()                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

**장점:**

| 항목 | 설명 |
|:---|:---|
| **백엔드 변경 없음** | `received`, `already_owned` 추가 불필요 |
| **즉각적 UX** | localStorage 조회는 동기식 → 즉시 판단 |
| **Eventual Consistency 해결** | Optimistic Update로 즉시 반영 |
| **단순한 구현** | 별도 API 호출 없이 로컬 캐시 활용 |

**단점:**
- 다른 기기에서 획득한 캐릭터는 홈 화면 진입 시 서버 동기화로 해결

---

## 4. 구현 계획 (Frontend-only)

### 단일 Phase (프론트엔드만 변경)

| Task | 담당 |
|:---|:---|
| 1. `CharacterCache.ts` 유틸 생성 | Frontend |
| 2. `CharacterCollection.tsx` 캐시 동기화 추가 | Frontend |
| 3. `Answer.tsx` 축하 효과 로직 수정 | Frontend |
| 4. 타입 정의 정리 (불필요한 필드 제거) | Frontend |
| 5. 로그아웃 시 캐시 클리어 | Frontend |
| E2E 테스트 | QA |

---

## 5. ~~백엔드 변경 상세~~ (불필요)

> ✅ **백엔드 변경 없음** - 기존 응답 그대로 사용

---

## 6. 프론트엔드 변경 상세

### 6.1 CharacterCache.ts (신규 유틸)

```typescript
// src/util/CharacterCache.ts
const OWNED_CHARACTERS_KEY = 'owned_characters';

/**
 * 보유 캐릭터 목록 조회 (localStorage)
 */
export const getOwnedCharacters = (): string[] => {
  try {
    return JSON.parse(localStorage.getItem(OWNED_CHARACTERS_KEY) || '[]');
  } catch {
    return [];
  }
};

/**
 * 보유 캐릭터 목록 저장 (서버 동기화 시 사용)
 */
export const setOwnedCharacters = (names: string[]) => {
  localStorage.setItem(OWNED_CHARACTERS_KEY, JSON.stringify(names));
};

/**
 * 캐릭터 추가 (Optimistic Update)
 */
export const addOwnedCharacter = (name: string) => {
  const list = getOwnedCharacters();
  if (!list.includes(name)) {
    list.push(name);
    setOwnedCharacters(list);
  }
};

/**
 * 캐시 클리어 (로그아웃 시)
 */
export const clearOwnedCharacters = () => {
  localStorage.removeItem(OWNED_CHARACTERS_KEY);
};

/**
 * 신규 캐릭터 여부 확인
 */
export const isNewCharacter = (name: string): boolean => {
  return !getOwnedCharacters().includes(name);
};
```

### 6.2 CharacterCollection.tsx 수정

```typescript
// src/pages/Home/CharacterCollection.tsx

import { setOwnedCharacters } from '@/util/CharacterCache';

useEffect(() => {
  const getAcquiredCharacter = async () => {
    const { data } = await api.get('/api/v1/users/me/characters');
    if (!data) {
      console.error('획득한 캐릭터 리스트를 불러올 수 없습니다.');
      return;
    }
    const names = data.map((item: MyCharacterResponse) => item.name);
    setAcquiredList(names);
    
    // ✅ 추가: localStorage 캐시 동기화
    setOwnedCharacters(names);
  };
  getAcquiredCharacter();
}, []);
```

### 6.3 Answer.tsx 수정

```typescript
// src/pages/Camera/Answer.tsx

import { isNewCharacter, addOwnedCharacter } from '@/util/CharacterCache';

// 변경 전
useEffect(() => {
  if (resultStatus === 'good' && reward?.received) {
    setShowCelebration(true);
  }
}, [resultStatus, reward?.received]);

// 변경 후 (Frontend-only 체크)
useEffect(() => {
  // reward가 있고 + 신규 캐릭터일 때만 축하 효과
  if (reward?.name && isNewCharacter(reward.name)) {
    setShowCelebration(true);
    
    // Optimistic Update: 로컬 캐시에 즉시 추가
    addOwnedCharacter(reward.name);
  }
}, [reward?.name]);
```

### 6.4 scan.type.ts 수정

```typescript
// src/api/services/scan/scan.type.ts

// 변경 전 (불필요한 필드 포함)
reward?: {
  received: string;        // ❌ 제거
  already_owned: boolean;  // ❌ 제거
  name: string;
  dialog: string;
  match_reason: string;
};

// 변경 후 (백엔드 실제 응답에 맞춤)
reward?: {
  name: string;
  dialog: string;
  match_reason: string;
  type: string;
};
```

### 6.5 로그아웃 시 캐시 클리어

```typescript
// src/components/myPage/LogoutDialog.tsx (또는 logout 처리 위치)

import { clearOwnedCharacters } from '@/util/CharacterCache';

const handleLogout = async () => {
  await api.post('/api/v1/auth/logout');
  
  // ✅ 추가: 캐릭터 캐시 클리어
  clearOwnedCharacters();
  clearStorageUserInfo();
  
  window.location.replace('/#/login');
};
```

---

## 7. 테스트 시나리오

### 7.1 신규 캐릭터 획득

```
Given: 
  - 사용자가 "일렉" 캐릭터를 보유하지 않음
  - localStorage 캐시에 "일렉" 없음
When: 전기전자제품 이미지 스캔 성공, reward.name = "일렉"
Then:
  - isNewCharacter("일렉") = true
  - 축하 효과 표시됨 ✅
  - localStorage 캐시에 "일렉" 추가됨
  - 홈 화면에서 "일렉" 캐릭터 표시됨
```

### 7.2 기존 캐릭터 재획득

```
Given: 
  - 사용자가 "일렉" 캐릭터를 이미 보유
  - localStorage 캐시에 "일렉" 있음
When: 전기전자제품 이미지 스캔 성공, reward.name = "일렉"
Then:
  - isNewCharacter("일렉") = false
  - 축하 효과 미표시 ✅
  - 홈 화면에서 "일렉" 캐릭터 유지
```

### 7.3 Eventual Consistency 시나리오

```
Given: 사용자가 "일렉" 캐릭터 방금 획득
When: 스캔 결과 화면에서 즉시 홈으로 이동
Then:
  - Optimistic Update로 localStorage에 "일렉" 이미 추가됨
  - 서버 API 응답 전에도 홈 화면에서 "일렉" 표시 ✅
  - 서버 동기화 후에도 "일렉" 유지
```

### 7.4 로그아웃 후 재로그인

```
Given: 사용자가 로그아웃
When: 다른 계정으로 로그인 후 홈 화면 진입
Then:
  - localStorage 캐시 클리어됨
  - 새 계정의 캐릭터 목록으로 캐시 갱신됨
```

---

## 8. 데이터 플로우 (수정 후)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Frontend-only Ownership Check Flow                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Frontend]                    [Scan Worker]           [Character Worker]   │
│      │                              │                         │             │
│  ┌───┴───┐                          │                         │             │
│  │ Home  │ GET /users/me/characters │                         │             │
│  │ 진입  │──────────────────────────┼─────────────────────────┼──►          │
│  │       │◄─────────────────────────┼─────────────────────────┼──           │
│  │       │ ["이코", "페이피"]        │                         │             │
│  │       │         │                │                         │             │
│  │       │  setOwnedCharacters()    │  (localStorage 캐시)    │             │
│  └───┬───┘         ▼                │                         │             │
│      │    localStorage: ["이코","페이피"]                      │             │
│      │                              │                         │             │
│  ┌───┴───┐                          │                         │             │
│  │Camera │ POST /scan               │                         │             │
│  │       │────────────────────────► │                         │             │
│  │       │                          │ character.match         │             │
│  │       │                          │────────────────────────►│             │
│  │       │                          │◄────────────────────────│             │
│  │       │ SSE: done                │                         │             │
│  │       │◄─────────────────────────│                         │             │
│  │       │ {name: "일렉", ...}      │                         │             │
│  └───┬───┘                          │                         │             │
│      │                              │                         │             │
│  ┌───┴───┐                          │                         │             │
│  │Answer │                          │                         │             │
│  │       │ isNewCharacter("일렉")   │                         │             │
│  │       │     ↓                    │                         │             │
│  │       │ localStorage 조회        │                         │             │
│  │       │ ["이코","페이피"]에 없음 │                         │             │
│  │       │     ↓                    │                         │             │
│  │       │ ✅ 축하 효과 표시!       │                         │             │
│  │       │ addOwnedCharacter("일렉")│                         │             │
│  │       │     ↓                    │                         │             │
│  │       │ localStorage: ["이코","페이피","일렉"]              │             │
│  └───┬───┘                          │                         │             │
│      │                              │                         │             │
│  ┌───┴───┐                          │                         │             │
│  │ Home  │ (즉시 이동해도 OK)       │                         │             │
│  │       │ localStorage에 "일렉" 이미 있음 ✅                 │             │
│  └───────┘                          │                         │             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**핵심 포인트:**
1. 홈 화면 진입 시 서버 데이터로 localStorage 캐시 동기화
2. Answer 페이지에서 localStorage 캐시로 신규 여부 즉시 판단
3. Optimistic Update로 캐시에 즉시 추가 → Eventual Consistency 해결

---

## 9. 결론 및 권장 사항

### ✅ 채택된 해결책: Frontend-only (Option D)

| 항목 | 내용 |
|:---|:---|
| **백엔드 변경** | 없음 |
| **프론트엔드 변경** | 5개 파일 |
| **예상 소요 시간** | ~70분 |
| **핵심 원리** | localStorage 캐시 + Optimistic Update |

### 구현 체크리스트

- [ ] `src/util/CharacterCache.ts` 생성
- [ ] `CharacterCollection.tsx`에서 `setOwnedCharacters()` 호출 추가
- [ ] `Answer.tsx`에서 `isNewCharacter()` 체크 로직으로 변경
- [ ] `scan.type.ts`에서 불필요한 `received`, `already_owned` 필드 제거
- [ ] 로그아웃 시 `clearOwnedCharacters()` 호출 추가
- [ ] E2E 테스트

### 예상 효과

1. **축하 효과 버그 해결** - 신규 캐릭터 획득 시 축하 화면 정상 표시
2. **Eventual Consistency 해결** - Optimistic Update로 즉각적인 UX
3. **유지보수성** - 백엔드 변경 없이 프론트엔드 단독 해결

