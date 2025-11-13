# GitOps 도구 선택: Helm → Kustomize 전환

**문서 버전**: v0.8.0  
**최종 업데이트**: 2025-11-13  
**작성자**: Architecture Team

---

## 🎯 의사결정 요약

**결정**: Helm Chart 제거 후 Kustomize 기반 GitOps로 전환

**날짜**: 2025-11-11

**상태**: ✅ 승인됨

---

## 📊 배경 및 문제점

### 기존 구조 (Helm Chart)

```
backend/
├── charts/ecoeco-backend/
│   ├── Chart.yaml
│   ├── templates/
│   │   ├── api/deployment.yaml
│   │   ├── workers/deployment.yaml
│   │   └── ingress.yaml
│   ├── values.yaml
│   └── values-14nodes.yaml
└── argocd/applications/
    └── ecoeco-14nodes-appset.yaml
```

### 발생한 문제들

#### 1. **복잡한 Template 로직**
```yaml
# templates/api/deployment.yaml
{{- range $name, $config := .Values.api }}
{{- if and (ne $name "common") (ne $name "namespace") (ne $name "ingress") 
           (hasKey $config "enabled") $config.enabled }}
  # 복잡한 조건문과 변수 참조
{{- end }}
{{- end }}
```

**문제점**:
- Template 문법이 복잡하여 디버깅 어려움
- `nil pointer` 오류가 자주 발생
- values 구조와 template 참조 불일치

#### 2. **ApplicationSet과의 통합 문제**
```yaml
# ApplicationSet에서 --set으로 개별 API 활성화 시도
parameters:
  - name: "api.{{domain}}.enabled"
    value: "true"
```

**문제점**:
- `--set`으로 enabled만 변경해도 모든 API가 렌더링됨
- Helm의 range 로직이 ApplicationSet의 의도를 무시
- 여러 리소스가 중복 생성됨

#### 3. **ArgoCD 캐싱 문제**
- Helm template 결과가 캐시되어 최신 변경사항 미반영
- repo-server 재시작 필요
- 디버깅 주기가 매우 느림 (5-10분/시도)

#### 4. **MSA 원칙 위반**
```
문제: 하나의 Helm Chart가 7개 API + 2개 Worker를 모두 관리
결과: 
  - API 간 의존성 불명확
  - 개별 API 배포 불가능
  - 전체 재배포 필요
```

---

## 🔍 도구 비교 분석

### Option 1: Helm Chart (현재)

| 장점 | 단점 |
|------|------|
| • 강력한 템플릿 엔진 | • ❌ 복잡한 문법 (Go template) |
| • 패키지 관리 | • ❌ 디버깅 어려움 |
| • 버전 관리 | • ❌ nil pointer 오류 빈발 |
| • Chart Repository | • ❌ ApplicationSet 통합 복잡 |
|  | • ❌ MSA에 과도한 추상화 |

**결론**: 우리 프로젝트에는 **Over-Engineering**

### Option 2: Kustomize ✅ (선택)

| 장점 | 단점 |
|------|------|
| • ✅ 순수 YAML (템플릿 없음) | • 조건부 로직 제한 |
| • ✅ Overlay 방식으로 커스터마이징 | • 복잡한 변수 치환 불가 |
| • ✅ ArgoCD 네이티브 지원 | • Chart Repository 미지원 |
| • ✅ 디버깅 용이 | |
| • ✅ Git diff 명확 | |
| • ✅ MSA에 적합 (API별 독립) | |

**결론**: 우리 요구사항에 **Perfect Fit**

### Option 3: Plain YAML

| 장점 | 단점 |
|------|------|
| • 가장 단순 | • ❌ 중복 코드 많음 |
| • 학습 곡선 없음 | • ❌ 유지보수 어려움 |
|  | • ❌ 환경별 분리 불가 |

**결론**: 확장성 부족

---

## 💡 Kustomize 선택 이유

### 1. **명확성 (Clarity)**
```yaml
# Helm Template (복잡)
{{- if and (ne $name "common") (hasKey $config "enabled") $config.enabled }}

# Kustomize (명확)
# overlays/auth/kustomization.yaml
resources:
  - ../../base
namePrefix: auth-
```

### 2. **MSA 원칙 준수**
```
각 API가 독립적인 overlay 보유:
k8s/overlays/
├── auth/        → 독립 배포
├── my/          → 독립 배포
├── scan/        → 독립 배포
└── ...
```

