# 🏗️ 4-Tier 배포 아키텍처

> **Software Engineering Layered Architecture**  
> **4-Tier**: Control Plane → Data Plane → Message Queue → Storage  
> **날짜**: 2025-10-31

## 📋 목차

1. [4-Tier 정의](#4-tier-정의)
2. [전체 아키텍처](#전체-아키텍처)
3. [Tier별 상세](#tier별-상세)
4. [통신 흐름](#통신-흐름)
5. [확장 전략](#확장-전략)

---

## 🎯 4-Tier 정의

### Software Engineering Perspective

```
4-Tier Layered Architecture:

Tier 1: Control Plane (Orchestration Layer)
├─ 책임: Cluster Management, Scheduling, Monitoring
├─ 관심사: "어떻게 워크로드를 배치하고 관리할 것인가?"
└─ 구성: Kubernetes Control Plane + Observability

Tier 2: Data Plane (Business Logic Layer)
├─ 책임: Request Processing, Business Logic Execution
├─ 관심사: "비즈니스 요구사항을 어떻게 처리할 것인가?"
└─ 구성: Sync API + Async Workers (구현 세부사항)

Tier 3: Message Queue (Middleware Layer)
├─ 책임: Asynchronous Communication, Message Routing
├─ 관심사: "메시지를 어떻게 안전하게 전달할 것인가?"
└─ 구성: RabbitMQ HA Cluster

Tier 4: Persistence (Storage Layer)
├─ 책임: Data Persistence, Caching
├─ 관심사: "데이터를 어떻게 영속적으로 저장할 것인가?"
└─ 구성: PostgreSQL + Redis + Celery Beat

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
핵심:
✅ 물리적 노드 (4개) ≠ 논리적 Tier (4계층)
✅ Storage 노드 = Tier 3 (MQ) + Tier 4 (DB)
✅ Clean Architecture Principles
```

---

## 🌐 전체 아키텍처

### 4-Tier System Diagram

```mermaid
graph TB
    subgraph Internet["🌐 Internet"]
        Users["사용자<br/>Mobile App"]
    end
    
    subgraph AWS["☁️ AWS Services"]
        Route53["Route53<br/>DNS Management"]
        ALB["Application Load Balancer<br/>L7 Routing + SSL"]
        ACM["ACM<br/>*.growbin.app<br/>Auto-Renewal"]
        S3["S3<br/>prod-sesacthon-images<br/>Pre-signed URL"]
    end
    
    subgraph T1["🎛️ Tier 1: Control Plane"]
        direction TB
        API["kube-apiserver<br/>etcd"]
        Sched["scheduler<br/>controller-manager"]
        Monitor["Prometheus<br/>Grafana"]
        GitOps["ArgoCD<br/>GitOps CD"]
        
        API --- Sched
        Sched --- Monitor
        Monitor --- GitOps
    end
    
    subgraph T2["⚙️ Tier 2: Data Plane"]
        direction TB
        
        subgraph Sync["Sync API Worker-1"]
            Auth["auth-service x2<br/>OAuth JWT"]
            Users["users-service x1<br/>Profile History"]
            Loc["locations-service x1<br/>Bin Search"]
        end
        
        subgraph Async["Async Processing Worker-2"]
            Waste["waste-service x2<br/>Image API"]
            AIW["AI Workers x3<br/>GPT-4o Vision"]
            BatchW["Batch Workers x2<br/>Batch Jobs"]
        end
        
        Auth --- Users
        Users --- Loc
        Waste --- AIW
        AIW --- BatchW
    end
    
    subgraph T3["📬 Tier 3: Message Queue"]
        RMQ["RabbitMQ HA Cluster x3<br/><br/>q.ai Priority:10<br/>q.batch Priority:1<br/>q.api Priority:5<br/>q.sched Priority:3<br/>q.dlq DLX"]
    end
    
    subgraph T4["💾 Tier 4: Persistence"]
        DB["PostgreSQL<br/>StatefulSet<br/>50GB PVC<br/><br/>auth schema<br/>users schema<br/>waste schema"]
        RedisDB["Redis<br/>Deployment<br/><br/>Result Backend<br/>Cache 7-day TTL"]
        BeatSvc["Celery Beat x1<br/><br/>Scheduler<br/>DatabaseScheduler"]
        
        DB --- RedisDB
        RedisDB --- BeatSvc
    end
    
    Users --> Route53
    Route53 --> ALB
    ACM -.->|SSL Cert| ALB
    
    ALB --> Auth
    ALB --> Waste
    ALB --> GitOps
    ALB --> Monitor
    
    T1 -.->|orchestrate| T2
    
    Auth -->|publish| T3
    Waste -->|publish| T3
    T3 -->|consume| AIW
    T3 -->|consume| BatchW
    
    Auth <-->|CRUD| DB
    Users <-->|CRUD| DB
    Waste <-->|CRUD| DB
    
    Waste <-->|cache| RedisDB
    AIW <-->|result| RedisDB
    
    Waste --> S3
    AIW --> OpenAI["OpenAI<br/>GPT-4o Vision"]
    Loc --> Kakao["Kakao Map API"]
    Auth --> KakaoOAuth["Kakao OAuth"]
    
    style Internet fill:#0d47a1,color:#fff,stroke:#01579b,stroke-width:4px
    style AWS fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:3px
    style T1 fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:5px
    style T2 fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:5px
    style T3 fill:#f57c00,color:#fff,stroke:#e65100,stroke-width:5px
    style T4 fill:#c2185b,color:#fff,stroke:#880e4f,stroke-width:5px
    style Sync fill:#388e3c,color:#fff,stroke:#2e7d32,stroke-width:3px
    style Async fill:#43a047,color:#fff,stroke:#388e3c,stroke-width:3px
    style API fill:#42a5f5,color:#000,stroke:#1976d2,stroke-width:2px
    style Sched fill:#64b5f6,color:#000,stroke:#42a5f5,stroke-width:2px
    style Monitor fill:#90caf9,color:#000,stroke:#64b5f6,stroke-width:2px
    style GitOps fill:#bbdefb,color:#000,stroke:#90caf9,stroke-width:2px
    style Auth fill:#81c784,color:#000,stroke:#66bb6a,stroke-width:2px
    style Users fill:#a5d6a7,color:#000,stroke:#81c784,stroke-width:2px
    style Loc fill:#c8e6c9,color:#000,stroke:#a5d6a7,stroke-width:2px
    style Waste fill:#ffb74d,color:#000,stroke:#ffa726,stroke-width:2px
    style AIW fill:#ffcc80,color:#000,stroke:#ffb74d,stroke-width:2px
    style BatchW fill:#ffe0b2,color:#000,stroke:#ffcc80,stroke-width:2px
    style RMQ fill:#ff8a65,color:#000,stroke:#ff7043,stroke-width:2px
    style DB fill:#f48fb1,color:#000,stroke:#ec407a,stroke-width:2px
    style RedisDB fill:#f8bbd0,color:#000,stroke:#f48fb1,stroke-width:2px
    style BeatSvc fill:#fce4ec,color:#000,stroke:#f8bbd0,stroke-width:2px
```

---

## 📊 Tier별 상세

### Tier 1: Control Plane

**Physical:** Master (t3.large, 8GB, 80GB, $60/월)

```mermaid
graph TB
    subgraph CP["Control Plane Components"]
        API["kube-apiserver<br/>RESTful API<br/>6443"]
        ETCD["etcd<br/>Key-Value Store<br/>Cluster State"]
        Scheduler["kube-scheduler<br/>Pod Placement"]
        Controller["kube-controller-manager<br/>Control Loops"]
    end
    
    subgraph Observ["Observability"]
        Prom["Prometheus<br/>Metrics Collection"]
        Graf["Grafana<br/>Visualization"]
        Metrics["Metrics Server<br/>HPA Support"]
    end
    
    subgraph CD["Continuous Deployment"]
        ArgoCD["ArgoCD<br/>GitOps Engine<br/>Auto Sync"]
    end
    
    API --> ETCD
    API --> Scheduler
    API --> Controller
    Prom --> Graf
    
    style CP fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:3px
    style Observ fill:#1976d2,color:#fff,stroke:#1565c0,stroke-width:2px
    style CD fill:#2196f3,color:#fff,stroke:#1976d2,stroke-width:2px
    style API fill:#42a5f5,color:#000,stroke:#1976d2,stroke-width:2px
    style ETCD fill:#64b5f6,color:#000,stroke:#42a5f5,stroke-width:2px
    style Scheduler fill:#90caf9,color:#000,stroke:#64b5f6,stroke-width:2px
    style Controller fill:#bbdefb,color:#000,stroke:#90caf9,stroke-width:2px
```

### Tier 2: Data Plane

**Physical:** Worker-1 + Worker-2 (t3.medium ×2, 4GB ×2, $60/월)

```mermaid
graph TB
    subgraph DP["Data Plane Business Logic"]
        subgraph Sync["Sync API Worker-1 Reactor Pattern"]
            Auth["auth-service x2<br/>OAuth 2.0<br/>Kakao Google Naver<br/>JWT 발급 즉시 응답"]
            Users["users-service x1<br/>Profile Management<br/>History Query"]
            Loc["locations-service x1<br/>Kakao Map Search<br/>Bin Navigation"]
        end
        
        subgraph Async["Async Processing Worker-2 Task Queue"]
            Waste["waste-service x2<br/>Image Analysis API<br/>Job Creation"]
            AIWorker["AI Workers x3<br/>GPT-4o Vision<br/>Queue: q.ai<br/>gevent pool"]
            BatchWorker["Batch Workers x2<br/>Batch Jobs<br/>Queue: q.batch q.sched<br/>processes pool"]
        end
    end
    
    Auth -.->|same tier| Users
    Users -.->|same tier| Loc
    Waste -.->|same tier| AIWorker
    
    style DP fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:4px
    style Sync fill:#388e3c,color:#fff,stroke:#2e7d32,stroke-width:3px
    style Async fill:#43a047,color:#fff,stroke:#388e3c,stroke-width:3px
    style Auth fill:#81c784,color:#000,stroke:#66bb6a,stroke-width:2px
    style Users fill:#a5d6a7,color:#000,stroke:#81c784,stroke-width:2px
    style Loc fill:#c8e6c9,color:#000,stroke:#a5d6a7,stroke-width:2px
    style Waste fill:#ffb74d,color:#000,stroke:#ffa726,stroke-width:2px
    style AIWorker fill:#ffcc80,color:#000,stroke:#ffb74d,stroke-width:2px
    style BatchWorker fill:#ffe0b2,color:#000,stroke:#ffcc80,stroke-width:2px
```

### Tier 3: Message Queue (Middleware)

**Physical:** Storage 노드의 RabbitMQ

```mermaid
graph LR
    subgraph MQ["Message Queue Middleware"]
        Exchange["Topic Exchange<br/>tasks<br/><br/>Routing by Key"]
        
        Q1["q.ai<br/>Priority: 10<br/>TTL: 300s<br/>AI Vision"]
        Q2["q.batch<br/>Priority: 1<br/>TTL: 3600s<br/>Batch Jobs"]
        Q3["q.api<br/>Priority: 5<br/>TTL: 300s<br/>External API"]
        Q4["q.sched<br/>Priority: 3<br/>Scheduled Jobs"]
        Q5["q.dlq<br/>Dead Letter<br/>Failed Messages"]
        
        DLX["DLX<br/>Direct Exchange"]
    end
    
    Exchange --> Q1
    Exchange --> Q2
    Exchange --> Q3
    Exchange --> Q4
    
    Q1 -.->|failure| DLX
    Q2 -.->|failure| DLX
    Q3 -.->|failure| DLX
    Q4 -.->|failure| DLX
    DLX --> Q5
    
    style MQ fill:#f57c00,color:#fff,stroke:#e65100,stroke-width:4px
    style Exchange fill:#ef6c00,color:#fff,stroke:#e65100,stroke-width:3px
    style Q1 fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:2px
    style Q2 fill:#5e35b1,color:#fff,stroke:#4527a0,stroke-width:2px
    style Q3 fill:#00838f,color:#fff,stroke:#006064,stroke-width:2px
    style Q4 fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:2px
    style Q5 fill:#b71c1c,color:#fff,stroke:#7f0000,stroke-width:3px
    style DLX fill:#c62828,color:#fff,stroke:#b71c1c,stroke-width:2px
```

### Tier 4: Persistence (Storage Layer)

**Physical:** Storage 노드의 Database + Cache

```mermaid
graph TB
    subgraph Storage["Persistence Storage Layer"]
        DB["PostgreSQL<br/>StatefulSet<br/><br/>ACID Transactions<br/>Relational Data<br/>50GB PVC"]
        
        Redis["Redis<br/>Deployment<br/><br/>Celery Result Backend<br/>Application Cache<br/>Session Store"]
        
        Beat["Celery Beat x1<br/><br/>Task Scheduler<br/>DatabaseScheduler<br/>Prevent Duplicate"]
    end
    
    DB -.->|schema for| Beat
    Redis -.->|backend for| Beat
    
    style Storage fill:#c2185b,color:#fff,stroke:#880e4f,stroke-width:4px
    style DB fill:#ec407a,color:#fff,stroke:#d81b60,stroke-width:2px
    style Redis fill:#f06292,color:#000,stroke:#ec407a,stroke-width:2px
    style Beat fill:#f48fb1,color:#000,stroke:#f06292,stroke-width:2px
```

---

## 🔄 통신 흐름

### Tier 간 Dependency

```mermaid
graph TB
    T1["Tier 1<br/>Control Plane<br/><br/>Orchestration"]
    T2["Tier 2<br/>Data Plane<br/><br/>Business Logic"]
    T3["Tier 3<br/>Message Queue<br/><br/>Middleware"]
    T4["Tier 4<br/>Persistence<br/><br/>Storage"]
    
    T1 -.->|orchestrate| T2
    T2 -->|publish/consume| T3
    T2 <-->|read/write| T4
    T3 -.->|metadata| T4
    
    style T1 fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:4px
    style T2 fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:4px
    style T3 fill:#f57c00,color:#fff,stroke:#e65100,stroke-width:4px
    style T4 fill:#c2185b,color:#fff,stroke:#880e4f,stroke-width:4px
```

### OAuth 로그인 흐름 (Tier 2 Sync)

```mermaid
sequenceDiagram
    actor User
    participant App
    participant ALB
    participant Auth as Tier 2 Sync<br/>auth-service
    participant Kakao as Kakao OAuth
    participant DB as Tier 4<br/>PostgreSQL
    participant Redis as Tier 4<br/>Redis
    
    User->>App: "카카오 로그인" 클릭
    App->>ALB: GET /api/v1/auth/login/kakao
    ALB->>Auth: 라우팅
    Auth->>App: OAuth URL
    
    App->>Kakao: Redirect OAuth
    User->>Kakao: 로그인 + 동의
    Kakao->>App: Callback code
    
    App->>Auth: POST /callback/kakao
    
    activate Auth
    Auth->>Kakao: Token 요청 0.5초
    Kakao-->>Auth: Access Token
    Auth->>Kakao: 프로필 요청 0.3초
    Kakao-->>Auth: User Info
    
    Auth->>DB: 사용자 생성/조회 0.1초
    Auth->>Auth: JWT 생성 0.05초
    Auth->>Redis: 세션 저장 0.05초
    deactivate Auth
    
    Auth-->>App: JWT Token
    Note over Auth: 총 ~1-2초<br/>동기 처리 완료
    
    App->>User: 로그인 완료
    
    Note over Tier 2 Sync: 사용자 대기<br/>즉시 응답 필요<br/>Queue 불필요
```

### 이미지 분석 흐름 (Tier 2 → 3 → 4)

```mermaid
sequenceDiagram
    participant API as Tier 2 Sync<br/>waste-service
    participant MQ as Tier 3<br/>RabbitMQ
    participant Worker as Tier 2 Async<br/>AI Worker
    participant DB as Tier 4<br/>PostgreSQL
    participant Cache as Tier 4<br/>Redis
    
    API->>API: Job ID 생성
    API->>MQ: Publish q.ai<br/>ai.analyze
    Note over MQ: Tier 3 책임:<br/>메시지 라우팅<br/>우선순위 관리<br/>Delivery Guarantee
    
    MQ->>Worker: Consume Priority 10
    Note over Worker: Tier 2 책임:<br/>Business Logic<br/>AI 분석 처리
    
    Worker->>Cache: 캐시 확인
    Note over Cache: Tier 4 책임:<br/>데이터 캐싱
    
    alt Cache Hit
        Cache-->>Worker: 결과 반환
    else Cache Miss
        Worker->>Worker: GPT-4o Vision API
        Worker->>DB: 결과 저장
        Note over DB: Tier 4 책임:<br/>데이터 영속성
        Worker->>Cache: 캐싱 7일
    end
    
    Worker->>MQ: ACK
```

---

## 📊 리소스 할당

### 물리적 노드 vs 논리적 Tier

```
Physical Topology (4 Nodes):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Master (t3.large, 8GB, 80GB, $60)
   └─ Tier 1: Control Plane

2. Worker-1 (t3.medium, 4GB, 40GB, $30)
   └─ Tier 2: Data Plane (Sync)

3. Worker-2 (t3.medium, 4GB, 40GB, $30)
   └─ Tier 2: Data Plane (Async)

4. Storage (t3.large, 8GB, 100GB, $60)
   ├─ Tier 3: Message Queue (RabbitMQ)
   └─ Tier 4: Persistence (PostgreSQL, Redis)

Logical Topology (4 Tiers):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tier 1: Control Plane
└─ Node: Master

Tier 2: Data Plane (Business Logic)
├─ Node: Worker-1 (Sync API)
└─ Node: Worker-2 (Async Processing)

Tier 3: Message Queue (Middleware)
└─ Node: Storage (RabbitMQ HA)

Tier 4: Persistence (Storage)
└─ Node: Storage (PostgreSQL, Redis, Beat)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
핵심: 4 Nodes, 4 Tiers, 논리적 분리
```

---

## 🎯 확장 전략

### Tier별 독립 확장

```
Tier 2 (Data Plane) 확장:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
시나리오 1: API 트래픽 증가
└─ Worker-1 노드 추가
└─ HPA: auth-service 2 → 5
└─ 비용: +$30/월

시나리오 2: AI 분석 증가
└─ Worker-2 노드 추가
└─ HPA: AI Workers 3 → 10
└─ 비용: +$30/월

Tier 3 (Message Queue) 확장:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
시나리오: 메시지 처리량 증가
└─ RabbitMQ 노드 추가 (3 → 5)
└─ Queue Sharding (q.ai.0, q.ai.1, ...)
└─ 비용: Storage 노드 확장에 포함

Tier 4 (Persistence) 확장:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
시나리오 1: DB 읽기 증가
└─ PostgreSQL 읽기 복제본
└─ 비용: +$60/월

시나리오 2: Cache 증가
└─ Redis Cluster (3-node)
└─ 비용: Storage 노드 확장에 포함
```

---

## 📚 관련 문서

- [DEPLOYMENT_GUIDE](../../DEPLOYMENT_GUIDE.md) - 배포 자동화
- [Task Queue 설계](task-queue-design.md) - Tier 3 상세
- [VPC 네트워크](../infrastructure/vpc-network-design.md)
- [Self-Managed K8s](why-self-managed-k8s.md)

---

**작성일**: 2025-10-31  
**아키텍처**: 4-Tier Layered Architecture  
**총 비용**: $185/월  
**노드**: 4개 (물리적)  
**Tier**: 4계층 (논리적)  
**원칙**: Separation of Concerns + Clean Architecture
