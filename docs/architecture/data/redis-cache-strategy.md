# Redis 캐싱 전략 설계 (Cache-Aside Pattern)

## 🎯 Redis Database 재구성

### Database 할당

```yaml
Redis Databases (0-15):
  DB 0: JWT BlackList (auth 전용)
  DB 1: API Response Cache (공통)
  DB 2: User Profile Cache (my)
  DB 3: Character State Cache (character)
  DB 4: Location Cache (location)
  DB 5: Recycle Info Cache (info)
  DB 6: Chat History Cache (chat)
  DB 7: Scan Results Cache (scan)
  DB 8: Rate Limiting (공통)
  DB 9: Celery Task Results (Worker)
  DB 10-15: 예약 (미래 확장)
```

---

## 🏗️ Cache-Aside 패턴 구현

### 패턴 개요

```python
# Cache-Aside (Look-Aside) 패턴
def get_data(key):
    # 1. Redis 조회
    data = redis.get(key)
    
    if data:
        # 2a. Cache Hit
        return data
    else:
        # 2b. Cache Miss
        data = db.query(key)  # DB 조회
        redis.set(key, data, ex=TTL)  # Cache 저장
        return data

def update_data(key, value):
    # 1. DB 업데이트
    db.update(key, value)
    
    # 2. Cache 무효화
    redis.delete(key)
    # 또는 Cache 즉시 갱신
    # redis.set(key, value, ex=TTL)
```

---

## 📦 도메인별 캐싱 전략

### 1. auth (DB 0: JWT BlackList)

```python
# services/auth-api/cache.py
import redis
from datetime import datetime, timedelta
import json

redis_auth = redis.Redis(host="k8s-redis", port=6379, db=0, decode_responses=True)

class JWTBlackList:
    """JWT BlackList 관리"""
    
    @staticmethod
    def add_to_blacklist(jti: str, user_id: str, reason: str, exp: int):
        """BlackList에 추가"""
        key = f"blacklist:{jti}"
        
        data = {
            "user_id": user_id,
            "reason": reason,
            "blacklisted_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.fromtimestamp(exp).isoformat()
        }
        
        # TTL 계산
        ttl = exp - int(datetime.utcnow().timestamp())
        if ttl > 0:
            redis_auth.setex(key, ttl, json.dumps(data))
    
    @staticmethod
    def is_blacklisted(jti: str) -> bool:
        """BlackList 확인"""
        return redis_auth.exists(f"blacklist:{jti}")
    
    @staticmethod
    def get_blacklist_info(jti: str) -> dict:
        """BlackList 정보 조회"""
        data = redis_auth.get(f"blacklist:{jti}")
        return json.loads(data) if data else None

# 사용 예시
# if JWTBlackList.is_blacklisted(jti):
#     raise HTTPException(401, "Token revoked")
```

### 2. my (DB 2: User Profile Cache)

```python
# services/my-api/cache.py
import redis
import json
from typing import Optional

redis_my = redis.Redis(host="k8s-redis", port=6379, db=2, decode_responses=True)

class UserProfileCache:
    """사용자 프로필 캐시"""
    
    TTL = 3600  # 1시간
    
    @staticmethod
    def get_profile(user_id: str) -> Optional[dict]:
        """프로필 조회 (Cache-Aside)"""
        key = f"user:profile:{user_id}"
        
        # 1. Redis 조회
        cached = redis_my.get(key)
        if cached:
            return json.loads(cached)
        
        # 2. PostgreSQL 조회
        profile = db.query(
            "SELECT * FROM my_db.users WHERE user_id = %s",
            (user_id,)
        ).fetchone()
        
        if profile:
            # 3. Redis에 저장
            redis_my.setex(key, UserProfileCache.TTL, json.dumps(profile))
        
        return profile
    
    @staticmethod
    def update_profile(user_id: str, data: dict):
        """프로필 업데이트"""
        key = f"user:profile:{user_id}"
        
        # 1. PostgreSQL 업데이트
        db.execute(
            "UPDATE my_db.users SET ... WHERE user_id = %s",
            (user_id,)
        )
        
        # 2. Cache 무효화
        redis_my.delete(key)
        
        # 또는 즉시 갱신
        # redis_my.setex(key, UserProfileCache.TTL, json.dumps(data))
    
    @staticmethod
    def get_activity_history(user_id: str) -> list:
        """활동 내역 조회"""
        key = f"user:activity:{user_id}"
        
        # Redis 조회
        cached = redis_my.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL 조회
        activities = db.query(
            "SELECT * FROM my_db.activities WHERE user_id = %s ORDER BY created_at DESC LIMIT 100",
            (user_id,)
        ).fetchall()
        
        # Redis 저장 (TTL 짧게 - 자주 변경됨)
        redis_my.setex(key, 300, json.dumps(activities))  # 5분
        
        return activities

# FastAPI 엔드포인트
@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    profile = UserProfileCache.get_profile(user_id)
    if not profile:
        raise HTTPException(404, "User not found")
    return profile

@router.put("/profile/{user_id}")
async def update_profile(user_id: str, data: ProfileUpdate):
    UserProfileCache.update_profile(user_id, data.dict())
    return {"message": "Profile updated"}
```

