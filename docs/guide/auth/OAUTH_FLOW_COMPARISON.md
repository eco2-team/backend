# OAuth 로그인 플로우 비교

## 📋 버전 1: JSON 응답 방식 (현재 버전)

### 특징
- 콜백 엔드포인트가 **JSON 응답**을 반환
- 프론트엔드가 콜백 URL을 직접 호출하여 결과를 처리
- SPA(React, Vue 등)에 적합

### 전체 절차

```
[사용자]
  ↓ 1. "네이버로 로그인" 버튼 클릭
[프론트엔드]
  ↓ 2. GET /api/v1/auth/naver
[백엔드]
  ↓ 3. { authorization_url: "https://nid.naver.com/..." } 응답
[프론트엔드]
  ↓ 4. window.location.href = authorization_url
[네이버]
  ↓ 5. 사용자 로그인/동의
[네이버]
  ↓ 6. http://localhost:8000/api/v1/auth/naver/callback?code=...&state=...
[백엔드]
  ↓ 7. JSON 응답 + 쿠키 설정
  {
    "success": true,
    "data": {
      "user": { "id": "...", "email": "...", ... }
    }
  }
[브라우저]
  ↓ 8. JSON 화면 표시 (개발자 확인용)
[프론트엔드]
  ↓ 9. /me API 호출하여 로그인 상태 확인
```

### API 엔드포인트

**1단계: Authorization URL 생성**
```bash
GET http://localhost:8000/api/v1/auth/naver
GET http://localhost:8000/api/v1/auth/google
GET http://localhost:8000/api/v1/auth/kakao
```

**응답:**
```json
{
  "success": true,
  "data": {
    "provider": "naver",
    "state": "...",
    "authorization_url": "https://nid.naver.com/oauth2.0/authorize?...",
    "expires_at": "2025-11-20T12:08:17Z"
  }
}
```

**2단계: OAuth 콜백 (자동)**
```
GET http://localhost:8000/api/v1/auth/naver/callback?code=...&state=...
```

**응답:**
```json
{
  "success": true,
  "data": {
    "user": {
      "id": "5d6adcfa-bde0-46d1-b80a-a4cd67075add",
      "provider": "naver",
      "email": "user@example.com",
      "username": "홍길동",
      "nickname": "홍길동",
      "profile_image_url": null,
      "created_at": "2025-11-20T11:33:18.229787Z",
      "last_login_at": "2025-11-20T11:33:18.242709Z"
    }
  }
}
```

**쿠키 자동 설정:**
- `s_access`: Access Token (15분)
- `s_refresh`: Refresh Token (14일)

**3단계: 로그인 확인**
```bash
GET http://localhost:8000/api/v1/auth/me
```

### 프론트엔드 구현 예시

```javascript
// 1. 로그인 버튼 클릭
async function handleLogin(provider) {
  try {
    const response = await fetch(`http://localhost:8000/api/v1/auth/${provider}`);
    const data = await response.json();
    
    if (data.success) {
      // OAuth 페이지로 이동
      window.location.href = data.data.authorization_url;
    }
  } catch (error) {
    console.error('로그인 실패:', error);
  }
}

// 2. 콜백 후 로그인 확인 (앱 로드 시)
async function checkLoginStatus() {
  try {
    const response = await fetch('http://localhost:8000/api/v1/auth/me', {
      credentials: 'include'
    });
    const data = await response.json();
    
    if (data.success) {
      // 로그인 상태
      console.log('현재 사용자:', data.data);
    }
  } catch (error) {
    // 로그아웃 상태
  }
}
```

### 장점
✅ SPA 친화적  
✅ API 응답을 명확하게 확인 가능  
✅ 프론트엔드가 에러 처리 제어  
✅ 개발/디버깅 용이  

### 단점
❌ 콜백 후 JSON이 브라우저에 표시됨 (UX 개선 필요)  
❌ 프론트엔드에서 추가 처리 필요  

---

## 📋 버전 2: 프론트엔드 리다이렉트 방식

### 특징
- 콜백 엔드포인트가 **프론트엔드로 리다이렉트**
- 전통적인 OAuth 플로우
- 서버 사이드 렌더링(SSR)에 적합

### 전체 절차

```
[사용자]
  ↓ 1. "네이버로 로그인" 버튼 클릭
[프론트엔드]
  ↓ 2. GET /api/v1/auth/naver
[백엔드]
  ↓ 3. { authorization_url: "https://nid.naver.com/..." } 응답
[프론트엔드]
  ↓ 4. window.location.href = authorization_url
