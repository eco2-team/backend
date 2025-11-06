# 🏗️ 전체 서비스 노드 배치 설계 (확장판)

## 📋 전체 서비스 목록

### 1. REST API 서비스 (동기)

```yaml
기존:
  - waste-api: 폐기물 분류 (이미지 업로드, 분석 결과 조회)

추가:
  - auth: 인증/인가 (JWT, OAuth, 로그인/로그아웃)
  - userinfo: 고객 정보 (프로필, 이력, 설정)
  - location: 지도 (수거함 위치, 거리 계산)
  - recycle-info: 재활용 정보 (품목별 가이드, FAQ)
  - chat-llm: LLM 채팅 (실시간 대화형 질의응답)

총 6개 API 서비스
```

### 2. Celery Workers (비동기)

```yaml
기존:
  - image-uploader: S3 업로드, 이미지 전처리
  - gpt5-analyzer: GPT-5 멀티모달 분석
  - rule-retriever: 분리배출 규칙 조회
  - response-generator: 응답 생성
  - task-scheduler: 주기 작업 (Beat)

추가 가능:
  - (chat-llm이 동기/비동기 여부에 따라)

총 5-6개 Worker 유형
```

---

## 🎯 서비스 특성 분석

### API 서비스별 특성

#### 1. waste-api

```yaml
역할: 폐기물 분류 메인 API
엔드포인트:
  - POST /api/v1/waste/analyze (이미지 분석 요청)
  - GET /api/v1/waste/{task_id} (결과 조회)

특성:
  - 높은 트래픽 (메인 기능)
  - 비동기 작업 연동 (Celery)
  - CPU: 중간
  - Memory: 중간

리소스:
  replicas: 3
  cpu: 200m
  memory: 512Mi
```

#### 2. auth

```yaml
역할: 인증/인가
엔드포인트:
  - POST /api/v1/auth/login
  - POST /api/v1/auth/logout
  - POST /api/v1/auth/refresh
  - POST /api/v1/auth/verify

특성:
  - 중간 트래픽 (모든 요청의 전제)
  - JWT 발급/검증
  - Redis 세션 확인
  - CPU: 낮음
  - Memory: 낮음

리소스:
  replicas: 2
  cpu: 100m
  memory: 256Mi
```

#### 3. userinfo

```yaml
역할: 사용자 정보 관리
엔드포인트:
  - GET /api/v1/users/me
  - PUT /api/v1/users/me
  - GET /api/v1/users/{id}/history

특성:
  - 낮은 트래픽
  - DB 조회 위주
  - CPU: 낮음
  - Memory: 낮음

리소스:
  replicas: 2
  cpu: 100m
  memory: 256Mi
```

#### 4. location

```yaml
역할: 수거함 위치 검색
엔드포인트:
  - GET /api/v1/locations/nearby
  - GET /api/v1/locations/search

특성:
  - 중간 트래픽
  - 외부 API (Kakao Map)
  - CPU: 낮음
  - Network: 중간

리소스:
  replicas: 2
  cpu: 100m
  memory: 256Mi
```

#### 5. recycle-info

```yaml
역할: 재활용 정보 제공
엔드포인트:
  - GET /api/v1/recycle/items/{id}
  - GET /api/v1/recycle/faq
  - GET /api/v1/recycle/guide

특성:
  - 낮은 트래픽
  - 정적 컨텐츠 (JSON 조회)
  - CPU: 낮음
  - Memory: 낮음

리소스:
  replicas: 2
  cpu: 100m
  memory: 256Mi
```

#### 6. chat-llm

```yaml
역할: LLM 채팅 (실시간 대화형)
엔드포인트:
  - POST /api/v1/chat/message
  - WebSocket /api/v1/chat/ws

특성:
  - 중간-높은 트래픽 (인기 기능)
  - 외부 API (GPT-4o mini)
  - 실시간 응답 필요
  - CPU: 낮음
  - Network: 높음

구현 방식:
  옵션 1: 동기 API (FastAPI + Streaming)
  옵션 2: 비동기 Worker (Celery + WebSocket)

리소스 (동기 API 기준):
  replicas: 3
  cpu: 100m
  memory: 256Mi
```