### 3. character (DB 3: Character State Cache)

```python
# services/character-api/cache.py
import redis
import json

redis_character = redis.Redis(host="k8s-redis", port=6379, db=3, decode_responses=True)

class CharacterCache:
    """캐릭터 상태 캐시"""
    
    TTL = 600  # 10분 (자주 변경됨)
    
    @staticmethod
    def get_character_state(user_id: str) -> dict:
        """캐릭터 상태 조회"""
        key = f"character:state:{user_id}"
        
        # Redis 조회
        cached = redis_character.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL 조회
        character = db.query(
            """
            SELECT c.*, 
                   COUNT(m.id) as total_missions,
                   SUM(CASE WHEN m.status='completed' THEN 1 ELSE 0 END) as completed_missions
            FROM character_db.characters c
            LEFT JOIN character_db.missions m ON c.user_id = m.user_id
            WHERE c.user_id = %s
            GROUP BY c.id
            """,
            (user_id,)
        ).fetchone()
        
        if character:
            redis_character.setex(key, CharacterCache.TTL, json.dumps(character))
        
        return character
    
    @staticmethod
    def update_character_exp(user_id: str, exp_gain: int):
        """경험치 업데이트 (Write-Through)"""
        key = f"character:state:{user_id}"
        
        # 1. PostgreSQL 업데이트
        db.execute(
            "UPDATE character_db.characters SET exp = exp + %s WHERE user_id = %s",
            (exp_gain, user_id)
        )
        
        # 2. Redis에서 즉시 갱신 (Write-Through)
        cached = redis_character.get(key)
        if cached:
            character = json.loads(cached)
            character['exp'] += exp_gain
            
            # 레벨업 체크
            if character['exp'] >= character['exp_required']:
                character['level'] += 1
                character['exp'] -= character['exp_required']
                character['exp_required'] = calculate_exp_required(character['level'])
            
            redis_character.setex(key, CharacterCache.TTL, json.dumps(character))
        else:
            # Cache Miss면 무효화만
            redis_character.delete(key)
    
    @staticmethod
    def get_mission_list(user_id: str) -> list:
        """미션 목록 조회"""
        key = f"character:missions:{user_id}"
        
        cached = redis_character.get(key)
        if cached:
            return json.loads(cached)
        
        missions = db.query(
            "SELECT * FROM character_db.missions WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        
        redis_character.setex(key, CharacterCache.TTL, json.dumps(missions))
        
        return missions

# FastAPI 엔드포인트
@router.get("/character/{user_id}")
async def get_character(user_id: str):
    return CharacterCache.get_character_state(user_id)

@router.post("/character/{user_id}/exp")
async def gain_exp(user_id: str, exp: int):
    CharacterCache.update_character_exp(user_id, exp)
    return {"message": "Exp gained"}
```

### 4. location (DB 4: Location Cache) ⭐ 중요

