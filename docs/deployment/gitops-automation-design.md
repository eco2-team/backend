# GitOps 기반 인프라 자동화 전환 설계

## 🎯 현재 문제점

### 현재 워크플로우 (스크립트 중심)

```bash
# 1. Terraform 수동 실행
cd terraform
terraform plan
terraform apply
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

# 2. Ansible 수동 실행
cd ../ansible
ansible-playbook site.yml
ansible-playbook playbooks/label-nodes.yml

# 3. ArgoCD 수동 배포
kubectl apply -f argocd/application-14nodes.yaml

# 문제점:
# ❌ 수동 개입 필요
# ❌ 실행 순서 보장 안됨
# ❌ 실패 시 재시도 로직 없음
# ❌ 상태 추적 어려움
# ❌ 간극 발생 (Terraform → Ansible → K8s)
```

---

## 🚀 제안: GitOps 기반 자동화 아키텍처

### 전체 흐름도

```yaml
┌─────────────────────────────────────────────────────────────────┐
│                  GitHub Repository (단일 진실의 원천)               │
│  ├── terraform/                                                  │
│  ├── ansible/                                                    │
│  ├── k8s/                                                        │
│  └── argocd/                                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Git Push / PR Merge
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│          Step 1: Atlantis (Terraform GitOps)                     │
│  - PR 생성 시 자동 `terraform plan`                               │
│  - PR 승인 후 자동 `terraform apply`                              │
│  - Outputs를 S3/ConfigMap에 자동 저장                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Terraform 완료 Webhook
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│    Step 2: ArgoCD Hooks (Ansible 실행)                           │
│  - PreSync Hook: Ansible site.yml 실행                           │
│  - Sync: Kubernetes 리소스 배포                                   │
│  - PostSync Hook: label-nodes.yml 실행                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 자동 완료
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│               Kubernetes Cluster (최종 상태)                      │
│  - 14 Nodes Running                                              │
│  - Applications Deployed                                         │
│  - Monitoring Active                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 상세 구현 방안

### Option 1: Atlantis + ArgoCD (권장 ⭐)

#### 1-1. Atlantis 설정 (Terraform GitOps)

```yaml
# atlantis.yaml (프로젝트 루트)
version: 3
automerge: false
delete_source_branch_on_merge: true

projects:
  - name: sesacthon-infrastructure
    dir: terraform
    workspace: production
    terraform_version: v1.5.0
    
    # Terraform 실행 후 자동 작업
    workflow: custom
    
workflows:
  custom:
    plan:
      steps:
        - init
        - plan
    
    apply:
      steps:
        - init
        - apply
        
        # ✅ Outputs를 K8s ConfigMap에 저장
        - run: |
            terraform output -json > /tmp/tf-outputs.json
            kubectl create configmap terraform-outputs \
              --from-file=/tmp/tf-outputs.json \
              --namespace=argocd \
              --dry-run=client -o yaml | kubectl apply -f -
        
        # ✅ ArgoCD Application Sync 트리거
        - run: |
            argocd app sync sesacthon-infrastructure \
              --prune --force
```

#### 1-2. ArgoCD Application (Ansible Hook 포함)

```yaml
# argocd/application-14nodes-gitops.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sesacthon-infrastructure
  namespace: argocd
spec:
  project: default
  
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: k8s
  
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    
    # ✅ Sync Hooks: Ansible 실행
    syncOptions:
      - CreateNamespace=true
    
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # PreSync Hook: Ansible site.yml 실행
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
---
apiVersion: batch/v1
kind: Job
metadata:
  name: ansible-bootstrap
  namespace: argocd
  annotations:
    argocd.argoproj.io/hook: PreSync      # ⚡ Sync 전 실행
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  template:
    spec:
      restartPolicy: Never
      
      # Terraform Outputs를 환경 변수로 주입
      envFrom:
        - configMapRef:
            name: terraform-outputs
      
      containers:
        - name: ansible
          image: cytopia/ansible:latest
          command:
            - /bin/bash
            - -c
            - |
              set -e
              
              # Git Clone
              git clone https://github.com/SeSACTHON/backend /workspace
              cd /workspace/ansible
              
              # Terraform Outputs에서 인벤토리 생성
              echo "$ANSIBLE_INVENTORY" > inventory/hosts.ini
              
              # Ansible 실행
              ansible-playbook site.yml -i inventory/hosts.ini
              
              echo "✅ Ansible Bootstrap Complete"
          
          volumeMounts:
            - name: ssh-key
              mountPath: /root/.ssh
              readOnly: true
      
      volumes:
        - name: ssh-key
          secret:
            secretName: k8s-cluster-key
            defaultMode: 0600

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # PostSync Hook: 노드 라벨링
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
---
apiVersion: batch/v1
kind: Job
metadata:
  name: label-nodes
  namespace: argocd
  annotations:
    argocd.argoproj.io/hook: PostSync     # ⚡ Sync 후 실행
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: argocd-application-controller
      
      containers:
        - name: kubectl
          image: bitnami/kubectl:latest
          command:
            - /bin/bash
            - -c
            - |
              set -e
              
              # Git Clone
              git clone https://github.com/SeSACTHON/backend /workspace
              cd /workspace/ansible
              
              # 노드 라벨링 실행
              ansible-playbook playbooks/label-nodes.yml \
                -i inventory/hosts.ini
              
              echo "✅ Node Labels Applied"
