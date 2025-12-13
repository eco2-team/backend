# Auth Service Guide (v0.8.0)

## Local Docker Testing

1. `.env.local` 생성  
   ```bash
   cd domains/auth
   cp env.local.sample .env.local
   ```
   - Google / Kakao / Naver OAuth 자격 증명을 **로컬 테스트용** 값으로 채웁니다.
2. 컨테이너 기동  
   ```bash
   docker compose -f domains/auth/docker-compose.auth-local.yml up --build
   ```
   - Postgres: `localhost:5433`
   - Redis: `localhost:6380`
   - Auth API: `http://localhost:8000`
3. 종료  
   ```bash
   docker compose -f domains/auth/docker-compose.auth-local.yml down -v
   ```
4. 주요 환경변수 (docker compose가 자동 주입)
   - `AUTH_DATABASE_URL=postgresql+asyncpg://sesacthon:sesacthon@db:5432/sesacthon`
   - `AUTH_REDIS_BLACKLIST_URL=redis://redis:6379/0`
   - `AUTH_REDIS_OAUTH_STATE_URL=redis://redis:6379/3`

## Kubernetes Deployment (dev/prod)

- OAuth 자격 증명은 **AWS SSM Parameter Store** → **External Secrets Operator** → `auth-secret` 로 주입됩니다.
- 토큰/세션 환경 변수는 `AUTH_` prefix 로 읽히며, `domains/auth/core/config.py` (`Settings` 클래스)가 단일 진실원(SSOT) 입니다.
- Auth API 이미지는 `docker.io/mng990/eco2:auth-{env}-latest` 태그를 사용합니다.

## OAuth Redirect & Frontend 설정

- `AUTH_FRONTEND_URL` 환경 변수를 통해 성공 리다이렉트 목적지를 제어합니다 (`Settings.frontend_url`).
- 기본값은 `https://frontend-beta-gray-c44lrfj3n1.vercel.app` 이지만, 운영 환경에서는 `https://frontend.dev.growbin.app` 와 같이 growbin 도메인으로 오버라이드해야 쿠키가 공유됩니다.
- 실패 시 리다이렉트는 `frontend_url + "/login?error=oauth_failed"` 로 자동 계산됩니다.

## 참고 문서

- `docs/guide/auth/README_COOKIE.md` – 쿠키/도메인 정책
- `docs/guide/auth/FRONTEND_AUTH_GUIDE.md` – 프론트 단 refresh 처리 가이드
- `docs/guide/auth/OAUTH_PROVIDER_MAPPING.md` – 프로바이더별 데이터 매핑
