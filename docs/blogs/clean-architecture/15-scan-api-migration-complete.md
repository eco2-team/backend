# 이코에코(Eco²) Clean Architecture #15: Scan API Clean Architecture 마이그레이션 완료

> 작성일: 2026-01-09
> 작성자: Backend Team, Frontend Team
> 이전 글: [#14 Celery + RabbitMQ 트러블슈팅](../async/14-celery-rabbitmq-troubleshooting.md)

## 개요

Scan API의 Clean Architecture 마이그레이션을 완료하고, 프론트엔드와 E2E 연동 테스트를 성공적으로 마쳤습니다. 이 글에서는 #14 이후 진행된 주요 작업과 의사결정을 정리합니다.

### 주요 성과

| 항목 | 상태 |
|------|------|
| Scan API Clean Architecture | ✅ 완료 |
| RabbitMQ Topology CR 일원화 | ✅ 완료 |
| Fanout Exchange 1:N 라우팅 | ✅ 완료 |
| FE-BE E2E 연동 | ✅ 완료 |
| Image API Redis 안정성 개선 | ✅ 완료 |
| FE SSE 실시간 스캔 진행 상태 | ✅ 완료 |
| FE 캐릭터 Optimistic Update | ✅ 완료 |

---

## 1. RabbitMQ Queue 전략 최종 결정

### 1.1 문제 상황

`scan.reward` 태스크 완료 시 두 개의 서비스에 데이터를 저장해야 했습니다:

```python
# 기존 구현 (2번 publish)
celery_app.send_task("character.save_ownership", args=[...])  # 1번째
celery_app.send_task("users.save_character", args=[...])      # 2번째
```

**문제점:**
- 동일 데이터를 2번 네트워크 전송
- 원자성 미보장 (하나만 실패 가능)
- 의도 불명확 (같은 이벤트인지 다른 이벤트인지)

### 1.2 해결: Fanout Exchange 도입

```
scan.reward 완료
      │
      │ kombu.Producer.publish(exchange='reward.events')
      │ (1번만 publish!)
      ▼
┌─────────────────────┐
│   reward.events     │  Fanout Exchange
│  (type: fanout)     │  routing_key 무시, 모든 바인딩 큐로 브로드캐스트
└─────────────────────┘
      │
      ├── character.save_ownership 큐 → character-worker
      └── users.save_character 큐 → users-worker
```

### 1.3 왜 Named Direct가 아닌 Fanout인가?

초기에는 Named Direct Exchange를 계획했으나, Celery의 한계로 Fanout으로 전환했습니다.

```python
# ❌ 실패: Celery send_task()의 exchange 파라미터가 무시됨
celery_app.send_task(
    "reward.character",
    exchange="reward.direct",  # task_routes에 의해 무시됨!
    routing_key="reward.character",
)

# ✅ 성공: kombu Producer + Fanout Exchange
from kombu import Connection, Exchange, Producer
from kombu.pools import producers

exchange = Exchange("reward.events", type="fanout", durable=True)
with producers[conn].acquire(block=True) as producer:
    producer.publish(
        payload,
        exchange=exchange,
        routing_key="",  # Fanout은 무시
        serializer="json",
    )
```

| 관점 | Named Direct | Fanout |
|------|--------------|--------|
| routing_key | 필수 (매칭 기반) | 무시됨 |
| Celery 호환 | ❌ `send_task()` exchange 무시 | ✅ kombu 직접 사용 |
| 구현 복잡도 | 높음 | 낮음 |
| 확장성 | routing_key 추가 필요 | Binding CR만 추가 |

---

## 2. Topology CR 일원화

### 2.1 책임 분리 원칙

```
┌─────────────────────────────────────────────────────────────────┐
│                    Topology CR (Source of Truth)                │
│              workloads/rabbitmq/base/topology/                  │
├─────────────────────────────────────────────────────────────────┤
│  exchanges.yaml  │  Exchange 정의 (타입, durability)            │
│  queues.yaml     │  Queue 정의 (TTL, DLX, arguments)            │
│  bindings.yaml   │  Exchange → Queue 바인딩                     │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    Python Celery 설정                           │
├─────────────────────────────────────────────────────────────────┤
│  task_routes     │  Task → Queue 매핑 (애플리케이션 레벨)       │
│                  │  ⚠️ CR로 위임 불가 (Python 코드 필수)        │
│  task_queues     │  no_declare=True로 큐 목록만 정의            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Celery 설정 변경

```python
# apps/character_worker/setup/celery.py
CHARACTER_TASK_QUEUES = [
    Queue("character.match", exchange="", routing_key="character.match", no_declare=True),
    Queue("character.save_ownership", exchange="", routing_key="character.save_ownership", no_declare=True),
    Queue("character.grant_default", exchange="", routing_key="character.grant_default", no_declare=True),
]

celery_app.conf.update(
    task_queues=CHARACTER_TASK_QUEUES,
    task_create_missing_queues=False,  # Topology CR에 위임
    task_default_exchange="",          # AMQP Default Exchange
)
```

**핵심 포인트:**
- `no_declare=True`: Celery가 큐를 선언하지 않음 (Topology CR이 생성)
- `exchange=""`: AMQP Default Exchange 명시
- `task_create_missing_queues=False`: 누락된 큐 자동 생성 방지

---

## 3. Worker Pool 선택과 캐시 공유

### 3.1 Pool별 특성

| Pool | 캐시 공유 | 사용 케이스 |
|------|-----------|-------------|
| `prefork` | ❌ (프로세스 격리) | CPU-bound |
| `threads` | ✅ (MainProcess 공유) | I/O-bound, 메모리 공유 필요 |
| `gevent` | ✅ (greenlet 공유) | 고동시성 I/O-bound |

### 3.2 character-match-worker 설정

```yaml
# workloads/domains/character-match-worker/base/deployment.yaml
args:
- -P
- threads  # 캐시 공유를 위해 threads pool 사용
- -Q
- character.match
- -c
- '16'     # 높은 concurrency (캐시 조회 위주)
```

### 3.3 캐시 초기화 시그널

```python
from celery.signals import worker_process_init, worker_ready

@worker_process_init.connect
def init_worker_process(**kwargs):
    # prefork/gevent pool용
    _init_character_cache()

@worker_ready.connect
def init_worker_ready(**kwargs):
    # threads pool용 (MainProcess에서 호출)
    _init_character_cache()
```

---

## 4. gevent + asyncio 충돌 해결

### 4.1 문제

```
RuntimeError: Task <Task pending> got Future attached to a different loop
```

`character-worker`는 `-P gevent` pool을 사용하는데, `reward_event_task.py`에서 `asyncio.new_event_loop()`을 사용하여 충돌 발생.

### 4.2 해결: 동기 DB 세션 사용

```python
# Before (asyncio) - gevent와 충돌
async def _save_ownership_batch_async(batch_data):
    async with async_session_factory() as session:
        result = await session.execute(sql, params)
        await session.commit()

# After (sync) - gevent 호환
def _save_ownership_batch_sync(batch_data):
    with sync_session_factory() as session:
        result = session.execute(sql, params)
        session.commit()
```

---

## 5. Image API Redis 안정성 개선

### 5.1 문제

프론트엔드에서 이미지 업로드 시 첫 요청이 실패하는 현상:

```
redis.exceptions.ConnectionError: Connection closed by server.
```

### 5.2 해결: 재시도 로직 추가

```python
# domains/image/core/config.py
class Settings(BaseSettings):
    # Redis connection settings
    redis_health_check_interval: int = Field(30, ge=5, le=300)
    redis_retry_attempts: int = Field(3, ge=1, le=10)
    redis_retry_base_delay: float = Field(0.1, ge=0.01, le=5.0)
    redis_socket_timeout: int = Field(5, ge=1, le=30)
    redis_socket_connect_timeout: int = Field(5, ge=1, le=30)
```

```python
# domains/image/core/redis.py
retry = Retry(
    backoff=ExponentialBackoff(base=settings.redis_retry_base_delay),
    retries=settings.redis_retry_attempts,
)

_redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    health_check_interval=settings.redis_health_check_interval,
    retry=retry,
    retry_on_timeout=True,
    retry_on_error=[redis.ConnectionError, redis.TimeoutError, ConnectionResetError],
    socket_keepalive=True,
    socket_connect_timeout=settings.redis_socket_connect_timeout,
    socket_timeout=settings.redis_socket_timeout,
)
```

**서비스 레벨 재시도:**

```python
# domains/image/services/image.py
async def _save_pending_upload(self, object_key: str, pending: PendingUpload) -> None:
    max_retries = self.settings.redis_retry_attempts
    base_delay = self.settings.redis_retry_base_delay

    for attempt in range(max_retries):
        try:
            await self._redis.setex(...)
            return
        except (RedisConnectionError, RedisTimeoutError, ConnectionResetError) as e:
            logger.warning("Redis setex failed, retrying", extra={...})
            if attempt < max_retries - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    raise last_error
