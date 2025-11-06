# 🎯 API 중심 Helm Chart 구조 (개선안)

## 💡 핵심 개념

### AI Worker도 API의 일부로 통합

```yaml
기존 관점:
  - API Services (FastAPI)
  - AI Workers (Celery)
  → 분리된 개념

개선된 관점:
  - API Services
    ├── REST API (FastAPI)
    └── Async API (AI Workers)
  → 통합된 개념 ✅
```

---

## 🏗️ 개선된 디렉토리 구조

### 최종 Chart 구조

```
charts/
└── growbin-backend/
    ├── Chart.yaml
    ├── values.yaml
    ├── values-dev.yaml
    ├── values-prod.yaml
    │
    └── templates/
        ├── _helpers.tpl  # 공통 템플릿 함수
        │
        ├── api/  # 모든 API 서비스
        │   │
        │   ├── rest/  # REST API (FastAPI)
        │   │   ├── waste-deployment.yaml
        │   │   ├── waste-service.yaml
        │   │   ├── users-deployment.yaml
        │   │   ├── users-service.yaml
        │   │   ├── auth-deployment.yaml
        │   │   ├── auth-service.yaml
        │   │   ├── recycling-deployment.yaml
        │   │   └── locations-deployment.yaml
        │   │
        │   └── async/  # Async API (AI Workers)
        │       ├── preprocess-deployment.yaml
        │       ├── vision-deployment.yaml
        │       ├── rag-deployment.yaml
        │       ├── llm-deployment.yaml
        │       └── hpa.yaml
        │
        ├── ingress/
        │   ├── api-ingress.yaml
        │   └── monitoring-ingress.yaml
        │
        ├── monitoring/
        │   ├── servicemonitor.yaml
        │   └── prometheusrule.yaml
        │
        └── infrastructure/  # 선택: 인프라 리소스
            ├── configmap.yaml
            └── secret.yaml
```

---

## 📝 values.yaml (API 중심 구조)

```yaml
# charts/growbin-backend/values.yaml

# Global 설정
global:
  image:
    registry: ghcr.io
    repository: your-org/growbin-backend
    tag: latest
    pullPolicy: IfNotPresent
  
  domain: growbin.app
  environment: production

# Celery/RabbitMQ (Async API용)
celery:
  broker: "amqp://admin:password@rabbitmq.messaging:5672//"
  backend: "redis://redis.default:6379/1"

# OpenAI (AI API용)
openai:
  apiKeySecret: openai-secrets
  models:
    vision: "gpt-5-vision-preview"
    llm: "gpt-4o-mini"

#
# API Services
#
api:
  # REST API
  rest:
    # Waste API
    waste:
      enabled: true
      replicas: 3
      port: 8000
      path: /api/v1/waste
      resources:
        requests: { cpu: 200m, memory: 256Mi }
        limits: { cpu: 1000m, memory: 512Mi }
      nodeSelector:
        workload: application
      autoscaling:
        enabled: true
        minReplicas: 3
        maxReplicas: 10
        targetCPUUtilizationPercentage: 70
    
    # Users API
    users:
      enabled: true
      replicas: 2
      port: 8000
      path: /api/v1/users
      resources:
        requests: { cpu: 100m, memory: 128Mi }
        limits: { cpu: 500m, memory: 256Mi }
      nodeSelector:
        workload: application
    
    # Auth API
    auth:
      enabled: true
      replicas: 2
      port: 8000
      path: /api/v1/auth
      resources:
        requests: { cpu: 100m, memory: 128Mi }
        limits: { cpu: 500m, memory: 256Mi }
      nodeSelector:
        workload: application
    
    # Recycling API
    recycling:
      enabled: false  # 아직 개발 안 됨
      replicas: 2
      port: 8000
      path: /api/v1/recycling
      resources:
        requests: { cpu: 100m, memory: 128Mi }
      limits: { cpu: 500m, memory: 256Mi }
    
    # Locations API
    locations:
      enabled: false  # 아직 개발 안 됨
      replicas: 2
      port: 8000
      path: /api/v1/locations
      resources:
        requests: { cpu: 100m, memory: 128Mi }
        limits: { cpu: 500m, memory: 256Mi }
  
  # Async API (AI Workers)
  async:
    # Preprocess Worker
    preprocess:
      enabled: true
      replicas: 3
      queue: q.preprocess
      pool: processes
      concurrency: 8
      resources:
        requests: { cpu: 300m, memory: 256Mi }
        limits: { cpu: 1000m, memory: 512Mi }
      nodeSelector:
        workload: async-workers
    
    # Vision Worker (GPT-5)
    vision:
      enabled: true
      replicas: 5
      queue: q.vision
      pool: gevent
      concurrency: 20
      resources:
        requests: { cpu: 100m, memory: 256Mi }
        limits: { cpu: 500m, memory: 512Mi }
      nodeSelector:
        workload: async-workers
      autoscaling:
        enabled: true
        minReplicas: 5
        maxReplicas: 8
        targetCPUUtilizationPercentage: 70
    
    # RAG Worker
    rag:
      enabled: true
      replicas: 2
      queue: q.rag
      pool: processes
      concurrency: 10
      resources:
        requests: { cpu: 100m, memory: 128Mi }
        limits: { cpu: 300m, memory: 256Mi }
      nodeSelector:
        workload: async-workers
    
    # LLM Worker (GPT-4o mini)
    llm:
      enabled: true
      replicas: 3
      queue: q.llm
      pool: gevent
      concurrency: 20
      resources:
        requests: { cpu: 100m, memory: 256Mi }
        limits: { cpu: 500m, memory: 512Mi }
      nodeSelector:
        workload: async-workers

#
# Ingress
#
ingress:
  enabled: true
  className: alb
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/group.name: growbin-alb
  tls:
    enabled: true
    certificateArn: "arn:aws:acm:..."
  
  # Path Routing
  paths:
    - path: /api/v1/waste
      serviceName: waste
      servicePort: 8000
    - path: /api/v1/users
      serviceName: users
      servicePort: 8000
    - path: /api/v1/auth
      serviceName: auth
      servicePort: 8000

#
# Monitoring
#
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
    scrapeTimeout: 10s
  
  prometheusRule:
    enabled: true
    groups:
      - name: api-alerts
        rules:
          - alert: HighErrorRate
            expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
          - alert: HighLatency
            expr: histogram_quantile(0.95, http_request_duration_seconds_bucket) > 2
      
      - name: worker-alerts
        rules:
          - alert: VisionQueueHigh
            expr: rabbitmq_queue_messages{queue="q.vision"} > 1000
          - alert: DLQNotEmpty
            expr: rabbitmq_queue_messages{queue="q.dlq"} > 100
```

