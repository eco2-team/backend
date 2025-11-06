# GitHub Container Registry (GHCR) 세팅 가이드

## 🎯 GHCR이란?

GitHub Container Registry는 GitHub에서 제공하는 컨테이너 이미지 저장소입니다.
- **무료**: Public 리포지토리는 무료
- **통합**: GitHub와 완벽하게 통합
- **보안**: GitHub 권한 시스템 활용
- **속도**: 빠른 이미지 Pull/Push

---

## 📋 사전 준비

### 필요한 것
```bash
1. GitHub 계정
2. GitHub 리포지토리 (SeSACTHON)
3. Docker 설치
4. GitHub CLI (gh) 또는 Personal Access Token
```

---

## 🔑 1단계: Personal Access Token 생성

### GitHub 웹에서 생성

1. **GitHub 로그인** → 우측 상단 프로필 클릭

2. **Settings** 클릭

3. 좌측 메뉴에서 **Developer settings** 클릭

4. **Personal access tokens** → **Tokens (classic)** 클릭

5. **Generate new token** → **Generate new token (classic)** 클릭

6. **Token 설정**:
   ```yaml
   Note: GHCR Token for SeSACTHON
   Expiration: 90 days (또는 No expiration)
   
   Scopes (권한 선택):
     ✅ write:packages  # 이미지 업로드
     ✅ read:packages   # 이미지 다운로드
     ✅ delete:packages # 이미지 삭제
     ✅ repo            # 리포지토리 접근
   ```

7. **Generate token** 클릭

8. **토큰 복사** (⚠️ 한 번만 표시됩니다!)
   ```
   ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

---

## 🔐 2단계: 로컬에서 GHCR 로그인

### 방법 1: Docker CLI로 로그인
```bash
# 환경 변수에 토큰 저장
export GHCR_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# GHCR 로그인
echo $GHCR_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# 성공 메시지:
# Login Succeeded
```

### 방법 2: GitHub CLI로 로그인 (추천)
```bash
# GitHub CLI 설치 (Mac)
brew install gh

# GitHub 인증
gh auth login

# Docker 자동 로그인
gh auth token | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### 로그인 확인
```bash
# Docker 설정 확인
cat ~/.docker/config.json

# 출력:
{
  "auths": {
    "ghcr.io": {
      "auth": "base64_encoded_credentials"
    }
  }
}
```

---

## 🏷️ 3단계: 이미지 빌드 & 태깅

### 이미지 네이밍 규칙
```
ghcr.io/OWNER/IMAGE_NAME:TAG

예시:
ghcr.io/your-org/waste-api:latest
ghcr.io/your-org/waste-api:v1.0.0
ghcr.io/your-org/auth-api:main-abc123
```

### 각 API별 이미지 빌드
```bash
# Waste API
cd services/waste-api
docker build -t ghcr.io/your-org/waste-api:latest .

# Auth API
cd ../auth-api
docker build -t ghcr.io/your-org/auth-api:latest .

# Userinfo API
cd ../userinfo-api
docker build -t ghcr.io/your-org/userinfo-api:latest .

# Location API
cd ../location-api
docker build -t ghcr.io/your-org/location-api:latest .

# Recycle Info API
cd ../recycle-info-api
docker build -t ghcr.io/your-org/recycle-info-api:latest .

# Chat LLM API
cd ../chat-llm-api
docker build -t ghcr.io/your-org/chat-llm-api:latest .
```

### 태그 전략
```bash
# Git SHA 태그 (추천)
docker build -t ghcr.io/your-org/waste-api:$(git rev-parse --short HEAD) .

# Semantic Version 태그
docker build -t ghcr.io/your-org/waste-api:v1.2.3 .

# 멀티 태그
docker build -t ghcr.io/your-org/waste-api:latest \
             -t ghcr.io/your-org/waste-api:v1.2.3 \
             -t ghcr.io/your-org/waste-api:$(git rev-parse --short HEAD) .
```

---

## 📤 4단계: 이미지 Push

### 단일 이미지 Push
```bash
docker push ghcr.io/your-org/waste-api:latest
```

### 모든 태그 Push
```bash
docker push --all-tags ghcr.io/your-org/waste-api
```

### 전체 API 이미지 Push 스크립트
```bash
#!/bin/bash
# scripts/push-all-images.sh

OWNER="your-org"
TAG=$(git rev-parse --short HEAD)

APIs=("waste-api" "auth-api" "userinfo-api" "location-api" "recycle-info-api" "chat-llm-api")

for api in "${APIs[@]}"; do
  echo "Building and pushing $api..."
  
  cd services/$api
  
  docker build -t ghcr.io/$OWNER/$api:$TAG \
               -t ghcr.io/$OWNER/$api:latest .
  
  docker push ghcr.io/$OWNER/$api:$TAG
  docker push ghcr.io/$OWNER/$api:latest
  
  cd ../..
done

echo "All images pushed successfully!"
```

---

## 🔓 5단계: 이미지 Public으로 설정

### GitHub 웹에서 설정

1. **GitHub 리포지토리** 페이지로 이동

2. 우측 사이드바에서 **Packages** 클릭

3. 이미지 선택 (예: waste-api)

4. **Package settings** 클릭

5. **Change visibility** → **Public** 선택

6. 리포지토리 이름 입력하여 확인

### 모든 이미지를 Public으로 설정
```bash
# GitHub CLI 사용
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  /user/packages/container/waste-api/versions/VERSION_ID \
  -f visibility='public'
```

---

## 🤖 6단계: GitHub Actions 세팅

### GitHub Secrets 설정

1. **리포지토리** → **Settings** → **Secrets and variables** → **Actions**

2. **New repository secret** 클릭

