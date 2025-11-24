# 류지환 – Data Engineer (AI)

## 연락처
- 전화: 010-4008-0967
- 이메일: ryoo0504@gmail.com
- GitHub: https://github.com/mangowhoiscloud (Current), https://github.com/mng990 (Archive)
- Blog: https://rooftopsnow.tistory.com/
- LinkedIn: https://www.linkedin.com/in/jihwan-ryu-b6b04a202/

## 지원 포지션
- 토스증권 [주니어 집중 채용] Data Engineer (AI) (~11/23)

## Summary & 지원 동기
- **글로벌 클라우드 스토리지 서비스(Robin Storage)의 서버 모듈 개발 경험:** 라쿠텐 심포니에서 독일, 일본 리전의 통신망을 커버하는 클라우드 플랫폼의 백엔드(스토리지)와 인프라를 개발했습니다.
- **AI 도입에 대한 열망과 실행:** 글로벌 환경에서 AI에 대한 명확한 수요를 확인했고, 이를 주도적으로 실행할 수 있는 보다 동적인 환경을 찾아 나섰습니다. 현재는 약 30.6억 토큰(Claude 4.5 Sonnet, GPT-5.1 Codex 등)을 공격적으로 소모해 1인 개발로 14-nodes 쿠버네티스 클러스터와 선언형 GitOps 파이프라인을 구축하며 극대화된 생산성을 검증하는 중입니다.
- **빠른 실행과 데이터 기반 성장:** 토스증권의 애자일한 문화와 데이터 기반 의사결정 환경에서, 인프라/백엔드 역량을 발휘해 금융 데이터 혁신에 기여하고자 합니다.
- **SideCar Growth:** 현재는 Terraform/Ansible/Kubernetes 기반의 개인 클러스터를 운영하며, LLM 모델(Claude 4.5 Sonnet, GPT-5.1 Codex)을 활용해 개발 생산성을 극대화하는 AI-Driven 방식을 실험하고 있습니다.

## 핵심 역량
- **Cloud & Infra:** Rakuten Cloud Platform v5.5.0 & OStore v1.0.0 Dev, AWS(EC2, S3, VPC, IAM), Kubernetes, Terraform, Ansible
- **Data & AI:** ElasticSearch, RAG Pipeline Optimization, LLM Experimentation (Prompt Engineering)
- **Backend:** Java(Spring Boot), Python(FastAPI), REST/RPC, Solidity, C++
- **DevOps:** Kubernetes, Docker, GitHub Actions, ArgoCD(GitOps, Sync-wave), Helm-charts, Kustomize, Terraform, Ansible
- **Collaboration:** Global Cross-functional Team Collaboration (English/Korean), Jira/Confluence 기반 애자일 협업

## Proffesional Exprience
### Rakuten Symphony Korea – Cloud Engineer / Jr. Storage Dev (2024.12.09 – 2025.08.31)
- **Robin Storage v5.5.0 & Rakuten OStore v1.0.0 개발 참여:** 글로벌 스토리지 플랫폼의 서버 사이드 모듈 개발 및 인프라 최적화를 담당했습니다.
- **Robin Storage (Block Storage) 개발:**
    - **Control Plane ↔ Data Plane RPC 개발:** 스냅샷 로딩 시 Data Plane(RDVM) 상태 불일치 문제를 해결하기 위해 비동기 RPC 프로시저(`RDVM_VOL_CFG_UPDATE`)를 신규 개발하여 클러스터 상태 일관성을 확보했습니다.
    - **I/O 성능 병목 개선:** 스냅샷 반복 읽기 시 쓰기 락(`down_write`) 점유로 인한 동시성 저하를 확인하고, 이를 읽기 락(`down_read`)으로 전환하여 처리량을 개선했습니다. 나아가 epoll 기반 Reactor 모델의 한계를 분석하고 io_uring 기반 Proactor 모델 전환 로드맵을 제시했습니다.
- **Rakuten OStore (Object Storage) 개발:**
    - **Authentication 버그 픽스:** 사용자 비활성화 시 Access Key가 삭제되는 문제를 수정하고, Gateway-CM-DB 간의 데이터 흐름을 분석하여 인증 로직을 개선했습니다.
    - **Root User 초기화 로직 구현:** 설치 시점에만 Root 사용자가 생성되도록 제어하고, CM 부팅 시 자동 동기화 및 GW 캐시 전파 로직을 설계 및 구현했습니다.
- **Global Collaboration:** 인도(개발 리드), 미국(일정 수립 및 개발), 일본(QA, 개발) 등 4개국 엔지니어와 협업하며 Jira/Confluence 기반의 애자일 스프린트를 수행했습니다.

