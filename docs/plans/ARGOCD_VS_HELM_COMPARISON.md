# ArgoCD Application vs Helm Chart 비교

## 📊 두 방식 비교표

| 항목 | ArgoCD Application | Helm Chart |
|------|-------------------|------------|
| **구현 난이도** | ⭐ 매우 쉬움 | ⭐⭐⭐ 보통 |
| **작업 시간** | 5분 | 30-60분 |
| **기존 파일 활용** | ✅ 그대로 사용 | ⚠️ 변환 필요 |
| **환경별 설정** | ❌ 어려움 | ✅ 쉬움 (values-dev/prod) |
| **버전 관리** | ⚠️ 제한적 | ✅ 우수 (Chart.yaml) |
| **롤백** | ✅ 가능 | ✅ 쉬움 |
| **재사용성** | ❌ 낮음 | ✅ 높음 |
| **유지보수** | ⚠️ 보통 | ✅ 우수 |
| **GitOps 호환** | ✅ 완벽 | ✅ 완벽 |
| **권장 상황** | 빠른 프로토타입 | 프로덕션 환경 |

---

## Option 1: ArgoCD Application (빠른 적용)

### 📝 구현 방법

#### 1. ArgoCD Application YAML 생성

```yaml
# k8s/argocd/ai-workers-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  
  # Git 저장소 설정
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: k8s/waste  # ⬅️ 현재 YAML 파일 위치
  
  # 배포 대상
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  
  # 자동 동기화 정책
  syncPolicy:
    automated:
      prune: true        # 삭제된 리소스 자동 제거
      selfHeal: true     # Drift 자동 복구
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true  # Namespace 자동 생성
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  
  # Health Check 무시 항목 (HPA가 replicas 관리)
  ignoreDifferences:
  - group: apps
    kind: Deployment
    jsonPointers:
    - /spec/replicas
```

#### 2. 배포 명령어

```bash
# ArgoCD Application 등록
kubectl apply -f k8s/argocd/ai-workers-app.yaml

# 상태 확인
argocd app get ai-workers

# 수동 Sync (필요 시)
argocd app sync ai-workers

# ArgoCD UI에서 확인
# https://argocd.growbin.app
```

#### 3. 파일 구조 (변경 없음)

```
k8s/
└── waste/
    └── ai-workers-deployment.yaml  # ⬅️ 그대로 사용

k8s/argocd/
└── ai-workers-app.yaml  # ⬅️ 새로 추가
```

---

### ✅ 장점

1. **매우 빠른 구현** (5분)
   - 기존 YAML 파일 그대로 사용
   - Application 정의만 추가

2. **즉시 자동화**
   - Main 브랜치에 Merge → 자동 배포
   - Drift 발생 시 자동 복구

3. **간단한 구조**
   - 추가 학습 불필요
   - 직관적인 설정

---

### ⚠️ 단점

1. **환경별 설정 어려움**
   ```
   ❌ 불가능:
     - dev: replica 3개
     - prod: replica 5개
   
   ⚠️ 해결책: 별도 디렉토리
     k8s/waste-dev/
     k8s/waste-prod/
   ```

2. **변수 관리 제한**
   ```yaml
   # Hard-coded 값
   image: ghcr.io/org/waste-service:latest
   replicas: 5
   
   # 변경하려면 YAML 직접 수정 필요
   ```

3. **재사용성 낮음**
   - 다른 프로젝트에서 사용 어려움
   - 템플릿화 불가

---

## Option 2: Helm Chart (프로덕션 권장)

### 📝 구현 방법

#### 1. Helm Chart 생성

```bash
# Chart 생성
helm create charts/ai-workers

# 생성된 구조
charts/ai-workers/
├── Chart.yaml           # Chart 메타데이터
├── values.yaml          # 기본 설정
├── values-dev.yaml      # 개발 환경 설정
├── values-prod.yaml     # 프로덕션 설정
└── templates/
    ├── deployment.yaml
    ├── hpa.yaml
    ├── servicemonitor.yaml
    ├── configmap.yaml
    └── secret.yaml
```

#### 2. Chart.yaml

```yaml
# charts/ai-workers/Chart.yaml
apiVersion: v2
name: ai-workers
description: AI Worker Pipeline (GPT-5 Vision + GPT-4o mini)
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - ai
  - celery
  - rabbitmq
  - openai
maintainers:
  - name: Your Team
    email: team@growbin.app
```

#### 3. values.yaml (기본 설정)

