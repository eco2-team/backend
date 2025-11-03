# 인프라 배포 프로세스 다이어그램

## 현재 배포 프로세스 흐름

### 전체 배포 플로우

```mermaid
graph TB
    Start([시작: auto-rebuild.sh]) --> Step1[1. destroy-with-cleanup.sh]
    
    Step1 --> K8sCleanup[Kubernetes 리소스 정리]
    K8sCleanup --> IngressDel[Ingress 삭제]
    IngressDel --> PVCDel[PVC 삭제]
    PVCDel --> RabbitMQDel[RabbitMQ CR 삭제<br/>kubectl delete rabbitmqcluster]
    RabbitMQDel --> HelmDel[Helm Release 삭제<br/>Prometheus, ArgoCD 등]
    HelmDel --> AWSCleanup[AWS 리소스 정리<br/>EBS 볼륨, 보안 그룹]
    AWSCleanup --> TerraformDestroy[Terraform Destroy]
    
    TerraformDestroy --> Step2[2. rebuild-cluster.sh]
    
    Step2 --> TFInit[Terraform Init]
    TFInit --> TFDestroy[Terraform Destroy<br/>기존 인프라 삭제]
    TFDestroy --> TFApply[Terraform Apply<br/>인프라 생성]
    
    TFApply --> EC2[EC2 인스턴스 생성<br/>Master, Worker-1, Worker-2, Storage]
    EC2 --> VPC[VPC/서브넷 생성]
    VPC --> S3[S3 버킷 생성]
    S3 --> IAM[IAM 역할 생성]
    IAM --> ACM[ACM 인증서]
    ACM --> EIP[Elastic IP 할당]
    
    EIP --> InventoryGen[Ansible Inventory 생성]
    InventoryGen --> AnsibleExec[3. Ansible site.yml 실행]
    
    AnsibleExec --> OSConfig[OS 설정<br/>Swap 비활성화, 커널 파라미터]
    OSConfig --> Docker[Docker/containerd 설치]
    Docker --> K8sInst[Kubernetes 패키지 설치]
    K8sInst --> MasterInit[Master 초기화<br/>kubeadm init]
    MasterInit --> WorkerJoin[Worker 조인<br/>kubeadm join]
    WorkerJoin --> CNI[CNI 설치<br/>Calico]
    CNI --> Labels[노드 레이블 지정<br/>workload=storage 등]
    
    Labels --> Addons[Add-ons 설치]
    Addons --> CertManager[Cert-manager 설치]
    CertManager --> EBSDriver[EBS CSI Driver 설치]
    EBSDriver --> ALBController[AWS Load Balancer Controller]
    
    ALBController --> ArgoCD[ArgoCD 설치<br/>Helm]
    ArgoCD --> Monitoring[Prometheus 설치<br/>Helm]
    Monitoring --> RabbitMQ[RabbitMQ 설치<br/>Operator + CR]
    
    RabbitMQ --> RabbitMQOp[RabbitMQ Operator 설치<br/>kubectl apply]
    RabbitMQOp --> RabbitMQCR[RabbitmqCluster CR 생성<br/>kubectl apply]
    RabbitMQCR --> RabbitMQPod[RabbitMQ Pod 생성<br/>Operator 자동 관리]
    
    RabbitMQPod --> Redis[Redis 설치<br/>kubectl apply]
    Redis --> Ingress[Ingress 리소스 생성]
    Ingress --> ETCDBackup[etcd 백업 설정]
    ETCDBackup --> End([완료])
    
    style Start fill:#2196F3,stroke:#1565C0,stroke-width:2px,color:#ffffff
    style Step1 fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style Step2 fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style AnsibleExec fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#ffffff
    style RabbitMQOp fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style RabbitMQCR fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style RabbitMQPod fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style End fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#ffffff
```

## 상세 배포 단계

### Phase 1: 리소스 정리 (destroy-with-cleanup.sh)

