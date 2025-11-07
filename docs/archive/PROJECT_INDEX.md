# 📋 프로젝트 인덱스

> **모든 문서를 한눈에**

## 🚀 시작하기

### 처음이신가요?

**→ [README.md](README.md)** - 프로젝트 소개부터 시작

### 구축하려면?

**→ [docs/guides/setup-checklist.md](docs/guides/setup-checklist.md)** ⭐⭐⭐⭐⭐

```bash
# 또는 자동화
./scripts/provision.sh  # 35분
```

---

## 📁 문서 구조

```
프로젝트 루트:
├── README.md                           ⭐ 메인 문서
├── CONVENTIONS.md                      (레거시)
├── DEPLOYMENT.md                       (레거시)
│
├── terraform/ (19개)                   Terraform 코드
├── ansible/ (17개)                     Ansible 코드
├── scripts/                            자동화 스크립트
│   ├── provision.sh
│   └── destroy.sh
│
└── docs/ (49개 문서)
    ├── 📖 README.md                    문서 센터
    │
    ├── overview/ (4개)                 프로젝트 개요
    │   ├── project-final-summary.md   최종 요약 ⭐
    │   ├── final-architecture.md      기술 스택
    │   └── architecture-decision.md
    │
    ├── guides/ (3개)                   실용 가이드
    │   ├── setup-checklist.md         구축 순서 ⭐⭐⭐⭐⭐
    │   ├── iac-quick-start.md
    │   └── deployment-setup.md
    │
    ├── getting-started/ (4개)          시작 가이드
    ├── development/ (5개)              개발 가이드
    ├── deployment/ (5개)               배포 가이드
    ├── infrastructure/ (3개)           인프라 구축
    ├── architecture/ (6개 + 7개)       아키텍처
    │   ├── final-k8s-architecture.md  ⭐⭐⭐⭐⭐
    │   ├── task-queue-design.md
    │   └── decisions/ (검토 과정)
    │
    └── contributing/ (2개)             기여 가이드
```

---

## 🎯 목적별 문서

### 구축

```
1. docs/guides/setup-checklist.md
2. docs/guides/iac-quick-start.md
3. docs/infrastructure/iac-terraform-ansible.md
```

### 이해

```
1. docs/overview/project-final-summary.md
2. docs/architecture/final-k8s-architecture.md
3. docs/architecture/decision-summary.md
```

### 개발

```
1. docs/development/conventions.md
2. docs/development/pep8-guide.md
3. docs/development/git-workflow.md
```

### 배포

```
1. docs/deployment/gitops-argocd-helm.md
2. docs/deployment/ghcr-setup.md
```

---

## 📊 통계

```
총 문서: 60+ 개
├─ Markdown: 49개
├─ Terraform: 19개
├─ Ansible: 17개
└─ Scripts: 2개

총 코드: 10,000+ 줄
```

---

**버전**: 2.0  
**업데이트**: 2025-10-30

