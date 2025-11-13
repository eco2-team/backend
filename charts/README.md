# Charts Directory - Deprecated

## 상태

**⚠️ Helm Chart는 더 이상 사용되지 않습니다.**

현재 프로젝트는 **Kustomize** 기반 GitOps로 전환되었습니다.

## 히스토리

- **2025-11-08**: Helm Chart 사용 종료, Kustomize로 전환 결정
- **2025-11-13**: Helm Chart 완전 제거, `charts/` 디렉토리 정리

## 참고 문서

- [Helm vs Kustomize 결정 문서](../docs/architecture/08-GITOPS_TOOLING_DECISION.md)
- [네임스페이스 전략 분석](../docs/architecture/09-NAMESPACE_STRATEGY_ANALYSIS.md)

## 현재 GitOps 구조

```
k8s/
├── base/                       # Kustomize Base
│   ├── deployment.yaml
│   ├── service.yaml
│   └── kustomization.yaml
├── overlays/                   # 도메인별 Overlay
│   ├── auth/
│   ├── my/
│   ├── scan/
│   ├── character/
│   ├── location/
│   ├── info/
│   └── chat/
├── namespaces/                 # 네임스페이스 정의
│   └── domain-based.yaml
└── networkpolicies/            # NetworkPolicy
    └── domain-isolation.yaml

argocd/
└── applications/
    └── ecoeco-appset-kustomize.yaml  # ApplicationSet

ansible/
└── playbooks/
    └── 10-namespaces.yml       # 네임스페이스 생성 자동화
```

---

**마지막 업데이트**: 2025-11-13  
**담당자**: EcoEco Backend Team