[네이버]
  ↓ 5. 사용자 로그인/동의
[네이버]
  ↓ 6. http://localhost:8000/api/v1/auth/naver/callback?code=...&state=...
[백엔드]
  ↓ 7. 로그인 처리 + 쿠키 설정
  ↓ 8. HTTP 302 Redirect
[브라우저]
  ↓ 9. http://localhost:3000/login/success 자동 이동
[프론트엔드]
  ↓ 10. 성공 페이지 표시 + /me API 호출
```

### 콜백 엔드포인트 수정 필요

**현재 (JSON 응답):**
```python
@naver_router.get("/callback", response_model=LoginSuccessResponse)
async def naver_callback(code: str, state: str, ...):
    user = await service.login_with_provider(...)
    return LoginSuccessResponse(data=LoginData(user=user))
```

**수정 후 (리다이렉트):**
```python
@naver_router.get("/callback")
async def naver_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    ...
):
    # 사용자가 거부한 경우
    if error:
        return RedirectResponse(
            url=f"http://localhost:3000/login/error?message={error}",
            status_code=302
        )
    
    # 필수 파라미터 없음
    if not code or not state:
        return RedirectResponse(
            url="http://localhost:3000/login/error?message=Missing parameters",
            status_code=302
        )
    
    try:
        user = await service.login_with_provider(...)
        # 성공 - 프론트엔드로 리다이렉트
        return RedirectResponse(
            url="http://localhost:3000/login/success",
            status_code=302
        )
    except Exception as e:
        # 실패 - 에러 페이지로 리다이렉트
        return RedirectResponse(
            url=f"http://localhost:3000/login/error?message={str(e)}",
            status_code=302
        )
```

### 프론트엔드 구현 예시

**로그인 페이지 (동일):**
```javascript
async function handleLogin(provider) {
  const response = await fetch(`http://localhost:8000/api/v1/auth/${provider}`);
  const data = await response.json();
  window.location.href = data.data.authorization_url;
}
```

**성공 페이지 (`/login/success`):**
```javascript
// 자동으로 로그인 완료됨 (쿠키 설정됨)
async function loadUserInfo() {
  const response = await fetch('http://localhost:8000/api/v1/auth/me', {
    credentials: 'include'
  });
  const data = await response.json();
  
  if (data.success) {
    displayUser(data.data);
  }
}

window.onload = loadUserInfo;
```

**에러 페이지 (`/login/error`):**
```javascript
const urlParams = new URLSearchParams(window.location.search);
const errorMessage = urlParams.get('message');
displayError(errorMessage);
```

### 장점
✅ 깔끔한 UX (JSON이 사용자에게 보이지 않음)  
✅ 성공/실패 페이지로 자동 이동  
✅ 전통적인 OAuth 플로우  
✅ 에러 처리가 명확  

### 단점
❌ 프론트엔드 URL 하드코딩 필요  
❌ CORS 설정 더 신경써야 함  
❌ 개발 시 리다이렉트로 인한 디버깅 어려움  

---

## 🎯 권장 사항

### 프로덕션 환경
→ **버전 2 (리다이렉트 방식)** 추천
- 사용자가 JSON을 보지 않음
- 더 나은 UX

### 개발/테스트 환경
→ **버전 1 (JSON 응답)** 추천
- API 응답을 직접 확인 가능
- 디버깅 용이

### 구현 방법
환경 변수로 분기 처리:
```python
FRONTEND_REDIRECT_URL = os.getenv("FRONTEND_REDIRECT_URL")

if FRONTEND_REDIRECT_URL:
    # 리다이렉트 모드
    return RedirectResponse(url=f"{FRONTEND_REDIRECT_URL}/login/success")
else:
    # JSON 응답 모드
    return LoginSuccessResponse(data=LoginData(user=user))
```

---

## 📝 환경 설정

### 환경 변수 추가
```bash
# .env.local (로컬 개발)
FRONTEND_REDIRECT_URL=

# .env.prod (프로덕션)
FRONTEND_REDIRECT_URL=https://growbin.app
```

### OAuth Redirect URI 설정
**네이버/구글/카카오 개발자 콘솔:**
```
http://localhost:8000/api/v1/auth/naver/callback
http://localhost:8000/api/v1/auth/google/callback
http://localhost:8000/api/v1/auth/kakao/callback
```

**프로덕션:**
```
https://api.growbin.app/api/v1/auth/naver/callback
https://api.growbin.app/api/v1/auth/google/callback
https://api.growbin.app/api/v1/auth/kakao/callback
```

