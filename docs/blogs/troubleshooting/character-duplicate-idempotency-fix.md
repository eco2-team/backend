# Eventual Consistency 트러블슈팅: Character Rewards INSERT 멱등성 미보장 버그 픽스

> **날짜**: 2025-12-30  
> **영향 범위**: `my.user_characters` 테이블, 캐릭터 인벤토리 조회  
> **심각도**: Medium (데이터 중복, UX 영향)

---

## 1. 문제 발견

### 1.1 증상

사용자가 `/api/v1/user/me/characters` API를 호출했을 때, 동일한 캐릭터가 두 번 표시되는 문제 발생.

```json
[
    {
        "id": "a68c313e-3fd3-41b6-ae90-72640c6f0aba",
        "code": "char-paepy",
        "name": "페이피",
        "type": "",
        "dialog": "테이프와 스테이플은 떼고 깨끗하게 접어요!",
        "acquired_at": "2025-12-24T12:10:19.825556Z"
    },
    // ... 중간 생략 ...
    {
        "id": "c7df88f5-66af-4d75-bcd4-1825a5692738",
        "code": "char-paepy",
        "name": "페이피",
        "type": "골판지류, 신문지, 과자상자, 백판지, 책자",
        "dialog": "테이프와 스테이플은 떼고 깨끗하게 접어요!",
        "acquired_at": "2025-12-02T23:20:20.199493Z"
    }
]
```

**관찰된 중복**:
- `char-petty` (페티): 2개
- `char-paepy` (페이피): 2개

---

## 2. 시스템 아키텍처 (문제 발생 지점)

### 2.1 캐릭터 보상 저장 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    Character Reward Flow                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  scan-worker (scan.reward)                                  │
│       │                                                     │
│       ├── 1. character.match 호출 (동기)                    │
│       │       └── character-worker의 로컬 캐시에서 매칭     │
│       │       └── 반환: { character_id, character_code, ... }│
│       │                                                     │
│       └── 2. DB 저장 task 발행 (Fire & Forget)              │
│               │                                             │
│               ├── character.save_ownership                  │
│               │       └── character.character_ownerships    │
│               │       └── ON CONFLICT (user_id, character_id)│
│               │                                             │
│               └── my.save_character ← 🐛 문제 발생 지점     │
│                       └── user_profile.user_characters      │
│                       └── ON CONFLICT (user_id, character_id)│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 관련 테이블 스키마

```sql
-- user_profile.user_characters (문제 발생 테이블)
CREATE TABLE user_profile.user_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    character_id UUID NOT NULL,        -- ← 문제의 원인
    character_code VARCHAR(64) NOT NULL,
    character_name VARCHAR(120) NOT NULL,
    character_type VARCHAR(64),
    character_dialog VARCHAR(500),
    source VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'owned',
    acquired_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_character UNIQUE (user_id, character_id)  -- ← 문제의 제약
);
```

---

## 3. 데이터 분석

### 3.1 중복 데이터 조회

```sql
SELECT user_id, character_code, COUNT(*) as cnt
FROM user_profile.user_characters
GROUP BY user_id, character_code
HAVING COUNT(*) > 1;
```

**결과**:
```
               user_id                | character_code | cnt 
--------------------------------------+----------------+-----
 8b8ec006-2d95-45aa-bdef-e08201f1bb82 | char-petty     |   2
 8b8ec006-2d95-45aa-bdef-e08201f1bb82 | char-paepy     |   2
```

### 3.2 상세 데이터 분석

```sql
SELECT id, user_id, character_id, character_code, character_name, acquired_at 
FROM user_profile.user_characters 
WHERE character_code IN ('char-petty', 'char-paepy') 
  AND user_id = '8b8ec006-2d95-45aa-bdef-e08201f1bb82'
ORDER BY character_code, acquired_at DESC;
```

**결과**:
```
                  id                  |               user_id                |             character_id             | character_code | acquired_at          
--------------------------------------+--------------------------------------+--------------------------------------+----------------+-------------------------------
 de0922d7-c95a-4022-912a-026317336850 | 8b8ec006-... | a68c313e-3fd3-41b6-ae90-72640c6f0aba | char-paepy     | 2025-12-24 12:10:19 ← 새로운 ID
 48d11f4e-66f2-4b5b-adab-1d4e65e66dfc | 8b8ec006-... | c7df88f5-66af-4d75-bcd4-1825a5692738 | char-paepy     | 2025-12-02 23:20:20 ← 원래 ID
 6ec7120b-da70-4374-9555-b7c3fd7a6ea0 | 8b8ec006-... | f2c21422-c57a-4012-818e-e44ba940756c | char-petty     | 2025-12-24 03:13:22 ← 새로운 ID
 24d1af0a-a1be-490f-b83c-0caed8e62ec6 | 8b8ec006-... | 44490ae4-e02b-451b-8bed-b2e43f8edeee | char-petty     | 2025-12-21 06:45:20 ← 원래 ID
```

