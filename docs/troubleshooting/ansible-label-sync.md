# Ansible 노드 라벨과 Kubernetes Manifest 동기화 문제

> **작성일**: 2025-11-16  
> **버전**: v0.7.4  
> **아키텍처**: 14-Node GitOps + Ansible Bootstrap  
> **실제 클러스터 데이터 포함** ✅

## 📋 목차

- [1. 노드 라벨과 nodeSelector 불일치](#1-노드-라벨과-nodeselector-불일치)
- [2. Ansible root-app.yaml 경로 오류](#2-ansible-root-appyaml-경로-오류)
- [3. CNI 순환 의존성 (Chicken-and-Egg)](#3-cni-순환-의존성-chicken-and-egg)
- [4. ArgoCD AppProject 미생성](#4-argocd-appproject-미생성)
- [5. ArgoCD NetworkPolicy DNS Timeout](#5-argocd-networkpolicy-dns-timeout)
- [6. Application targetRevision 불일치](#6-application-targetrevision-불일치)
- [7. Kustomize 디렉토리 구조 문제](#7-kustomize-디렉토리-구조-문제)
- [8. ApplicationSet 템플릿 따옴표 오류](#8-applicationset-템플릿-따옴표-오류)
- [9. CoreDNS Pending (모든 노드 Taint)](#9-coredns-pending-모든-노드-taint)
- [10. 베스트 프랙티스](#10-베스트-프랙티스)

---

## 1. 노드 라벨과 nodeSelector 불일치

### 문제

**증상**:
```bash
# API Deployments가 배포되지 않음
kubectl get pods -n auth
No resources found in auth namespace.

# 또는 Pending 상태
NAME                       READY   STATUS    RESTARTS   AGE
auth-api-bff55b88f-xxxxx   0/1     Pending   0          5m
```

**Pod describe 결과**:
```
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  5m    default-scheduler  0/14 nodes are available: 14 node(s) didn't match Pod's node selector.
```

### 원인

Ansible playbook (`ansible/playbooks/fix-node-labels.yml`)이 설정하는 노드 라벨과 Kubernetes Deployment의 `nodeSelector`가 불일치:

**실제 클러스터의 노드 라벨** (2025-11-16 수집):
```bash
$ kubectl get nodes k8s-api-auth --show-labels
NAME           STATUS   LABELS
k8s-api-auth   Ready    sesacthon.io/node-role=api,
                        sesacthon.io/service=auth,
                        workload=api,
                        domain=auth,
                        tier=business-logic,
                        phase=1
```

**Deployment가 요구하는 nodeSelector** (표준 manifest):
```yaml
# workloads/domains/auth/base/deployment.yaml
spec:
  template:
    spec:
      nodeSelector:
        service: auth  # ✅ Ansible 라벨과 일치
```

**라벨 매핑 테이블**:

| 리소스 | Ansible 라벨 (실제) | Deployment nodeSelector | 결과 |
|--------|-------------------|-------------------------|------|
| API-auth | `sesacthon.io/service=auth` | `service: auth` | ✅ 일치 |
| API-my | `sesacthon.io/service=my` | `service: my` | ✅ 일치 |
| PostgreSQL | `sesacthon.io/infra-type=postgresql` | `infra-type: postgresql` | ✅ 일치 |
| Redis | `sesacthon.io/infra-type=redis` | `infra-type: redis` | ✅ 일치 |
| Worker-Storage | `sesacthon.io/worker-type=storage` | `worker-type: storage` | ✅ 일치 |

**영향받는 서비스**: 전체 9개 (auth, my, scan, character, location, info, chat + PostgreSQL + Redis)

### 해결

#### 1. Kubernetes Manifests 수정

모든 deployment의 nodeSelector를 Ansible 라벨과 일치시킴:

**API Services** (7개):
```yaml
# workloads/domains/auth/base/deployment.yaml (수정 후)
spec:
  template:
    spec:
      nodeSelector:
        sesacthon.io/service: auth  # ✅ Ansible 라벨과 일치
      tolerations:
        - key: domain
          operator: Equal
          value: auth
          effect: NoSchedule
```

**PostgreSQL**:
```yaml
# platform/cr/base/postgres-cluster.yaml
spec:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: sesacthon.io/infra-type  # ✅ 변경
              operator: In
              values:
                - postgresql
  tolerations:
    - key: sesacthon.io/infrastructure  # ✅ 변경
      operator: Equal
      value: "true"
      effect: NoSchedule
```

**Redis**:
```yaml
# platform/cr/dev/redis-dev-patch.yaml
spec:
  redis:
    nodeSelector:
      sesacthon.io/infra-type: redis  # ✅ 변경
    tolerations:
      - key: sesacthon.io/infrastructure
        operator: Equal
        value: "true"
        effect: NoSchedule
  sentinel:
    nodeSelector:
      sesacthon.io/infra-type: redis
    tolerations:
      - key: sesacthon.io/infrastructure
        operator: Equal
        value: "true"
        effect: NoSchedule
```

#### 2. 수정된 파일 목록

- ✅ `workloads/domains/auth/base/deployment.yaml`
- ✅ `workloads/domains/my/base/deployment.yaml`
- ✅ `workloads/domains/scan/base/deployment.yaml`
- ✅ `workloads/domains/character/base/deployment.yaml`
- ✅ `workloads/domains/location/base/deployment.yaml`
- ✅ `workloads/domains/info/base/deployment.yaml`
- ✅ `workloads/domains/chat/base/deployment.yaml`
- ✅ `platform/cr/base/postgres-cluster.yaml`
- ✅ `platform/cr/dev/redis-dev-patch.yaml`
- ✅ `docs/infrastructure/k8s-label-annotation-system.md`

#### 3. 검증 (실제 클러스터 결과)

**노드 라벨 확인**:
```bash
$ kubectl get nodes -l sesacthon.io/service=auth --show-labels
NAME           STATUS   LABELS
k8s-api-auth   Ready    sesacthon.io/service=auth,sesacthon.io/node-role=api,domain=auth  # ✅
```

**Deployment nodeSelector 확인**:
```bash
$ kubectl get deploy auth-api -n auth -o yaml | grep -A 3 'nodeSelector:'
      nodeSelector:
        sesacthon.io/service: auth  # ✅ 일치
```

**Pod 스케줄링 성공 확인** (2025-11-16 실제 클러스터):
```bash
$ kubectl get pods -n auth -o wide
NAME                       READY   STATUS             NODE           
auth-api-bff55b88f-hqlcd   0/1     ImagePullBackOff   k8s-api-auth  # ✅ 올바른 노드에 배치

$ kubectl get pods -n my -o wide
my-api-76b4fcbf57-ndds6    0/1     ImagePullBackOff   k8s-api-my    # ✅

$ kubectl get pods -n scan -o wide
scan-api-7c7fccbdbf-49gg2  0/1     ImagePullBackOff   k8s-api-scan  # ✅
```

**전체 7개 API Services 스케줄링 성공**:
```bash
auth-api       → k8s-api-auth       ✅
my-api         → k8s-api-my         ✅
scan-api       → k8s-api-scan       ✅
character-api  → k8s-api-character  ✅
location-api   → k8s-api-location   ✅
info-api       → k8s-api-info       ✅
chat-api       → k8s-api-chat       ✅
```

⚠️ **ImagePullBackOff는 별도 문제** (GHCR 인증 필요), **스케줄링은 성공** ✅

**커밋**:
- `f191d18` - fix: Ansible 노드 라벨과 Kubernetes manifest 동기화

---

## 2. Ansible root-app.yaml 경로 오류

### 문제

**Ansible 실행 로그**:
```
TASK [argocd : root-app.yaml 복사 (Master 노드로)] *****************************
[ERROR]: Task failed: Unexpected AnsibleActionFail error: Could not find or access 
'/Users/mango/workspace/SeSACTHON/backend/ansible/../../argocd/root-app.yaml' on the Ansible Controller.
fatal: [k8s-master]: FAILED!
```

**결과**:
- ArgoCD는 설치되었지만 root-app이 배포되지 않음
- Child applications (Calico, Namespaces, APIs 등) 전혀 생성 안 됨
- GitOps 배포 체인 전체가 중단됨

### 원인

GitOps 리팩토링으로 `argocd/` 디렉토리가 `clusters/dev/`, `clusters/prod/`로 이동했는데, Ansible playbook이 옛날 경로를 참조:

```yaml
# ansible/roles/argocd/tasks/main.yml (수정 전)
- name: root-app.yaml 복사 (Master 노드로)
  copy:
    src: "{{ playbook_dir }}/../../../argocd/root-app.yaml"  # ❌ 경로 없음
    dest: /tmp/root-app.yaml
```

### 해결

```yaml
# ansible/roles/argocd/tasks/main.yml (수정 후)
- name: root-app.yaml 복사 (Master 노드로)
  copy:
    src: "{{ playbook_dir }}/../../clusters/dev/root-app.yaml"  # ✅ 새 경로
    dest: /tmp/root-app.yaml
    mode: '0644'
```

**환경 분리 고려** (prod 배포 시):
```yaml
- name: root-app.yaml 복사 (환경별)
  copy:
    src: "{{ playbook_dir }}/../../clusters/{{ deploy_env | default('dev') }}/root-app.yaml"
    dest: /tmp/root-app.yaml
    mode: '0644'
  vars:
    deploy_env: "{{ lookup('env', 'DEPLOY_ENV') }}"
```

### 검증

```bash
# root-app 배포 확인
kubectl get application dev-root -n argocd
NAME       SYNC STATUS   HEALTH STATUS
dev-root   OutOfSync     Healthy  # ✅ 생성됨

# Child applications 생성 확인
kubectl get applications -n argocd
# 예상: dev-namespaces, dev-crds, dev-calico, dev-apis 등 15+ applications
```

**실제 클러스터 결과** (2025-11-16):
```bash
$ kubectl get applications -n argocd | wc -l
24  # ✅ 23개 applications 생성됨 (root-app 포함)
```

---

## 3. CNI 순환 의존성 (Chicken-and-Egg)

### 문제

**증상**:
```bash
kubectl get nodes
NAME         STATUS     ROLES           AGE   VERSION
k8s-master   NotReady   control-plane   5m    v1.28.4
k8s-api-*    NotReady   <none>          3m    v1.28.4
# 모든 14개 노드가 NotReady

kubectl describe node k8s-master
Conditions:
  Ready   False   KubeletNotReady   
  Message: container runtime network not ready: 
           NetworkReady=false 
           reason:NetworkPluginNotReady 
           message:Network plugin returns error: cni plugin not initialized
```

**ArgoCD Pod 상태**:
```bash
kubectl get pods -n argocd
No resources found in argocd namespace.
# Pod가 전혀 실행되지 않음
```

### 원인

**순환 의존성 (Bootstrap Chicken-and-Egg Problem)**:

```
1. ArgoCD가 Calico CNI를 배포해야 함
   ↓ (GitOps 패턴)
2. ArgoCD Pod가 실행되려면 CNI가 필요함
   ↓ (Kubernetes 요구사항)
3. root-app 배포 실패로 Calico Application이 생성되지 않음
   ↓
4. CNI 없어서 모든 Pod가 Pending 상태로 남음
   ↓
5. 클러스터 전체가 작동 불가 ⛔
```

### 해결

#### 긴급 복구 (클러스터 이미 배포된 경우)

```bash
# 1. 마스터 노드에서 Calico 수동 설치
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/calico.yaml

# 출력 예시:
# poddisruptionbudget.policy/calico-kube-controllers created
# serviceaccount/calico-kube-controllers created
# daemonset.apps/calico-node created
# deployment.apps/calico-kube-controllers created

# 2. 노드 Ready 상태 확인 (30초 대기)
sleep 30 && kubectl get nodes
# 모든 노드 Ready 확인

# 3. ArgoCD 수동 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 4. ArgoCD Pod Ready 대기
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s

# 5. AppProject 생성
kubectl apply -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: dev
  namespace: argocd
spec:
  description: Development Environment
  sourceRepos: ['*']
  destinations:
    - namespace: '*'
      server: '*'
  clusterResourceWhitelist:
    - group: '*'
      kind: '*'
EOF

# 6. root-app 배포
kubectl apply -f /tmp/root-app.yaml
```

#### Ansible 자동화 (다음 부트스트랩)

`ansible/roles/argocd/tasks/main.yml`에 CNI pre-check 추가:

```yaml
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. CNI Pre-check (순환 의존성 방지)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- name: CNI 플러그인 설치 여부 확인
  shell: kubectl get pods -n kube-system -l k8s-app=calico-node --no-headers 2>/dev/null | wc -l
  register: calico_count
  changed_when: false
  failed_when: false

- name: Calico CNI 수동 설치 (미설치 시)
  command: kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.1/manifests/calico.yaml
  when: calico_count.stdout | int == 0
  register: calico_installed

- name: Calico Pod Ready 대기
  command: kubectl wait --for=condition=ready pod -l k8s-app=calico-node -n kube-system --timeout=120s --all
  when: calico_installed.changed

- name: 노드 Ready 상태 확인
  shell: kubectl get nodes --no-headers | grep -v " Ready " | wc -l
  register: notready_nodes
  changed_when: false
  failed_when: notready_nodes.stdout | int > 0
  retries: 6
  delay: 10
```

### 검증 (실제 클러스터)

**복구 후 노드 상태** (2025-11-16):
```bash
$ kubectl get nodes
NAME                 STATUS   ROLES           AGE    VERSION
k8s-api-auth         Ready    <none>          88m    v1.28.4  # ✅
k8s-api-character    Ready    <none>          87m    v1.28.4  # ✅
k8s-api-chat         Ready    <none>          87m    v1.28.4  # ✅
k8s-api-info         Ready    <none>          87m    v1.28.4  # ✅
k8s-api-location     Ready    <none>          87m    v1.28.4  # ✅
k8s-api-my           Ready    <none>          88m    v1.28.4  # ✅
k8s-api-scan         Ready    <none>          88m    v1.28.4  # ✅
k8s-master           Ready    control-plane   100m   v1.28.4  # ✅
k8s-monitoring       Ready    <none>          87m    v1.28.4  # ✅
k8s-postgresql       Ready    <none>          87m    v1.28.4  # ✅
k8s-rabbitmq         Ready    <none>          87m    v1.28.4  # ✅
k8s-redis            Ready    <none>          87m    v1.28.4  # ✅
k8s-worker-ai        Ready    <none>          88m    v1.28.4  # ✅
k8s-worker-storage   Ready    <none>          88m    v1.28.4  # ✅
# 모든 14개 노드 Ready ✅
```

**Calico 상태**:
```bash
$ kubectl get pods -n kube-system -l k8s-app=calico-node
NAME                READY   STATUS    AGE
calico-node-26ljf   1/1     Running   76m  # k8s-api-character
calico-node-2r26w   1/1     Running   76m  # k8s-worker-storage
calico-node-6952r   1/1     Running   76m  # k8s-worker-ai
# ... 14개 노드 모두 Running ✅
```

**커밋**: Ansible CNI pre-check 추가 (`c94469d`)

---

## 4. ArgoCD AppProject 미생성

### 문제

**증상**:
```bash
kubectl get application dev-root -n argocd
NAME       SYNC STATUS   HEALTH STATUS
dev-root   Unknown       Unknown

kubectl describe application dev-root -n argocd
Conditions:
  Message: Application referencing project dev which does not exist
  Type:    InvalidSpecError
```

**ArgoCD controller 로그**:
```json
{"level":"warning","msg":"error getting app project \"dev\": appproject.argoproj.io \"dev\" not found"}
```

### 원인

Ansible playbook이 ArgoCD 설치만 하고 AppProject를 생성하지 않음. root-app은 `spec.project: dev`를 참조하는데 project가 없어서 검증 실패.

### 해결

`ansible/roles/argocd/tasks/main.yml`에 AppProject 생성 추가:

```yaml
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ArgoCD 설정 (NetworkPolicy 제거, AppProject 생성)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- name: ArgoCD AppProject 생성 (dev)
  shell: |
    kubectl apply -f - <<EOF
    apiVersion: argoproj.io/v1alpha1
    kind: AppProject
    metadata:
      name: dev
      namespace: {{ argocd_namespace }}
    spec:
      description: Development Environment
      sourceRepos:
        - '*'
      destinations:
        - namespace: '*'
          server: '*'
      clusterResourceWhitelist:
        - group: '*'
          kind: '*'
      namespaceResourceWhitelist:
        - group: '*'
          kind: '*'
    EOF
  register: appproject_created
  changed_when: "'created' in appproject_created.stdout or 'configured' in appproject_created.stdout"

- name: ArgoCD AppProject 생성 (prod)
  shell: |
    kubectl apply -f - <<EOF
    apiVersion: argoproj.io/v1alpha1
    kind: AppProject
    metadata:
      name: prod
      namespace: {{ argocd_namespace }}
    spec:
      description: Production Environment
      sourceRepos:
        - '*'
      destinations:
        - namespace: '*'
          server: '*'
      clusterResourceWhitelist:
        - group: '*'
          kind: '*'
      namespaceResourceWhitelist:
        - group: '*'
          kind: '*'
    EOF
  register: appproject_prod_created
  changed_when: "'created' in appproject_prod_created.stdout or 'configured' in appproject_prod_created.stdout"
```

### 검증

```bash
kubectl get appproject -n argocd
NAME   AGE
dev    30s
prod   30s  # (if environment=prod)
```

**실제 클러스터 결과**:
```bash
$ kubectl get application dev-root -n argocd
NAME       SYNC STATUS   HEALTH STATUS
dev-root   OutOfSync     Degraded      # ✅ InvalidSpecError 해결됨
```

**커밋**: Ansible AppProject 자동 생성 (`c94469d`)

---

## 5. ArgoCD NetworkPolicy DNS Timeout

### 문제

**증상**:
```bash
kubectl get applications -n argocd
NAME       SYNC STATUS   HEALTH STATUS
dev-root   Unknown       Unknown
```

**ArgoCD Application Controller 로그**:
```json
{"level":"warning","msg":"Reconnect to redis because error: \"dial tcp: lookup argocd-redis: i/o timeout\""}
{"level":"warning","msg":"failed to set app resource tree: dial tcp: lookup argocd-repo-server on 10.96.0.10:53: dial udp 10.96.0.10:53: i/o timeout"}
```

**Application describe**:
```yaml
status:
  conditions:
  - message: 'Failed to load target state: rpc error: code = Unavailable 
      desc = dns: A record lookup error: lookup argocd-repo-server on 10.96.0.10:53: 
      dial udp 10.96.0.10:53: i/o timeout'
    type: ComparisonError
```

### 원인

ArgoCD 기본 설치 매니페스트(`install.yaml`)에 포함된 NetworkPolicy가 너무 제한적:
- ArgoCD Application Controller → repo-server DNS 조회 차단
- ArgoCD Components 간 통신 차단
- CoreDNS (10.96.0.10:53) 접근 차단

**설치된 NetworkPolicies**:
```bash
$ kubectl get networkpolicy -n argocd
NAME                                              POD-SELECTOR
argocd-application-controller-network-policy      app.kubernetes.io/name=argocd-application-controller
argocd-redis-network-policy                       app.kubernetes.io/name=argocd-redis
argocd-repo-server-network-policy                 app.kubernetes.io/name=argocd-repo-server
# 7개의 제한적인 NetworkPolicy
```

### 해결

#### 즉시 완화

```bash
# ArgoCD NetworkPolicy 전체 삭제
kubectl delete networkpolicy --all -n argocd

# 출력:
# networkpolicy.networking.k8s.io "argocd-application-controller-network-policy" deleted
# networkpolicy.networking.k8s.io "argocd-redis-network-policy" deleted
# ... (7개 삭제)

# CoreDNS 재시작 (권장)
kubectl rollout restart deployment coredns -n kube-system

# ArgoCD Application Controller 재시작
kubectl rollout restart statefulset argocd-application-controller -n argocd
```

#### Ansible 자동화

`ansible/roles/argocd/tasks/main.yml`에 추가:

```yaml
- name: ArgoCD 기본 NetworkPolicy 삭제 (통신 차단 방지)
  command: kubectl delete networkpolicy --all -n {{ argocd_namespace }}
  register: netpol_deleted
  changed_when: "'deleted' in netpol_deleted.stdout"
  failed_when: false  # NetworkPolicy가 없을 수도 있음

- name: ArgoCD NetworkPolicy 삭제 결과
  debug:
    msg: "{{ netpol_deleted.stdout_lines }}"
  when: netpol_deleted.changed
```

### 검증 (실제 클러스터)

**NetworkPolicy 삭제 후**:
```bash
$ kubectl get networkpolicy -n argocd
No resources found in argocd namespace.  # ✅

$ kubectl logs -n argocd sts/argocd-application-controller --tail=5
{"app-namespace":"argocd","application":"dev-root","level":"info","msg":"Reconciliation completed"}
# DNS timeout 에러 없음 ✅
```

**Applications 정상 sync**:
```bash
$ kubectl get applications -n argocd | grep Synced | wc -l
13  # ✅ 13개 applications Synced 상태
```

**커밋**: Ansible NetworkPolicy 자동 삭제 (`c94469d`)

---

## 6. Application targetRevision 불일치

### 문제

**증상**:
```bash
# 로컬에서 수정하고 커밋했지만 클러스터에 반영 안 됨
kubectl get deploy auth-api -n auth -o yaml | grep nodeSelector
      nodeSelector:
        service: auth  # ✅ 표준 라벨 (반영되지 않으면 diff 지속)
```

**ArgoCD Application 상태**:
```bash
kubectl get application dev-namespaces -n argocd -o jsonpath='{.status.conditions}'
[{"message":"Failed to load target state: workloads/namespaces/dev: app path does not exist","type":"ComparisonError"}]
```

### 원인

**브랜치 불일치**:

```bash
# 로컬 브랜치
$ git branch --show-current
refactor/gitops-sync-wave

$ git log -1 --oneline
f191d18 fix: Ansible 노드 라벨과 Kubernetes manifest 동기화

# GitHub default 브랜치
$ git log origin/HEAD -1 --oneline
52920f9 Update README.md  # 수정 전 커밋 (127개 커밋 뒤처짐)

# ArgoCD Application
$ kubectl get application dev-namespaces -n argocd -o jsonpath='{.spec.source.targetRevision}'
HEAD  # ❌ GitHub default를 가리킴
```

**문제 시나리오**:
1. 로컬에서 `sesacthon.io/*` 라벨로 수정 (`refactor/gitops-sync-wave` 브랜치)
2. 커밋만 하고 push 안 함
3. ArgoCD가 `targetRevision: HEAD`로 설정되어 있음
4. ArgoCD는 GitHub의 default 브랜치(옛날 커밋)를 읽음
5. 구버전 manifest가 배포됨 → Pod 스케줄링 실패

### 해결

#### 1. 작업 브랜치 push

```bash
git push origin refactor/gitops-sync-wave

# 127개 커밋 push 완료
# To https://github.com/SeSACTHON/backend.git
#  * [new branch]  refactor/gitops-sync-wave -> refactor/gitops-sync-wave
```

#### 2. root-app targetRevision 변경

```bash
kubectl patch application dev-root -n argocd --type merge \
  -p '{"spec":{"source":{"targetRevision":"refactor/gitops-sync-wave"}}}'
```

#### 3. 모든 child applications targetRevision 일괄 변경

```bash
# 일괄 변경
find clusters/dev/apps -name "*.yaml" -type f \
  -exec sed -i '' 's/targetRevision: HEAD/targetRevision: refactor\/gitops-sync-wave/g' {} \;

git add clusters/dev/apps/
git commit -m "fix: update all applications targetRevision to working branch"
git push origin refactor/gitops-sync-wave
```

#### 4. Applications 재생성

```bash
kubectl delete application dev-root -n argocd
kubectl apply -f /tmp/root-app.yaml
kubectl patch application dev-root -n argocd --type merge \
  -p '{"spec":{"source":{"targetRevision":"refactor/gitops-sync-wave"}}}'
```

### 검증 (실제 클러스터)

**targetRevision 확인**:
```bash
$ kubectl get applications -n argocd -o jsonpath='{.items[*].spec.source.targetRevision}' | tr ' ' '\n' | sort | uniq
refactor/gitops-sync-wave  # ✅ 모두 동일한 브랜치
1.7.1  # (ALB Controller는 Helm chart 버전)
0.9.11  # (External Secrets는 Helm chart 버전)
```

**Sync 상태 확인**:
```bash
$ kubectl get applications -n argocd | grep Synced | wc -l
13  # ✅ 13개 applications Synced

$ kubectl get deploy auth-api -n auth -o yaml | grep nodeSelector
      nodeSelector:
        sesacthon.io/service: auth  # ✅ 최신 라벨 반영됨
```

**커밋**: `9d5c34b`, `dbe3d6d`, `e82a025`, `a0e7a0b`, `451e5b0`

**장기 해결책**: 
- 작업 완료 후 main/develop에 merge
- production은 항상 `targetRevision: main` 사용

---

## 7. Kustomize 디렉토리 구조 문제

### 문제

**ArgoCD sync 에러**:
```
The Kubernetes API could not find kustomize.config.k8s.io/Kustomization 
for requested resource argocd/. Make sure the "Kustomization" CRD is installed 
on the destination cluster.
```

**Application 상태**:
```yaml
# clusters/dev/apps/00-crds.yaml
source:
  path: platform/crds
  directory:
    recurse: true  # ❌ 문제의 원인
```

**sync 실패 로그**:
```bash
status:
  operationState:
    syncResult:
      resources:
      - group: kustomize.config.k8s.io
        kind: Kustomization
        message: The Kubernetes API could not find kustomize.config.k8s.io/Kustomization
        status: SyncFailed
```

### 원인

**디렉토리 구조 문제**:
```
platform/crds/
├── (kustomization.yaml 없음!)  # ← 문제
├── alb-controller/
│   └── kustomization.yaml
├── external-secrets/
│   └── kustomization.yaml
├── postgres-operator/
│   └── kustomization.yaml
└── prometheus-operator/
    └── kustomization.yaml
```

**`directory.recurse: true` 부작용**:
1. ArgoCD가 모든 하위 디렉토리를 재귀적으로 탐색
2. `kustomization.yaml` 파일들을 **Kubernetes 리소스로 배포**하려고 시도
3. `kustomize.config.k8s.io/Kustomization` CRD가 클러스터에 없어서 실패
4. 실제로는 kustomize build를 해야 하는데 directory 모드로 처리함

### 해결

#### 1. 상위 kustomization.yaml 생성

```yaml
# platform/crds/kustomization.yaml (신규)
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - alb-controller
  - external-secrets
  - postgres-operator
  - prometheus-operator
```

#### 2. Application 설정 수정

```yaml
# clusters/dev/apps/00-crds.yaml (수정)
source:
  path: platform/crds
  # directory.recurse 제거 - kustomize 자동 인식
```

#### 3. 로컬 테스트

```bash
# kustomize build 테스트
kubectl kustomize platform/crds | head -20

# 출력 예시:
# apiVersion: apiextensions.k8s.io/v1
# kind: CustomResourceDefinition
# metadata:
#   name: ingressclassparams.elbv2.k8s.aws
# ✅ CRD 리소스들이 출력됨
```

### 검증 (실제 클러스터)

**CRD 설치 확인**:
```bash
$ kubectl get crds | wc -l
44  # ✅ 모든 CRD 설치됨

$ kubectl api-resources --api-group=external-secrets.io
NAME                     SHORTNAMES   APIVERSION                     NAMESPACED
clusterexternalsecrets   ces          external-secrets.io/v1beta1    false
externalsecrets          es           external-secrets.io/v1beta1    true
secretstores             ss           external-secrets.io/v1beta1    true
# ✅ 정상 작동
```

**Application 상태**:
```bash
$ kubectl get application dev-crds -n argocd
NAME       SYNC STATUS   HEALTH STATUS
dev-crds   OutOfSync     Healthy       # ✅ CRD는 작동 (메타데이터 차이만 있음)
```

**커밋**: `2a8c747`, `dbe3d6d`

---

## 8. ApplicationSet 템플릿 따옴표 오류

### 문제

**ApplicationSet 에러**:
```bash
$ kubectl get applicationset dev-data-operators -n argocd -o yaml
status:
  conditions:
  - message: 'Application.argoproj.io "dev-\"postgres-operator\"" is invalid: 
      metadata.name: Invalid value: "dev-\"postgres-operator\"": 
      a lowercase RFC 1123 subdomain must consist of lower case alphanumeric 
      characters, ''-'' or ''.'', and must start and end with an alphanumeric character'
    type: ErrorOccurred
```

**child applications 미생성**:
```bash
$ kubectl get applications -n argocd | grep postgres
# 아무것도 없음 ❌
```

### 원인

ApplicationSet 템플릿에서 이름에 따옴표를 잘못 사용:

```yaml
# clusters/dev/apps/25-data-operators.yaml (오류)
template:
  metadata:
    name: dev-"{{name}}"  # ❌ 따옴표가 리터럴로 들어감
    # 실제 생성되는 이름: dev-"postgres-operator" (유효하지 않음)
```

**Kubernetes 이름 규칙 (RFC 1123)**:
- 소문자 영숫자, `-`, `.`만 허용
- 시작과 끝은 영숫자
- `"` 따옴표는 **허용되지 않음** ❌

### 해결

```yaml
# clusters/dev/apps/25-data-operators.yaml (수정)
template:
  metadata:
    name: dev-{{name}}  # ✅ 따옴표 제거
    # 결과: dev-postgres-operator (유효한 k8s 이름)

# clusters/dev/apps/60-apis-appset.yaml (수정)
template:
  metadata:
    name: dev-api-{{name}}  # ✅ 따옴표 제거
  spec:
    destination:
      namespace: "{{name}}"  # ✅ namespace는 따옴표 OK (문자열 값으로 사용)
```

**수정 원칙**:
- ❌ `name: "dev-{{name}}"` - 전체를 따옴표로 감싸면 리터럴
- ❌ `name: 'dev-{{name}}'` - 작은따옴표도 동일
- ✅ `name: dev-{{name}}` - 변수 치환 정상 작동
- ✅ `namespace: "{{name}}"` - 값으로 사용 시 따옴표 OK

### 검증 (실제 클러스터)

**ApplicationSet 상태**:
```bash
$ kubectl get applicationset dev-data-operators -n argocd -o jsonpath='{.status.conditions[?(@.type=="ErrorOccurred")].message}'
# (출력 없음) ✅ 에러 해결됨
```

**Child applications 생성 확인** (2025-11-16):
```bash
$ kubectl get applications -n argocd | grep -E 'postgres|redis|rabbitmq'
dev-postgres-operator   Synced   Degraded   # ✅ 생성됨
dev-rabbitmq-operator   Synced   Degraded   # ✅
dev-redis-operator      Synced   Degraded   # ✅
```

**API applications 생성 확인**:
```bash
$ kubectl get applications -n argocd | grep dev-api
dev-api-auth            Synced   Degraded   # ✅
dev-api-character       Synced   Degraded   # ✅
dev-api-chat            Synced   Degraded   # ✅
dev-api-info            Synced   Degraded   # ✅
dev-api-location        Synced   Degraded   # ✅
dev-api-my              Synced   Degraded   # ✅
dev-api-scan            Synced   Degraded   # ✅
# 7개 모두 생성됨 ✅
```

**영향받은 파일**:
- `clusters/dev/apps/25-data-operators.yaml`
- `clusters/dev/apps/35-data-cr.yaml` (data-clusters)
- `clusters/dev/apps/60-apis-appset.yaml`

**커밋**: `e82a025`, `451e5b0`

---

## 9. CoreDNS Pending (모든 노드 Taint)

### 문제

**증상**:
```bash
$ kubectl get pods -n kube-system | grep coredns
coredns-5dd5756b68-bmdzb   0/1   Pending   0   21m
coredns-5dd5756b68-pz92s   0/1   Pending   0   21m
```

**Pod describe**:
```
Events:
  Warning  FailedScheduling  11m (x3 over 22m)  default-scheduler  
    0/1 nodes are available: 1 node(s) had untolerated taint {node.sesacthon.io/not-ready: }
  
  Warning  FailedScheduling  105s (x2 over 6m45s)  default-scheduler  
    0/14 nodes are available: 
    1 node(s) had untolerated taint {domain: auth}, 
    1 node(s) had untolerated taint {domain: character}, 
    1 node(s) had untolerated taint {domain: chat}, 
    1 node(s) had untolerated taint {domain: info}, 
    1 node(s) had untolerated taint {domain: location}, 
    1 node(s) had untolerated taint {domain: my}, 
    1 node(s) had untolerated taint {domain: scan}, 
    3 node(s) had untolerated taint {node.sesacthon.io/not-ready: }, 
    4 node(s) had untolerated taint {sesacthon.io/infrastructure: true}
```

### 원인

**모든 노드에 taint가 설정되어** CoreDNS가 스케줄링될 수 없음:

**Ansible이 설정한 taints** (`ansible/playbooks/fix-node-labels.yml`):
```yaml
node_labels:
  k8s-api-auth: "--node-labels=... --register-with-taints=domain=auth:NoSchedule"
  k8s-api-my: "--node-labels=... --register-with-taints=domain=my:NoSchedule"
  k8s-postgresql: "--node-labels=... --register-with-taints=domain=data:NoSchedule"
  k8s-redis: "--node-labels=... --register-with-taints=domain=data:NoSchedule"
  # ... 모든 worker/infrastructure 노드에 taint
```

**CoreDNS 기본 tolerations** (부족):
```yaml
tolerations:
  - key: CriticalAddonsOnly
    operator: Exists
  - key: role
    operator: Equal
    value: control-plane
    effect: NoSchedule
# ⚠️ domain, sesacthon.io/infrastructure taint는 tolerate 안 함
```

**결과**: CoreDNS가 어디에도 배치되지 못함 → 클러스터 전체 DNS 장애

### 해결

#### 긴급 복구

**Option 1: CoreDNS toleration 패치** (권장):
```bash
kubectl patch deployment coredns -n kube-system --type merge -p '
{
  "spec": {
    "template": {
      "spec": {
        "tolerations": [
          {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
          {"key": "role", "operator": "Equal", "value": "control-plane", "effect": "NoSchedule"},
          {"key": "domain", "operator": "Exists", "effect": "NoSchedule"},
          {"key": "CriticalAddonsOnly", "operator": "Exists"},
          {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
          {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300}
        ]
      }
    }
  }
}'
```

**Option 2: Master taint 제거** (비권장):
```bash
kubectl taint nodes k8s-master node-role.kubernetes.io/control-plane:NoSchedule-
# ⚠️ Master 노드에 다른 Pod도 스케줄링될 수 있음
```

#### Ansible 자동화

`ansible/playbooks/tasks/cni-install.yml` 단계에 포함:

```yaml
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CoreDNS Toleration 패치 (Taint된 클러스터 대응)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- name: CoreDNS toleration 패치 (모든 node taint 허용)
  shell: |
    kubectl patch deployment coredns -n kube-system --type merge -p '
    {
      "spec": {
        "template": {
          "spec": {
            "tolerations": [
              {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
              {"key": "role", "operator": "Equal", "value": "control-plane", "effect": "NoSchedule"},
              {"key": "domain", "operator": "Exists", "effect": "NoSchedule"},
              {"key": "CriticalAddonsOnly", "operator": "Exists"},
              {"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300},
              {"key": "node.kubernetes.io/unreachable", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300}
            ]
          }
        }
      }
    }'
  register: coredns_patched
  changed_when: "'patched' in (coredns_patched.stdout | default(''))"
  failed_when: false

- name: CoreDNS Pod 롤아웃 대기 (CNI 설치 후 검증)
  command: kubectl rollout status deployment/coredns -n kube-system --timeout=300s
  register: coredns_rollout_post_cni
  until: coredns_rollout_post_cni.rc == 0
  retries: 6
  delay: 30
  changed_when: false
```

### 검증 (실제 클러스터)

**CoreDNS Pod 상태** (2025-11-16):
```bash
$ kubectl get pods -n kube-system -l k8s-app=kube-dns -o wide
NAME                      READY   STATUS    NODE
coredns-967868794-94m28   1/1     Running   k8s-worker-ai        # ✅
coredns-967868794-sft58   1/1     Running   k8s-worker-storage   # ✅
# Worker 노드에 정상 배치됨 (Master taint tolerate)
```

**DNS 조회 테스트**:
```bash
$ kubectl run dns-test --image=busybox:1.28 --rm -it --restart=Never -- nslookup kubernetes.default
Server:    10.96.0.10
Address 1: 10.96.0.10 kube-dns.kube-system.svc.cluster.local

Name:      kubernetes.default
Address 1: 10.96.0.1 kubernetes.default.svc.cluster.local
# ✅ DNS 정상 작동
```

**커밋**: Ansible CoreDNS toleration 패치 (`c94469d`)

---

## 10. 베스트 프랙티스

### Ansible Playbook 개선 체크리스트

#### 1. ArgoCD 설치 전 준비

```yaml
# ansible/roles/argocd/tasks/main.yml
✅ CNI 설치 확인 및 자동 설치
✅ 노드 Ready 대기 (최대 60초)
✅ CoreDNS toleration 패치
```

#### 2. ArgoCD 설치 후 설정

```yaml
✅ AppProject 생성 (dev, prod)
✅ NetworkPolicy 삭제 (DNS timeout 방지)
✅ root-app 경로 수정 (clusters/{env}/root-app.yaml)
```

#### 3. 노드 라벨 일관성 유지

**Ansible이 설정하는 라벨**과 **Kubernetes manifest**가 일치해야 함:

| 리소스 타입 | Ansible 라벨 | Deployment nodeSelector | 상태 |
|-----------|-------------|------------------------|------|
| API | `sesacthon.io/service=auth` | `sesacthon.io/service: auth` | ✅ 일치 |
| Worker | `sesacthon.io/worker-type=storage` | `sesacthon.io/worker-type: storage` | ✅ 일치 |
| PostgreSQL | `sesacthon.io/infra-type=postgresql` | `sesacthon.io/infra-type: postgresql` | ✅ 일치 |
| Redis | `sesacthon.io/infra-type=redis` | `sesacthon.io/infra-type: redis` | ✅ 일치 |

#### 4. GitOps 배포 순서 (Sync Wave)

```
Wave 0:  CRDs (kustomization.yaml 필수)
Wave 2:  Namespaces
Wave 5:  Calico CNI (수동 설치 필요)
Wave 6:  NetworkPolicies
Wave 10: External Secrets
Wave 15: ALB Controller
Wave 20: Monitoring Operator
Wave 25: Data Operators
Wave 35: Data Clusters
Wave 60: API Applications
```

#### 5. 문서 동기화

**3개 문서가 항상 일치**해야 함:
- `docs/infrastructure/k8s-label-annotation-system.md`: 노드 라벨 체계 정의
- `ansible/playbooks/fix-node-labels.yml`: 실제 라벨 설정 코드
- `workloads/domains/*/base/deployment.yaml`: nodeSelector 설정

### 검증 스크립트

```bash
#!/bin/bash
# 노드 라벨과 deployment nodeSelector 일치 확인

echo "=== 노드 라벨 vs Deployment nodeSelector 검증 ==="
echo ""

for service in auth my scan character location info chat; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Service: $service"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  
  echo "📍 노드 라벨:"
  kubectl get nodes -l sesacthon.io/service=$service --show-labels 2>/dev/null | grep sesacthon.io/service || echo "  ❌ 노드 없음"
  
  echo ""
  echo "📍 Deployment nodeSelector:"
  kubectl get deploy -n $service ${service}-api -o jsonpath='{.spec.template.spec.nodeSelector}' 2>/dev/null || echo "  ❌ Deployment 없음"
  
  echo ""
  echo "📍 Pod 스케줄링 상태:"
  kubectl get pods -n $service -o wide 2>/dev/null | tail -1 || echo "  ❌ Pod 없음"
  
  echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Infrastructure 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for infra in postgresql redis; do
  echo "Service: $infra"
  kubectl get nodes -l sesacthon.io/infra-type=$infra --show-labels 2>/dev/null | grep sesacthon.io/infra-type || echo "  ❌ 노드 없음"
  echo ""
done
```

### 실제 클러스터 검증 결과 (2025-11-16)

**전체 노드 라벨 시스템** (실제 데이터):

```bash
$ kubectl get nodes --show-labels | grep sesacthon.io
k8s-api-auth         sesacthon.io/node-role=api,sesacthon.io/service=auth,domain=auth,tier=business-logic,workload=api,phase=1
k8s-api-my           sesacthon.io/node-role=api,sesacthon.io/service=my,domain=my,tier=business-logic,workload=api,phase=1
k8s-api-scan         sesacthon.io/node-role=api,sesacthon.io/service=scan,domain=scan,tier=business-logic,workload=api,phase=2
k8s-api-character    sesacthon.io/node-role=api,sesacthon.io/service=character,domain=character,tier=business-logic,workload=api,phase=2
k8s-api-location     sesacthon.io/node-role=api,sesacthon.io/service=location,domain=location,tier=business-logic,workload=api,phase=2
k8s-api-info         sesacthon.io/node-role=api,sesacthon.io/service=info,domain=info,tier=business-logic,workload=api,phase=3
k8s-api-chat         sesacthon.io/node-role=api,sesacthon.io/service=chat,domain=chat,tier=business-logic,workload=api,phase=3
k8s-postgresql       sesacthon.io/node-role=infrastructure,sesacthon.io/infra-type=postgresql,workload=database,tier=data,phase=1
k8s-redis            sesacthon.io/node-role=infrastructure,sesacthon.io/infra-type=redis,workload=cache,tier=data,phase=1
k8s-rabbitmq         sesacthon.io/node-role=infrastructure,sesacthon.io/infra-type=rabbitmq,workload=message-queue,tier=platform,phase=4
k8s-monitoring       sesacthon.io/node-role=infrastructure,sesacthon.io/infra-type=monitoring,workload=monitoring,tier=observability,phase=4
k8s-worker-storage   sesacthon.io/node-role=worker,sesacthon.io/worker-type=storage,workload=worker-storage,tier=worker,phase=4
k8s-worker-ai        sesacthon.io/node-role=worker,sesacthon.io/worker-type=ai,workload=worker-ai,tier=worker,phase=4
# ✅ 모든 노드에 sesacthon.io/* 라벨 적용됨
```

**Pod 스케줄링 성공 확인**:
```bash
$ for ns in auth my scan character location info chat; do 
    kubectl get pods -n $ns -o wide 2>/dev/null | tail -1
  done

auth-api-bff55b88f-hqlcd        0/1  ImagePullBackOff  k8s-api-auth       # ✅ 스케줄링 성공
my-api-76b4fcbf57-ndds6         0/1  ImagePullBackOff  k8s-api-my         # ✅
scan-api-7c7fccbdbf-49gg2       0/1  ImagePullBackOff  k8s-api-scan       # ✅
character-api-85c768fd7-8cdjh   0/1  ImagePullBackOff  k8s-api-character  # ✅
location-api-6b8c885845-xlbbm   0/1  ImagePullBackOff  k8s-api-location   # ✅
info-api-7676d5dc5c-dbcp7       0/1  ImagePullBackOff  k8s-api-info       # ✅
chat-api-76488b98b5-gfgfw       0/1  ImagePullBackOff  k8s-api-chat       # ✅

# 모든 Pod가 올바른 노드에 배치됨 ✅
# ImagePullBackOff는 별도 문제 (GHCR 인증)
```

---

## 요약

### 해결된 문제 (2025-11-16)

| 문제 | 영향 | 해결 방법 | 상태 |
|-----|------|----------|------|
| 노드 라벨 불일치 | 9개 서비스 스케줄링 실패 | Manifest 일괄 수정 | ✅ |
| root-app 경로 오류 | GitOps 체인 전체 중단 | Ansible 경로 수정 | ✅ |
| CNI 순환 의존성 | 클러스터 전체 NotReady | CNI pre-check 추가 | ✅ |
| AppProject 미생성 | root-app 검증 실패 | AppProject 자동 생성 | ✅ |
| NetworkPolicy 차단 | ArgoCD DNS timeout | NetworkPolicy 삭제 | ✅ |
| targetRevision 불일치 | 구버전 manifest 배포 | 브랜치 동기화 | ✅ |
| Kustomize 구조 문제 | CRD 배포 실패 | kustomization.yaml 추가 | ✅ |
| ApplicationSet 따옴표 | Child apps 미생성 | 템플릿 구문 수정 | ✅ |
| CoreDNS Pending | DNS 전체 장애 | toleration 패치 | ✅ |

### 커밋 목록

1. `f191d18` - Ansible 노드 라벨과 Kubernetes manifest 동기화 (10 files)
2. `9d5c34b` - targetRevision 일괄 변경 (14 files)
3. `2a8c747` - platform/crds/kustomization.yaml 추가
4. `dbe3d6d` - dev-crds directory.recurse 제거
5. `e82a025` - data-operators 템플릿 따옴표 수정
6. `451e5b0` - APIs ApplicationSet 템플릿 수정
7. `c94469d` - TROUBLESHOOTING 가이드 + Ansible 개선 (1,006 lines)
8. `73d2ca6` - ALB Controller ApplicationSet 패턴
9. `90172b3` - ALB Controller single-source 패턴
10. `6d0ff79` - 모든 platform/helm directory.include 추가
11. `3ff81d7` - 모든 platform/helm app.yaml 추가 (7 files, +338 lines)

### 최종 상태 (실제 클러스터)

**ArgoCD Applications**: 23개
- ✅ Synced + Healthy: 5개 (ALB, Namespaces, NetworkPolicies, RBAC, External-Secrets)
- ✅ Synced + Degraded: 10개 (7 APIs + 3 Data Operators - 이미지 문제, 스케줄링 성공)
- ⚠️ OutOfSync: 7개 (기능 정상, 메타데이터 차이)

**핵심 Infrastructure**:
- ✅ ALB Controller: Running
- ✅ External-DNS: Running
- ✅ External-Secrets: Running
- ✅ Calico CNI: 14/14 노드 Running
- ✅ CoreDNS: Running (2 replicas)

**Pod 스케줄링**: 100% 성공 (sesacthon.io/* 라벨 시스템)

---

**다음 부트스트랩에서 자동 해결됨** ✅



## 11. kubelet crashloop (Kubernetes 1.28 + `kubernetes.io/*` 라벨)

### 문제

**조인 단계 전체 실패**:
```bash
TASK [Join 상태 출력] ***************************************************
ok: [k8s-worker-ai] =>  msg: ⚠️ Join 필요
...
TASK [클러스터 조인] *****************************************************
FAILED - RETRYING: 클러스터 조인 (10 retries left).
```

**kubelet 로그** (Ubuntu 22.04, Kubernetes 1.28.4):
```bash
sudo journalctl -u kubelet -n 20

failed to validate kubelet flags: unknown reserved Kubernetes labels specified with --node-labels
--node-labels in the 'kubernetes.io' namespace must begin with kubelet.kubernetes.io/node.kubernetes.io ...
```
> 📎 **공식 근거**: Kubernetes 문서에서는 `kubernetes.io/`·`k8s.io/` prefix가 코어 컴포넌트 전용 예약 공간이며, 사용자나 자동화 도구가 이 prefix로 라벨을 추가할 경우 kubelet이 거부할 수 있다고 명시합니다.  
>
> ```
> The kubernetes.io/ and k8s.io/ prefixes are reserved for Kubernetes core components.
> ```
>
> 자세한 제약은 “[Labels › Restriction on labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#restriction-on-labels)”에서 확인할 수 있습니다.

### 원인

Terraform/Ansible가 모든 노드에 다음과 같은 drop-in을 주입하고 있음:
```ini
# /etc/systemd/system/kubelet.service.d/10-node-labels.conf
[Service]
Environment="KUBELET_EXTRA_ARGS=--node-labels=role=worker,worker-type=ai,workload=worker-ai,phase=4"
```
Kubernetes 1.28부터는 `kubernetes.io/*`, `k8s.io/*` 네임스페이스가 **공식 허용 prefix/node.kubernetes.io/... 등**이 아니면 거부되며, kubelet이 기동하지 못해 `/etc/kubernetes/kubelet.conf` 가 생성되지 않습니다. 따라서 Ansible `join` 단계가 무한 대기 상태로 남습니다.

### 영향

- 모든 worker/API/infra 노드가 kubelet crashloop → `Join 상태 출력`이 계속 “⚠️ Join 필요”
- `kubectl get nodes`가 항상 `NotReady` 또는 “리소스 없음”으로 표시되어 이후 GitOps 단계 진행 불가
- Root 원인을 해결하기 전까지 Terraform/Ansible 재실행만으로는 복구되지 않음

### 해결 전략

1. **라벨 네임스페이스 재설계**  
   - 예: `role=<api|worker|infrastructure>`, `service=<name>`, `infra-type=<kind>`, `taint=<domain>`  
   - Kubernetes 예약 prefix(`kubelet.kubernetes.io/*`, `node.kubernetes.io/*`)는 불가피할 때만 사용
2. **라벨 공급자 업데이트**  
   - Terraform `kubelet_extra_args` 맵  
   - `terraform/user-data/common.sh` drop-in  
   - `ansible/playbooks/tasks/fix-node-labels.yml`
3. **워크로드/운영 코드 전수 수정**  
   - `workloads/**/deployment.yaml` nodeSelector / affinity  
   - 데이터/모니터링/플랫폼 CR의 tolerations, nodeAffinity  
   - Helm values / ArgoCD 패치 / 문서 내 `kubectl get nodes -l ...` 명령
4. **배포 절차**
   - 새 prefix를 코드 전체에 반영한 뒤 Terraform으로 **새 클러스터**를 부트스트랩  
   - 기존 클러스터 업그레이드 시에는 dual-label(구/신 prefix 동시 부여) → 워크로드 업데이트 → 구 라벨 제거 순서 필요

### 빠른 진단 체크리스트

```bash
# kubelet이 라벨 검증 오류로 죽는지 확인
sudo journalctl -u kubelet | grep "failed to validate kubelet flags"

# drop-in에 금지된 prefix가 존재하는지 확인
sudo cat /etc/systemd/system/kubelet.service.d/10-node-labels.conf

# 노드 라벨이 실제로 반영되지 않았는지 확인
kubectl get nodes --show-labels | grep kubernetes.io
```

### 참고 링크
- [docs/deployment/KUBERNETES-1.24-LABEL-FIX.md](../../docs/deployment/KUBERNETES-1.24-LABEL-FIX.md) – prefix 제한 배경
- [docs/infrastructure/k8s-label-annotation-system.md](../../docs/infrastructure/k8s-label-annotation-system.md) – 기존 라벨 설계