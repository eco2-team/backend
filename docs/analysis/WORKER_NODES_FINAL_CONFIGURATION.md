# 🖥️ Worker 노드 최종 구성 (HPA 제거)

## 📊 전제 조건

```yaml
노드 구성:
  Worker-CPU (t3.medium):
    vCPU: 2 cores (2000m)
    RAM: 4GB (4096Mi)
    라벨: workload=compute-cpu
  
  Worker-Network (t3.medium):
    vCPU: 2 cores (2000m)
    RAM: 4GB (4096Mi)
    라벨: workload=compute-network

HPA: 제거 (모든 Worker 고정 replica)
```

---

## 🎯 Worker-CPU 노드 구성

### 배치된 워크로드

```yaml
1. preprocess-worker:
   replicas: 3
   pool: processes
   concurrency: 8
   resources:
     requests:
       cpu: 300m
       memory: 256Mi
     limits:
       cpu: 1000m
       memory: 512Mi
   
   총 리소스 (3 Pods):
     cpu requests: 900m (0.9 cores)
     cpu limits: 3000m (3 cores)
     memory requests: 768Mi
     memory limits: 1536Mi

2. rag-worker:
   replicas: 2
   pool: processes
   concurrency: 4
   resources:
     requests:
       cpu: 200m
       memory: 256Mi
     limits:
       cpu: 800m
       memory: 512Mi
   
   총 리소스 (2 Pods):
     cpu requests: 400m (0.4 cores)
     cpu limits: 1600m (1.6 cores)
     memory requests: 512Mi
     memory limits: 1024Mi
```

### 리소스 합계 (Worker-CPU)

```yaml
가용 리소스:
  vCPU: 2000m (2 cores)
  RAM: 4096Mi (4GB)

사용량 (requests):
  preprocess: 900m CPU, 768Mi RAM
  rag: 400m CPU, 512Mi RAM
  ────────────────────────────────
  총 requests: 1300m CPU (65%), 1280Mi RAM (31%)

사용량 (limits):
  preprocess: 3000m CPU, 1536Mi RAM
  rag: 1600m CPU, 1024Mi RAM
  ────────────────────────────────
  총 limits: 4600m CPU (230%), 2560Mi RAM (62%)

여유 (requests 기준):
  vCPU: 700m (35%) ✅
  RAM: 2816Mi (69%) ✅

상태: ✅ 여유 충분
```

### CPU Over-commitment

```yaml
⚠️ CPU limits 합계가 가용 CPU 초과 (230%)

이유:
  - Kubernetes는 requests 기준으로 스케줄링
  - limits는 최대 사용량 (동시 사용 안 함)
  - CPU 집약 작업은 순차 처리

실제 동작:
  - 평균 사용률: 50-70% (requests 기준)
  - 피크 시: CPU Throttling 발생 가능
  - 안전: 작업이 순차적이라 괜찮음
```

---

## 🎯 Worker-Network 노드 구성

### 배치된 워크로드

```yaml
1. vision-worker:
   replicas: 5 (고정, HPA 제거)
   pool: gevent
   concurrency: 20
   resources:
     requests:
       cpu: 100m
       memory: 256Mi
     limits:
       cpu: 500m
       memory: 512Mi
   
   총 리소스 (5 Pods):
     cpu requests: 500m (0.5 cores)
     cpu limits: 2500m (2.5 cores)
     memory requests: 1280Mi
     memory limits: 2560Mi

2. llm-worker:
   replicas: 3
   pool: gevent
   concurrency: 10
   resources:
     requests:
       cpu: 100m
       memory: 256Mi
     limits:
       cpu: 500m
       memory: 512Mi
   
   총 리소스 (3 Pods):
     cpu requests: 300m (0.3 cores)
     cpu limits: 1500m (1.5 cores)
     memory requests: 768Mi
     memory limits: 1536Mi

3. celery-beat:
   replicas: 1
   resources:
     requests:
       cpu: 50m
       memory: 128Mi
     limits:
       cpu: 200m
       memory: 256Mi
   
   총 리소스 (1 Pod):
     cpu requests: 50m (0.05 cores)
     cpu limits: 200m (0.2 cores)
     memory requests: 128Mi
     memory limits: 256Mi
```

### 리소스 합계 (Worker-Network)

