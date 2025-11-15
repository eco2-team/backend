# Redis JWT BlackList 설계 문서

## 📋 개요

JWT는 기본적으로 Stateless하지만, 다음 상황에서 즉시 무효화가 필요합니다:
- 사용자 로그아웃
- 계정 탈퇴
- 비밀번호 변경
- 관리자에 의한 강제 로그아웃

BlackList 방식으로 이를 효율적으로 처리합니다.

---

## 🔧 Redis 데이터 구조

### Database 할당

```yaml
Redis Databases:
  0: JWT BlackList          # ← 변경
  1: API Response Cache
  2: Celery Task Results
  3: Rate Limiting
```

### BlackList Key 설계

```python
# Key Pattern
blacklist:{jti}

# 예시
blacklist:550e8400-e29b-41d4-a716-446655440000

# Value
{
    "user_id": "12345",
    "reason": "logout",  # logout, account_deleted, password_changed, force_logout
    "blacklisted_at": "2025-11-08T12:00:00Z",
    "expires_at": "2025-11-08T13:00:00Z"  # JWT exp와 동일
}

# TTL
- JWT 만료 시간까지 (exp - now)
- 만료되면 Redis가 자동 삭제
```

---

## 🏗️ 아키텍처

### 1. JWT 발급 (auth-api)

```python
from datetime import datetime, timedelta
import uuid
import jwt

def create_access_token(user_id: str) -> str:
    """
    Access Token 생성 (1시간)
    """
    jti = str(uuid.uuid4())
    
    payload = {
        "user_id": user_id,
        "jti": jti,  # JWT ID (고유 식별자)
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=1),
        "type": "access"
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token


def create_refresh_token(user_id: str) -> str:
    """
    Refresh Token 생성 (7일)
    """
    jti = str(uuid.uuid4())
    
    payload = {
        "user_id": user_id,
        "jti": jti,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=7),
        "type": "refresh"
    }
    
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token
```

### 2. JWT 검증 미들웨어

```python
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import redis
import json

redis_client = redis.Redis(host="k8s-redis", port=6379, db=0, decode_responses=True)
security = HTTPBearer()


async def verify_token(credentials: HTTPAuthorizationCredentials):
    """
    JWT 검증 및 BlackList 체크
    """
    token = credentials.credentials
    
    try:
        # 1. JWT 디코딩
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        jti = payload.get("jti")
        user_id = payload.get("user_id")
        
        # 2. BlackList 체크 (Redis)
        blacklist_key = f"blacklist:{jti}"
        if redis_client.exists(blacklist_key):
            # BlackList에 있음 → 무효화된 토큰
            blacklist_info = json.loads(redis_client.get(blacklist_key))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token has been revoked: {blacklist_info['reason']}"
            )
        
        # 3. 검증 성공
        return {
            "user_id": user_id,
            "jti": jti,
            "payload": payload
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# FastAPI Dependency
from fastapi import Depends

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    현재 사용자 정보 가져오기
    """
    token_data = await verify_token(credentials)
    return token_data
```

### 3. 로그아웃 처리

```python
from datetime import datetime
import json

async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: dict = Depends(get_current_user)
):
    """
    로그아웃 - BlackList에 추가
    """
    jti = current_user["jti"]
    user_id = current_user["user_id"]
    exp = current_user["payload"]["exp"]
    
    # BlackList에 추가
    blacklist_key = f"blacklist:{jti}"
    blacklist_data = {
        "user_id": user_id,
        "reason": "logout",
        "blacklisted_at": datetime.utcnow().isoformat(),
        "expires_at": datetime.fromtimestamp(exp).isoformat()
    }
    
    # TTL 계산 (만료 시간까지)
    ttl_seconds = exp - int(datetime.utcnow().timestamp())
    if ttl_seconds > 0:
        redis_client.setex(
            blacklist_key,
            ttl_seconds,
            json.dumps(blacklist_data)
        )
    
    return {"message": "Logged out successfully"}
```

### 4. 계정 탈퇴 처리

```python
async def delete_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: dict = Depends(get_current_user)
):
    """
    계정 탈퇴 - 모든 활성 토큰 무효화
    """
    user_id = current_user["user_id"]
    
    # 1. 현재 토큰 BlackList 추가
    jti = current_user["jti"]
    exp = current_user["payload"]["exp"]
    
    blacklist_key = f"blacklist:{jti}"
    blacklist_data = {
        "user_id": user_id,
        "reason": "account_deleted",
        "blacklisted_at": datetime.utcnow().isoformat(),
        "expires_at": datetime.fromtimestamp(exp).isoformat()
    }
    
    ttl_seconds = exp - int(datetime.utcnow().timestamp())
    if ttl_seconds > 0:
        redis_client.setex(
            blacklist_key,
            ttl_seconds,
            json.dumps(blacklist_data)
        )
    
    # 2. 사용자의 모든 활성 토큰 무효화
    # (선택 사항: user_tokens:{user_id} Set에 JTI 추적)
    user_tokens_key = f"user_tokens:{user_id}"
    token_jtis = redis_client.smembers(user_tokens_key)
    
    for jti in token_jtis:
        blacklist_key = f"blacklist:{jti}"
        # 각 토큰을 BlackList에 추가
        # (TTL은 각 토큰의 exp에 맞게 설정)
    
    # 3. 사용자 토큰 추적 Set 삭제
    redis_client.delete(user_tokens_key)
    
    # 4. DB에서 사용자 데이터 삭제
    # await delete_user_from_db(user_id)
    
    return {"message": "Account deleted successfully"}
```

