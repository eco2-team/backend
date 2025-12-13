# ext-authz 헤더 주입 확장 계획 (x-scope 제외)

## 현황
- ext-authz(Go) 허용 시 `x-user-id` 헤더에 `sub`를 주입.
- 도메인 서비스는 주로 `_shared.security.jwt.extract_token_payload`로 토큰 클레임(sub/jti/type/exp/iat/provider 등)을 언패킹.
- Envoy ext_authz 연동(05-istio)으로 헤더 전달 기반은 이미 존재하나, 추가 클레임 헤더는 주입하지 않음.

## 목표
- 공통 의존성 없이 헤더만으로 도메인 서비스가 사용자/토큰 메타데이터를 소비할 수 있도록 확장하되, `x-scope`는 제외.

## 주입 대상 제안 (예시)
- `x-user-id`: `sub` (기존)
- `x-jti`: 토큰 JTI
- `x-token-type`: access/refresh
- `x-provider`: kakao/google 등
- `x-token-iat`: iat (Unix)
- `x-token-exp`: exp (Unix)
- `x-token-iss`: iss
- `x-token-aud`: aud
- `x-token-nbf`: nbf

## 적용 단계
1) ext-authz: OkHttpResponse 헤더에 위 필드 주입 추가(검증 통과 시).  
2) Envoy/Istio: ext_authz 응답 헤더를 업스트림으로 전달하는 설정 유지(기본 동작 확인).  
3) 서비스: `_shared` 의존 최소화를 원하는 경로에서 헤더 파싱으로 전환하거나, 헤더가 없을 때 기존 파서를 fallback으로 사용.  
4) 검증: 헤더 전달/누락 시나리오에 대한 통합 테스트(allow/deny, 만료/블랙리스트) 추가.

## 유의사항
- 민감정보 최소화: payload 전체 전달 금지, 필요한 최소 클레임만 헤더화.
- 캐시/로그: 헤더 기반 로그에 PII가 남지 않도록 필터링 고려.
- 시계 동기화: exp/nbf/iat는 기존 clock skew(기본 5s)와 정합 유지.