### 3.3 character 테이블 검증

```sql
SELECT id, code, name FROM character.characters 
WHERE code IN ('char-petty', 'char-paepy');
```

**결과**:
```
                  id                  |    code    |  name  
--------------------------------------+------------+--------
 c7df88f5-66af-4d75-bcd4-1825a5692738 | char-paepy | 페이피  ← 올바른 ID
 44490ae4-e02b-451b-8bed-b2e43f8edeee | char-petty | 페티    ← 올바른 ID
```

### 3.4 존재하지 않는 character_id 확인

```sql
SELECT id, code, name FROM character.characters 
WHERE id IN ('a68c313e-3fd3-41b6-ae90-72640c6f0aba', 'f2c21422-c57a-4012-818e-e44ba940756c');
```

**결과**:
```
 id | code | name 
----+------+------
(0 rows)
```

**핵심 발견**: `user_characters`에 저장된 `character_id` 중 일부가 `character.characters` 테이블에 존재하지 않음!

---

## 4. 근본 원인 분석

### 4.1 문제의 핵심

```
┌─────────────────────────────────────────────────────────────┐
│                    Eventual Consistency 문제                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. character 테이블의 ID가 변경됨                          │
│     - 원인: DB 마이그레이션, 테이블 재생성, 또는 데이터 복구 │
│     - 결과: 기존 ID와 새 ID가 공존                          │
│                                                             │
│  2. character-worker의 로컬 캐시가 잘못된 ID를 가짐         │
│     - 캐시 워밍업 시점에 임시 데이터 로드                   │
│     - 또는 캐시 동기화 이벤트 누락                          │
│                                                             │
│  3. UNIQUE 제약이 character_id 기준                         │
│     - 같은 character_code도 다른 character_id면 저장 가능   │
│     - 멱등성 보장 실패                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 타임라인 추정

```
2025-12-02: char-paepy 최초 획득 (character_id: c7df88f5...)
    ↓
2025-12-21: char-petty 최초 획득 (character_id: 44490ae4...)
    ↓
[2025-12-23 ~ 24 사이 어딘가]
    - character 테이블 재생성 또는 데이터 마이그레이션
    - character-worker 캐시에 임시 ID가 로드됨
    ↓
2025-12-24: char-petty 재획득 시도 (character_id: f2c21422... - 잘못된 ID)
    - UNIQUE(user_id, character_id) 통과 → 중복 저장
    ↓
2025-12-24: char-paepy 재획득 시도 (character_id: a68c313e... - 잘못된 ID)
    - UNIQUE(user_id, character_id) 통과 → 중복 저장
```

### 4.3 코드 분석

**문제의 코드** (`my/tasks/sync_character.py`):

```python
sql = text(
    f"""
    INSERT INTO user_profile.user_characters
        (user_id, character_id, character_code, ...)
    VALUES {", ".join(values)}
    ON CONFLICT (user_id, character_id) DO NOTHING  -- ← 문제!
"""
)
```

**문제점**:
- `character_id`가 캐시에서 잘못 전달되면 다른 레코드로 인식
- 동일한 캐릭터(character_code)가 다른 ID로 중복 저장

---

## 5. 해결 방안

### 5.1 설계 원칙

```
┌─────────────────────────────────────────────────────────────┐
│                    멱등성 기준 변경                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  기존: UNIQUE(user_id, character_id)                        │
│  - 캐시 불일치 시 중복 허용                                 │
│  - character_id는 변할 수 있음 (DB 마이그레이션 등)         │
│                                                             │
│  변경: UNIQUE(user_id, character_code)                      │
│  - character_code는 불변 (캐릭터마다 고유)                  │
│  - 캐시 불일치에도 중복 방지                                │
│  - Self-healing: 기존 레코드의 character_id를 최신으로 갱신 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 수정된 코드

**1. `my/models/user_character.py`**:

```python
class UserCharacter(Base):
    __tablename__ = "user_characters"
    __table_args__ = (
        # Bug fix (2025-12-30): character_id → character_code 기준으로 변경
        UniqueConstraint("user_id", "character_code", name="uq_user_character_code"),
        {"schema": "user_profile"},
    )
```

**2. `my/tasks/sync_character.py`**:

