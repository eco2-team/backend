# Worker 로컬 캐시와 RabbitMQ Fanout 기반 동기화

> 이전 글: [Celery Chain 고도화](./09-celery-chain-events-part2.md)
>
> 관련 트러블슈팅: [Celery + RabbitMQ 트러블슈팅 가이드](./14-celery-rabbitmq-troubleshooting.md)

---

## 개요

본 문서는 **Worker 로컬 캐시를 활용한 DB 조회 없는 매칭**과 **RabbitMQ Fanout Exchange 기반 캐시 동기화** 구현을 다룬다.

---

## 1. 설계 배경

### 1.1 기존 문제

캐릭터 매칭에서 매 요청마다 PostgreSQL 조회:

```python
async def evaluate_reward(self, classification):
    characters = await self.repository.get_all()  # ~50ms
    for char in characters:
        if char.match_label == classification.middle_category:
            return char
```

**문제점**:
- 매 요청 DB 조회 (~50ms 추가)
- DB 장애 시 매칭 불가
- Worker 스케일링 = DB 부하 스케일링

### 1.2 캐싱 대상 선정: Character Catalog

**캐싱 대상 조건:**
- 읽기 빈도 >> 쓰기 빈도
- 데이터 크기가 작음 (메모리에 적재 가능)
- 모든 Worker가 동일한 데이터 필요
- 실시간성보다 일관성이 중요

**Character Catalog 특성:**

| 항목 | 값 |
|------|-----|
| 레코드 수 | 13개 (최대 ~100개) |
| 레코드 크기 | ~500 bytes |
| 총 메모리 | ~50KB |
| 읽기 빈도 | 매 스캔 요청 (수백 회/일) |
| 쓰기 빈도 | 캐릭터 추가 시 (수 회/월) |

캐릭터 카탈로그는 운영자가 수동으로 추가하는 마스터 데이터. 사용자 행동으로 변경되지 않음.

### 1.3 설계 원칙

캐릭터 데이터는 **거의 변경되지 않음**. 각 Worker 메모리에 캐싱하여 사용.

```
Before:  Worker → PostgreSQL (~50ms)
After:   Worker → Local Memory (~0.01ms)
```

### 1.4 성능 비교

| 방식 | 레이턴시 | 실패 모드 |
|------|----------|-----------|
| DB 조회 | ~50ms | DB 장애 시 전체 실패 |
| Redis 캐시 | ~2ms | Redis 장애 시 실패 |
| **로컬 캐시** | ~0.01ms | 캐시 미스 시 매칭 불가 |

---

## 2. 캐시 동기화 아키텍처

### 2.1 문제: 다중 Worker 동기화

Worker Pod가 여러 개 실행될 때 캐릭터 추가/수정/삭제 시 **모든 Worker의 캐시를 동시에 갱신**해야 함.

### 2.2 RabbitMQ Fanout 선택

| 방법 | 장점 | 단점 |
|------|------|------|
| Redis Pub/Sub | 단순, 빠름 | Redis 의존, 메시지 유실 |
| Kafka | 영속성, 재생 가능 | 오버스펙, 운영 복잡 |
| **RabbitMQ Fanout** | 기존 인프라 활용 | 메시지 유실 가능 |
| DB Polling | 단순 | 지연, DB 부하 |

**선택 근거**:
- Celery가 이미 RabbitMQ 사용 중 → 추가 인프라 불필요
- Fanout Exchange는 브로드캐스트에 최적화
- 메시지 유실은 배포 시 전체 갱신으로 보완

---

## 3. Fanout Exchange 구성

### 3.1 Exchange 정의

```yaml
# workloads/rabbitmq/base/topology/exchanges.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Exchange
metadata:
  name: character-cache
  namespace: rabbitmq
spec:
  name: character.cache
  type: fanout       # 모든 바인딩된 큐에 브로드캐스트
  durable: true
  autoDelete: false
  vhost: eco2
```

### 3.2 이벤트 타입

| Type | Payload | 용도 |
|------|---------|------|
| `full_refresh` | `{"type": "full_refresh", "characters": [...]}` | 전체 캐시 교체 |
| `upsert` | `{"type": "upsert", "character": {...}}` | 단일 캐릭터 추가/수정 |
| `delete` | `{"type": "delete", "character_id": "..."}` | 단일 캐릭터 삭제 |

---

## 4. Consumer 구현

### 4.1 익명 큐 (Exclusive)

각 Worker가 고유한 임시 큐를 생성하여 모두 Fanout Exchange에 바인딩:

