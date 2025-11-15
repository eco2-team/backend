# Growbin Backend - 13 Node Microservices Architecture

## 🎯 완벽한 API 분리 구조 (1 API = 1 Node)

### 핵심 원칙
```
✅ 각 API는 독립된 노드에서 실행
✅ 장애 격리 (한 API 문제가 다른 API에 영향 없음)
✅ 독립적인 스케일링
✅ 명확한 책임 분리
✅ 비용 최적화 (트래픽에 맞는 인스턴스 타입)
```

---

## 📊 전체 클러스터 구성 (13 Nodes)

### Control Plane (1 Node)
```yaml
k8s-master:
  인스턴스: t3.large
  메모리: 8GB
  역할: Control Plane + ArgoCD
  AZ: ap-northeast-2a
```

### API Layer (6 Nodes) - 1 API per Node

#### 🔥 High Traffic APIs

**1. k8s-api-waste**
```yaml
인스턴스: t3.small (2GB)
AZ: ap-northeast-2a
서비스: waste-api (폐기물 분석)
Replicas: 3개
트래픽: 매우 높음 (메인 기능)
특징:
  - Celery 작업 트리거
  - 이미지 업로드 처리
  - GPT-5 Vision 분석 요청
```

**2. k8s-api-chat-llm**
```yaml
인스턴스: t3.small (2GB)
AZ: ap-northeast-2c
서비스: chat-llm-api (LLM 채팅)
Replicas: 3개
트래픽: 높음
특징:
  - 실시간 채팅
  - GPT-4o mini 호출
  - WebSocket 지원 (선택)
```

**3. k8s-api-auth**
```yaml
인스턴스: t3.micro (1GB)
AZ: ap-northeast-2b
서비스: auth-api (인증/인가)
Replicas: 2개
트래픽: 높음 (모든 요청 통과)
특징:
  - JWT 발급/검증
  - OAuth2 소셜 로그인
  - Redis 세션 스토어
```

#### 📊 Medium Traffic APIs

**4. k8s-api-userinfo**
```yaml
인스턴스: t3.micro (1GB)
AZ: ap-northeast-2c
서비스: userinfo-api (사용자 정보)
Replicas: 2개
트래픽: 중간
특징:
  - 프로필 조회/수정
  - 포인트 관리
  - 활동 히스토리
```

**5. k8s-api-location**
```yaml
인스턴스: t3.micro (1GB)
AZ: ap-northeast-2a
서비스: location-api (지도/위치)
Replicas: 2개
트래픽: 중간
특징:
  - Kakao Map API 호출
  - 근처 수거함 검색
  - 위치 기반 서비스
```

#### 📖 Low Traffic APIs

**6. k8s-api-recycle-info**
```yaml
인스턴스: t3.micro (1GB)
AZ: ap-northeast-2b
서비스: recycle-info-api (재활용 정보)
Replicas: 2개
트래픽: 낮음
특징:
  - 품목 정보 조회
  - 캐싱 적극 활용
  - FAQ 제공
```

---

### Worker Layer (2 Nodes) - Celery

**7. k8s-worker-storage**
```yaml
인스턴스: t3.medium (4GB)
AZ: ap-northeast-2a
Workers:
  - image-uploader (3 Pods): S3 업로드
  - rule-retriever (2 Pods): JSON 규칙 조회
  - task-scheduler (1 Pod): Celery Beat
총 6 Pods
```

**8. k8s-worker-ai**
```yaml
인스턴스: t3.medium (4GB)
AZ: ap-northeast-2b
Workers:
  - gpt5-analyzer (5 Pods): GPT-5 Vision API
  - response-generator (3 Pods): GPT-4o mini API
총 8 Pods
```

---

### Infrastructure Layer (4 Nodes)

**9. k8s-rabbitmq** (t3.small, 2GB)
**10. k8s-postgresql** (t3.small, 2GB)
**11. k8s-redis** (t3.small, 2GB)
**12. k8s-monitoring** (t3.large, 8GB)

---

## 💰 비용 분석

### 인스턴스별 비용 (서울 리전, On-Demand)
```yaml
t3.micro  (1 vCPU, 1GB):  $0.0104/시간 x 4개 = $30/월
t3.small  (2 vCPU, 2GB):  $0.0208/시간 x 4개 = $60/월
t3.medium (2 vCPU, 4GB):  $0.0416/시간 x 2개 = $60/월
t3.large  (2 vCPU, 8GB):  $0.0832/시간 x 2개 = $120/월

총 비용: ~$270/월
```