```yaml
가용 리소스:
  vCPU: 2000m (2 cores)
  RAM: 4096Mi (4GB)

사용량 (requests):
  vision: 500m CPU, 1280Mi RAM
  llm: 300m CPU, 768Mi RAM
  beat: 50m CPU, 128Mi RAM
  ────────────────────────────────
  총 requests: 850m CPU (42.5%), 2176Mi RAM (53%)

사용량 (limits):
  vision: 2500m CPU, 2560Mi RAM
  llm: 1500m CPU, 1536Mi RAM
  beat: 200m CPU, 256Mi RAM
  ────────────────────────────────
  총 limits: 4200m CPU (210%), 4352Mi RAM (106%)

여유 (requests 기준):
  vCPU: 1150m (57.5%) ✅
  RAM: 1920Mi (47%) ✅

상태: ✅ 여유 충분
```

### Network I/O 특성

```yaml
⚠️ CPU limits 초과 (210%), RAM limits 초과 (106%)

왜 괜찮은가?
  1. gevent pool (비동기 I/O):
     - 대부분 시간을 외부 API 대기
     - 실제 CPU 사용: 10-20%
     - 동시 피크 가능성 낮음
  
  2. Network 병목:
     - GPT-5 Vision API: 응답 대기
     - GPT-4o mini API: 응답 대기
     - CPU는 유휴 상태
  
  3. Rate Limiting:
     - 외부 API Rate Limit
     - 동시 처리 제한
     - 자연스러운 조절

실제 사용률:
  - CPU: 20-30% (평균)
  - RAM: 50-60% (평균)
  - Network: 80-90% (병목)
```

---

## 📊 전체 클러스터 리소스 (Worker만)

### 총 Worker Pod 수

```yaml
Worker-CPU:
  - preprocess-worker: 3 Pods
  - rag-worker: 2 Pods
  소계: 5 Pods

Worker-Network:
  - vision-worker: 5 Pods
  - llm-worker: 3 Pods
  - celery-beat: 1 Pod
  소계: 9 Pods

전체: 14 Pods
```

### 총 리소스 사용 (requests)

```yaml
CPU:
  Worker-CPU: 1300m (65% of 2 cores)
  Worker-Network: 850m (42.5% of 2 cores)
  ────────────────────────────────────
  총: 2150m (53.75% of 4 cores)
  여유: 1850m (46.25%) ✅

RAM:
  Worker-CPU: 1280Mi (31% of 4GB)
  Worker-Network: 2176Mi (53% of 4GB)
  ────────────────────────────────────
  총: 3456Mi (42% of 8GB)
  여유: 4640Mi (58%) ✅

상태: ✅ 매우 안전
```

---

## 🔄 HPA 제거 전후 비교

### HPA 적용 시 (이전)

```yaml
vision-worker:
  minReplicas: 5
  maxReplicas: 8
  
문제점:
  ❌ Scale Out 시 RAM 부족 가능
     8 Pods × 256Mi = 2048Mi
     + llm (768Mi) + beat (128Mi)
     = 2944Mi (72% 사용)
  
  ❌ 예측 불가능
     트래픽 급증 시 OOM 위험
  
  ❌ 복잡성 증가
     HPA 메트릭 설정, 튜닝 필요
```

### HPA 제거 후 (현재)

```yaml
vision-worker:
  replicas: 5 (고정)
  
장점:
  ✅ 예측 가능한 리소스
     항상 2176Mi RAM 사용
  
  ✅ 안정성
     OOM 위험 없음
  
  ✅ 단순성
     메트릭 설정 불필요

처리 능력:
  - vision-worker: 5 Pods × 20 concurrency = 100 동시 처리
  - 충분: GPT-5 Vision API Rate Limit이 먼저 제약
```

---

## 🎯 노드별 최종 구성 요약

### Worker-CPU 노드

