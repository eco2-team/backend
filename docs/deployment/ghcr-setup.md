# 📦 GitHub Container Registry (GHCR) 설정

> **Docker Hub Organization 유료화 대응**  
> **대안**: GitHub Container Registry (GHCR) - 완전 무료  
> **날짜**: 2025-10-30

## 🎯 왜 GHCR인가?

### Docker Hub vs GHCR 비교

| 항목 | Docker Hub (개인) | Docker Hub (Org) | GHCR |
|------|------------------|-----------------|------|
| **비용** | 무료 (Public만) | 💰 $9/월 | ✅ 완전 무료 |
| **Private 레포** | ❌ 1개만 | ✅ 무제한 | ✅ 무제한 |
| **Public 레포** | ✅ 무제한 | ✅ 무제한 | ✅ 무제한 |
| **용량 제한** | ❌ 없음 | ❌ 없음 | ✅ 없음 |
| **GitHub 통합** | ❌ | ❌ | ✅✅ 완벽 |
| **자동 인증** | ❌ | ❌ | ✅ GITHUB_TOKEN |
| **별도 계정** | 필요 | 필요 | 불필요 |

**결론: GHCR이 압도적 ✅**

---

## ⚙️ GHCR 설정

### 1. Package 설정 (Repository 레벨)

```
Repository → Settings → Actions → General

Workflow permissions:
└─ ✅ Read and write permissions (기본값)
   └─ packages에 Push 권한 포함

별도 설정 불필요!
```

### 2. GitHub Actions 설정 (자동)

```yaml
# GitHub Actions에서 자동 인증
- name: GHCR 로그인
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}  # ⭐ 자동 제공

# 이미지 푸시
- name: Build and Push
  uses: docker/build-push-action@v5
  with:
    push: true
    tags: ghcr.io/${{ github.repository }}/auth-service:latest
```

**장점:**
- ✅ GITHUB_TOKEN 자동 생성 (모든 워크플로우)
- ✅ 권한 자동 부여
- ✅ 별도 Secret 설정 불필요

### 3. Package Visibility 설정

```
첫 Push 후:

1. GitHub → Packages 탭
2. 생성된 Package 클릭
3. Package settings
4. Change visibility → Public

또는 자동 Public 설정:
- GitHub Actions에서 빌드 시 자동 Public
- 또는 cli로: gh api ...
```

---

## 🔧 Kubernetes에서 GHCR 사용

### Public 레포지토리 (권장, 간단)

```yaml
# Helm values-prod.yaml
image:
  repository: ghcr.io/your-org/sesacthon-backend/auth-service
  tag: abc1234
  pullPolicy: Always

# imagePullSecrets 불필요!
```

**장점:**
- ✅ 설정 간단
- ✅ imagePullSecrets 불필요
- ✅ 누구나 Pull 가능

### Private 레포지토리 (보안 중요 시)

```bash
# 1. GitHub Personal Access Token 생성
# https://github.com/settings/tokens
# Scopes: read:packages

# 2. Kubernetes Secret 생성
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<github-email> \
  --namespace=auth

# 다른 Namespace에도 복제
for ns in users waste recycling locations; do
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=<github-username> \
    --docker-password=<github-token> \
    --docker-email=<github-email> \
    --namespace=$ns
done
```

```yaml
# Helm values (Private용)
image:
  repository: ghcr.io/your-org/sesacthon-backend/auth-service
  tag: abc1234

imagePullSecrets:
  - name: ghcr-secret
```

---

## 🎯 이미지 경로

### 표준 경로

```
ghcr.io/{owner}/{repository}/{package-name}:{tag}

예시:
ghcr.io/sesacthon-org/sesacthon-backend/auth-service:abc1234
ghcr.io/sesacthon-org/sesacthon-backend/auth-service:latest
ghcr.io/sesacthon-org/sesacthon-backend/waste-service:abc1234
```

### 태그 전략

```
main 브랜치 Push:
├─ abc1234 (short SHA)
├─ latest
└─ main

develop 브랜치 Push:
├─ def5678
└─ develop

Release Tag (v1.0.0):
├─ v1.0.0
├─ v1.0
├─ v1
└─ latest
```

---

## 💰 비용 비교

```
Docker Hub (Organization):
├─ 월 $9 (5명까지)
├─ Private 무제한
└─ 총: $9/월

GHCR:
├─ 월 $0 (무료!)
├─ Private 무제한
├─ Public 무제한
└─ 총: $0/월

절감: $9/월 × 12개월 = $108/년
```

---

## 🚀 첫 Push 테스트

### 로컬에서 테스트

```bash
# 1. GHCR 로그인 (Personal Access Token)
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin

# 2. 이미지 빌드
docker build -t ghcr.io/your-org/sesacthon-backend/auth-service:test \
  ./services/auth

# 3. 푸시
docker push ghcr.io/your-org/sesacthon-backend/auth-service:test

# 4. 확인
# https://github.com/orgs/your-org/packages

# 5. Pull 테스트 (Public인 경우)
docker pull ghcr.io/your-org/sesacthon-backend/auth-service:test
```

### GitHub Actions에서 자동

```bash
# 코드 수정 후 Push만 하면
git push origin main

# GitHub Actions가 자동으로:
# 1. 빌드
# 2. GHCR 푸시
# 3. Helm values 업데이트
```

---

## 📚 참고 자료

- [GHCR 공식 문서](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Actions와 GHCR](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions)

---

**작성일**: 2025-10-30  
**레지스트리**: GHCR (ghcr.io)  
**비용**: $0/월 (무료!)  
**상태**: ✅ 최종 확정