### 3. **GitOps 최적화**
```
Git Commit → ArgoCD Sync 흐름이 명확:

1. git push (k8s/overlays/auth/deployment.yaml 수정)
2. ArgoCD detects change
3. kubectl apply -k k8s/overlays/auth/
4. Done ✅

Helm의 경우:
1. git push (values.yaml 수정)
2. ArgoCD pulls repo
3. Helm template rendering (캐시 이슈)
4. Diff 계산 (복잡)
5. kubectl apply
```

### 4. **디버깅 용이성**
```bash
# Kustomize: 로컬에서 즉시 확인
$ kubectl kustomize k8s/overlays/auth/
# → 최종 YAML 출력 (1초)

# Helm: ArgoCD 통해서만 확인 가능
$ helm template ... --values ...
# → template 오류 시 ArgoCD에서만 확인 (5분+)
```

### 5. **학습 곡선**
```
Helm:
  - Go template 문법 학습 필요
  - values 구조 설계 필요
  - template 디버깅 스킬 필요
  예상 학습 시간: 2-3주

Kustomize:
  - YAML만 알면 됨
  - overlay 개념만 이해
  예상 학습 시간: 1-2일
```

---

## 📐 새로운 디렉토리 구조

```
backend/
├── k8s/
│   ├── base/                          # 공통 manifests
│   │   ├── deployment.yaml            # API Deployment 기본 템플릿
│   │   ├── service.yaml               # Service 기본 템플릿
│   │   └── kustomization.yaml         # base resources 정의
│   │
│   ├── overlays/                      # API별 커스터마이징
│   │   ├── auth/
│   │   │   ├── deployment-patch.yaml # auth 전용 설정 (replica, image, etc)
│   │   │   ├── configmap.yaml        # auth 전용 ConfigMap
│   │   │   └── kustomization.yaml    # auth overlay 정의
│   │   │
│   │   ├── my/
│   │   │   ├── deployment-patch.yaml
│   │   │   └── kustomization.yaml
│   │   │
│   │   ├── scan/
│   │   ├── character/
│   │   ├── location/
│   │   ├── info/
│   │   └── chat/
│   │
│   └── workers/                       # Worker overlays
│       ├── storage/
│       └── ai/
│
├── argocd/
│   └── applications/
│       └── ecoeco-appset-kustomize.yaml  # Kustomize 기반 ApplicationSet
│
└── charts/                            # ⚠️ 제거 예정
    └── ecoeco-backend/
```

---

## 🔄 마이그레이션 계획

### Phase 1: Kustomize Base 생성 ✅
```bash
k8s/base/
├── deployment.yaml       # 공통 Deployment
├── service.yaml          # 공통 Service
└── kustomization.yaml
```

### Phase 2: Auth Overlay 생성 (Pilot)
```bash
k8s/overlays/auth/
├── deployment-patch.yaml
├── configmap.yaml
└── kustomization.yaml
```

### Phase 3: ApplicationSet 수정
- `spec.source.helm` → `spec.source.kustomize` 변경
- `path: k8s/overlays/{{domain}}` 지정

### Phase 4: Auth API 테스트 배포
- ArgoCD sync
- Pod 상태 확인
- 서비스 동작 확인

### Phase 5: 나머지 API 확장
- my, scan, character, location, info, chat
- workers (storage, ai)

### Phase 6: Helm Chart 제거
- `charts/` 디렉토리 삭제
- 문서 업데이트

---

## 📊 예상 효과

### 개발 속도
```
Before (Helm):
  변경 → commit → push → ArgoCD sync → template 렌더링 → 오류 확인
  ⏱️ 평균 5-10분/시도
  디버깅 주기: 느림

After (Kustomize):
  변경 → kubectl kustomize (로컬 확인) → commit → push → ArgoCD sync
  ⏱️ 평균 1-2분/시도
  디버깅 주기: 빠름
```

### 코드 복잡도
```
Before:
  - templates/api/deployment.yaml: 120 lines (template 로직)
  - values-14nodes.yaml: 458 lines
  Total: ~600 lines (+ template 문법)

After:
  - k8s/base/deployment.yaml: 50 lines (순수 YAML)
  - k8s/overlays/auth/*: 30 lines
  Total per API: ~80 lines (순수 YAML)
```

### 학습 곡선
```
신규 팀원 온보딩:
  Helm: 2-3주 (Go template 학습)
  Kustomize: 1-2일 (YAML + overlay 개념)
```

---

## 🎓 Kustomize 핵심 개념

