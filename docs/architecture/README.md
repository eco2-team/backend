# 🏛️ 아키텍처 문서

> **AI Waste Coach Backend 아키텍처 결정 기록**

## 📚 문서 구조

```
architecture/
├── 📋 최종 결정 문서 (여기)
├── 💭 decisions/ (검토 과정)
└── 🎨 가이드
```

---

## 🎯 최종 결정 문서

### 핵심 아키텍처

1. **[📋 아키텍처 결정 요약](decision-summary.md)** ⭐⭐⭐
   - 모든 의사결정 한눈에
   - 채택/기각 기술 목록
   - 최종 스택 정리

2. **[🏗️ 최종 K8s 아키텍처](final-k8s-architecture.md)** ⭐⭐⭐⭐⭐
   - 전체 시스템 시각화
   - 노드별 배치
   - 데이터 흐름
   - GitOps 파이프라인

3. **[🖼️ 이미지 처리 아키텍처](image-processing-architecture.md)** ⭐
   - 이미지 분석 파이프라인
   - 캐싱 전략
   - 최적화 방안

4. **[⚡ Polling vs WebSocket](polling-vs-websocket.md)** ⭐
   - 실시간 통신 방식 비교
   - 트래픽 시뮬레이션
   - 최종 결정: Short Polling

5. **[🐰 Task Queue 설계](task-queue-design.md)** ⭐⭐⭐
   - RabbitMQ + Celery
   - 5개 큐: fast, bulk, external, sched, dlq
   - prefetch, DLX, TTL 정책

6. **[🏢 마이크로서비스 아키텍처](microservices-architecture.md)** ⭐
   - 5개 도메인 서비스
   - 서비스 간 통신
   - Traefik Gateway

7. **[🔄 GitOps 멀티서비스](gitops-multi-service.md)** ⭐⭐
   - 서비스별 독립 CI/CD
   - Path-based Triggers
   - 빌드 시간 75% 단축

---

## 💭 의사결정 과정

**[decisions/](decisions/)** 폴더 - 검토 및 비교 분석

- Docker Compose vs ECS vs K8s 비교
- Self-managed K8s 검토
- k3s vs kubeadm 검토
- EKS 비용 분석
- EKS + ArgoCD 검토

**→ 최종 결정에 이르기까지의 논의 기록**

---

## 🎨 가이드

- **[Mermaid 색상 가이드](mermaid-color-guide.md)** - 다이어그램 색상 표준

---

## 📊 채택된 최종 스택

| 분야 | 선택 | 문서 |
|------|------|------|
| **서버 구조** | Kubernetes (kubeadm) | [final-k8s-architecture.md](final-k8s-architecture.md) |
| **실시간 통신** | Short Polling | [polling-vs-websocket.md](polling-vs-websocket.md) |
| **Task Queue** | RabbitMQ + Celery | [task-queue-design.md](task-queue-design.md) |
| **마이크로서비스** | 5개 도메인 분리 | [microservices-architecture.md](microservices-architecture.md) |
| **CI/CD** | GitOps (ArgoCD + Helm) | [gitops-multi-service.md](gitops-multi-service.md) |
| **이미지 처리** | S3 + AI API + 캐싱 | [image-processing-architecture.md](image-processing-architecture.md) |

---

## 🚀 빠른 참조

**구축하려면**: [../../SETUP_CHECKLIST.md](../../SETUP_CHECKLIST.md)

**인프라 설정**: [../infrastructure/](../infrastructure/)

**배포 가이드**: [../deployment/](../deployment/)

---

**문서 버전**: 2.0 (정리 완료)  
**최종 업데이트**: 2025-10-30
