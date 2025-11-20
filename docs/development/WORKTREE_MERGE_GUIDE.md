# 🌳 Git Worktree 병합 가이드

## 📍 현재 상황

```
메인 저장소: /Users/mango/workspace/SeSACTHON/backend
  └─ 브랜치: feature/character (현재 체크아웃)

Worktree: /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth
  └─ 브랜치: feature/auth (작업 중) ⭐
```

---

## 🎯 병합 전략 (2가지 방법)

### 방법 1: 로컬 병합 (빠른 방법) ✅

#### Step 1: Worktree에서 변경사항 커밋
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth

# 변경사항 스테이징
git add domain/
git add workloads/apis/auth/base/configmap.yaml
git add DEPLOYMENT_CHECKLIST.md
git add KUSTOMIZE_IMAGE_CHECK.md
git add TODAY_CHANGES.md

# 오래된 services/ 디렉토리 삭제 확인 (이미 삭제됨)
git status

# 커밋
git commit -m "feat(auth): OAuth failure redirect and PostgreSQL schema setup

- Add OAuth login failure redirect to frontend
- Configure auth schema for PostgreSQL tables  
- Add init_db.py schema auto-creation
- Update ConfigMap with frontend URL
- Verify Kustomize image configuration
- Add deployment and kustomize check documentation"
```

#### Step 2: 원격 브랜치에 푸시
```bash
git push origin feature/auth
```

#### Step 3: 메인 저장소에서 develop으로 병합
```bash
# 메인 저장소로 이동
cd /Users/mango/workspace/SeSACTHON/backend

# develop 브랜치로 체크아웃
git checkout develop

# 원격 develop 최신화
git pull origin develop

# feature/auth 브랜치 병합
git merge feature/auth

# 충돌 해결 (있다면)
# git status 확인 후 충돌 파일 수정
# git add <충돌_해결_파일>
# git commit

# develop에 푸시
git push origin develop
```

---

### 방법 2: Pull Request (권장) 🎯

#### Step 1: Worktree에서 변경사항 커밋 & 푸시
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth

# 변경사항 스테이징 및 커밋 (방법1과 동일)
git add domain/ workloads/ *.md
git commit -m "feat(auth): OAuth failure redirect and PostgreSQL schema setup"

# 원격 브랜치에 푸시
git push origin feature/auth
```

#### Step 2: GitHub에서 Pull Request 생성
```
1. GitHub 저장소 접속
2. "Pull requests" 탭 클릭
3. "New pull request" 버튼
4. Base: develop ← Compare: feature/auth
5. 제목: "feat(auth): OAuth failure redirect and PostgreSQL schema setup"
6. 설명 작성 (아래 템플릿 사용)
7. "Create pull request" 클릭
```

#### PR 설명 템플릿
```markdown
## 🎯 작업 내용

### OAuth 로그인 실패 리다이렉트
- OAuth 로그인 실패 시 프론트엔드로 자동 리다이렉트
- 경로: `https://frontend-beta-gray-c44lrfj3n1.vercel.app/login?error=oauth_failed`
- 적용: Google, Kakao, Naver 3개 프로바이더

### PostgreSQL 스키마 설정
- `auth` 스키마에 테이블 생성
- 테이블: `auth.users`, `auth.login_audits`
- init_db.py에서 스키마 자동 생성

### 설정 파일 추가
- ConfigMap에 프론트엔드 URL 추가
- 배포 체크리스트 문서 추가
- Kustomize 설정 검증 문서 추가

## 📊 변경 통계
- 178 files changed
- +240 insertions, -4,733 deletions

## ✅ 테스트
- [x] Kustomize build 성공
- [x] Dockerfile 빌드 컨텍스트 검증
- [x] 스키마 설정 확인
- [ ] Docker 이미지 빌드 & 푸시 (병합 후)
- [ ] 배포 및 동작 테스트 (병합 후)

## 📝 관련 이슈
- #이슈번호 (있다면)
```

#### Step 3: 리뷰 & 병합
```
1. 팀원 리뷰 요청
2. 리뷰 승인 후 "Merge pull request" 클릭
3. Squash and merge 또는 Merge commit 선택
4. 병합 완료!
```

---

## 🔄 병합 후 Worktree 정리

### Option 1: Worktree 유지 (다음 작업 계속)
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth

# develop의 최신 변경사항 가져오기
git fetch origin develop
git rebase origin/develop

# 또는 새 브랜치 생성
git checkout -b feature/auth-phase2
```

### Option 2: Worktree 삭제 (작업 완료)
```bash
# 메인 저장소로 이동
cd /Users/mango/workspace/SeSACTHON/backend

# Worktree 제거
git worktree remove worktrees/feature-auth

# 또는 강제 제거 (변경사항 무시)
git worktree remove --force worktrees/feature-auth

# 브랜치 삭제 (선택)
git branch -d feature/auth
git push origin --delete feature/auth
```

---

## ⚠️ 주의사항

### 1. Worktree 작업 시
- ✅ **DO**: Worktree에서 커밋 & 푸시
- ❌ **DON'T**: 메인 저장소에서 같은 브랜치 체크아웃 (충돌 발생)

### 2. 병합 전 확인사항
```bash
# Worktree에서 확인
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth
git status                    # 커밋 안된 변경사항 확인
git log origin/develop..HEAD  # 병합될 커밋 확인
git diff origin/develop       # 변경사항 확인
```

### 3. 충돌 발생 시
```bash
# 병합 중 충돌 발생
git status          # 충돌 파일 확인
# 충돌 파일 수정
git add <파일>
git commit          # 또는 git merge --continue

# 병합 취소하고 싶다면
git merge --abort
```

---

## 🚀 추천 워크플로우

### 1단계: 작업 완료 확인 (Worktree)
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth
git status
git log --oneline -5
```

### 2단계: 커밋 & 푸시 (Worktree)
```bash
git add .
git commit -m "feat(auth): complete OAuth and schema setup"
git push origin feature/auth
```

### 3단계: Pull Request 생성 (GitHub)
```
GitHub에서 PR 생성 → 리뷰 → 병합
```

### 4단계: 메인 저장소 동기화
```bash
cd /Users/mango/workspace/SeSACTHON/backend
git checkout develop
git pull origin develop
```

### 5단계: Worktree 정리 (선택)
```bash
# 계속 사용할 경우
cd worktrees/feature-auth
git fetch origin
git rebase origin/develop

# 삭제할 경우
cd /Users/mango/workspace/SeSACTHON/backend
git worktree remove worktrees/feature-auth
```

---

## 📋 현재 해야 할 작업

### 즉시 실행 가능
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth

# 1. 변경사항 확인
git status

# 2. 스테이징
git add domain/ workloads/apis/auth/base/configmap.yaml *.md

# 3. 커밋
git commit -m "feat(auth): OAuth failure redirect and PostgreSQL schema setup"

# 4. 푸시
git push origin feature/auth
```

### 그 다음
- GitHub에서 PR 생성 (develop ← feature/auth)
- 또는 로컬에서 직접 병합

---

**작성일**: 2025-11-20  
**Worktree**: `/Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth`  
**브랜치**: `feature/auth`

