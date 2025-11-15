# 이코에코 GitOps 파이프라인 다이어그램

**문서 버전**: v1.0.0  
**최종 업데이트**: 2025-11-12  
**작성자**: SeSACTHON 2025

---

## 🚀 완전한 GitOps 파이프라인 플로우

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a', 'background':'#1a1a1a', 'mainBkg':'#1a1a1a', 'secondBkg':'#2d2d2d', 'tertiaryBkg':'#3d3d3d', 'edgeLabelBackground':'#1a1a1a', 'clusterBkg':'#2d2d2d', 'clusterBorder':'#555', 'titleColor':'#fff', 'nodeBorder':'#555', 'nodeTextColor':'#fff'}}}%%
graph TD
    subgraph Developer["👨‍💻 개발자"]
        DEV1["코드 작성<br/>services/auth/main.py"]
        DEV2["Manifest 수정<br/>k8s/overlays/auth/"]
    end
    
    subgraph GitHub["🔄 GitHub Repository"]
        GIT1["Git Push<br/>main branch"]
        GIT2["Terraform PR<br/>atlantis apply"]
    end
    
    subgraph CI["🔨 CI Pipeline (GitHub Actions)"]
        CI1["코드 변경 감지<br/>services/**"]
        CI2["Docker Build<br/>ghcr.io/sesacthon/auth:latest"]
        CI3["Image Push<br/>GitHub Container Registry"]
    end
    
    subgraph CD["🚀 CD Pipeline (ArgoCD + Kustomize)"]
        CD1["Git 폴링<br/>3분 간격"]
        CD2["Kustomize Build<br/>kubectl kustomize k8s/overlays/auth/"]
        CD3["Manifest Render<br/>base + overlay"]
        CD4["Diff Detection<br/>Compare with Cluster"]
        CD5["Auto Sync<br/>kubectl apply"]
        CD6["Health Check<br/>Pod Ready"]
    end
    
    subgraph K8s["☸️ Kubernetes Cluster (14 Nodes)"]
        K1["Rolling Update<br/>auth-api Deployment"]
        K2["Pod Creation<br/>auth-api-xxx"]
        K3["Service Ready<br/>NodePort 30000"]
    end
    
    subgraph Infra["🏗️ Infrastructure Layer (Atlantis)"]
        INF1["Terraform Plan<br/>PR Comment"]
        INF2["Terraform Apply<br/>EC2, VPC, IAM"]
        INF3["AWS Resources<br/>Infrastructure"]
    end
    
    subgraph Monitor["📊 Monitoring"]
        MON1["Prometheus<br/>Metrics Collection"]
        MON2["Grafana<br/>Dashboard"]
        MON3["Alertmanager<br/>26+ Rules"]
    end
    
    DEV1 --> GIT1
    DEV2 --> GIT1
    GIT1 --> CI1
    CI1 --> CI2
    CI2 --> CI3
    CI3 --> CD1
    
    GIT1 --> CD1
    CD1 --> CD2
    CD2 --> CD3
    CD3 --> CD4
    CD4 --> CD5
    CD5 --> CD6
    
    CD6 --> K1
    K1 --> K2
    K2 --> K3
    
    GIT2 --> INF1
    INF1 --> INF2
    INF2 --> INF3
    
    K3 --> MON1
    MON1 --> MON2
    MON1 --> MON3
    
    style Developer fill:#0e7490,stroke:#fff,stroke-width:2px,color:#fff
    style GitHub fill:#2d2d2d,stroke:#fff,stroke-width:2px,color:#fff
    style CI fill:#166534,stroke:#fff,stroke-width:2px,color:#fff
    style CD fill:#b91c1c,stroke:#fff,stroke-width:2px,color:#fff
    style K8s fill:#1e3a8a,stroke:#fff,stroke-width:2px,color:#fff
    style Infra fill:#78350f,stroke:#fff,stroke-width:2px,color:#fff
    style Monitor fill:#581c87,stroke:#fff,stroke-width:2px,color:#fff
    
    style DEV1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEV2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style GIT1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style GIT2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CI1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CI2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CI3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD4 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD5 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style CD6 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style K1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style K2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style K3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style INF1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style INF2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style INF3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style MON1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style MON2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style MON3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 🎯 4-Layer GitOps 아키텍처

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a', 'background':'#1a1a1a', 'mainBkg':'#1a1a1a', 'secondBkg':'#2d2d2d'}}}%%
graph TB
    subgraph Layer3["Layer 3: Application Development"]
        L3A["🎯 개발자<br/>services/auth/main.py"]
        L3B["🔨 GitHub Actions<br/>Build & Push Image"]
        L3C["📦 GHCR<br/>ghcr.io/sesacthon/auth:latest"]
    end
    
    subgraph Layer2["Layer 2: GitOps CD (ArgoCD + Kustomize)"]
        L2A["🚀 ApplicationSet<br/>7개 API 자동 생성"]
        L2B["📁 Kustomize Overlays<br/>k8s/overlays/auth/"]
        L2C["⏱️ Auto-Sync<br/>3분 간격 폴링"]
        L2D["☸️ kubectl apply<br/>Rolling Update"]
    end
    
    subgraph Layer1["Layer 1: Cluster Configuration (Ansible)"]
        L1A["⚙️ Kubeadm Init<br/>클러스터 초기화"]
        L1B["🔧 Calico CNI<br/>Network Policy"]
        L1C["🏷️ Node Labels<br/>domain=auth"]
        L1D["📦 System Components<br/>CoreDNS, CSI"]
    end
    
    subgraph Layer0["Layer 0: Infrastructure (Atlantis + Terraform)"]
        L0A["☁️ AWS Resources<br/>14 EC2 Instances"]
        L0B["🌐 VPC + Subnets<br/>Public/Private"]
        L0C["⚖️ ALB + ACM<br/>HTTPS Ingress"]
        L0D["🔐 Security Groups<br/>IAM Roles"]
    end
    
    L3A --> L3B
    L3B --> L3C
    L3C --> L2A
    
    L2A --> L2B
    L2B --> L2C
    L2C --> L2D
    
    L2D --> L1A
    L1A --> L1B
    L1B --> L1C
    L1C --> L1D
    
    L1D --> L0A
    L0A --> L0B
    L0B --> L0C
    L0C --> L0D
    
    style Layer3 fill:#0e7490,stroke:#fff,stroke-width:3px,color:#fff
    style Layer2 fill:#b91c1c,stroke:#fff,stroke-width:3px,color:#fff
    style Layer1 fill:#166534,stroke:#fff,stroke-width:3px,color:#fff
    style Layer0 fill:#78350f,stroke:#fff,stroke-width:3px,color:#fff
    
    style L3A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L3B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L3C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L2A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L2B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L2C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L2D fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L1A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L1B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L1C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L1D fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L0A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L0B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L0C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style L0D fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 🔄 ApplicationSet 배포 플로우

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a'}}}%%
graph LR
    subgraph ArgoCD["🚀 ArgoCD ApplicationSet"]
        AS["ApplicationSet<br/>ecoeco-api-services-kustomize"]
    end
    
    subgraph Phase1["Phase 1 APIs"]
        APP1["ecoeco-api-auth<br/>Wave 1"]
        APP2["ecoeco-api-my<br/>Wave 1"]
        APP3["ecoeco-api-scan<br/>Wave 1"]
    end
    
    subgraph Phase2["Phase 2 APIs"]
        APP4["ecoeco-api-character<br/>Wave 2"]
        APP5["ecoeco-api-location<br/>Wave 2"]
    end
    
    subgraph Phase3["Phase 3 APIs"]
        APP6["ecoeco-api-info<br/>Wave 3"]
        APP7["ecoeco-api-chat<br/>Wave 3"]
    end
    
    subgraph K8s["☸️ Kubernetes Cluster"]
        NS["Namespace: api"]
        DEP1["auth-api Deployment"]
        DEP2["my-api Deployment"]
        DEP3["scan-api Deployment"]
        DEP4["character-api Deployment"]
        DEP5["location-api Deployment"]
        DEP6["info-api Deployment"]
        DEP7["chat-api Deployment"]
    end
    
    AS --> APP1
    AS --> APP2
    AS --> APP3
    AS --> APP4
    AS --> APP5
    AS --> APP6
    AS --> APP7
    
    APP1 --> DEP1
    APP2 --> DEP2
    APP3 --> DEP3
    APP4 --> DEP4
    APP5 --> DEP5
    APP6 --> DEP6
    APP7 --> DEP7
    
    DEP1 --> NS
    DEP2 --> NS
    DEP3 --> NS
    DEP4 --> NS
    DEP5 --> NS
    DEP6 --> NS
    DEP7 --> NS
    
    style ArgoCD fill:#b91c1c,stroke:#fff,stroke-width:3px,color:#fff
    style Phase1 fill:#0e7490,stroke:#fff,stroke-width:2px,color:#fff
    style Phase2 fill:#0369a1,stroke:#fff,stroke-width:2px,color:#fff
    style Phase3 fill:#075985,stroke:#fff,stroke-width:2px,color:#fff
    style K8s fill:#1e3a8a,stroke:#fff,stroke-width:3px,color:#fff
    
    style AS fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP4 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP5 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP6 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style APP7 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style NS fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP4 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP5 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP6 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style DEP7 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 📊 Kustomize 구조

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a'}}}%%
graph TD
    subgraph Git["📁 Git Repository: k8s/"]
        BASE["base/<br/>공통 템플릿"]
        OVERLAY["overlays/<br/>서비스별 커스터마이징"]
    end
    
    subgraph BaseResources["Base Resources"]
        B1["deployment.yaml<br/>공통 Deployment"]
        B2["service.yaml<br/>공통 Service"]
        B3["kustomization.yaml<br/>Base 정의"]
    end
    
    subgraph Overlays["Overlays (7개 API)"]
        O1["auth/<br/>인증/인가"]
        O2["my/<br/>마이페이지"]
        O3["scan/<br/>쓰레기 분류"]
        O4["character/<br/>캐릭터"]
        O5["location/<br/>위치 기반"]
        O6["info/<br/>재활용 정보"]
        O7["chat/<br/>AI 챗봇"]
    end
    
    subgraph AuthOverlay["auth/ 상세"]
        A1["kustomization.yaml<br/>namePrefix: auth-<br/>namespace: api"]
        A2["deployment-patch.yaml<br/>replicas: 2<br/>env: JWT_SECRET"]
        A3["images:<br/>ghcr.io/sesacthon/auth:latest"]
    end
    
    subgraph ArgoCD["🚀 ArgoCD"]
        ARG["ApplicationSet<br/>자동 렌더링"]
    end
    
    BASE --> B1
    BASE --> B2
    BASE --> B3
    
    OVERLAY --> O1
    OVERLAY --> O2
    OVERLAY --> O3
    OVERLAY --> O4
    OVERLAY --> O5
    OVERLAY --> O6
    OVERLAY --> O7
    
    O1 --> A1
    O1 --> A2
    O1 --> A3
    
    B1 --> A1
    B2 --> A1
    B3 --> A1
    
    A1 --> ARG
    A2 --> ARG
    A3 --> ARG
    
    style Git fill:#2d2d2d,stroke:#fff,stroke-width:3px,color:#fff
    style BaseResources fill:#166534,stroke:#fff,stroke-width:2px,color:#fff
    style Overlays fill:#0e7490,stroke:#fff,stroke-width:2px,color:#fff
    style AuthOverlay fill:#b91c1c,stroke:#fff,stroke-width:2px,color:#fff
    style ArgoCD fill:#78350f,stroke:#fff,stroke-width:3px,color:#fff
    
    style BASE fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style OVERLAY fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style B1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style B2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style B3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O4 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O5 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O6 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style O7 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style A1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style A2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style A3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style ARG fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 🌊 ArgoCD Sync Wave 배포 순서

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a'}}}%%
graph TD
    subgraph Wave0["Wave 0: Infrastructure"]
        W0A["PostgreSQL<br/>메인 DB"]
        W0B["Redis<br/>JWT Blacklist + Cache"]
        W0C["RabbitMQ<br/>메시지 큐"]
    end
    
    subgraph Wave1["Wave 1: Phase 1 APIs"]
        W1A["auth-api<br/>인증/인가"]
        W1B["my-api<br/>마이페이지"]
        W1C["scan-api<br/>쓰레기 분류"]
    end
    
    subgraph Wave2["Wave 2: Phase 2 APIs"]
        W2A["character-api<br/>캐릭터"]
        W2B["location-api<br/>위치 기반"]
    end
    
    subgraph Wave3["Wave 3: Phase 3 APIs"]
        W3A["info-api<br/>재활용 정보"]
        W3B["chat-api<br/>AI 챗봇"]
    end
    
    subgraph Wave4["Wave 4: Workers"]
        W4A["storage-worker<br/>S3 이미지 처리"]
        W4B["ai-worker<br/>AI 모델 추론"]
    end
    
    W0A --> W1A
    W0B --> W1A
    W0C --> W1A
    
    W0A --> W1B
    W0B --> W1B
    
    W0A --> W1C
    W0C --> W1C
    
    W1A --> W2A
    W1A --> W2B
    
    W1A --> W3A
    W1A --> W3B
    
    W1C --> W4A
    W1C --> W4B
    
    style Wave0 fill:#78350f,stroke:#fff,stroke-width:3px,color:#fff
    style Wave1 fill:#0e7490,stroke:#fff,stroke-width:3px,color:#fff
    style Wave2 fill:#0369a1,stroke:#fff,stroke-width:3px,color:#fff
    style Wave3 fill:#075985,stroke:#fff,stroke-width:3px,color:#fff
    style Wave4 fill:#166534,stroke:#fff,stroke-width:3px,color:#fff
    
    style W0A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W0B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W0C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W1A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W1B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W1C fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W2A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W2B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W3A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W3B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W4A fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style W4B fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 🔄 변경 시나리오: Auth API 업데이트

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a'}}}%%
sequenceDiagram
    participant Dev as 👨‍💻 개발자
    participant Git as 📁 GitHub
    participant CI as 🔨 GitHub Actions
    participant GHCR as 📦 GHCR
    participant ArgoCD as 🚀 ArgoCD
    participant K8s as ☸️ Kubernetes
    participant Monitor as 📊 Prometheus
    
    Dev->>Git: 1. git push<br/>services/auth/main.py
    Git->>CI: 2. Webhook Trigger<br/>workflow: api-build.yml
    CI->>CI: 3. Docker Build<br/>FROM python:3.11
    CI->>GHCR: 4. Image Push<br/>ghcr.io/sesacthon/auth:latest
    GHCR->>ArgoCD: 5. Image Updated
    
    Dev->>Git: 6. git push<br/>k8s/overlays/auth/deployment-patch.yaml
    Git->>ArgoCD: 7. Git Poll (3분)<br/>New Commit Detected
    ArgoCD->>ArgoCD: 8. Kustomize Build<br/>kubectl kustomize k8s/overlays/auth/
    ArgoCD->>ArgoCD: 9. Diff Detection<br/>Compare Manifests
    ArgoCD->>K8s: 10. kubectl apply<br/>Deployment: auth-api
    K8s->>K8s: 11. Rolling Update<br/>Old Pod → New Pod
    K8s->>ArgoCD: 12. Health Check<br/>Pod Ready: 2/2
    ArgoCD->>ArgoCD: 13. Sync Status<br/>✅ Synced + Healthy
    K8s->>Monitor: 14. Metrics Export<br/>deployment_status=1
    
    Note over Dev,Monitor: 전체 배포 소요 시간: 5-10분