```mermaid
sequenceDiagram
    participant User
    participant Script as destroy-with-cleanup.sh
    participant K8s as Kubernetes API
    participant AWS as AWS API
    participant TF as Terraform
    
    User->>Script: 실행
    Script->>K8s: kubectl delete ingress --all
    Script->>K8s: kubectl delete pvc --all
    Script->>K8s: kubectl delete rabbitmqcluster
    Script->>K8s: helm uninstall (Prometheus, ArgoCD)
    Script->>AWS: EBS 볼륨 삭제
    Script->>AWS: 보안 그룹 삭제
    Script->>TF: terraform destroy
```

### Phase 2: 인프라 생성 (rebuild-cluster.sh → Terraform)

```mermaid
graph LR
    A[Terraform Init] --> B[Terraform Destroy<br/>기존 삭제]
    B --> C[Terraform Apply<br/>인프라 생성]
    C --> D[EC2 인스턴스<br/>Master, Workers, Storage]
    C --> E[VPC/Subnet/IGW]
    C --> F[S3 버킷]
    C --> G[IAM 역할]
    C --> H[ACM 인증서]
    C --> I[Elastic IP]
    
    D --> J[Ansible Inventory 생성]
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
```

### Phase 3: Kubernetes 클러스터 구축 (Ansible)

```mermaid
graph LR
    subgraph SG1 ["1. 기반 설정"]
        direction LR
        A[OS 설정] --> B[Container Runtime] --> C[Kubernetes 패키지]
    end
    
    subgraph SG2 ["2. 클러스터 구성"]
        direction LR
        D[Master 초기화] --> E[Worker 조인] --> F[CNI 설치] --> G[노드 레이블]
    end
    
    subgraph SG3 ["3. 인프라 Add-ons"]
        direction LR
        H1[Cert-manager] & H2[EBS CSI Driver] & H3[ALB Controller]
    end
    
    subgraph SG4 ["4. 애플리케이션 Stack"]
        direction LR
        I[ArgoCD] & J[Prometheus] & K1[RabbitMQ Op] & K2[RabbitMQ CR] & K3[RabbitMQ Pod] & L[Redis]
        K1 --> K2 --> K3
    end
    
    C --> D
    G --> H1
    G --> H2
    G --> H3
    H1 --> I
    H2 --> J
    H3 --> K1
    H3 --> L
    
    style A fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#ffffff
    style B fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#ffffff
    style C fill:#4CAF50,stroke:#2E7D32,stroke-width:2px,color:#ffffff
    style D fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style E fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style F fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style G fill:#FF9800,stroke:#E65100,stroke-width:2px,color:#ffffff
    style H1 fill:#2196F3,stroke:#1565C0,stroke-width:2px,color:#ffffff
    style H2 fill:#2196F3,stroke:#1565C0,stroke-width:2px,color:#ffffff
    style H3 fill:#2196F3,stroke:#1565C0,stroke-width:2px,color:#ffffff
    style I fill:#9C27B0,stroke:#6A1B9A,stroke-width:2px,color:#ffffff
    style J fill:#9C27B0,stroke:#6A1B9A,stroke-width:2px,color:#ffffff
    style K1 fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style K2 fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style K3 fill:#FFC107,stroke:#F57C00,stroke-width:2px,color:#000000
    style L fill:#9C27B0,stroke:#6A1B9A,stroke-width:2px,color:#ffffff
```

## RabbitMQ 배포 상세 (순수 Operator 방식)