### 1. Base (공통)
```yaml
# k8s/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api  # overlay에서 치환됨
spec:
  replicas: 2  # overlay에서 override 가능
  template:
    spec:
      containers:
      - name: app
        image: ghcr.io/sesacthon/placeholder  # overlay에서 치환
        ports:
        - containerPort: 8000
```

### 2. Overlay (커스터마이징)
```yaml
# k8s/overlays/auth/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: api
namePrefix: auth-

resources:
  - ../../base

images:
  - name: ghcr.io/sesacthon/placeholder
    newName: ghcr.io/sesacthon/auth
    newTag: latest

patches:
  - path: deployment-patch.yaml
```

### 3. Patch (부분 수정)
```yaml
# k8s/overlays/auth/deployment-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 2
  template:
    spec:
      nodeSelector:
        domain: auth
      containers:
      - name: app
        env:
        - name: SERVICE_NAME
          value: "auth-api"
```

---

## 🔬 실전 비교: Helm vs Kustomize

### 시나리오 1: Auth API에 환경 변수 추가

#### Helm 방식 (복잡)
```yaml
# values-14nodes.yaml (458 lines)
api:
  auth:
    enabled: true
    replicas: 2
    image:
      repository: ghcr.io/sesacthon/auth
      tag: latest
    env:
      - name: SERVICE_NAME
        value: "auth-api"
      - name: LOG_LEVEL    # ← 추가
        value: "DEBUG"

# templates/api/deployment.yaml (120 lines)
{{- range $name, $config := .Values.api }}
{{- if and (ne $name "common") (hasKey $config "enabled") $config.enabled }}
apiVersion: apps/v1
kind: Deployment
...
spec:
  template:
    spec:
      containers:
      - name: {{ $name }}
        env:
        {{- range $config.env }}
        - name: {{ .name }}
          value: {{ .value | quote }}
        {{- end }}
{{- end }}
{{- end }}
```

**문제점**:
- values.yaml 458줄 중 auth 섹션 찾아야 함
- template 문법 이해 필요
- 로컬 검증 불가 (ArgoCD에서만 확인)

#### Kustomize 방식 (명확)
```yaml
# k8s/overlays/auth/deployment-patch.yaml (30 lines)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: SERVICE_NAME
          value: "auth-api"
        - name: LOG_LEVEL    # ← 추가
          value: "DEBUG"
```

**장점**:
- 파일 30줄, 수정 부분만 명확
- 순수 YAML (학습 불필요)
- 로컬 검증: `kubectl kustomize k8s/overlays/auth/`

---

### 시나리오 2: 7개 API 모두에 공통 환경 변수 추가

#### Helm 방식
```yaml
# values-14nodes.yaml
api:
  common:
    env:
      - name: SHARED_CONFIG    # ← 공통 추가
        value: "production"
  
  auth:
    enabled: true
    env: []  # common + auth 병합 로직 필요
  my:
    enabled: true
    env: []
  # ... 나머지 5개 API
```

**문제점**:
- template에서 common과 개별 env 병합 로직 필요
- `merge` 함수 사용 (Go template 고급 문법)
- nil pointer 오류 가능성

#### Kustomize 방식
```yaml
# k8s/base/deployment.yaml (base에 추가)
spec:
  template:
    spec:
      containers:
      - name: app
        env:
        - name: SHARED_CONFIG    # ← 공통 추가
          value: "production"

# 모든 overlay가 자동으로 상속 ✅
# auth, my, scan, ... 모두 적용됨!
```

**장점**:
- base 한 곳만 수정
- 자동 상속 (병합 로직 불필요)
- 명확한 우선순위 (overlay > base)

---

### 시나리오 3: Auth API만 replicas 3으로 증가

#### Helm 방식
```yaml
# values-14nodes.yaml
api:
  common:
    replicas: 2  # 기본값
  
  auth:
    enabled: true
    replicas: 3  # ← 개별 설정
```

#### Kustomize 방식
```yaml
# k8s/overlays/auth/deployment-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3  # ← 개별 설정
```

**동일한 방식**, 하지만 Kustomize가 더 명확!

---

## 💻 로컬 개발 워크플로우 비교

### Helm 방식
```bash
# 1. values.yaml 수정
vim values-14nodes.yaml

# 2. template 렌더링 (느림)
helm template ecoeco-backend charts/ecoeco-backend \
  --values values-14nodes.yaml \
  --set api.auth.enabled=true > /tmp/auth.yaml

# 3. 결과 확인
cat /tmp/auth.yaml | grep -A 20 "kind: Deployment"

# 4. 오류 발견 시 1번부터 반복
# ⏱️ 평균 5-10분/시도
```