```

---

### Option 2: GitHub Actions + AWX (중간 복잡도)

```yaml
# .github/workflows/infrastructure.yml
name: Infrastructure as Code

on:
  push:
    branches: [main]
    paths:
      - 'terraform/**'
      - 'ansible/**'
  
  pull_request:
    branches: [main]
    paths:
      - 'terraform/**'

jobs:
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Job 1: Terraform Plan (PR)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  terraform-plan:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0
      
      - name: Terraform Init
        run: cd terraform && terraform init
      
      - name: Terraform Plan
        run: cd terraform && terraform plan -out=tfplan
      
      - name: Comment PR
        uses: actions/github-script@v6
        with:
          script: |
            const output = `### Terraform Plan
            \`\`\`
            ${process.env.PLAN_OUTPUT}
            \`\`\`
            `;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: output
            })

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Job 2: Terraform Apply (Main Branch)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  terraform-apply:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    
    outputs:
      terraform_outputs: ${{ steps.outputs.outputs }}
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
      
      - name: Terraform Apply
        run: |
          cd terraform
          terraform init
          terraform apply -auto-approve
      
      - name: Export Outputs
        id: outputs
        run: |
          cd terraform
          terraform output -json > /tmp/tf-outputs.json
          echo "outputs=$(cat /tmp/tf-outputs.json)" >> $GITHUB_OUTPUT
      
      - name: Save to S3
        run: |
          aws s3 cp /tmp/tf-outputs.json \
            s3://sesacthon-terraform-state/outputs/latest.json

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Job 3: Trigger AWX Ansible Job
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ansible-bootstrap:
    needs: terraform-apply
    runs-on: ubuntu-latest
    
    steps:
      - name: Trigger AWX Job Template
        run: |
          curl -X POST \
            https://awx.sesacthon.com/api/v2/job_templates/1/launch/ \
            -H "Authorization: Bearer ${{ secrets.AWX_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d '{
              "extra_vars": ${{ needs.terraform-apply.outputs.terraform_outputs }}
            }'
      
      - name: Wait for Job Completion
        run: |
          # AWX Job 상태 폴링
          while true; do
            STATUS=$(curl -s \
              https://awx.sesacthon.com/api/v2/jobs/$JOB_ID/ \
              -H "Authorization: Bearer ${{ secrets.AWX_TOKEN }}" \
              | jq -r '.status')
            
            if [ "$STATUS" = "successful" ]; then
              echo "✅ Ansible Job Complete"
              break
            elif [ "$STATUS" = "failed" ]; then
              echo "❌ Ansible Job Failed"
              exit 1
            fi
            
            sleep 10
          done

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Job 4: Sync ArgoCD Application
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  argocd-sync:
    needs: ansible-bootstrap
    runs-on: ubuntu-latest
    
    steps:
      - name: ArgoCD Sync
        run: |
          argocd login argocd.sesacthon.com \
            --username admin \
            --password ${{ secrets.ARGOCD_PASSWORD }}
          
          argocd app sync sesacthon-infrastructure \
            --prune --force
          
          argocd app wait sesacthon-infrastructure \
            --timeout 600
```

---

### Option 3: Flux + Terraform Controller (최소 스크립트)

```yaml
# flux-system/terraform-controller.yaml
apiVersion: infra.contrib.fluxcd.io/v1alpha1
kind: Terraform
metadata:
  name: sesacthon-infrastructure
  namespace: flux-system
spec:
  # Git 소스
  sourceRef:
    kind: GitRepository
    name: flux-system
  
  # Terraform 경로
  path: ./terraform
  
  # 자동 적용
  interval: 5m
  approvePlan: auto
  
  # Outputs를 Secret으로 저장
  writeOutputsToSecret:
    name: terraform-outputs
  
  # 완료 후 Webhook
  runnerPodTemplate:
    spec:
      containers:
        - name: tf-runner
          image: hashicorp/terraform:1.5.0
---
# flux-system/ansible-controller.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: ansible-sync
  namespace: flux-system