```mermaid
sequenceDiagram
    participant Ansible
    participant K8s as Kubernetes API
    participant Operator as RabbitMQ Operator
    participant Pod as RabbitMQ Pod
    
    Ansible->>K8s: kubectl apply (Operator YAML)
    Note over K8s: CRD 자동 생성<br/>rabbitmqclusters.rabbitmq.com
    
    K8s->>Operator: Operator Deployment 생성
    Operator->>Operator: Operator Pod 실행
    
    Ansible->>K8s: kubectl apply (RabbitmqCluster CR)
    Note over K8s: Operator가 감지
    
    Operator->>K8s: StatefulSet 생성
    Operator->>K8s: Service 생성
    Operator->>K8s: ConfigMap 생성
    Operator->>K8s: Secret 참조
    
    K8s->>Pod: Pod 생성 및 스케줄링
    Pod->>Pod: RabbitMQ 서버 시작
    Pod->>Operator: 상태 업데이트
    Operator->>K8s: RabbitmqCluster.status 업데이트
    
    Note over Ansible,Pod: Day-2 운영 (확장, 업그레이드 등)은<br/>Operator가 자동 관리
```

## 인프라 구성 요소

### Terraform 관리 리소스

```mermaid
graph TB
    A[Terraform] --> B[Compute]
    A --> C[Network]
    A --> D[Storage]
    A --> E[Security]
    A --> F[DNS]
    
    B --> B1[EC2: Master t3.large]
    B --> B2[EC2: Worker-1 t3.medium]
    B --> B3[EC2: Worker-2 t3.medium]
    B --> B4[EC2: Storage t3.large]
    
    C --> C1[VPC]
    C --> C2[Subnets 3개]
    C --> C3[Internet Gateway]
    C --> C4[Route Tables]
    
    D --> D1[S3 Bucket]
    
    E --> E1[Security Groups]
    E --> E2[IAM Roles]
    E --> E3[IAM Policies]
    
    F --> F1[Route53]
    F --> F2[ACM Certificate]
```

### Kubernetes 관리 리소스 (Ansible)

```mermaid
graph TB
    A[Kubernetes Cluster] --> B[Control Plane]
    A --> C[Data Plane]
    A --> D[Storage]
    A --> E[Add-ons]
    
    B --> B1[Master Node<br/>kube-apiserver, etcd]
    
    C --> C1[Worker-1<br/>FastAPI Pods]
    C --> C2[Worker-2<br/>Celery Workers]
    C --> C3[Storage Node<br/>RabbitMQ, Redis, PostgreSQL]
    
    D --> D1[EBS CSI Driver]
    D --> D2[StorageClass: gp3]
    D --> D3[PVCs]
    
    E --> E1[ArgoCD<br/>Helm]
    E --> E2[Prometheus Stack<br/>Helm]
    E --> E3[RabbitMQ Operator<br/>kubectl]
    E --> E4[Cert-manager<br/>kubectl]
    E --> E5[ALB Controller<br/>Helm]
```

## 배포 스크립트 계층 구조

```mermaid
graph TD
    A[auto-rebuild.sh<br/>최상위 자동화] --> B[destroy-with-cleanup.sh<br/>리소스 정리]
    A --> C[rebuild-cluster.sh<br/>재구축]
    
    B --> B1[kubectl 명령어들]
    B --> B2[helm uninstall]
    B --> B3[aws cli]
    B --> B4[terraform destroy]
    
    C --> C1[terraform init/destroy/apply]
    C --> C2[ansible-playbook site.yml]
    
    C2 --> D[Ansible Playbooks]
    D --> D1[OS 설정]
    D --> D2[Kubernetes 설치]
    D --> D3[CNI 설치]
    D --> D4[Add-ons 설치]
    D --> D5[RabbitMQ Role<br/>Operator 방식]
    D --> D6[Redis Role]
```

## CI/CD 로드맵

### 현재 상태
- ✅ 인프라 자동화 (Terraform + Ansible)
- ✅ 스크립트 기반 배포 (auto-rebuild.sh)
- ✅ GitOps 준비 (ArgoCD 설치됨)
- ⚠️ CI/CD 파이프라인 미구현

### Phase 1: 기본 CI/CD 설정 (우선순위: 높음)

