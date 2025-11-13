# 🔍 API 개발 사전 조사 보고서

> **작성일**: 2025-11-12  
> **프로젝트**: Eco² (이코에코) Backend  
> **대상 서비스**: auth, my, location, info

---

## 📋 목차

1. [프로젝트 개요](#-프로젝트-개요)
2. [데이터베이스 아키텍처](#-데이터베이스-아키텍처)
3. [서비스별 상세 요구사항](#-서비스별-상세-요구사항)
4. [외부 API 연동](#-외부-api-연동)
5. [기존 패턴 및 컨벤션](#-기존-패턴-및-컨벤션)
6. [개발 계획 및 우선순위](#-개발-계획-및-우선순위)

---

## 🎯 프로젝트 개요

### 애플리케이션 정보

```yaml
프로젝트명: Eco² (이코에코)
목적: AI 기반 쓰레기 분류 및 재활용 정보 제공 애플리케이션
아키텍처: Self-Managed Kubernetes (14-Node)
배포 방식: GitOps (Terraform + Ansible + Kustomize + ArgoCD)
```

### 전체 서비스 구성

```yaml
API Services (7개):
  1. auth: JWT 인증/인가 (t3.micro, 1GB) ⭐ [개발 대상]
  2. my: 사용자 정보 관리 (t3.micro, 1GB) ⭐ [개발 대상]
  3. scan: AI 이미지 분석 (t3.small, 2GB) [Pending - AI 파트]
  4. character: 캐릭터 시스템 (t3.micro, 1GB) [Pending - 디자이너]
  5. location: 위치 기반 서비스 (t3.micro, 1GB) ⭐ [개발 대상]
  6. info: 재활용 정보 (t3.micro, 1GB) ⭐ [개발 대상]
  7. chat: AI 챗봇 (t3.small, 2GB) [Pending - AI 파트]

Worker Services (2개):
  - storage: S3 이미지 처리 (t3.small, 2GB)
  - ai: AI 모델 추론 (t3.small, 2GB)

Infrastructure (4개):
  - postgresql: 메인 DB (t3.small, 2GB)
  - redis: JWT Blacklist + Cache (t3.micro, 1GB)
  - rabbitmq: 비동기 작업 큐 (t3.small, 2GB)
  - monitoring: Prometheus + Grafana (t3.small, 2GB)
```

### 개발 우선순위

```yaml
Phase 1 (현재): 유저 기능 + 부가 기능
  ✅ auth: 인증/인가
  ✅ my: 사용자 정보
  ✅ location: 위치 서비스
  ✅ info: 재활용 정보

Phase 2 (대기중): AI 기능
  ⏸️ scan: 이미지 분석 (AI 파트 개발 완료 후)
  ⏸️ chat: 챗봇 (AI 파트 개발 완료 후)

Phase 3 (대기중): 보상 시스템
  ⏸️ character: 캐릭터 보상 (디자이너 작업 완료 후)
```

---

## 🗄️ 데이터베이스 아키텍처

### Database per Service 패턴 (스키마 분리)

```yaml
PostgreSQL: k8s-postgresql.data.svc.cluster.local:5432/ecoeco
인스턴스: t3.small (2 vCPU, 2GB RAM)
스토리지: 100GB EBS gp3
패턴: 1개 PostgreSQL 인스턴스, 다중 스키마 분리
```

### 스키마 목록

```sql
-- 1. auth 스키마 (auth 서비스 전용)
CREATE SCHEMA auth;

CREATE TABLE auth.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE auth.refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,  -- Refresh Token 해시값
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_auth_users_email ON auth.users(email);
CREATE INDEX idx_auth_users_username ON auth.users(username);
CREATE INDEX idx_refresh_tokens_user ON auth.refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_expires ON auth.refresh_tokens(expires_at);

-- 참고: Access Token은 DB에 저장하지 않음 (Stateless)
-- 로그아웃 시 Redis Blacklist에 JTI 저장
```

```sql
-- 2. users 스키마 (my 서비스 전용)
CREATE SCHEMA users;

CREATE TABLE users.profiles (
    user_id UUID PRIMARY KEY,  -- auth.users.id 참조 (외래키 없음)
    nickname VARCHAR(100),
    avatar_url VARCHAR(500),
    bio TEXT,
    points INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    total_scans INTEGER DEFAULT 0,
    total_recycles INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users.settings (
    user_id UUID PRIMARY KEY,
    notification_enabled BOOLEAN DEFAULT TRUE,
    language VARCHAR(10) DEFAULT 'ko',
    theme VARCHAR(20) DEFAULT 'light',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users.activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,  -- scan, recycle, level_up, etc.
    points_earned INTEGER DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_users_profiles_user_id ON users.profiles(user_id);
CREATE INDEX idx_users_activities_user_id ON users.activities(user_id);
CREATE INDEX idx_users_activities_created ON users.activities(created_at);
```

```sql
-- 3. locations 스키마 (location 서비스 전용)
CREATE SCHEMA locations;

CREATE TABLE locations.user_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE locations.recycle_centers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    phone VARCHAR(20),
    operating_hours JSONB,
    region VARCHAR(50),  -- 시/도 정보
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE locations.recycle_bins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    bin_type VARCHAR(50),  -- plastic, paper, glass, general
    region VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_user_locations_user_id ON locations.user_locations(user_id);
CREATE INDEX idx_recycle_centers_region ON locations.recycle_centers(region);
CREATE INDEX idx_recycle_bins_region ON locations.recycle_bins(region);
CREATE INDEX idx_recycle_centers_location ON locations.recycle_centers USING GIST (
    ll_to_earth(latitude, longitude)
);
CREATE INDEX idx_recycle_bins_location ON locations.recycle_bins USING GIST (
    ll_to_earth(latitude, longitude)
);
```

```sql
-- 4. recycle_info 스키마 (info 서비스 전용)
CREATE SCHEMA recycle_info;

CREATE TABLE recycle_info.items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,  -- plastic, paper, metal, glass, etc.
    subcategory VARCHAR(50),
    description TEXT,
    how_to_recycle TEXT NOT NULL,
    do_not_do TEXT,
    tips JSONB,
    images JSONB,
    recyclable BOOLEAN DEFAULT TRUE,
    search_keywords TEXT[],  -- 검색용 키워드 배열
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE recycle_info.categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,
    icon VARCHAR(100),
    description TEXT,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE recycle_info.regional_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region VARCHAR(50) NOT NULL,  -- 시/도
    district VARCHAR(50),  -- 시/군/구
    rules JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE recycle_info.faqs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category VARCHAR(50),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    view_count INTEGER DEFAULT 0,
    helpful_count INTEGER DEFAULT 0,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE recycle_info.user_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    query TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_items_category ON recycle_info.items(category);
CREATE INDEX idx_items_search ON recycle_info.items USING GIN (search_keywords);
CREATE INDEX idx_regional_rules_region ON recycle_info.regional_rules(region);
CREATE INDEX idx_faqs_category ON recycle_info.faqs(category);
CREATE INDEX idx_faqs_view_count ON recycle_info.faqs(view_count DESC);
CREATE INDEX idx_user_queries_user_id ON recycle_info.user_queries(user_id);
```

### 스키마 접근 권한

```sql
-- Role 생성
CREATE ROLE api_auth_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_users_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_locations_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_recycle_role LOGIN PASSWORD 'secure_password';

-- 권한 부여
GRANT ALL ON SCHEMA auth TO api_auth_role;
GRANT ALL ON SCHEMA users TO api_users_role;
GRANT ALL ON SCHEMA locations TO api_locations_role;
GRANT ALL ON SCHEMA recycle_info TO api_recycle_role;

GRANT ALL ON ALL TABLES IN SCHEMA auth TO api_auth_role;
GRANT ALL ON ALL TABLES IN SCHEMA users TO api_users_role;
GRANT ALL ON ALL TABLES IN SCHEMA locations TO api_locations_role;
GRANT ALL ON ALL TABLES IN SCHEMA recycle_info TO api_recycle_role;

GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO api_auth_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA users TO api_users_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA locations TO api_locations_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA recycle_info TO api_recycle_role;
```

### 연결 문자열

```yaml
AUTH_DB_URL: "postgresql://api_auth_role:password@postgresql.data.svc.cluster.local:5432/ecoeco?options=-c%20search_path=auth"

USERS_DB_URL: "postgresql://api_users_role:password@postgresql.data.svc.cluster.local:5432/ecoeco?options=-c%20search_path=users"

LOCATIONS_DB_URL: "postgresql://api_locations_role:password@postgresql.data.svc.cluster.local:5432/ecoeco?options=-c%20search_path=locations"

RECYCLE_DB_URL: "postgresql://api_recycle_role:password@postgresql.data.svc.cluster.local:5432/ecoeco?options=-c%20search_path=recycle_info"
```

---

## 📝 서비스별 상세 요구사항

### 1️⃣ Auth Service (인증/인가)

#### 역할
- JWT 기반 인증 (Stateless)
- 회원가입/로그인/로그아웃
- Access Token + Refresh Token
- Redis Blacklist를 통한 토큰 무효화
- OAuth2 소셜 로그인 (Kakao, Google)

#### 핵심 엔드포인트

```python
POST   /api/v1/auth/register           # 회원가입
POST   /api/v1/auth/login              # 로그인 (JWT 발급)
POST   /api/v1/auth/logout             # 로그아웃 (토큰 블랙리스트)
POST   /api/v1/auth/refresh            # Access Token 갱신
GET    /api/v1/auth/me                 # 현재 사용자 정보
POST   /api/v1/auth/verify-email       # 이메일 인증
POST   /api/v1/auth/reset-password     # 비밀번호 재설정

# OAuth2
GET    /api/v1/auth/oauth/kakao        # Kakao 로그인 URL
POST   /api/v1/auth/oauth/kakao/callback  # Kakao 콜백
GET    /api/v1/auth/oauth/google       # Google 로그인 URL
POST   /api/v1/auth/oauth/google/callback # Google 콜백
```

#### 기술 스택

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0

# Auth
python-jose[cryptography]==3.3.0  # JWT
passlib[bcrypt]==1.7.4             # 비밀번호 해싱
python-multipart==0.0.6            # Form 데이터

# DB
sqlalchemy==2.0.25
asyncpg==0.29.0
alembic==1.13.1

# Redis
redis==5.0.1
hiredis==2.3.2

# HTTP Client
httpx==0.26.0

# Email (선택)
email-validator==2.1.0
```

#### Redis 활용 (Blacklist 방식)

```yaml
JWT Blacklist (로그아웃):
  키: blacklist:{token_jti}
  TTL: 토큰 만료 시간까지 (남은 시간)
  값: "1" 또는 user_id
  목적: 로그아웃된 Access Token 무효화
  
  예시:
    - 토큰 발급: 2025-11-12 10:00, 만료: 10:30
    - 로그아웃: 2025-11-12 10:15
    - Redis TTL: 15분 (남은 만료 시간)

Rate Limiting (로그인 제한):
  키: rate_limit:login:{ip}
  TTL: 60초
  값: 시도 횟수
  목적: 로그인 시도 횟수 제한 (5회/분)

User Info Cache (선택):
  키: user:info:{user_id}
  TTL: 300초 (5분)
  값: JSON (사용자 기본 정보)
  목적: /auth/me 엔드포인트 성능 향상
```

#### JWT 구조

```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "user_id",           // UUID
    "email": "user@example.com",
    "username": "testuser",
    "exp": 1234567890,          // 만료 시간 (30분 후)
    "iat": 1234567800,          // 발급 시간
    "jti": "unique-token-id",   // JWT ID (Blacklist 키로 사용)
    "type": "access"            // access | refresh
  }
}
```

#### 로그아웃 플로우 (Blacklist 방식)

```mermaid
sequenceDiagram
    participant Client
    participant API as Auth API
    participant Redis
    
    Client->>API: POST /auth/logout
    Note over Client: Authorization: Bearer {access_token}
    
    API->>API: JWT 검증 및 파싱
    API->>API: JTI 추출
    
    API->>Redis: SET blacklist:{jti} "1"
    Note over Redis: TTL = 토큰 남은 시간
    Redis-->>API: OK
    
    API-->>Client: 200 OK
    
    Note over Client,Redis: 이후 모든 요청에서 Blacklist 확인
    
    Client->>API: GET /auth/me
    API->>API: JWT 검증
    API->>Redis: EXISTS blacklist:{jti}
    
    alt 토큰이 Blacklist에 있음
        Redis-->>API: 1 (exists)
        API-->>Client: 401 Unauthorized
    else 토큰이 Blacklist에 없음
        Redis-->>API: 0 (not exists)
        API-->>Client: 200 OK (사용자 정보)
    end
```

---

### 2️⃣ My Service (사용자 정보)

#### 역할
- 사용자 프로필 관리
- 포인트/레벨 시스템
- 활동 히스토리
- 설정 관리

#### 핵심 엔드포인트

```python
GET    /api/v1/users/me                # 내 프로필 조회
PATCH  /api/v1/users/me                # 프로필 수정
DELETE /api/v1/users/me                # 계정 삭제 (Soft Delete)

GET    /api/v1/users/me/points         # 포인트 조회
GET    /api/v1/users/me/level          # 레벨 정보
GET    /api/v1/users/me/activities     # 활동 히스토리
GET    /api/v1/users/me/settings       # 설정 조회
PATCH  /api/v1/users/me/settings       # 설정 수정

POST   /api/v1/users/me/avatar         # 프로필 이미지 업로드 (비동기)
```

#### 포인트 시스템

```yaml
획득 방법:
  - 쓰레기 스캔: 10 포인트
  - 재활용 완료: 50 포인트
  - 일일 출석: 5 포인트
  - 친구 초대: 100 포인트

레벨 시스템:
  - 레벨 1: 0-100 포인트
  - 레벨 2: 101-300 포인트
  - 레벨 3: 301-600 포인트
  - 레벨 4: 601-1000 포인트
  - 레벨 5: 1001+ 포인트

레벨 혜택:
  - 캐릭터 스킨 언락
  - 특별 뱃지 획득
  - 리더보드 순위
```

#### Redis 캐싱

```yaml
User Profile Cache:
  키: user:profile:{user_id}
  TTL: 3600초 (1시간)
  목적: 프로필 정보 캐싱

User Points Cache:
  키: user:points:{user_id}
  TTL: 300초 (5분)
  목적: 포인트 정보 캐싱

Leaderboard:
  키: leaderboard:weekly
  타입: Sorted Set
  목적: 주간 리더보드
```

---

### 3️⃣ Location Service (위치 기반 서비스)

#### 역할
- 근처 분리수거함 검색
- 재활용 센터 위치 검색
- 주소 ↔ 좌표 변환 (Geocoding)
- Kakao Map API 연동

#### 핵심 엔드포인트

```python
# 검색
GET    /api/v1/locations/bins          # 근처 수거함 검색
GET    /api/v1/locations/centers       # 재활용 센터 검색

# Geocoding
POST   /api/v1/locations/geocode       # 주소 → 좌표
POST   /api/v1/locations/reverse       # 좌표 → 주소

# 사용자 위치
GET    /api/v1/locations/me            # 내 저장 위치 목록
POST   /api/v1/locations/me            # 위치 저장
PUT    /api/v1/locations/me/{id}       # 위치 수정
DELETE /api/v1/locations/me/{id}       # 위치 삭제
```

#### Kakao Map API 연동

```yaml
Local API (장소 검색):
  URL: https://dapi.kakao.com/v2/local/search/keyword.json
  용도: 근처 재활용 센터 검색
  
  파라미터:
    - query: 검색어 (재활용센터, 분리수거함 등)
    - x: 경도
    - y: 위도
    - radius: 반경 (m)

Geocoding API:
  URL: https://dapi.kakao.com/v2/local/search/address.json
  용도: 주소 → 좌표 변환

Reverse Geocoding API:
  URL: https://dapi.kakao.com/v2/local/geo/coord2address.json
  용도: 좌표 → 주소 변환
```

#### Redis 캐싱

```yaml
Geocoding Cache:
  키: geocode:{address}
  TTL: 86400초 (24시간)
  목적: Kakao API 호출 절약

Location Search Cache:
  키: location:bins:{lat}:{lon}:{radius}
  TTL: 3600초 (1시간)
  목적: 검색 결과 캐싱

Recycle Centers Cache:
  키: location:centers:{region}
  TTL: 86400초 (24시간)
  목적: 지역별 센터 정보 캐싱
```

---

### 4️⃣ Info Service (재활용 정보)

#### 역할
- 품목별 분리배출 정보 제공
- 카테고리별 재활용 가이드
- FAQ 관리
- 지역별 배출 규정
- 검색 기능

#### 핵심 엔드포인트

```python
# 품목 정보
GET    /api/v1/recycle/items/{id}      # 품목 상세 정보
GET    /api/v1/recycle/items           # 품목 목록 (페이지네이션)
POST   /api/v1/recycle/items/search    # 품목 검색 (키워드)

# 카테고리
GET    /api/v1/recycle/categories      # 카테고리 목록

# 지역 규정
GET    /api/v1/recycle/rules/{region}  # 지역별 배출 규정

# FAQ
GET    /api/v1/recycle/faq             # FAQ 목록
GET    /api/v1/recycle/faq/{id}        # FAQ 상세
POST   /api/v1/recycle/faq/{id}/helpful  # 도움 됨 표시

# 통계
GET    /api/v1/recycle/stats           # 재활용 통계
```

#### 품목 카테고리

```yaml
주요 카테고리:
  - plastic: 플라스틱 (페트병, 비닐 등)
  - paper: 종이 (박스, 신문 등)
  - metal: 금속 (캔, 철제품 등)
  - glass: 유리 (병, 유리제품 등)
  - general: 일반 쓰레기
  - food: 음식물 쓰레기
  - large: 대형 폐기물
  - electronic: 전자제품
  - hazardous: 유해 폐기물
```

#### 검색 전략

```yaml
Option 1: PostgreSQL Full-Text Search (권장)
  - tsvector 인덱스 활용
  - 한글 검색 지원 (pg_trgm 확장)
  - 구현 난이도: 중간

Option 2: LIKE 검색 (간단)
  - 배열 필드 활용
  - GIN 인덱스
  - 구현 난이도: 낮음

Option 3: Elasticsearch (고급)
  - 별도 검색 엔진
  - 구현 난이도: 높음
  - 향후 확장용
```

#### Redis 캐싱

```yaml
Item Cache:
  키: recycle:item:{id}
  TTL: 86400초 (24시간)
  목적: 품목 정보 캐싱

Categories Cache:
  키: recycle:categories
  TTL: 86400초 (24시간)
  목적: 카테고리 목록 캐싱

Search Cache:
  키: recycle:search:{query}
  TTL: 3600초 (1시간)
  목적: 검색 결과 캐싱

Regional Rules Cache:
  키: recycle:rules:{region}
  TTL: 86400초 (24시간)
  목적: 지역 규정 캐싱
```

---

## 🔌 외부 API 연동

### Kakao API

#### Kakao REST API Key

```yaml
용도: Kakao Map API 연동
설정:
  - 환경변수: KAKAO_API_KEY
  - Kubernetes Secret: kakao-secrets
  - 헤더: Authorization: KakaoAK {API_KEY}
```

#### Kakao OAuth 2.0

```yaml
용도: Kakao 소셜 로그인
설정:
  - Client ID: KAKAO_CLIENT_ID
  - Client Secret: KAKAO_CLIENT_SECRET
  - Redirect URI: https://growbin.app/auth/kakao/callback
  
인증 플로우:
  1. 프론트엔드가 Kakao 로그인 URL로 리다이렉트
  2. 사용자 로그인 후 Callback으로 code 전달
  3. Backend가 code로 Access Token 요청
  4. Access Token으로 사용자 정보 조회
  5. JWT 발급 및 DB 저장
```

### Google OAuth 2.0

```yaml
용도: Google 소셜 로그인
설정:
  - Client ID: GOOGLE_CLIENT_ID
  - Client Secret: GOOGLE_CLIENT_SECRET
  - Redirect URI: https://growbin.app/auth/google/callback
  
인증 플로우:
  (Kakao와 동일)
```

### OpenAI API (AI 서비스용)

```yaml
용도: GPT-4o-mini API 호출 (chat, scan)
설정:
  - API Key: OPENAI_API_KEY
  - Kubernetes Secret: openai-secrets
  
비고: scan, chat 서비스 개발 시 활용
```

---

## 🛠️ 기존 패턴 및 컨벤션

### FastAPI 프로젝트 구조

```
services/{service-name}/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱 진입점
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # 환경 변수 설정
│   │   ├── security.py      # JWT, 비밀번호 해싱
│   │   └── deps.py          # 의존성 주입 (DB, Redis)
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py    # API 라우터 통합
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── auth.py  # 엔드포인트 구현
│   │           └── users.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── database.py      # SQLAlchemy 모델
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── request.py       # 요청 스키마
│   │   └── response.py      # 응답 스키마
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py  # 비즈니스 로직
│   │   └── user_service.py
│   └── utils/
│       ├── __init__.py
│       ├── redis.py         # Redis 헬퍼
│       └── exceptions.py    # 커스텀 예외
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_api.py
```

### Health Check 패턴

```python
# app/health.py (기존 패턴)
from fastapi import FastAPI
import asyncpg
import redis

@app.get("/health")
def health_check():
    """기본 Health Check"""
    return {"status": "healthy", "service": "auth-api"}

@app.get("/ready")
async def readiness_check():
    """Readiness Check (DB, Redis 연결 확인)"""
    try:
        # PostgreSQL 확인
        await check_postgres()
        
        # Redis 확인
        await check_redis()
        
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not ready", "error": str(e)}, 503
```

### 환경변수 관리

```python
# app/core/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Auth API"
    API_V1_STR: str = "/api/v1"
    
    # PostgreSQL
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "postgresql.data.svc.cluster.local")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "ecoeco")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "api_auth_role")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            f"?options=-c%20search_path=auth"
        )
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis.data.svc.cluster.local")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "changeme")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    class Config:
        case_sensitive = True