```

---

## 6. E2E 테스트 결과

### 6.1 테스트 환경

- **API Endpoint**: `POST https://api.dev.growbin.app/api/v1/scan`
- **Image Upload**: `POST https://api.dev.growbin.app/api/v1/images/scan`
- **테스트 횟수**: 4회

### 6.2 결과

| # | Image Upload | Scan Pipeline | character.match | reward.character |
|---|--------------|---------------|-----------------|------------------|
| 1 | ✅ | ✅ | ✅ 일렉 매칭 | ✅ Fanout 브로드캐스트 |
| 2 | ✅ | ✅ | ❌ (일반폐기물) | ❌ |
| 3 | ✅ | ✅ | ❌ (일반폐기물) | ❌ |
| 4 | ✅ | ✅ | ❌ (일반폐기물) | ❌ |

### 6.3 검증 완료 항목

- [x] Image API Redis 재시도 로직 정상 동작
- [x] Scan API → scan_worker 파이프라인 (vision → rule → answer → reward)
- [x] character.match 동기 응답 (10초 타임아웃 내 완료)
- [x] reward.events Fanout → character.save_ownership + users.save_character
- [x] 각 Worker DB 저장 (character.character_ownerships, users.user_characters)

---

## 7. API 명세 (프론트엔드 연동용)