```yaml
# charts/ai-workers/values.yaml

# Global 설정
global:
  image:
    registry: ghcr.io
    repository: your-org/waste-service
    tag: latest
    pullPolicy: IfNotPresent

# Celery 설정
celery:
  broker: "amqp://admin:password@rabbitmq.messaging:5672//"
  backend: "redis://redis.default:6379/1"

# OpenAI 설정
openai:
  apiKeySecret: openai-secrets  # Secret 이름
  model:
    vision: "gpt-5-vision-preview"
    llm: "gpt-4o-mini"

# Preprocess Worker
preprocessWorker:
  enabled: true
  replicas: 3
  image:
    tag: ""  # global.image.tag 사용
  resources:
    requests:
      cpu: 300m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 512Mi
  pool: processes
  concurrency: 8
  prefetchMultiplier: 4
  nodeSelector:
    workload: async-workers

# Vision Worker
visionWorker:
  enabled: true
  replicas: 5
  image:
    tag: ""
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
  pool: gevent
  concurrency: 20
  prefetchMultiplier: 1
  nodeSelector:
    workload: async-workers
  
  # HPA 설정
  autoscaling:
    enabled: true
    minReplicas: 5
    maxReplicas: 8
    targetCPUUtilizationPercentage: 70
    targetQueueLength: 200

# RAG Worker
ragWorker:
  enabled: true
  replicas: 2
  image:
    tag: ""
  resources:
    requests:
      cpu: 100m
      memory: 128Mi
    limits:
      cpu: 300m
      memory: 256Mi
  pool: processes
  concurrency: 10
  nodeSelector:
    workload: async-workers

# LLM Worker
llmWorker:
  enabled: true
  replicas: 3
  image:
    tag: ""
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
  pool: gevent
  concurrency: 20
  nodeSelector:
    workload: async-workers

# Monitoring
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
  prometheusRule:
    enabled: true
```

#### 4. values-prod.yaml (프로덕션 오버라이드)

```yaml
# charts/ai-workers/values-prod.yaml

global:
  image:
    tag: "v1.0.0"  # 프로덕션 태그

# Vision Worker 증가
visionWorker:
  replicas: 8  # 프로덕션은 더 많이
  autoscaling:
    minReplicas: 8
    maxReplicas: 12

# 리소스 증가
preprocessWorker:
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 1Gi
```

#### 5. templates/deployment.yaml (예시)

```yaml
# charts/ai-workers/templates/preprocess-deployment.yaml
{{- if .Values.preprocessWorker.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ai-workers.fullname" . }}-preprocess
  labels:
    {{- include "ai-workers.labels" . | nindent 4 }}
    component: preprocess
spec:
  replicas: {{ .Values.preprocessWorker.replicas }}
  selector:
    matchLabels:
      {{- include "ai-workers.selectorLabels" . | nindent 6 }}
      component: preprocess
  template:
    metadata:
      labels:
        {{- include "ai-workers.selectorLabels" . | nindent 8 }}
        component: preprocess
    spec:
      {{- with .Values.preprocessWorker.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
      - name: worker
        image: "{{ .Values.global.image.registry }}/{{ .Values.global.image.repository }}:{{ .Values.global.image.tag | default .Chart.AppVersion }}"
        imagePullPolicy: {{ .Values.global.image.pullPolicy }}
        command:
        - python
        - workers/preprocess_worker.py
        env:
        - name: CELERY_BROKER_URL
          value: {{ .Values.celery.broker | quote }}
        - name: CELERY_RESULT_BACKEND
          value: {{ .Values.celery.backend | quote }}
        resources:
          {{- toYaml .Values.preprocessWorker.resources | nindent 10 }}
{{- end }}
```

#### 6. ArgoCD Application (Helm 버전)

```yaml
# k8s/argocd/ai-workers-helm-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ai-workers
  namespace: argocd
spec:
  project: default
  
  source:
    repoURL: https://github.com/your-org/sesacthon-backend.git
    targetRevision: main
    path: charts/ai-workers  # ⬅️ Helm Chart 경로
    helm:
      valueFiles:
        - values-prod.yaml  # ⬅️ 환경별 values 파일
  
  destination:
    server: https://kubernetes.default.svc
    namespace: waste
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

#### 7. 배포 명령어

```bash
# 로컬 테스트
helm template ai-workers charts/ai-workers \
  --values charts/ai-workers/values-prod.yaml

# 수동 배포
helm upgrade --install ai-workers charts/ai-workers \
  --namespace waste \
  --create-namespace \
  --values charts/ai-workers/values-prod.yaml

