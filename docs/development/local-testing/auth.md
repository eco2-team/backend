# Auth API 로컬 테스트 가이드

## 한눈에 보기

- **기본 포트**: `8000`
- **Swagger**: `http://localhost:8000/api/v1/auth/docs`
- **헬스 체크**: `/health`, `/ready`, `/metrics`
- **의존성**: Postgres 16, Redis 7 (블랙리스트/State 관리), OAuth 공급자 자격증명

## 1. 사전 준비

1. 가상환경 + 의존성 설치
   ```bash
   cd /Users/mango/workspace/SeSACTHON/backend
   source .venv/bin/activate
   pip install -r domains/auth/requirements.txt
   pytest domains/auth/tests
   ```
2. `domains/auth/.env.local` 작성  
   (파일이 없으면 docker compose가 실패합니다)
   ```bash
   cat > domains/auth/.env.local <<'EOF'
   AUTH_ENVIRONMENT=local
   AUTH_FRONTEND_URL=http://localhost:5173
   AUTH_COOKIE_DOMAIN=localhost
   AUTH_JWT_SECRET_KEY=local-auth-secret
   AUTH_CHARACTER_API_BASE_URL=http://host.docker.internal:8004
   AUTH_CHARACTER_API_TOKEN=local-character-token

  # 실제 OAuth 앱 등록 값 (모든 공급자에 localhost 콜백을 등록해 두었습니다)
  AUTH_GOOGLE_CLIENT_ID=YOUR_LOCAL_GOOGLE_CLIENT_ID
  AUTH_GOOGLE_CLIENT_SECRET=YOUR_LOCAL_GOOGLE_CLIENT_SECRET
  AUTH_GOOGLE_REDIRECT_URI=http://localhost:5173/auth/google/callback

  AUTH_KAKAO_CLIENT_ID=YOUR_LOCAL_KAKAO_REST_API_KEY
  AUTH_KAKAO_REDIRECT_URI=http://localhost:5173/auth/kakao/callback

  AUTH_NAVER_CLIENT_ID=YOUR_LOCAL_NAVER_CLIENT_ID
  AUTH_NAVER_CLIENT_SECRET=YOUR_LOCAL_NAVER_CLIENT_SECRET
  AUTH_NAVER_REDIRECT_URI=http://localhost:5173/auth/naver/callback
   EOF
   ```
   > OAuth 공급자와의 실 로그인까지 확인하려면 위 값에 실제 자격증명이 필수입니다.

## 2. docker compose로 전체 스택 실행

```bash
cd /Users/mango/workspace/SeSACTHON/backend/domains/auth
docker-compose -f docker-compose.auth-local.yml up --build -d
# 컨테이너 목록
docker-compose -f docker-compose.auth-local.yml ps
```

- `db` (Postgres 16), `redis`, `db-bootstrap`, `auth` 서비스가 순차적으로 뜹니다.
- 종료 시 `docker compose -f docker-compose.auth-local.yml down -v` 로 볼륨까지 정리하세요.

## 3. 기본 동작 확인

```bash
# 서버 상태
curl -s http://localhost:8000/api/v1/auth/health | jq
curl -s http://localhost:8000/api/v1/auth/ready | jq
curl -s http://localhost:8000/api/v1/auth/metrics | jq

# OAuth authorization URL 생성 (Google 예시)
curl -s "http://localhost:8000/api/v1/auth/google?redirect_uri=http://localhost:5173/auth/google/callback&device_id=local-device" | jq
```

## 4. 쿠키 발급 / 로그인 플로우

1. 위 authorization API 응답의 `authorization_url`을 브라우저에서 열고 실제 공급자(Google 등)에 로그인합니다.
2. 설정한 `redirect_uri` 로 돌아오면 `code`, `state` 쿼리 파라미터가 붙어 있습니다.
3. 프론트에서 다음 API 호출을 보내면 세션 쿠키(`s_access`, `s_refresh`)가 내려옵니다.

```bash
curl -i -X POST http://localhost:8000/api/v1/auth/login/google \
  -H 'Content-Type: application/json' \
  -d '{
        "code": "<브라우저에서 받은 code>",
        "state": "<브라우저에서 받은 state>",
        "redirect_uri": "http://localhost:5173/auth/google/callback"
      }'
```

4. 쿠키를 포함해 `/api/v1/auth/me`를 호출하면 로그인 정보 확인 가능:

