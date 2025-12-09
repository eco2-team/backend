# 류지환 (Jihwan Ryu)
**AI Platform & Cloud Infrastructure Engineer**
📧 ryoo0504@gmail.com | 🔗 [GitHub](https://github.com/mangowhoiscloud) | 📝 [Blog](https://rooftopsnow.tistory.com/)

---

## 🚀 Professional Summary
**[Cloud-Native 기술로 AI 서비스의 안정성과 생산성을 책임지는 플랫폼 엔지니어]**

**라쿠텐 심포니(Rakuten Symphony)**에서 대규모 클러스터 스토리지 엔진을 개발하며 OS 커널 및 네트워크 레벨의 **Deep Dive 역량**을 쌓았습니다. 이를 바탕으로 **이코에코(Eco²)** 프로젝트에서 **Kubernetes 기반의 GitOps 파이프라인**과 **AI 모델 서빙 아키텍처**를 직접 설계 및 구축했습니다.

**1. 다양한 AI/LLM 서빙 파이프라인 설계 및 최적화 경험**
단일 모델 연동에 그치지 않고, **Vision(Eco²), Audio(Aimo), Text(DREAM)** 등 다양한 모달리티(Modality)에 최적화된 서빙 파이프라인을 설계하고 배포했습니다. Eco²에서는 Vision 모델과 RAG 간의 **Context Pollution** 문제를 **Stateless 아키텍처와 Strict Injection**으로 해결하여 답변 신뢰성을 확보했고, DREAM과 Aimo에서는 **비동기 처리 및 임베딩 검색 최적화**를 통해 서비스 응답성(Latency)을 개선했습니다.

**2. Enterprise-grade Kubernetes Platform 구축**
**Self-managed Kubernetes 클러스터**를 직접 운영하며 CNI, CSI, Ingress 등 핵심 컴포넌트를 깊이 이해하고 있습니다. AI 추론 부하가 핵심 서비스에 영향을 주지 않도록 **Workload Isolation(노드 격리)** 전략을 적용하고, **ArgoCD**와 **External Secrets**를 활용한 **Zero-touch Deployment** 환경을 구현하여 개발팀이 모델 실험과 배포에만 집중할 수 있는 생산성 높은 플랫폼을 제공했습니다.

**3. High-Performance System Engineering**
문제의 원인을 시스템 밑바닥에서 찾아 해결합니다. 라쿠텐 재직 시 스토리지 엔진의 **Lock Contention(자원 경합)** 문제를 커널 레벨의 락 메커니즘 개선으로 해결하고, 노드 간 상태 동기화를 위한 **RPC 모듈**과 보안성이 강화된 **Object Storage API Gateway**를 직접 설계 및 개발했습니다.

---

## 💼 Work Experience

### **Rakuten Symphony Korea** | Cloud BU
**Jr. Storage Developer (Server)** | *2024.12 - 2025.08*

**High-Performance Storage Kernel Optimization**
*   **Concurrency Control Optimization:** Robin Storage 엔진의 성능 테스트(fio) 중 대용량 I/O 처리 시 `SEGMENT_LOCK` 오용으로 인한 병목 현상을 식별. 기존 Mutex Lock을 **Read-Write Lock (`down_read`)** 메커니즘으로 재설계하여 읽기 작업의 동시성(Concurrency)을 확보하고 **I/O 처리량(Throughput) 저하 문제 해결**.
*   **Stability Engineering:** 스토리지 스냅샷 로딩 시 `RDVM_STATE` 자원 경합(Race Condition)으로 인한 시스템 크래시(Crash) 원인을 규명. 상태 확인 로직에 **엄격한 락 검증(Lock Assertion)** 프로세스를 도입하여 프로덕션 환경에서의 **시스템 안정성 99.9% 달성**.
*   **RPC Development:** 분산 환경에서의 스토리지 상태 동기화를 위해 `RDVM` 상태 수집용 **Remote Procedure Call (RPC)** 모듈을 신규 개발하여 노드 간 데이터 일관성 확보.

**Infrastructure & Security Development**
*   **Object Storage Security:** Rakuten Object Storage v1.0.0의 초기 배포(Install-time) 시 **Root Account 자동 생성 및 주입 로직**을 설계/구현하고, 사용자 비활성화(Deactivate) 시 Access Key 잔존 버그를 수정하여 **보안 취약점(Security Vulnerability) 제거**.
*   **Network Virtualization Research:** `OVS/OVN` 및 `Kube-OVN` 기반의 가상 네트워크 아키텍처를 분석하고 Hands-on 테스트를 수행하여 클라우드 네이티브 네트워크 기술력 확보.

**Global Collaboration**
*   **Technical Communication:** 미국, 인도, 일본 지사 엔지니어들과 Jira/GitHub/Zoom을 통해 영어로 소통하며 코드 리뷰 및 기술 협의 주도.
*   **Knowledge Sharing:** 클라우드 스토리지 복구 전략(Disaster Recovery, Erasure Coding) 및 I/O 플로우에 대한 기술 분석 문서를 작성하고, 글로벌 팀을 대상으로 **30분간 기술 세미나 진행** 및 피드백 수렴.

---

## 🛠 Projects

### **Eco² (이코에코): GPT-5.1 Vision Recycling Assistant**
**Role: AI Platform & Infrastructure Lead** | *2025.10 - 2025.12*
🏆 **SeSACTHON 2025 Excellence Award (서울경제진흥원 대표이사상, Top 4)**

**1. Enterprise-grade K8s Cluster & GitOps**
*   **Self-managed Cluster:** AWS EC2 상에 `kubeadm`으로 14-node 클러스터를 직접 구축하고, **Workload Isolation(API/AI 노드 분리)**을 통해 AI 추론 부하가 핵심 서비스에 영향을 주지 않도록 격리.
*   **GitOps Pipeline:** `ArgoCD Sync-wave`와 `External Secrets`를 도입하여 인프라/DB/앱 배포 순서를 제어하고, 민감 정보 주입을 자동화하여 **Zero-touch Deployment** 환경 구현.

**2. AI & Backend Integration (Schema-driven Pipeline)**
*   **Hallucination Control:** 초기 RAG 파이프라인에서 대화 히스토리가 Vision 분류 결과를 왜곡하는 '맥락 오염' 현상을 발견. 이를 해결하기 위해 **Stateless 아키텍처**로 전환하고, 시스템 프롬프트에 **Negative Constraints(부정 제약 조건)**를 설정하여 LLM이 **주입된 컨텍스트(In-context Data) 내에서만 답변(Grounding)**하도록 강제하여 신뢰성 확보.
*   **Structured Output Integration:** LLM의 출력을 **Pydantic 기반의 엄격한 JSON 스키마**로 강제하여, 후속 시스템인 `Character API`가 별도의 파싱 로직 없이 데이터를 소비할 수 있도록 **결정론적(Deterministic) 인터페이스** 구축. (캐릭터 1:1 매칭 자동화)

**3. Traffic Management & Engineering Trade-off**
*   **Traffic Engineering:** `AWS Load Balancer Controller`를 활용해 Ingress와 ALB를 직접 연동하여 불필요한 프록시 Hop을 제거하고, `External-DNS`로 도메인 연결을 자동화하여 네트워크 레이턴시 최소화.
*   **Operator to Helm:** 초기 RabbitMQ Operator 도입 시 CRD 버전 호환성 문제를 겪고, 제한된 시간 내 안정성 확보를 위해 **Bitnami Helm Chart**로 신속하게 전환하여 비동기 메시지 처리 파이프라인을 성공적으로 구축.

---

### **DREAM: Generative AI Storytelling Service with RAG Pipeline**
**Role: Cloud DevOps & Backend Developer** | *2024.09*

*   **CI/CD Automation:** Built an automated deployment pipeline using GitHub Actions and AWS CodeDeploy, reducing deployment time by **80%**.
*   **Resource Optimization:** Resolved server freezing issues caused by memory spikes (89% usage) by implementing **Docker Resource Limits** and Swap memory configurations, stabilizing usage around 40%.
*   **Security & Routing:** Configured **NGINX Reverse Proxy** to secure internal ports and optimized API routing for SSL/TLS termination.

---

### **Aimo: AI-Powered Community for Accident Liability Assessment**
**Role: Backend Developer** | *2024.09 - 2024.11*

1.  **API & Database Design:** 복잡한 투표 및 과실 비율 판단 로직을 처리하기 위해 **정규화된 ERD**를 설계하고, 명확한 **RESTful API 명세서**를 작성하여 프론트엔드와의 협업 효율 증대.
2.  **AI Serving Integration:** Python 기반의 AI 추론 모델(LLM, STT)을 백엔드 서비스와 통합하기 위해 **Internal API Gateway** 역할을 수행하는 래퍼(Wrapper) API를 구현하고, 입력 데이터 전처리부터 결과 반환까지의 **E2E 파이프라인**을 설계하여 AI 기능의 서비스화 주도.
3.  **Multimedia Processing:** AWS S3를 활용하여 대용량 음성/이미지 데이터를 처리하는 **멀티파트 업로드 API**를 구현하고, **비동기 STT 파이프라인**을 연동하여 타임아웃 없는 안정적인 미디어 처리 환경 구축.

---

## 🔧 Technical Skills
*   **Languages:** Python, Go, C/C++, Java
*   **Cloud & DevOps:** Kubernetes (Self-managed/EKS), Docker, AWS, Terraform, Ansible, ArgoCD, GitHub Actions
*   **Backend & AI:** FastAPI, Spring Boot, Redis, PostgreSQL, RabbitMQ, OpenAI API, LangChain
*   **Tools:** Grafana, Prometheus, Kustomize, Helm

---

## 🎓 Education
*   **부산대학교** | 정보컴퓨터공학 학사 (*2017.03 - 2023.08*)
*   **카카오테크 부트캠프** | Cloud Native 과정 (*2024.06 - 2024.11*)

---

## 📜 Certifications & Languages
*   **정보처리기사** (2024.12)
*   **OPIc IH** (English - Professional Proficiency)