### 7.1 Image Upload

```http
POST /api/v1/images/scan
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "filename": "photo.png",
  "content_type": "image/png"
}
```

**Response:**
```json
{
  "key": "scan/abc123.png",
  "upload_url": "https://s3.ap-northeast-2.amazonaws.com/...",
  "cdn_url": "https://images.dev.growbin.app/scan/abc123.png",
  "expires_in": 900,
  "required_headers": {"Content-Type": "image/png"}
}
```

### 7.2 Scan Request

```http
POST /api/v1/scan
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "image_url": "https://images.dev.growbin.app/scan/abc123.png"
}
```

**Response:**
```json
{
  "job_id": "d44e4c6e-6b15-49a9-8529-f79a37ce9b14",
  "stream_url": "/api/v1/scan/d44e4c6e.../events",
  "result_url": "/api/v1/scan/d44e4c6e.../result",
  "status": "queued"
}
```

### 7.3 SSE Events

```http
GET /api/v1/scan/{job_id}/events
Authorization: Bearer <JWT>
Accept: text/event-stream
```

**Events:**
```
event: progress
data: {"step": "vision", "progress": 25, "message": "이미지 분석 중..."}

event: progress
data: {"step": "rule", "progress": 50, "message": "분류 규칙 검색 중..."}

event: progress
data: {"step": "answer", "progress": 75, "message": "답변 생성 중..."}

event: complete
data: {"step": "reward", "progress": 100, "result": {...}}
```

### 7.4 Final Result

```http
GET /api/v1/scan/{job_id}/result
Authorization: Bearer <JWT>
```

**Response:**
```json
{
  "classification": {
    "major_category": "전기전자제품",
    "middle_category": "소형가전",
    "minor_category": "무선이어폰 충전 케이스"
  },
  "disposal_steps": [...],
  "reward": {
    "character_id": "uuid",
    "character_name": "일렉",
    "character_code": "elec",
    "received": true
  }
}
```

---

## 8. 트러블슈팅 요약