### Kustomize 방식
```bash
# 1. deployment-patch.yaml 수정
vim k8s/overlays/auth/deployment-patch.yaml

# 2. 즉시 렌더링 (빠름)
kubectl kustomize k8s/overlays/auth/

# 3. 결과 확인 (1초)
kubectl kustomize k8s/overlays/auth/ | grep -A 20 "kind: Deployment"

# 4. 오류 발견 시 1번부터 반복
# ⏱️ 평균 1-2분/시도
```

**차이점**:
- Helm: 5-10분/시도 (template 렌더링)
- Kustomize: 1-2분/시도 (즉시 확인)
- **생산성 5배 향상!** ✅

---

## 🐛 실제 발생한 Helm 문제 사례

### Case 1: nil pointer 오류

**상황**: auth API 비활성화 후 활성화 시도

```yaml
# values-14nodes.yaml
api:
  auth:
    enabled: false  # ← 비활성화
    # image 섹션 삭제됨
```

**에러**:
```
Error: template: ecoeco-backend/templates/api/deployment.yaml:45:28: 
executing "ecoeco-backend/templates/api/deployment.yaml" 
at <$config.image.repository>: nil pointer evaluating interface {}.repository
```

**원인**: 
- `enabled: false`로 설정 후 `image` 섹션 삭제
- template에서 `$config.image.repository` 참조 시 nil

**Helm 해결**:
```yaml
{{- if $config.image }}
  image: {{ $config.image.repository }}:{{ $config.image.tag }}
{{- end }}
```
→ 모든 template에 nil 체크 추가 (유지보수 ↑)

**Kustomize 해결**:
```yaml
# k8s/overlays/auth/ 디렉토리 전체 삭제
# ArgoCD ApplicationSet에서 제외
```
→ 파일이 없으면 배포 안 됨 (명확!)

---

### Case 2: ApplicationSet 통합 문제

**상황**: ApplicationSet으로 7개 API 개별 배포 시도

```yaml
# argocd/applications/ecoeco-14nodes-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
  - list:
      elements:
      - domain: auth
      - domain: my
      # ...
  template:
    spec:
      source:
        helm:
          parameters:
          - name: api.{{domain}}.enabled
            value: "true"
```

**문제점**:
- `--set api.auth.enabled=true`만 변경
- Helm template의 `range` 로직이 **모든 API를 렌더링**
- auth만 배포하려 했는데 my, scan도 생성됨!

**Kustomize 해결**:
```yaml
spec:
  template:
    spec:
      source:
        path: k8s/overlays/{{domain}}  # ← 디렉토리 분리
```
→ auth 디렉토리만 참조 = auth만 배포 ✅

---

### Case 3: ArgoCD repo-server 캐싱

**상황**: values.yaml 수정 후 ArgoCD sync해도 반영 안 됨

```bash
# values.yaml 수정
git commit -m "Update auth replicas to 3"
git push

# ArgoCD sync
argocd app sync ecoeco-auth

# 확인
kubectl get deploy auth-api -n api
# NAME       READY   UP-TO-DATE   AVAILABLE
# auth-api   2/2     2            2           # ← 여전히 2개!
```

**원인**: 
- ArgoCD repo-server가 Helm template 결과 캐시
- Git commit 감지해도 template 재렌더링 안 함

**Helm 해결**:
```bash
# repo-server 재시작 (비정상적)
kubectl rollout restart deployment argocd-repo-server -n argocd

# 또는 hard refresh
argocd app sync ecoeco-auth --hard-refresh
```

**Kustomize 해결**:
- 캐싱 이슈 없음 (template 없음)
- Git commit = 즉시 반영 ✅

---

## 📊 정량적 비교

### 코드 복잡도

| 항목 | Helm | Kustomize |
|------|------|-----------|
| **총 라인 수** | ~600 lines | ~80 lines/API |
| **values.yaml** | 458 lines | 0 (불필요) |
| **template 파일** | 120 lines | 0 (불필요) |
| **API별 설정** | 20-30 lines | 30 lines |
| **학습 시간** | 2-3주 | 1-2일 |
| **디버깅 시간** | 5-10분/시도 | 1-2분/시도 |

### 개발 생산성

| 작업 | Helm | Kustomize | 차이 |
|------|------|-----------|------|
| 환경 변수 추가 | 10분 | 2분 | **5배** |
| replicas 변경 | 5분 | 1분 | **5배** |
| 새 API 추가 | 30분 | 10분 | **3배** |
| 오류 디버깅 | 20분 | 5분 | **4배** |