```python
self.queue = Queue(
    name="",               # RabbitMQ가 자동 생성 (amq.gen-xxxx)
    exchange=CACHE_EXCHANGE,
    exclusive=True,        # 이 연결만 사용
    auto_delete=True,      # 연결 종료 시 삭제
)
```

### 4.2 이벤트 핸들러

```python
class CacheUpdateConsumer(ConsumerMixin):
    def on_message(self, body: dict, message: Message):
        event_type = body.get("type")
        
        if event_type == "full_refresh":
            self.cache.set_all(body.get("characters", []))
        elif event_type == "upsert":
            self.cache.upsert(body.get("character"))
        elif event_type == "delete":
            self.cache.delete(body.get("character_id"))
        
        message.ack()
```

### 4.3 백그라운드 Thread

Worker 프로세스 내 별도 스레드로 Consumer 실행:

```python
class CacheConsumerThread(threading.Thread):
    def __init__(self, broker_url: str, cache: CharacterLocalCache):
        super().__init__(daemon=True, name="CacheConsumerThread")
        self.broker_url = broker_url
        self.cache = cache
        self._stop_event = threading.Event()
    
    def run(self):
        while not self._stop_event.is_set():
            try:
                with Connection(self.broker_url, heartbeat=60) as conn:
                    consumer = CacheUpdateConsumer(conn, self.cache)
                    consumer.run()
            except (socket.timeout, TimeoutError):
                if not self._stop_event.is_set():
                    time.sleep(1)  # 재연결 대기
```

---

## 5. Catalog 업데이트 시 동기화

### 5.1 업데이트 시나리오

| 시나리오 | 트리거 | 동기화 방법 |
|----------|--------|-------------|
| 캐릭터 추가 | CSV import Job | `full_refresh` 이벤트 발행 |
| 캐릭터 수정 | Admin API (미구현) | `upsert` 이벤트 발행 |
| 캐릭터 삭제 | Admin API (미구현) | `delete` 이벤트 발행 |
| Worker 배포 | ArgoCD Sync | PostSync Hook → `full_refresh` |

### 5.2 CSV Import 흐름

```
운영자: CSV 업로드
          │
          ▼
┌─────────────────────────────┐
│  import_character_catalog   │  (Kubernetes Job)
│  - CSV 파싱                  │
│  - DB INSERT/UPDATE         │
│  - publish_full_refresh()   │
└─────────────────────────────┘
          │
          ▼
    character.cache (Fanout Exchange)
          │
          ├─── Worker-1: cache.set_all()
          ├─── Worker-2: cache.set_all()
          └─── Worker-N: cache.set_all()
```

### 5.3 Publisher 구현

```python
class CharacterCachePublisher:
    def publish_full_refresh(self, characters: list[dict]) -> None:
        self._publish({
            "type": "full_refresh",
            "characters": characters,
        })
    
    def publish_upsert(self, character: dict) -> None:
        self._publish({
            "type": "upsert",
            "character": character,
        })
    
    def publish_delete(self, character_id: str) -> None:
        self._publish({
            "type": "delete",
            "character_id": character_id,
        })
```

### 5.4 Import Job 예시

```python
# domains/character/jobs/import_character_catalog.py
async def import_and_publish(csv_path: str) -> None:
    # 1. DB에 저장
    characters = await parse_and_save(csv_path)
    
    # 2. 캐시 동기화 이벤트 발행
    publisher = get_cache_publisher(broker_url)
    publisher.publish_full_refresh([
        {
            "id": str(c.id),
            "code": c.code,
            "name": c.name,
            "match_label": c.match_label,
            "type_label": c.metadata.get("type"),
            "dialog": c.metadata.get("dialog"),
        }
        for c in characters
    ])
```

---

## 6. 캐시 워밍업 (배포 시)

### 6.1 ArgoCD PostSync Hook

배포 완료 후 Job이 실행되어 캐시 초기화:

```yaml
# workloads/domains/character-match-worker/base/cache-warmup-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: cache-warmup
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
```

### 6.2 워밍업 흐름

```
ArgoCD Sync → Deployment 업데이트 → Pods 준비 완료
                                         ↓
                                  PostSync Hook 실행
                                         ↓
                                  cache-warmup Job
                                         ↓
                             SELECT * FROM characters
                                         ↓
                          publish full_refresh to character.cache
                                         ↓
                          모든 Worker 캐시 동기화 완료
```

---

## 7. Celery Pool과 캐시 공유

### 7.1 prefork vs threads

