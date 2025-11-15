# 🚢 배포 가이드

프로덕션 배포 및 운영 절차를 GitOps 기준으로 정리한 컬렉션입니다.  
2025-11 구조 개편 이후 문서를 주제별 서브 디렉토리로 정리했습니다.

## 📁 디렉토리 구조

| 디렉토리 | 설명 | 대표 문서 |
|----------|------|-----------|
| `gitops/` | ArgoCD, Atlantis, GHCR, Terraform 파이프라인 | `gitops/GITOPS_ARCHITECTURE.md`, `gitops/TERRAFORM-OPERATOR-PIPELINE.md`, `gitops/GHCR_GUIDE.md` |
| `namespaces/` | Namespace 전략, 점검 리포트 | `namespaces/NAMESPACE_CONSISTENCY_CHECKLIST.md`, `namespaces/NAMESPACE_ADDITIONAL_RESOURCES_REPORT.md` |
| `platform/` | 인프라/모니터링/노드 운영 | `platform/INFRASTRUCTURE_DEPLOYMENT.md`, `platform/MONITORING_SETUP.md`, `platform/NODE_TAINT_MANAGEMENT.md` |
| `phase3/` | Phase 3 (Atlantis + Hooks) 배포 절차 | `phase3/PHASE3_QUICK_START.md`, `phase3/AUTO_REBUILD_GUIDE.md` |

## 🔑 바로가기

1. **GitOps 전반**  
   - [GITOPS_ARCHITECTURE](gitops/GITOPS_ARCHITECTURE.md)  
   - [TERRAFORM-OPERATOR-PIPELINE](gitops/TERRAFORM-OPERATOR-PIPELINE.md)  
   - [ARGOCD_ACCESS](gitops/ARGOCD_ACCESS.md) / [argocd-hooks-setup-guide](gitops/argocd-hooks-setup-guide.md)

2. **레지스트리 & 이미지**  
   - [GHCR_GUIDE](gitops/GHCR_GUIDE.md)  
   - [helm-argocd-guide](gitops/helm-argocd-guide.md)

3. **네임스페이스 거버넌스**  
   - [NAMESPACE_CONSISTENCY_CHECKLIST](namespaces/NAMESPACE_CONSISTENCY_CHECKLIST.md)  
   - [NAMESPACE_CONSISTENCY_REPORT_2025-11-13](namespaces/NAMESPACE_CONSISTENCY_REPORT_2025-11-13.md)

4. **플랫폼 운영**  
   - [INFRASTRUCTURE_DEPLOYMENT](platform/INFRASTRUCTURE_DEPLOYMENT.md)  
   - [MONITORING_SETUP](platform/MONITORING_SETUP.md)  
   - [NODE_TAINT_MANAGEMENT](platform/NODE_TAINT_MANAGEMENT.md)

5. **Phase 3 / 재구축**  
   - [PHASE3_QUICK_START](phase3/PHASE3_QUICK_START.md)  
   - [AUTO_REBUILD_GUIDE](phase3/AUTO_REBUILD_GUIDE.md)

---

**문서 버전**: 1.1.0 (2025-11-16 디렉토리 리팩터링 반영)

