# 🗄️ 데이터베이스 스키마 구조

> **13-Node 아키텍처의 Database per Service 패턴**  
> **1개 PostgreSQL 인스턴스, 다중 스키마 분리**  
> **Eco² (이코에코) - v0.6.0**

---

## 📋 목차

1. [아키텍처 패턴](#아키텍처-패턴)
2. [PostgreSQL 스키마 구조](#postgresql-스키마-구조)
3. [Worker Local SQLite WAL](#worker-local-sqlite-wal)
4. [데이터 흐름](#데이터-흐름)

---

## 🏗️ 아키텍처 패턴

### Database per Service (Schema 분리)

```mermaid
graph TB
    subgraph PostgreSQL["PostgreSQL (k8s-postgresql, t3a.medium)"]
        direction TB
        AuthDB[(auth 스키마)]
        UserDB[(users 스키마)]
        LocationDB[(locations 스키마)]
        WasteDB[(waste 스키마)]
        RecycleDB[(recycle_info 스키마)]
        ChatDB[(chat_llm 스키마)]
        TaskDB[(tasks 스키마<br/>Worker 동기화)]
    end
    
    subgraph API["API Services (6개)"]
        AuthAPI[API-Auth]
        UserAPI[API-Userinfo]
        LocAPI[API-Location]
        WasteAPI[API-Waste]
        RecycleAPI[API-Recycle-Info]
        ChatAPI[API-Chat-LLM]
    end
    
    subgraph Workers["Worker Services (2개)"]
        StorageW[Worker-Storage<br/>Local SQLite WAL]
        AIW[Worker-AI<br/>Local SQLite WAL]
    end
    
    AuthAPI -->|auth 스키마만 접근| AuthDB
    UserAPI -->|users 스키마만 접근| UserDB
    LocAPI -->|locations 스키마만 접근| LocationDB
    WasteAPI -->|waste 스키마만 접근| WasteDB
    RecycleAPI -->|recycle_info 스키마만 접근| RecycleDB
    ChatAPI -->|chat_llm 스키마만 접근| ChatDB
    
    StorageW -->|배치 동기화<br/>5분 주기| TaskDB
    AIW -->|배치 동기화<br/>5분 주기| TaskDB
    
    style PostgreSQL fill:#1a5490,stroke:#0d2950,stroke-width:4px,color:#fff
    style AuthDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style UserDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style LocationDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style WasteDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style RecycleDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style ChatDB fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    style TaskDB fill:#e67e22,stroke:#ca6f1e,stroke-width:2px,color:#fff
    
    style AuthAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style UserAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style LocAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style WasteAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style RecycleAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style ChatAPI fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    
    style StorageW fill:#16a085,stroke:#117a65,stroke-width:2px,color:#fff
    style AIW fill:#16a085,stroke:#117a65,stroke-width:2px,color:#fff
```

### 주요 특징

#### ✅ 장점
- **논리적 격리**: 각 서비스가 독립적인 스키마 소유
- **비용 효율**: 1개 PostgreSQL 인스턴스만 필요
- **관리 용이**: 중앙 집중식 백업/모니터링
- **리소스 효율**: 연결 풀 공유

#### ⚠️ 주의사항
- **스키마 명명 규칙**: 각 서비스별 고유 스키마명
- **권한 분리**: 각 API는 자신의 스키마만 접근
- **트랜잭션 격리**: 스키마 간 JOIN 최소화

---

## 🗄️ PostgreSQL 스키마 구조

### 노드 정보

```yaml
노드: k8s-postgresql
인스턴스 타입: t3a.medium (2 vCPU, 4GB RAM)
네임스페이스: database
스토리지: 100GB (EBS gp3)
배포 방식: StatefulSet
```

### 스키마 목록

```mermaid
graph LR
    subgraph PG["PostgreSQL Instance"]
        direction TB
        
        subgraph API_Schemas["API 전용 스키마"]
            S1[auth<br/>인증/인가]
            S2[users<br/>사용자 정보]
            S3[locations<br/>위치 서비스]
            S4[waste<br/>쓰레기 분석]
            S5[recycle_info<br/>재활용 정보]
            S6[chat_llm<br/>LLM 챗봇]
        end
        
        subgraph Worker_Schemas["Worker 전용 스키마"]
            S7[tasks<br/>작업 결과/이력]
        end
        
        subgraph System_Schemas["시스템 스키마"]
            S8[public<br/>공통 설정]
        end
    end
    
    style PG fill:#1a5490,stroke:#0d2950,stroke-width:4px,color:#fff
    style API_Schemas fill:#2c3e50,stroke:#1a252f,stroke-width:2px,color:#fff
    style Worker_Schemas fill:#16a085,stroke:#117a65,stroke-width:2px,color:#fff
    style System_Schemas fill:#7f8c8d,stroke:#626567,stroke-width:2px,color:#fff
    
    style S1 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S2 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S3 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S4 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S5 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S6 fill:#9b59b6,stroke:#7d3c98,stroke-width:2px,color:#fff
    style S7 fill:#e67e22,stroke:#ca6f1e,stroke-width:2px,color:#fff
    style S8 fill:#95a5a6,stroke:#7b8a8b,stroke-width:2px,color:#000
```

### 상세 스키마 정보

#### 1. auth 스키마
```sql
-- 소유자: api-auth 서비스
-- 테이블:
CREATE SCHEMA auth;

CREATE TABLE auth.users (
    id UUID PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE auth.sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id),
    token VARCHAR(500) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE auth.refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id),
    token VARCHAR(500) NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
```

#### 2. users 스키마
```sql
-- 소유자: api-userinfo 서비스
CREATE SCHEMA users;

CREATE TABLE users.profiles (
    user_id UUID PRIMARY KEY,  -- auth.users.id 참조 (외래키 없음)
    nickname VARCHAR(100),
    avatar_url VARCHAR(500),
    bio TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users.settings (
    user_id UUID PRIMARY KEY,
    notification_enabled BOOLEAN DEFAULT TRUE,
    language VARCHAR(10) DEFAULT 'ko',
    theme VARCHAR(20) DEFAULT 'light'
);
```

#### 3. locations 스키마
```sql
-- 소유자: api-location 서비스
CREATE SCHEMA locations;

CREATE TABLE locations.user_locations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,  -- auth.users.id 참조
    name VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE locations.recycle_centers (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    phone VARCHAR(20),
    operating_hours JSONB
);
```

#### 4. waste 스키마
```sql
-- 소유자: api-waste 서비스
CREATE SCHEMA waste;

CREATE TABLE waste.analyses (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    waste_type VARCHAR(50),  -- plastic, paper, metal, glass, etc.
    confidence DECIMAL(5, 4),
    analysis_result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE waste.images (
    id UUID PRIMARY KEY,
    analysis_id UUID REFERENCES waste.analyses(id),
    s3_key VARCHAR(500) NOT NULL,
    cloudfront_url VARCHAR(500),
    uploaded_at TIMESTAMP DEFAULT NOW()
);
```

#### 5. recycle_info 스키마
```sql
-- 소유자: api-recycle-info 서비스
CREATE SCHEMA recycle_info;

CREATE TABLE recycle_info.items (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    how_to_recycle TEXT,
    do_not_do TEXT,
    images JSONB
);

CREATE TABLE recycle_info.user_queries (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    query TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 6. chat_llm 스키마
```sql
-- 소유자: api-chat-llm 서비스
CREATE SCHEMA chat_llm;

CREATE TABLE chat_llm.conversations (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chat_llm.messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES chat_llm.conversations(id),
    role VARCHAR(20) NOT NULL,  -- user, assistant
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 7. tasks 스키마 (Worker 동기화)
```sql
-- 소유자: Worker 서비스
CREATE SCHEMA tasks;

CREATE TABLE tasks.task_results (
    id UUID PRIMARY KEY,
    task_id VARCHAR(255) UNIQUE NOT NULL,
    task_name VARCHAR(100) NOT NULL,
    worker_name VARCHAR(50) NOT NULL,  -- storage, ai
    status VARCHAR(20) NOT NULL,  -- pending, success, failure
    result JSONB,
    error TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    synced_at TIMESTAMP DEFAULT NOW()  -- WAL 동기화 시각
);

CREATE TABLE tasks.task_history (
    id UUID PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- queued, started, completed, failed
    event_data JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tasks_worker ON tasks.task_results(worker_name);
CREATE INDEX idx_tasks_status ON tasks.task_results(status);
CREATE INDEX idx_tasks_completed ON tasks.task_results(completed_at);
```

---

## 💾 Worker Local SQLite WAL

### Robin 패턴 구조

```mermaid
graph TB
    subgraph Worker["Worker Node"]
        direction TB
        
        subgraph LocalStorage["Local Storage (PVC 50GB)"]
            SQLite[SQLite WAL<br/>worker.db]
        end
        
        WorkerProcess[Worker Process<br/>Celery]
        
        WorkerProcess -->|1. Write| SQLite
    end
    
    subgraph Central["Central PostgreSQL"]
        TaskSchema[(tasks 스키마)]
    end
    
    SQLite -->|2. Batch Sync<br/>5분 주기| TaskSchema
    
    subgraph Recovery["복구 메커니즘"]
        WALCheck[WAL Checkpoint]
        Rollback[Rollback on Failure]
    end
    
    SQLite -.->|장애 시| WALCheck
    WALCheck -.->|복구| Rollback
    
    style Worker fill:#16a085,stroke:#117a65,stroke-width:3px,color:#fff
    style LocalStorage fill:#27ae60,stroke:#1e8449,stroke-width:2px,color:#fff
    style SQLite fill:#2ecc71,stroke:#28b463,stroke-width:2px,color:#000
    style WorkerProcess fill:#1abc9c,stroke:#17a589,stroke-width:2px,color:#fff
    
    style Central fill:#1a5490,stroke:#0d2950,stroke-width:3px,color:#fff
    style TaskSchema fill:#3498db,stroke:#2874a6,stroke-width:2px,color:#fff
    
    style Recovery fill:#e74c3c,stroke:#c0392b,stroke-width:2px,color:#fff
    style WALCheck fill:#ec7063,stroke:#e74c3c,stroke-width:2px,color:#fff
    style Rollback fill:#ec7063,stroke:#e74c3c,stroke-width:2px,color:#fff
```

### SQLite 스키마 (로컬)

```sql
-- Worker Local SQLite (worker.db)

CREATE TABLE local_tasks (
    id TEXT PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    task_name TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,  -- JSON
    error TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    synced_to_pg INTEGER DEFAULT 0  -- 0: not synced, 1: synced
);

CREATE INDEX idx_local_not_synced ON local_tasks(synced_to_pg) 
WHERE synced_to_pg = 0;

CREATE INDEX idx_local_completed ON local_tasks(completed_at) 
WHERE completed_at IS NOT NULL;
```

---

## 🔄 데이터 흐름

### API 요청 흐름

```mermaid
sequenceDiagram
    participant Client
    participant API as API Service
    participant PG as PostgreSQL<br/>(해당 스키마)
    
    Client->>API: HTTP Request
    
    Note over API: 자신의 스키마만 접근
    API->>PG: SELECT FROM [스키마].[테이블]
    PG-->>API: Result
    
    alt 데이터 수정
        API->>PG: INSERT/UPDATE/DELETE
        PG-->>API: Success
    end
    
    API-->>Client: HTTP Response
    
    Note over API,PG: ✅ 스키마 격리<br/>다른 스키마 접근 불가
```

### Worker 동기화 흐름

```mermaid
sequenceDiagram
    participant Worker as Worker Process
    participant SQLite as Local SQLite
    participant Sync as Sync Process
    participant PG as PostgreSQL<br/>(tasks 스키마)
    
    Note over Worker: 작업 시작
    Worker->>SQLite: INSERT task (status=pending)
    
    Note over Worker: 작업 수행
    Worker->>Worker: Process Task
    
    alt 성공
        Worker->>SQLite: UPDATE (status=success)
    else 실패
        Worker->>SQLite: UPDATE (status=failure)
    end
    
    Note over Sync: 5분마다 실행
    Sync->>SQLite: SELECT WHERE synced_to_pg=0
    SQLite-->>Sync: Unsynced Tasks
    
    loop 배치 동기화
        Sync->>PG: INSERT INTO tasks.task_results
        PG-->>Sync: Success
        Sync->>SQLite: UPDATE synced_to_pg=1
    end
    
    Note over Sync,PG: ✅ 네트워크 장애에도<br/>로컬 작업 가능
```

---

## 📊 스키마 접근 권한

### Role 기반 권한 분리

```sql
-- API 서비스별 Role 생성
CREATE ROLE api_auth_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_users_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_locations_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_waste_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_recycle_role LOGIN PASSWORD 'secure_password';
CREATE ROLE api_chat_role LOGIN PASSWORD 'secure_password';
CREATE ROLE worker_role LOGIN PASSWORD 'secure_password';

-- 스키마 권한 부여
GRANT ALL ON SCHEMA auth TO api_auth_role;
GRANT ALL ON SCHEMA users TO api_users_role;
GRANT ALL ON SCHEMA locations TO api_locations_role;
GRANT ALL ON SCHEMA waste TO api_waste_role;
GRANT ALL ON SCHEMA recycle_info TO api_recycle_role;
GRANT ALL ON SCHEMA chat_llm TO api_chat_role;
GRANT ALL ON SCHEMA tasks TO worker_role;

-- 테이블 권한
GRANT ALL ON ALL TABLES IN SCHEMA auth TO api_auth_role;
GRANT ALL ON ALL TABLES IN SCHEMA users TO api_users_role;
-- ... (나머지 동일)

-- 시퀀스 권한
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO api_auth_role;
-- ... (나머지 동일)
```

### 연결 문자열

```yaml
# API 서비스 환경 변수
API_AUTH_DB_URL: "postgresql://api_auth_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=auth"
API_USERS_DB_URL: "postgresql://api_users_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=users"
API_LOCATIONS_DB_URL: "postgresql://api_locations_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=locations"
API_WASTE_DB_URL: "postgresql://api_waste_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=waste"
API_RECYCLE_DB_URL: "postgresql://api_recycle_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=recycle_info"
API_CHAT_DB_URL: "postgresql://api_chat_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=chat_llm"

# Worker 서비스
WORKER_DB_URL: "postgresql://worker_role:password@k8s-postgresql:5432/ecoeco?options=-c%20search_path=tasks"
```

---

## 🔒 보안 고려사항

### 스키마 격리
- ✅ 각 API는 자신의 스키마만 접근 가능
- ✅ 크로스 스키마 쿼리 방지 (search_path 설정)
- ✅ Role 기반 권한 관리

### 데이터 보호
- ✅ 비밀번호 해시 저장 (bcrypt)
- ✅ JWT 토큰 기반 인증
- ✅ HTTPS 통신 (ALB SSL Termination)

### 백업 전략
- ✅ PostgreSQL 자동 백업 (pg_dump)
- ✅ Worker Local SQLite WAL (로컬 복구)
- ✅ S3 백업 (향후)

---

## 📚 관련 문서

- [서비스 아키텍처](SERVICE_ARCHITECTURE.md)
- [Worker WAL 구현 가이드](../guides/WORKER_WAL_IMPLEMENTATION.md)
- [최종 K8s 아키텍처](final-k8s-architecture.md)

---

**최종 업데이트**: 2025-11-07  
**아키텍처 버전**: 3.0 (13-Node + Worker Local SQLite WAL)  
**앱 이름**: Eco² (이코에코)  
**패턴**: Database per Service (Schema 분리) + Robin (Worker WAL)

