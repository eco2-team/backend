## ALB Controller 구성 흐름

```mermaid
graph TD
    subgraph "Kubernetes Cluster"
        Ingress[["Ingress<br/>domain-ingress"]]:::ing
        ALBCtrl{{"AWS Load Balancer Controller"}}:::ctrl
    end

    subgraph "AWS"
        AWSAPI[(AWS ELB/TargetGroup API)]:::aws
        ALB["ALB (HTTPS Listener)"]:::alb
        TG["Target Group<br/>instance 모드"]:::tg
    end

    Ingress -->|매니페스트 감시| ALBCtrl
    ALBCtrl -->|IAM Role로 API 호출<br/>(Create/Update Listener/Rules/TG)| AWSAPI
    AWSAPI -->|리스너/규칙 생성| ALB
    AWSAPI -->|노드 IP:NodePort 등록| TG
    ALBCtrl -->|상태 확인| AWSAPI

    classDef ing fill:#FEF3C7,stroke:#D97706,color:#111;
    classDef ctrl fill:#FCD34D,stroke:#B45309,color:#111;
    classDef aws fill:#DBEAFE,stroke:#1D4ED8,color:#111;
    classDef alb fill:#FECACA,stroke:#B91C1C,color:#111;
    classDef tg fill:#FBCFE8,stroke:#BE185D,color:#111;
```

## 실시간 트래픽 경로

```mermaid
graph TD
    ClientLeft["사용자(Client)"]:::client
    ClientRight["사용자(Client)"]:::client

    ClientLeft -->|HTTPS 443| ALBData["ALB"]:::alb
    ALBData -->|라우팅| TGData["Target Group"]:::tg
    TGData -->|NodePort 31666| IngressData["Ingress<br/>domain-ingress"]:::ing

    IngressData --> Node1["노드 A<br/>k8s-api-domain"]:::node
    Node1 -->|ClusterIP 8000| Pod1["domain-api Pod #1"]:::pod
    Pod1 -->|응답| ClientLeft

    IngressData --> Node2["노드 B<br/>k8s-api-domain-2"]:::node
    Node2 -->|ClusterIP 8000| Pod2["domain-api Pod #2"]:::pod
    Pod2 -->|응답| ClientRight
    classDef client fill:#BFDBFE,stroke:#1D4ED8,color:#111;
    classDef alb fill:#FECACA,stroke:#B91C1C,color:#111;
    classDef tg fill:#FBCFE8,stroke:#BE185D,color:#111;
    classDef ing fill:#FEF3C7,stroke:#D97706,color:#111;
    classDef node fill:#C7D2FE,stroke:#4338CA,color:#111;
    classDef pod fill:#A7F3D0,stroke:#047857,color:#111;
```

