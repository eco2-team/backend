# FastAPI 프로젝트 템플릿 생성 스크립트

## 각 도메인별 디렉토리 구조

```
services/
├── waste-api/              # ✅ 기존 (메인 폐기물 분석)
├── auth-api/               # 🆕 인증/인가
├── userinfo-api/           # 🆕 고객 정보
├── location-api/           # 🆕 지도/위치
├── recycle-info-api/       # 🆕 재활용 정보
└── chat-llm-api/           # 🆕 LLM 채팅
```

## 표준 FastAPI 프로젝트 구조

```
{service-name}-api/
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱 진입점
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # 환경 변수 설정
│   │   └── dependencies.py  # 의존성 주입
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── endpoints/   # 라우터들
│   │       └── deps.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── domain.py        # Pydantic 모델
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── request.py       # 요청/응답 스키마
│   ├── services/
│   │   ├── __init__.py
│   │   └── business_logic.py
│   └── db/
│       ├── __init__.py
│       ├── session.py       # DB 세션
│       └── models.py        # SQLAlchemy 모델
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_api.py
```

---

## 1. Auth API (인증/인가)

### 주요 기능
- JWT 토큰 발급/검증
- 사용자 로그인/로그아웃
- OAuth2 소셜 로그인 (Kakao, Google)
- 권한 관리 (RBAC)

### 핵심 엔드포인트
```python
POST   /api/v1/auth/login           # 로그인
POST   /api/v1/auth/logout          # 로그아웃
POST   /api/v1/auth/refresh         # 토큰 갱신
POST   /api/v1/auth/register        # 회원가입
GET    /api/v1/auth/me              # 현재 사용자 정보
POST   /api/v1/auth/oauth/kakao     # Kakao 로그인
POST   /api/v1/auth/oauth/google    # Google 로그인
```

### 기술 스택
- `python-jose[cryptography]` - JWT
- `passlib[bcrypt]` - 비밀번호 해싱
- `python-multipart` - Form 데이터
- `httpx` - OAuth2 클라이언트

---

## 2. Userinfo API (고객 정보)

### 주요 기능
- 사용자 프로필 관리
- 사용자 설정
- 포인트/리워드 관리
- 활동 히스토리

### 핵심 엔드포인트
```python
GET    /api/v1/users/{user_id}           # 사용자 조회
PATCH  /api/v1/users/{user_id}           # 프로필 수정
DELETE /api/v1/users/{user_id}           # 계정 삭제
GET    /api/v1/users/{user_id}/points    # 포인트 조회
GET    /api/v1/users/{user_id}/history   # 활동 히스토리
POST   /api/v1/users/{user_id}/avatar    # 프로필 이미지 업로드
```

### 기술 스택
- `sqlalchemy` - ORM
- `alembic` - DB 마이그레이션
- `python-jose` - JWT 검증 (auth-api와 공유)

---

## 3. Location API (지도/위치)

### 주요 기능
- 근처 분리수거함 검색
- 주소 → 좌표 변환 (Geocoding)
- 좌표 → 주소 변환 (Reverse Geocoding)
- 재활용 센터 위치 정보

### 핵심 엔드포인트
```python
GET    /api/v1/locations/bins              # 근처 수거함 검색
GET    /api/v1/locations/centers           # 재활용 센터 검색
POST   /api/v1/locations/geocode           # 주소 → 좌표
POST   /api/v1/locations/reverse-geocode   # 좌표 → 주소
GET    /api/v1/locations/route             # 경로 안내
```

### 기술 스택
- `httpx` - Kakao Map API 호출
- `redis` - 위치 정보 캐싱 (GeoHash)
- `geopy` - 지리 계산

---

## 4. Recycle Info API (재활용 정보)

### 주요 기능
- 품목별 분리배출 정보 조회
- 재활용 가능 여부 판단
- 지역별 배출 규정
- FAQ 및 가이드

