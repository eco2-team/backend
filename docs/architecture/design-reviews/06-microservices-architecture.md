# 🏗️ 마이크로서비스 아키텍처 설계

> **최종 결정**: Kubernetes 기반 도메인별 서버 분리  
> **구성**: 5개 Namespace, Nginx Ingress, Helm Charts  
> **날짜**: 2025-10-30  
> **상태**: ✅ 최종 확정

## 📋 목차

1. [도메인 분석](#도메인-분석)
2. [아키텍처 옵션 비교](#아키텍처-옵션-비교)
3. [추천 아키텍처](#추천-아키텍처)
4. [최종 결정](#최종-결정)

---

## 🎯 도메인 분석

### 서비스 도메인 구조

```mermaid
graph TD
    subgraph Core["핵심 도메인 (High Traffic)"]
        Waste["🗑️ Waste Service<br/>쓰레기 인식<br/>- AI Vision 호출<br/>- 이미지 처리<br/>- 진행률 관리"]
        Recycling["♻️ Recycling Service<br/>재활용 정보<br/>- LLM 피드백<br/>- 세척법 제공<br/>- 분류 가이드"]
    end
    
    subgraph Support["지원 도메인 (Low Traffic)"]
        Auth["🔐 Auth Service<br/>인증/인가<br/>- OAuth 로그인<br/>- JWT 발급<br/>- 세션 관리"]
        Users["👤 Users Service<br/>사용자 관리<br/>- 프로필 조회<br/>- 정보 수정<br/>- 분석 이력"]
        Locations["📍 Locations Service<br/>위치 정보<br/>- 수거함 검색<br/>- 지도 연동<br/>- 거리 계산"]
    end
    
    Waste -.->|사용자 정보| Users
    Recycling -.->|분석 결과| Waste
    Locations -.->|사용자 위치| Users
    
    style Waste fill:#ffe1e1,stroke:#ff3333,stroke-width:3px
    style Recycling fill:#ffe1f5,stroke:#ff66cc,stroke-width:3px
    style Auth fill:#e1f5ff,stroke:#0066cc
    style Users fill:#e1ffe1,stroke:#00cc66
    style Locations fill:#fff4e1,stroke:#ff9900
```

### 도메인별 특성

| 도메인 | 트래픽 | 리소스 | 확장성 | 우선순위 |
|--------|--------|--------|--------|----------|
| **Waste** | 높음 | CPU/Memory (이미지 처리) | 수평 확장 필수 | 🔴 Critical |
| **Recycling** | 높음 | Network (LLM API) | 수평 확장 권장 | 🔴 Critical |
| **Auth** | 중간 | 낮음 | 2-3 인스턴스면 충분 | 🟡 Important |
| **Users** | 낮음 | 낮음 | 단일 인스턴스 가능 | 🟢 Normal |
| **Locations** | 낮음 | 낮음 | 단일 인스턴스 가능 | 🟢 Normal |

---

## 🔄 아키텍처 옵션 비교

### 옵션 1: **Monolithic (단일 서버)** ❌

```mermaid
graph TB
    subgraph Single["단일 FastAPI 서버"]
        AuthR[Auth Routes]
        UserR[Users Routes]
        WasteR[Waste Routes]
        RecyclingR[Recycling Routes]
        LocationsR[Locations Routes]
    end
    
    Single --> DB[(PostgreSQL)]
    Single --> Redis[(Redis)]
    
    style Single fill:#ffe1e1,stroke:#ff3333
```

**장점:**
- ✅ 구현 간단
- ✅ 배포 쉬움
- ✅ 로컬 개발 편함

**단점:**
- ❌ **도메인 분리 불가** (요구사항 미충족)
- ❌ 부분 배포 불가능
- ❌ 확장성 제한
- ❌ 장애 격리 불가

**결론: 요구사항 불일치로 기각 ❌**

---

### 옵션 2: **Docker Compose (Multi-Container)** ⭐ (해커톤 추천)

```mermaid
graph TB
    subgraph LB["Nginx / Traefik (API Gateway)"]
        Gateway[API Gateway<br/>:80]
    end
    
    subgraph Services["Docker Compose Services"]
        Auth["auth-service<br/>:8001"]
        Users["users-service<br/>:8002"]
        Waste["waste-service<br/>:8003<br/>(3 replicas)"]
        Recycling["recycling-service<br/>:8004<br/>(2 replicas)"]
        Locations["locations-service<br/>:8005"]
    end
    
    subgraph Data["공유 데이터"]
        DB[(PostgreSQL<br/>:5432)]
        Redis[(Redis<br/>:6379)]
    end
    
    Gateway -->|/api/v1/auth| Auth
    Gateway -->|/api/v1/users| Users
    Gateway -->|/api/v1/waste| Waste
    Gateway -->|/api/v1/recycling| Recycling
    Gateway -->|/api/v1/locations| Locations
    
    Auth --> DB
    Users --> DB
    Waste --> DB
    Recycling --> DB
    Locations --> DB
    
    Waste --> Redis
    Recycling --> Redis
    
    style Gateway fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style Waste fill:#ffe1e1,stroke:#ff3333,stroke-width:3px
    style Recycling fill:#ffe1f5,stroke:#ff66cc
    style Auth fill:#e1f5ff,stroke:#0066cc
    style Users fill:#e1ffe1,stroke:#00cc66
    style Locations fill:#fff0e1,stroke:#ffaa00
```

#### docker-compose.yml 구조

```yaml
version: '3.8'

services:
  # API Gateway
  gateway:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/gateway.conf:/etc/nginx/nginx.conf
    depends_on:
      - auth-service
      - users-service
      - waste-service
      - recycling-service
      - locations-service
  
  # 도메인 서비스들
  auth-service:
    build:
      context: ./services/auth
    environment:
      SERVICE_NAME: auth
      DATABASE_URL: postgresql://user:pass@db:5432/sesacthon
    ports:
      - "8001:8000"
  
  users-service:
    build:
      context: ./services/users
    ports:
      - "8002:8000"
  
  waste-service:
    build:
      context: ./services/waste
    deploy:
      replicas: 3  # 부하 분산
    environment:
      AI_VISION_API_URL: ${AI_VISION_API_URL}
    ports:
      - "8003-8005:8000"
  
  recycling-service:
    build:
      context: ./services/recycling
    deploy:
      replicas: 2
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    ports:
      - "8006-8007:8000"
  
  locations-service:
    build:
      context: ./services/locations
    ports:
      - "8008:8000"
  
  # Celery Workers (Waste/Recycling 전용)
  waste-worker:
    build:
      context: ./services/waste
    command: celery -A app.worker worker --loglevel=info
    deploy:
      replicas: 5
  
  # 공유 데이터
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

**장점:**
- ✅ **도메인 분리 완료** (독립적 서비스)
- ✅ **구현 간단** (Docker Compose만)
- ✅ **부분 배포 가능** (waste만 재시작)
- ✅ **개발 편의성** (docker-compose up 하나로 실행)
- ✅ **비용 효율** (단일 EC2에서 실행 가능)
- ✅ **해커톤 적합** (1-2일 내 구현 가능)

**단점:**
- ⚠️ 단일 서버 의존 (EC2 1대)
- ⚠️ 자동 스케일링 제한적
- ⚠️ 서비스 디스커버리 수동

**구현 난이도:** ⭐⭐ (낮음)  
**해커톤 적합도:** ⭐⭐⭐⭐⭐ (최고)

---

### 옵션 3: **AWS ECS (Fargate) - Multi-Service** ⭐⭐

```mermaid
graph TB
    subgraph ALB["AWS Application Load Balancer"]
        LB[ALB<br/>Path-based Routing]
    end
    
    subgraph ECS["ECS Cluster"]
        subgraph Task1["Task Definition: auth"]
            Auth1[auth-service<br/>Container]
        end
        
        subgraph Task2["Task Definition: users"]
            Users1[users-service<br/>Container]
        end
        
        subgraph Task3["Task Definition: waste"]
            Waste1[waste-service #1]
            Waste2[waste-service #2]
            Waste3[waste-service #3]
        end
        
        subgraph Task4["Task Definition: recycling"]
            Recycling1[recycling-service #1]
            Recycling2[recycling-service #2]
        end
        
        subgraph Task5["Task Definition: locations"]
            Locations1[locations-service]
        end
    end
    
    subgraph Data["AWS 관리형 서비스"]
        RDS[(RDS PostgreSQL)]
        ElastiCache[(ElastiCache Redis)]
    end
    
    LB -->|/api/v1/auth| Task1
    LB -->|/api/v1/users| Task2
    LB -->|/api/v1/waste| Task3
    LB -->|/api/v1/recycling| Task4
    LB -->|/api/v1/locations| Task5
    
    Task1 --> RDS
    Task2 --> RDS
    Task3 --> RDS
    Task4 --> RDS
    Task5 --> RDS
    
    Task3 --> ElastiCache
    Task4 --> ElastiCache
    
    style LB fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style Waste1 fill:#ffe1e1,stroke:#ff3333
    style Waste2 fill:#ffe1e1,stroke:#ff3333
    style Waste3 fill:#ffe1e1,stroke:#ff3333
    style Recycling1 fill:#ffe1f5,stroke:#ff66cc
    style Recycling2 fill:#ffe1f5,stroke:#ff66cc
```

**장점:**
- ✅ **진정한 마이크로서비스**
- ✅ **자동 스케일링** (서비스별 독립)
- ✅ **관리형 서비스** (인프라 관리 최소화)
- ✅ **고가용성** (Multi-AZ)
- ✅ **장애 격리** (한 서비스 죽어도 다른 서비스 정상)

**단점:**
- ⚠️ **비용 높음** ($200-300/월)
- ⚠️ **설정 복잡** (Task Definition × 5개)
- ⚠️ **로컬 개발** 어려움
- ⚠️ **디버깅** 복잡

**구현 난이도:** ⭐⭐⭐⭐ (높음)  
**해커톤 적합도:** ⭐⭐⭐ (보통)

---

### 옵션 4: **Kubernetes (EKS/GKE)** ❌

```mermaid
graph TB
    subgraph Ingress["Ingress Controller (Nginx)"]
        IG[Ingress<br/>Path Routing]
    end
    
    subgraph K8s["Kubernetes Cluster"]
        subgraph NS1["Namespace: auth"]
            AuthDep[Deployment: auth<br/>Replicas: 2]
            AuthSvc[Service: auth-svc]
        end
        
        subgraph NS2["Namespace: waste"]
            WasteDep[Deployment: waste<br/>Replicas: 5]
            WasteSvc[Service: waste-svc]
            WasteHPA[HPA: Auto Scale<br/>Min: 2, Max: 10]
        end
        
        subgraph NS3["Namespace: recycling"]
            RecyclingDep[Deployment: recycling<br/>Replicas: 3]
            RecyclingSvc[Service: recycling-svc]
        end
    end
    
    IG --> AuthSvc
    IG --> WasteSvc
    IG --> RecyclingSvc
    
    AuthSvc --> AuthDep
    WasteSvc --> WasteDep
    RecyclingSvc --> RecyclingDep
    
    WasteHPA -.->|Auto Scale| WasteDep
    
    style IG fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style WasteDep fill:#ffe1e1,stroke:#ff3333,stroke-width:3px
```

**장점:**
- ✅ **최고 수준의 확장성**
- ✅ **자동 복구** (Self-healing)
- ✅ **서비스 메시** (Istio 등)
- ✅ **진정한 Cloud Native**

**단점:**
- ❌ **학습 곡선 매우 높음**
- ❌ **설정 극도로 복잡** (Helm, YAML 지옥)
- ❌ **비용 매우 높음** ($500+/월)
- ❌ **해커톤 기간에 불가능**
- ❌ **오버엔지니어링**

**구현 난이도:** ⭐⭐⭐⭐⭐ (매우 높음)  
**해커톤 적합도:** ⭐ (부적합)

**결론: 해커톤 규모에 과도함 ❌**

---

### 옵션 5: **하이브리드 (Docker Compose + 도메인 분리)** ⭐⭐⭐ (최종 추천)

```mermaid
graph TB
    subgraph Client["📱 클라이언트"]
        App[Mobile App]
    end
    
    subgraph Edge["엣지 계층"]
        CDN[CloudFront CDN]
        Gateway[API Gateway<br/>Nginx/Traefik<br/>Path-based Routing]
    end
    
    subgraph Backend["백엔드 서비스 (Docker Compose)"]
        subgraph Core["Core Services (High Load)"]
            Waste[waste-service × 3<br/>- AI Vision<br/>- Celery Worker × 5]
            Recycling[recycling-service × 2<br/>- LLM Integration]
        end
        
        subgraph Support["Support Services"]
            Auth[auth-service × 2<br/>- OAuth<br/>- JWT]
            Users[users-service × 1]
            Locations[locations-service × 1]
        end
    end
    
    subgraph Data["데이터 계층"]
        DB[(PostgreSQL<br/>Single Primary<br/>+ Read Replica)]
        Cache[(Redis Cluster<br/>3 nodes)]
    end
    
    subgraph External["외부 서비스"]
        S3[S3<br/>Image Storage]
        AI[AI APIs<br/>Roboflow/OpenAI]
        Map[Kakao Map]
    end
    
    App --> CDN
    CDN --> Gateway
    
    Gateway -->|/api/v1/auth/*| Auth
    Gateway -->|/api/v1/users/*| Users
    Gateway -->|/api/v1/waste/*| Waste
    Gateway -->|/api/v1/recycling/*| Recycling
    Gateway -->|/api/v1/locations/*| Locations
    
    Waste --> DB
    Waste --> Cache
    Waste --> S3
    Waste --> AI
    
    Recycling --> DB
    Recycling --> Cache
    Recycling --> AI
    
    Auth --> DB
    Auth --> Cache
    
    Users --> DB
    Locations --> DB
    Locations --> Map
    
    style Gateway fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style Waste fill:#ffe1e1,stroke:#ff3333,stroke-width:3px
    style Recycling fill:#ffe1f5,stroke:#ff66cc,stroke-width:2px
    style Auth fill:#e1f5ff,stroke:#0066cc
    style Users fill:#e1ffe1,stroke:#00cc66
    style Locations fill:#fff0e1,stroke:#ffaa00
```

#### 프로젝트 구조

```
backend/
├── services/                    # 도메인별 서비스
│   ├── auth/
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── users/
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── waste/                   # High Traffic
│   │   ├── app/
│   │   ├── worker/              # Celery Worker
│   │   ├── Dockerfile
│   │   ├── Dockerfile.worker
│   │   └── requirements.txt
│   │
│   ├── recycling/               # High Traffic
│   │   ├── app/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── locations/
│       ├── app/
│       ├── Dockerfile
│       └── requirements.txt
│
├── gateway/                     # API Gateway
│   └── nginx/
│       └── gateway.conf
│
├── shared/                      # 공유 라이브러리
│   ├── common/
│   │   ├── exceptions.py
│   │   ├── responses.py
│   │   └── dependencies.py
│   └── core/
│       ├── database.py
│       └── security.py
│
├── docker-compose.yml           # 전체 서비스 정의
├── docker-compose.dev.yml       # 개발 환경
└── Makefile
```

#### docker-compose.yml 예시

```yaml
version: '3.8'

services:
  # API Gateway
  gateway:
    image: traefik:v2.10
    ports:
      - "80:80"
      - "8080:8080"  # Dashboard
    volumes:
      - ./gateway/traefik.yml:/etc/traefik/traefik.yml
      - /var/run/docker.sock:/var/run/docker.sock
    labels:
      - "traefik.enable=true"
  
  # Auth Service
  auth-service:
    build: ./services/auth
    deploy:
      replicas: 2
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/sesacthon
      REDIS_URL: redis://redis:6379/0
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.auth.rule=PathPrefix(`/api/v1/auth`)"
      - "traefik.http.services.auth.loadbalancer.server.port=8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  # Waste Service (High Load)
  waste-service:
    build: ./services/waste
    deploy:
      replicas: 3  # 높은 트래픽 대응
    environment:
      AI_VISION_API_URL: ${AI_VISION_API_URL}
      DATABASE_URL: postgresql://user:pass@db:5432/sesacthon
      REDIS_URL: redis://redis:6379/1
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.waste.rule=PathPrefix(`/api/v1/waste`)"
      - "traefik.http.services.waste.loadbalancer.server.port=8000"
    depends_on:
      - db
      - redis
  
  # Waste Worker (Celery)
  waste-worker:
    build:
      context: ./services/waste
      dockerfile: Dockerfile.worker
    deploy:
      replicas: 5
    command: celery -A app.worker worker --loglevel=info --concurrency=4
    environment:
      REDIS_URL: redis://redis:6379/1
      AI_VISION_API_URL: ${AI_VISION_API_URL}
    depends_on:
      - redis
  
  # Recycling Service
  recycling-service:
    build: ./services/recycling
    deploy:
      replicas: 2
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      DATABASE_URL: postgresql://user:pass@db:5432/sesacthon
      REDIS_URL: redis://redis:6379/2
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.recycling.rule=PathPrefix(`/api/v1/recycling`)"
  
  # Users Service
  users-service:
    build: ./services/users
    deploy:
      replicas: 1
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.users.rule=PathPrefix(`/api/v1/users`)"
  
  # Locations Service
  locations-service:
    build: ./services/locations
    deploy:
      replicas: 1
    environment:
      KAKAO_MAP_API_KEY: ${KAKAO_MAP_API_KEY}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.locations.rule=PathPrefix(`/api/v1/locations`)"
  
  # 공유 데이터
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: sesacthon
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: sesacthon
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sesacthon"]
  
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:

networks:
  default:
    name: sesacthon_network
    driver: bridge
```

**장점:**
- ✅ **도메인 완전 분리** (각 서비스 독립)
- ✅ **서비스별 스케일링** (waste만 3개, locations는 1개)
- ✅ **Traefik 자동 라우팅** (설정 간단)
- ✅ **로컬/프로덕션 동일** (일관된 환경)
- ✅ **부분 배포 가능** (waste만 재시작)
- ✅ **비용 합리적** (EC2 t3.large 1대면 충분)

**단점:**
- ⚠️ 서비스가 5개 → 복잡도 증가
- ⚠️ 공유 라이브러리 관리 필요

**구현 난이도:** ⭐⭐⭐ (중간)  
**해커톤 적합도:** ⭐⭐⭐⭐ (높음)

---

### 옵션 6: **API Gateway + AWS Lambda (Serverless)** 🚀

```mermaid
graph TB
    subgraph Client["📱 클라이언트"]
        App[Mobile App]
    end
    
    subgraph AWS["AWS Serverless"]
        APIGW[API Gateway<br/>REST API]
        
        subgraph Lambda["Lambda Functions"]
            AuthLambda[auth-handler]
            UsersLambda[users-handler]
            WasteLambda[waste-handler]
            RecyclingLambda[recycling-handler]
            LocationsLambda[locations-handler]
        end
        
        SQS[SQS Queue<br/>비동기 처리]
        
        subgraph Worker["Lambda Workers"]
            WasteWorker[waste-worker<br/>AI Vision]
            RecyclingWorker[recycling-worker<br/>LLM]
        end
    end
    
    App --> APIGW
    APIGW -->|/auth| AuthLambda
    APIGW -->|/users| UsersLambda
    APIGW -->|/waste| WasteLambda
    APIGW -->|/recycling| RecyclingLambda
    APIGW -->|/locations| LocationsLambda
    
    WasteLambda --> SQS
    SQS --> WasteWorker
    SQS --> RecyclingWorker
    
    style APIGW fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style WasteLambda fill:#ffe1e1,stroke:#ff3333
    style WasteWorker fill:#ffe1e1,stroke:#ff3333
```

**장점:**
- ✅ **완전 자동 스케일링** (무제한)
- ✅ **사용량 기반 과금** (요청 없으면 $0)
- ✅ **관리 포인트 최소**
- ✅ **Cold Start 개선** (Provisioned Concurrency)

**단점:**
- ❌ **Cold Start** (첫 요청 2-3초 지연)
- ❌ **타임아웃 제한** (15분)
- ❌ **로컬 개발 어려움**
- ❌ **FastAPI 최적화 어려움**

**구현 난이도:** ⭐⭐⭐⭐⭐ (매우 높음)  
**해커톤 적합도:** ⭐ (부적합)

---

## 🎯 추천 아키텍처

### ⭐ **최종 추천: 하이브리드 (Docker Compose + 도메인 분리)**

```mermaid
graph TB
    subgraph Internet["🌐 인터넷"]
        Users[사용자들]
    end
    
    subgraph AWS["AWS EC2 (t3.large × 1)"]
        subgraph Gateway["API Gateway"]
            Traefik[Traefik<br/>:80, :443<br/>- Path Routing<br/>- Load Balancing<br/>- SSL]
        end
        
        subgraph Services["Docker Compose Services"]
            direction TB
            
            subgraph HighLoad["High Load Services"]
                W1[waste-api #1]
                W2[waste-api #2]
                W3[waste-api #3]
                WW1[waste-worker #1]
                WW2[waste-worker #2]
                WW3[waste-worker #3]
                WW4[waste-worker #4]
                WW5[waste-worker #5]
                
                R1[recycling-api #1]
                R2[recycling-api #2]
            end
            
            subgraph LowLoad["Low Load Services"]
                A1[auth-api × 2]
                U1[users-api × 1]
                L1[locations-api × 1]
            end
        end
        
        subgraph Data["Data Layer"]
            DB[(PostgreSQL)]
            Redis[(Redis)]
        end
    end
    
    Users --> Traefik
    
    Traefik -->|/api/v1/auth/*| A1
    Traefik -->|/api/v1/users/*| U1
    Traefik -->|/api/v1/waste/*| W1
    Traefik -->|/api/v1/waste/*| W2
    Traefik -->|/api/v1/waste/*| W3
    Traefik -->|/api/v1/recycling/*| R1
    Traefik -->|/api/v1/recycling/*| R2
    Traefik -->|/api/v1/locations/*| L1
    
    W1 --> Redis
    W2 --> Redis
    W3 --> Redis
    Redis --> WW1
    Redis --> WW2
    Redis --> WW3
    Redis --> WW4
    Redis --> WW5
    
    R1 --> Redis
    R2 --> Redis
    
    A1 --> DB
    U1 --> DB
    W1 --> DB
    R1 --> DB
    L1 --> DB
    
    style Traefik fill:#fff4e1,stroke:#ff9900,stroke-width:3px
    style W1 fill:#ffe1e1,stroke:#ff3333,stroke-width:2px
    style W2 fill:#ffe1e1,stroke:#ff3333,stroke-width:2px
    style W3 fill:#ffe1e1,stroke:#ff3333,stroke-width:2px
    style WW1 fill:#ffcccc,stroke:#ff3333
    style WW2 fill:#ffcccc,stroke:#ff3333
    style WW3 fill:#ffcccc,stroke:#ff3333
    style WW4 fill:#ffcccc,stroke:#ff3333
    style WW5 fill:#ffcccc,stroke:#ff3333
    style R1 fill:#ffe1f5,stroke:#ff66cc
    style R2 fill:#ffe1f5,stroke:#ff66cc
    style A1 fill:#e1f5ff,stroke:#0066cc
    style U1 fill:#e1ffe1,stroke:#00cc66
    style L1 fill:#fff0e1,stroke:#ffaa00
```

---

## ✅ 최종 결정

### **Docker Compose + Traefik (하이브리드 MSA)**

#### 선택 이유

1. **✅ 도메인 분리 달성**
   - 각 도메인이 독립적인 컨테이너
   - 서비스별 독립 배포 가능

2. **✅ 트래픽 기반 스케일링**
   - Waste: 3 replicas (높은 부하)
   - Recycling: 2 replicas
   - Users/Locations: 1 replica (낮은 부하)

3. **✅ 해커톤 적합**
   - 구현 시간: 2-3일
   - Docker Compose 하나로 관리
   - 로컬 개발 = 프로덕션 환경

4. **✅ 비용 효율**
   - EC2 t3.large 1대: ~$60/월
   - Kubernetes 대비 1/10 비용

5. **✅ 운영 편의성**
   - `docker-compose up` 하나로 전체 실행
   - 로그 확인 쉬움
   - 디버깅 간편

#### 서비스별 스펙

| 서비스 | Replicas | CPU | Memory | 이유 |
|--------|----------|-----|--------|------|
| **waste-api** | 3 | 0.5 | 512MB | 이미지 업로드 트래픽 |
| **waste-worker** | 5 | 1.0 | 1GB | AI 처리, 병렬 실행 |
| **recycling-api** | 2 | 0.3 | 256MB | LLM 호출 |
| **auth-api** | 2 | 0.2 | 256MB | OAuth 트래픽 |
| **users-api** | 1 | 0.2 | 256MB | 낮은 트래픽 |
| **locations-api** | 1 | 0.2 | 256MB | 낮은 트래픽 |

**총 리소스:**
- CPU: ~6 cores
- Memory: ~6GB
- EC2: t3.large (2 vCPU, 8GB) 또는 t3.xlarge (4 vCPU, 16GB)

---

## 🔧 구현 계획

### Phase 1: 기본 구조 (Day 1)

```bash
# 1. 서비스 분리
services/
├── auth/       # FastAPI + OAuth
├── users/      # FastAPI + CRUD
├── waste/      # FastAPI + Celery
├── recycling/  # FastAPI + LLM
└── locations/  # FastAPI + Map API

# 2. 공유 라이브러리
shared/
├── common/     # 공통 유틸
└── core/       # DB, Security

# 3. docker-compose.yml 작성
# 4. Traefik Gateway 설정
```

### Phase 2: 서비스 구현 (Day 2-3)

```bash
# 각 서비스 병렬 개발
- auth: OAuth 통합
- waste: AI Vision + Celery
- recycling: LLM 통합
- users: 기본 CRUD
- locations: 지도 API
```

### Phase 3: 통합 & 배포 (Day 4)

```bash
# 1. 서비스 간 통신 테스트
# 2. Gateway 라우팅 검증
# 3. EC2 배포
# 4. 모니터링 설정
```

---

## 📊 성능 예측

### 동시 사용자 100명 처리

```
=== 요청 분산 ===
Auth: 20 req/s
Users: 10 req/s
Waste: 150 req/s (폴링 포함)
Recycling: 50 req/s
Locations: 20 req/s

=== 서비스별 처리 ===
Waste (3 replicas): 150 / 3 = 50 req/s each
→ FastAPI 여유도 95%

Recycling (2 replicas): 50 / 2 = 25 req/s each
→ 여유도 97%

Auth/Users/Locations (1 replica): 각 10-20 req/s
→ 여유도 98%

결론: 충분히 처리 가능 ✅
```

---

## 💰 비용 비교

### 월간 비용 (1만 요청 기준)

| 아키텍처 | AWS 비용 | 관리 난이도 | 해커톤 적합 |
|----------|----------|-------------|------------|
| **Docker Compose** | $60 | ⭐⭐ 낮음 | ⭐⭐⭐⭐⭐ |
| **ECS Fargate** | $200 | ⭐⭐⭐ 중간 | ⭐⭐⭐ |
| **Kubernetes** | $500 | ⭐⭐⭐⭐⭐ 높음 | ⭐ |
| **Lambda** | $100 | ⭐⭐⭐⭐ 높음 | ⭐⭐ |

---

## 🔄 향후 전환 전략

### 단계별 발전 경로

```mermaid
flowchart LR
    A[Stage 1:<br/>Docker Compose<br/>단일 EC2] --> B[Stage 2:<br/>Docker Swarm<br/>다중 EC2]
    B --> C[Stage 3:<br/>AWS ECS<br/>관리형 서비스]
    C --> D[Stage 4:<br/>Kubernetes<br/>Cloud Native]
    
    A -.->|해커톤| A
    B -.->|MVP 출시| B
    C -.->|정식 서비스| C
    D -.->|대규모 확장| D
    
    style A fill:#e1ffe1,stroke:#00cc66,stroke-width:3px
    style B fill:#fff4e1,stroke:#ff9900
    style C fill:#e1f5ff,stroke:#0066cc
    style D fill:#f0e1ff,stroke:#9933ff
```

**해커톤 → MVP → 프로덕션 전환이 자연스러움**

---

## 📚 참고 자료

- [Docker Compose 공식 문서](https://docs.docker.com/compose/)
- [Traefik 공식 문서](https://doc.traefik.io/traefik/)
- [Microservices Pattern](https://microservices.io/patterns/index.html)
- [12 Factor App](https://12factor.net/)

---

**작성일**: 2025-10-30  
**결정 대기**: 팀 논의 후 최종 확정  
**상태**: 🔄 검토 중