```python
# services/location-api/cache.py
import redis
import json
from typing import List

redis_location = redis.Redis(host="k8s-redis", port=6379, db=4, decode_responses=True)

class LocationCache:
    """위치 정보 캐시 (높은 히트율)"""
    
    TTL = 86400  # 24시간 (거의 변경 안 됨)
    
    @staticmethod
    def search_nearby_centers(lat: float, lon: float, radius: int = 5) -> List[dict]:
        """근처 재활용 센터 검색"""
        # Geo 해싱으로 캐시 키 생성
        geo_hash = geohash.encode(lat, lon, precision=5)  # ~2.5km
        key = f"location:nearby:{geo_hash}:{radius}"
        
        # Redis 조회
        cached = redis_location.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL + PostGIS 조회
        centers = db.query(
            """
            SELECT id, name, address, lat, lon,
                   ST_Distance(
                       ST_MakePoint(%s, %s)::geography,
                       ST_MakePoint(lon, lat)::geography
                   ) as distance
            FROM location_db.recycle_centers
            WHERE ST_DWithin(
                ST_MakePoint(lon, lat)::geography,
                ST_MakePoint(%s, %s)::geography,
                %s * 1000
            )
            ORDER BY distance
            LIMIT 20
            """,
            (lon, lat, lon, lat, radius)
        ).fetchall()
        
        # Redis 저장 (긴 TTL)
        redis_location.setex(key, LocationCache.TTL, json.dumps(centers))
        
        return centers
    
    @staticmethod
    def get_center_detail(center_id: str) -> dict:
        """센터 상세 정보"""
        key = f"location:center:{center_id}"
        
        cached = redis_location.get(key)
        if cached:
            return json.loads(cached)
        
        center = db.query(
            "SELECT * FROM location_db.recycle_centers WHERE id = %s",
            (center_id,)
        ).fetchone()
        
        if center:
            # 센터 정보는 거의 변경 안 됨
            redis_location.setex(key, LocationCache.TTL, json.dumps(center))
        
        return center
    
    @staticmethod
    def warm_cache_popular_locations():
        """인기 위치 사전 캐싱 (Cron Job)"""
        # 서울 주요 지역
        popular_coords = [
            (37.5665, 126.9780),  # 서울 시청
            (37.5172, 127.0473),  # 강남역
            (37.5511, 126.9882),  # 홍대입구
            # ... 더 추가
        ]
        
        for lat, lon in popular_coords:
            LocationCache.search_nearby_centers(lat, lon)

# FastAPI 엔드포인트
@router.get("/centers/nearby")
async def search_nearby(lat: float, lon: float, radius: int = 5):
    return LocationCache.search_nearby_centers(lat, lon, radius)

@router.get("/centers/{center_id}")
async def get_center(center_id: str):
    return LocationCache.get_center_detail(center_id)
```

### 5. info (DB 5: Recycle Info Cache) ⭐ 중요

```python
# services/info-api/cache.py
import redis
import json

redis_info = redis.Redis(host="k8s-redis", port=6379, db=5, decode_responses=True)

class RecycleInfoCache:
    """재활용 정보 캐시 (거의 정적)"""
    
    TTL = 604800  # 7일 (거의 변경 안 됨)
    
    @staticmethod
    def get_recycle_guide(category: str) -> dict:
        """재활용 가이드 조회"""
        key = f"info:guide:{category}"
        
        # Redis 조회
        cached = redis_info.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL 조회
        guide = db.query(
            "SELECT * FROM info_db.recycle_guides WHERE category = %s",
            (category,)
        ).fetchone()
        
        if guide:
            # 긴 TTL (거의 변경 안 됨)
            redis_info.setex(key, RecycleInfoCache.TTL, json.dumps(guide))
        
        return guide
    
    @staticmethod
    def get_all_categories() -> list:
        """전체 카테고리 목록"""
        key = "info:categories:all"
        
        cached = redis_info.get(key)
        if cached:
            return json.loads(cached)
        
        categories = db.query(
            "SELECT DISTINCT category FROM info_db.recycle_guides ORDER BY category"
        ).fetchall()
        
        redis_info.setex(key, RecycleInfoCache.TTL, json.dumps(categories))
        
        return categories
    
    @staticmethod
    def search_info(keyword: str) -> list:
        """키워드 검색"""
        key = f"info:search:{keyword.lower()}"
        
        cached = redis_info.get(key)
        if cached:
            return json.loads(cached)
        
        results = db.query(
            """
            SELECT * FROM info_db.recycle_guides
            WHERE LOWER(title) LIKE %s OR LOWER(content) LIKE %s
            LIMIT 50
            """,
            (f"%{keyword}%", f"%{keyword}%")
        ).fetchall()
        
        # 검색 결과도 캐싱
        redis_info.setex(key, 3600, json.dumps(results))  # 1시간
        
        return results
    
    @staticmethod
    def warm_cache_all_guides():
        """전체 가이드 사전 캐싱 (앱 시작 시)"""
        guides = db.query("SELECT * FROM info_db.recycle_guides").fetchall()
        
        for guide in guides:
            key = f"info:guide:{guide['category']}"
            redis_info.setex(key, RecycleInfoCache.TTL, json.dumps(guide))
        
        print(f"Warmed cache: {len(guides)} guides")

# FastAPI 시작 시
@app.on_event("startup")
async def startup():
    RecycleInfoCache.warm_cache_all_guides()

# FastAPI 엔드포인트
@router.get("/guides/{category}")
async def get_guide(category: str):
    return RecycleInfoCache.get_recycle_guide(category)

@router.get("/search")
async def search(keyword: str):
    return RecycleInfoCache.search_info(keyword)
```