settings = Settings()
```

---

## 📅 개발 계획 및 우선순위

### Phase 1: Auth Service (최우선) ⭐⭐⭐

```yaml
목표: JWT 인증 기반 마련
기간: 1-2일
난이도: 중간

Tasks:
  1. 프로젝트 구조 설정
     - core/config.py (환경변수)
     - core/security.py (JWT, 비밀번호)
     - core/deps.py (DB, Redis 의존성)
  
  2. DB 모델 및 마이그레이션
     - models/database.py (SQLAlchemy 모델)
     - Alembic 초기화
     - 초기 마이그레이션 생성
  
  3. 기본 인증 엔드포인트
     - POST /auth/register (회원가입)
     - POST /auth/login (로그인)
     - POST /auth/logout (로그아웃)
     - POST /auth/refresh (토큰 갱신)
     - GET /auth/me (현재 사용자)
  
  4. Redis 연동
     - JWT Blacklist
     - Rate Limiting
     - Session Cache
  
  5. 테스트
     - 단위 테스트 (pytest)
     - 통합 테스트
     - Postman 컬렉션

우선순위: 최우선 (다른 서비스가 의존)
```

### Phase 2: My Service (2순위) ⭐⭐

```yaml
목표: 사용자 정보 관리
기간: 1-2일
난이도: 낮음