## In-Progress
### 이코에코(Eco²) – RAG/LLM 기반 재활용 분류 및 캐릭터 생성 앱 (2025.10.30 – Present)[https://github.com/eco2-team/backend]
- **Role:** Backend & DevOps
- **개요:** 경량 RAG/LLM을 활용한 폐기물 이미지 분류 및 챗봇 기능을 제공하며, 공공 데이터(KECO)와 연동해 보상 거점 정보를 안내, 분리수거한 폐기물과 캐릭터를 매칭해주는 게이미피케이션 서비스입니다. Kubernetes 클러스터에서 보다 유연하고 확장 가능한 인프라를 제공합니다.
- **Infrastructure & GitOps:** 
    - **AWS 인프라 프로비저닝:** Terraform으로 VPC, 14개의 EC2 인스턴스(t3a.large/medium), ALB, ACM(SSL/TLS) 등 60여 개의 AWS 리소스를 코드로 정의해 15분 내 구축 자동화.
    - **Kubernetes 클러스터 구성:** Ansible Playbook을 통해 OS 설정, Kubeadm 초기화, CNI(Calico VXLAN), 쿠버네티스, ArgoCD Root-App 부트스트래핑.
    - **선언형 GitOps 파이프라인:** ArgoCD + Helm-charts + Kustomize(Base/Overlays) 구조로 7개 도메인 API와 Infra(DB, Redis, RabbitMQ) 리소스를 배포하며, Sync Wave로 배포 순서(Infra → App)를 제어.
- **Architecture Strategy (4-Tier & Resource Isolation):**
    - **4-Tier 아키텍처:** Presentation(ALB) → Business(API Nodes) → Integration(RabbitMQ/Celery) → Data(PostgreSQL/Redis) 계층으로 노드 역할을 분리해 안정성 확보.
    - **Node Affinity & Taints:** 도메인별 네임스페이스 격리와 함께 Taints/Tolerations를 적용해 API 파드가 Infra 노드에 침범하지 않도록 스케줄링 제어.
    - **Network Policy:** Zero Trust 원칙에 따라 네임스페이스 간 통신을 기본 차단하고, 필요한 Egress만 명시적으로 허용해 ALB 안정성 및 보안 강화.
- **성과:** 
    - **14-Node Production-Ready Cluster:** Terraform/Ansible로 14개 노드(Master/API/Worker/Infra)를 4-Tier 아키텍처로 자동 구축 및 운영.
    - **GitOps & Sync-wave:** ArgoCD App-of-Apps 패턴과 Sync-wave를 활용해 인프라(DB/MQ) → 앱 배포 순서를 제어하고, GitHub Actions와 연동해 이미지 빌드부터 배포까지 완전 자동화 달성.
    - **Observability:** Prometheus/Grafana로 리소스 사용량 및 API 상태를 실시간 모니터링하며 리소스 격리 및 최적화 수행.

## Side Projects
### Aimo – LLM 기반 갈등 중재 서비스 (2024.10 – 2024.11)
- **GitHub:** [mng990/aimo-backend](https://github.com/mng990/aimo-backend)
- **Role:** Backend Developer
- **개요:** 사용자의 대화를 분석하여 관련 판례 및 법령을 제공하는 LLM 기반 서비스.
- **주요 역할:**
    - Spring 기반의 백엔드 서버 구축 및 REST API 설계.
    - 동기식 모델 서빙, 확장 계획 설계

### Dream – RAG/Langchain 기반 스토리/이미지 생성 서비스 (2024.09.04 – 2024.09.07)
- **GitHub:** [KakaoTech-Hackathon-Dream](https://github.com/KakaoTech-Hackathon-Dream)
- **Role:** DevOps
- **개요:** 생성형 AI(LLM, RAG, Diffusion)를 활용해 노년층의 미완의 꿈을 스토리와 이미지로 시각화하는 서비스 (KakaoTech Hackathon).
- **주요 역할:**
    - AWS EC2, S3, RDS, Elasticsearch를 활용한 클라우드 인프라 아키텍처 설계 및 구축.
    - GitHub Actions와 AWS CodeDeploy를 연동하여 레거시 CI/CD 파이프라인을 구축, 배포 자동화 달성.
    - NGINX 리버스 프록시 설정 및 SSL/TLS 인증서(Certbot) 적용으로 보안성 강화.
    - Docker 컨테이너 기반의 애플리케이션 배포 환경 구성.

### Ethereum Multi-Token 기반 경매/운송 플랫폼 (2022.03.16 – 2022.11.14)
- **GitHub:** [mng990/ethereum_FisheriesMarket](https://github.com/mng990/ethereum_FisheriesMarket)
- **Role:** Backend Developer (스마트 컨트랙트 및 이더리움 블록체인 네트워크 개발)
- **주요 역할:**
    - Solidity(ERC-1155)를 활용해 상품/경매/화폐 토큰을 개발하고 스마트 컨트랙트 배포.
    - Geth 및 Ganache를 활용해 Private Ethereum Network 환경 구축 및 테스트 수행.
    - Web3.js와 IPFS 연동을 통해 미디어 데이터의 무결성을 보장하는 탈중앙화 스토리지 로직 구현.

## Education & Certifications
- 부산대학교 컴퓨터공학부 학사 (2017.03 - 2023.08)
- KakaoTech Bootcamp, 중도 하차 (2024.07 - 2024.11.18)
- 정보처리기사 (Engineer Information Processing)
- OPIc IH (Intermediate High)

## Language
- 한국어 (모국어)
- 영어 (OPIc IH, 글로벌 협업 경험 보유)