---

## 🖥️ 노드 배치 전략

### 현재 노드 (7개)

```yaml
1. Master (t3.large, 8GB): Control Plane
2. Worker-1 (t3.medium, 4GB): 비동기 작업 (기존)
3. Worker-2 (t3.medium, 4GB): AI 처리 (기존)
4. RabbitMQ (t3.small, 2GB): 메시지 큐
5. PostgreSQL (t3.small, 2GB): 데이터베이스
6. Redis (t3.small, 2GB): 캐시
7. Monitoring (t3.large, 8GB): Prometheus + Grafana
```

### 문제점

```yaml
API 서비스 배치 위치 없음:
  - waste-api는 어디?
  - auth, userinfo 등은 어디?

해결책:
  ✅ API 전용 노드 추가 필요
```

---

## 🎯 최종 노드 설계 (9개 노드)

### 제안: 2개 API 노드 추가

```yaml
총 노드: 9개 (기존 7 + API 2)
추가 비용: t3.medium ×2 = ~$60/월

노드 구성:
  1. Master (t3.large, 8GB)
  2. API-1 (t3.medium, 4GB) ← 신규
  3. API-2 (t3.medium, 4GB) ← 신규
  4. Worker-1 (t3.medium, 4GB)
  5. Worker-2 (t3.medium, 4GB)
  6. RabbitMQ (t3.small, 2GB)
  7. PostgreSQL (t3.small, 2GB)
  8. Redis (t3.small, 2GB)
  9. Monitoring (t3.large, 8GB)
```

---

## 📦 상세 노드 배치

### API-1 노드 (t3.medium, 4GB)

```yaml
라벨: workload=api
네임스페이스: api

배치:
  1. waste-api (×3 Pods):
     역할: 폐기물 분류 메인 API
     CPU: 200m each → 600m total
     RAM: 512Mi each → 1536Mi total
  
  2. chat-llm (×3 Pods):
     역할: LLM 채팅
     CPU: 100m each → 300m total
     RAM: 256Mi each → 768Mi total
  
  3. auth (×2 Pods):
     역할: 인증/인가
     CPU: 100m each → 200m total
     RAM: 256Mi each → 512Mi total

총 리소스:
  CPU: 600m + 300m + 200m = 1100m / 2000m (55%) ✅
  RAM: 1536Mi + 768Mi + 512Mi = 2816Mi / 4096Mi (69%) ✅

총 Pods: 8개

특징:
  - 높은 트래픽 서비스 집중
  - waste-api + chat-llm (메인 기능)
  - auth (필수 기능)
```

### API-2 노드 (t3.medium, 4GB)

```yaml
라벨: workload=api
네임스페이스: api

배치:
  1. userinfo (×2 Pods):
     역할: 사용자 정보
     CPU: 100m each → 200m total
     RAM: 256Mi each → 512Mi total
  
  2. location (×2 Pods):
     역할: 지도/위치
     CPU: 100m each → 200m total
     RAM: 256Mi each → 512Mi total
  
  3. recycle-info (×2 Pods):
     역할: 재활용 정보
     CPU: 100m each → 200m total
     RAM: 256Mi each → 512Mi total

총 리소스:
  CPU: 200m + 200m + 200m = 600m / 2000m (30%) ✅
  RAM: 512Mi + 512Mi + 512Mi = 1536Mi / 4096Mi (37.5%) ✅

총 Pods: 6개

특징:
  - 낮은-중간 트래픽 서비스
  - 보조 기능
  - 리소스 여유 충분 (확장 가능)
```

### Worker-1 노드 (t3.medium, 4GB)