### 핵심 엔드포인트
```python
GET    /api/v1/recycle/items/{item_id}      # 품목 정보
GET    /api/v1/recycle/categories           # 카테고리 목록
POST   /api/v1/recycle/search               # 품목 검색
GET    /api/v1/recycle/rules/{region}       # 지역별 규정
GET    /api/v1/recycle/faq                  # FAQ
```

### 기술 스택
- `sqlalchemy` - 품목 DB
- `redis` - 품목 정보 캐싱
- `elasticsearch` - 전문 검색 (선택)

---

## 5. Chat LLM API (LLM 채팅)

### 주요 기능
- 분리수거 관련 질의응답
- 대화형 인터페이스
- 대화 히스토리 관리
- 추천 질문 제공

### 핵심 엔드포인트
```python
POST   /api/v1/chat/messages               # 메시지 전송
GET    /api/v1/chat/sessions/{session_id}  # 세션 조회
DELETE /api/v1/chat/sessions/{session_id}  # 세션 삭제
GET    /api/v1/chat/suggestions            # 추천 질문
POST   /api/v1/chat/feedback               # 피드백
```

### 기술 스택
- `openai` - GPT-4o mini API
- `redis` - 대화 히스토리 캐싱
- `langchain` (선택) - LLM 체인

---

## 공통 requirements.txt

```txt
# FastAPI Core
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0

# Database
sqlalchemy==2.0.25
asyncpg==0.29.0  # PostgreSQL async
alembic==1.13.1

# Redis
redis==5.0.1
hiredis==2.3.2

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6

# HTTP Client
httpx==0.26.0

# Monitoring
prometheus-client==0.19.0
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0

# Logging
structlog==24.1.0

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
httpx==0.26.0  # Test client
```

---

## 공통 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드
COPY ./app ./app

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 개발 시작 가이드

### 1. 새 서비스 생성

```bash
# 예: auth-api 생성
mkdir -p services/auth-api/app/{api/v1/endpoints,core,models,schemas,services,db}
cd services/auth-api

# requirements.txt 생성
cat > requirements.txt << 'EOF'
fastapi==0.109.0
uvicorn[standard]==0.27.0
# ... (위 공통 requirements.txt 참고)
EOF

# Dockerfile 생성
cat > Dockerfile << 'EOF'
FROM python:3.11-slim
# ... (위 공통 Dockerfile 참고)
EOF
```

### 2. FastAPI 앱 생성 (app/main.py)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/ready")
def readiness_check():
    return {"status": "ready"}

# API 라우터
app.include_router(api_router, prefix=settings.API_V1_STR)
```

### 3. 로컬 개발

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
export DATABASE_URL="postgresql://user:pass@localhost/db"
export REDIS_URL="redis://localhost:6379/0"

# 실행
uvicorn app.main:app --reload --port 8000
```

### 4. Docker로 실행

```bash
# 이미지 빌드
docker build -t auth-api:latest .

# 실행
docker run -p 8000:8000 \
  -e DATABASE_URL="..." \
  -e REDIS_URL="..." \
  auth-api:latest
```

### 5. Git Push → 자동 배포

```bash
# 코드 작성 완료 후
git add services/auth-api/
git commit -m "feat: Add auth-api with JWT authentication"
git push origin feature/auth-api

# PR 병합 → main 브랜치
# → GitHub Actions가 자동으로:
#   1. Docker 이미지 빌드
#   2. GHCR에 푸시
#   3. Helm values.yaml 업데이트
#   4. ArgoCD가 자동 배포
```

---

## 다음 단계

1. **각 서비스 스켈레톤 생성** ✅
2. **공통 라이브러리 추출** (auth, logging, monitoring)
3. **API Gateway 추가** (선택, Kong/Traefik)
4. **서비스 간 통신** (gRPC 또는 REST)
5. **통합 테스트** (pytest + Docker Compose)

**결론**: 표준화된 FastAPI 템플릿으로 각 도메인 API를 독립적으로 개발하고, CI/CD 파이프라인을 통해 자동 배포할 수 있습니다! 🚀