#### 1.1 GitHub Actions 워크플로우
```yaml
# 필요 작업:
- [ ] .github/workflows/infrastructure.yml
  - Terraform Plan/Apply 자동화
  - Ansible 실행 자동화
  - 환경별 분리 (dev/staging/prod)
  
- [ ] .github/workflows/validate.yml
  - Terraform validate
  - Ansible syntax check
  - YAML linting
```

#### 1.2 Secret 관리
```yaml
# GitHub Secrets 필요:
- [ ] AWS_ACCESS_KEY_ID
- [ ] AWS_SECRET_ACCESS_KEY
- [ ] SSH_PRIVATE_KEY (또는 AWS Systems Manager)
- [ ] RABBITMQ_PASSWORD
- [ ] GRAFANA_PASSWORD
```

### Phase 2: 애플리케이션 CI/CD (우선순위: 중간)

#### 2.1 애플리케이션 빌드 파이프라인
```yaml
# 필요 작업:
- [ ] .github/workflows/application-build.yml
  - Docker 이미지 빌드
  - 이미지 스캔 (보안)
  - ECR 푸시
  
- [ ] .github/workflows/application-deploy.yml
  - ArgoCD Application 업데이트
  - 또는 kubectl 직접 배포
```

#### 2.2 GitOps 구성
```yaml
# 필요 작업:
- [ ] ArgoCD Application 정의
  - Application YAML 생성
  - Kustomize 또는 Helm Chart 준비
  
- [ ] Git 저장소 구조
  - apps/ 디렉토리
  - envs/ 디렉토리 (dev/staging/prod)
```

### Phase 3: 고급 CI/CD 기능 (우선순위: 낮음)

#### 3.1 자동 테스트
```yaml
# 필요 작업:
- [ ] 통합 테스트
  - 클러스터 헬스 체크
  - RabbitMQ 연결 테스트
  - API 엔드포인트 테스트
  
- [ ] E2E 테스트
  - 전체 워크플로우 테스트
```

#### 3.2 롤백 자동화
```yaml
# 필요 작업:
- [ ] 자동 롤백 스크립트
- [ ] 헬스 체크 기반 롤백
- [ ] 이전 버전 자동 복구
```

#### 3.3 모니터링 통합
```yaml
# 필요 작업:
- [ ] 배포 알림 (Slack/Discord)
- [ ] 메트릭 수집 (Prometheus)
- [ ] 로그 집계 (ELK/Fluentd)
```

### Phase 4: 멀티 환경 관리 (우선순위: 낮음)

#### 4.1 환경 분리
```yaml
# 필요 작업:
- [ ] 환경별 Terraform Workspace
- [ ] 환경별 Ansible Inventory
- [ ] 환경별 Kubernetes Namespace
```

#### 4.2 Blue-Green 배포
```yaml
# 필요 작업:
- [ ] ArgoCD Rollout 설정
- [ ] 트래픽 분할 구성
```

## 구현 우선순위 요약

### 즉시 구현 (1-2주)
1. ✅ GitHub Actions 기본 워크플로우
2. ✅ Secret 관리 설정
3. ✅ Terraform/Ansible 자동화

### 단기 구현 (1개월)
1. ✅ 애플리케이션 빌드 파이프라인
2. ✅ ArgoCD GitOps 구성
3. ✅ 기본 테스트 자동화

### 중기 구현 (2-3개월)
1. ⚠️ 고급 테스트 (통합/E2E)
2. ⚠️ 자동 롤백
3. ⚠️ 모니터링 통합

### 장기 구현 (3개월+)
1. ⚠️ 멀티 환경 관리
2. ⚠️ Blue-Green 배포
3. ⚠️ 카나리 배포

## 참고 파일

- `scripts/auto-rebuild.sh` - 최상위 자동화 스크립트
- `scripts/destroy-with-cleanup.sh` - 리소스 정리
- `scripts/rebuild-cluster.sh` - 재구축 프로세스
- `ansible/site.yml` - Ansible 메인 플레이북
- `ansible/roles/rabbitmq/tasks/main.yml` - RabbitMQ Operator 배포