---

## 📊 메모리 효율성 비교

### Session 방식 (기존)

```python
# 모든 활성 사용자의 세션 저장
사용자 10,000명 x 500 bytes = 5MB

# 문제점
- 모든 요청마다 Redis 조회
- 사용자가 많을수록 메모리 증가
- Stateless 장점 상실
```

### BlackList 방식 (개선)

```python
# 로그아웃/탈퇴한 사용자만 저장
- 일반적으로 동시 로그아웃: 전체 사용자의 1-5%
- 10,000명 중 500명 로그아웃 = 250KB
- TTL 자동 정리로 메모리 효율적

# 장점
- 메모리 사용량 95% 감소
- JWT Stateless 유지
- Redis 부하 감소 (BlackList 체크만)
```

---

## 🔐 보안 강화

### 1. Refresh Token Rotation

```python
async def refresh_access_token(refresh_token: str):
    """
    Access Token 갱신 + Refresh Token Rotation
    """
    # 1. Refresh Token 검증
    payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])
    old_jti = payload["jti"]
    user_id = payload["user_id"]
    
    # 2. BlackList 체크
    if redis_client.exists(f"blacklist:{old_jti}"):
        raise HTTPException(status_code=401, detail="Token revoked")
    
    # 3. 새 토큰 발급
    new_access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    
    # 4. 기존 Refresh Token BlackList 추가 (Rotation)
    exp = payload["exp"]
    ttl = exp - int(datetime.utcnow().timestamp())
    if ttl > 0:
        redis_client.setex(
            f"blacklist:{old_jti}",
            ttl,
            json.dumps({
                "user_id": user_id,
                "reason": "token_rotated",
                "blacklisted_at": datetime.utcnow().isoformat()
            })
        )
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token
    }
```

### 2. 다중 디바이스 관리

```python
# 사용자별 활성 토큰 추적
user_tokens:{user_id} = Set[jti1, jti2, jti3]

# 로그인 시 추가
redis_client.sadd(f"user_tokens:{user_id}", jti)

# 로그아웃 시 제거
redis_client.srem(f"user_tokens:{user_id}", jti)

# 모든 디바이스 로그아웃
all_jtis = redis_client.smembers(f"user_tokens:{user_id}")
for jti in all_jtis:
    # BlackList 추가
    pass
```

---

## 🎯 Best Practices

### 1. JTI는 필수

```python
# ✅ Good
payload = {
    "user_id": "123",
    "jti": str(uuid.uuid4()),  # 고유 ID
    "exp": datetime.utcnow() + timedelta(hours=1)
}

# ❌ Bad
payload = {
    "user_id": "123",
    # jti 없음 → BlackList 불가능
    "exp": datetime.utcnow() + timedelta(hours=1)
}
```

### 2. TTL 자동 정리

```python
# Redis에서 자동 삭제되도록 TTL 설정
ttl_seconds = exp - int(datetime.utcnow().timestamp())
redis_client.setex(key, ttl_seconds, value)

# 수동 정리 불필요
```

### 3. Redis 파이프라인 사용

```python
# 여러 토큰을 한 번에 BlackList에 추가
pipe = redis_client.pipeline()
for jti in jtis:
    pipe.setex(f"blacklist:{jti}", ttl, data)
pipe.execute()
```

### 4. 모니터링

```python
# BlackList 크기 모니터링
blacklist_count = len(redis_client.keys("blacklist:*"))

# 메트릭 수집
prometheus_client.gauge("redis_blacklist_size", blacklist_count)
```

---

## 🔄 Migration 계획

### Step 1: Redis Database 재구성

```bash
# Redis 설정 변경
redis-cli -h k8s-redis

# Database 0 정리 (기존 세션 삭제)
SELECT 0
FLUSHDB

# 새로운 구조 시작
```

### Step 2: auth-api 코드 업데이트

```python
# 1. JWT에 jti 추가
# 2. 검증 로직에 BlackList 체크 추가
# 3. 로그아웃/탈퇴 시 BlackList 추가
```

### Step 3: 점진적 배포

```yaml
# Blue-Green Deployment
1. auth-api-v2 배포 (BlackList 방식)
2. 트래픽 일부 전환 (10%)
3. 모니터링 (에러율, 응답 시간)
4. 점진적 확대 (50% → 100%)
5. auth-api-v1 제거
```

---

## 📊 성능 비교

| 항목 | Session 방식 | BlackList 방식 |
|-----|-------------|----------------|
| Redis 메모리 | 5MB (10K users) | 250KB (500 logout) |
| 요청당 Redis 조회 | 모든 요청 | BlackList만 |
| JWT Stateless | ❌ | ✅ |
| 스케일링 | Redis 병목 | 수평 확장 가능 |
| 로그아웃 즉시성 | 즉시 | 즉시 |

---

## 🎓 참고 자료

- [RFC 7519 - JWT](https://datatracker.ietf.org/doc/html/rfc7519)
- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [Redis Best Practices](https://redis.io/docs/manual/patterns/)

---

**최종 업데이트**: 2025-11-08  
**적용 Phase**: Phase 1 (즉시 적용 가능)

