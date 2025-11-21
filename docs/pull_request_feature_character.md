# Pull Request · feature/character → develop

## 📋 변경 사항
- Character 서비스 데이터 계층 재구성 및 공유 JWT 의존성 도입
- 멀티 스테이지 Dockerfile·README 추가, Redis/Postgres DNS 가이드 문서화
- ArgoCD dev 환경 `targetRevision` 을 `develop` 으로 통일

## 🔧 상세 내용
1. `services/character/app/database/` 로 SQLAlchemy Base / Session / Models 이관
2. `services/_shared/security/` JWT 모듈 재사용 및 Character 라우터 통합
3. Dockerfile 헬스체크·비루트 구성, `services/character/README.md` 작성
4. `workloads/domains/character/base/configmap.yaml` 등 GitOps 경로 및 가이드 업데이트
5. dev ArgoCD Applications 의 `targetRevision` 을 `develop` 으로 변경

## 🧪 테스트
```bash
cd services/character
python3 -m pytest
```

## 🚀 배포 영향
- Character API 재배포 시 Docker Hub 리포지토리(`docker.io/mng990/eco2`)는 동일
- ArgoCD dev 환경이 `develop` 브랜치를 기준으로 자동 Sync

## ✅ 체크리스트
- [ ] feature/character 브랜치 push (SSH 권한 필요)
- [ ] GitHub PR 생성 후 리뷰 요청