```yaml
라벨: workload=async-workers
네임스페이스: workers

배치:
  1. image-uploader (×3 Pods):
     CPU: 300m each → 900m total
     RAM: 256Mi each → 768Mi total
  
  2. rule-retriever (×2 Pods):
     CPU: 200m each → 400m total
     RAM: 256Mi each → 512Mi total
  
  3. task-scheduler (×1 Pod):
     CPU: 50m
     RAM: 128Mi

총 리소스:
  CPU: 1350m / 2000m (67.5%) ✅
  RAM: 1408Mi / 4096Mi (34%) ✅

총 Pods: 6개 (변경 없음)
```

### Worker-2 노드 (t3.medium, 4GB)

```yaml
라벨: workload=async-workers
네임스페이스: workers

배치:
  1. gpt5-analyzer (×5 Pods):
     CPU: 100m each → 500m total
     RAM: 256Mi each → 1280Mi total
  
  2. response-generator (×3 Pods):
     CPU: 100m each → 300m total
     RAM: 256Mi each → 768Mi total

총 리소스:
  CPU: 800m / 2000m (40%) ✅
  RAM: 2048Mi / 4096Mi (50%) ✅

총 Pods: 8개 (변경 없음)
```

### 인프라 노드 (4개, 변경 없음)

```yaml
RabbitMQ (t3.small, 2GB):
  - 메시지 큐
  
PostgreSQL (t3.small, 2GB):
  - 데이터베이스
  
Redis (t3.small, 2GB):
  - 캐시

Monitoring (t3.large, 8GB):
  - Prometheus + Grafana
```

---

## 📊 전체 클러스터 요약

### 노드 요약 (9개)

```yaml
Control Plane:
  - Master (t3.large, 8GB)

Application Layer:
  - API-1 (t3.medium, 4GB): 8 Pods
  - API-2 (t3.medium, 4GB): 6 Pods
  - Worker-1 (t3.medium, 4GB): 6 Pods (Celery)
  - Worker-2 (t3.medium, 4GB): 8 Pods (Celery)

Infrastructure Layer:
  - RabbitMQ (t3.small, 2GB)
  - PostgreSQL (t3.small, 2GB)
  - Redis (t3.small, 2GB)

Platform Layer:
  - Monitoring (t3.large, 8GB)
```

### 리소스 요약

```yaml
총 vCPU: 18 cores
총 RAM: 38GB
총 Pods: 28개

비용:
  - 기존 (7 노드): ~$180/월
  - 추가 (2 노드): ~$60/월
  - 총: ~$240/월
```

### Pod 분포

```yaml
API Pods (14개):
  - waste-api: 3
  - chat-llm: 3
  - auth: 2
  - userinfo: 2
  - location: 2
  - recycle-info: 2

Celery Worker Pods (14개):
  - image-uploader: 3
  - gpt5-analyzer: 5
  - rule-retriever: 2
  - response-generator: 3
  - task-scheduler: 1
```

---

## 🎨 시각화

### 전체 클러스터 구조