```bash
curl -s --cookie "s_access=<Set-Cookie 값>" http://localhost:8000/api/v1/auth/me | jq
```

> `Provider API error` 가 발생하면 `.env.local`의 client id/secret/redirect가 실제 등록 정보와 일치하는지 확인하세요.

## 5. 다른 도메인과 함께 사용할 때

실제 JWT 검증 + 세션 쿠키 흐름을 통합적으로 확인하려면 아래 순서를 그대로 따라 주세요.

1. 위 섹션 2의 명령으로 Auth 스택을 띄워 둡니다.
2. 브라우저 로그인으로 `s_access` 쿠키를 확보하고, 터미널 환경 변수로 저장합니다.
3. 테스트하려는 도메인의 `*_AUTH_DISABLED` 값을 `false` 로 두고 재기동합니다.
4. 모든 도메인이 동일한 `AUTH_JWT_SECRET_KEY` 값을 사용하도록 맞춥니다. (대부분의 서비스는 `AUTH_*` 이름을 alias 로 받아들이므로 별도의 `<DOMAIN>_JWT_SECRET_KEY` 를 설정할 필요가 없습니다.)
5. 아래 명령 템플릿 중 필요한 것만 골라 실행하면, 쿠키를 포함한 실제 요청까지 한 번에 검증할 수 있습니다.

```bash
# 0) 공통: Auth 스택과 동일한 JWT 시크릿 + s_access 쿠키 저장
export AUTH_JWT_SECRET_KEY=local-auth-secret
export S_ACCESS_COOKIE='<브라우저에서 복사한 s_access 값>'

# 1) My API (docker compose)
cd /Users/mango/workspace/SeSACTHON/backend/domains/my
MY_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  docker compose -f docker-compose.my-local.yml up --build -d
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  http://localhost:8002/api/v1/users/<보호된-엔드포인트> | jq

# 2) Scan API (uvicorn)
cd /Users/mango/workspace/SeSACTHON/backend
SCAN_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  uvicorn domains.scan.main:app --reload --port 8003
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  "http://localhost:8003/api/v1/scan/classify" \
  -H 'Content-Type: application/json' \
  -d '{"image_urls":["https://..."],"user_input":"텍스트"}'

# 3) Character API (uvicorn)
cd /Users/mango/workspace/SeSACTHON/backend
CHARACTER_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  uvicorn domains.character.main:app --reload --port 8004
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  http://localhost:8004/api/v1/character/rewards | jq

# 4) Location API (docker compose)
cd /Users/mango/workspace/SeSACTHON/backend/domains/location
LOCATION_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  docker compose -f docker-compose.location-local.yml up --build -d
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  "http://localhost:8010/api/v1/location/search?query=강남" | jq

# 5) Image API (docker compose)
cd /Users/mango/workspace/SeSACTHON/backend/domains/image
IMAGE_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  docker compose -f docker-compose.image-local.yml up --build -d
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  http://localhost:8020/api/v1/image/upload/init \
  -H 'Content-Type: application/json' \
  -d '{"target":"chat","mime_type":"image/png"}'

# 6) Chat API (uvicorn)
cd /Users/mango/workspace/SeSACTHON/backend
CHAT_AUTH_DISABLED=false AUTH_JWT_SECRET_KEY=$AUTH_JWT_SECRET_KEY \
  uvicorn domains.chat.main:app --reload --port 8030
curl -s --cookie "s_access=${S_ACCESS_COOKIE}" \
  http://localhost:8030/api/v1/chat/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"페트병 어떻게 버려?"}' | jq
```

> 위 예시는 대표 도메인만 실어두었습니다. 나머지 서비스도 동일하게 `*_AUTH_DISABLED=false` 상태에서 Auth 스택이 발급한 `s_access` 쿠키를 `curl --cookie` 또는 브라우저/포스트맨에 첨부하면 됩니다.

## 6. Troubleshooting

| 증상 | 조치 |
| ---- | ---- |
| `pg_config executable not found` | 호스트에 Postgres 클라이언트 패키지를 설치하거나 Docker Compose를 이용합니다. |
| OAuth 콜백이 400 | `.env.local` 의 redirect URI와 실제 요청 URI를 동일하게 맞춥니다. |
| `/api/v1/auth/me` 401 | 쿠키가 설정되지 않은 상태입니다. 브라우저로 OAuth 로그인 후 다시 호출하세요. |

