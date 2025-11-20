# 배포 준비 체크리스트

## ✅ 개발 완료
- [x] OAuth 플로우 구현 (Google, Naver, Kakao)
- [x] 콜백 엔드포인트
- [x] 자동 회원가입
- [x] JWT + Cookie 인증
- [x] 로그아웃 기능
- [x] 응답 표준화
- [x] 문서화

## 🔧 배포 전 필수 작업

### A. 코드 정리
- [ ] 불필요한 엔드포인트 제거 (POST /login/{provider})
- [ ] 불필요한 import 제거 (RedirectResponse)
- [ ] OAuthAuthorizeParams 단순화

### B. 환경 설정
- [ ] 프로덕션 환경 변수 설정
  - AUTH_ENVIRONMENT=prod
  - Redirect URI 프로덕션 URL
  - JWT_SECRET_KEY (강력한 시크릿)
- [ ] CORS 설정 변경 (allow_origins)
- [ ] 쿠키 설정 확인 (secure=True)

### C. DB 마이그레이션
- [ ] Alembic 마이그레이션 스크립트 생성
- [ ] 테이블 생성 스크립트 준비

### D. OAuth 콘솔 설정
- [ ] Google: 프로덕션 Redirect URI 등록
- [ ] Naver: 프로덕션 Redirect URI 등록
- [ ] Kakao: 프로덕션 Redirect URI 등록

### E. 테스트
- [ ] 로컬 전체 플로우 테스트
- [ ] DB 스키마 생성 확인
- [ ] 로그인 → 로그아웃 테스트
- [ ] 각 프로바이더별 테스트

### F. CI/CD
- [ ] Docker 이미지 빌드 테스트
- [ ] Kubernetes manifest 확인
- [ ] Health check 엔드포인트 확인

### G. Git
- [ ] 변경사항 커밋
- [ ] feature/auth → develop 머지
- [ ] develop → main 머지 (릴리즈)

## 🎯 우선순위

### Phase 1: 코드 완성 (지금)
1. 불필요한 코드 정리
2. 환경 설정 준비
3. 로컬 테스트

### Phase 2: 배포 준비
1. 변경사항 커밋
2. 브랜치 머지
3. Docker 이미지 빌드

### Phase 3: 프로덕션 배포
1. OAuth 콘솔 설정
2. Kubernetes 배포
3. 프로덕션 테스트

## 📋 예상 소요 시간
- Phase 1: 30분
- Phase 2: 20분  
- Phase 3: 40분
- **총 약 1.5시간**

