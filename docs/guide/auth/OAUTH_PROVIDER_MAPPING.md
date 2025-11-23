# OAuth 프로바이더별 프로필 정보 매핑

## 📋 개요

각 OAuth 프로바이더(Google, Naver, Kakao)에서 제공하는 사용자 정보를 DB에 저장하는 방식을 정리한 문서입니다.

---

## 🔵 Google OAuth

### API 응답 구조

```json
{
  "sub": "107754689264640366020",
  "name": "jihwan ryu",
  "given_name": "jihwan",
  "family_name": "ryu",
  "email": "ryoo0504@gmail.com",
  "picture": "https://lh3.googleusercontent.com/..."
}
```

### 매핑 규칙

| Google API 필드 | OAuthProfile 필드 | DB 저장 (users 테이블) | 설명 |
|-----------------|-------------------|------------------------|------|
| `sub` | `provider_user_id` | `provider_user_id` | Google 고유 사용자 ID |
| `email` | `email` | `email` | 이메일 주소 |
| `name` | `name` | `username` | 전체 이름 (예: "jihwan ryu") |
| `given_name` | `nickname` | `nickname` | 이름만 (예: "jihwan") |
| `picture` | `profile_image_url` | `profile_image_url` | 프로필 이미지 URL |

### DB 저장 예시

```sql
provider: 'google'
provider_user_id: '107754689264640366020'
email: 'ryoo0504@gmail.com'
username: 'jihwan ryu'      -- name (전체 이름)
nickname: 'jihwan'          -- given_name (이름만)
profile_image_url: 'https://lh3.googleusercontent.com/...'
```

### 특징

- ✅ `given_name`을 nickname으로 사용
- ✅ `name`을 username으로 사용
- ✅ 이메일 필수 제공
- ✅ 프로필 이미지 URL 제공
- ✅ PKCE 지원

---

## 📱 Naver OAuth

### API 응답 구조

```json
{
  "resultcode": "00",
  "message": "success",
  "response": {
    "id": "123456789",
    "email": "ryoo0504@naver.com",
    "name": "류지환",
    "nickname": "류지환",
    "profile_image": "https://ssl.pstatic.net/..."
  }
}
```

### 매핑 규칙

| Naver API 필드 | OAuthProfile 필드 | DB 저장 (users 테이블) | 설명 |
|----------------|-------------------|------------------------|------|
| `response.id` | `provider_user_id` | `provider_user_id` | Naver 고유 사용자 ID |
| `response.email` | `email` | `email` | 이메일 주소 |
| `response.name` | `name` | `username` | 이름 (예: "류지환") |
| `response.nickname` | `nickname` | `nickname` | 닉네임 (예: "류지환") |
| `response.profile_image` | `profile_image_url` | `profile_image_url` | 프로필 이미지 URL |

### DB 저장 예시

```sql
provider: 'naver'
provider_user_id: '123456789'
email: 'ryoo0504@naver.com'
username: '류지환'          -- name
nickname: '류지환'          -- nickname (보통 name과 동일)
profile_image_url: 'https://ssl.pstatic.net/...'
```

### 특징

- ✅ `name`과 `nickname`이 대부분 동일
- ✅ 이메일 필수 제공
- ✅ 프로필 이미지 URL 제공
- ❌ PKCE 미지원

---

## 💬 Kakao OAuth

### API 응답 구조

```json
{
  "id": 3340000000,
  "kakao_account": {
    "email": "user@example.com",
    "profile": {
      "nickname": "홍길동",
      "profile_image_url": "http://k.kakaocdn.net/..."
    }
  }
}
```

### 매핑 규칙

| Kakao API 필드 | OAuthProfile 필드 | DB 저장 (users 테이블) | 설명 |
|----------------|-------------------|------------------------|------|
| `id` | `provider_user_id` | `provider_user_id` | Kakao 고유 사용자 ID (숫자) |
| `kakao_account.email` | `email` | `email` | 이메일 주소 (선택적) |
| `kakao_account.profile.nickname` | `name` | `username` | 닉네임 |
| `kakao_account.profile.nickname` | `nickname` | `nickname` | 닉네임 (name과 동일) |
| `kakao_account.profile.profile_image_url` | `profile_image_url` | `profile_image_url` | 프로필 이미지 URL |

### DB 저장 예시

```sql
provider: 'kakao'
provider_user_id: '3340000000'
email: NULL                  -- 사용자가 동의하지 않으면 NULL
username: '홍길동'          -- profile.nickname
nickname: '홍길동'          -- profile.nickname (username과 동일)
profile_image_url: 'http://k.kakaocdn.net/...'
```

### 특징

- ✅ `nickname`을 username과 nickname 모두로 사용
- ⚠️ 이메일은 선택적 (사용자가 거부 가능)
- ✅ 프로필 이미지 URL 제공
- ✅ PKCE 지원
- ⚠️ scope를 보내지 않음 (카카오 개발자 콘솔에서 설정)

---

