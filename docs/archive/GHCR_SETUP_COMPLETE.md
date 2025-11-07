# GHCR Setup Complete! 🎉

## ✅ 완료된 작업

### 1. GHCR 로그인 확인
```bash
✅ Docker에 GHCR 로그인 완료
✅ GitHub Organization: SeSACTHON
```

### 2. 이미지 저장소 설정
```yaml
모든 이미지가 다음 경로로 설정됨:
  - ghcr.io/sesacthon/waste-api
  - ghcr.io/sesacthon/auth-api
  - ghcr.io/sesacthon/userinfo-api
  - ghcr.io/sesacthon/location-api
  - ghcr.io/sesacthon/recycle-info-api
  - ghcr.io/sesacthon/chat-llm-api
  - ghcr.io/sesacthon/ecoeco-backend (Workers)
```

### 3. 업데이트된 파일
```
✅ charts/ecoeco-backend/values-13nodes.yaml
   - 모든 이미지 경로 업데이트

✅ .github/workflows/api-deploy.yml
   - IMAGE_PREFIX: sesacthon

✅ scripts/push-to-ghcr.sh
   - 새 빌드 & 푸시 스크립트 생성
```

---

## 🚀 다음 단계

### Option 1: 수동 빌드 & 푸시 (테스트용)
```bash
# 한 번에 모든 이미지 빌드 & 푸시
cd /Users/mango/workspace/SeSACTHON/backend
./scripts/push-to-ghcr.sh

# 또는 특정 태그로
./scripts/push-to-ghcr.sh v1.0.0

# 개별 이미지 빌드 (예: auth-api)
cd services/auth-api
docker build -t ghcr.io/sesacthon/auth-api:latest .
docker push ghcr.io/sesacthon/auth-api:latest
```

### Option 2: GitHub Actions 자동 빌드 (추천)
```bash
# 코드 커밋 & 푸시만 하면 자동 빌드!
git add .
git commit -m "feat: Setup GHCR"
git push origin main

# GitHub Actions가 자동으로:
# 1. 변경된 서비스 감지
# 2. Docker 이미지 빌드
# 3. GHCR에 푸시
# 4. Helm values.yaml 업데이트
```

---

## 🔓 이미지를 Public으로 설정

빌드 후 GitHub 웹에서:

1. **https://github.com/orgs/SeSACTHON/packages** 접속

2. 각 패키지 클릭 (예: waste-api)

3. **Package settings** 클릭

4. **Change package visibility** → **Public** 선택

5. 리포지토리 이름(`backend`) 입력하여 확인

⚠️ **Public 설정 후 누구나 이미지를 Pull 할 수 있습니다!**

---

## 📝 GitHub Actions Secrets 설정 (선택)

자동 빌드는 `GITHUB_TOKEN`을 사용하므로 추가 설정은 **선택사항**입니다.

만약 별도 토큰을 사용하려면:

1. **리포지토리** → **Settings** → **Secrets and variables** → **Actions**

2. **New repository secret** 클릭

3. Secret 추가:
   ```
   Name: GHCR_TOKEN
   Value: ghp_your_token_here
   ```

---

## ✅ 확인 사항

```bash
# 1. GHCR 로그인 확인
cat ~/.docker/config.json | grep ghcr.io

# 2. 이미지 빌드 테스트 (auth-api 예시)
cd services/auth-api
docker build -t ghcr.io/sesacthon/auth-api:test .

# 3. 이미지 푸시 테스트
docker push ghcr.io/sesacthon/auth-api:test

# 4. 푸시된 이미지 확인
# https://github.com/orgs/SeSACTHON/packages
```

---

## 🎯 추천 워크플로우

### 개발 → 배포
```bash
# 1. 코드 수정
vim services/waste-api/app/main.py

# 2. Git 커밋
git add services/waste-api
git commit -m "feat: Update waste-api endpoint"
git push origin main

# 3. GitHub Actions 자동 실행 (약 5-10분)
# → Docker Build
# → GHCR Push (ghcr.io/sesacthon/waste-api:abc123)
# → values.yaml 업데이트

# 4. ArgoCD 자동 배포 (3분 내)
# → Helm Chart Sync
# → k8s-api-waste 노드에 배포

# 5. 확인
kubectl get pods -n api -o wide | grep waste
```

---

**🎉 GHCR 세팅 완료!**

이제 준비가 끝났습니다:
- ✅ GHCR 로그인
- ✅ 이미지 경로 설정
- ✅ 빌드 스크립트
- ✅ GitHub Actions 설정

다음 작업을 선택하세요:
1. `./scripts/push-to-ghcr.sh` 실행 (수동 빌드)
2. Git Push (자동 빌드 트리거)
3. 이미지 Public 설정

