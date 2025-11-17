# Rapid Diagnostics Runbook

> README.md가 내비게이션 허브를 담당하며, 이 문서는 **현장 즉응을 위한 진단/복구 절차**를 담고 있습니다. 증상별 상세 사례는 README에서 링크된 전용 문서를 참고하세요.

---

## 1. 상태 점검 절차

### 1.1 클러스터 스냅샷
```bash
# 노드 · Pod · ArgoCD Application
kubectl get nodes -o wide
kubectl get pods -A
kubectl get applications -n argocd
kubectl get applicationset -n argocd

# 노드 라벨/taint 확인
kubectl get nodes --show-labels | grep sesacthon.io
kubectl describe node <node> | grep -A4 Taints
```

### 1.2 증상별 1차 체크
| 증상 | 즉시 확인 | 후속 문서 |
|------|-----------|-----------|
| 노드 NotReady / CoreDNS Pending | `kubectl describe node <node>` / `kubectl get pods -n kube-system` | `ansible-label-sync.md#3` |
| ArgoCD Unknown / OutOfSync | `kubectl describe application <app>` / `argocd app logs <app>` | `argocd-applicationset-patterns.md`, `gitops-deployment.md` |
| ALB/Service 생성 실패 | `kubectl logs -n kube-system deploy/aws-load-balancer-controller` | `gitops-deployment.md#10`, `cluster-cases.md` |
| GHCR ImagePullBackOff | `kubectl describe pod <pod>` Events | `gitops-deployment.md#4` |
| IRSA / ExternalSecret 지연 | `kubectl get externalsecret -A`, ESO logs | `cluster-cases.md`, `ansible-label-sync.md` |

> IRSA Hook가 600초 이상 대기하는 경우, Wave 10~11 전에 필수 Secret을 수동으로 준비해 Hook 실패를 방지하세요.
>
> 🔐 **AWS 자격증명 Secret 체크**  
> - IRSA 미사용 구성에서는 `aws-global-credentials` Secret이 `kube-system`과 `platform-system` 네임스페이스에 반드시 존재해야 합니다.  
> - Secret이 없다면 `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md` Step 1.5에 따라 즉시 생성하세요.

---

## 2. 부트스트랩 체크리스트

```bash
# 1. vCPU 한도 확인
aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region ap-northeast-2

# 2. 잔존 리소스 정리
../../scripts/maintenance/destroy-with-cleanup.sh

# 3. 노드 라벨/taint 동기화
# - docs/infrastructure/k8s-label-annotation-system.md
# - ansible/playbooks/fix-node-labels.yml
# - workloads/apis/*/base/deployment.yaml

# 4. Git 상태
git status
git push origin <branch>

# 5. Ansible 부트스트랩
ansible-playbook -i ansible/inventory/hosts.ini ansible/site.yml
```

- **CNI 확인**: `kubectl wait --for=condition=ready pod -l k8s-app=calico-node -n calico-system --timeout=300s`  
- **IRSA 선행 조건**: `/sesacthon/{env}/iam/*` SSM 파라미터 존재 여부 확인 → ExternalSecrets가 읽기 전에 문제 없도록 함.

---

## 3. Incident Response Flow

1. **로그 수집**
   ```bash
   kubectl get events -A --sort-by='.lastTimestamp'
   kubectl logs -n argocd sts/argocd-application-controller --tail=100
   ```
2. **영향 범위 파악**
   - OutOfSync/Unknown Application 수
   - Pending/CrashLoop Pod가 속한 네임스페이스
   - AWS ALB/TargetGroup 잔존 여부 (`aws elbv2 describe-*`)
3. **긴급 복구**
   - 각 문서의 “긴급 복구” 섹션 실행
   - 필요 시 `kubectl scale`, `argocd app sync --force`, `kubectl rollout undo`
4. **근본 해결**
   - Git에서 Helm/Kustomize 수정 → PR → `argocd app diff`
   - Terraform/Ansible 변경은 재적용 전 README 체크리스트 재확인

---

## 4. 모니터링 지표 & 에스컬레이션

| 지표 | 정상 | 경보 기준 | 대응 |
|------|------|-----------|------|
| Ready Nodes | 14 | < 13 | 라벨/taint 재적용, CNI 확인 |
| ArgoCD OutOfSync | 0 | ≥ 3 (10분 이상) | Webhook/IRSA/네트워크 점검 |
| ExternalSecret 상태 | All Synced | Pending/Failed ≥1 | SSM 권한, IRSA Secret 확인 |
| AWS TargetGroup 잔존 | 0 | 존재 시 destroy 실패 | `scripts/cleanup-vpc-resources.sh` 실행 |

- **지원 채널**  
  - GitHub Issues: https://github.com/SeSACTHON/backend/issues  
  - Slack: #backend-support (로그/명령 결과 첨부)  
  - AWS 리소스 장애: Terraform 담당자와 즉시 공유

---

> 📌 추가 사례·심층 분석은 README의 “빠른 참조” 및 문서 카탈로그에서 확인하세요. 이 Runbook은 “무엇을 어떤 순서로 점검/복구할지”에 집중합니다.
