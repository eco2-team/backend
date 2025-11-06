# 🔄 Worker 분류 재분석 및 수정

## ❌ 기존 분류의 문제점

### 제가 잘못 분류한 것

```yaml
Worker-CPU:
  ❌ preprocess (CPU 집약)
  ❌ rag (CPU 집약)

Worker-Network:
  ❌ vision (Network 집약)
  ❌ llm (Network 집약)
  ❌ beat (Scheduler)
```

### 문제점

```yaml
1. preprocess 작업 분석:
   ❌ "CPU 집약"으로 분류
   
   실제 작업:
     - S3 업로드 → Network I/O
     - 이미지 해시 계산 → CPU (경량)
     - 이미지 크기 조정 → CPU (중간)
   
   결론: CPU보다 I/O 비중이 더 높음!

2. 단순한 Pool 타입으로만 분류:
   ❌ processes → CPU
   ❌ gevent → Network
   
   문제: Pool은 구현 방식일 뿐, 워크로드 특성 아님!
```

---

## ✅ 올바른 분류 기준

### 실제 워크로드 특성 분석

#### 1. preprocess-worker

```yaml
작업 내용:
  - S3 업로드 (boto3.upload_fileobj)
  - 이미지 해시 계산 (hashlib.sha256)
  - 이미지 크기 조정 (PIL.Image.resize)
  - Redis 캐시 체크

워크로드 특성:
  ⚠️ I/O: 매우 높음 (S3 업로드)
  ⚠️ Network: 높음 (AWS API 호출)
  ✅ CPU: 중간 (이미지 리사이징)
  ✅ Memory: 낮음

병목:
  🔴 S3 업로드 속도 (네트워크)
  🟡 이미지 리사이징 (CPU)

Pool 선택:
  - processes: 이미지 처리 GIL 회피
  - 하지만 실제 대기는 Network I/O

결론: I/O Bound (Network 성격 강함)
```

#### 2. vision-worker

```yaml
작업 내용:
  - GPT-5 Vision API 호출
  - JSON 응답 파싱

워크로드 특성:
  🔴 Network: 매우 높음 (외부 API)
  ✅ CPU: 매우 낮음 (JSON 파싱만)
  ✅ Memory: 낮음

병목:
  🔴 GPT-5 API 응답 시간 (네트워크)

Pool 선택:
  - gevent: 네트워크 대기 최적화

결론: 100% Network Bound
```

#### 3. rag-worker

```yaml
작업 내용:
  - JSON 파일 로컬 조회 (로컬 파일 읽기)
  - 텍스트 필터링
  - Prompt 구성

워크로드 특성:
  ✅ CPU: 낮음 (텍스트 처리)
  ✅ I/O: 낮음 (로컬 파일, 캐싱 가능)
  ✅ Memory: 낮음
  ✅ Network: 없음

병목:
  🟢 없음 (매우 빠름)

Pool 선택:
  - processes: CPU 병렬 처리

결론: Compute Bound (경량)
```

#### 4. llm-worker

```yaml
작업 내용:
  - GPT-4o mini API 호출
  - 응답 저장

워크로드 특성:
  🔴 Network: 매우 높음 (외부 API)
  ✅ CPU: 매우 낮음
  ✅ Memory: 낮음

병목:
  🔴 GPT-4o API 응답 시간 (네트워크)

Pool 선택:
  - gevent: 네트워크 대기 최적화

결론: 100% Network Bound
```

#### 5. celery-beat

```yaml
작업 내용:
  - 스케줄 관리
  - Task 발행 (RabbitMQ)

워크로드 특성:
  ✅ CPU: 극히 낮음
  ✅ Memory: 낮음
  ✅ Network: 낮음 (주기적 Task 발행)

결론: 매우 경량, 어디든 배치 가능
```

---

## 🎯 올바른 분류

### 기준 1: 주요 병목 (Bottleneck)

```yaml
Network Bound:
  🔴 vision-worker (GPT-5 API 대기)
  🔴 llm-worker (GPT-4o API 대기)
  🟡 preprocess-worker (S3 업로드 대기)

Compute Bound:
  🟢 rag-worker (CPU 처리, 매우 경량)

Scheduler:
  🟢 celery-beat (극히 경량)
```

### 기준 2: 리소스 특성

```yaml
높은 Concurrency 필요 (외부 API 대기):
  - vision-worker (20 concurrency)
  - llm-worker (10 concurrency)
  - preprocess-worker (8 concurrency)

낮은 Concurrency (CPU 처리):
  - rag-worker (4 concurrency)
```

---

## 🏗️ 올바른 노드 배치

### 제안: 워크로드 특성별 분리

#### 옵션 1: 단순 분리 (2 노드)

```yaml
Worker-IO (t3.medium, 4GB):
  워크로드: I/O & Network Bound
  
  배치:
    - preprocess-worker (×3)
    - vision-worker (×5)
    - llm-worker (×3)
    - celery-beat (×1)
  
  특징:
    - 대부분 시간을 대기 (S3, GPT API)
    - CPU 사용률 낮음 (20-30%)
    - 높은 concurrency
  
  리소스:
    CPU: 850m + 900m = 1750m (87.5%)
    RAM: 2176Mi + 768Mi = 2944Mi (72%)

Worker-Compute (t3.medium, 4GB):
  워크로드: CPU Bound
  
  배치:
    - rag-worker (×2)
  
  특징:
    - 로컬 파일 처리
    - CPU 집약 (텍스트 처리)
  
  리소스:
    CPU: 400m (20%)
    RAM: 512Mi (12%)
  
  ⚠️ 문제: 리소스 낭비 심함 (80% 유휴)
```

