# 📚 AI Waste Coach Backend - 문서 센터

> **AI 기반 쓰레기 분류 및 재활용 코칭 서비스** 백엔드 문서

---

## 🚀 빠른 시작

### 지금 바로 구축하려면?

**[📋 구축 체크리스트](guides/setup-checklist.md)** ← 여기서 시작! ⭐⭐⭐⭐⭐

```bash
# 또는 자동화
./scripts/provision.sh  # 35분 완성
```

**[IaC 빠른 시작 가이드](guides/iac-quick-start.md)**

---

## 📖 문서 카테고리

### 🎯 [개요](overview/)

프로젝트 전체 요약

- [**프로젝트 최종 요약**](overview/project-final-summary.md) - 구축 완료 상태 ⭐
- [최종 아키텍처](overview/final-architecture.md) - 기술 스택
- [아키텍처 결정](overview/architecture-decision.md) - 구성 요약

### 📖 [가이드](guides/)

빠른 시작 및 실용 가이드

- [**구축 체크리스트**](guides/setup-checklist.md) - 우선순위별 단계 ⭐⭐⭐⭐⭐
- [IaC 빠른 시작](guides/iac-quick-start.md) - Terraform + Ansible
- [배포 환경 구축](guides/deployment-setup.md) - GitOps 설정

### 🚀 [시작하기](getting-started/)

프로젝트를 처음 접하는 개발자용

- [설치 가이드](getting-started/installation.md) - 개발 환경 세팅
- [빠른 시작](getting-started/quickstart.md) - 5분 만에 시작
- [프로젝트 구조](getting-started/project-structure.md) - 폴더 구조

### 💻 [개발 가이드](development/)

코드 작성 시 필수 규칙

- [코딩 컨벤션](development/conventions.md) - 네이밍, 스타일, PEP 8
- [PEP 8 완벽 가이드](development/pep8-guide.md) - Python 표준
- [Git 워크플로우](development/git-workflow.md) - 브랜치, 커밋 규칙
- [코드 품질 체크리스트](development/code-quality-checklist.md) - PR 전 확인

### 🚢 [배포 가이드](deployment/)

프로덕션 배포 및 운영

- [**GitOps 배포 (ArgoCD + Helm)**](deployment/gitops-argocd-helm.md) - 자동 배포 ⭐⭐⭐
- [GHCR 설정](deployment/ghcr-setup.md) - GitHub Container Registry (무료)
- [Docker 배포](deployment/docker.md) - 로컬 개발용

### 🏗️ [인프라](infrastructure/)

Kubernetes 클러스터 구축

- [**K8s 클러스터 구축**](infrastructure/k8s-cluster-setup.md) - kubeadm 수동 설치 ⭐⭐⭐
- [**IaC (Terraform + Ansible)**](infrastructure/iac-terraform-ansible.md) - 자동화 구축 ⭐⭐⭐

### 🏛️ [아키텍처](architecture/)

기술 결정 및 설계 문서

- [**아키텍처 결정 요약**](architecture/decision-summary.md) - 전체 의사결정 ⭐
- [**최종 K8s 아키텍처**](architecture/final-k8s-architecture.md) - 시스템 전체 ⭐⭐⭐⭐⭐
- [**Task Queue 설계**](architecture/task-queue-design.md) - RabbitMQ + Celery ⭐⭐⭐
- [이미지 처리 아키텍처](architecture/image-processing-architecture.md) - 이미지 파이프라인
- [Polling vs WebSocket](architecture/polling-vs-websocket.md) - 실시간 통신
- [Istio Service Mesh](architecture/istio-service-mesh.md) - MVP 후 검토
- [의사결정 과정](architecture/decisions/) - 검토 및 비교 문서

### 🤝 [기여 가이드](contributing/)

프로젝트 기여 방법

- [기여 방법](contributing/how-to-contribute.md) - 기여 절차

---

## 🗺️ 추천 학습 경로

### 신규 개발자

```
1. overview/project-final-summary.md (전체 이해)
2. getting-started/installation.md (환경 설정)
3. getting-started/quickstart.md (빠른 시작)
4. development/conventions.md (코딩 규칙)
5. development/git-workflow.md (Git 사용법)
```

### 인프라 담당자

```
1. overview/final-architecture.md (아키텍처)
2. guides/setup-checklist.md (구축 순서) ⭐
3. infrastructure/iac-terraform-ansible.md (IaC)
4. deployment/gitops-argocd-helm.md (GitOps)
```

### 아키텍트

```
1. architecture/final-k8s-architecture.md (전체 시스템)
2. architecture/decision-summary.md (결정 요약)
3. architecture/task-queue-design.md (Queue 설계)
4. architecture/decisions/ (검토 과정)
```

---

## 📊 문서 통계

```
총 문서: 60+ 개

docs/
├─ overview: 4개 (프로젝트 개요)
├─ guides: 3개 (실용 가이드)
├─ getting-started: 4개
├─ development: 5개
├─ deployment: 5개
├─ infrastructure: 3개
├─ architecture: 6개 (최종)
│   └─ decisions: 7개 (검토)
└─ contributing: 2개

+ IaC 코드: 36개
```

---

## 🔍 검색 가이드

| 찾고 싶은 것 | 문서 |
|------------|------|
| **구축 방법** | [guides/setup-checklist.md](guides/setup-checklist.md) |
| **전체 아키텍처** | [architecture/final-k8s-architecture.md](architecture/final-k8s-architecture.md) |
| **비용 및 시간** | [overview/final-architecture.md](overview/final-architecture.md) |
| **자동화 구축** | [guides/iac-quick-start.md](guides/iac-quick-start.md) |
| **배포 방법** | [deployment/gitops-argocd-helm.md](deployment/gitops-argocd-helm.md) |
| **코딩 규칙** | [development/conventions.md](development/conventions.md) |
| **Git 사용법** | [development/git-workflow.md](development/git-workflow.md) |
| **왜 이렇게 설계했나?** | [architecture/decision-summary.md](architecture/decision-summary.md) |
| **다른 옵션은?** | [architecture/decisions/](architecture/decisions/) |

---

## 🎯 핵심 명령어

```bash
# 전체 구축 (자동화)
./scripts/provision.sh

# 인프라 삭제
./scripts/destroy.sh

# 클러스터 상태 확인
kubectl get nodes

# ArgoCD 앱 목록
argocd app list

# 전체 Pod 상태
kubectl get pods -A
```

---

**문서 버전**: 2.0 (재구성 완료)  
**최종 업데이트**: 2025-10-30
