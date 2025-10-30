# 🚀 배포 환경 구축 가이드

## ✅ 최종 확정 배포 방식

**GitHub Actions (CI) + ArgoCD (CD) + Helm + GHCR**

### 전체 흐름

```
1. 코드 수정 & Push
   ↓
2. GitHub Actions (CI)
   - Lint, Test
   - Docker Build
   - GHCR Push (ghcr.io)
   - Helm values 업데이트
   ↓
3. ArgoCD (CD)
   - Git 모니터링 (3분마다)
   - Helm Diff 계산
   - Kubernetes 자동 배포
   ↓
4. 완료 (Slack 알림)
```

## 📦 필요한 설정

### 1. GitHub Container Registry (GHCR)

```bash
# ✅ 별도 설정 불필요!
# GitHub Actions가 자동으로 GHCR 접근

# Package visibility 설정
Repository → Settings → Packages
└─ Public 권장 (누구나 Pull 가능)

# 이미지 경로:
ghcr.io/your-org/sesacthon-backend/auth-service
ghcr.io/your-org/sesacthon-backend/users-service
ghcr.io/your-org/sesacthon-backend/waste-service
ghcr.io/your-org/sesacthon-backend/recycling-service
ghcr.io/your-org/sesacthon-backend/locations-service

장점:
✅ 완전 무료 (Private도 무료!)
✅ 별도 계정 불필요
✅ GITHUB_TOKEN 자동 인증
✅ 용량 제한 없음
```

### 2. GitHub Secrets

```
Repository → Settings → Secrets

필수:
└─ SLACK_WEBHOOK_URL (선택, 알림용)

불필요:
✅ GITHUB_TOKEN: 자동 제공됨
❌ DOCKERHUB_USERNAME, TOKEN: 불필요
```

### 3. Kubernetes 클러스터

```bash
# docs/architecture/k8s-cluster-setup.md 참고
# 1 Master + 2 Worker (kubeadm)
# 구축 시간: 1.5시간
```

### 4. ArgoCD 설치

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 5. Helm Charts 작성

```bash
# charts/ 폴더에 5개 서비스
helm create charts/auth
helm create charts/users
# ...
```

### 6. ArgoCD Applications 등록

```bash
kubectl apply -f argocd/applications/all-services.yaml
```

## 🚀 첫 배포

```bash
# 1. 코드 수정
vim services/auth/app/main.py

# 2. Push
git add .
git commit -m "feat: Add OAuth login"
git push origin main

# 3. GitHub Actions 자동 실행
# - CI 통과 (Lint, Test)
# - Docker Build
# - GHCR Push (ghcr.io/your-org/sesacthon-backend/auth-service:abc1234)
# - Helm values 업데이트 (image.tag: abc1234)
# - Git Push

# 4. ArgoCD 자동 배포 (3분 이내)
# - Git 변경 감지
# - Helm Diff 계산
# - kubectl apply (Rolling Update)

# 5. 확인
argocd app list
kubectl get pods -n auth

# 6. 이미지 확인
echo "https://github.com/orgs/your-org/packages?repo_name=sesacthon-backend"
```

## 📚 상세 문서

- [GitOps 배포 가이드](docs/deployment/gitops-argocd-helm.md)
- [K8s 클러스터 구축](docs/architecture/k8s-cluster-setup.md)
- [Task Queue 설계](docs/architecture/task-queue-design.md)

---

**작성일**: 2025-10-30  
**배포 방식**: GitOps (ArgoCD + Helm)
