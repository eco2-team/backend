# 📊 FastAPI 프로젝트 구조 비교 분석

> **Medium 글 vs 우리 프로젝트**  
> **참고**: [Build Fast, Scale Smart: The Ultimate FastAPI Project Structure Guide](https://medium.com/@vignarajj/build-fast-scale-smart-the-ultimate-fastapi-project-structure-guide-dc41c35f64cd)  
> **작성일**: 2025-11-12

---

## 📋 목차

1. [개요](#개요)
2. [구조 비교](#구조-비교)
3. [주요 차이점](#주요-차이점)
4. [장단점 분석](#장단점-분석)
5. [최종 권장사항](#최종-권장사항)

---

## 🎯 개요

### Medium 글 (Vignaraj의 구조)
```yaml
대상: 모놀리식 FastAPI 애플리케이션
규모: 단일 서비스, 다중 도메인
특징: 전통적인 레이어드 아키텍처
```

### 우리 프로젝트 (Eco²)
```yaml
대상: 마이크로서비스 아키텍처
규모: 다중 서비스 (auth, my, location, info)
특징: Domain-Driven Design, 서비스 독립성
```

---

## 🏗️ 구조 비교

### Medium 글의 구조 (모놀리식)

```
fastapi_project/
├── app/
│   ├── __init__.py
│   ├── main.py                    # 메인 진입점
│   │
│   ├── api/                       # API 계층
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py          # 메인 라우터
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── users.py       # 사용자 엔드포인트
│   │           ├── items.py       # 아이템 엔드포인트
│   │           └── auth.py        # 인증 엔드포인트
│   │
│   ├── core/                      # 핵심 설정
│   │   ├── __init__.py
│   │   ├── config.py              # 환경변수 설정
│   │   ├── security.py            # 보안 (JWT 등)
│   │   └── dependencies.py        # 의존성 주입
│   │
│   ├── db/                        # 데이터베이스
│   │   ├── __init__.py
│   │   ├── base.py                # Base 클래스
│   │   ├── session.py             # DB 세션
│   │   └── init_db.py             # DB 초기화
│   │
│   ├── models/                    # SQLAlchemy 모델
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── item.py
│   │   └── ...
│   │
│   ├── schemas/                   # Pydantic 스키마
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── item.py
│   │   └── token.py
│   │
│   ├── crud/                      # CRUD 연산
│   │   ├── __init__.py
│   │   ├── crud_user.py
│   │   └── crud_item.py
│   │
│   ├── services/                  # 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   └── auth_service.py
│   │
│   └── utils/                     # 유틸리티
│       ├── __init__.py
│       └── email.py
│
├── tests/                         # 테스트
│   ├── __init__.py
│   ├── conftest.py
│   └── test_api/
│       ├── test_users.py
│       └── test_auth.py
│
├── alembic/                       # DB 마이그레이션
│   ├── versions/
│   └── env.py
│
├── .env                           # 환경변수
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md
```

### 우리 프로젝트 구조 (마이크로서비스)

```
services/
├── auth/                          # 인증 서비스
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── deps.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── auth.py
│   │   │           └── oauth.py
│   │   ├── schemas/
│   │   │   ├── request.py
│   │   │   └── response.py
│   │   ├── models/
│   │   │   └── database.py
│   │   ├── services/
│   │   │   └── auth_service.py
│   │   └── utils/
│   │       ├── redis_client.py
│   │       └── exceptions.py
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
│
├── my/                            # 사용자 정보 서비스
│   └── (동일한 구조)
│
├── location/                      # 위치 서비스
│   └── (동일한 구조)
│
└── info/                          # 재활용 정보 서비스
    └── (동일한 구조)
```

---

## 🔍 주요 차이점

### 1. **아키텍처 패턴**

| 측면 | Medium (Vignaraj) | 우리 프로젝트 |
|------|------------------|--------------|
| **패턴** | 모놀리식 (Monolithic) | 마이크로서비스 (Microservices) |
| **서비스 수** | 1개 | 4개 (auth, my, location, info) |
| **배포 단위** | 전체 애플리케이션 | 서비스별 독립 배포 |
| **확장** | 수직 확장 | 수평 확장 (서비스별) |
| **DB** | 단일 DB | Schema per Service |

### 2. **디렉토리 구조**

#### 공통점 ✅
```python
# 두 구조 모두 동일
app/
├── main.py              # FastAPI 진입점
├── core/                # 설정, 보안
├── api/v1/              # API 버전 관리
├── models/              # SQLAlchemy 모델
├── schemas/             # Pydantic 스키마
├── services/            # 비즈니스 로직
└── utils/               # 유틸리티
```

#### 차이점 ❌

| 디렉토리 | Medium | 우리 프로젝트 | 설명 |
|---------|--------|--------------|------|
| **crud/** | ✅ 있음 | ❌ 없음 | 우리는 `services/`에 포함 |
| **db/** | ✅ 별도 디렉토리 | 📁 `core/deps.py`에 포함 | DB 세션 관리 위치 |
| **repositories/** | ❌ 없음 | ✅ 있음 (선택) | 복잡한 쿼리 분리 시 |
| **alembic/** | 📁 루트 레벨 | 📁 각 서비스 내부 | 마이그레이션 위치 |

### 3. **서비스 계층 구조**

#### Medium 글의 계층
```
Controller (API Endpoints)
    ↓
Service Layer (비즈니스 로직)
    ↓
CRUD Layer (DB 접근)
    ↓
Models (SQLAlchemy)
```

#### 우리 프로젝트의 계층 (옵션)
```
Option A (Simple):
API Endpoints
    ↓
Service Layer (비즈니스 로직 + DB 접근)
    ↓
Models

Option B (Complex):
API Endpoints
    ↓
Service Layer (비즈니스 로직)
    ↓
Repository Layer (DB 접근)
    ↓
Models
```

### 4. **schemas/ 구조**

#### Medium 글
```python
# app/schemas/user.py
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class User(UserBase):
    id: int
    class Config:
        from_attributes = True
```

#### 우리 프로젝트
```python
# app/schemas/request.py
class UserCreateRequest(BaseModel):
    email: str
    password: str

class UserUpdateRequest(BaseModel):
    username: Optional[str]

# app/schemas/response.py
class UserResponse(BaseModel):
    id: str
    email: str
    username: str
```

**차이점**:
- Medium: 상속 기반 (`UserBase`, `UserCreate`, `User`)
- 우리: Request/Response 명시적 분리

### 5. **CRUD vs Service**

#### Medium 글 (CRUD 패턴)
```python
# app/crud/crud_user.py
class CRUDUser:
    def get(self, db: Session, id: int) -> Optional[User]:
        return db.query(User).filter(User.id == id).first()
    
    def create(self, db: Session, obj_in: UserCreate) -> User:
        db_obj = User(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

crud_user = CRUDUser()

# app/services/user_service.py
def create_user(db: Session, user: UserCreate):
    # 비즈니스 로직
    if crud_user.get_by_email(db, user.email):
        raise HTTPException(400, "Email exists")
    return crud_user.create(db, user)
```

#### 우리 프로젝트 (Service 통합)
```python
# app/services/user_service.py
async def create_user(db: Session, user: UserCreateRequest) -> User:
    # 비즈니스 로직
    existing = await db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(400, "Email exists")
    
    # DB 접근
    db_user = User(**user.dict())
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user
```

---

## ⚖️ 장단점 분석

### Medium 구조 (모놀리식)

#### 장점 ✅
1. **단순성**
   - 하나의 코드베이스
   - 쉬운 디버깅
   - 로컬 개발 간편

2. **성능**
   - 서비스 간 네트워크 호출 없음
   - 트랜잭션 관리 용이

3. **초기 개발 속도**
   - 빠른 프로토타입
   - 작은 팀에 적합

4. **CRUD 분리**
   - DB 로직 명확히 분리
   - 재사용성 높음

#### 단점 ❌
1. **확장성 제한**
   - 전체 애플리케이션 스케일링 필요
   - 부분 스케일 불가능

2. **배포 리스크**
   - 작은 변경도 전체 재배포
   - 장애 시 전체 서비스 영향

3. **기술 스택 고정**
   - 모든 기능이 동일 기술
   - 도메인별 최적화 어려움

4. **팀 확장 어려움**
   - 코드 충돌 가능성
   - 큰 팀에서 관리 복잡

### 우리 구조 (마이크로서비스)

#### 장점 ✅
1. **독립 배포**
   - 서비스별 독립 배포
   - 장애 격리
   - 빠른 배포 사이클

2. **수평 확장**
   - 부하 높은 서비스만 스케일링
   - 비용 최적화

3. **기술 다양성**
   - 도메인별 최적 기술 선택
   - 점진적 기술 업그레이드

4. **팀 분리**
   - 도메인별 팀 운영
   - 명확한 소유권

5. **Kubernetes 친화적**
   - Pod 단위 배포
   - Auto-scaling
   - 무중단 배포

#### 단점 ❌
1. **복잡성 증가**
   - 서비스 간 통신
   - 분산 트랜잭션
   - 디버깅 어려움

2. **초기 설정 비용**
   - 인프라 구축
   - CI/CD 파이프라인
   - 모니터링 설정

3. **데이터 일관성**
   - 서비스 간 데이터 동기화
   - 분산 트랜잭션 처리

4. **네트워크 오버헤드**
   - 서비스 간 HTTP 호출
   - 레이턴시 증가

---

## 💡 세부 비교

### 1. **DB 세션 관리**

#### Medium 글
```python
# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

#### 우리 프로젝트
```python
# app/core/deps.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

**차이점**:
- Medium: 동기 (`Session`)
- 우리: 비동기 (`AsyncSession`) ⭐ 성능 우위

### 2. **의존성 주입**

#### Medium 글
```python
# app/core/dependencies.py
from fastapi import Depends

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    payload = jwt.decode(token, SECRET_KEY)
    user = crud.user.get(db, id=payload["sub"])
    if not user:
        raise HTTPException(401)
    return user
```

#### 우리 프로젝트
```python
# app/core/deps.py
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis)
) -> User:
    # 1. Blacklist 체크 (Redis)
    jti = get_jti_from_token(token)
    if await redis.exists(f"blacklist:{jti}"):
        raise HTTPException(401, "Token revoked")
    
    # 2. JWT 검증
    payload = jwt.decode(token, SECRET_KEY)
    
    # 3. 사용자 조회
    result = await db.execute(
        select(User).where(User.id == payload["sub"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401)
    return user
```

**차이점**:
- 우리: Redis Blacklist 체크 추가 ⭐
- 우리: 비동기 DB 쿼리

### 3. **Config 설정**

#### Medium 글
```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Project"
    VERSION: str = "1.0.0"
    DATABASE_URL: str
    SECRET_KEY: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

#### 우리 프로젝트
```python
# app/core/config.py
class Settings(BaseSettings):
    PROJECT_NAME: str = "Auth API"
    API_V1_STR: str = "/api/v1"
    
    # PostgreSQL (스키마별)
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_SCHEMA: str = "auth"  # ⭐ 스키마 분리
    
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:..."
            f"?options=-c%20search_path={self.POSTGRES_SCHEMA}"
        )
    
    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    
    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
```

**차이점**:
- 우리: 스키마 명시 (`search_path`) ⭐
- 우리: Redis 설정 추가
- 우리: Property로 동적 URL 생성

---

## 🎯 최종 권장사항

### 우리 프로젝트에 적용할 점

#### 1. **CRUD 계층 추가 (선택적)**

복잡한 쿼리가 많은 경우 CRUD 계층 도입 고려:

```python
# app/repositories/user_repository.py (Medium 스타일)
class UserRepository:
    async def get_by_id(self, db: AsyncSession, user_id: str) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def create(self, db: AsyncSession, user: User) -> User:
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

user_repository = UserRepository()

# app/services/user_service.py
async def create_user(
    db: AsyncSession,
    user_data: UserCreateRequest
) -> User:
    # 비즈니스 로직
    existing = await user_repository.get_by_email(db, user_data.email)
    if existing:
        raise HTTPException(400, "Email exists")
    
    # 생성
    user = User(**user_data.dict())
    return await user_repository.create(db, user)
```

**언제 사용?**
- ✅ 복잡한 쿼리가 많을 때
- ✅ 쿼리 재사용이 많을 때
- ✅ 팀이 클 때 (계층 분리 명확)

**언제 불필요?**
- ❌ 간단한 CRUD만 있을 때
- ❌ 작은 팀일 때
- ❌ 빠른 개발이 우선일 때

#### 2. **schemas/ 구조 개선**

Medium 스타일의 상속 패턴 일부 도입:

```python
# app/schemas/user.py
class UserBase(BaseModel):
    """공통 필드"""
    email: EmailStr
    username: str

class UserCreateRequest(UserBase):
    """생성 요청"""
    password: str

class UserUpdateRequest(BaseModel):
    """수정 요청 (선택적 필드)"""
    username: Optional[str] = None
    bio: Optional[str] = None

class UserResponse(UserBase):
    """응답"""
    id: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
```

**장점**:
- 코드 중복 감소
- 일관성 유지
- 타입 안정성

#### 3. **alembic/ 위치 결정**

```yaml
Option A: 서비스별 마이그레이션 (현재)
  services/auth/alembic/
  services/my/alembic/
  
  장점: 서비스 독립성
  단점: 중복 설정

Option B: 중앙 마이그레이션 (Medium 스타일)
  alembic/
  ├── versions/
  │   ├── auth/
  │   ├── my/
  │   └── ...
  
  장점: 통합 관리
  단점: 서비스 결합도 증가

권장: Option A (마이크로서비스에 적합) ⭐
```

### 최종 권장 구조

```
services/{service-name}/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── deps.py          # DB, Redis, get_current_user
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │
│   ├── schemas/             # Medium 스타일 상속 도입 ⭐
│   │   ├── __init__.py
│   │   └── {domain}.py      # UserBase, UserCreate, UserResponse
│   │
│   ├── models/
│   │   └── database.py
│   │
│   ├── services/            # 비즈니스 로직
│   │   └── {feature}_service.py
│   │
│   ├── repositories/        # 복잡한 경우만 추가 ⭐
│   │   └── {feature}_repository.py
│   │
│   └── utils/
│       ├── redis_client.py
│       ├── exceptions.py
│       └── responses.py
│
├── alembic/                 # 서비스별 마이그레이션 ⭐
│   ├── versions/
│   └── env.py
│
├── tests/
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 📊 요약

| 기능 | Medium (모놀리식) | 우리 (마이크로서비스) | 권장 |
|------|------------------|---------------------|------|
| **기본 구조** | ✅ 훌륭함 | ✅ 동일 | 유지 |
| **CRUD 계층** | ✅ 명시적 분리 | ⚠️ Service에 포함 | 선택적 도입 |
| **Schema 상속** | ✅ Base 패턴 | ⚠️ Request/Response 분리 | 일부 도입 |
| **비동기** | ❌ 동기 | ✅ 비동기 | 우리가 우위 ⭐ |
| **서비스 분리** | ❌ 모놀리식 | ✅ 마이크로서비스 | 우리가 우위 ⭐ |
| **Blacklist** | ❌ 없음 | ✅ Redis | 우리가 우위 ⭐ |

### 최종 결론

```yaml
현재 우리 구조 (9/10):
  ✅ 마이크로서비스 아키텍처
  ✅ 비동기 FastAPI
  ✅ Redis Blacklist
  ✅ Schema per Service
  ✅ 서비스별 독립 배포

Medium 구조에서 참고할 점:
  1. schemas/ 상속 패턴 (선택적 도입)
  2. repositories/ 계층 (복잡한 경우만)
  3. 명확한 계층 분리 (CRUD, Service)

결론:
  우리 구조는 이미 훌륭함! ⭐
  Medium 글의 장점을 선택적으로 도입하면 더욱 완벽해짐
```

---

**작성일**: 2025-11-12  
**작성자**: Claude Sonnet 4.5 Thinking  
**참고**: Medium - Vignaraj Ravi


