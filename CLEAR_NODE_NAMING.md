# Growbin Backend - 9 Node Cluster Architecture

## 🏗️ 노드 구성 (명확한 용도별 이름)

### Control Plane
```yaml
k8s-master (t3.large, 8GB):
  역할: Kubernetes Control Plane + ArgoCD
  AZ: ap-northeast-2a
  워크로드: Control Plane, etcd, API Server
```

---

### API Layer (2 Nodes)

#### 1. k8s-api-high-traffic (t3.medium, 4GB)
```yaml
목적: 높은 트래픽 API 서비스
AZ: ap-northeast-2b
서비스:
  - waste-api (메인 폐기물 분석) - 높은 트래픽
  - chat-llm-api (LLM 채팅) - AI 기반, 높은 응답 시간
  - auth-api (인증/인가) - 모든 요청 통과

Replicas:
  - waste-api: 3개
  - chat-llm-api: 3개
  - auth-api: 2개
  총 8 Pods

리소스:
  - CPU: 2 vCPU
  - RAM: 4GB
  - 예상 사용률: 70-80%
```

#### 2. k8s-api-low-traffic (t3.medium, 4GB)
```yaml
목적: 낮은 트래픽 API 서비스
AZ: ap-northeast-2c
서비스:
  - userinfo-api (사용자 정보) - 조회 위주
  - location-api (지도/위치) - Kakao API 호출
  - recycle-info-api (재활용 정보) - 캐싱 가능

Replicas:
  - userinfo-api: 2개
  - location-api: 2개
  - recycle-info-api: 2개
  총 6 Pods

리소스:
  - CPU: 2 vCPU
  - RAM: 4GB
  - 예상 사용률: 40-60%
```

---

### Worker Layer (2 Nodes - Celery)

#### 3. k8s-worker-storage (t3.medium, 4GB)
```yaml
목적: 스토리지 I/O 및 경량 처리
AZ: ap-northeast-2a
Workers:
  - image-uploader (3 Pods)
    - S3 업로드
    - 이미지 해싱
    - Redis 캐싱
  
  - rule-retriever (2 Pods)
    - JSON 규칙 조회
    - 경량 CPU 작업
  
  - task-scheduler (1 Pod - Celery Beat)
    - 주기적 작업 스케줄링
    - 단일 인스턴스 필수

총 6 Pods

리소스:
  - CPU: 2 vCPU
  - RAM: 4GB
  - 스토리지: 40GB
  - 예상 사용률: 50-70%
```

#### 4. k8s-worker-ai (t3.medium, 4GB)
```yaml
목적: AI/LLM 외부 API 호출
AZ: ap-northeast-2b
Workers:
  - gpt5-analyzer (5 Pods)
    - GPT-5 Vision API 호출 (멀티모달)
    - 네트워크 I/O 집중
    - Rate Limit 준수
  
  - response-generator (3 Pods)
    - GPT-4o mini API 호출
    - 최종 응답 생성

총 8 Pods

리소스:
  - CPU: 2 vCPU
  - RAM: 4GB
  - 예상 사용률: 60-80%
  
특징:
  - gevent pool (비동기 I/O)
  - Prefetch=1 (Rate Limit)
```

---

### Infrastructure Layer (4 Nodes)

#### 5. k8s-rabbitmq (t3.small, 2GB)
```yaml
목적: 메시지 큐
AZ: ap-northeast-2a (Master와 동일 AZ)
워크로드: RabbitMQ
큐:
  - q.image_upload
  - q.gpt5_analysis
  - q.rule_retrieval
  - q.response_generation
  - q.dlq (Dead Letter Queue)

리소스:
  - CPU: 2 vCPU
  - RAM: 2GB
  - 스토리지: 40GB
```

#### 6. k8s-postgresql (t3.small, 2GB)
```yaml
목적: 관계형 데이터베이스
AZ: ap-northeast-2b
워크로드: PostgreSQL 15
데이터베이스:
  - growbin (메인 DB)
  - auth (인증 DB)
  - analytics (분석 DB)

리소스:
  - CPU: 2 vCPU
  - RAM: 2GB
  - 스토리지: 60GB
```