### 6. chat (DB 6: Chat History Cache)

```python
# services/chat-api/cache.py
import redis
import json

redis_chat = redis.Redis(host="k8s-redis", port=6379, db=6, decode_responses=True)

class ChatHistoryCache:
    """대화 기록 캐시"""
    
    TTL = 1800  # 30분
    
    @staticmethod
    def get_recent_history(user_id: str, limit: int = 10) -> list:
        """최근 대화 기록"""
        key = f"chat:history:{user_id}"
        
        # Redis 조회
        cached = redis_chat.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL 조회
        history = db.query(
            """
            SELECT * FROM chat_db.conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit)
        ).fetchall()
        
        redis_chat.setex(key, ChatHistoryCache.TTL, json.dumps(history))
        
        return history
    
    @staticmethod
    def add_conversation(user_id: str, message: str, response: str):
        """대화 추가 (Write-Through)"""
        key = f"chat:history:{user_id}"
        
        # 1. PostgreSQL 저장
        db.execute(
            """
            INSERT INTO chat_db.conversations (user_id, message, response, created_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (user_id, message, response)
        )
        
        # 2. Cache 무효화 (다음 조회 시 갱신)
        redis_chat.delete(key)

# FastAPI 엔드포인트
@router.get("/chat/history/{user_id}")
async def get_history(user_id: str, limit: int = 10):
    return ChatHistoryCache.get_recent_history(user_id, limit)
```

### 7. scan (DB 7: Scan Results Cache)

```python
# services/scan-api/cache.py
import redis
import json

redis_scan = redis.Redis(host="k8s-redis", port=6379, db=7, decode_responses=True)

class ScanResultCache:
    """스캔 결과 캐시"""
    
    TTL = 3600  # 1시간
    
    @staticmethod
    def get_scan_result(task_id: str) -> dict:
        """스캔 결과 조회"""
        key = f"scan:result:{task_id}"
        
        # Redis 조회
        cached = redis_scan.get(key)
        if cached:
            return json.loads(cached)
        
        # PostgreSQL 조회
        result = db.query(
            "SELECT * FROM scan_db.scan_results WHERE task_id = %s",
            (task_id,)
        ).fetchone()
        
        if result:
            redis_scan.setex(key, ScanResultCache.TTL, json.dumps(result))
        
        return result
    
    @staticmethod
    def get_user_scan_history(user_id: str, limit: int = 20) -> list:
        """사용자 스캔 히스토리"""
        key = f"scan:history:{user_id}"
        
        cached = redis_scan.get(key)
        if cached:
            return json.loads(cached)
        
        history = db.query(
            """
            SELECT * FROM scan_db.scan_results
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit)
        ).fetchall()
        
        redis_scan.setex(key, ScanResultCache.TTL, json.dumps(history))
        
        return history

# FastAPI 엔드포인트
@router.get("/scan/{task_id}")
async def get_scan_result(task_id: str):
    return ScanResultCache.get_scan_result(task_id)

@router.get("/scan/history/{user_id}")
async def get_history(user_id: str):
    return ScanResultCache.get_user_scan_history(user_id)
```