spec:
  schedule: "*/5 * * * *"  # 5분마다 체크
  
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: ansible
              image: cytopia/ansible:latest
              command:
                - /bin/bash
                - -c
                - |
                  # Terraform Outputs 확인
                  LAST_RUN=$(kubectl get secret terraform-outputs \
                    -n flux-system \
                    -o jsonpath='{.metadata.annotations.lastRun}')
                  
                  # 변경사항이 있으면 Ansible 실행
                  if [ "$LAST_RUN" != "$CURRENT_TIME" ]; then
                    git clone https://github.com/SeSACTHON/backend /workspace
                    cd /workspace/ansible
                    ansible-playbook site.yml
                  fi
```

---

## 📊 비교표

| 구분 | 현재 (스크립트) | Option 1 (Atlantis+ArgoCD) | Option 2 (GitHub+AWX) | Option 3 (Flux) |
|------|----------------|---------------------------|----------------------|-----------------|
| **수동 개입** | ❌ 매번 필요 | ✅ 자동 | ✅ 자동 | ✅ 자동 |
| **간극 제거** | ❌ 큼 | ✅ Hook으로 연결 | ⚠️ Job 연결 | ✅ Controller 연결 |
| **재시도** | ❌ 수동 | ✅ ArgoCD 자동 | ⚠️ 스크립트 필요 | ✅ CronJob 자동 |
| **상태 추적** | ❌ 없음 | ✅ ArgoCD UI | ⚠️ GitHub Actions | ✅ Flux UI |
| **복잡도** | 낮음 | **중간** ⭐ | 중간 | 높음 |
| **학습 곡선** | 없음 | 중간 | 낮음 | 높음 |
| **비용** | 무료 | 무료 | 무료 | 무료 |
| **권장도** | - | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

---

## 🎯 Eco² 프로젝트 권장 방안

### 단계별 전환 계획

```yaml
Phase 1: 현재 → GitHub Actions (1주)
  - .github/workflows/infrastructure.yml 작성
  - Terraform Plan/Apply 자동화
  - 간극: GitHub Actions → Ansible 스크립트 호출 (여전히 존재)

Phase 2: GitHub Actions → Atlantis (2주)
  - Atlantis 설치 (K8s 또는 별도 서버)
  - PR 기반 Terraform 자동화
  - 간극: Atlantis Webhook → Ansible 스크립트 (개선됨)

Phase 3: Atlantis + ArgoCD Hooks (최종) (2주) ⭐
  - ArgoCD PreSync/PostSync Hook 설정
  - Ansible을 K8s Job으로 실행
  - 간극: 완전 제거 (Git Push → 완전 자동)
```

---

## 💡 스크립트 최소화 전략

### 제거 가능한 스크립트

```bash
# ❌ 제거 대상
scripts/deployment/deploy-full-stack.sh    # → Atlantis Workflow
scripts/deployment/update-inventory.sh     # → Terraform Output → ConfigMap
scripts/cluster/validate-cluster.sh        # → ArgoCD Health Check
```

### 남겨야 할 스크립트 (최소)

```bash
# ✅ 유지 (응급 복구용)
scripts/maintenance/destroy-with-cleanup.sh   # 인프라 완전 삭제
scripts/diagnostics/check-cluster-health.sh   # 수동 디버깅
```

---

## 🚀 최종 GitOps 워크플로우 (Option 1)

```yaml
┌────────────────────┐
│  Developer         │
└────────┬───────────┘
         │
         │ 1. Git Push (terraform/*, ansible/*)
         ↓
┌────────────────────────────────┐
│  GitHub Repository             │
│  - terraform/                  │
│  - ansible/                    │
│  - k8s/                        │
└────────┬───────────────────────┘
         │
         │ 2. Webhook
         ↓
┌────────────────────────────────┐
│  Atlantis (Terraform GitOps)   │
│  - terraform plan (PR)         │
│  - terraform apply (Merge)     │
│  - Output → ConfigMap          │
└────────┬───────────────────────┘
         │
         │ 3. Trigger ArgoCD Sync
         ↓
┌────────────────────────────────┐
│  ArgoCD (K8s GitOps)           │
│  - PreSync: Ansible Bootstrap  │ ← ⚡ 간극 제거!
│  - Sync: K8s Manifests         │
│  - PostSync: Label Nodes       │ ← ⚡ 간극 제거!
└────────┬───────────────────────┘
         │
         │ 4. 자동 완료
         ↓
┌────────────────────────────────┐
│  Kubernetes Cluster            │
│  ✅ 14 Nodes Running           │
│  ✅ Apps Deployed              │
│  ✅ Monitoring Active          │
└────────────────────────────────┘

총 개입: 0회
총 스크립트: 0개
간극: 완전 제거
```

---

**작성일**: 2025-11-08  
**권장**: Option 1 (Atlantis + ArgoCD Hooks)  
**다음 단계**: Atlantis 설치 및 ArgoCD Hook 작성

