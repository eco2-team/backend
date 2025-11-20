# PR: Feature/character → develop

## 개요
- Character 서비스 구조 개편 (database 패키지, 공유 JWT 모듈)
- Dockerfile 멀티 스테이지 및 비루트 실행
- Redis/Postgres DNS 확인 가이드 문서화
- ArgoCD dev 환경 targetRevision 을 develop 으로 정렬

## 변경 요약
1. `services/character/app/database/` 로 SQLAlchemy Base/Session/Models 이관
2. `services/_shared/security/` JWT 유틸 도입 및 Character 라우터 통합
3. Dockerfile 헬스체크/비루트 구성, README 추가
4. `workloads/apis/character/base/configmap.yaml` 등 GitOps 경로 업데이트
5. Dev ArgoCD Applications 의 targetRevision 을 `develop` 으로 통일

## 테스트
```bash
cd services/character
python3 -m pytest
```

## 배포 영향
- Character API 재배포 시 Docker Hub 이미지 경로 동일 (docker.io/mng990/eco2)
- ArgoCD dev 환경은 이제 develop 브랜치 기준으로 sync

## TODO
- [ ] feature/character 브랜치 push (SSH 권한 필요)
- [ ] GitHub PR 생성 후 리뷰 요청
