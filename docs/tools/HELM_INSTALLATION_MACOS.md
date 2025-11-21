# macOS Helm 설치 및 PostgreSQL Chart 확인 가이드

## 1️⃣ Helm 설치 (macOS)

### 방법 1: Homebrew 사용 (추천)
```bash
# Homebrew가 없다면 먼저 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Helm 설치
brew install helm

# 설치 확인
helm version
```

### 방법 2: 스크립트 사용
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### 방법 3: 직접 다운로드
```bash
# Intel Mac
curl -LO https://get.helm.sh/helm-v3.13.0-darwin-amd64.tar.gz
tar -zxvf helm-v3.13.0-darwin-amd64.tar.gz
sudo mv darwin-amd64/helm /usr/local/bin/helm

# Apple Silicon (M1/M2)
curl -LO https://get.helm.sh/helm-v3.13.0-darwin-arm64.tar.gz
tar -zxvf helm-v3.13.0-darwin-arm64.tar.gz
sudo mv darwin-arm64/helm /usr/local/bin/helm
```

---

## 2️⃣ Bitnami PostgreSQL Chart 확인

### Bitnami Repository 추가
```bash
# Bitnami repo 추가
helm repo add bitnami https://charts.bitnami.com/bitnami

# Repository 업데이트
helm repo update

# 확인
helm repo list
```

---

## 3️⃣ PostgreSQL Chart 정보 확인

### Chart 버전 확인
```bash
# 사용 가능한 Chart 버전들
helm search repo bitnami/postgresql --versions | head -20

# 예상 출력:
# NAME                    CHART VERSION   APP VERSION     DESCRIPTION
# bitnami/postgresql      16.2.1          16.4.0          PostgreSQL...
# bitnami/postgresql      16.2.0          16.4.0          PostgreSQL...
```

### 특정 Chart 버전의 기본 이미지 확인
```bash
# Chart 16.2.1의 기본값 확인
helm show values bitnami/postgresql --version 16.2.1 | grep -A 10 "image:"

# 예상 출력:
# image:
#   registry: docker.io
#   repository: bitnami/postgresql
#   tag: 16.4.0  # ← 기본 태그 확인
#   pullPolicy: IfNotPresent
```

### Chart의 모든 기본값 확인
```bash
# 전체 values.yaml 확인
helm show values bitnami/postgresql --version 16.2.1 > postgresql-values.yaml

# 파일 열어서 확인
cat postgresql-values.yaml | less
```

---

## 4️⃣ 사용 가능한 이미지 태그 확인

### 방법 1: Helm으로 확인
```bash
# Chart의 기본 이미지 태그
helm show values bitnami/postgresql --version 16.2.1 | grep "tag:"

# 결과:
#   tag: 16.4.0
```

### 방법 2: Docker Hub API 사용
```bash
# Bitnami PostgreSQL의 사용 가능한 태그들
curl -s "https://hub.docker.com/v2/repositories/bitnami/postgresql/tags/?page_size=100" | \
    jq -r '.results[].name' | head -20

# 또는 간단히
curl -s "https://registry.hub.docker.com/v2/repositories/bitnami/postgresql/tags/?page_size=25" | \
    python3 -m json.tool | grep '"name"'
```

### 방법 3: 브라우저로 확인
```
https://hub.docker.com/r/bitnami/postgresql/tags
```

---

## 5️⃣ 우리 설정 검증

### 현재 사용 중인 설정 확인
```bash
cd /Users/mango/workspace/SeSACTHON/backend

# dev 환경 이미지 확인
cat clusters/dev/apps/27-postgresql.yaml | grep -A 5 "image:"

# 예상 출력:
# image:
#   registry: docker.io
#   repository: bitnami/postgresql
#   tag: 16.4.0
#   pullPolicy: IfNotPresent
```

### Helm Template으로 실제 생성될 리소스 확인
```bash
# Helm Chart를 다운로드
helm pull bitnami/postgresql --version 16.2.1 --untar

# Template 렌더링 (실제 생성될 YAML 확인)
helm template my-postgresql bitnami/postgresql \
    --version 16.2.1 \
    --set image.tag=16.4.0 \
    --set auth.username=sesacthon \
    --set auth.database=ecoeco \
    > postgresql-rendered.yaml

# 생성된 YAML에서 이미지 확인
cat postgresql-rendered.yaml | grep "image:"
```