```

---

## 🛠️ 도구별 역할 매트릭스

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#1a1a1a', 'primaryTextColor':'#fff', 'primaryBorderColor':'#444', 'lineColor':'#888', 'secondaryColor':'#2d2d2d', 'tertiaryColor':'#1a1a1a'}}}%%
graph TD
    subgraph Atlantis["🏗️ Atlantis + Terraform"]
        AT1["AWS 인프라 관리<br/>EC2, VPC, IAM"]
        AT2["PR 기반 워크플로우<br/>atlantis plan/apply"]
        AT3["실행 시점<br/>인프라 변경 시"]
    end
    
    subgraph Ansible["⚙️ Ansible"]
        AN1["K8s 클러스터 설정<br/>Kubeadm, CNI"]
        AN2["수동 실행<br/>ansible-playbook"]
        AN3["실행 시점<br/>클러스터 설정 변경 시"]
    end
    
    subgraph ArgoCD["🚀 ArgoCD + Kustomize"]
        AR1["K8s 리소스 배포<br/>Deployment, Service"]
        AR2["자동 실행<br/>Git Auto-Sync 3분"]
        AR3["실행 시점<br/>애플리케이션 배포 시"]
    end
    
    subgraph GHA["🔨 GitHub Actions"]
        GH1["CI/CD<br/>빌드, 테스트, 이미지"]
        GH2["자동 실행<br/>Git Push 이벤트"]
        GH3["실행 시점<br/>코드 변경 시"]
    end
    
    style Atlantis fill:#78350f,stroke:#fff,stroke-width:3px,color:#fff
    style Ansible fill:#166534,stroke:#fff,stroke-width:3px,color:#fff
    style ArgoCD fill:#b91c1c,stroke:#fff,stroke-width:3px,color:#fff
    style GHA fill:#0e7490,stroke:#fff,stroke-width:3px,color:#fff
    
    style AT1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AT2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AT3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AN1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AN2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AN3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AR1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AR2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style AR3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style GH1 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style GH2 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
    style GH3 fill:#334155,stroke:#64748b,stroke-width:2px,color:#fff
```