3. **Secret 추가**:
   ```yaml
   Name: GHCR_TOKEN
   Value: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Workflow 파일 확인
```yaml
# .github/workflows/api-deploy.yml (이미 생성됨)

- name: Log in to GitHub Container Registry
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}  # 또는 GHCR_TOKEN
```

### GITHUB_TOKEN vs GHCR_TOKEN

**GITHUB_TOKEN (추천)**:
```yaml
✅ 자동 생성 (설정 불필요)
✅ 해당 Workflow에만 권한
✅ 자동 만료
✅ 보안 강화

사용:
password: ${{ secrets.GITHUB_TOKEN }}
```

**GHCR_TOKEN (Personal Access Token)**:
```yaml
✅ 모든 리포지토리 접근
✅ 외부에서도 사용 가능
⚠️ 수동 관리 필요
⚠️ 만료 관리 필요

사용:
password: ${{ secrets.GHCR_TOKEN }}
```

---

## 📥 7단계: Kubernetes에서 이미지 Pull

### Public 이미지 (인증 불필요)
```yaml
# Helm values-13nodes.yaml
api:
  waste:
    image:
      repository: ghcr.io/your-org/waste-api
      tag: latest
```

### Private 이미지 (ImagePullSecret 필요)
```bash
# Kubernetes Secret 생성
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=GHCR_TOKEN \
  --docker-email=YOUR_EMAIL \
  --namespace=api

# Helm values에 추가
api:
  common:
    imagePullSecrets:
      - name: ghcr-secret
```

---

## ✅ 8단계: 테스트

### 이미지 Pull 테스트
```bash
# Public 이미지 Pull
docker pull ghcr.io/your-org/waste-api:latest

# 이미지 확인
docker images | grep ghcr.io

# 실행 테스트
docker run -p 8000:8000 ghcr.io/your-org/waste-api:latest
curl http://localhost:8000/health
```

### Kubernetes에서 테스트
```bash
# Master 노드에서
kubectl run test-waste --image=ghcr.io/your-org/waste-api:latest -n api

# Pod 확인
kubectl get pods -n api | grep test-waste

# 로그 확인
kubectl logs test-waste -n api

# 정리
kubectl delete pod test-waste -n api
```

---

## 🔄 전체 워크플로우

### 개발 → 배포 프로세스
```bash
# 1. 코드 수정
cd services/waste-api
vim app/main.py

# 2. 로컬 테스트
docker build -t waste-api:test .
docker run -p 8000:8000 waste-api:test

# 3. Git Push
git add .
git commit -m "feat: Update waste-api"
git push origin main

# 4. GitHub Actions 자동 실행
# → Docker Build
# → GHCR Push (ghcr.io/your-org/waste-api:abc123)
# → Helm values.yaml 업데이트
# → Git Commit & Push

# 5. ArgoCD 자동 감지 (3분 내)
# → Helm Chart Sync
# → Kubernetes 배포
# → k8s-api-waste 노드에 배포

# 6. 배포 확인
kubectl get pods -n api -o wide | grep waste
```

---

## 🛠️ 트러블슈팅

### 1. 로그인 실패
```bash
# 에러: unauthorized: authentication required
# 해결: 토큰 권한 확인

# write:packages 권한이 있는지 확인
# 토큰 재생성 후 다시 로그인
echo $NEW_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
```

### 2. Push 실패
```bash
# 에러: denied: permission_denied
# 해결: 리포지토리 권한 확인

# Organization의 경우 Package 권한 설정
# Settings → Member privileges → Package creation 확인
```

### 3. Pull 실패 (Kubernetes)
```bash
# 에러: ErrImagePull
# 해결: ImagePullSecret 확인

kubectl get pods -n api
kubectl describe pod <pod-name> -n api

# ImagePullSecret 재생성
kubectl delete secret ghcr-secret -n api
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=USERNAME \
  --docker-password=TOKEN \
  --namespace=api
```

### 4. 이미지 태그 오류
```bash
# 에러: manifest unknown
# 해결: 태그 확인

# GHCR 웹에서 확인
# https://github.com/your-org?tab=packages

# 또는 API로 확인
gh api /user/packages/container/waste-api/versions
```

---

## 📊 GHCR 사용 현황 확인

### 웹에서 확인
```
1. GitHub 프로필 → Packages
2. 각 패키지 클릭
3. Versions 탭에서 모든 태그 확인
4. Usage 탭에서 다운로드 통계 확인
```

### CLI로 확인
```bash
# 모든 패키지 목록
gh api /user/packages?package_type=container

# 특정 패키지 버전
gh api /user/packages/container/waste-api/versions

# 다운로드 통계
gh api /user/packages/container/waste-api/versions/VERSION_ID/stats
```

---

## 🎯 Best Practices

### 1. 태그 전략
```bash
✅ SHA 태그: 배포 추적 용이
   ghcr.io/your-org/waste-api:abc123

✅ Semantic Version: 릴리스 관리
   ghcr.io/your-org/waste-api:v1.2.3

✅ latest: 개발/테스트 용도
   ghcr.io/your-org/waste-api:latest

❌ production: 사용하지 말 것
   (latest처럼 모호함)
```

### 2. 이미지 크기 최적화
```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY ./app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

### 3. 보안
```bash
✅ Public 이미지: 민감 정보 제거
✅ Private 이미지: 중요 서비스용
✅ Token 관리: 주기적 재생성
✅ Secrets: GitHub Secrets 사용
```

---

**🎉 GHCR 세팅 완료!**

이제 Git Push만 하면 자동으로:
1. Docker 이미지 빌드
2. GHCR에 업로드
3. Kubernetes에 배포

모든 것이 자동화됩니다! 🚀

