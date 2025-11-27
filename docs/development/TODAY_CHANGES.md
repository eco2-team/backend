# 📋 오늘 작업한 변경사항 요약

## 🎯 작업 개요
**브랜치**: `feature/auth`  
**기준**: `origin/develop`  
**주요 작업**: OAuth 로그인 실패 시 프론트엔드 리다이렉트 구현 및 DB 스키마 설정

---

## 📊 전체 변경 통계

```
178 files changed, 240 insertions(+), 4733 deletions(-)
```

### 주요 변경사항
- **삭제**: `services/` 디렉토리 전체 (구 구조)
- **추가**: `domain/` 디렉토리 (새 구조)
- **수정**: ConfigMap, OAuth 콜백, DB 모델

---

## ✅ 오늘 작업한 핵심 파일 (2025-11-20)

### 1. **OAuth 로그인 실패 리다이렉트 구현**

#### `domain/auth/core/config.py`
```python
# 추가됨
frontend_url: str = "https://frontend1.dev.growbin.app"

@property
def oauth_failure_redirect_url(self) -> str:
    return f"{self.frontend_url}/login?error=oauth_failed"
```

#### `domain/auth/api/v1/endpoints/auth.py`
```python
# 각 OAuth 콜백에 try-except 추가
try:
    user = await service.login_with_provider(...)
    return LoginSuccessResponse(...)
except Exception:
    settings = get_settings()
    return RedirectResponse(url=settings.oauth_failure_redirect_url)
```

### 2. **PostgreSQL 스키마 설정**

#### `domain/auth/models/user.py`
```python
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", ...),
        {"schema": "auth"},  # ✅ 추가됨
    )
```

#### `domain/auth/models/login_audit.py`
```python
class LoginAudit(Base):
    __tablename__ = "login_audits"
    __table_args__ = ({"schema": "auth"},)  # ✅ 추가됨
    
    user_id = ForeignKey("auth.users.id", ...)  # ✅ 스키마 포함
```

#### `domain/auth/init_db.py`
```python
async def init_db():
    # ✅ 스키마 자동 생성 추가
    await conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
    await conn.run_sync(Base.metadata.create_all)
```

### 3. **Kubernetes ConfigMap**

#### `workloads/domains/auth/base/configmap.yaml`
```yaml
# 추가됨
AUTH_FRONTEND_URL: "https://frontend1.dev.growbin.app"
```

### 4. **문서 추가**
- ✅ `DEPLOYMENT_CHECKLIST.md` - 배포 체크리스트
- ✅ `KUSTOMIZE_IMAGE_CHECK.md` - Kustomize 이미지 설정 검증

---

## 🔍 변경사항 상세 분석

### A. 기존 develop 대비 삭제된 파일 (구조 변경)
```
services/
├── auth/          → domain/auth/로 이동
├── character/     → domain/character/로 이동
├── chat/          → domain/chat/로 이동
├── info/          → domain/info/로 이동
├── location/      → domain/location/로 이동
├── my/            → domain/my/로 이동
└── scan/          → domain/scan/로 이동
```

### B. 새로 추가된 파일 (추적되지 않음)
```
domain/
├── _shared/                    ✅ 공통 모듈
│   └── security/
│       ├── jwt.py
│       └── dependencies.py
└── auth/                       ✅ Auth 서비스 (feature-auth)
    ├── core/
    │   └── config.py          ✅ 프론트엔드 URL 추가
    ├── models/
    │   ├── user.py            ✅ 스키마 지정
    │   └── login_audit.py     ✅ 스키마 지정
    ├── api/v1/endpoints/
    │   └── auth.py            ✅ OAuth 실패 리다이렉트
    ├── init_db.py             ✅ 스키마 자동 생성
    └── ...
```

