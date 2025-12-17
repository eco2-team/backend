# 이코에코 클러스터 네트워크 토폴로지

## 개요

이코에코 백엔드 클러스터의 네트워크 아키텍처입니다. Istio 서비스 메시 기반으로 구성되어 있으며, ext-authz를 통한 중앙집중식 인증/인가를 수행합니다.

---

## 전체 아키텍처

```mermaid
flowchart TB
    subgraph External["외부"]
        User["👤 User/Client"]
        Route53["Route 53<br/>(DNS)"]
        ALB["AWS ALB<br/>(HTTPS 443)"]
    end

    subgraph AWS_VPC["AWS VPC"]
        subgraph K8s["Kubernetes Cluster"]
            
            subgraph CP["Control Plane Layer"]
                subgraph PlatformCP["Platform CP"]
                    ArgoCD["ArgoCD"]
                    ALBC["AWS LB<br/>Controller"]
                    ExtDNS["ExternalDNS"]
                    ExtSecrets["External<br/>Secrets"]
                end
                
                subgraph IstioCP["Istio CP"]
                    Istiod["Istiod"]
                end
            end
            
            subgraph DP["Data Plane Layer"]
                subgraph Ingress["Ingress (istio-system)"]
                    IG["Istio Ingress Gateway<br/>(Envoy)"]
                    EF["EnvoyFilter<br/>(cookie→header)"]
                    VS["VirtualService<br/>Routing"]
                end
                
                subgraph AuthZ["AuthN/AuthZ (auth ns)"]
                    ExtAuthz["ext-authz<br/>(Go, gRPC:50051)"]
                end
                
                subgraph Services["Microservices (Envoy Sidecars)"]
                    Auth["auth-api<br/>:8000"]
                    My["my-api<br/>:8000"]
                    Scan["scan-api<br/>:8000"]
                    Character["character-api<br/>:8000"]
                    Location["location-api<br/>:8000"]
                    Image["image-api<br/>:8000"]
                    Chat["chat-api<br/>:8000"]
                end
            end
            
            subgraph Data["Data Infrastructure"]
                Redis[("Redis<br/>(cache/blacklist)")]
                PostgreSQL[("PostgreSQL<br/>(database)")]
            end
            
            subgraph Obs["Observability"]
                Prometheus["Prometheus"]
                Grafana["Grafana"]
            end
        end
    end

    %% External Flow
    User -->|HTTPS| Route53
    Route53 -->|Alias| ALB
    ALB -->|Forward| IG

    %% Control Plane
    ArgoCD -.->|Sync| K8s
    ALBC -.->|AWS API| ALB
    ExtDNS -.->|AWS API| Route53
    Istiod -.->|xDS| IG
    Istiod -.->|xDS| Services

    %% Data Plane Flow
    IG --> EF
    EF --> VS
    VS -->|AuthorizationPolicy| ExtAuthz
    ExtAuthz -->|Blacklist Check| Redis
    
    VS --> Auth
    VS --> My
    VS --> Scan
    VS --> Character
    VS --> Location
    VS --> Image
    VS --> Chat

    %% Data Access
    Auth --> PostgreSQL
    Auth --> Redis
    My --> PostgreSQL
    Scan --> PostgreSQL
    Character --> PostgreSQL
    Location --> PostgreSQL
    Image --> PostgreSQL
    Chat --> PostgreSQL

    %% Observability
    Prometheus -.->|Scrape| Services
    Prometheus -.->|Scrape| ExtAuthz
    Grafana -.->|Query| Prometheus

    classDef external fill:#f9f,stroke:#333,stroke-width:2px
    classDef cp fill:#bbf,stroke:#333,stroke-width:2px
    classDef dp fill:#bfb,stroke:#333,stroke-width:2px
    classDef data fill:#fbb,stroke:#333,stroke-width:2px
    classDef obs fill:#ffb,stroke:#333,stroke-width:2px
```

---

## AuthN/AuthZ 상세 흐름

```mermaid
sequenceDiagram
    autonumber
    participant Client as 👤 Client
    participant ALB as AWS ALB
    participant IG as Istio Gateway<br/>(Envoy)
    participant EF as EnvoyFilter<br/>(Lua)
    participant AP as AuthorizationPolicy
    participant EA as ext-authz<br/>(gRPC)
    participant Redis as Redis
    participant API as Backend API

    Client->>ALB: HTTPS Request<br/>(Cookie: s_access=<JWT>)
    ALB->>IG: Forward (HTTP)
    
    rect rgb(255, 240, 200)
        Note over EF: Cookie → Header 변환
        IG->>EF: Request with Cookie
        EF->>EF: Extract s_access cookie
        EF->>IG: Add Authorization: Bearer <JWT>
    end
    
    rect rgb(200, 255, 200)
        Note over AP,EA: ext-authz 검증
        IG->>AP: Check /api/v1/* path
        AP->>EA: gRPC Check Request
        EA->>EA: JWT Verify (HS256)
        EA->>Redis: IsBlacklisted(jti)?
        Redis-->>EA: false
        EA-->>AP: OK + Headers<br/>(x-user-id, x-auth-provider)
    end
    
    AP-->>IG: Inject Headers
    IG->>API: Request + x-user-id
    API-->>IG: Response
    IG-->>ALB: Response
    ALB-->>Client: HTTPS Response
```