---

## 📚 참고 자료

| 문서 | 링크 |
|------|------|
| GitOps Pipeline (Kustomize) | [GITOPS_PIPELINE_KUSTOMIZE.md](../deployment/GITOPS_PIPELINE_KUSTOMIZE.md) |
| ArgoCD 접속 정보 | [ARGOCD_ACCESS.md](../deployment/ARGOCD_ACCESS.md) |
| GitOps Tooling Decision | [08-GITOPS_TOOLING_DECISION.md](./08-GITOPS_TOOLING_DECISION.md) |
| Service Architecture | [03-SERVICE_ARCHITECTURE.md](./03-SERVICE_ARCHITECTURE.md) |
| Cluster Validation Report | [CLUSTER_VALIDATION_REPORT.md](../validation/CLUSTER_VALIDATION_REPORT.md) |

---

## 🔑 핵심 포인트

### 1. **완전 자동화된 CD 파이프라인**
- Git Push → 3분 이내 자동 배포
- Manual approval 불필요
- Self-healing으로 Drift 자동 복구

### 2. **Kustomize 기반 Manifest 관리**
- 순수 YAML (템플릿 없음)
- Base + Overlays 구조
- Git diff 명확, 디버깅 용이

### 3. **ApplicationSet으로 멀티 서비스 관리**
- 7개 API를 하나의 ApplicationSet으로 관리
- Phase별 Sync Wave 제어
- 독립적인 배포 및 롤백

### 4. **4-Layer 분리 아키텍처**
- Layer 0: Infrastructure (Atlantis + Terraform)
- Layer 1: Cluster Configuration (Ansible)
- Layer 2: GitOps CD (ArgoCD + Kustomize)
- Layer 3: Application Development (GitHub Actions)

---

**Last Updated**: 2025-11-12  
**Version**: v0.8.0  
**Architecture**: 14-Node Self-Managed Kubernetes