Tasks:
  1. 프로젝트 구조 설정
  2. DB 모델 및 마이그레이션
  3. 엔드포인트 구현
     - GET /users/me (프로필 조회)
     - PATCH /users/me (프로필 수정)
     - GET /users/me/points (포인트 조회)
     - GET /users/me/activities (활동 히스토리)
     - GET /users/me/settings (설정)
     - PATCH /users/me/settings (설정 수정)
  
  4. Redis 캐싱
  5. Auth Service 연동 (JWT 검증)
  6. 테스트

우선순위: 2순위 (Auth 완료 후)
```

### Phase 3: Location Service (3순위) ⭐⭐

```yaml
목표: 위치 기반 서비스 + Kakao Map API
기간: 2-3일
난이도: 중간

Tasks:
  1. 프로젝트 구조 설정
  2. DB 모델 및 마이그레이션
  3. Kakao Map API 연동
     - httpx 클라이언트
     - Local API (장소 검색)
     - Geocoding API
     - Reverse Geocoding API
  
  4. 엔드포인트 구현
     - GET /locations/bins (근처 수거함)
     - GET /locations/centers (재활용 센터)
     - POST /locations/geocode (주소→좌표)
     - POST /locations/reverse (좌표→주소)
     - GET /locations/me (내 위치 목록)
     - POST /locations/me (위치 저장)
  
  5. Redis 캐싱 (Kakao API 호출 절약)
  6. 위치 기반 검색 최적화 (PostGIS)
  7. 테스트