---

## 🎯 핵심 개선 사항

### 1. **논리적 계층 구조**

```
api/
├── rest/     # 동기 API (FastAPI)
│   ├── waste      → GET/POST /api/v1/waste
│   ├── users      → GET/POST /api/v1/users
│   └── auth       → POST /api/v1/auth/login
│
└── async/    # 비동기 API (AI Workers)
    ├── preprocess → Celery Worker (이미지 전처리)
    ├── vision     → Celery Worker (GPT-5 Vision)
    ├── rag        → Celery Worker (RAG 조회)
    └── llm        → Celery Worker (GPT-4o mini)
```

### 2. **일관된 설정 구조**

```yaml
# REST API 설정
api.rest.waste:
  enabled: true
  replicas: 3
  port: 8000
  path: /api/v1/waste

# Async API 설정 (동일한 패턴)
api.async.vision:
  enabled: true
  replicas: 5
  queue: q.vision
  pool: gevent
```

### 3. **확장 용이성**

```yaml
# 새 REST API 추가
api.rest.analytics:
  enabled: true
  replicas: 2
  path: /api/v1/analytics

# 새 Async API 추가
api.async.notification:
  enabled: true
  replicas: 2
  queue: q.notification
```

---

## 📋 템플릿 예시

### REST API 템플릿

```yaml
# charts/growbin-backend/templates/api/rest/waste-deployment.yaml
{{- if .Values.api.rest.waste.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-api-waste
  labels:
    {{- include "growbin-backend.labels" . | nindent 4 }}
    app.kubernetes.io/component: api-rest
    app.kubernetes.io/name: waste
spec:
  replicas: {{ .Values.api.rest.waste.replicas }}
  selector:
    matchLabels:
      {{- include "growbin-backend.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api-rest
      app.kubernetes.io/name: waste
  template:
    metadata:
      labels:
        {{- include "growbin-backend.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api-rest
        app.kubernetes.io/name: waste
    spec:
      {{- with .Values.api.rest.waste.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
      - name: api
        image: "{{ .Values.global.image.registry }}/{{ .Values.global.image.repository }}:{{ .Values.global.image.tag }}"
        imagePullPolicy: {{ .Values.global.image.pullPolicy }}
        ports:
        - name: http
          containerPort: {{ .Values.api.rest.waste.port }}
          protocol: TCP
        env:
        - name: SERVICE_NAME
          value: "waste"
        - name: CELERY_BROKER_URL
          value: {{ .Values.celery.broker | quote }}
        livenessProbe:
          httpGet:
            path: /health
            port: http
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: http
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          {{- toYaml .Values.api.rest.waste.resources | nindent 10 }}
{{- end }}
```

### Async API 템플릿