Celery는 여러 pool 타입을 지원하며, 캐시 공유 여부가 달라진다.

**prefork (기본값)**:
```
MainProcess (Cache Consumer)
     │
     └─ fork()
          └─ ForkPoolWorker-1 (별도 프로세스) → 캐시 격리
          └─ ForkPoolWorker-2 (별도 프로세스) → 캐시 격리
```

**threads**:
```
MainProcess
     ├─ CacheConsumerThread → CharacterLocalCache
     ├─ ThreadPoolExecutor-0 ─┘ (공유)
     ├─ ThreadPoolExecutor-1 ─┘ (공유)
     └─ ThreadPoolExecutor-2 ─┘ (공유)
```

### 7.2 character-match-worker 설정

캐시 조회가 주 작업이므로 `threads` pool 사용:

```yaml
# deployment.yaml
args:
- -P
- threads
- -c
- '4'
```

| Pool | 프로세스 모델 | 캐시 공유 | 용도 |
|------|--------------|-----------|------|
| `prefork` | 다중 프로세스 | ❌ | CPU-bound |
| `threads` | 다중 스레드 | ✅ | I/O-bound, 캐시 필요 |
| `gevent` | Greenlet | ✅ | 고동시성 I/O |

---

## 8. Thread-Safe 캐시 구현

### 8.1 싱글톤 + Lock

```python
class CharacterLocalCache:
    _instance: CharacterLocalCache | None = None
    _lock = Lock()  # 싱글톤 생성용
    
    def __new__(cls) -> CharacterLocalCache:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-Checked Locking
                    instance = super().__new__(cls)
                    instance._characters = {}
                    instance._data_lock = Lock()  # 데이터 접근용
                    cls._instance = instance
        return cls._instance
    
    def set_all(self, characters: list[dict]):
        with self._data_lock:
            self._characters.clear()
            for char in characters:
                cached = CachedCharacter.from_dict(char)
                self._characters[cached.id] = cached
    
    def get_all(self) -> list[CachedCharacter]:
        with self._data_lock:
            return list(self._characters.values())
```

---

## 9. 캐시 미스 정책

### 9.1 DB Fallback 없음

```python
if not characters:
    logger.warning("Character cache empty")
    return None  # 매칭 실패 → reward null
```

**근거**:
- 응답 경로에 DB를 넣지 않는 원칙 유지
- 캐시 미스는 배포 직후 수 초 동안만 발생
- PostSync Hook이 해결

### 9.2 Eventual Consistency 허용 구간

```
배포 시점:
0s    ArgoCD Sync 시작
5s    새 Pods 준비 완료
5s    PostSync Hook 시작     ← 이 구간에서
7s    cache-warmup Job 완료     캐시 미스 가능 (~2초)
7s    full_refresh 이벤트 발행
7.1s  모든 Worker 캐시 동기화
```

---

## 10. 관련 코드

| 파일 | 역할 |
|------|------|
| `domains/_shared/cache/cache_consumer.py` | Fanout Consumer 구현 |
| `domains/_shared/cache/cache_publisher.py` | 이벤트 발행 |
| `domains/_shared/cache/character_cache.py` | Thread-safe 캐시 |
| `domains/character/jobs/warmup_cache.py` | 배포 시 캐시 워밍업 |
| `domains/character/jobs/import_character_catalog.py` | CSV 업로드 시 캐시 동기화 |
| `workloads/domains/character-match-worker/base/cache-warmup-job.yaml` | PostSync Hook |
| `workloads/domains/character-match-worker/base/deployment.yaml` | threads pool 설정 |

---

## 11. Trade-off

| 항목 | 장점 | 단점 |
|------|------|------|
| 인메모리 캐시 | ~0.01ms 성능 | 메모리 사용 (미미) |
| Fanout 브로드캐스트 | 즉시 동기화 | 네트워크 트래픽 |
| threads pool | 캐시 공유 | GIL 제약 (I/O-bound에서는 무관) |
| PostSync Hook | 자동 워밍업 | 배포 시간 +2초 |
| No DB Fallback | 성능 일관성 | 캐시 미스 시 매칭 불가 |

---

## References

- [RabbitMQ Fanout Exchange](https://www.rabbitmq.com/tutorials/tutorial-three-python.html)
- [kombu ConsumerMixin](https://kombu.readthedocs.io/en/stable/reference/kombu.mixins.html)
- [ArgoCD Resource Hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)
- [Thread-safe Singleton Pattern](https://refactoring.guru/design-patterns/singleton)
