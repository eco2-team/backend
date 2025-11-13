# 🚀 마이크로서비스 코딩 컨벤션

> **Eco² (이코에코) - 14-Node 마이크로서비스 아키텍처**  
> **동기식 도메인 (auth, my, location, info) 개발 가이드**

---

## 📋 목차

1. [아키텍처 개요](#아키텍처-개요)
2. [프로젝트 구조](#프로젝트-구조)
3. [네이밍 컨벤션](#네이밍-컨벤션)
4. [코드 스타일 (PEP 8)](#코드-스타일-pep-8)
5. [DTO & Validation](#dto--validation)
6. [API 응답 포맷](#api-응답-포맷)
7. [데이터베이스 모델](#데이터베이스-모델)
8. [서비스 간 통신](#서비스-간-통신)
9. [테스트 전략](#테스트-전략)

---

## 🏗️ 아키텍처 개요

### 마이크로서비스 패턴

```yaml
서비스 단위: 1 도메인 = 1 서비스 = 1 Kubernetes Pod = 1 Node
배포 방식: 독립 배포 (GitOps + ArgoCD)
DB 격리: Database per Service (스키마 분리)
통신: REST API (서비스 간 HTTP 호출)
```

### 현재 개발 대상 (동기식 서비스)

```
services/
├── auth/          ⭐ JWT 인증, OAuth2 (Blacklist)
├── my/            ⭐ 사용자 정보, 포인트, 활동
├── location/      ⭐ Kakao Map API, 위치 검색
└── info/          ⭐ 재활용 정보, FAQ, 검색

Worker 기반 (비동기 - 향후 개발):
├── scan/          ⏸️ AI 이미지 분석 (Worker-Storage, Worker-AI)
├── chat/          ⏸️ LLM 챗봇 (Worker-AI)
└── character/     ⏸️ 캐릭터 보상 (디자이너 작업 대기)
```

---

## 📁 프로젝트 구조

### 서비스별 독립 구조

```
services/
└── {service-name}/              # 예: auth, my, location, info
    ├── Dockerfile
    ├── requirements.txt
    ├── .dockerignore
    ├── README.md
    ├── app/
    │   ├── __init__.py
    │   ├── main.py              # FastAPI 앱 진입점
    │   │
    │   ├── core/                # 핵심 설정
    │   │   ├── __init__.py
    │   │   ├── config.py        # 환경변수 (Pydantic Settings)
    │   │   ├── security.py      # JWT, 비밀번호 해싱
    │   │   └── deps.py          # 공통 의존성 (DB, Redis, get_current_user)
    │   │
    │   ├── api/                 # API 계층
    │   │   ├── __init__.py
    │   │   └── v1/
    │   │       ├── __init__.py
    │   │       ├── router.py    # 전체 라우터 통합
    │   │       └── endpoints/
    │   │           ├── __init__.py
    │   │           └── {feature}.py  # 엔드포인트 구현
    │   │
    │   ├── schemas/             # Pydantic DTO (Request/Response)
    │   │   ├── __init__.py
    │   │   ├── request.py
    │   │   └── response.py
    │   │
    │   ├── models/              # SQLAlchemy 모델
    │   │   ├── __init__.py
    │   │   └── database.py
    │   │
    │   ├── services/            # 비즈니스 로직
    │   │   ├── __init__.py
    │   │   └── {feature}_service.py
    │   │
    │   ├── repositories/        # DB 접근 계층 (선택)
    │   │   ├── __init__.py
    │   │   └── {feature}_repository.py
    │   │
    │   └── utils/               # 유틸리티
    │       ├── __init__.py
    │       ├── redis_client.py
    │       ├── exceptions.py
    │       └── responses.py     # 공통 응답 포맷
    │
    └── tests/                   # 테스트
        ├── __init__.py
        ├── conftest.py
        ├── test_endpoints.py
        └── test_services.py
```

### 구조 설명

| 디렉토리 | 역할 | 비고 |
|---------|------|------|
| `core/` | 설정, 보안, 의존성 | 모든 서비스에서 공통 |
| `api/v1/endpoints/` | API 엔드포인트 | FastAPI Router |
| `schemas/` | Pydantic DTO | Request/Response 분리 |
| `models/` | SQLAlchemy 모델 | 해당 서비스 스키마만 접근 |
| `services/` | 비즈니스 로직 | 도메인 로직 구현 |
| `repositories/` | DB 접근 (선택) | 복잡한 쿼리가 많을 경우 |
| `utils/` | 유틸리티 | Redis, 예외, 응답 포맷 |

---

## 🏷️ 네이밍 컨벤션

### 1. 서비스명

```bash
# 서비스 디렉토리명: 소문자, 하이픈 없음
services/auth/
services/my/
services/location/
services/info/

# 배포명 (Kubernetes): 소문자
Deployment: auth, my, location, info
Service: auth-service, my-service, location-service, info-service
```

### 2. 파일명

| 파일 유형 | 규칙 | 예시 |
|---------|------|------|
| 메인 진입점 | `main.py` | `app/main.py` |
| 설정 | `config.py` | `core/config.py` |
| 보안 | `security.py` | `core/security.py` |
| 라우터 | `router.py` | `api/v1/router.py` |
| 엔드포인트 | `{feature}.py` | `endpoints/users.py`, `endpoints/auth.py` |
| 스키마 | `request.py`, `response.py` | `schemas/request.py` |
| 모델 | `database.py` | `models/database.py` |
| 서비스 | `{feature}_service.py` | `services/auth_service.py` |

### 3. 함수/메서드명

#### Endpoint (API 계층)

```python
# HTTP 메서드 + 명사
@router.post("/users")
async def create_user():
    pass

@router.get("/users/{user_id}")
async def get_user(user_id: int):
    pass

@router.patch("/users/{user_id}")
async def update_user(user_id: int):
    pass

@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    pass

@router.get("/users")
async def list_users():
    pass
```

#### Service (비즈니스 로직)

```python
# 동사 + 명사
async def find_user_by_id(user_id: int) -> User:
    """단건 조회"""
    pass

async def find_users_by_email(email: str) -> List[User]:
    """다건 조회"""
    pass

async def create_user(user_data: UserCreateRequest) -> User:
    """생성"""
    pass

async def update_user(user_id: int, user_data: UserUpdateRequest) -> User:
    """수정"""
    pass

async def delete_user(user_id: int) -> bool:
    """삭제"""
    pass
```

### 4. 클래스명

```python
# DTO: {기능}{Request|Response}
class UserCreateRequest(BaseModel):
    pass

class UserCreateResponse(BaseModel):
    pass

# Model: 도메인명
class User(Base):
    pass

class RefreshToken(Base):
    pass

# Service: {기능}Service (선택)
class AuthService:
    pass
```

---

## 📏 코드 스타일 (PEP 8)

### 기본 규칙

```python
# 1. 들여쓰기: 4칸 스페이스
def example():
    if True:
        pass

# 2. 최대 줄 길이: 100자 (Black 설정)
# 3. 문자열: 작은따옴표 선호 (일반), 큰따옴표 3개 (Docstring)
message = 'Hello'

"""이것은 Docstring"""

# 4. Import 순서
# - 표준 라이브러리
import os
from datetime import datetime
from typing import Optional, List

# - 서드파티 라이브러리
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# - 로컬 모듈
from app.core.config import settings
from app.core.deps import get_db, get_current_user
from app.models.database import User
from app.schemas.request import UserCreateRequest
```

### 함수 정의 (매개변수 3개 이상 → 줄바꿈)

```python
# ✅ 좋은 예
async def create_user(
    user_data: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> User:
    pass

# ✅ 좋은 예 (2개 이하)
async def get_user(user_id: int) -> Optional[User]:
    pass
```

### 비교 연산

```python
# ✅ None 비교: is/is not
if user is None:
    pass

# ✅ Boolean: 직접 사용
if is_active:
    pass

# ✅ 빈 시퀀스
if not my_list:
    pass
```

---

## 📦 DTO & Validation

### 원칙

1. **요청/응답은 항상 DTO(Pydantic Schema) 사용**
2. **DTO는 비즈니스 로직 포함 금지**
3. **Endpoint → Service 간 이동은 DTO로만**
4. **DTO ↔ Model 변환은 Service에서 수행**

### Request DTO

```python
# app/schemas/request.py
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional

class UserCreateRequest(BaseModel):
    """사용자 생성 요청"""
    
    email: EmailStr = Field(..., description="이메일", example="user@example.com")
    password: str = Field(..., min_length=8, description="비밀번호")
    username: str = Field(..., min_length=2, max_length=50, description="사용자명")
    
    @validator('password')
    def validate_password(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError('비밀번호는 최소 1개의 숫자를 포함해야 합니다')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "password123",
                "username": "홍길동"
            }
        }

class UserUpdateRequest(BaseModel):
    """사용자 수정 요청"""
    
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    bio: Optional[str] = Field(None, max_length=500)
```

### Response DTO

```python
# app/schemas/response.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class UserResponse(BaseModel):
    """사용자 응답"""
    
    id: str = Field(..., description="사용자 ID (UUID)")
    email: str = Field(..., description="이메일")
    username: str = Field(..., description="사용자명")
    is_active: bool = Field(..., description="활성화 여부")
    created_at: datetime = Field(..., description="생성일시")
    
    class Config:
        from_attributes = True  # SQLAlchemy 모델 → DTO 변환

class TokenResponse(BaseModel):
    """JWT 토큰 응답"""
    
    access_token: str = Field(..., description="Access Token")
    refresh_token: str = Field(..., description="Refresh Token")
    token_type: str = Field(default="bearer", description="토큰 타입")
    expires_in: int = Field(..., description="만료 시간 (초)")
```

---

## 📡 API 응답 포맷

### 공통 응답 래퍼 (선택)

```python
# app/utils/responses.py
from typing import Optional, Any, TypeVar, Generic
from datetime import datetime
from pydantic import BaseModel

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    """공통 API 응답 포맷"""
    
    success: bool
    message: str
    data: Optional[T] = None
    timestamp: str
    
    @classmethod
    def success_response(
        cls,
        message: str,
        data: Any = None
    ) -> 'ApiResponse':
        return cls(
            success=True,
            message=message,
            data=data,
            timestamp=datetime.utcnow().isoformat()
        )
    
    @classmethod
    def error_response(
        cls,
        message: str,
        data: Any = None
    ) -> 'ApiResponse':
        return cls(
            success=False,
            message=message,
            data=data,
            timestamp=datetime.utcnow().isoformat()
        )
```

### 사용 예시

```python
# app/api/v1/endpoints/users.py
from app.utils.responses import ApiResponse
from app.schemas.response import UserResponse

@router.post("/users", response_model=ApiResponse[UserResponse])
async def create_user(
    user_data: UserCreateRequest,
    db: Session = Depends(get_db)
):
    user = await create_user_service(db, user_data)
    
    return ApiResponse.success_response(
        message="사용자가 생성되었습니다.",
        data=UserResponse.from_orm(user)
    )
```

### 응답 예시

```json
{
  "success": true,
  "message": "사용자가 생성되었습니다.",
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "username": "홍길동",
    "is_active": true,
    "created_at": "2025-11-12T10:30:45"
  },
  "timestamp": "2025-11-12T10:30:45.123456"
}
```

---

## 🗄️ 데이터베이스 모델

### SQLAlchemy 모델

```python
# app/models/database.py
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    """사용자 모델 (auth 스키마)"""
    
    __tablename__ = 'users'
    __table_args__ = {'schema': 'auth'}  # 스키마 명시
    
    # Primary Key (UUID)
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment='사용자 ID'
    )
    
    # 기본 정보
    username = Column(String(100), unique=True, nullable=False, comment='사용자명')
    email = Column(String(255), unique=True, nullable=False, comment='이메일')
    password_hash = Column(String(255), nullable=False, comment='비밀번호 해시')
    
    # 상태
    is_active = Column(Boolean, default=True, nullable=False, comment='활성화 여부')
    is_verified = Column(Boolean, default=False, nullable=False, comment='이메일 인증 여부')
    
    # 타임스탬프 (필수)
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment='생성일시'
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment='수정일시'
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
```

### 모델 규칙

```yaml
테이블명: 소문자 복수형 (users, refresh_tokens)
스키마: __table_args__ = {'schema': '{schema_name}'}
컬럼명: snake_case (user_id, created_at)
PK: UUID 사용 (uuid.uuid4())
타임스탬프: created_at, updated_at 필수
Comment: 모든 컬럼에 한글 설명
```

---

## 🔌 서비스 간 통신

### HTTP 기반 통신

```python
# app/utils/http_client.py
import httpx
from app.core.config import settings

class ServiceClient:
    """서비스 간 HTTP 통신 클라이언트"""
    
    def __init__(self):
        self.timeout = httpx.Timeout(10.0, connect=5.0)
    
    async def call_auth_service(self, endpoint: str, **kwargs):
        """Auth 서비스 호출"""
        url = f"{settings.AUTH_SERVICE_URL}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
    
    async def call_my_service(self, endpoint: str, **kwargs):
        """My 서비스 호출"""
        url = f"{settings.MY_SERVICE_URL}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()

service_client = ServiceClient()
```

### 사용 예시

```python
# location 서비스에서 auth 서비스 호출
from app.utils.http_client import service_client

async def verify_user_token(token: str):
    """Auth 서비스를 통해 토큰 검증"""
    try:
        result = await service_client.call_auth_service(
            '/api/v1/auth/verify',
            headers={'Authorization': f'Bearer {token}'}
        )
        return result['data']
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 서비스 URL 설정

```python
# app/core/config.py
class Settings(BaseSettings):
    # 서비스 URL (Kubernetes Service DNS)
    AUTH_SERVICE_URL: str = "http://auth-service.api.svc.cluster.local:8000"
    MY_SERVICE_URL: str = "http://my-service.api.svc.cluster.local:8000"
    LOCATION_SERVICE_URL: str = "http://location-service.api.svc.cluster.local:8000"
    INFO_SERVICE_URL: str = "http://info-service.api.svc.cluster.local:8000"
```

---

## 🧪 테스트 전략

### 디렉토리 구조

```
tests/
├── conftest.py              # Pytest 설정
├── test_endpoints.py        # API 엔드포인트 테스트
├── test_services.py         # 비즈니스 로직 테스트
└── test_integration.py      # 통합 테스트
```

### 기본 테스트 설정

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.deps import get_db
from app.models.database import Base

# 테스트용 DB
SQLALCHEMY_TEST_DATABASE_URL = "postgresql://test:test@localhost/test_db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine)

@pytest.fixture(scope="function")
def db():
    """테스트용 DB 세션"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db):
    """테스트 클라이언트"""
    def override_get_db():
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

### 엔드포인트 테스트

```python
# tests/test_endpoints.py
import pytest
from fastapi import status

def test_create_user(client):
    """사용자 생성 테스트"""
    response = client.post(
        "/api/v1/users",
        json={
            "email": "test@example.com",
            "password": "password123",
            "username": "테스트유저"
        }
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data['success'] is True
    assert data['data']['email'] == "test@example.com"

def test_get_user(client):
    """사용자 조회 테스트"""
    # Given: 사용자 생성
    create_response = client.post("/api/v1/users", json={...})
    user_id = create_response.json()['data']['id']
    
    # When: 사용자 조회
    response = client.get(f"/api/v1/users/{user_id}")
    
    # Then: 성공
    assert response.status_code == status.HTTP_200_OK
```

---

## 📝 Docstring (Google Style)

```python
async def find_recycling_locations(
    latitude: float,
    longitude: float,
    radius: int = 1000,
    db: Session = Depends(get_db)
) -> List[Location]:
    """사용자 위치 기반 재활용 수거함 검색
    
    Args:
        latitude: 위도 (WGS84)
        longitude: 경도 (WGS84)
        radius: 검색 반경 (미터 단위, 기본값: 1000m)
        db: 데이터베이스 세션
    
    Returns:
        List[Location]: 반경 내 재활용 수거함 목록
    
    Raises:
        HTTPException: 좌표가 유효하지 않을 경우 (400)
    
    Example:
        >>> locations = await find_recycling_locations(37.5665, 126.9780)
        >>> len(locations)
        5
    """
    pass
```

---

## 🛠️ 코드 포매팅

### pyproject.toml

```toml
[tool.black]
line-length = 100
target-version = ['py311']
include = '\.pyi?$'
extend-exclude = '''
/(
  \.eggs
  | \.git
  | \.venv
  | build
  | dist
)/
'''

[tool.isort]
profile = "black"
line_length = 100
multi_line_output = 3
include_trailing_comma = true
```

### 실행

```bash
# 포맷팅
black app/
isort app/

# 린트 검사
flake8 app/

# 타입 체크
mypy app/
```

---

## ✅ 체크리스트

### 새 서비스 생성 시

- [ ] 디렉토리 구조 생성 (`app/`, `tests/`)
- [ ] `requirements.txt` 작성
- [ ] `Dockerfile` 작성
- [ ] `app/main.py` (FastAPI 진입점)
- [ ] `app/core/config.py` (환경변수)
- [ ] `app/core/deps.py` (의존성)
- [ ] `app/models/database.py` (SQLAlchemy 모델)
- [ ] `app/schemas/` (Request/Response DTO)
- [ ] `app/api/v1/endpoints/` (엔드포인트)
- [ ] `app/services/` (비즈니스 로직)
- [ ] `tests/` (테스트 코드)
- [ ] Health Check (`/health`, `/ready`)
- [ ] Kubernetes manifest (`k8s/overlays/{service}/`)
- [ ] ArgoCD Application 설정

---

## 🎯 참고

- [PEP 8](https://peps.python.org/pep-0008/)
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [12 Factor App](https://12factor.net/)
- [Database Schema Structure](../architecture/02-database-schema-structure.md)

---

**작성일**: 2025-11-12  
**버전**: v1.0.0  
**대상**: auth, my, location, info (동기식 서비스)