우선순위: 3순위
```

### Phase 4: Info Service (4순위) ⭐

```yaml
목표: 재활용 정보 제공
기간: 2-3일
난이도: 중간

Tasks:
  1. 프로젝트 구조 설정
  2. DB 모델 및 마이그레이션
  3. 초기 데이터 삽입
     - 품목 정보 (100+ 항목)
     - 카테고리 (9개)
     - FAQ (20+ 항목)
     - 지역별 규정 (17개 시/도)
  
  4. 검색 기능 구현
     - PostgreSQL Full-Text Search
     - 키워드 검색 최적화
  
  5. 엔드포인트 구현
     - GET /recycle/items (품목 목록)
     - GET /recycle/items/{id} (품목 상세)
     - POST /recycle/items/search (검색)
     - GET /recycle/categories (카테고리)
     - GET /recycle/rules/{region} (지역 규정)
     - GET /recycle/faq (FAQ)
  
  6. Redis 캐싱
  7. 테스트

우선순위: 4순위
```

### Phase 5: 통합 테스트 및 배포 ⭐⭐⭐

```yaml
목표: 전체 서비스 통합 및 배포
기간: 1-2일
난이도: 중간

Tasks:
  1. 서비스 간 통합 테스트
  2. Kubernetes 배포 설정
     - k8s/overlays/{service}/deployment-patch.yaml
     - 환경변수 설정
     - Secret 생성
  
  3. ArgoCD 배포
     - Git Push
     - ArgoCD 자동 동기화 확인
  
  4. API Gateway 설정 (Ingress)
  5. 모니터링 확인 (Prometheus + Grafana)
  6. 부하 테스트 (선택)
  7. 문서 작성

