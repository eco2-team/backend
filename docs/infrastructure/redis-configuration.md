# 💾 Redis 구성 및 사용 전략

> **Tier 4: Persistence Layer - Cache & State Management**  
> **날짜**: 2025-10-31  
> **배포**: Storage Node (t3.large, 8GB)

## 📋 목차

1. [Redis 역할 (Tier 4)](#redis-역할-tier-4)
2. [DB별 사용 전략](#db별-사용-전략)
3. [Kubernetes 배포](#kubernetes-배포)
4. [모니터링](#모니터링)

---

## 🎯 Redis 역할 (Tier 4)

### Tier 4 Persistence Layer

```
Redis 책임:
✅ Caching (성능 최적화)
✅ State Storage (상태 저장, 반복 조회 가능)
✅ Result Backend (Celery)
✅ Rate Limiting (DDoS 방지)

❌ Session Store (JWT Stateless이므로 불필요)
❌ Message Queue (RabbitMQ가 담당)

관심사:
└─ "빠르게 접근 가능한 데이터를 어떻게 저장할 것인가?"
```

---

## 📊 DB별 사용 전략

### DB 0: Celery Result Backend ⭐⭐⭐

```python
# Celery 설정
result_backend = 'redis://redis.default:6379/0'

# 자동 저장 (Celery가 관리)
celery-task-meta-{task_id} = {
    "status": "SUCCESS",
    "result": {...},
    "traceback": null,
    "date_done": "2025-10-31T10:30:00"
}

TTL: 86400초 (24시간, task_result_expires)
크기: ~1-5KB/task
예상 메모리: ~50MB (10,000 tasks)

사용:
└─ Celery Worker가 자동 저장
└─ task.get() 결과 조회
```

### DB 1: Image Hash Cache ⭐⭐⭐⭐⭐ (최우선!)

```python
# AI 비용 70% 절감의 핵심!

# Perceptual Hash 기반 캐싱
import imagehash
from PIL import Image

# Hash 계산
img = Image.open("trash.jpg")
phash = str(imagehash.phash(img, hash_size=16))

# 캐시 키
cache:image:hash:{phash} = {
    "waste_type": "PET 플라스틱",
    "confidence": 0.95,
    "feedback": "깨끗이 세척 후 라벨 제거하고 뚜껑 분리...",
    "category": "플라스틱",
    "recyclable": true,
    "analyzed_at": "2025-10-31T10:30:00"
}

TTL: 604800초 (7일)
크기: ~10KB/이미지
예상 메모리: ~100MB (10,000 unique 이미지)

효과:
✅ 같은 쓰레기 사진 (콜라캔, 우유팩 등)
✅ 10,000 요청 중 7,000 캐시 히트 (70%)
✅ AI API 호출: 3,000회만
✅ 비용 절감: $70/월
✅ 응답 속도: 5초 → 1초

가장 중요한 최적화!
```

### DB 2: Job Progress Tracking ⭐⭐⭐⭐

```python
# 0.5초마다 Polling (RabbitMQ 불가!)

# Worker (진행률 업데이트)
job:{job_id}:progress = {
    "progress": 50,
    "message": "AI 분석 중...",
    "stage": "ai_vision",
    "updated_at": "2025-10-31T10:30:45"
}

TTL: 3600초 (1시간)
크기: ~1KB/job
예상 메모리: ~10MB (1,000 active jobs)

업데이트 빈도: 10-15회/job
조회 빈도: 20-30회/job (0.5초마다)

# API (반복 조회)
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    progress = await redis.get(f"job:{job_id}:progress")
    # ✅ 같은 Key 무한 반복 조회
    # ✅ Overwrite 가능
    # ✅ 여러 API 서버에서 동시 조회
    return json.loads(progress)
```

### DB 3: Rate Limiting ⭐⭐

```python
# DDoS 방지 및 API 보호

from fastapi import Request
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

# 설정
await FastAPILimiter.init(redis_url="redis://redis.default:6379/3")

# 사용
@app.post("/api/v1/waste/analyze",
    dependencies=[Depends(RateLimiter(times=60, seconds=60))]
)
async def analyze():
    # 1분당 60회 제한
    pass

# Redis 데이터 구조
ratelimit:ip:{ip}:{endpoint} = 15  # 현재 요청 횟수
TTL: 60초

# 또는 수동 구현
key = f"ratelimit:ip:{client_ip}:/api/v1/waste/analyze"
count = await redis.incr(key)
if count == 1:
    await redis.expire(key, 60)
if count > 60:
    raise HTTPException(429, "Too many requests")

크기: ~100B/IP
예상 메모리: ~5MB (10,000 IPs)
```

### DB 4: Token Blacklist ⭐ (선택)

```python
# 로그아웃 및 탈취 토큰 무효화

# 로그아웃 시
@app.post("/api/v1/auth/logout")
async def logout(token: str = Depends(verify_jwt)):
    payload = decode_jwt(token)
    
    # 1. Refresh Token DB에서 삭제 (PostgreSQL)
    await db.execute(
        "DELETE FROM refresh_tokens WHERE user_id = $1",
        payload["user_id"]
    )
    
    # 2. Access Token Blacklist (Redis)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_in = payload["exp"] - int(time.time())
    
    await redis.setex(
        f"blacklist:token:{token_hash}",
        expires_in,  # Token 만료 시간까지만
        "revoked"
    )

# 모든 API 요청 시 확인 (Middleware)
@app.middleware("http")
async def check_token_blacklist(request: Request, call_next):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        is_blacklisted = await redis.exists(f"blacklist:token:{token_hash}")
        if is_blacklisted:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has been revoked"}
            )
    return await call_next(request)

크기: ~100B/token
예상 메모리: ~1MB (선택 사용)
```

---

## 🚀 Kubernetes 배포

### Redis Deployment (Tier 4)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
      tier: persistence
  template:
    metadata:
      labels:
        app: redis
        tier: persistence
    spec:
      nodeSelector:
        workload: storage  # Storage 노드
      containers:
      - name: redis
        image: redis:7-alpine
        command:
        - redis-server
        - --appendonly yes
        - --maxmemory 2gb
        - --maxmemory-policy allkeys-lru
        - --databases 16
        ports:
        - containerPort: 6379
        volumeMounts:
        - name: data
          mountPath: /data
        resources:
          requests:
            cpu: 200m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi
        livenessProbe:
          tcpSocket:
            port: 6379
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: data
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: default
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
  type: ClusterIP
```

### ConfigMap (DB별 설정)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
  namespace: default
data:
  redis.conf: |
    # DB 분리
    databases 16
    
    # 메모리 관리
    maxmemory 2gb
    maxmemory-policy allkeys-lru
    
    # Persistence
    appendonly yes
    appendfsync everysec
    
    # 네트워크
    tcp-backlog 511
    timeout 0
    
    # 클라이언트 연결
    maxclients 10000
```

---

## 📊 모니터링

### Prometheus Metrics

```yaml
# Redis Exporter
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-exporter
  namespace: default
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: exporter
        image: oliver006/redis_exporter:latest
        env:
        - name: REDIS_ADDR
          value: "redis.default:6379"
        ports:
        - containerPort: 9121

---
# ServiceMonitor (Prometheus)
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: redis
  namespace: default
spec:
  selector:
    matchLabels:
      app: redis
  endpoints:
  - port: metrics
    interval: 30s
```

### 주요 메트릭

```
메모리:
├─ redis_memory_used_bytes
├─ redis_memory_max_bytes
└─ redis_memory_fragmentation_ratio

성능:
├─ redis_commands_processed_total
├─ redis_keyspace_hits_total (캐시 히트)
├─ redis_keyspace_misses_total (캐시 미스)
└─ redis_connected_clients

DB별:
├─ redis_db_keys{db="1"}  # Image Cache
├─ redis_db_keys{db="2"}  # Job Progress
└─ redis_db_keys{db="3"}  # Rate Limit

알람:
├─ 캐시 히트율 < 60% → Warning
├─ 메모리 사용 > 80% → Warning
└─ 연결 수 > 5000 → Warning
```

---

## 🎯 Best Practices

### 1. 캐시 히트율 최적화

```python
# Image Hash Cache 히트율 목표: 70%+

# 모니터링
hits = redis.info('stats')['keyspace_hits']
misses = redis.info('stats')['keyspace_misses']
hit_rate = hits / (hits + misses) * 100

# 히트율 낮으면:
# - TTL 늘리기 (7일 → 14일)
# - Hash 알고리즘 조정 (hash_size 증가)
# - 유사 이미지 범위 확대
```

### 2. 메모리 관리

```python
# maxmemory-policy 설정
maxmemory 2gb
maxmemory-policy allkeys-lru  # LRU eviction

# DB별 우선순위:
# DB 1 (Image Cache) → 가장 중요 (큰 메모리)
# DB 2 (Progress) → TTL 1시간 (자동 정리)
# DB 3 (Rate Limit) → TTL 1분 (자동 정리)
# DB 4 (Blacklist) → TTL 동적 (자동 정리)
```

### 3. Persistence 설정

```
appendonly yes
appendfsync everysec

# RDB + AOF 혼합:
# - RDB: 빠른 복구
# - AOF: 데이터 안전성

백업:
- AOF 파일: /data/appendonly.aof
- RDB 파일: /data/dump.rdb
```

---

## 📚 관련 문서

- [RabbitMQ HA 구성](rabbitmq-ha-setup.md) - Tier 3
- [Task Queue 설계](../architecture/task-queue-design.md)
- [Image Processing](../architecture/image-processing-architecture.md)

---

**작성일**: 2025-10-31  
**Tier**: 4 (Persistence)  
**노드**: Storage (공유)  
**메모리**: ~2GB (총 8GB 중)