#### 옵션 2: 통합 배치 (1 노드) ← **비추**

```yaml
Worker-All (t3.medium, 4GB):
  모든 Worker 배치
  
  리소스:
    CPU: 2150m (107.5%) ❌ 초과
    RAM: 3456Mi (84%) ⚠️ 빡빡
  
  문제: 1개 노드로는 부족
```

#### 옵션 3: 혼합 배치 (2 노드) ← **추천** ✅

```yaml
Worker-1 (t3.medium, 4GB):
  라벨: workload=async-workers
  
  배치:
    - preprocess-worker (×3)
    - rag-worker (×2)
    - celery-beat (×1)
  
  이유:
    ✅ preprocess는 I/O지만 processes pool
    ✅ rag는 CPU지만 경량
    ✅ beat는 극히 경량
    ✅ 함께 배치해도 간섭 없음
  
  리소스:
    CPU: 900m + 400m + 50m = 1350m (67.5%) ✅
    RAM: 768Mi + 512Mi + 128Mi = 1408Mi (34%) ✅

Worker-2 (t3.medium, 4GB):
  라벨: workload=async-workers
  
  배치:
    - vision-worker (×5)
    - llm-worker (×3)
  
  이유:
    ✅ 둘 다 외부 API 호출
    ✅ 둘 다 gevent pool
    ✅ 둘 다 높은 concurrency
    ✅ 유사한 워크로드 특성
  
  리소스:
    CPU: 500m + 300m = 800m (40%) ✅
    RAM: 1280Mi + 768Mi = 2048Mi (50%) ✅
```

---

## 📊 최종 Worker 구성 (수정)

### Worker-1 노드

```yaml
노드: k8s-worker-1 (t3.medium, 4GB)
라벨: workload=async-workers
네임스페이스: workers

배치:
  1. preprocess-worker (×3):
     Pool: processes
     Concurrency: 8
     CPU: 300m each → 900m total
     RAM: 256Mi each → 768Mi total
  
  2. rag-worker (×2):
     Pool: processes
     Concurrency: 4
     CPU: 200m each → 400m total
     RAM: 256Mi each → 512Mi total
  
  3. celery-beat (×1):
     CPU: 50m
     RAM: 128Mi

총 리소스 (requests):
  CPU: 1350m / 2000m (67.5%) ✅
  RAM: 1408Mi / 4096Mi (34%) ✅

여유:
  CPU: 650m (32.5%)
  RAM: 2688Mi (66%)

특징:
  - preprocess: S3 업로드 (I/O)
  - rag: JSON 조회 (CPU)
  - beat: 스케줄링 (경량)
  - 서로 간섭 없음
```

### Worker-2 노드

```yaml
노드: k8s-worker-2 (t3.medium, 4GB)
라벨: workload=async-workers
네임스페이스: workers

배치:
  1. vision-worker (×5):
     Pool: gevent
     Concurrency: 20
     CPU: 100m each → 500m total
     RAM: 256Mi each → 1280Mi total
  
  2. llm-worker (×3):
     Pool: gevent
     Concurrency: 10
     CPU: 100m each → 300m total
     RAM: 256Mi each → 768Mi total

총 리소스 (requests):
  CPU: 800m / 2000m (40%) ✅
  RAM: 2048Mi / 4096Mi (50%) ✅

여유:
  CPU: 1200m (60%)
  RAM: 2048Mi (50%)

특징:
  - 둘 다 외부 API 호출
  - 둘 다 Network Bound
  - 실제 CPU 사용 매우 낮음 (10-20%)
  - 대부분 시간을 API 대기
```

---

## 🔑 핵심 정리

### 왜 이렇게 분류했나?

```yaml
❌ 잘못된 기준:
  - Pool 타입 (processes vs gevent)
  - CPU vs Network 단순 이분법

✅ 올바른 기준:
  1. 실제 워크로드 특성:
     - preprocess: I/O (S3 업로드)
     - vision/llm: Network (외부 API)
     - rag: CPU (로컬 처리)
  
  2. 리소스 사용 패턴:
     - preprocess + rag: processes pool
     - vision + llm: gevent pool, 높은 concurrency
  
  3. 배치 균형:
     - Worker-1: 1350m CPU (67.5%)
     - Worker-2: 800m CPU (40%)
     - 전체: 균형 잡힘
```

### 노드 라벨링

```yaml
현재 (7노드):
  k8s-worker-1: workload=async-workers
  k8s-worker-2: workload=async-workers

제안 (8노드):
  k8s-api-1: workload=api
  k8s-api-2: workload=api
  k8s-worker-1: workload=async-workers
  k8s-worker-2: workload=async-workers
  (나머지 4개: 인프라 전용)
```

---

**결론**: Worker-1(preprocess+rag+beat), Worker-2(vision+llm)로 혼합 배치가 가장 효율적입니다! ✅

