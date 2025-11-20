# Version 0.7.3 - GitOps Deployment

## Local Docker Testing

1. `cp domain/auth/env.local.sample domain/auth/.env.local` 후 OAuth/JWT 값을 채워주세요.
2. `docker compose -f domain/docker-compose.auth-local.yml up --build` (worktree 루트에서 실행).
   - Postgres: `localhost:5433`
   - Redis: `localhost:6380`
3. 테스트 후 `docker compose -f domain/docker-compose.auth-local.yml down -v` 로 정리합니다.
