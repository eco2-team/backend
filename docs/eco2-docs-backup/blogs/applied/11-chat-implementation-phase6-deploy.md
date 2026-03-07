# Chat 서비스 구현 Phase 6: Docker & K8s

> 컨테이너화와 오케스트레이션, 프로덕션 배포 준비

---

## 1. Dockerfile 설계

### 1.1 멀티스테이지 빌드

```dockerfile
# Stage 1: Builder
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime
COPY --from=builder /install /usr/local
COPY apps/chat /app/chat
```

**멀티스테이지의 이점:**

| 항목 | 단일 스테이지 | 멀티스테이지 |
|------|--------------|-------------|
| 이미지 크기 | ~1.5GB | ~300MB |
| 빌드 캐시 | 비효율적 | 레이어 캐싱 |
| 보안 | gcc 포함 | 런타임만 |

### 1.2 Chat API Dockerfile

```dockerfile
FROM python:3.12-slim AS runtime

# 헬스체크
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:8000/health || exit 1

# FastAPI 실행
CMD ["python", "-m", "uvicorn", "chat.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
```

### 1.3 Chat Worker Dockerfile

```dockerfile
FROM python:3.12-slim AS runtime

# chat 패키지 복사 (domain, application 재사용)
COPY apps/chat /app/chat
COPY apps/chat_worker /app/chat_worker

# Taskiq Worker 실행
CMD ["taskiq", "worker", "chat_worker.main:broker", \
     "--workers", "4", "--max-async-tasks", "10"]
```

**chat 패키지 공유:**

```
chat_worker
    └── imports → chat.domain
                  chat.application.chat.ports
                  chat.infrastructure
```

단일 이미지에서 chat 패키지를 포함하여 코드 재사용.

---

## 2. 의존성 관리

### 2.1 Chat API requirements.txt

```
# Web Framework
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.10.0

# LLM Clients
openai>=1.58.0
anthropic>=0.40.0
tiktoken>=0.8.0

# LangGraph
langgraph>=0.2.0
langchain-core>=0.3.0

# Redis
redis>=5.2.0
```

### 2.2 Chat Worker requirements.txt

```
# Task Queue
taskiq>=0.11.0
taskiq-aio-pika>=0.4.0

# LLM (chat 의존성)
openai>=1.58.0
anthropic>=0.40.0
```

**버전 고정 전략:**

```
개발: >=1.58.0 (유연성)
프로덕션: ==1.58.1 (안정성)
```

---

## 3. Kubernetes 매니페스트

### 3.1 Kustomize 구조

```
workloads/domains/chat-worker/
├── base/
│   ├── deployment.yaml
│   ├── configmap.yaml
│   ├── hpa.yaml
│   └── kustomization.yaml
├── dev/
│   ├── kustomization.yaml
│   └── patch-deployment.yaml
└── prod/
    └── kustomization.yaml
```

**Kustomize 선택 이유:**

| 도구 | 장점 | 단점 |
|------|------|------|
| Helm | 템플릿 강력 | 복잡한 values |
| **Kustomize** | 오버레이 패턴, 간단 | 조건문 제한 |
| Raw YAML | 단순 | 중복 코드 |

Eco² 프로젝트는 환경별 차이가 크지 않아 Kustomize가 적합.

### 3.2 Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chat-worker
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: chat-worker
          image: mng990/eco2:chat-worker-latest
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
          envFrom:
            - configMapRef:
                name: chat-worker-config
            - secretRef:
                name: chat-worker-secret
```

**리소스 설정 근거:**

```
LangGraph 파이프라인:
  - 메모리: State 유지, LLM 응답 버퍼
  - CPU: 토큰 처리, 비동기 I/O

기준:
  - 512Mi: 평균 부하
  - 1Gi: 피크 (긴 대화, 복잡 쿼리)
```

### 3.3 HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 0
```

**스케일링 전략:**

```
Scale Up:
  - 즉시 (stabilization 0초)
  - 최대 2 Pod씩

Scale Down:
  - 5분 안정화 후
  - 10%씩 감소
```

빠른 확장, 신중한 축소로 트래픽 변동 대응.

### 3.4 환경별 패치

```yaml
# dev/patch-deployment.yaml
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: chat-worker
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
          env:
            - name: CHAT_WORKER_LOG_LEVEL
              value: "DEBUG"
```

**개발 환경 최적화:**

- 단일 레플리카 (비용 절감)
- 낮은 리소스 할당
- DEBUG 로깅

---

## 4. ConfigMap vs Secret

### 4.1 ConfigMap (공개 설정)

```yaml
data:
  CHAT_WORKER_SERVICE_NAME: "chat-worker"
  CHAT_WORKER_LOG_LEVEL: "INFO"
  CHAT_WORKER_DEFAULT_PROVIDER: "openai"
  CHAT_WORKER_CONCURRENCY: "10"
```

### 4.2 Secret (민감 정보)

```yaml
# External Secrets Operator로 관리
CHAT_WORKER_OPENAI_API_KEY: <from-vault>
CHAT_WORKER_ANTHROPIC_API_KEY: <from-vault>
CHAT_WORKER_RABBITMQ_URL: <from-vault>
```

**Eco² 프로젝트의 Secret 관리:**

```
Vault → External Secrets → K8s Secret → Pod
```

---

## 5. 프로브 설정

### 5.1 Liveness Probe

```yaml
livenessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - "pgrep -f 'taskiq worker' || exit 1"
  initialDelaySeconds: 30
  periodSeconds: 30
```

**프로세스 체크를 사용하는 이유:**

```
HTTP 프로브:
  - Worker에 HTTP 서버 필요
  - 추가 포트 노출
  
프로세스 프로브:
  - Taskiq Worker 프로세스 확인
  - 간단하고 정확함
```

### 5.2 Readiness Probe

```yaml
readinessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - "pgrep -f 'taskiq worker' || exit 1"
  initialDelaySeconds: 10
  periodSeconds: 10
```

---

## 6. 배포 플로우

### 6.1 CI/CD 파이프라인

```
Git Push → GitHub Actions
    │
    ├── Lint & Test
    │
    ├── Docker Build
    │       └── mng990/eco2:chat-worker-{sha}
    │
    └── Push to Registry
            │
            ▼
        ArgoCD Sync
            │
            └── K8s Deployment
```

### 6.2 ArgoCD Application

```yaml
# clusters/dev/apps/chat-worker.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-chat-worker
spec:
  source:
    path: workloads/domains/chat-worker/dev
  destination:
    namespace: chat
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

---

## 7. 최종 디렉토리 구조

```
apps/chat/
├── Dockerfile
├── requirements.txt
├── domain/
├── application/
├── infrastructure/
├── presentation/
├── setup/
└── main.py

apps/chat_worker/
├── Dockerfile
├── requirements.txt
├── domain/          # chat.domain import
├── setup/
├── tasks/
└── main.py

workloads/domains/
├── chat/            # Chat API (기존)
└── chat-worker/     # Chat Worker (신규)
    ├── base/
    ├── dev/
    └── prod/
```

---

## 8. 다음 단계

구현 완료! 다음 작업:

1. **테스트** - 단위 테스트, 통합 테스트
2. **CI 파이프라인** - GitHub Actions 업데이트
3. **ArgoCD Application** - ApplicationSet 추가
4. **모니터링** - Prometheus 메트릭, Grafana 대시보드

---

**작성일**: 2026-01-13  
**Phase**: 6/6 (Docker & K8s) ✅ 완료

