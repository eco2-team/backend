# 🤝 기여 가이드

AI Waste Coach Backend 프로젝트에 기여해주셔서 감사합니다!

## 🎯 기여 방법

### 1. 이슈 확인 및 생성

- [이슈 목록](https://github.com/your-org/sesacthon-backend/issues) 확인
- 중복된 이슈가 없는지 검색
- 새로운 이슈 생성 시 [템플릿](issue-guide.md) 사용

### 2. 개발 환경 설정

```bash
# 저장소 Fork
# GitHub에서 Fork 버튼 클릭

# Fork한 저장소 클론
git clone https://github.com/YOUR_USERNAME/sesacthon-backend.git
cd backend

# Upstream 저장소 추가
git remote add upstream https://github.com/original/sesacthon-backend.git

# 개발 환경 설정
make dev-setup
```

### 3. 브랜치 생성 및 작업

```bash
# develop 브랜치에서 시작
git checkout develop
git pull upstream develop

# feature 브랜치 생성
git checkout -b feature/1-your-feature
```

### 4. 코드 작성

- [코딩 컨벤션](../development/conventions.md) 준수
- 테스트 코드 작성
- 문서 업데이트

### 5. Pull Request 제출

- [PR 가이드](pull-request.md) 참고
- PR 템플릿 작성
- CI 검사 통과 확인

---

## 📝 기여 규칙

### 코드 품질

- ✅ Black, isort, Flake8 통과
- ✅ 모든 테스트 통과
- ✅ 커버리지 80% 이상 유지
- ✅ Docstring 작성

### 커밋 메시지

```bash
# 올바른 형식
feat: 사용자 프로필 조회 API 추가
fix: JWT 토큰 만료 시간 오류 수정
docs: API 문서 업데이트
```

자세한 내용은 [Git 워크플로우](../development/git-workflow.md)를 참고하세요.

---

## 🚀 첫 기여 시작하기

### Good First Issue

처음 기여하시나요? [good first issue](https://github.com/your-org/sesacthon-backend/labels/good%20first%20issue) 라벨을 확인하세요.

### 도움이 필요하신가요?

- 팀 Slack 채널에 질문
- [Issue](https://github.com/your-org/sesacthon-backend/issues/new) 생성
- [토론](https://github.com/your-org/sesacthon-backend/discussions) 참여

---

**문서 버전**: 1.0.0  
**최종 업데이트**: 2025-10-30