| Phase | 문제 | 해결 |
|-------|------|------|
| 1 | `PreconditionFailed` x-message-ttl | `no_declare=True` |
| 1 | `ImproperlyConfigured` Queue 누락 | `task_queues` 정의 |
| 2 | Queue 바인딩이 `celery(direct)` | `exchange=""` 명시 |
| 2 | `Character cache not loaded` | `worker_ready` signal 추가 |
| 2 | `POSTGRES_HOST` 잘못된 서비스 이름 | 서비스 이름 수정 |
| 3 | Celery `exchange` 파라미터 무시 | kombu Producer 직접 사용 |
| 3 | `struct.error` 직렬화 오류 | `serializer="json"` 명시 |
| 4 | `character_code` 컬럼 없음 | Migration 수동 적용 |
| 4 | gevent + asyncio 충돌 | sync DB로 변경 |
| 5 | Redis `Connection closed by server` | 재시도 로직 + 설정 파라미터화 |

---

## 9. 관련 PR 목록

| PR | 제목 |
|----|------|
| #344-348 | Celery Queue 선언 충돌 해결 |
| #349-352 | Worker 설정 및 캐시 초기화 |
| #353-356 | Fanout Exchange 전환 |
| #357-358 | DB 마이그레이션 및 Worker 호환성 |
| #360 | Image API Redis 재시도 로직 |

---

## 10. 프론트엔드 연동 (FE)

> 작성일: 2026-01-09
> 관련 PR: #74-82

### 10.1 SSE 실시간 스캔 진행 상태

기존 동기 방식에서 SSE(Server-Sent Events) 기반 실시간 업데이트로 전환했습니다.

**기존 방식:**
```typescript
// ❌ 동기 방식 - 전체 처리 완료까지 대기
const { data } = await api.post('/api/v1/scan/classify', { image_url });
```

**SSE 방식:**
```typescript
// ✅ SSE 방식 - 단계별 실시간 업데이트
const { data } = await api.post('/api/v1/scan', { image_url });
// → { job_id, stream_url, result_url, status }

const eventSource = new EventSource(stream_url, { withCredentials: true });
eventSource.addEventListener('vision', (e) => setStep(1));
eventSource.addEventListener('rule', (e) => setStep(2));
eventSource.addEventListener('answer', (e) => setStep(3));
eventSource.addEventListener('done', (e) => fetchResult(job_id));
```

### 10.2 SSE 연결 구조

```
┌─────────────┐     POST /scan      ┌─────────────┐
│   Browser   │ ─────────────────▶  │   Scan API  │
└─────────────┘                     └─────────────┘
       │                                   │
       │  GET /scan/{job_id}/events        │ Redis Pub/Sub
       │  (EventSource)                    ▼
       │                            ┌─────────────┐
       └──────────────────────────▶ │ SSE Gateway │
                                    └─────────────┘
                                           │
                                    SSE Events:
                                    - vision (step 1)
                                    - rule (step 2)
                                    - answer (step 3)
                                    - done (complete)
```

### 10.3 useScanSSE Hook

SSE 연결 및 폴링 fallback을 처리하는 커스텀 훅을 구현했습니다.

```typescript
// src/hooks/useScanSSE.ts
export const useScanSSE = (options?: UseScanSSEOptions) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [result, setResult] = useState<ScanClassifyResponse | null>(null);

  const connect = useCallback((streamUrl: string, resultUrl: string) => {
    const eventSource = new EventSource(fullUrl, { withCredentials: true });

    // Named event 리스너 등록
    ['vision', 'rule', 'answer', 'reward', 'done'].forEach((stage) => {
      eventSource.addEventListener(stage, (event) => {
        const data = JSON.parse(event.data);
        console.log(`📨 SSE [${stage}] 이벤트:`, data);
        setCurrentStep(STAGE_TO_STEP[data.stage]);

        if (data.stage === 'done') {
          disconnect();
          fetchResult();
        }
      });
    });

    // SSE 실패 시 폴링으로 fallback
    eventSource.onerror = () => {
      console.warn('⚠️ SSE 연결 에러, 폴링으로 전환');
      disconnect();
      startPolling(jobId);
    };
  }, []);

  return { connect, disconnect, currentStep, isComplete, result };
};
```

### 10.4 SSE CORS 이슈 해결

**문제:**
```
Access to EventSource at 'https://api.dev.growbin.app/...' from origin 
'https://frontend.dev.growbin.app' has been blocked by CORS policy
```

**원인:**
- `allow_origins=["*"]`와 `allow_credentials=True` 조합 불가 (브라우저 보안 정책)

