# ArgoCD App of Apps 구조 정리 완료 ✅

## 📝 작업 내용

### 1. ✅ Legacy 디렉토리 정리
- `argocd/applications/` → `argocd/applications-archive/` 이동
- 단독 Application 파일들 (`application*.yaml`) archive로 이동
- `applications/` 디렉토리에 README 추가 (참고용)

### 2. ✅ Wave 기반 App of Apps 구조 구현
```
argocd/apps/
├── 00-foundations.yaml          # Wave -1
├── 10-infrastructure.yaml       # Wave 0
├── 20-platform.yaml             # Wave 10
├── 30-monitoring.yaml           # Wave 20
├── 40-data-operators.yaml       # Wave 25
├── 50-data-clusters.yaml        # Wave 30
├── 60-gitops-tools.yaml         # Wave 50
├── 70-apis-app-of-apps.yaml     # Wave 55 (Nested App of Apps)
│
└── apis/                        # API 개별 파일들
    ├── auth-api.yaml            # Wave 60
    ├── my-api.yaml              # Wave 61
    ├── scan-api.yaml            # Wave 62
    ├── character-api.yaml       # Wave 65
    ├── location-api.yaml        # Wave 66
    ├── info-api.yaml            # Wave 70
    ├── chat-api.yaml            # Wave 71
    │
    └── workers/
        └── celery-workers.yaml  # Wave 75
```

### 3. ✅ 브랜치 전략 통일
- 모든 활성 Application: `targetRevision: refactor/operator-ansible-minimal`
- Archive 파일들: 브랜치 불일치 유지 (참고용)

### 4. ✅ 문서화 업데이트
- `argocd/README.md`: 전체 App of Apps 구조 설명
- `argocd/applications/README.md`: applications/ 디렉토리 용도 설명
- `argocd/applications-archive/README.md`: Archive 이유 및 파일 목록

---

## 🌊 Wave 기반 배포 순서

| Wave | Application | Path | 설명 |
|------|------------|------|------|
| -1 | Foundations | `k8s/foundations/` | CRDs, RBAC |
| 0 | Infrastructure | `k8s/infrastructure/` | Namespaces, NetworkPolicies |
| 10 | Platform | `k8s/platform/` | Cert-Manager, ALB Controller |
| 20 | Monitoring | `k8s/monitoring/` | Prometheus, Grafana |
| 25 | Data Operators | `k8s/data-operators/` | PostgreSQL, Redis, RabbitMQ Operators |
| 30 | Data Clusters | `k8s/databases/` | Database Instances |
| 50 | GitOps Tools | `k8s/atlantis/` | Atlantis |
| 55 | APIs App of Apps | `argocd/apps/apis/` | Nested App of Apps |
| 60-62 | Phase 1 Core APIs | `k8s/overlays/{auth,my,scan}` | Core APIs |
| 65-66 | Phase 2 Extended APIs | `k8s/overlays/{character,location}` | Extended APIs |
| 70-71 | Phase 3 Advanced APIs | `k8s/overlays/{info,chat}` | Advanced APIs |
| 75 | Workers | `k8s/workers/` | Celery Workers |

---

## 🎯 주요 변경 사항

### Before (기존 구조)
```
argocd/
├── application*.yaml (단독 파일들)
├── applications/ (7개 ApplicationSet, 혼재)
└── apps/ (2개 파일만)
```

**문제점**:
- ❌ 배포 순서 제어 어려움
- ❌ Infrastructure와 Application 구분 없음
- ❌ 브랜치 전략 불일치 (main, develop, HEAD 혼재)
- ❌ 구조가 불명확

### After (개선 구조)
```
argocd/
├── root-app.yaml (최상위)
├── apps/ (Wave 기반 8개 Application)
│   └── apis/ (7개 API + 1개 Workers)
├── applications/ (README만)
└── applications-archive/ (Legacy 보관)
```

**개선점**:
- ✅ Sync Wave로 명확한 배포 순서
- ✅ Infrastructure (Wave -1~50) / Application (Wave 55~75) 분리
- ✅ 브랜치 전략 통일 (`refactor/operator-ansible-minimal`)
- ✅ Nested App of Apps 패턴
- ✅ Kustomize 기반 (Infrastructure + API Overlays)

---

## 📚 참고 문서

- **설계 문서**: `docs/architecture/KUSTOMIZE_APP_OF_APPS.md`
- **GitOps 가이드**: `docs/architecture/GITOPS_BEST_PRACTICES.md`
- **ArgoCD 운영**: `docs/guides/ARGOCD_GUIDE.md`

---

## 🚀 다음 단계

1. **테스트 배포**
   ```bash
   kubectl apply -f argocd/root-app.yaml
   kubectl get applications -n argocd --watch
   ```

2. **develop 브랜치 merge**
   ```bash
   git checkout develop
   git merge refactor/operator-ansible-minimal
   # targetRevision을 develop으로 변경
   ```

3. **프로덕션 배포**
   - `main` 브랜치 merge
   - `targetRevision: main`으로 변경

---

**작업 완료일**: 2025-11-14  
**작업자**: AI Assistant + User  
**상태**: ✅ 완료