```python
sql = text(
    f"""
    INSERT INTO user_profile.user_characters
        (user_id, character_id, character_code, ...)
    VALUES {", ".join(values)}
    ON CONFLICT (user_id, character_code) DO UPDATE SET
        character_id = EXCLUDED.character_id,  -- Self-healing
        character_name = EXCLUDED.character_name,
        character_type = COALESCE(EXCLUDED.character_type, user_profile.user_characters.character_type),
        character_dialog = COALESCE(EXCLUDED.character_dialog, user_profile.user_characters.character_dialog),
        updated_at = NOW()
"""
)
```

**3. `my/repositories/user_character_repository.py`**:

```python
stmt = (
    insert(UserCharacter)
    .values(...)
    .on_conflict_do_update(
        constraint="uq_user_character_code",  # Bug fix
        set_={
            "character_id": character_id,  # Self-healing
            "character_name": character_name,
            ...
        },
    )
    .returning(UserCharacter)
)
```

---

## 6. 마이그레이션 실행

### 6.1 중복 데이터 정리

```sql
-- Step 1: 중복 확인
SELECT user_id, character_code, COUNT(*) as cnt
FROM user_profile.user_characters
GROUP BY user_id, character_code
HAVING COUNT(*) > 1;

-- Step 2: 중복 삭제 (가장 오래된 것만 유지)
DELETE FROM user_profile.user_characters
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY user_id, character_code
                   ORDER BY acquired_at ASC  -- 가장 오래된 것 유지
               ) as rn
        FROM user_profile.user_characters
    ) ranked
    WHERE rn > 1
);
-- 결과: DELETE 2
```

### 6.2 제약조건 변경

```sql
-- Step 3: 기존 제약 삭제
ALTER TABLE user_profile.user_characters 
DROP CONSTRAINT IF EXISTS uq_user_character;

-- Step 4: 새 제약 생성
ALTER TABLE user_profile.user_characters 
ADD CONSTRAINT uq_user_character_code UNIQUE (user_id, character_code);
```

### 6.3 검증

```sql
\d user_profile.user_characters

-- 결과:
-- Indexes:
--     "user_characters_pkey" PRIMARY KEY, btree (id)
--     "ix_user_characters_character_id" btree (character_id)
--     "ix_user_characters_user_id" btree (user_id)
--     "uq_user_character_code" UNIQUE CONSTRAINT, btree (user_id, character_code)
```

---

## 7. 검증

### 7.1 중복 저장 테스트

```python
# 같은 캐릭터를 다른 character_id로 저장 시도
await repo.grant_character(
    user_id=user_id,
    character_id=UUID("a68c313e-3fd3-41b6-ae90-72640c6f0aba"),  # 잘못된 ID
    character_code="char-petty",
    character_name="페티",
    ...
)

# 결과: 기존 레코드의 character_id가 새 값으로 갱신됨 (UPSERT)
# 중복 레코드 생성 안됨 ✅
```

### 7.2 API 응답 확인

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.dev.growbin.app/api/v1/user/me/characters | jq '.[] | .code' | sort | uniq -c

# 결과: 모든 캐릭터가 1개씩만 존재 ✅
```

---

## 8. 교훈 및 권장사항

### 8.1 Eventual Consistency 환경에서의 멱등성

```
┌─────────────────────────────────────────────────────────────┐
│                    Best Practices                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. UNIQUE 제약 기준 선택                                   │
│     - 변할 수 있는 값: character_id, session_id 등 ❌       │
│     - 불변 값: character_code, user_id + business_key ✅   │
│                                                             │
│  2. Self-Healing UPSERT                                     │
│     - ON CONFLICT DO NOTHING → 문제 숨김 ❌                 │
│     - ON CONFLICT DO UPDATE → 자동 복구 ✅                  │
│                                                             │
│  3. 캐시 일관성                                             │
│     - 캐시 데이터는 언제든 변할 수 있음을 가정              │
│     - DB가 진실의 원천(Source of Truth)                     │
│     - 캐시 불일치에도 DB 무결성 보장 필요                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 향후 개선 사항

1. **character-worker 캐시 검증**: DB와 캐시 일관성 주기적 검증
2. **모니터링 추가**: 중복 저장 시도 감지 메트릭
3. **테스트 추가**: 캐시 불일치 상황 시뮬레이션 테스트

---

## 9. 관련 커밋

```
e67ab58a fix(my): use character_code for idempotency instead of character_id
```

**변경 파일**:
- `domains/my/models/user_character.py`
- `domains/my/repositories/user_character_repository.py`
- `domains/my/tasks/sync_character.py`
- `domains/my/jobs/fix_duplicate_characters.py` (마이그레이션 스크립트)

