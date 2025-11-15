# 🏗️ 이미지 처리 아키텍처

> **4-Tier 기반 AI 쓰레기 분류 파이프라인**  
> **RabbitMQ (Task Queue) + Redis (Cache & State)**  
> **날짜**: 2025-10-31  
> **상태**: ✅ 프로덕션 준비

## 📋 목차

1. [시스템 개요](#시스템-개요)
2. [4-Tier 아키텍처](#4-tier-아키텍처)
3. [Celery 이중 연결](#celery-이중-연결)
4. [데이터 흐름](#데이터-흐름)
5. [Redis 캐싱 전략](#redis-캐싱-전략)
6. [최적화](#최적화)

---

## 🎯 시스템 개요

### 서비스 목표

```
사용자가 쓰레기 사진을 찍으면:
1. GPT-4o Vision이 재질/형태/혼합 여부 분석
2. LLM이 "어떻게, 왜 그렇게 버려야 하는지" 설명
3. 위치 기반으로 가장 가까운 재활용 수거함 추천

핵심:
✅ 응답 시간: 3-5초 (캐시 히트 시 1초)
✅ AI 비용 절감: 70% (Image Hash Cache)
✅ 동시 처리: 100-500명
```

---

## 🏗️ 4-Tier 아키텍처

### Image Processing in 4-Tier

```mermaid
graph TB
    subgraph Client["Client Layer"]
        User["사용자
Mobile App"]
    end
    
    subgraph AWS["AWS Services"]
        Route53["Route53"]
        ALB["ALB
L7 Routing"]
        S3["S3
Pre-signed URL
Image Storage"]
    end
    
    subgraph Tier1["Tier 1: Control Plane"]
        CP["Master
Orchestration"]
    end
    
    subgraph Tier2["Tier 2: Data Plane"]
        API["waste-service x2
FastAPI Sync API
 
1. Job ID 생성
2. S3 URL 발급
3. Task 발행"]
        
        Worker["AI Workers x3
Celery Async
 
1. 이미지 다운로드
2. Hash 계산
3. GPT-4o Vision
4. 결과 저장"]
    end
    
    subgraph Tier3["Tier 3: Message Queue"]
        RMQ["RabbitMQ HA x3
 
q.ai Queue
 
Task 전달
일회성 메시지"]
    end
    
    subgraph Tier4["Tier 4: Persistence"]
        Redis["Redis
 
DB 1: Image Hash Cache
DB 2: Job Progress
 
반복 조회 가능"]
        
        DB["PostgreSQL
 
Final Results
User History"]
    end
    
    subgraph External["External"]
        OpenAI["OpenAI
GPT-4o Vision"]
    end
    
    User --> Route53
    Route53 --> ALB
    ALB --> API
    
    User --> S3
    
    API -->|"1. publish task"| RMQ
    RMQ -->|"2. consume task"| Worker
    Worker -->|"3. ACK (삭제)"| RMQ
    
    Worker -->|"4. update progress
0.5초마다 덮어쓰기"| Redis
    Worker -->|"5. check cache
반복 조회"| Redis
    
    API -->|"6. get progress
0.5초마다 조회"| Redis
    
    Worker --> S3
    Worker --> OpenAI
    Worker --> DB
    
    style Client fill:#0d47a1,color:#fff,stroke:#01579b,stroke-width:3px
    style AWS fill:#e65100,color:#fff,stroke:#bf360c,stroke-width:3px
    style Tier1 fill:#1565c0,color:#fff,stroke:#0d47a1,stroke-width:4px
    style Tier2 fill:#2e7d32,color:#fff,stroke:#1b5e20,stroke-width:4px
    style Tier3 fill:#f57c00,color:#fff,stroke:#e65100,stroke-width:4px
    style Tier4 fill:#c2185b,color:#fff,stroke:#880e4f,stroke-width:4px
    style API fill:#81c784,color:#000,stroke:#66bb6a,stroke-width:2px
    style Worker fill:#a5d6a7,color:#000,stroke:#81c784,stroke-width:2px
    style RMQ fill:#ffb74d,color:#000,stroke:#ffa726,stroke-width:2px
    style Redis fill:#f48fb1,color:#000,stroke:#ec407a,stroke-width:2px
    style DB fill:#f8bbd0,color:#000,stroke:#f48fb1,stroke-width:2px
```

---

## 🔄 Celery 이중 연결 구조

### RabbitMQ + Redis 동시 사용

```python
from celery import Celery

# Celery는 두 개의 독립적인 연결 유지
app = Celery('waste_processor',
    # Tier 3: Message Queue (Task 전달)
    broker='amqp://admin:password@rabbitmq.messaging:5672//',
    
    # Tier 4: Storage (결과 및 상태 저장)
    result_backend='redis://redis.default:6379/0'
)

# 역할 분리:
# RabbitMQ (broker): Task를 Producer → Consumer 전달
# Redis (result_backend): Task 결과 및 진행률 저장
```

### Tier 3: RabbitMQ (Message Queue)

```
역할: Task 전달 (일회성 메시지)

특성:
✅ Producer가 Task 발행
✅ Queue에 메시지 저장
✅ Consumer가 consume
✅ ACK 후 메시지 삭제
✅ 한 번만 전달 (Exactly Once)

사용:
└─ Task 전달용
   - API → Worker로 작업 요청
   - Priority, Routing 지원
   - Delivery Guarantee
```

### Tier 4: Redis (Persistence - Cache & State)

```
역할: 상태 저장 (반복 조회 가능)

특성:
✅ Key-Value Store
✅ Random Access (특정 key 직접 조회)
✅ Overwrite 가능 (최신 값으로 업데이트)
✅ 여러 번 읽어도 데이터 유지
✅ TTL 자동 만료

사용:
├─ DB 0: Celery Result Backend
├─ DB 1: Image Hash Cache ⭐⭐⭐⭐⭐
├─ DB 2: Job Progress Tracking ⭐⭐⭐⭐
└─ DB 3: Session Store
```

---

## 📊 데이터 흐름

### 전체 시퀀스 (4-Tier)

```mermaid
sequenceDiagram
    actor User
    participant App as Mobile App
    participant API as Tier 2 Sync<br/>waste-service
    participant MQ as Tier 3 MQ<br/>RabbitMQ q.ai
    participant Worker as Tier 2 Async<br/>AI Worker
    participant Redis as Tier 4 Cache<br/>Redis DB1,DB2
    participant DB as Tier 4 DB<br/>PostgreSQL
    participant S3
    participant AI as OpenAI API
    
    User->>App: [1] 쓰레기 사진 촬영
    
    App->>API: [2] POST /api/v1/waste/analyze
    API->>API: Job ID 생성
    API->>App: S3 Pre-signed URL
    
    App->>S3: [3] 이미지 직접 업로드
    
    App->>API: [4] POST /upload-complete/{job_id}
    
    Note over API: Tier 2 Data Plane<br/>비즈니스 로직
    API->>MQ: [5] Publish q.ai<br/>ai.analyze
    Note over MQ: Tier 3 Middleware<br/>메시지 전달 (일회성)
    
    MQ->>Worker: [6] Consume task
    Worker->>MQ: ACK (메시지 삭제)
    
    activate Worker
    Note over Worker: Tier 2 Data Plane<br/>비동기 처리
    
    Worker->>Redis: [7] 10% 이미지 다운로드 중
    Note over Redis: Tier 4 Persistence<br/>DB 2: Progress
    
    Worker->>S3: 이미지 다운로드
    Worker->>Worker: Hash 계산 (pHash)
    
    Worker->>Redis: [8] 캐시 확인<br/>cache:hash:{phash}
    Note over Redis: Tier 4 Persistence<br/>DB 1: Image Cache
    
    alt Cache Hit 70%
        Redis-->>Worker: 캐시된 결과
        Worker->>Redis: 100% 완료
        Worker-->>App: 즉시 응답 1초
    else Cache Miss 30%
        Worker->>Redis: 30% 전처리 중
        Worker->>Redis: 50% AI 분석 중
        
        Worker->>AI: GPT-4o Vision API
        AI-->>Worker: 분류 결과
        
        Worker->>Redis: 70% 피드백 생성 중
        Worker->>Redis: 90% 위치 검색 중
        
        Worker->>DB: 최종 결과 저장
        Note over DB: Tier 4 Persistence<br/>영구 저장
        
        Worker->>Redis: 캐싱 7일<br/>cache:hash:{phash}
        Worker->>Redis: 100% 완료
    end
    deactivate Worker
    
    loop Polling 0.5초마다
        App->>API: [9] GET /status/{job_id}
        API->>Redis: 진행률 조회 (반복)
        Note over Redis: Tier 4<br/>같은 Key 반복 조회 가능!
        Redis-->>App: progress: 80%
    end
    
    App->>API: [10] GET /result/{job_id}
    API->>Redis: 최종 결과 조회
    Redis-->>App: result
    
    App->>User: 결과 표시
```

---

## 🐰 RabbitMQ 역할 (Tier 3)

### Task 전달만!

```python
# Producer (waste-service, Tier 2)
from celery import current_app

@app.post("/upload-complete/{job_id}")
async def upload_complete(job_id: str):
    # RabbitMQ에 Task 발행
    current_app.send_task(
        'tasks.analyze_image',
        args=[job_id],
        queue='q.ai',
        routing_key='ai.analyze',
        priority=10
    )
    # → RabbitMQ q.ai에 메시지 추가
    # → Worker가 consume할 때까지 대기
    
    return {"status": "queued"}

# Consumer (AI Worker, Tier 2)
@celery_app.task(bind=True, queue='q.ai')
def analyze_image(self, job_id):
    # RabbitMQ에서 메시지 받음
    # (여기서 메시지는 큐에서 제거됨)
    
    # 실제 처리...
    
    # 완료 후 RabbitMQ에 ACK
    # → 메시지 완전 삭제
    return result

# RabbitMQ 역할:
# ✅ Producer → Consumer 메시지 전달
# ✅ 한 번 전달하면 끝
# ❌ 진행률 저장 못 함 (메시지 삭제되니까)
```

---

## 💾 Redis 역할 (Tier 4)

### 1. Image Hash Cache (DB 1) ⭐⭐⭐⭐⭐

**가장 중요! AI 비용 70% 절감**

```python
import imagehash
from PIL import Image
import redis

redis_cache = redis.Redis(host='redis.default', port=6379, db=1)

@celery_app.task
def analyze_image(job_id):
    # 1. 이미지 다운로드
    image_path = download_from_s3(f"{job_id}.jpg")
    
    # 2. Perceptual Hash 계산
    img = Image.open(image_path)
    phash = str(imagehash.phash(img, hash_size=16))
    
    # 3. 캐시 확인 (Redis DB 1)
    cache_key = f"cache:image:hash:{phash}"
    cached = redis_cache.get(cache_key)
    
    if cached:
        # 캐시 히트! AI API 호출 스킵!
        print("✅ 캐시 히트! AI 비용 절감!")
        return json.loads(cached)
    
    # 4. 캐시 미스 → AI 분석
    result = await analyze_with_gpt4o_vision(image_path)
    
    # 5. 결과 캐싱 (7일)
    redis_cache.setex(
        cache_key,
        86400 * 7,  # 7일
        json.dumps(result)
    )
    
    return result

# 효과:
# - 같은 쓰레기 사진 (콜라캔, 우유팩 등)
# - 10,000 요청 중 7,000 캐시 히트
# - AI API 호출: 3,000회만 (70% 절감!)
# - 비용 절감: $100/월 이상
```

### 2. Job Progress Tracking (DB 2) ⭐⭐⭐⭐

**0.5초마다 반복 조회**

```python
redis_progress = redis.Redis(host='redis.default', port=6379, db=2)

# Worker (진행률 업데이트)
def analyze_image(job_id):
    # 10% - 다운로드
    update_progress(job_id, 10, "이미지 다운로드 중...")
    download_image()
    
    # 30% - 해시 계산
    update_progress(job_id, 30, "캐시 확인 중...")
    calculate_hash()
    
    # 50% - AI 분석
    update_progress(job_id, 50, "AI 분석 중...")
    analyze_with_ai()
    
    # 100% - 완료
    update_progress(job_id, 100, "완료!")

def update_progress(job_id, progress, message):
    # Redis에 진행률 저장 (Overwrite)
    redis_progress.setex(
        f"job:{job_id}:progress",
        3600,  # 1시간 TTL
        json.dumps({
            "progress": progress,
            "message": message,
            "updated_at": datetime.now().isoformat()
        })
    )

# API (진행률 조회)
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    # Redis에서 조회 (0.5초마다 반복!)
    progress = await redis_progress.get(f"job:{job_id}:progress")
    
    # ✅ 같은 Key를 무한 반복 조회 가능
    # ✅ 메시지 삭제 안 됨
    # ✅ 여러 API 서버에서 동시 조회
    
    return json.loads(progress)

# RabbitMQ로는 불가능한 이유:
# ❌ consume하면 메시지 삭제됨
# ❌ 0.5초마다 새 메시지 발행? (비효율)
# ❌ Random access 불가
```

### 3. Celery Result Backend (DB 0) ⭐⭐⭐

**Celery 표준**

```python
# Celery 설정
result_backend = 'redis://redis.default:6379/0'

# Worker (자동 저장)
@app.task
def analyze_image(job_id):
    return {"waste_type": "PET", "confidence": 0.95}
    # Celery가 자동으로 Redis DB 0에 저장
    # celery-task-meta-{task_id} = {...}

# API (결과 조회)
task = analyze_image.apply_async(args=[job_id])
result = task.get(timeout=10)  # Redis에서 조회
# task.state  → 'SUCCESS'
# task.result → {"waste_type": "PET", ...}
```

### 4. Session Store (DB 3) ⭐⭐

```python
redis_session = redis.Redis(host='redis.default', port=6379, db=3)

# Refresh Token 저장
redis_session.setex(
    f"session:{user_id}:refresh",
    86400 * 30,  # 30일
    refresh_token
)

# OAuth State (CSRF 방지)
redis_session.setex(
    f"oauth:state:{state}",
    600,  # 10분
    json.dumps(user_data)
)
```

---

## 🔄 완전한 데이터 흐름

### 코드 예시

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tier 2: FastAPI (waste-service)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/api/v1/waste/analyze")
async def create_analysis():
    job_id = str(uuid.uuid4())
    
    # S3 Pre-signed URL
    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': 'images', 'Key': f'{job_id}.jpg'},
        ExpiresIn=300
    )
    
    # Redis DB 2: 초기 진행률
    await redis_progress.setex(
        f"job:{job_id}:progress",
        3600,
        json.dumps({"progress": 0, "status": "pending"})
    )
    
    return {"job_id": job_id, "upload_url": upload_url}

@app.post("/upload-complete/{job_id}")
async def upload_complete(job_id: str):
    # RabbitMQ (Tier 3)에 Task 발행
    celery_app.send_task(
        'tasks.analyze_image',
        args=[job_id],
        queue='q.ai',
        routing_key='ai.analyze'
    )
    # → RabbitMQ q.ai에 메시지 추가
    
    return {"status": "processing"}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    # Redis DB 2에서 진행률 조회 (0.5초마다 반복)
    progress = await redis_progress.get(f"job:{job_id}:progress")
    return json.loads(progress)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tier 2: Celery Worker (AI Worker)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

celery_app = Celery(
    broker='amqp://admin:password@rabbitmq.messaging:5672//',  # Tier 3
    result_backend='redis://redis.default:6379/0'  # Tier 4
)

@celery_app.task(bind=True, queue='q.ai')
def analyze_image(self, job_id):
    # [RabbitMQ에서 메시지 받음 → ACK → 메시지 삭제]
    
    # 10% - 다운로드
    update_progress(job_id, 10, "다운로드 중...")
    image_path = download_from_s3(f"{job_id}.jpg")
    
    # 20% - Hash 계산
    update_progress(job_id, 20, "캐시 확인 중...")
    img = Image.open(image_path)
    phash = str(imagehash.phash(img, hash_size=16))
    
    # 캐시 확인 (Redis DB 1)
    cache_key = f"cache:image:hash:{phash}"
    cached = redis_cache.get(cache_key)
    
    if cached:
        update_progress(job_id, 100, "캐시 히트!")
        return json.loads(cached)
    
    # 50% - AI 분석
    update_progress(job_id, 50, "AI 분석 중...")
    result = gpt4o_vision_api(image_path)
    
    # 70% - 피드백 생성
    update_progress(job_id, 70, "피드백 생성 중...")
    feedback = generate_feedback(result)
    
    # 90% - DB 저장
    update_progress(job_id, 90, "저장 중...")
    save_to_db(job_id, result)
    
    # 결과 캐싱 (Redis DB 1, 7일)
    final_result = {"waste_type": result, "feedback": feedback}
    redis_cache.setex(cache_key, 86400 * 7, json.dumps(final_result))
    
    # 100% - 완료
    update_progress(job_id, 100, "완료!")
    
    return final_result  # → Redis DB 0 (result_backend)

def update_progress(job_id, progress, message):
    # Redis DB 2에 진행률 저장 (Overwrite)
    redis_progress.setex(
        f"job:{job_id}:progress",
        3600,
        json.dumps({"progress": progress, "message": message})
    )
```

---

## 💡 Redis 캐싱 전략 (Tier 4)

### Image Hash Cache (핵심!)

```python
# Perceptual Hash (pHash)
def calculate_image_hash(image_path):
    """
    동일/유사 이미지 감지:
    - 정확히 같은 사진 → 같은 해시
    - 약간 회전/크기 변경 → 같은 해시
    - 완전히 다른 사진 → 다른 해시
    """
    img = Image.open(image_path)
    return str(imagehash.phash(img, hash_size=16))

# 예시:
hash1 = phash("콜라캔_정면.jpg")     # "a1b2c3d4e5f6g7h8"
hash2 = phash("콜라캔_측면.jpg")     # "a1b2c3d4e5f6g7h8" (거의 동일!)
hash3 = phash("사이다캔.jpg")        # "z9y8x7w6v5u4t3s2" (다름)

# 캐시 전략:
cache_key = f"cache:image:hash:{hash1}"
cached_result = redis.get(cache_key)

if cached_result:
    # 캐시 히트!
    # - AI API 호출 스킵
    # - 응답 시간: 1초
    # - 비용: $0
    return json.loads(cached_result)

# 캐시 미스
result = call_ai_api()  # 3-5초, 비용 $0.01
redis.setex(cache_key, 86400 * 7, json.dumps(result))

# 효과:
# 월 10,000 요청 × 70% 캐시 히트 = 7,000회 절감
# 비용 절감: 7,000 × $0.01 = $70/월
```

---

## 📊 Redis DB별 데이터 구조

```python
# Redis 6개 DB 활용

# DB 0: Celery Result Backend (Celery 자동 관리)
celery-task-meta-{task_id} = {
    "status": "SUCCESS",
    "result": {...},
    "traceback": null,
    "children": []
}
TTL: task_result_expires (default 24h)

# DB 1: Image Hash Cache ⭐⭐⭐⭐⭐
cache:image:hash:{phash} = {
    "waste_type": "PET 플라스틱",
    "confidence": 0.95,
    "feedback": "깨끗이 세척 후 라벨 제거...",
    "analyzed_at": "2025-10-31T10:30:00"
}
TTL: 604800초 (7일)
예상 크기: 1KB × 10,000 = 10MB
캐시 히트율: 70%+

# DB 2: Job Progress Tracking ⭐⭐⭐⭐
job:{job_id}:progress = {
    "progress": 50,
    "message": "AI 분석 중...",
    "stage": "ai_vision",
    "updated_at": "2025-10-31T10:30:45"
}
TTL: 3600초 (1시간)
업데이트 빈도: 10-15회/job
조회 빈도: 20-30회/job (0.5초마다)

# DB 3: Session Store ⭐⭐
session:{user_id}:refresh_token = "eyJhbGc..."
TTL: 2592000초 (30일)

oauth:state:{state} = {"user_id": 123, "provider": "kakao"}
TTL: 600초 (10분)

# DB 4: Rate Limiting ⭐
ratelimit:ip:{ip}:{endpoint} = 15  # 요청 횟수
TTL: 60초 (1분)
```

---

## 🎯 최적화 효과

### Image Hash Cache 효과

```
시나리오: 월 10,000 이미지 분석 요청

캐시 없이:
├─ AI API 호출: 10,000회
├─ 평균 비용: $0.01/요청
├─ 총 비용: $100/월
└─ 평균 응답: 5초

Image Hash Cache (70% 히트):
├─ AI API 호출: 3,000회 (70% 절감!)
├─ 캐시 히트: 7,000회
├─ AI 비용: $30/월
├─ Redis 비용: ~$5/월
├─ 총 비용: $35/월
├─ 절감: $65/월 (65%!)
└─ 평균 응답: 2.2초 (캐시 1초 + AI 5초)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Image Hash Cache = 가장 중요한 최적화!
```

---

## 🎯 결론

### RabbitMQ vs Redis 역할

```
Tier 3: RabbitMQ (Message Queue)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Task 전달 (일회성)
✅ Producer → Consumer
✅ Consume 후 메시지 삭제
✅ Priority, Routing
✅ Delivery Guarantee

사용:
└─ Task Queue (비동기 작업 요청)

❌ Progress Tracking 불가
   - 메시지 삭제됨
   - 반복 조회 불가
   - Random access 불가

Tier 4: Redis (Persistence - Cache & State)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 상태 저장 (반복 조회 가능)
✅ Key-Value (Random access)
✅ Overwrite 가능
✅ 여러 번 읽기 가능
✅ TTL 자동 관리

사용:
├─ DB 0: Celery Result Backend
├─ DB 1: Image Hash Cache ⭐⭐⭐⭐⭐ (70% 절감!)
├─ DB 2: Job Progress Tracking ⭐⭐⭐⭐
└─ DB 3: Session Store

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Celery 연결:
✅ broker = RabbitMQ (Task 전달)
✅ result_backend = Redis (결과 및 상태 저장)

두 개 모두 필요!
```

---

**image-processing-architecture.md가 올바른 구조로 재작성되었습니다!** ✅

**가장 중요한 것: Redis DB 1 (Image Hash Cache) - AI 비용 70% 절감!** 💰