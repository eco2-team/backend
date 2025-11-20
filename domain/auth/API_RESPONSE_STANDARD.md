# 표준화된 API 응답 형식 적용

## 변경 사항

### 1. 공통 응답 스키마 생성 (`schemas/common.py`)

모든 API 응답을 일관된 형식으로 제공하기 위한 공통 스키마를 추가했습니다:

```python
{
  "success": true,
  "data": { ... },
  "error": null
}
```

**성공 응답:**
```python
{
  "success": true,
  "data": {
    "user": {
      "id": "...",
      "email": "..."
    }
  },
  "error": null
}
```

**실패 응답:**
```python
{
  "success": false,
  "data": null,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Missing access token",
    "field": null  // validation error인 경우 필드명
  }
}
```

### 2. 커스텀 Exception Handler (`core/exceptions.py`)

모든 예외를 표준 형식으로 변환하는 핸들러를 추가했습니다:

- `HTTPException`: HTTP 상태 코드에 따라 적절한 에러 코드 매핑
- `RequestValidationError`: Pydantic validation 에러 처리
- `Exception`: 일반 예외를 500 에러로 변환

**에러 코드 매핑:**
- `400` → `BAD_REQUEST`
- `401` → `UNAUTHORIZED`
- `403` → `FORBIDDEN`
- `404` → `NOT_FOUND`
- `409` → `CONFLICT`
- `422` → `VALIDATION_ERROR`
- `500` → `INTERNAL_SERVER_ERROR`

### 3. Auth 스키마 업데이트 (`schemas/auth.py`)

기존 응답 모델을 표준 형식으로 래핑:

- `AuthorizationResponse` → `AuthorizationSuccessResponse`
- `LoginResponse` → `LoginSuccessResponse`
- `LogoutResponse` → `LogoutSuccessResponse`
- `User` → `UserSuccessResponse`

### 4. 엔드포인트 수정

모든 엔드포인트가 표준 응답 형식을 사용하도록 수정:

- `api/v1/endpoints/auth.py`: 인증 관련 엔드포인트
- `api/v1/endpoints/health.py`: Health check 엔드포인트
- `api/v1/endpoints/metrics.py`: Metrics 엔드포인트

### 5. Main 앱 설정 (`main.py`)

Exception handler를 앱에 등록하여 모든 에러를 자동으로 표준 형식으로 변환합니다.

## 사용 예시

### 성공 케이스

**요청:**
```bash
GET /api/v1/auth/me
Cookie: s_access=<valid_token>
```

**응답:**
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "provider": "google",
    "email": "user@example.com",
    "username": "user",
    "nickname": "User",
    "profile_image_url": "https://example.com/profile.jpg",
    "created_at": "2024-01-01T00:00:00Z",
    "last_login_at": "2024-01-02T00:00:00Z"
  },
  "error": null
}
```

### 실패 케이스

**요청:**
```bash
GET /api/v1/auth/me
# No cookie
```

**응답:**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Missing access token",
    "field": null
  }
}
```

### Validation 에러

**요청:**
```bash
POST /api/v1/auth/login/google
{
  "code": "",  // 빈 문자열 - min_length=1 위반
  "state": "abc"  // 너무 짧음 - min_length=8 위반
}
```

**응답:**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "String should have at least 1 character",
    "field": "body.code"
  }
}
```

## 기대 효과

1. **일관성**: 모든 API 응답이 동일한 구조를 따름
2. **타입 안정성**: 클라이언트에서 응답 타입을 정확히 예측 가능
3. **에러 처리 간소화**: 클라이언트에서 `success` 필드로 성공/실패 판단
4. **디버깅 용이**: 구조화된 에러 코드와 메시지로 문제 파악 쉬움
5. **Swagger 문서화**: OpenAPI 스펙에 정확한 응답 형식이 표시됨

## 마이그레이션 가이드

기존 클라이언트 코드를 수정해야 합니다:

**Before:**
```typescript
const response = await fetch('/api/v1/auth/me');
const user = await response.json();
console.log(user.email);
```

**After:**
```typescript
const response = await fetch('/api/v1/auth/me');
const result = await response.json();

if (result.success) {
  console.log(result.data.email);
} else {
  console.error(result.error.code, result.error.message);
}
```