# ArgoCD로 자동 배포
kubectl apply -f k8s/argocd/ai-workers-helm-app.yaml
```

---

### ✅ 장점

1. **환경별 설정 분리**
   ```bash
   # 개발 환경
   helm install ai-workers . -f values-dev.yaml
   
   # 프로덕션
   helm install ai-workers . -f values-prod.yaml
   ```

2. **변수화된 설정**
   ```yaml
   # 한 곳에서 관리
   visionWorker:
     replicas: 5  # ⬅️ 쉽게 변경
   ```

3. **버전 관리**
   ```yaml
   Chart.yaml:
     version: 1.0.0  # Chart 버전
     appVersion: "1.0.0"  # 앱 버전
   ```

4. **재사용 가능**
   ```bash
   # 다른 클러스터에 배포
   helm install ai-workers oci://registry/charts/ai-workers
   ```

5. **테스트 용이**
   ```bash
   # Dry-run
   helm template . --debug
   
   # Lint
   helm lint .
   ```

---

### ⚠️ 단점

1. **초기 작업 시간**
   - Chart 작성: 30-60분
   - 템플릿 변환 필요

2. **학습 곡선**
   - Helm 템플릿 문법 이해 필요
   - Go 템플릿 언어

3. **복잡도 증가**
   - 디버깅 어려움 (템플릿 중첩)
   - values 파일 관리

---

## 🎯 실제 파일 예시 비교

### ArgoCD Application 방식

```
변경 사항:
+ k8s/argocd/ai-workers-app.yaml  (1개 파일 추가)

기존 유지:
  k8s/waste/ai-workers-deployment.yaml
  k8s/monitoring/ai-pipeline-alerts.yaml
```

### Helm Chart 방식

```
변경 사항:
+ charts/ai-workers/  (새 디렉토리)
  ├── Chart.yaml
  ├── values.yaml
  ├── values-dev.yaml
  ├── values-prod.yaml
  └── templates/
      ├── preprocess-deployment.yaml
      ├── vision-deployment.yaml
      ├── rag-deployment.yaml
      ├── llm-deployment.yaml
      ├── hpa.yaml
      └── servicemonitor.yaml

+ k8s/argocd/ai-workers-helm-app.yaml

기존 파일:
- k8s/waste/ai-workers-deployment.yaml (이동)
- k8s/monitoring/ai-pipeline-alerts.yaml (이동)
```

---

## 📊 의사결정 매트릭스

### 즉시 배포가 필요한 경우 → ArgoCD Application

```
상황:
✅ 빠르게 자동화 필요
✅ 환경이 하나 (프로덕션만)
✅ 설정 변경 빈도 낮음
✅ 팀 Helm 경험 부족

선택: ArgoCD Application
시간: 5분
```

### 장기 운영을 고려하는 경우 → Helm Chart

```
상황:
✅ dev, staging, prod 환경 분리
✅ 설정 변경 빈도 높음
✅ 다른 클러스터 배포 계획
✅ 팀에 Helm 경험 있음

선택: Helm Chart
시간: 30-60분 (초기), 이후 유지보수 용이
```

---

## 💡 권장 사항

### 단계적 접근 (추천!)

```
Phase 1 (지금): ArgoCD Application
  - 5분 만에 자동화 완성
  - 즉시 GitOps 적용
  - 문제 없이 작동 확인

Phase 2 (1-2주 후): Helm Chart로 마이그레이션
  - 여유 있을 때 천천히 변환
  - 환경별 설정 추가
  - 프로덕션 품질 확보
```

---

## 🚀 빠른 시작 가이드

### ArgoCD Application (5분)

```bash
# 1. Application YAML 생성
cat > k8s/argocd/ai-workers-app.yaml <<EOF
[위의 YAML 내용]
EOF

# 2. 배포
kubectl apply -f k8s/argocd/ai-workers-app.yaml

# 3. 확인
argocd app get ai-workers
```

### Helm Chart (60분)

```bash
# 1. Chart 생성
helm create charts/ai-workers

# 2. 기존 YAML을 템플릿으로 변환
mv k8s/waste/ai-workers-deployment.yaml \
   charts/ai-workers/templates/

# 3. values.yaml 작성
# [위의 values.yaml 내용 작성]

# 4. 테스트
helm template charts/ai-workers

# 5. ArgoCD Application 등록
kubectl apply -f k8s/argocd/ai-workers-helm-app.yaml
```

---

**어떤 방식을 선택하시겠습니까?** 🤔

