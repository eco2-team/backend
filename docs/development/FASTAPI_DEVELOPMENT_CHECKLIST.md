# FastAPI 개발 체크리스트

## 📋 PR 제출 전 필수 확인 사항

### 1. 코드 포맷팅 (Black) ⭐ **필수**

**문제**: CI에서 Black 포맷 체크 실패

**원인**: 
- 코드 스타일이 Black 표준과 일치하지 않음
- 자동 포맷팅 미적용

**해결 방법**:
```bash
# 전체 서비스 포맷팅
python3 -m black services/

# 특정 서비스 포맷팅
python3 -m black services/auth
python3 -m black services/chat

# 포맷 체크만 (CI와 동일)
python3 -m black --check services/
```

**Black 설정**: `pyproject.toml`
```toml
[tool.black]
line-length = 88
target-version = ['py311']
include = '\.pyi?$'
```

### 2. Lint 검증 (Ruff)

**실행**:
```bash
# 전체 서비스 lint
python3 -m ruff check services/

# 특정 서비스
python3 -m ruff check services/auth

# 자동 수정
python3 -m ruff check --fix services/auth
```

**주요 체크 항목**:
- 미사용 import
- 변수명 컨벤션
- 코드 복잡도
- Docstring

### 3. 단위 테스트 (pytest)

**실행**:
```bash
# 특정 서비스 테스트
cd services/auth
PYTHONPATH=/Users/mango/workspace/SeSACTHON/backend/services/auth pytest tests/ -v

# 전체 서비스 테스트 (루트에서)
for service in auth character chat info location my scan; do
    echo "Testing $service..."
    cd services/$service
    PYTHONPATH=$(pwd) pytest tests/
    cd ../..
done
```

**테스트 작성 필수 사항**:
```python
# tests/test_app.py (최소 요구사항)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_fastapi_app_instantiates():
    """FastAPI 앱이 정상적으로 인스턴스화되는지 확인"""
    assert app is not None

def test_health_check():
    """헬스 체크 엔드포인트 테스트"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

## 🚀 로컬 CI 시뮬레이션

**PR 전 로컬에서 CI와 동일한 검증 실행**:

```bash
#!/bin/bash
# ci-local-check.sh

set -e

SERVICE=${1:-"all"}

if [ "$SERVICE" = "all" ]; then
    SERVICES=(auth character chat info location my scan)
else
    SERVICES=($SERVICE)
fi

echo "🔧 Installing tools..."
python3 -m pip install -q black==24.4.2 ruff==0.6.9 pytest==8.3.3

for svc in "${SERVICES[@]}"; do
    echo ""
    echo "================================================"
    echo "🧪 Testing service: $svc"
    echo "================================================"
    
    # 1. Black
    echo "📝 Black format check..."
    python3 -m black --check services/$svc || {
        echo "❌ Black failed! Run: python3 -m black services/$svc"
        exit 1
    }
    
    # 2. Ruff
    echo "🔍 Ruff lint..."
    python3 -m ruff check services/$svc || {
        echo "❌ Ruff failed!"
        exit 1
    }
    
    # 3. Pytest
    echo "✅ Running tests..."
    cd services/$svc
    python3 -m pip install -q -r requirements.txt
    PYTHONPATH=$(pwd) python3 -m pytest tests/ -v || {
        echo "❌ Tests failed!"
        exit 1
    }
    cd ../..
    
    echo "✅ $svc passed all checks!"
done

echo ""
echo "🎉 All services passed local CI checks!"
```

**사용법**:
```bash
# 전체 서비스 체크
./ci-local-check.sh

# 특정 서비스만 체크
./ci-local-check.sh auth
```

## 📚 의존성 관리

### requirements.txt 표준

**기본 의존성**:
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
python-multipart==0.0.6

# Observability
prometheus-fastapi-instrumentator==6.1.0

# Testing
pytest==8.3.3
httpx==0.25.2
```

**서비스별 추가 의존성**:
```txt
# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6

# Chat (GPT-4o-mini)
openai==1.3.7

# Database
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.13.0

# Redis
redis==5.0.1
```

## 🔍 CI 파이프라인 이해

### GitHub Actions 워크플로우

**파일**: `.github/workflows/ci-quality-gate.yml`

**실행 순서**:
1. **Commit Filter**: chore/docs 타입은 스킵
2. **Detect API Changes**: services/ 변경사항 감지
3. **API Quality** (서비스별 병렬):
   - Black format check
   - Ruff lint
   - pytest
4. **API Build & Push**: 모든 테스트 통과 시 이미지 빌드

### 실패 시나리오

**Black 실패**:
```
Error: would reformat services/auth/app/main.py
Oh no! 💥 💔 💥
7 files would be reformatted
```
→ 해결: `python3 -m black services/auth`

**Ruff 실패**:
```
services/auth/app/main.py:1:1: F401 [*] `os` imported but unused
```
→ 해결: 미사용 import 제거 또는 `# noqa: F401`

**Pytest 실패**:
```
FAILED tests/test_app.py::test_health_check - AssertionError
```
→ 해결: 테스트 코드 또는 실제 코드 수정

## 🛠️ 개발 환경 설정

### 로컬 개발 서버 실행

```bash
cd services/auth
uvicorn app.main:app --reload --port 8001

# 또는 모든 서비스 동시 실행 (tmux/screen 사용)
./scripts/run-all-services.sh
```

### 환경 변수

**필수 환경 변수** (`.env` 파일):
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# Redis
REDIS_URL=redis://localhost:6379/0

# Chat 서비스 (GPT-4o-mini)
OPENAI_API_KEY=sk-...

# JWT (Auth 서비스)
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## 📝 커밋 메시지 컨벤션

**CI 스킵 조건**:
- `chore:` - 빌드/설정 변경
- `docs:` - 문서만 변경

**CI 실행 타입**:
- `feat:` - 새 기능
- `fix:` - 버그 수정
- `refactor:` - 리팩토링
- `test:` - 테스트 추가/수정

## ⚠️ 주의사항

### 1. Black 포맷팅은 자동화할 것
```bash
# pre-commit hook 설정 추천
pip install pre-commit
pre-commit install
```

### 2. 테스트 커버리지 유지
- 최소 1개 이상의 테스트 필수
- 주요 엔드포인트는 모두 테스트 작성

### 3. requirements.txt 동기화
- 새 패키지 추가 시 버전 명시
- 모든 서비스에 공통 의존성 통일

## 🎯 체크리스트 요약

PR 제출 전 확인:

- [ ] `python3 -m black services/` 실행
- [ ] `python3 -m ruff check services/` 통과
- [ ] 모든 서비스 `pytest` 통과
- [ ] `requirements.txt` 업데이트
- [ ] `.env` 환경 변수 문서화
- [ ] API 문서 업데이트 (`/docs` 확인)
- [ ] 커밋 메시지 컨벤션 준수

## 🔗 관련 문서

- [FastAPI 엔드포인트 스타일 가이드](./FASTAPI_ENDPOINT_STYLE.md)
- [CI Quality Gate 아키텍처](../architecture/GITHUB_ACTIONS_CI_QUALITY_GATE.md)
- [서비스 개발 가이드](./03-SERVICE_DEVELOPMENT.md)

---

**마지막 업데이트**: 2025-11-15  
**작성자**: CI/CD 파이프라인 개선 작업 중 발견된 이슈 기반