---

## 네임스페이스 구조

```mermaid
flowchart LR
    subgraph istio-system["istio-system"]
        istiod["Istiod"]
        ig["Ingress Gateway"]
        gw["Gateway"]
        ap["AuthorizationPolicy"]
        ef["EnvoyFilter"]
    end

    subgraph auth["auth"]
        auth-api["auth-api"]
        ext-authz["ext-authz"]
    end

    subgraph my["my"]
        my-api["my-api"]
    end

    subgraph scan["scan"]
        scan-api["scan-api"]
    end

    subgraph character["character"]
        character-api["character-api"]
    end

    subgraph location["location"]
        location-api["location-api"]
    end

    subgraph image["image"]
        image-api["image-api"]
    end

    subgraph chat["chat"]
        chat-api["chat-api"]
    end

    subgraph redis["redis"]
        redis-server[("Redis")]
    end

    subgraph postgres["postgres"]
        pg-server[("PostgreSQL")]
    end

    subgraph prometheus["prometheus"]
        prom["Prometheus"]
    end

    subgraph grafana["grafana"]
        graf["Grafana"]
    end

    ig --> auth-api
    ig --> my-api
    ig --> scan-api
    ig --> character-api
    ig --> location-api
    ig --> image-api
    ig --> chat-api

    ap -.->|gRPC| ext-authz
    ext-authz --> redis-server

    auth-api --> pg-server
    auth-api --> redis-server
```

---

## 노드 배치 (EC2)

```mermaid
flowchart TB
    subgraph Master["k8s-master (t3.xlarge)"]
        CP["Control Plane<br/>+ Prometheus"]
    end

    subgraph API_Nodes["API Nodes"]
        subgraph auth_node["k8s-api-auth (t3.small)"]
            auth_pod["auth-api"]
            extauthz_pod["ext-authz"]
        end
        subgraph my_node["k8s-api-my (t3.small)"]
            my_pod["my-api"]
        end
        subgraph scan_node["k8s-api-scan (t3.medium)"]
            scan_pod["scan-api"]
        end
        subgraph char_node["k8s-api-character (t3.small)"]
            char_pod["character-api"]
        end
        subgraph loc_node["k8s-api-location (t3.small)"]
            loc_pod["location-api"]
        end
        subgraph img_node["k8s-api-image (t3.small)"]
            img_pod["image-api"]
        end
        subgraph chat_node["k8s-api-chat (t3.medium)"]
            chat_pod["chat-api"]
        end
    end

    subgraph Infra_Nodes["Infrastructure Nodes"]
        subgraph pg_node["k8s-postgresql (t3.large)"]
            pg["PostgreSQL"]
        end
        subgraph redis_node["k8s-redis (t3.medium)"]
            redis["Redis"]
        end
        subgraph mon_node["k8s-monitoring (t3.large)"]
            prom["Prometheus"]
            graf["Grafana"]
        end
        subgraph gw_node["k8s-ingress-gateway (t3.medium)"]
            istio_gw["Istio Gateway"]
        end
    end

    subgraph Worker_Nodes["Worker Nodes"]
        subgraph storage_node["k8s-worker-storage (t3.medium)"]
            celery_io["Celery (I/O)"]
        end
        subgraph ai_node["k8s-worker-ai (t3.medium)"]
            celery_net["Celery (Network)"]
        end
    end
```

---

## 주요 구성 요소

### Istio 리소스

| 리소스 | 이름 | 네임스페이스 | 역할 |
|--------|------|-------------|------|
| Gateway | eco2-gateway | istio-system | 외부 트래픽 진입점 |
| EnvoyFilter | cookie-to-header | istio-system | s_access 쿠키 → Authorization 헤더 |
| AuthorizationPolicy | ext-authz-policy | istio-system | /api/v1/* 경로 ext-authz 호출 |
| VirtualService | {domain}-vs | 각 ns | 경로 기반 라우팅 |

### ext-authz 설정

| 항목 | 값 |
|------|-----|
| Service | ext-authz.auth.svc.cluster.local |
| Port | 50051 (gRPC) |
| Timeout | 0.25s |
| failOpen | false |
| 검증 대상 헤더 | authorization, x-refresh-token, x-request-id |

### 우회 경로 (notPaths)

- OAuth: `/api/v1/auth/{kakao,google,naver}`, `/api/v1/auth/{provider}/callback`
- 토큰 갱신: `/api/v1/auth/refresh`
- 문서: `/api/v1/{service}/docs`, `/api/v1/{service}/openapi.json`
- 헬스체크: `/api/v1/{service}/{health,ready,metrics}`