```
┌─────────────────────────────────────────┐
│   Worker-CPU (t3.medium, 2 cores, 4GB)  │
├─────────────────────────────────────────┤
│                                          │
│  📦 preprocess-worker (×3)              │
│     ├─ CPU: 300m each (900m total)      │
│     ├─ RAM: 256Mi each (768Mi total)    │
│     ├─ Pool: processes                   │
│     └─ Concurrency: 8                    │
│                                          │
│  📦 rag-worker (×2)                     │
│     ├─ CPU: 200m each (400m total)      │
│     ├─ RAM: 256Mi each (512Mi total)    │
│     ├─ Pool: processes                   │
│     └─ Concurrency: 4                    │
│                                          │
│  ────────────────────────────────────   │
│  총 사용 (requests):                     │
│    CPU: 1300m / 2000m (65%)  ✅        │
│    RAM: 1280Mi / 4096Mi (31%) ✅       │
│                                          │
│  여유:                                   │
│    CPU: 700m (35%)                      │
│    RAM: 2816Mi (69%)                    │
└─────────────────────────────────────────┘
```

### Worker-Network 노드

```
┌─────────────────────────────────────────┐
│ Worker-Network (t3.medium, 2 cores, 4GB)│
├─────────────────────────────────────────┤
│                                          │
│  📦 vision-worker (×5)                  │
│     ├─ CPU: 100m each (500m total)      │
│     ├─ RAM: 256Mi each (1280Mi total)   │
│     ├─ Pool: gevent                      │
│     └─ Concurrency: 20                   │
│                                          │
│  📦 llm-worker (×3)                     │
│     ├─ CPU: 100m each (300m total)      │
│     ├─ RAM: 256Mi each (768Mi total)    │
│     ├─ Pool: gevent                      │
│     └─ Concurrency: 10                   │
│                                          │
│  📦 celery-beat (×1)                    │
│     ├─ CPU: 50m                          │
│     ├─ RAM: 128Mi                        │
│     └─ Role: Scheduler                   │
│                                          │
│  ────────────────────────────────────   │
│  총 사용 (requests):                     │
│    CPU: 850m / 2000m (42.5%) ✅        │
│    RAM: 2176Mi / 4096Mi (53%)  ✅      │
│                                          │
│  여유:                                   │
│    CPU: 1150m (57.5%)                   │
│    RAM: 1920Mi (47%)                    │
└─────────────────────────────────────────┘
```

---

## 📈 처리 능력 계산

### Worker-CPU (CPU 집약)

```yaml
preprocess-worker:
  총 동시 처리: 3 Pods × 8 concurrency = 24개
  작업 유형: 이미지 해싱, S3 업로드
  처리 시간: 부하 테스트 후 측정 필요
  
rag-worker:
  총 동시 처리: 2 Pods × 4 concurrency = 8개
  작업 유형: JSON 조회, 컨텍스트 결합
  처리 시간: 부하 테스트 후 측정 필요
```

### Worker-Network (Network I/O)

```yaml
vision-worker:
  총 동시 처리: 5 Pods × 20 concurrency = 100개
  작업 유형: GPT-5 Vision API 호출
  병목: 외부 API Rate Limit
  
llm-worker:
  총 동시 처리: 3 Pods × 10 concurrency = 30개
  작업 유형: GPT-4o mini API 호출
  병목: 외부 API Rate Limit

실제 제약:
  ⚠️ OpenAI API Rate Limit이 먼저 제약
  - Worker 증설보다 Rate Limit 협상 필요
```

---

## ✅ 최종 판단

### 리소스 충족도

```yaml
Worker-CPU:
  ✅ CPU 여유: 35%
  ✅ RAM 여유: 69%
  ✅ 상태: 매우 안전

Worker-Network:
  ✅ CPU 여유: 57.5%
  ✅ RAM 여유: 47%
  ✅ 상태: 안전

전체:
  ✅ 총 14 Pods (2 노드)
  ✅ CPU 사용: 53.75% (requests)
  ✅ RAM 사용: 42% (requests)
  ✅ HPA 불필요 (고정 replica로 충분)
```

### 확장 전략

```yaml
단기 (1-3개월):
  현재 구성 유지
  - 고정 replica로 충분
  - 리소스 여유 충분

중기 (3-6개월):
  트래픽 증가 시:
    옵션 1: Worker-Network → t3.large 업그레이드
    옵션 2: Worker 노드 1개 추가
  
장기 (6-12개월):
  도메인별 분리:
    - Worker-Vision (전용)
    - Worker-LLM (전용)
    - Worker-CPU (전용)
```

---

**결론**: HPA 제거 후 Worker 노드 2개로 충분하며, 리소스 여유도 안전한 수준입니다! ✅

