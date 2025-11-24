# Local Cluster Bootstrap Guide

> **목적**: 로컬 장비(또는 개발용 맥)에서 SeSACTHON GitOps 클러스터를 처음부터 올릴 때 필요한 순서를 한 문서에 정리한다. Terraform → Ansible → ArgoCD Root-App 순서를 그대로 따라가면 v0.7.4 Sync Wave 구성이 자동으로 재현된다.

---

## 1. 사전 준비

| 항목 | 내용 |
|------|------|
| 요구 도구 | Terraform ≥ 1.7, Ansible ≥ 2.16, kubectl ≥ 1.28, helm ≥ 3.14, AWS CLI |
| 자격 증명 | AWS 계정 액세스 키 (VPC/EC2/SSM 권한), `~/.aws/credentials` 또는 `AWS_PROFILE` |
| 네트워크 | Terraform/Ansible 실행 호스트에서 AWS API, GitHub, SSM 접근 가능해야 함 |
| SSH 키 | `terraform/modules/ec2`에서 정의한 키페어에 해당하는 개인 키 (Ansible용) |

> 참고: Ansible 부트스트랩 세부 설명은 `docs/architecture/deployment/ANSIBLE_BOOTSTRAP_PLAN.md`를 함께 확인한다.

---

## 2. 전체 흐름

```
Terraform (네트워크·노드·SSM) → Ansible (kubeadm + Calico + ArgoCD) → ArgoCD Root-App (Sync Wave 0~70)
```

---

## 3. 단계별 절차

### Step 0. 리포지토리 준비

```bash
git clone https://github.com/SeSACTHON/backend.git
cd backend
```

- 작업 브랜치: `refactor/gitops-sync-wave` (최신 기준)
- `terraform/env/dev.tfvars` 혹은 `prod.tfvars`의 변수값을 실제 AWS 계정 정보에 맞게 갱신한다.

### Step 1. Terraform으로 인프라 생성

```bash
cd terraform
terraform init
terraform apply -var-file env/dev.tfvars  # prod 환경이면 prod.tfvars
```

- 생성 범위: VPC, Subnet, EC2 노드(14대), IAM Role(IRSA), SSM Parameter(Secrets/Outputs), Route53 등.
- 작업 완료 후 아래 명령으로 주요 출력 확인:

```bash
terraform output
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
terraform output -raw kubeconfig > ~/.kube/sesacthon-dev  # 필요 시
```

> **체크포인트**: `aws ssm get-parameter --name /sesacthon/dev/data/postgres-password` 등 핵심 파라미터가 모두 존재해야 ExternalSecrets가 정상 동작한다.

### Step 2. Ansible로 Kubernetes 부트스트랩

```bash
cd ../ansible
ansible-galaxy install -r requirements.yml  # 필요한 경우
```

- 주요 작업 순서:
  1. OS 준비 (`common`, `docker`, `kubernetes` roles)
  2. `kubeadm init / join`으로 마스터·워커 결합
  3. Calico VXLAN (playbooks/04-cni-install.yml)
  4. 노드 라벨·taint 적용 (`playbooks/label-nodes.yml`)
  5. ArgoCD 네임스페이스 및 초기 설치 (site.yml 마지막 단계)

- 완료 후 `~/.kube/config`를 업데이트하거나, 마스터 노드의 `/etc/kubernetes/admin.conf`를 로컬로 복사한다.

### Step 3. ArgoCD Root-App 배포

1. ArgoCD 접속 (포트포워딩 등) 또는 `kubectl`로 직접 Apply.

```bash
# ArgoCD가 설치되어 있음을 전제
kubectl apply -n argocd -f clusters/dev/root-app.yaml
# prod 환경은 clusters/prod/root-app.yaml
```

2. 초기 Sync 확인:

```bash
kubectl get applications -n argocd
argocd app get dev-root   # argocd CLI 사용 시
```

3. Root-App는 `clusters/{env}/apps` 디렉터리 이하의 모든 Sync Wave 파일을 자동으로 생성/동기화한다.

### Step 4. Sync Wave 진행 모니터링

| Wave | 주요 내용 | 확인 명령 |
|------|-----------|-----------|
| 0 | CRDs | `kubectl get crd | grep monitoring.coreos.com` |
| 5/6 | Calico / NetworkPolicy | `kubectl get pods -n kube-system -l k8s-app=calico-node` |
| 10/11 | ExternalSecrets Operator/CR | `kubectl get externalsecret -A` |
| 15/16 | ALB Controller / ExternalDNS | `kubectl get deployment -n kube-system aws-load-balancer-controller` |
| 20/21 | kube-prometheus-stack / Grafana | `kubectl get pods -n prometheus`, `kubectl get pods -n grafana` |
| 25/35 | Data Operators / CR | `kubectl get postgres -A`, `kubectl get redisfailover -A` |
| 60/70 | API + Ingress | `kubectl get deploy -n auth`, `kubectl get ingress -A` |