```yaml
# charts/growbin-backend/templates/api/async/vision-deployment.yaml
{{- if .Values.api.async.vision.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "growbin-backend.fullname" . }}-api-async-vision
  labels:
    {{- include "growbin-backend.labels" . | nindent 4 }}
    app.kubernetes.io/component: api-async
    app.kubernetes.io/name: vision
spec:
  replicas: {{ .Values.api.async.vision.replicas }}
  selector:
    matchLabels:
      {{- include "growbin-backend.selectorLabels" . | nindent 6 }}
      app.kubernetes.io/component: api-async
      app.kubernetes.io/name: vision
  template:
    metadata:
      labels:
        {{- include "growbin-backend.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: api-async
        app.kubernetes.io/name: vision
    spec:
      {{- with .Values.api.async.vision.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
      - name: worker
        image: "{{ .Values.global.image.registry }}/{{ .Values.global.image.repository }}:{{ .Values.global.image.tag }}"
        command:
        - python
        - workers/vision_worker.py
        env:
        - name: CELERY_BROKER_URL
          value: {{ .Values.celery.broker | quote }}
        - name: CELERY_RESULT_BACKEND
          value: {{ .Values.celery.backend | quote }}
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: {{ .Values.openai.apiKeySecret }}
              key: api-key
        - name: QUEUE_NAME
          value: {{ .Values.api.async.vision.queue | quote }}
        resources:
          {{- toYaml .Values.api.async.vision.resources | nindent 10 }}
{{- end }}
```

---

## 🚀 개발 후 배포 시나리오

### 시나리오 1: 새 REST API 추가

```yaml
# values.yaml
api:
  rest:
    analytics:  # ⬅️ 새로 추가
      enabled: true
      replicas: 2
      port: 8000
      path: /api/v1/analytics
      resources:
        requests: { cpu: 100m, memory: 128Mi }
```

```bash
# 템플릿 추가
cp templates/api/rest/waste-deployment.yaml \
   templates/api/rest/analytics-deployment.yaml

# 수정 (waste → analytics)
sed -i 's/waste/analytics/g' templates/api/rest/analytics-deployment.yaml

# Git Push
git add charts/
git commit -m "feat: Add Analytics API"
git push

# ✅ 자동 배포!
```

### 시나리오 2: 새 Async API 추가

```yaml
# values.yaml
api:
  async:
    notification:  # ⬅️ 새로 추가
      enabled: true
      replicas: 2
      queue: q.notification
      pool: gevent
      concurrency: 10
```

```bash
# 템플릿 추가 및 Push
# ✅ 자동 배포!
```

### 시나리오 3: 환경별 설정

```yaml
# values-dev.yaml
api:
  rest:
    waste:
      replicas: 1  # 개발은 1개
  async:
    vision:
      replicas: 2  # 개발은 2개

# values-prod.yaml
api:
  rest:
    waste:
      replicas: 5  # 프로덕션은 5개
  async:
    vision:
      replicas: 8  # 프로덕션은 8개
```

---

## 📊 최종 파일 구조

```
backend/
├── charts/
│   └── growbin-backend/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values-dev.yaml
│       ├── values-prod.yaml
│       │
│       └── templates/
│           ├── _helpers.tpl
│           │
│           ├── api/
│           │   ├── rest/
│           │   │   ├── waste-deployment.yaml
│           │   │   ├── users-deployment.yaml
│           │   │   ├── auth-deployment.yaml
│           │   │   ├── recycling-deployment.yaml
│           │   │   └── locations-deployment.yaml
│           │   │
│           │   └── async/
│           │       ├── preprocess-deployment.yaml
│           │       ├── vision-deployment.yaml
│           │       ├── rag-deployment.yaml
│           │       ├── llm-deployment.yaml
│           │       └── hpa.yaml
│           │
│           ├── ingress/
│           │   └── api-ingress.yaml
│           │
│           └── monitoring/
│               ├── servicemonitor.yaml
│               └── prometheusrule.yaml
│
├── k8s/
│   └── argocd/
│       └── growbin-backend-app.yaml
│
├── app/
│   ├── api/
│   │   ├── waste/
│   │   ├── users/
│   │   └── auth/
│   └── tasks/
│       ├── preprocess.py
│       ├── vision.py
│       ├── rag.py
│       └── llm.py
│
└── workers/
    ├── preprocess_worker.py
    ├── vision_worker.py
    ├── rag_worker.py
    └── llm_worker.py
```

---

## ✅ 장점 요약

### 1. **명확한 계층 구조**
```
api/
├── rest/   (동기 API)
└── async/  (비동기 API)
```

### 2. **일관된 명명 규칙**
```
Pod 이름:
- growbin-backend-api-rest-waste-xxx
- growbin-backend-api-async-vision-xxx

Label:
- app.kubernetes.io/component: api-rest
- app.kubernetes.io/component: api-async
```

### 3. **쉬운 확장**
```yaml
# 새 API 추가
api.rest.newservice: { enabled: true }
api.async.newworker: { enabled: true }
```

### 4. **논리적 그룹화**
```
모니터링:
- REST API 메트릭 → Prometheus
- Async API 메트릭 → Celery + Prometheus

로그:
- kubectl logs -l app.kubernetes.io/component=api-rest
- kubectl logs -l app.kubernetes.io/component=api-async
```

---

## 🎯 결론

**AI Worker를 `api/async/`로 관리하는 것이 최선입니다!** ✅

**이유**:
1. 논리적으로 일관됨 (둘 다 API)
2. 확장 가능 (새 worker 추가 용이)
3. 관리 포인트 단일화
4. 명명 규칙 통일

이 구조로 가시면 장기적으로 훨씬 깔끔하고 확장 가능한 시스템이 됩니다! 🚀

