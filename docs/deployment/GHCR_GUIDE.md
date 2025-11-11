# GHCR (GitHub Container Registry) 사용 가이드

GitHub Packages를 통한 컨테이너 이미지 레지스트리 설정 및 확인 방법

## 📋 목차

1. [GHCR이란?](#ghcr이란)
2. [사전 준비](#사전-준비)
3. [GitHub Token 생성](#github-token-생성)
4. [GHCR 동작 확인](#ghcr-동작-확인)
5. [수동 이미지 푸시](#수동-이미지-푸시)
6. [GitHub Actions 통합](#github-actions-통합)
7. [문제 해결](#문제-해결)

---

## 🐳 GHCR이란?

**GitHub Container Registry (GHCR)**는 GitHub에서 제공하는 컨테이너 이미지 레지스트리입니다.

### 장점
- ✅ **무료**: Public 저장소는 무료 (Private도 일정량 무료)
- ✅ **통합**: GitHub Actions와 완벽한 통합
- ✅ **보안**: GitHub 계정 기반 인증
- ✅ **속도**: GitHub CDN을 통한 빠른 다운로드
- ✅ **버전 관리**: Git과 동일한 버전 태깅

### vs Docker Hub
| 기능 | GHCR | Docker Hub |
|------|------|------------|
| 무료 Public 저장소 | ✅ 무제한 | ✅ 무제한 |
| 무료 Private 저장소 | ✅ 제한적 | ❌ 1개 |
| GitHub Actions 통합 | ✅ 완벽 | ⚠️ 별도 설정 |
| 이미지 크기 제한 | 없음 | 없음 |

---

## 🔧 사전 준비

### 1. Docker 설치 확인

```bash
docker --version
# Docker version 24.0.0 이상
```

### 2. jq 설치 (JSON 파싱용)

```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# 확인
jq --version
```

---

## 🔑 GitHub Token 생성

### Step 1: GitHub Settings 접속

1. GitHub 로그인
2. 우측 상단 프로필 클릭
3. **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
4. **Generate new token (classic)** 클릭

### Step 2: Token 설정

**Note**: `GHCR Access for SeSACTHON Backend`

**Expiration**: `90 days` (또는 원하는 기간)

**Scopes** (필수):
- ✅ `write:packages` - 패키지 업로드
- ✅ `read:packages` - 패키지 다운로드
- ✅ `delete:packages` - 패키지 삭제 (선택사항)

### Step 3: Token 복사 및 저장

```bash
# Token 복사 (한 번만 표시됨!)
# ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 환경변수 설정 (임시)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export GITHUB_USERNAME=your-github-username

# 영구 설정 (~/.zshrc 또는 ~/.bashrc)
echo 'export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' >> ~/.zshrc
echo 'export GITHUB_USERNAME=your-github-username' >> ~/.zshrc
source ~/.zshrc
```

⚠️ **보안 주의**: Token은 비밀번호와 동일하게 취급하세요!

---

## ✅ GHCR 동작 확인

### 자동 테스트 스크립트 실행

```bash
cd /Users/mango/workspace/SeSACTHON/backend
./scripts/testing/test-ghcr.sh
```

### 테스트 항목

스크립트는 다음을 자동으로 확인합니다:

1. ✅ **환경변수 확인**
   - `GITHUB_TOKEN`
   - `GITHUB_USERNAME`
   - `GITHUB_ORG` (기본값: sesacthon)

2. ✅ **GHCR 로그인 테스트**
   ```bash
   echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
   ```

3. ✅ **이미지 빌드 & 푸시 테스트**
   - 임시 테스트 이미지 생성
   - GHCR에 푸시
   - 푸시 성공 확인

4. ✅ **이미지 Pull 테스트**
   - GHCR에서 이미지 다운로드
   - 컨테이너 실행 테스트

5. ✅ **GitHub API 테스트**
   - 패키지 목록 조회
   - 패키지 메타데이터 확인

### 예상 출력

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🐳 GHCR (GitHub Container Registry) 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ 환경 변수 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ GITHUB_TOKEN: ghp_xxxxxx...
✅ GITHUB_USERNAME: your-username
✅ GITHUB_ORG: sesacthon

2️⃣ GHCR 로그인 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 GHCR 로그인 중...
✅ GHCR 로그인 성공!

3️⃣ 테스트 이미지 빌드 & 푸시
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 테스트 이미지: ghcr.io/sesacthon/test-api:test-1699999999
🔨 이미지 빌드 중...
✅ 이미지 빌드 성공
📤 GHCR에 푸시 중...
✅ GHCR 푸시 성공!

4️⃣ 이미지 Pull 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📥 GHCR에서 이미지 다운로드 중...
✅ 이미지 Pull 성공!
🏃 컨테이너 실행 테스트...
✅ 컨테이너 실행 성공!

5️⃣ GitHub Packages 목록 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 Organization의 패키지 목록:
✅ 패키지 수: 1

📦 패키지 목록:
   - test-api (visibility: public)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ GHCR 동작 확인 완료!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📤 수동 이미지 푸시

### 1. 이미지 빌드

```bash
# Auth API 예제
cd services/auth-api
docker build -t ghcr.io/sesacthon/auth-api:latest .
```

### 2. GHCR 로그인

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
```

### 3. 이미지 푸시

```bash
docker push ghcr.io/sesacthon/auth-api:latest
```

### 4. 푸시 확인

```bash
# GitHub 웹에서 확인
open https://github.com/orgs/sesacthon/packages

# 또는 API로 확인
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/orgs/sesacthon/packages?package_type=container
```

---

## 🤖 GitHub Actions 통합

### 자동 빌드 확인

1. **코드 푸시**
   ```bash
   git add services/auth-api/
   git commit -m "feat: Update auth API"
   git push origin main
   ```

2. **Actions 확인**
   - GitHub 저장소 → **Actions** 탭
   - `Build and Push API Images` workflow 확인
   - 각 API별 빌드 상태 확인

3. **이미지 확인**
   ```bash
   # 빌드된 이미지 확인
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
        https://api.github.com/orgs/sesacthon/packages/container/auth-api/versions \
        | jq '.[0].metadata.container.tags'
   ```

### Workflow 수동 실행

1. GitHub → **Actions** → **Build and Push API Images**
2. **Run workflow** 클릭
3. API 선택:
   - `all` - 모든 API 빌드
   - `auth` - Auth API만
   - `my` - My API만
   - 등...

---

## 🔍 패키지 확인 방법

### 1. GitHub 웹 UI

```bash
# Organization 패키지
https://github.com/orgs/sesacthon/packages

# 개별 패키지
https://github.com/sesacthon/backend/pkgs/container/auth-api
```

### 2. GitHub CLI

```bash
# GitHub CLI 설치
brew install gh

# 로그인
gh auth login

# 패키지 목록
gh api /orgs/sesacthon/packages?package_type=container
```

### 3. Docker CLI

```bash
# 이미지 Pull 테스트
docker pull ghcr.io/sesacthon/auth-api:latest

# 이미지 정보 확인
docker inspect ghcr.io/sesacthon/auth-api:latest
```

### 4. 쿠버네티스에서 확인

```bash
# Pod의 이미지 확인
kubectl get pods -n api -o jsonpath='{.items[*].spec.containers[*].image}'

# ImagePullSecrets 확인
kubectl get secret ghcr-secret -n api -o yaml
```

---

## 🐛 문제 해결

### 1. 로그인 실패

**증상**:
```
Error response from daemon: Get "https://ghcr.io/v2/": unauthorized
```

**해결**:
```bash
# Token 권한 확인
# write:packages, read:packages가 있는지 확인

# Token 재생성 후 다시 로그인
export GITHUB_TOKEN=new_token
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
```

### 2. 푸시 실패 (403 Forbidden)

**증상**:
```
denied: permission_denied
```

**원인 & 해결**:

1. **Organization 권한 부족**
   - GitHub → Organization Settings → Packages
   - Package creation 권한 확인

2. **Repository 연결 안됨**
   - Package Settings → Connect repository
   - backend 저장소 연결

3. **Token 만료**
   ```bash
   # 새 Token 생성 및 설정
   export GITHUB_TOKEN=new_token
   ```

### 3. 이미지 Pull 실패

**증상**:
```
Error response from daemon: pull access denied
```

**해결**:

1. **Public 설정 확인**
   ```bash
   # Package를 Public으로 변경
   # GitHub → Package → Settings → Change visibility
   ```

2. **Private인 경우 Secret 생성**
   ```bash
   # Kubernetes Secret 생성
   kubectl create secret docker-registry ghcr-secret \
     --docker-server=ghcr.io \
     --docker-username=$GITHUB_USERNAME \
     --docker-password=$GITHUB_TOKEN \
     --docker-email=$GITHUB_EMAIL \
     -n api
   ```

3. **Deployment에 Secret 추가**
   ```yaml
   spec:
     imagePullSecrets:
       - name: ghcr-secret
   ```

### 4. GitHub Actions 빌드 실패

**증상**:
```
Error: buildx failed with: error: failed to solve
```

**해결**:

1. **Dockerfile 경로 확인**
   ```yaml
   # .github/workflows/api-build.yml
   context: ./services/auth-api  # 경로 확인
   ```

2. **GITHUB_TOKEN 권한**
   ```yaml
   permissions:
     contents: read
     packages: write  # 필수!
   ```

3. **Actions 로그 확인**
   - GitHub → Actions → 실패한 workflow 클릭
   - 각 step의 상세 로그 확인

### 5. Organization 패키지 접근 불가

**증상**:
```
API rate limit exceeded
```

**해결**:
```bash
# Personal account 패키지로 조회
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/user/packages?package_type=container
```

---

## 📚 참고 자료

### 공식 문서
- [GitHub Packages 문서](https://docs.github.com/packages)
- [GHCR 소개](https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Actions + GHCR](https://docs.github.com/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions)

### 유용한 명령어

```bash
# 모든 로컬 이미지 삭제
docker rmi $(docker images -q ghcr.io/sesacthon/* --format "{{.ID}}")

# 특정 패키지의 모든 버전 조회
gh api /orgs/sesacthon/packages/container/auth-api/versions

# 패키지 삭제 (주의!)
gh api -X DELETE /orgs/sesacthon/packages/container/test-api

# Docker 로그아웃
docker logout ghcr.io
```

---

## 🎯 다음 단계

1. ✅ **GHCR 테스트 완료**
   ```bash
   ./scripts/testing/test-ghcr.sh
   ```

2. 🔄 **GitHub Actions 확인**
   - 코드 푸시 후 자동 빌드 확인
   - 이미지 태그 확인

3. 🚀 **ArgoCD 연동**
   - ArgoCD에서 GHCR 이미지 자동 배포
   - Image updater 설정 (선택사항)

4. 📊 **모니터링**
   - Package usage 확인
   - Image pull 통계 확인

