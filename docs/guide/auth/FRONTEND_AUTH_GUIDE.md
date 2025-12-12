# Frontend Auth Integration Guide

프론트엔드에서 OAuth 로그인/쿠키 기반 세션을 안정적으로 사용하기 위한 핵심 정리입니다.
두 가지 이슈(도메인/쿠키 정책, Access 만료 시 Refresh 처리)에 대해 반드시 반영해 주세요.

---

## 1. Vercel 도메인 & 쿠키 정책

| 항목 | 현재 상태 | 필요한 조치 |
|------|-----------|-------------|
| 백엔드 쿠키 도메인 | `.growbin.app` (Secure, HttpOnly, SameSite=Lax) | 이미 growbin 서브도메인 전역 공유 가능 |
| API 엔드포인트 | `https://api.dev.growbin.app` | 고정 |
| 프론트(Vercel 기본) | `https://frontend-beta-gray-xxxxx.vercel.app` | **쿠키 확인 불가** (eTLD가 vercel.app라 브라우저가 growbin.app 쿠키를 노출하지 않음) |
| 프론트 커스텀 도메인 | `https://frontend.dev.growbin.app` (Route53 CNAME 완료) | Vercel 프로젝트에 커스텀 도메인 연결 → 이후 dev 환경은 반드시 이 URL 사용 |

> **중요**: 쿠키를 직접 볼 수 있는지는 중요하지 않더라도, 브라우저는 eTLD가 다르면 쿠키를 요청에 보내지 않습니다.
> 따라서 프론트 배포 URL을 `*.growbin.app` 으로 맞춰야 로그인 후 API 요청에서도 자동으로 쿠키가 포함됩니다.

---

## 2. Access 만료 & Refresh 자동화

- Access 토큰은 15분, Refresh 토큰은 14일 유지 (서버에서 회전 시 갱신).
- 서버는 `/api/v1/auth/refresh` 엔드포인트에서 두 쿠키를 동시에 재발급합니다.
- 클라이언트에서 다음과 같은 패턴으로 자동화해 주세요.

### 2-1. Access 만료 시 흐름
1. API 호출에서 `401 UNAUTHORIZED` 를 받으면, 곧바로 `POST /api/v1/auth/refresh` 를 호출합니다. (요청 시 `withCredentials` 필수)
2. Refresh 요청이 성공하면 서버가 새 Access/Refresh 쿠키를 내려주므로, 이후에는 사용하던 API 호출을 한 번만 다시 보냅니다.
3. Refresh까지 실패(또는 401)하면 세션이 만료된 것이므로 즉시 로그아웃/재로그인을 유도합니다.

### 2-2. 구현 방식 예시
- HTTP 인터셉터(Axios, React Query, TanStack Query 등)
- Fetch Wrapper / Service 모듈
- SPA/모바일 앱의 전역 에러 핸들러

구체적인 구현(인터셉터 구조, 재시도 횟수, 알림 UI 등)은 프론트엔드 팀 자율에 맡깁니다. 단, “401 → /refresh → 원요청 재시도 → 실패 시 로그아웃” 시나리오만 일관되게 지켜주세요.

---

## 3. 에러/예외 처리

| 상황 | 서버 응답 | 프론트 동작 |
|------|-----------|-------------|
| Access 쿠키 없음/변조 | `401 Missing access token` | 로그인 페이지로 이동 |
| Refresh 쿠키 없음/만료 | `401 Missing/Refresh token not found` | 로그인 페이지로 이동 |
| Refresh 블랙리스트 | `401 Token revoked` | “세션이 만료되었습니다” 토스트 후 로그인 페이지 |
| Provider 오류 | `502 Provider API error` | “SNS 로그인 실패” 알림 |

---

## 4. 체크리스트

- [ ] 프론트 배포 URL을 `frontend.dev.growbin.app` 로 전환했는가?
- [ ] 모든 API 요청이 `withCredentials: true` 로 호출되는가?
- [ ] 401 응답 시 `/refresh` 자동 호출/재시도 로직이 있는가?
- [ ] Refresh 실패 시 강제 로그아웃/재로그인 UX가 준비되어 있는가?

문의나 추가 요구 사항이 있으면 공유해 주세요.
이 문서는 프론트엔드 온보딩/핸드오프 자료로 사용 가능합니다.