---

## 6️⃣ Chart와 이미지 호환성 테스트

### 로컬에서 Chart 설치 테스트 (DRY RUN)
```bash
# Dry-run으로 테스트 (실제 배포 안 함)
helm install dev-postgresql bitnami/postgresql \
    --version 16.2.1 \
    --namespace postgres \
    --create-namespace \
    --set image.tag=16.4.0 \
    --set auth.username=sesacthon \
    --set auth.database=ecoeco \
    --set auth.existingSecret=postgresql-secret \
    --dry-run \
    --debug | less

# 에러 없이 출력되면 ✅ 설정 올바름
```

---

## 7️⃣ 빠른 검증 스크립트

### 한 번에 확인
```bash
#!/bin/bash

echo "🔍 Helm 및 PostgreSQL Chart 검증"
echo ""

# Helm 버전
echo "1️⃣  Helm 버전:"
helm version --short
echo ""

# Bitnami repo 추가/업데이트
echo "2️⃣  Bitnami Repository 업데이트:"
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null
helm repo update bitnami
echo ""

# Chart 버전 확인
echo "3️⃣  PostgreSQL Chart 버전 (최신 5개):"
helm search repo bitnami/postgresql --versions | head -6
echo ""

# Chart 16.2.1의 기본 이미지 확인
echo "4️⃣  Chart 16.2.1의 기본 이미지 태그:"
helm show values bitnami/postgresql --version 16.2.1 | grep -A 3 "image:" | head -4
echo ""

# 우리 설정 확인
echo "5️⃣  현재 우리 설정:"
cat clusters/dev/apps/27-postgresql.yaml | grep -A 4 "image:"
echo ""

echo "✅ 검증 완료!"
```

---

## 8️⃣ 실전 명령어 모음

### 필수 확인 사항
```bash
# 1. Helm 설치
brew install helm

# 2. Bitnami repo 추가
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# 3. Chart 16.2.1의 기본 이미지 확인
helm show values bitnami/postgresql --version 16.2.1 | grep "tag:"

# 4. 사용 가능한 태그 확인 (Docker Hub)
open "https://hub.docker.com/r/bitnami/postgresql/tags"

# 5. Dry-run 테스트
helm template test bitnami/postgresql \
    --version 16.2.1 \
    --set image.tag=16.4.0 \
    --set auth.username=sesacthon \
    > /tmp/test.yaml && echo "✅ Template 생성 성공"
```

---

## 9️⃣ 트러블슈팅

### "command not found: helm"
```bash
# PATH 확인
echo $PATH

# Helm 위치 확인
which helm

# PATH에 추가 (.zshrc 또는 .bash_profile)
echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### "repository already exists"
```bash
# 기존 repo 제거 후 재추가
helm repo remove bitnami
helm repo add bitnami https://charts.bitnami.com/bitnami
```

### Chart 다운로드 실패
```bash
# 네트워크 확인
curl -I https://charts.bitnami.com/bitnami/index.yaml

# 프록시 설정 (필요시)
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
```

---

## 🎯 예상 결과

### Chart 16.2.1의 기본 이미지
```yaml
image:
  registry: docker.io
  repository: bitnami/postgresql
  tag: 16.4.0  # ← Chart가 권장하는 태그
  pullPolicy: IfNotPresent
```

### 우리 설정 (일치해야 함!)
```yaml
image:
  registry: docker.io
  repository: bitnami/postgresql
  tag: 16.4.0  # ✅ 동일!
  pullPolicy: IfNotPresent
```

---

## ✅ 빠른 시작

```bash
# 1. Helm 설치
brew install helm

# 2. Repo 추가
helm repo add bitnami https://charts.bitnami.com/bitnami

# 3. 확인
helm show values bitnami/postgresql --version 16.2.1 | grep "tag:"

# 결과: tag: 16.4.0 ✅
```

이제 Helm으로 Chart를 확인할 수 있습니다! 🚀