### 이전 구성 대비
```yaml
이전 (9 Nodes):
  - t3.large x 2 = $120
  - t3.medium x 4 = $120
  - t3.small x 3 = $45
  총: $285/월

현재 (13 Nodes):
  - t3.large x 2 = $120
  - t3.medium x 2 = $60
  - t3.small x 4 = $60
  - t3.micro x 4 = $30
  총: $270/월

절감: $15/월 (5% 감소) + 장애 격리 + 확장성 향상!
```

---

## 🎯 장점

### 1. 완벽한 장애 격리
```yaml
시나리오: auth-api에서 메모리 누수 발생

이전 구조 (여러 API가 한 노드):
  ❌ auth, waste, chat-llm 모두 영향
  ❌ 노드 전체 재시작 필요
  ❌ 3개 API 동시 다운타임

현재 구조 (1 API = 1 Node):
  ✅ k8s-api-auth 노드만 영향
  ✅ 다른 5개 API는 정상 동작
  ✅ auth만 재시작
```

### 2. 독립적인 스케일링
```bash
# 특정 API만 업그레이드
terraform apply -target=module.api_chat_llm
# → t3.small → t3.medium (단독 확장)

# 다른 API는 그대로 유지
# → 비용 효율적!
```

### 3. 명확한 모니터링
```yaml
Grafana Dashboard:
  - k8s-api-waste: CPU 80%, Memory 90%
    → waste-api 문제 즉시 식별
  
  - k8s-api-location: CPU 20%, Memory 30%
    → 정상 동작 확인
```

### 4. 배포 안정성
```bash
# Rolling Update - API별 독립 배포
kubectl rollout restart deployment/waste-api -n api

# 다른 API는 영향 없음
# → 무중단 배포 가능
```

### 5. 보안 격리
```yaml
네트워크 정책으로 API 간 통신 제한:
  - auth-api는 PostgreSQL만 접근
  - location-api는 외부 Kakao API만 호출
  - 불필요한 내부 통신 차단
```

---

## 🚀 Terraform 배포

```bash
cd terraform/
terraform init
terraform plan
terraform apply

# 노드 확인
terraform output cluster_info

# 출력 예시:
{
  total_nodes = 13
  total_vcpu = 18
  total_memory_gb = 26
  estimated_cost_usd = 270
  
  api_ips = [
    "54.180.xxx.1",  # waste
    "54.180.xxx.2",  # auth
    "54.180.xxx.3",  # userinfo
    "54.180.xxx.4",  # location
    "54.180.xxx.5",  # recycle-info
    "54.180.xxx.6"   # chat-llm
  ]
}
```

---

## 📋 NodeSelector 전략

### Helm values.yaml
```yaml
api:
  waste:
    nodeSelector:
      service: waste  # k8s-api-waste 노드만
  
  auth:
    nodeSelector:
      service: auth  # k8s-api-auth 노드만
  
  # ... 각 API별 독립 노드
```

### Ansible로 라벨 추가
```yaml
# playbooks/label-nodes.yml
- name: Label API nodes
  hosts: api_nodes
  tasks:
    - name: Add service label
      shell: |
        kubectl label node {{ inventory_hostname }} \
          service={{ service }} --overwrite
```

---

## 🎯 확장 계획

### 트래픽 증가 시
```bash
# 1단계: Replica 증가 (동일 노드 내)
api_waste.replicas: 3 → 5

# 2단계: 인스턴스 업그레이드
api_waste: t3.small → t3.medium

# 3단계: 노드 추가 (수평 확장)
# 새 노드: k8s-api-waste-2
# Load Balancer로 트래픽 분산
```

### 새 API 추가
```bash
# terraform/main.tf에 추가
module "api_notification" {
  source = "./modules/ec2"
  instance_name = "k8s-api-notification"
  instance_type = "t3.micro"
  ...
}

# Helm Chart에 추가
api.notification.enabled = true

# 자동 배포!
```

---

## 📊 리소스 요약

```yaml
총 13 Nodes:
  Control: 1
  API: 6 (독립)
  Worker: 2
  Infrastructure: 4

총 vCPU: 18 cores
총 RAM: 26GB
총 스토리지: 310GB

예상 비용: ~$270/월

AZ 분산:
  - ap-northeast-2a: 5 nodes
  - ap-northeast-2b: 4 nodes
  - ap-northeast-2c: 4 nodes
```

---

**🎉 결론: 완벽한 마이크로서비스 아키텍처!**

```
✅ 1 API = 1 Node = 명확한 책임
✅ 장애 격리 극대화
✅ 독립적인 스케일링
✅ 비용은 오히려 절감 ($15/월 ↓)
✅ 운영/모니터링 단순화
```

이제 각 팀은 자신의 API 노드만 집중 관리하면 됩니다! 🚀

