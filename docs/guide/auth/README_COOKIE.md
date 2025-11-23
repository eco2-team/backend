# Cookie 설정 가이드

## 현재 설정

`domains/auth/services/auth.py`에서 다음과 같이 쿠키를 관리합니다:

```python
ACCESS_COOKIE_NAME = "s_access"
REFRESH_COOKIE_NAME = "s_refresh"
COOKIE_PATH = "/"
COOKIE_SAMESITE = "lax"
COOKIE_DOMAIN = ".growbin.app"  # None: 현재 도메인만, ".dev.growbin.app": 서브도메인 공유
```

### 쿠키 속성

- `httponly=True`: JavaScript에서 접근 불가 (XSS 방어)
- `secure=True`: HTTPS에서만 전송 (중간자 공격 방어)
- `samesite="lax"`: Cross-site 요청 시 GET 요청에서만 쿠키 전송
- `path="/"`: 모든 경로에서 쿠키 유효
- `domain=None`: 기본적으로 현재 도메인에만 바인딩

## Domain 설정

### Case 1: 공용 도메인 (현재 기본)

```python
COOKIE_DOMAIN = ".growbin.app"
```

- dev: `api.dev.growbin.app`, `frontend.dev.growbin.app`
- prod: `api.growbin.app`, `growbin.app`
- 하나의 쿠키로 모든 `*.growbin.app` 서브도메인 접근 가능

### Case 2: 환경별 세분화

```python
import os
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", ".growbin.app")
```

- dev만 `.dev.growbin.app` 으로 제한하고 싶다면 ConfigMap/Secret에서 값을 덮어쓰면 됩니다.

> `domain` 앞에 반드시 `.`(점)을 붙여야 하위 서브도메인이 모두 포함됩니다.

## CORS 설정

`domains/auth/main.py`에서 기본적으로 전체 허용으로 등록되어 있습니다 (개발 편의성 목적):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # 운영환경에서는 특정 도메인으로 제한 권장
    allow_credentials=True,        # 쿠키 포함 요청 허용
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 운영 환경 권장 설정

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dev.growbin.app",
        "https://console.dev.growbin.app",
        "https://growbin.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)
```

## OAuth Callback 흐름

1. 사용자가 `/api/v1/auth/google/authorize` 호출
2. Google 로그인 페이지로 리다이렉트
3. 로그인 후 `/api/v1/auth/google/callback?code=...` 콜백
4. 백엔드에서 토큰 발급 및 쿠키 설정
5. 프론트엔드 URL로 최종 리다이렉트

**쿠키가 저장되지 않는 경우 체크리스트**:
- [ ] `secure=True`가 설정되었는데 HTTP로 접근하고 있지 않은가?
- [ ] `domain` 설정이 프론트엔드 도메인과 맞는가?
- [ ] CORS `allow_credentials=True`가 설정되었는가?
- [ ] 프론트엔드에서 `credentials: 'include'` 옵션을 사용하는가?
- [ ] 최종 리다이렉트 URL이 쿠키 도메인 범위 내에 있는가?

## 테스트 방법

### 1. 브라우저 개발자 도구

**Network 탭**:
```
Response Headers에서 확인:
Set-Cookie: s_access=...; HttpOnly; Secure; SameSite=Lax; Path=/; Domain=.dev.growbin.app
```

**Application 탭**:
- Cookies → `api.dev.growbin.app` (또는 설정한 domain)
- `s_access`, `s_refresh` 쿠키가 있는지 확인

### 2. curl 테스트

```bash
# 로그인 (callback 이후)
curl -i -X POST https://api.dev.growbin.app/api/v1/auth/google/callback \
  -H "Content-Type: application/json" \
  -d '{"code":"...","state":"..."}'

# Response Header에서 Set-Cookie 확인
```

### 3. 로그 확인

```bash
kubectl logs -n auth -l app=auth-api --tail=100 -f | grep -i cookie
```

## 트러블슈팅

### 쿠키가 저장되지 않음

1. **HTTPS 미사용**
   - `secure=True`이므로 HTTP에서는 쿠키가 설정되지 않음
   - 로컬 Docker 개발에서만 `secure=False`를 임시 허용하고, 운영/스테이징은 반드시 HTTPS 사용

2. **Domain 불일치**
   - 프론트엔드가 `console.dev.growbin.app`인데 domain이 `api.dev.growbin.app`로 고정
   - `COOKIE_DOMAIN = ".dev.growbin.app"`으로 변경

3. **SameSite 제약**
   - Cross-site 요청에서 쿠키가 차단됨
   - `samesite="none"`으로 변경 시 반드시 `secure=True` 필요

4. **브라우저 쿠키 정책**
   - Safari/Chrome에서 서드파티 쿠키 차단 설정 확인
   - 시크릿/프라이빗 모드는 쿠키 제한이 더 엄격함

### 쿠키는 있는데 요청에 포함되지 않음

1. **CORS credentials**
   ```javascript
   // 프론트엔드에서 반드시 설정
   fetch('https://api.dev.growbin.app/api/v1/auth/me', {
     credentials: 'include'  // 쿠키 포함
   })
   ```

## 참고 자료

- [MDN - Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [FastAPI Cookies](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [OWASP Cookie Security](https://owasp.org/www-community/controls/SecureCookieAttribute)


