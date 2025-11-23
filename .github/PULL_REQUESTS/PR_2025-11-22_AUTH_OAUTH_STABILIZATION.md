# Pull Request: Auth OAuth 안정화 (2025-11-20 ~ 2025-11-23)

## 📋 변경 사항

### 1. OAuth 콜백 안정화 (11/20~11/23)
- (11/20) 구글/카카오 로그인 실패 원인 추적을 위한 상세 로깅 및 import 정리.
- (11/21) RedirectResponse 객체 재사용으로 `Set-Cookie` 유지, 리다이렉트 이후에도 쿠키 손실 방지.
- (11/22) 쿠키 `domain`을 `.growbin.app`으로 확대해 dev/prod 서브도메인 간 세션 공유 가능하도록 변경.

### 2. 네트워크/보안 정비 (11/21~11/22)
- `allow-external-https` NetworkPolicy 추가로 auth 파드의 HTTPS egress 허용 → Kakao/Github 등 외부 provider 호출 안정화.
- ArgoCD GitHub webhook secret을 ExternalSecret + SSM 기반으로 재구성, 템플릿 문법 오류 및 README 수정.
- Pre-commit(Black/Ruff + 기본 hooks) 도입으로 CI lint/format 파이프라인 정상화.

### 3. DNS 구성 (11/23)
- Route53에 `frontend.growbin.app`, `frontend.dev.growbin.app` CNAME(Vercel) 레코드 추가  
  (Change IDs: `/change/C0319266JT9MJ5X34A3B`, `/change/C0282994NN7HNNOV0O6V`).
- growbin.app 전역으로 프런트 커스텀 도메인을 준비해 쿠키 정책과 일치.

## 🔍 커밋 하이라이트
```
5b005e4 fix(auth): share cookies across growbin.app subdomains
a952fcc fix(auth): persist cookies on oauth redirects
d81531e docs(webhook): Update ArgoCD webhook endpoint
7604cb3 fix(secrets): Fix ArgoCD webhook secret template syntax
fb696d8 fix(network): Allow external HTTPS egress for OAuth providers
a4a5d01 chore: Add pre-commit hooks for code quality
7531165 fix(auth): Fix import order for linter compliance
c8ce6ea feat(auth): Add error logging to OAuth callback handlers
```

## ✅ 테스트
- `kubectl logs -n auth deployment/auth-api --since=5m | grep -v health`
- Google / Kakao OAuth 로그인 시나리오 수동 검증
- Route53 `aws route53 get-change <id>`로 DNS 전파 상태 확인

## ✅ 체크리스트
- [x] Pre-commit (black/ruff 등) 통과
- [x] Dev 클러스터 배포/검증
- [x] DNS 변경 반영 대기 (Route53)
- [ ] Prod 반영 (향후)