#### 7. k8s-redis (t3.small, 2GB)
```yaml
목적: 캐시 및 세션 스토어
AZ: ap-northeast-2c
워크로드: Redis 7
용도:
  - 이미지 해시 캐싱
  - 세션 스토어
  - Celery 결과 백엔드
  - LLM 대화 히스토리

리소스:
  - CPU: 2 vCPU
  - RAM: 2GB
  - 스토리지: 30GB
```

#### 8. k8s-monitoring (t3.large, 8GB)
```yaml
목적: 모니터링 및 관측성
AZ: ap-northeast-2c
워크로드:
  - Prometheus (메트릭 수집)
  - Grafana (시각화)
  - Alertmanager (알림)

리소스:
  - CPU: 2 vCPU
  - RAM: 8GB
  - 스토리지: 60GB (TSDB)
```

---

## 📊 클러스터 전체 요약

### 총 리소스
```yaml
노드: 9개
  - Control Plane: 1
  - API Layer: 2
  - Worker Layer: 2
  - Infrastructure: 4

vCPU: 18 cores
RAM: 38GB
스토리지: 350GB

예상 비용: ~$240/월
```

### AZ 분산
```yaml
ap-northeast-2a:
  - k8s-master
  - k8s-worker-storage
  - k8s-rabbitmq

ap-northeast-2b:
  - k8s-api-high-traffic
  - k8s-worker-ai
  - k8s-postgresql

ap-northeast-2c:
  - k8s-api-low-traffic
  - k8s-redis
  - k8s-monitoring
```

---

## 🔧 NodeSelector 라벨

### API Pods
```yaml
nodeSelector:
  workload: api
  
배치:
  - waste-api → k8s-api-high-traffic
  - chat-llm-api → k8s-api-high-traffic
  - auth-api → k8s-api-high-traffic
  - userinfo-api → k8s-api-low-traffic
  - location-api → k8s-api-low-traffic
  - recycle-info-api → k8s-api-low-traffic
```

### Worker Pods
```yaml
nodeSelector:
  workload: async-workers
  type: storage  # 또는 ai
  
배치:
  Storage Node:
    - image-uploader
    - rule-retriever
    - task-scheduler
  
  AI Node:
    - gpt5-analyzer
    - response-generator
```

---

## 🚀 Terraform 배포

### 노드 생성
```bash
cd terraform/
terraform init
terraform plan
terraform apply

# 출력 확인
terraform output cluster_info
terraform output node_roles
terraform output ssh_commands
```

### SSH 접속
```bash
# API 노드
ssh -i ~/.ssh/sesacthon.pem ubuntu@<api-high-traffic-ip>
ssh -i ~/.ssh/sesacthon.pem ubuntu@<api-low-traffic-ip>

# Worker 노드
ssh -i ~/.ssh/sesacthon.pem ubuntu@<worker-storage-ip>
ssh -i ~/.ssh/sesacthon.pem ubuntu@<worker-ai-ip>
```

---

## 📋 네이밍 규칙

### 명확한 용도 표시
```yaml
이전 (넘버링):
  - k8s-api-1, k8s-api-2
  - k8s-worker-1, k8s-worker-2

현재 (용도 명시):
  - k8s-api-high-traffic (waste, chat-llm, auth)
  - k8s-api-low-traffic (userinfo, location, recycle-info)
  - k8s-worker-storage (image-uploader, rule-retriever, beat)
  - k8s-worker-ai (gpt5-analyzer, response-generator)
```

### 장점
```
✅ 한눈에 노드 용도 파악
✅ 트러블슈팅 시 빠른 식별
✅ 새 팀원 온보딩 용이
✅ 모니터링 대시보드에서 명확한 구분
✅ 노드 추가 시 일관된 네이밍
```

---

**결론**: 모든 노드 이름이 명확한 용도를 표시하도록 변경 완료! 🎯