---

## 🔄 Cache Invalidation 전략

### 1. TTL 기반 (시간 만료)

```python
# 가장 간단하고 안전
redis.setex(key, TTL, value)

# TTL 설정 가이드:
정적 데이터 (info): 7일
위치 데이터 (location): 1일
프로필 (my): 1시간
캐릭터 상태 (character): 10분
대화 기록 (chat): 30분
```

### 2. 명시적 무효화 (업데이트 시)

```python
# Write-Through: 업데이트 즉시 Cache 갱신
def update_profile(user_id, data):
    db.update(user_id, data)
    redis.set(f"user:profile:{user_id}", data, ex=TTL)

# Write-Behind: Cache 삭제 후 다음 조회 시 갱신
def update_profile(user_id, data):
    db.update(user_id, data)
    redis.delete(f"user:profile:{user_id}")
```

### 3. 패턴 기반 무효화

```python
# 특정 패턴의 모든 키 삭제
def invalidate_user_cache(user_id):
    pattern = f"*:{user_id}"
    for key in redis.scan_iter(match=pattern):
        redis.delete(key)
```

---

## 📊 Cache Warming (사전 로딩)

### 앱 시작 시

```python
# services/info-api/main.py
@app.on_event("startup")
async def warm_cache():
    # 1. 재활용 정보 전체 캐싱
    RecycleInfoCache.warm_cache_all_guides()
    
    # 2. 인기 위치 캐싱
    LocationCache.warm_cache_popular_locations()
    
    print("✅ Cache warmed")
```

### Cron Job으로 정기 갱신

```yaml
# kubernetes/cronjobs/cache-warming.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cache-warming
spec:
  schedule: "0 2 * * *"  # 매일 새벽 2시
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cache-warmer
            image: ghcr.io/mangowhoiscloud/cache-warmer:latest
            command:
            - python
            - scripts/warm_cache.py
```

---

## 🎯 Redis 설정 최적화

```conf
# k8s-redis ConfigMap
maxmemory 1.5gb
maxmemory-policy allkeys-lru

# LRU (Least Recently Used)
# - 메모리 부족 시 가장 오래된 키 삭제
# - Cache로 사용하기 적합

# Persistence
save 900 1
save 300 10
save 60 10000

appendonly yes
appendfsync everysec
```

---

## 📈 모니터링

```python
# Prometheus 메트릭
from prometheus_client import Counter, Histogram

cache_hits = Counter('redis_cache_hits', 'Redis cache hits', ['db', 'operation'])
cache_misses = Counter('redis_cache_misses', 'Redis cache misses', ['db', 'operation'])
cache_latency = Histogram('redis_cache_latency_seconds', 'Redis operation latency', ['db', 'operation'])

def get_with_metrics(key, db_num):
    with cache_latency.labels(db=db_num, operation='get').time():
        result = redis.get(key)
        
        if result:
            cache_hits.labels(db=db_num, operation='get').inc()
        else:
            cache_misses.labels(db=db_num, operation='get').inc()
        
        return result
```

---

## 🎯 최종 요약

```yaml
Redis Database 구성:
  DB 0: JWT BlackList (auth)
  DB 1: API Response Cache (공통)
  DB 2: User Profile (my)
  DB 3: Character State (character)
  DB 4: Location (location) ⭐ 높은 히트율
  DB 5: Recycle Info (info) ⭐ 높은 히트율
  DB 6: Chat History (chat)
  DB 7: Scan Results (scan)
  DB 8: Rate Limiting
  DB 9: Celery Results

캐싱 전략:
  - Cache-Aside (Look-Aside) 패턴
  - TTL 자동 만료
  - Write-Through (중요 데이터)
  - Cache Warming (정적 데이터)

TTL 가이드:
  - 정적 (info): 7일
  - 위치 (location): 1일
  - 프로필 (my): 1시간
  - 캐릭터 (character): 10분
  - 대화 (chat): 30분
```

---

**작성일**: 2025-11-08  
**최종 구성**: Redis 9개 DB, Cache-Aside 패턴, 도메인별 최적화