> **트러블슈팅 가이드**:
> - ArgoCD 배포 문제 (CrashLoopBackOff, 리디렉션 오류): `docs/troubleshooting/ARGOCD_DEPLOYMENT_ISSUES.md`
> - 기타 Sync Wave 문제: `docs/troubleshooting/TROUBLESHOOTING.md` 18.x~20.x 항목

### Step 5. Post-check & 로컬 개발용 설정

- `kubectl get nodes -L tier,workload,domain`
- `kubectl -n grafana port-forward svc/grafana 3000:80` 후 Web UI 접속, ExternalSecret에서 주입된 admin 패스워드 확인.
- 필요 시 `bin/helm`으로 각 Helm 차트를 `helm template` / `helm lint` 재확인 (`docs/refactor/gitops-sync-wave-TODO.md` 15번 항목 참고).

---

## 4. 자주 묻는 질문

1. **Terraform 없이 이미 만들어진 EC2를 재사용할 수 있나요?**  
   - 권장하지 않는다. Sync Wave 문서 및 ExternalSecret 경로가 Terraform output과 강하게 연결되어 있기 때문에, 동일한 변수/SSM 구조를 유지해야 한다.

2. **Grafana를 kube-prometheus-stack과 다시 묶고 싶다면?**  
   - `platform/helm/kube-prometheus-stack/{env}/patch-application.yaml`의 `helm.valuesObject.grafana.enabled`를 `true`로 변경하고 Wave 21 Grafana Application을 제거하면 된다. 배경 설명은 `docs/architecture/operator/OPERATOR_SOURCE_SPEC.md` 참고.

3. **로컬 Kubernetes (kind, k3d)에서 테스트 가능합니까?**  
   - 현 구성은 AWS 인프라(LoadBalancer, SSM, IRSA)에 의존하므로 kind/k3d만으로는 완전한 동작을 보장하지 않는다. 로컬 단일 노드 테스트가 필요하면 ExternalSecret/ALB/IRSA 섹션을 Mocking 해야 한다.

---

## 5. 참고 문서

- `docs/architecture/deployment/ANSIBLE_BOOTSTRAP_PLAN.md`
- `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md`
- `docs/architecture/operator/OPERATOR_SOURCE_SPEC.md`
- `docs/troubleshooting/TROUBLESHOOTING.md`

---

### Step 1.5. AWS 자격증명 Secret 생성 (임시 IRSA 대체)

IRSA/OIDC가 준비되지 않았다면 ALB Controller·ExternalDNS·External Secrets Operator는 AWS Access Key/Secret Key가 담긴 Secret을 필요로 합니다.

#### 1. Ansible 자동 프롬프트 (권장)
- `ansible/site.yml` → `roles/argocd` 실행 중 Root-App 배포 직전에 **Access Key/Secret Key 입력을 요청**합니다.
- 키를 입력하면 Ansible이 `kubectl apply -f -`로 `aws-global-credentials` Secret을 자동 생성합니다.
  - 네임스페이스: `kube-system`, `platform-system`
  - 비활성화하려면 `ansible-playbook ... -e create_aws_credentials_secret=false` 사용
  - CI 자동화에서는 `-e aws_access_key_id=XXX -e aws_secret_access_key=YYY`로 미리 주입 가능

#### 2. 수동 생성 (Fallback)
```bash
kubectl create secret generic aws-global-credentials \
  -n kube-system \
  --from-literal=aws_access_key_id=<ACCESS_KEY_ID> \
  --from-literal=aws_secret_access_key=<SECRET_ACCESS_KEY>

kubectl create secret generic aws-global-credentials \
  -n platform-system \
  --from-literal=aws_access_key_id=<ACCESS_KEY_ID> \
  --from-literal=aws_secret_access_key=<SECRET_ACCESS_KEY>
```

> **주의**
> - Secret은 Git에 커밋하지 말고, 키를 교체하면 `kubectl delete secret aws-global-credentials -n <ns>` 후 재생성하세요.
> - IRSA를 다시 사용할 준비가 되면 `terraform.tfvars`에서 `enable_irsa = true`로 전환하고 본 Secret을 제거합니다.

> 위 절차를 기준으로 로컬에서 테스트 클러스터를 올리고, GitOps Sync Wave 0→70까지 순차적으로 검증한다. 신규 작업자는 본 문서를 onboarding checklist로 사용한다.


