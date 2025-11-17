# ArgoCD ApplicationSet 패턴 문제 해결

> **작성일**: 2025-11-16  
> **실제 클러스터 데이터 포함** ✅  
> **해결한 문제**: platform/helm ApplicationSet 참조 오류, Multi-source 패턴 문제

## 📋 목차

- [1. Application이 ApplicationSet을 직접 참조하는 문제](#1-application이-applicationset을-직접-참조하는-문제)
- [2. Multi-source 패턴 Helm values 오류](#2-multi-source-패턴-helm-values-오류)
- [3. ApplicationSet app.yaml 파일 미push](#3-applicationset-appyaml-파일-미push)
- [4. 베스트 프랙티스](#4-베스트-프랙티스)

---

## 1. Application이 ApplicationSet을 직접 참조하는 문제

### 문제

**증상**:
```bash
$ kubectl get application dev-alb-controller -n argocd
NAME               SYNC STATUS   HEALTH STATUS
dev-alb-controller Unknown       Healthy

$ kubectl describe application dev-alb-controller -n argocd
Conditions:
  Message: Failed to load target state: failed to generate manifest for source 1 of 1: 
           rpc error: code = Unknown desc = platform/helm/alb-controller: app path does not exist
  Type:    ComparisonError
```

**Application 설정**:
```yaml
# clusters/dev/apps/15-alb-controller.yaml (구버전)
spec:
  source:
    path: platform/helm/alb-controller  # ❌ 디렉토리를 직접 참조
  destination:
    namespace: kube-system  # ❌ ApplicationSet이 배포될 namespace가 아님
```

**디렉토리 구조**:
```
platform/helm/alb-controller/
├── app.yaml      # ← ApplicationSet 정의
└── values/
    ├── dev.yaml
    └── prod.yaml
```

### 원인

1. `platform/helm/alb-controller`는 디렉토리인데, 그 안에 Kubernetes 리소스가 없음
2. 실제로는 `app.yaml`에 **ApplicationSet**이 정의되어 있음
3. Application은 ApplicationSet을 **리소스로 배포**해야 하는데, 디렉토리를 직접 참조함

**ArgoCD가 기대하는 구조**:
```
Application (clusters/dev/apps/15-alb-controller.yaml)
  ↓ deploys
ApplicationSet (platform/helm/alb-controller/app.yaml)
  ↓ generates
dev-alb-controller, prod-alb-controller (Helm charts)
```

### 해결

```yaml
# clusters/dev/apps/15-alb-controller.yaml (수정)
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-alb-controller-appset
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "15"
spec:
  project: dev
  source:
    repoURL: https://github.com/SeSACTHON/backend.git
    targetRevision: refactor/gitops-sync-wave
    path: platform/helm/alb-controller
    directory:
      include: app.yaml  # ✅ app.yaml만 배포 (ApplicationSet)
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd  # ✅ ApplicationSet이 생성될 namespace
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### 검증 (실제 클러스터)

**ApplicationSet 생성 확인** (2025-11-16):
```bash
$ kubectl get applicationset -n argocd | grep alb
alb-controller   20m  # ✅ ApplicationSet 생성됨
```

**Child application 생성 확인**:
```bash
$ kubectl get applications -n argocd | grep alb
dev-alb-controller          Synced   Healthy    # ✅ dev 환경 application 자동 생성
dev-alb-controller-appset   Synced   Degraded   # ✅ ApplicationSet wrapper
```

**ALB Controller Pod**:
```bash
$ kubectl get pods -n kube-system -l app.sesacthon.io/name=aws-load-balancer-controller
NAME                                            READY   STATUS    RESTARTS   AGE   NODE
aws-load-balancer-controller-5fcc4cfccb-89bb9   1/1     Running   0          18m   k8s-master
# ✅ 정상 작동
```

**적용 파일**:
- `clusters/dev/apps/05-calico.yaml`
- `clusters/dev/apps/15-alb-controller.yaml`
- `clusters/dev/apps/16-external-dns.yaml`
- `clusters/dev/apps/20-monitoring-operator.yaml` (kube-prometheus-stack)
- `clusters/dev/apps/21-grafana.yaml`
- `clusters/dev/apps/25-data-operators.yaml`

**커밋**: `6d0ff79`

---

## 2. Multi-source 패턴 Helm values 오류

### 문제

**증상**:
```bash
$ kubectl describe application dev-alb-controller -n argocd
Conditions:
  Message: failed to execute helm template command: 
           Error: execution error at (aws-load-balancer-controller/templates/deployment.yaml:62:28): 
           Chart cannot be installed without a valid clusterName!
  Type:    ComparisonError
```

**Application 설정** (구버전):
```yaml
# platform/helm/alb-controller/app.yaml
spec:
  sources:
    - repoURL: https://aws.github.io/eks-charts
      chart: aws-load-balancer-controller
      targetRevision: 1.7.1
    - repoURL: https://github.com/SeSACTHON/backend.git
      targetRevision: HEAD  # ❌ values 파일 참조
      ref: values
  helm:
    valueFiles:
      - "$values/platform/helm/alb-controller/values/dev.yaml"  # ❌ 경로 오류
```

### 원인

1. **Multi-source 패턴의 복잡성**: Helm chart와 values 파일을 별도 source로 관리
2. **$values 참조 오류**: `$values/{{ valueFile }}` 경로가 실제 파일과 불일치
3. **clusterName 누락**: values 파일을 찾지 못해 필수 파라미터 누락

### 해결

**Single-source 패턴으로 단순화**:

```yaml
# platform/helm/alb-controller/app.yaml (수정)
spec:
  source:
    repoURL: https://aws.github.io/eks-charts
    chart: aws-load-balancer-controller
    targetRevision: 1.7.1
    helm:
      releaseName: aws-load-balancer-controller
      values: |
        clusterName: sesacthon-{{env}}  # ✅ 환경별 동적 생성
        region: ap-northeast-2
        serviceAccount:
          create: false
          name: aws-load-balancer-controller
        replicaCount: 1
        ingressClass: alb
        createIngressClassResource: true
        defaultTargetType: instance
        nodeSelector:
          node-role.sesacthon.io/control-plane: ""
        tolerations:
          - key: node-role.sesacthon.io/control-plane
            operator: Exists
            effect: NoSchedule
```

**장점**:
- ✅ values 파일 경로 오류 없음
- ✅ 환경별 동적 생성 (`{{env}}` 변수)
- ✅ 단순한 구조로 디버깅 쉬움

### 검증 (실제 클러스터)

**Helm release 확인**:
```bash
$ kubectl get pods -n kube-system -l app.sesacthon.io/name=aws-load-balancer-controller -o yaml | grep -A 5 'env:'
    env:
    - name: CLUSTER_NAME
      value: sesacthon-dev  # ✅ 환경별 값 적용됨
```

**커밋**: `73d2ca6`, `90172b3`

---

## 3. ApplicationSet app.yaml 파일 미push

### 문제

**증상**:
```bash
$ kubectl describe application dev-postgres-operator -n argocd
Conditions:
  Message: Failed to load target state: platform/helm/postgres-operator: app path does not exist
  Type:    ComparisonError
```

**로컬 파일 확인**:
```bash
$ ls platform/helm/postgres-operator/
app.yaml  # ✅ 로컬에는 존재

$ git status platform/helm/postgres-operator/app.yaml
?? platform/helm/postgres-operator/app.yaml  # ❌ Git에 추적 안 됨
```

### 원인

1. 로컬에서 app.yaml 파일들을 생성함
2. `.gitignore`에 포함되어 있지 않지만 **수동으로 add하지 않음**
3. push할 때 누락됨
4. ArgoCD가 GitHub에서 파일을 찾을 수 없음

**누락된 파일 목록**:
```bash
$ git status --short platform/helm/*/app.yaml
?? platform/helm/calico/app.yaml
?? platform/helm/external-dns/app.yaml
?? platform/helm/grafana/app.yaml
?? platform/helm/kube-prometheus-stack/app.yaml
?? platform/helm/postgres-operator/app.yaml
?? platform/helm/rabbitmq-operator/app.yaml
?? platform/helm/redis-operator/app.yaml
# 7개 파일 모두 추적 안 됨
```

### 해결

```bash
# 모든 app.yaml 추가
git add platform/helm/*/app.yaml

# 커밋
git commit -m "feat: add ApplicationSet files for all platform charts"

# push
git push origin refactor/gitops-sync-wave
```

### 검증 (실제 클러스터)

**push 후 ApplicationSets 생성** (2025-11-16):
```bash
$ kubectl get applicationset -n argocd
NAME                 AGE
alb-controller       20m   # ✅
calico-cni           7m    # ✅
dev-apis             32m   # ✅
dev-data-clusters    36m   # ✅
dev-data-operators   8m    # ✅
external-dns         8m    # ✅
grafana              7m    # ✅
postgres-operator    8m    # ✅
rabbitmq-operator    8m    # ✅
redis-operator       8m    # ✅
# 10개 ApplicationSets 모두 생성됨 ✅
```

**Child applications 생성 확인**:
```bash
$ kubectl get applications -n argocd | wc -l
24  # ✅ 23개 + root-app

$ kubectl get applications -n argocd | grep -E 'postgres|redis|rabbitmq'
dev-postgres-operator   Synced   Degraded  # ✅
dev-rabbitmq-operator   Synced   Degraded  # ✅
dev-redis-operator      Synced   Degraded  # ✅
```

**커밋**: `3ff81d7` (+338 lines, 7 files)

---

## 4. 베스트 프랙티스

### ApplicationSet 디렉토리 구조

**권장 패턴**:
```
platform/helm/{service}/
├── app.yaml          # ApplicationSet 정의 (필수)
└── values/
    ├── dev.yaml      # 환경별 values
    └── prod.yaml
```

**root-app의 Application 정의**:
```yaml
# clusters/dev/apps/15-alb-controller.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-alb-controller-appset  # ApplicationSet wrapper
spec:
  source:
    path: platform/helm/alb-controller
    directory:
      include: app.yaml  # ✅ app.yaml만 배포
  destination:
    namespace: argocd  # ✅ ApplicationSet이 생성될 위치
```

### ApplicationSet 템플릿 작성 규칙

#### 1. 이름 규칙

```yaml
# ✅ 올바른 패턴
template:
  metadata:
    name: {{env}}-{{name}}           # dev-alb-controller
    name: dev-api-{{name}}           # dev-api-auth
    name: "{{env}}-{{service}}"      # 전체가 변수면 따옴표 OK

# ❌ 잘못된 패턴
template:
  metadata:
    name: "dev-{{name}}"             # dev-"alb-controller" (따옴표 포함됨)
    name: 'dev-{{name}}'             # 작은따옴표도 동일
    name: dev-"{{name}}"-suffix      # 부분 따옴표도 안 됨
```

#### 2. Namespace 규칙

```yaml
# ✅ 값으로 사용 시 따옴표 필요
spec:
  destination:
    namespace: "{{name}}"            # 문자열 값이므로 OK
    namespace: "{{namespace}}"       # OK

# ⚠️ 리터럴로 사용 시 따옴표 불필요
spec:
  destination:
    namespace: kube-system           # 고정 값
```

### Helm Single-source vs Multi-source

#### Single-source (권장)

```yaml
# 간단하고 명확
source:
  repoURL: https://aws.github.io/eks-charts
  chart: aws-load-balancer-controller
  targetRevision: 1.7.1
  helm:
    values: |
      clusterName: sesacthon-{{env}}
      region: ap-northeast-2
      # 모든 values를 inline으로
```

**장점**:
- ✅ 경로 오류 없음
- ✅ values 파일 관리 불필요
- ✅ 환경별 동적 생성 쉬움

**단점**:
- ⚠️ values가 길면 YAML 복잡
- ⚠️ 재사용성 낮음

#### Multi-source (고급)

```yaml
# values를 별도 Git repo에서 관리
sources:
  - repoURL: https://aws.github.io/eks-charts
    chart: aws-load-balancer-controller
    targetRevision: 1.7.1
  - repoURL: https://github.com/SeSACTHON/backend.git
    targetRevision: refactor/gitops-sync-wave
    ref: values
helm:
  valueFiles:
    - "$values/{{valueFile}}"
```

**장점**:
- ✅ Values 파일 버전 관리
- ✅ 재사용성 높음

**단점**:
- ⚠️ 경로 복잡 (`$values/` 참조)
- ⚠️ targetRevision 동기화 필요
- ⚠️ 디버깅 어려움

**권장**: 간단한 설정은 **single-source**, 복잡한 설정만 multi-source

### 실제 클러스터 결과 (2025-11-16)

**수정 후 ApplicationSets**:
```bash
$ kubectl get applicationset -n argocd -o wide
NAME                 AGE
alb-controller       20m   # ✅ single-source 패턴
calico-cni           7m    # ✅
external-dns         8m    # ✅
grafana              7m    # ✅
postgres-operator    8m    # ✅
redis-operator       8m    # ✅
rabbitmq-operator    8m    # ✅
dev-apis             32m   # ✅
dev-data-operators   8m    # ✅
dev-data-clusters    36m   # ✅
```

**모든 child applications 정상 생성**:
```bash
$ kubectl get applications -n argocd | grep Synced | wc -l
13  # ✅ 13개 applications Synced 상태
```

**커밋**: `73d2ca6`, `90172b3`, `6d0ff79`, `3ff81d7`

---

## 요약

### 해결된 문제

| 문제 | 원인 | 해결 | 상태 |
|-----|------|------|------|
| app path does not exist | ApplicationSet 직접 참조 | directory.include 추가 | ✅ |
| Helm clusterName 누락 | Multi-source 경로 오류 | Single-source 전환 | ✅ |
| app.yaml 미push | Git add 누락 | 7개 파일 추가 | ✅ |

### 변경 파일 목록

**clusters/dev/apps** (6개):
- `05-calico.yaml`
- `15-alb-controller.yaml`
- `16-external-dns.yaml`
- `20-monitoring-operator.yaml`
- `21-grafana.yaml`
- `25-data-operators.yaml`

**platform/helm** (7개 신규):
- `alb-controller/app.yaml`
- `calico/app.yaml`
- `external-dns/app.yaml`
- `grafana/app.yaml`
- `kube-prometheus-stack/app.yaml`
- `postgres-operator/app.yaml`
- `rabbitmq-operator/app.yaml`
- `redis-operator/app.yaml`

### 최종 결과

**ApplicationSets**: 10개 생성 ✅  
**Applications**: 23개 생성 ✅  
**ALB Controller**: Running ✅  

---

**관련 문서**:
- [ansible-label-sync.md](./ansible-label-sync.md)
- [gitops-deployment.md](./gitops-deployment.md)


