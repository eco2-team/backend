# ArgoCD Applications Archive

> **⚠️ 이 디렉토리는 더 이상 사용되지 않습니다**  
> **현재 구조**: `argocd/apps/` (App of Apps 패턴)

---

## 📁 Archive 내용

이 디렉토리는 이전 ArgoCD Application 정의들을 보관합니다.

### Legacy ApplicationSet Files

| 파일 | 아키텍처 | targetRevision | 설명 |
|------|----------|----------------|------|
| `ecoeco-14nodes-appset.yaml` | 14-Node | `main` | 14-Node Helm 기반 ApplicationSet |
| `api-services-appset.yaml` | 13-Node | `HEAD` | 13-Node API Services ApplicationSet |
| `worker-services-appset.yaml` | 13-Node | `HEAD` | Worker Services ApplicationSet |
| `ecoeco-appset-kustomize.yaml` | - | `main` | 초기 Kustomize 실험 |
| `ecoeco-backend-phase12.yaml` | - | `HEAD` | Phase 1-2 통합 Application |
| `ecoeco-backend.yaml` | - | `HEAD` | 기본 Backend Application |
| `test-auth-app.yaml` | - | `main` | Auth API 테스트용 |

### Legacy Application Files

| 파일 | 아키텍처 | targetRevision | 설명 |
|------|----------|----------------|------|
| `application.yaml` | - | `main` | 기본 Backend Application |
| `application-13nodes.yaml` | 13-Node | `develop` | 13-Node 전용 Application |
| `application-14nodes-with-hooks.yaml` | 14-Node | `main` | 14-Node + Ansible Hooks |

---

## 🔄 마이그레이션 이유

### Before (Archive)

**문제점**:
1. ❌ 여러 버전의 Application 파일 혼재 (13-node, 14-node, etc.)
2. ❌ Helm과 Kustomize 방식 혼용
3. ❌ 명확한 배포 순서 제어 어려움
4. ❌ Infrastructure와 Application 구분 없음
5. ❌ 브랜치 전략 불일치 (`main`, `develop`, `HEAD` 혼재)

**구조**:
```
argocd/
├── application.yaml                      # main
├── application-13nodes.yaml              # develop
├── application-14nodes-with-hooks.yaml   # main
└── applications/
    ├── ecoeco-14nodes-appset.yaml       # main
    ├── api-services-appset.yaml          # HEAD
    └── ... (혼재)
```

### After (Current)

**개선점**:
1. ✅ App of Apps 패턴으로 명확한 계층 구조
2. ✅ Sync Wave로 배포 순서 제어
3. ✅ Infrastructure (Kustomize) + Application (Kustomize Overlay) 분리
4. ✅ 브랜치 전략 통일 (현재 브랜치 기준)
5. ✅ 하나의 명확한 구조

**구조**:
```
argocd/
├── root-app.yaml                   # App of Apps
└── apps/
    ├── infrastructure.yaml         # Wave 0
    └── api-services.yaml           # Wave 3 (ApplicationSet)
```

---

## 📚 참고용 보관

이 파일들은 다음 목적으로 보관됩니다:

1. **히스토리 참고**
   - 과거 아키텍처 변경 이력
   - 설계 결정 근거

2. **롤백 가능성**
   - 긴급 상황 시 이전 구조로 복원
   - 비교 및 검증

3. **학습 자료**
   - Helm vs Kustomize 비교
   - ApplicationSet 패턴 학습

---

## ⚠️ 사용 금지

**이 디렉토리의 파일들은 더 이상 배포에 사용되지 않습니다.**

만약 이 파일들을 실수로 적용하면:
```bash
kubectl apply -f argocd/applications-archive/xxx.yaml
```

다음 문제가 발생할 수 있습니다:
- 🔴 브랜치 불일치 (outdated code)
- 🔴 중복 리소스 생성
- 🔴 App of Apps 구조와 충돌

**올바른 사용법**:
```bash
# Root App을 통한 배포 (권장)
kubectl apply -f argocd/root-app.yaml

# 또는 개별 Application 배포
kubectl apply -f argocd/apps/infrastructure.yaml
kubectl apply -f argocd/apps/api-services.yaml
```

---

## 🗑️ 삭제 계획

이 디렉토리는 다음 마일스톤 이후 삭제될 예정입니다:

1. ✅ App of Apps 패턴 안정화
2. ⏳ develop 브랜치 merge
3. ⏳ 프로덕션 배포 검증 (1주일)
4. ⏳ 팀 전체 승인

**예상 삭제일**: 2025-11-30

---

**Archive 생성일**: 2025-11-14  
**Archive 사유**: App of Apps 패턴으로 마이그레이션  
**관련 문서**: [Kustomize + App of Apps 가이드](../../docs/architecture/KUSTOMIZE_APP_OF_APPS.md)