## 🗄️ DB 스키마 (users 테이블)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,                    -- 'google', 'naver', 'kakao'
    provider_user_id VARCHAR(255) NOT NULL,           -- 프로바이더의 고유 사용자 ID
    email VARCHAR(320),                               -- 이메일 (Optional)
    username VARCHAR(120),                            -- 사용자 이름
    nickname VARCHAR(120),                            -- 닉네임
    profile_image_url VARCHAR(512),                   -- 프로필 이미지 URL
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT uq_users_provider_identifier 
        UNIQUE (provider, provider_user_id)
);
```

### 제약 조건

- **필수 필드**: `provider`, `provider_user_id`
- **선택 필드**: `email`, `username`, `nickname`, `profile_image_url`
- **고유 키**: `(provider, provider_user_id)` 조합

---

## 📊 프로바이더별 비교표

| 항목 | Google | Naver | Kakao |
|------|--------|-------|-------|
| **nickname 저장값** | `given_name` (이름만) | `nickname` (닉네임) | `profile.nickname` |
| **username 저장값** | `name` (전체 이름) | `name` (이름) | `profile.nickname` |
| **이메일 필수 여부** | ✅ 필수 | ✅ 필수 | ⚠️ 선택적 |
| **프로필 이미지** | ✅ 제공 | ✅ 제공 | ✅ 제공 |
| **PKCE 지원** | ✅ 지원 | ❌ 미지원 | ✅ 지원 |
| **Scope 설정** | ✅ API에서 전송 | ✅ API에서 전송 | ❌ 콘솔에서 설정 |

---

## 🔄 자동 회원가입 로직

```python
# domains/auth/repositories/user_repository.py

async def upsert_from_profile(self, profile: OAuthProfile) -> User:
    existing = await self.get_by_provider(profile.provider, profile.provider_user_id)
    
    if existing:
        # 기존 회원 → 정보 업데이트
        existing.email = profile.email or existing.email
        existing.nickname = profile.nickname or existing.nickname
        existing.username = profile.name or existing.username
        if profile.profile_image_url:
            existing.profile_image_url = str(profile.profile_image_url)
        existing.last_login_at = now_utc()
        return existing
    
    # 신규 회원 → 자동 생성
    user = User(
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        email=profile.email,
        nickname=profile.nickname or profile.name,  # nickname 우선, 없으면 name
        username=profile.name or profile.nickname,  # name 우선, 없으면 nickname
        profile_image_url=str(profile.profile_image_url) if profile.profile_image_url else None,
        last_login_at=now_utc(),
    )
    self.session.add(user)
    return user
```

### 우선순위

| DB 필드 | 우선순위 |
|---------|----------|
| `nickname` | `profile.nickname` → `profile.name` |
| `username` | `profile.name` → `profile.nickname` |
| `email` | `profile.email` (없으면 NULL) |

---

## 🧪 테스트 데이터 예시

### Google 로그인 결과
```json
{
  "id": "6d3078fd-5b44-4e8b-86ca-ba467baf1bb7",
  "provider": "google",
  "email": "ryoo0504@gmail.com",
  "username": "jihwan ryu",
  "nickname": "jihwan",
  "profile_image_url": "https://lh3.googleusercontent.com/a/ACg8ocKIUC...",
  "created_at": "2025-11-20T11:43:06.467419Z",
  "last_login_at": "2025-11-20T11:43:06.470488Z"
}
```

### Naver 로그인 결과
```json
{
  "id": "5d6adcfa-bde0-46d1-b80a-a4cd67075add",
  "provider": "naver",
  "email": "ryoo0504@naver.com",
  "username": "류지환",
  "nickname": "류지환",
  "profile_image_url": null,
  "created_at": "2025-11-20T11:33:18.229787Z",
  "last_login_at": "2025-11-20T11:33:18.242709Z"
}
```

### Kakao 로그인 결과 (이메일 동의 안 함)
```json
{
  "id": "abc12345-...",
  "provider": "kakao",
  "email": null,
  "username": "홍길동",
  "nickname": "홍길동",
  "profile_image_url": "http://k.kakaocdn.net/...",
  "created_at": "2025-11-20T...",
  "last_login_at": "2025-11-20T..."
}
```

---

## 📝 주의사항

### 1. 이메일이 없는 경우
- Kakao는 사용자가 이메일 제공을 거부할 수 있음
- DB에 `email` 필드는 `NULL` 허용
- 이메일이 없어도 회원가입 가능

### 2. 닉네임/이름 처리
- Google: `given_name`과 `name`을 분리하여 저장
- Naver/Kakao: 대부분 동일한 값

### 3. 프로필 이미지 URL
- Pydantic의 `HttpUrl` 타입을 `str`로 변환하여 저장
- 변환하지 않으면 DB 저장 시 에러 발생

### 4. provider_user_id
- 각 프로바이더의 고유 사용자 식별자
- Google: 숫자 문자열 (예: "107754689264640366020")
- Naver: 숫자 문자열 (예: "123456789")
- Kakao: 숫자 (DB에는 문자열로 저장, 예: "3340000000")

---

## 🔗 관련 파일

- `domains/auth/services/providers/google.py` - Google OAuth 구현
- `domains/auth/services/providers/naver.py` - Naver OAuth 구현
- `domains/auth/services/providers/kakao.py` - Kakao OAuth 구현
- `domains/auth/repositories/user_repository.py` - 사용자 저장 로직
- `domains/auth/models/user.py` - User 모델 정의
- `domains/auth/schemas/oauth.py` - OAuthProfile 스키마