```
┌─────────────────────────────────────────────────────────────┐
│         Kubernetes Cluster (9 Nodes, 28 Pods)               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─── API-1: High Traffic ─────────────────────────┐        │
│  │                                                  │        │
│  │  🗑️ waste-api (×3)     - 메인 기능              │        │
│  │  💬 chat-llm (×3)      - LLM 채팅               │        │
│  │  🔐 auth (×2)          - 인증/인가               │        │
│  │                                                  │        │
│  │  CPU: 1100m (55%), RAM: 2816Mi (69%)           │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─── API-2: Low-Medium Traffic ───────────────────┐        │
│  │                                                  │        │
│  │  👤 userinfo (×2)      - 사용자 정보             │        │
│  │  📍 location (×2)      - 지도/위치               │        │
│  │  ♻️ recycle-info (×2)  - 재활용 정보             │        │
│  │                                                  │        │
│  │  CPU: 600m (30%), RAM: 1536Mi (37.5%)          │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─── Worker-1: Storage & Processing ──────────────┐        │
│  │                                                  │        │
│  │  📤 image-uploader (×3)  - S3 업로드             │        │
│  │  📋 rule-retriever (×2)  - 규칙 조회             │        │
│  │  ⏰ task-scheduler (×1)  - 스케줄러              │        │
│  │                                                  │        │
│  │  CPU: 1350m (67.5%), RAM: 1408Mi (34%)         │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─── Worker-2: AI Processing ──────────────────────┐        │
│  │                                                  │        │
│  │  🤖 gpt5-analyzer (×5)      - GPT-5 분석         │        │
│  │  💬 response-generator (×3) - 응답 생성          │        │
│  │                                                  │        │
│  │  CPU: 800m (40%), RAM: 2048Mi (50%)            │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌─── Infrastructure (4 Nodes) ─────────────────────┐        │
│  │  📨 RabbitMQ  💾 PostgreSQL  🔴 Redis  📊 Monitoring │   │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Ingress 라우팅

### ALB Ingress 규칙

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: api
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
spec:
  ingressClassName: alb
  rules:
  - host: api.growbin.app
    http:
      paths:
      # 폐기물 분류
      - path: /api/v1/waste
        pathType: Prefix
        backend:
          service:
            name: waste-api
            port:
              number: 8000
      
      # 인증
      - path: /api/v1/auth
        pathType: Prefix
        backend:
          service:
            name: auth
            port:
              number: 8000
      
      # 사용자 정보
      - path: /api/v1/users
        pathType: Prefix
        backend:
          service:
            name: userinfo
            port:
              number: 8000
      
      # 위치
      - path: /api/v1/locations
        pathType: Prefix
        backend:
          service:
            name: location
            port:
              number: 8000
      
      # 재활용 정보
      - path: /api/v1/recycle
        pathType: Prefix
        backend:
          service:
            name: recycle-info
            port:
              number: 8000
      
      # LLM 채팅
      - path: /api/v1/chat
        pathType: Prefix
        backend:
          service:
            name: chat-llm
            port:
              number: 8000
```

---

## 🔐 네임스페이스 구조

### 최종 네임스페이스

```yaml
api (namespace):
  서비스:
    - waste-api
    - auth
    - userinfo
    - location
    - recycle-info
    - chat-llm
  
  노드: API-1, API-2
  총 Pods: 14개

workers (namespace):
  Celery Workers:
    - image-uploader
    - gpt5-analyzer
    - rule-retriever
    - response-generator
    - task-scheduler
  
  노드: Worker-1, Worker-2
  총 Pods: 14개

data (namespace):
  - postgresql
  - redis

messaging (namespace):
  - rabbitmq

monitoring (namespace):
  - prometheus
  - grafana
```

---

## ✅ 최종 결론

### 노드 배치

```yaml
API-1 (신규):
  ✅ waste-api (×3): 메인 기능
  ✅ chat-llm (×3): 인기 기능
  ✅ auth (×2): 필수 기능
  ✅ 55% CPU, 69% RAM

API-2 (신규):
  ✅ userinfo (×2): 사용자 관리
  ✅ location (×2): 위치 검색
  ✅ recycle-info (×2): 정보 제공
  ✅ 30% CPU, 37.5% RAM

Worker-1 (기존):
  ✅ Celery Workers (I/O + CPU)
  ✅ 67.5% CPU, 34% RAM

Worker-2 (기존):
  ✅ Celery Workers (AI)
  ✅ 40% CPU, 50% RAM
```

### 장점

```yaml
1. 명확한 분리:
   ✅ API 서비스 vs Celery Workers
   ✅ 높은 트래픽 vs 낮은 트래픽

2. 확장성:
   ✅ API-1: 메인 기능 확장 가능
   ✅ API-2: 보조 기능 추가 가능

3. 안정성:
   ✅ 모든 노드 안전한 리소스 사용률
   ✅ 충분한 여유 리소스

4. 비용 효율:
   ✅ 추가 비용: ~$60/월
   ✅ 총 6개 API 서비스 수용
```

---

**결론**: 2개 API 노드 추가로 총 6개 API 서비스를 안정적으로 배치 완료! 🎯

