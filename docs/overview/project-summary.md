# 📋 프로젝트 요약

> **AI Waste Coach Backend**

## 🎯 프로젝트

**AI 기반 쓰레기 분류 및 재활용 코칭 서비스 - 백엔드 API**

### 주요 기능

1. AI 쓰레기 스캐너 (Vision + LLM)
2. 위치 기반 재활용 수거함 제안
3. LLM 기반 피드백 코칭
4. 소셜 로그인 (OAuth 2.0)

---

## ✅ 최종 기술 스택

### 인프라
- Kubernetes (kubeadm, 1M + 2W, non-HA)
- Terraform + Ansible (IaC)

### GitOps
- GitHub Actions (CI)
- ArgoCD (CD)
- Helm Charts
- GHCR (무료)

### Backend
- FastAPI (Python 3.11+)
- 5개 마이크로서비스

### 비동기
- RabbitMQ (5개 큐)
- Celery Workers (12개)

---

## 📊 비용 및 시간

- **월 비용**: $105
- **구축 시간**: 35분 (IaC 자동화)

---

## 📚 주요 문서

- [최종 요약](project-final-summary.md)
- [최종 아키텍처](final-architecture.md)
- [구축 체크리스트](../guides/setup-checklist.md)

---

**버전**: 2.0