**해결:**
```python
# domains/sse-gateway/main.py
ALLOWED_ORIGINS = [
    "https://frontend1.dev.growbin.app",
    "https://frontend2.dev.growbin.app",
    "https://frontend.dev.growbin.app",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # 명시적 origin 목록
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)
```

### 10.5 캐릭터 소유권 Eventual Consistency 처리

백엔드에서 캐릭터 소유권이 비동기로 저장되므로, 프론트엔드에서 낙관적 업데이트(Optimistic Update)를 구현했습니다.

**문제:**
1. 스캔 완료 → `reward.events` Fanout → DB 저장 (비동기)
2. 프론트엔드가 캐릭터 목록 조회 시 아직 저장 안 됨
3. 축하 효과 후 컬렉션에서 캐릭터 미표시

**해결: localStorage 기반 Optimistic Update**

```typescript
// src/util/CharacterCache.ts
const OWNED_CHARACTERS_KEY = 'owned_characters';

export const getOwnedCharacters = (): string[] => {
  return JSON.parse(localStorage.getItem(OWNED_CHARACTERS_KEY) || '[]');
};

export const setOwnedCharacters = (names: string[]) => {
  localStorage.setItem(OWNED_CHARACTERS_KEY, JSON.stringify(names));
};

export const addOwnedCharacter = (name: string) => {
  const list = getOwnedCharacters();
  if (!list.includes(name)) {
    list.push(name);
    setOwnedCharacters(list);
  }
};

export const isNewCharacter = (name: string): boolean => {
  return !getOwnedCharacters().includes(name);
};
```

**스캔 결과 페이지:**
```typescript
// src/pages/Camera/Answer.tsx
useEffect(() => {
  if (reward?.name && isNewCharacter(reward.name)) {
    setShowCelebration(true);
    addOwnedCharacter(reward.name);  // Optimistic Update
  }
}, [reward?.name]);
```

**캐릭터 컬렉션:**
```typescript
// src/pages/Home/CharacterCollection.tsx
useEffect(() => {
  const getAcquiredCharacter = async () => {
    const { data } = await api.get('/api/v1/users/me/characters');
    const names = data.map((item) => item.name);
    setAcquiredList(names);
    setOwnedCharacters(names);  // 서버와 동기화
  };
  getAcquiredCharacter();
}, []);
```

### 10.6 네비게이션 버그 수정

**문제:**
- 스캔 완료 페이지 X 버튼 클릭 시 로그인 페이지로 이동

**원인:**
```typescript
// ❌ HashRouter에서 잘못된 경로
onClick={() => window.location.replace('/home')}
// → 서버에 /home 요청 → 404 또는 초기화 → 로그인 페이지
```

**해결:**
```typescript
// ✅ React Router 사용
onClick={() => navigate('/home', { replace: true })}
```

### 10.7 FE 관련 PR 목록

| PR | 제목 | 상태 |
|----|------|------|
| #74 | feat: 캐릭터 소유권 localStorage 캐시 구현 | ✅ Merged |
| #75-78 | feat: SSE 이벤트 리스닝 및 폴링 fallback | ✅ Merged |
| #79-80 | feat: SSE 이벤트 수신 상세 로그 추가 | ✅ Merged |
| #81-82 | fix: 스캔 완료 페이지 X 버튼 네비게이션 수정 | ✅ Merged |

---

## 11. 다음 단계

- [ ] Character API Clean Architecture 마이그레이션
- [ ] Chat API Clean Architecture 마이그레이션
- [x] ~~프론트엔드 캐릭터 획득 UI 연동~~ ✅ 완료
- [ ] 프로덕션 배포 준비

---

## 참고 자료

- [RabbitMQ Exchange Types](https://www.rabbitmq.com/tutorials/amqp-concepts.html#exchanges)
- [Celery Task Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)
- [kombu Producer API](https://docs.celeryq.dev/projects/kombu/en/stable/reference/kombu.html#producer)
- [51-rabbitmq-queue-strategy-report.md](../async/51-rabbitmq-queue-strategy-report.md)
- [52-fanout-exchange-migration-troubleshooting.md](../async/52-fanout-exchange-migration-troubleshooting.md)