우선순위: 최종 단계
```

---

## 📊 예상 소요 시간

```yaml
Phase 1: Auth Service        - 1-2일
Phase 2: My Service           - 1-2일
Phase 3: Location Service     - 2-3일
Phase 4: Info Service         - 2-3일
Phase 5: 통합 테스트 및 배포   - 1-2일

총 예상 기간: 7-12일 (1.5-2.5주)
```

---

## ✅ 사전 준비 체크리스트

### 인프라

- [x] PostgreSQL 클러스터 가동
- [x] Redis 클러스터 가동
- [x] RabbitMQ 클러스터 가동 (scan, chat 용)
- [x] Kubernetes 클러스터 안정화
- [x] ArgoCD GitOps 파이프라인

### 외부 서비스

- [ ] Kakao Developers 앱 등록
- [ ] Kakao REST API Key 발급
- [ ] Kakao OAuth Client ID/Secret 발급
- [ ] Google Cloud Console 앱 등록
- [ ] Google OAuth Client ID/Secret 발급
- [ ] OpenAI API Key 발급 (chat, scan 용)

### 개발 환경

- [ ] Python 3.11+ 설치
- [ ] Docker Desktop 설치
- [ ] kubectl 설정 (k8s 클러스터 연결)
- [ ] PostgreSQL 클라이언트 (psql, DBeaver 등)
- [ ] Redis CLI
- [ ] Postman 또는 HTTPie

### Git 및 배포

- [ ] GitHub Repository 권한
- [ ] GHCR (GitHub Container Registry) 접근
- [ ] ArgoCD 접속 정보
- [ ] Kubernetes Secret 생성 스크립트

---

## 🎯 다음 단계

### 즉시 시작 가능

1. **Auth Service 개발 시작**
   - 프로젝트 구조 생성
   - DB 모델 정의
   - JWT 구현

2. **DB 마이그레이션 준비**
   - Alembic 설정
   - 초기 스키마 생성 스크립트

3. **외부 API 키 발급**
   - Kakao Developers
   - Google Cloud Console

### 대기 중

- [ ] scan (AI 파트 개발 완료 후)
- [ ] chat (AI 파트 개발 완료 후)
- [ ] character (디자이너 작업 완료 후)

---

## 📚 참고 문서

- [Database Schema Structure](./architecture/02-database-schema-structure.md)
- [Service Architecture](./architecture/03-SERVICE_ARCHITECTURE.md)
- [GitOps Pipeline](./deployment/GITOPS_PIPELINE_KUSTOMIZE.md)
- [Monitoring Setup](./deployment/MONITORING_SETUP.md)

---

**작성자**: AI Assistant  
**검토자**: [담당자명]  
**최종 업데이트**: 2025-11-12  
**버전**: v1.0.0

