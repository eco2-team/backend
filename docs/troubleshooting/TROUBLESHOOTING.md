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
# - workloads/domains/*/base/deployment.yaml

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

---

## 5. Incident Log – Calico/Tigera 재배포 실패 (2025-11-18)

| 시각(KST) | Action | 결과/메시지 |
|-----------|--------|-------------|
| 19:00~20:30 | `kubectl get application dev-root -n argocd` | 하위 앱 `dev-external-dns`, `dev-external-secrets`, `dev-grafana`, `dev-calico`가 OutOfSync·Missing. 모든 노드 `node.kubernetes.io/network-unavailable` taint 유지. |
| 20:30 | `kubectl get application dev-calico -o yaml` | `operationState.message` = “waiting for deletion of operator.tigera.io/Installation/default”. Argo는 tigera 리소스를 prune만 반복. |
| 20:35~21:00 | SSA 도입 시도<br>`kubectl get application dev-calico -o jsonpath='{.spec.syncPolicy.syncOptions}'` → patch로 `ServerSideApply=true` 추가 | Annotation 256KiB 에러는 해소되었으나 기존 Installation CR이 삭제되지 않아 여전히 “Deletion 대기” 상태. |
| 21:00 | `kubectl patch installation.operator.tigera.io default --type='json' -p='[{"op":"remove","path":"/metadata/finalizers/0"}]'` (두 번) | `Installation/default` 삭제 성공. 그러나 관련 CRD(`installations.operator.tigera.io`, `apiservers.operator.tigera.io`) 및 Ansible 잔존 리소스 때문에 Argo가 새 Sync를 시작하지 못함. |
| 21:10~21:40 | `kubectl delete crd installations.operator.tigera.io apiservers.operator.tigera.io` 등 Calico CRD 정리 | 제거 완료했으나 Application OperationState가 reset되지 않아 컨트롤러 이벤트가 더 이상 갱신되지 않음. `kubectl patch application dev-calico ... {"status":{"reconciledAt":null}}` 필요했으나 네트워크 불능으로 효과 확인 불가. |
| 21:45 이후 | `kubectl logs -n argocd argocd-application-controller-0` | Pod는 Running이나 노드(10.0.3.88) kubelet 포트 연결 실패로 로그 수집 실패. 모든 노드가 `node.kubernetes.io/network-unavailable`이라 Logging/PortForward 모두 차단. |
| 22:00 | 결론: Calico를 GitOps(Helm)에서 제거하고 Ansible Playbook(`04-cni-install.yml`)로만 설치·운영. GitOps 경로(`clusters/dev/apps/05-calico.yaml`, `platform/helm/calico/**`) 삭제. |

> 📌 Calico/Tigera GitOps 충돌 사례, 전체 Application 리스트, 이벤트/describe 출력은 `docs/troubleshooting/CALICO_GITOPS_INCIDENT_2025-11-18.md` 문서에서 확인하세요. 여기서는 다른 증상 공통 절차만 유지합니다.

---

## 6. Incident Log – ALB 503 (TargetGroup empty) due to missing providerID (2025-12-09)

| 시각(KST) | Action | 결과/메시지 |
|-----------|--------|-------------|
| ~10:00 | 외부 503 발생, `describe-target-health` 전부 `[]` | ALB에는 타겟 미등록 상태 |
| 10:05~10:20 | 컨트롤러 로그 확인 | `Reconciler error … providerID is not specified for node: k8s-ingress-gateway` 반복 |
| 10:20 | `kubectl get nodes -o custom-columns=NAME,PID` | `k8s-ingress-gateway`, `k8s-master`에 providerID 없음 확인 |
| 10:25 | 노드 메타데이터로 patch | `kubectl patch node <node> -p '{"spec":{"providerID":"aws:///<az>/<instance-id>"}}'` |
| 10:30 | ALB 컨트롤러 재시작 후 TG 확인 | Targets 등록, 503 해소 |

요약 및 재발 방지
- 원인: ALB 컨트롤러 타겟 타입 `instance` 사용 시, providerID 없는 노드가 하나라도 있으면 TGB 리콘실이 실패하여 타겟이 비어 503 발생.
- 조치: 문제 노드(providerID 없음)를 `aws:///<AZ>/<INSTANCE_ID>`로 패치 후 컨트롤러 재시작. 필요 시 `scripts/utilities/fix-providerid.sh`로 일괄 적용.
- 예방: Ansible `03-1-set-provider-id.yml`의 필터에 `k8s-ingress-gateway`(및 control-plane) 포함, 또는 Ingress `alb.ingress.kubernetes.io/target-type: ip`로 전환하여 providerID 의존도 제거(보안그룹은 Pod CIDR 고려).
