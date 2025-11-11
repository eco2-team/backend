# 🔧 스크립트 및 유틸리티 전체 업데이트

## 🎯 PR 목적

14-Node 클러스터 배포/관리/테스트를 위한 모든 스크립트를 업데이트하고, 운영 편의성을 높이는 유틸리티를 추가합니다.
### Troubleshooting 문서 (14개)
인프라, Ansible, Monitoring, ArgoCD, Atlantis, Database 관련 실전 트러블슈팅

### Cluster 관리 스크립트 (3개)
- `deploy.sh`: 14-Node 자동 배포
- `destroy.sh`: 클러스터 정리
- `push-ssh-keys.sh`: SSH 키 배포

### Utilities 스크립트 (8개)
- `ssh-master.sh`: 노드 SSH 접속
- `create-atlantis-secret.sh`: Atlantis Secret
- `create-argocd-ssh-secret.sh`: ArgoCD SSH
- `fix-atlantis-config.sh`: Atlantis 설정 수정
- 기타 4개

### Testing 스크립트 (3개)
- `verify-cluster.sh`: 클러스터 검증
- `verify-gitops.sh`: GitOps 검증
- `test-github-actions.sh`: GitHub Actions 테스트

### Kubernetes 리소스
- `k8s/ingress/`: Ingress Controller
- `k8s/atlantis/`: Atlantis 배포

### 문서
- `V0.7.0_COMPLETION_GUIDE.md`

## 🚀 사용법

```bash
# 배포
./scripts/cluster/deploy.sh

# 정리
./scripts/cluster/destroy.sh

# 노드 접속
./scripts/utilities/ssh-master.sh auth
```

## ✅ 체크리스트
- [x] 스크립트 15개
- [x] K8s 리소스
- [x] 문서 추가

---
자세한 내용은 커밋 메시지를 참조하세요.