# GHCR 이미지 상태 점검 보고서
**작성일:** 2025-11-16  
**조직:** SeSACTHON

---

## 🔍 점검 결과

### GHCR 접근 상태
- ✅ Docker Login: 성공
- ⚠️ GitHub API (read:packages): 권한 부족
- ❓ 이미지 존재 여부: **확인 불가** (Docker daemon 없음)

### 확인된 사실

**1. CI 파이프라인:**
```yaml
api-build-push job:
  - services/ 변경 시에만 실행
  - Black, Ruff, Pytest 통과 후 실행
  - GHCR로 이미지 push
  - 태그: <sha>, latest
```

**2. 최근 성공한 CI (services/ 변경):**
```
19390242341 - "feat: Scaffold FastAPI services" (1m40s, success)
  → 이때 이미지가 빌드되었을 가능성
```

**3. 클러스터의 ImagePullBackOff:**
```
ghcr.io/sesacthon/auth-api:latest - 403 Forbidden
```

### 추론

**가능한 시나리오:**

#### A. 이미지가 없음 (80% 가능성)
- "Scaffold FastAPI services" 커밋 이후 실제 빌드 없음
- CI가 services/ 변경을 감지했지만 이미지 push 실패
- 또는 이미지가 빌드되었다가 삭제됨

#### B. 이미지 이름/조직 불일치 (15% 가능성)
- `ghcr.io/sesacthon/...` vs `ghcr.io/SeSACTHON/...` (대소문자)
- 또는 다른 조직명 사용

#### C. 이미지가 private (5% 가능성)
- 이미지는 존재하지만 visibility가 private
- Secret은 생성했지만 권한 문제

---

## 🎯 권장 조치

### 즉시 확인 (Manual)

**1. GitHub 웹 UI에서 직접 확인:**
```
https://github.com/orgs/SeSACTHON/packages
또는
https://github.com/SeSACTHON/backend/pkgs/container/<image-name>
```

**2. 실제 services/ 코드 변경 후 CI 트리거:**
```bash
# 간단한 변경으로 CI 실행
cd services/auth
echo "# Test" >> app/main.py
git add .
git commit -m "test: trigger ci image build"
git push origin develop
```

**3. 수동 이미지 빌드 (권장):**
```bash
# Docker daemon 시작 필요
# colima start  # 또는 Docker Desktop 실행

# 로그인
echo $GITHUB_TOKEN | docker login ghcr.io -u $GITHUB_USERNAME --password-stdin

# 빌드 및 푸시
cd services/auth
docker build -t ghcr.io/sesacthon/auth-api:latest .
docker push ghcr.io/sesacthon/auth-api:latest
```

---

## 📊 현재 상황 요약

**클러스터 상태:**
- ✅ 인프라: 완벽
- ✅ ArgoCD: 작동 중
- ✅ Applications: 모두 생성
- ✅ GHCR Secret: 생성됨
- ✅ imagePullSecrets: 설정됨
- 🔴 **이미지: GHCR에 없음 (추정)**

**다음 단계:**
1. GitHub UI에서 packages 확인
2. 없으면 수동 빌드 또는 CI 트리거
3. ArgoCD가 자동 배포

---

**결론:** 이미지가 GHCR에 push되지 않은 것으로 추정됩니다.