### C. 수정된 파일
```
workloads/domains/auth/base/configmap.yaml    ✅ 프론트엔드 URL 추가
domain/auth/core/config.py                 ✅ oauth_failure_redirect_url 추가
domain/auth/api/v1/endpoints/auth.py       ✅ OAuth 콜백 예외 처리
domain/auth/models/user.py                 ✅ schema='auth' 추가
domain/auth/models/login_audit.py          ✅ schema='auth' 추가
domain/auth/init_db.py                     ✅ CREATE SCHEMA 추가
```

---

## 🎯 오늘 구현한 기능

### 1. OAuth 로그인 실패 처리 ✅
- **목적**: OAuth 로그인 실패 시 프론트엔드로 리다이렉트
- **경로**: `https://frontend1.dev.growbin.app/login?error=oauth_failed`
- **적용 범위**: Google, Kakao, Naver 3개 프로바이더

### 2. PostgreSQL 스키마 분리 ✅
- **목적**: `auth` 스키마에 테이블 생성
- **테이블**: `auth.users`, `auth.login_audits`
- **자동 생성**: init_db.py에서 스키마 자동 생성

### 3. Dockerfile 빌드 컨텍스트 검증 ✅
- **확인**: `domain/_shared/` 공통 모듈 접근 가능
- **빌드 컨텍스트**: worktree 루트 (`.`)

### 4. Kustomize 이미지 설정 검증 ✅
- **Dev**: `docker.io/mng990/eco2-auth:dev-latest`
- **Prod**: `docker.io/mng990/eco2-auth:prod-latest`
- **테스트**: `kustomize build` 성공 확인

---

## 📦 커밋 대상 파일

### 추가해야 할 파일
```bash
git add domain/
git add DEPLOYMENT_CHECKLIST.md
git add KUSTOMIZE_IMAGE_CHECK.md
git add workloads/domains/auth/base/configmap.yaml
```

### 삭제 확인 (이미 develop에서 삭제됨)
```bash
git rm services/auth/
git rm services/character/
git rm services/chat/
# ... 기타 services/
```

---

## 🚀 다음 단계

### 1. Docker 이미지 빌드 & 푸시
```bash
cd /Users/mango/workspace/SeSACTHON/backend/worktrees/feature-auth
docker build -f domain/auth/Dockerfile -t docker.io/mng990/eco2-auth:dev-latest .
docker push docker.io/mng990/eco2-auth:dev-latest
```

### 2. Git 커밋 & 푸시
```bash
git add domain/ DEPLOYMENT_CHECKLIST.md KUSTOMIZE_IMAGE_CHECK.md
git add workloads/domains/auth/base/configmap.yaml
git commit -m "feat(auth): OAuth failure redirect and PostgreSQL schema setup

- Add OAuth login failure redirect to frontend
- Configure auth schema for PostgreSQL tables
- Add init_db.py schema auto-creation
- Update ConfigMap with frontend URL
- Verify Kustomize image configuration"

git push origin feature/auth
```

### 3. ArgoCD 동기화
- Git push 후 ArgoCD 자동 감지
- `docker.io/mng990/eco2-auth:dev-latest` 배포
- k8s-api-auth 노드에 배포 확인

### 4. 배포 후 검증
```bash
kubectl get pods -n auth -o wide
kubectl logs -n auth deployment/auth-api -f
curl https://api.growbin.app/api/v1/auth/health
```

---

## ✅ 체크리스트

- [x] OAuth 실패 리다이렉트 구현
- [x] PostgreSQL 스키마 설정
- [x] init_db.py 스키마 자동 생성
- [x] ConfigMap 프론트엔드 URL 추가
- [x] Dockerfile 빌드 컨텍스트 검증
- [x] Kustomize 이미지 설정 검증
- [ ] Docker 이미지 빌드 & 푸시
- [ ] Git 커밋 & 푸시
- [ ] ArgoCD 동기화 확인
- [ ] 배포 후 검증

---

**작성일**: 2025-11-20  
**브랜치**: feature/auth  
**작업자**: AI Assistant + User