### 팀 온보딩

| 항목 | Helm | Kustomize |
|------|------|-----------|
| **신규 팀원** | Go template 학습 2-3주 | YAML만 알면 됨 |
| **첫 배포** | values 구조 이해 1주 | overlay 개념 1일 |
| **자신감** | template 오류 두려움 | 순수 YAML 안심 |

---

## ✅ 결정 기준

### 우리 프로젝트의 요구사항
1. **MSA 아키텍처**: 7 APIs + 2 Workers 독립 관리 ✅
2. **GitOps 유지**: Git을 Single Source of Truth로 ✅
3. **빠른 배포 주기**: 개발 → 프로덕션 신속 반영 ✅
4. **명확한 디버깅**: 문제 발생 시 빠른 원인 파악 ✅
5. **낮은 학습 곡선**: 신규 팀원 빠른 적응 ✅

### Kustomize가 모든 요구사항을 충족 ✅

---

## 📚 참고 자료

### 내부 문서

#### 아키텍처 관련
- [GitOps 파이프라인 다이어그램](./GITOPS_PIPELINE_DIAGRAM.md) - Mermaid 기반 시각화
- [전체 서비스 아키텍처](./03-SERVICE_ARCHITECTURE.md) - 14-Node 전체 구조
- [13-Nodes 아키텍처](./13-nodes-architecture.md) - 노드별 상세 설계
- [마이크로서비스 구성](./microservices-13nodes.md) - API 배치 전략

#### 인프라 관련
- [VPC 네트워크 설계](../infrastructure/02-vpc-network-design.md) - Subnet, Security Group
- [CNI 비교 분석](../infrastructure/05-cni-comparison.md) - Calico VXLAN 선택 이유
- [IaC 구성](../infrastructure/03-iac-terraform-ansible.md) - Terraform + Ansible

#### 배포 관련
- [GitOps 아키텍처](../deployment/GITOPS_ARCHITECTURE.md) - 도구별 역할 분리
- [GitOps 파이프라인](../deployment/GITOPS_PIPELINE_KUSTOMIZE.md) - Kustomize 기반 배포
- [ArgoCD 가이드](../deployment/ARGOCD_ACCESS.md) - 접근 및 사용법
- [자동 재구축 가이드](../deployment/AUTO_REBUILD_GUIDE.md) - 원 커맨드 배포

#### 트러블슈팅
- [Helm → Kustomize 마이그레이션](../troubleshooting/20-HELM_KUSTOMIZE_MIGRATION.md) - 실제 전환 과정
- [전체 트러블슈팅 가이드](../TROUBLESHOOTING.md) - 주요 이슈 모음

### 외부 문서

#### Kustomize 공식 문서
- https://kubectl.docs.kubernetes.io/ - Kustomize CLI 가이드
- https://kustomize.io/ - Kustomize 홈페이지

#### ArgoCD + Kustomize
- https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/ - ArgoCD Kustomize 통합

#### Best Practices
- https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/ - Kubernetes 공식 가이드
- https://github.com/kubernetes-sigs/kustomize/tree/master/examples - 실전 예제

---

## 🔖 관련 이슈 및 PR

### GitHub Issues
- Issue #XX: Helm Chart template 복잡도 및 nil pointer 오류
- Issue #XX: ApplicationSet과 Helm 통합 문제
- Issue #XX: ArgoCD repo-server 캐싱 이슈

### Pull Requests
- PR #XX: Helm → Kustomize 마이그레이션
- PR #XX: k8s/base/ 디렉토리 구조 생성
- PR #XX: ApplicationSet Kustomize 전환
- PR #XX: charts/ 디렉토리 제거

### 관련 문서
- `docs/troubleshooting/20-HELM_KUSTOMIZE_MIGRATION.md` - 실제 전환 과정 및 트러블슈팅
- `docs/deployment/GITOPS_PIPELINE_KUSTOMIZE.md` - Kustomize 기반 파이프라인 설명

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-11-13 | v0.8.0 | 실전 비교 사례 추가 (Helm vs Kustomize), 문제 사례 3건 추가, 정량적 비교 테이블 추가, 참고 자료 섹션 보강 |
| 2025-11-11 | v0.7.1 | 초안 작성 - Helm → Kustomize 전환 결정 |

---

## ✍️ 승인

**Architecture Team**: ✅ Approved  
**DevOps Team**: ✅ Approved  
**Backend Team**: ✅ Approved

**최종 결정**: Kustomize 채택, Helm Chart 제거

