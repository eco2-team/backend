# 이코에코(Eco²) Agent #5: Checkpointer & State 관리

> Scan의 Stateless Reducer vs Chat의 Cache-Aside Checkpointer

[Agent #4](https://rooftopsnow.tistory.com/168)에서 Event Relay 계층을 다뤘습니다. 이번 포스팅에서는 **멀티턴 대화 컨텍스트**를 유지하는 Checkpointer 구현을 다룹니다.

**업데이트**: Cache-Aside 패턴 적용으로 Hot session은 Redis에서 ~1ms 응답.

---

## Scan vs Chat: 상태 관리의 차이

### Scan: Stateless Reducer Pattern

[Clean Architecture #14](https://rooftopsnow.tistory.com/144)에서 Scan은 **Stateless Reducer Pattern**으로 체크포인팅을 직접 구현했습니다.

```
┌─────────────────────────────────────────────────────────────┐
│              Scan 파이프라인 (단일 요청)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이미지 → Vision → Rule → Answer → Reward → 완료            │
│             │        │       │        │                     │
│             ▼        ▼       ▼        ▼                     │
│          Redis    Redis   Redis    Redis                    │
│          SETEX    SETEX   SETEX    SETEX                    │
│          (TTL)    (TTL)   (TTL)    (TTL)                    │
│                                                             │
│  복구: 실패한 Step에서 재시작 (LLM 재호출 방지)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

```python
# Scan: CheckpointingStepRunner (직접 구현)
class CheckpointingStepRunner:
    def run_with_checkpoint(self, step: Step, ctx: ClassifyContext):
        # 체크포인트 확인
        saved = redis.get(f"scan:checkpoint:{ctx.task_id}:{step.name}")
        if saved:
            return ClassifyContext.from_dict(saved)
        
        # Step 실행
        result = step.run(ctx)
        
        # 체크포인트 저장
        redis.setex(
            f"scan:checkpoint:{ctx.task_id}:{step.name}",
            3600,  # TTL 1시간
            result.to_dict(),
        )
        return result
```

### Chat: Cache-Aside Checkpointer

Chat은 **멀티턴 대화**가 필요합니다. Cursor처럼 수개월 전 대화도 기억해야 합니다.

**Cache-Aside 패턴**을 적용하여 Hot/Cold session을 효율적으로 처리합니다:

```
┌─────────────────────────────────────────────────────────────┐
│              Cache-Aside Checkpointer                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  조회 (get)                                                  │
│  ─────────                                                  │
│  Client → Redis (L1, ~1ms)                                  │
│              │                                              │
│              ├── Hit → Return (빠름)                        │
│              │                                              │
│              └── Miss → PostgreSQL (L2, ~5-10ms)            │
│                              │                              │
│                              └── Redis에 캐싱 (warm-up)     │
│                                                             │
│  저장 (put)                                                  │
│  ─────────                                                  │
│  Client → PostgreSQL (영구) + Redis (캐시)                   │
│           Write-Through                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

| 시나리오 | 응답 시간 | 설명 |
|----------|----------|------|
| **Hot session** | ~1ms | Redis 캐시 히트 |
| **Cold session** | ~5-10ms | PostgreSQL 조회 → 캐싱 |
| **장기 보존** | 영구 | PostgreSQL에 저장 |

---

## 구현: Cache-Aside Checkpointer

### 1. CachedPostgresSaver 클래스

```python
# apps/chat_worker/infrastructure/langgraph/checkpointer.py

class CachedPostgresSaver:
    """Cache-Aside 패턴 Checkpointer.
    
    L1: Redis (빠름, TTL 24시간)
    L2: PostgreSQL (영구)
    """
    
    def __init__(
        self,
        postgres_saver: AsyncPostgresSaver,
        redis: Redis,
        cache_ttl: int = 86400,  # 24시간
    ):
        self._postgres = postgres_saver
        self._redis = redis
        self._ttl = cache_ttl
    
    async def aget_tuple(self, config: dict) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        cache_key = f"chat:checkpoint:cache:{thread_id}"
        
        # L1: Redis 캐시 조회
        cached = await self._redis.get(cache_key)
        if cached:
            logger.debug("checkpoint_cache_hit", extra={"thread_id": thread_id})
        
        # L2: PostgreSQL 조회
        result = await self._postgres.aget_tuple(config)
        
        if result:
            # Warm-up: Redis에 캐싱
            await self._redis.setex(cache_key, self._ttl, json.dumps({...}))
        
        return result
    
    async def aput(self, config, checkpoint, metadata, new_versions=None):
        # Write-Through: PostgreSQL + Redis 둘 다 저장
        result = await self._postgres.aput(config, checkpoint, metadata, new_versions)
        await self._redis.setex(cache_key, self._ttl, json.dumps({...}))
        return result
```

### 2. 팩토리 함수

```python
async def create_cached_postgres_checkpointer(
    conn_string: str,
    redis: Redis,
    cache_ttl: int = 86400,
) -> CachedPostgresSaver:
    """Cache-Aside PostgreSQL 체크포인터 생성.
    
    L1: Redis (빠름, TTL)
    L2: PostgreSQL (영구)
    """
    postgres_saver = await AsyncPostgresSaver.from_conn_string(conn_string)
    return CachedPostgresSaver(
        postgres_saver=postgres_saver,
        redis=redis,
        cache_ttl=cache_ttl,
    )
```

### 2. Factory 수정

```python
# apps/chat_worker/infrastructure/langgraph/factory.py

def create_chat_graph(
    llm: LLMPort,
    retriever: RetrieverPort,
    event_publisher: EventPublisherPort,
    character_client: CharacterClientPort | None = None,
    location_client: LocationClientPort | None = None,
    checkpointer: BaseCheckpointSaver | None = None,  # 🆕
) -> CompiledGraph:
    """Chat 파이프라인 그래프 생성."""
    
    graph = StateGraph(dict)
    # ... 노드 추가 ...
    
    # 체크포인터 연결
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
```

### 3. Command 수정: thread_id 연결

```python
# apps/chat_worker/application/chat/commands/process_chat.py

class ProcessChatCommand:
    async def execute(self, request: ProcessChatRequest):
        initial_state = {
            "job_id": request.job_id,
            "session_id": request.session_id,
            "message": request.message,
            # ...
        }
        
        # 🆕 세션 ID → thread_id로 멀티턴 대화 연결
        config = {
            "configurable": {
                "thread_id": request.session_id,
            }
        }
        
        # 이전 대화 컨텍스트 자동 로드
        result = await self._pipeline.ainvoke(initial_state, config=config)
```

### 4. Dependencies 수정

```python
# apps/chat_worker/setup/dependencies.py

async def get_checkpointer():
    """LangGraph 체크포인터 싱글톤.
    
    Cache-Aside 패턴:
    - L1: Redis (빠름, TTL 24시간) - Hot session
    - L2: PostgreSQL (영구) - Cold session, 장기 보존
    """
    global _checkpointer
    if _checkpointer is None:
        settings = get_settings()
        
        if settings.postgres_url:
            # Cache-Aside: Redis L1 + PostgreSQL L2
            try:
                redis = await get_redis()
                _checkpointer = await create_cached_postgres_checkpointer(
                    conn_string=settings.postgres_url,
                    redis=redis,
                    cache_ttl=86400,  # 24시간
                )
                logger.info("CachedPostgresSaver initialized")
            except Exception:
                # Redis 폴백
                _checkpointer = await create_redis_checkpointer(
                    settings.redis_url,
                    ttl=86400,
                )
        else:
            # Redis (단기 세션)
            _checkpointer = await create_redis_checkpointer(
                settings.redis_url,
                ttl=86400,
            )
    
    return _checkpointer
```

### 5. Config 수정

```python
# apps/chat_worker/setup/config.py

class Settings(BaseSettings):
    # Redis (이벤트 스트림, 단기 캐시)
    redis_url: str = "redis://localhost:6379/0"
    
    # 🆕 PostgreSQL (체크포인팅, 멀티턴 대화)
    # None이면 Redis 폴백 (TTL 24시간)
    postgres_url: str | None = None
```

---

## PostgreSQL 스키마

LangGraph가 자동 생성하는 테이블:

```sql
CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE INDEX idx_checkpoints_thread ON checkpoints(thread_id);
CREATE INDEX idx_checkpoints_created ON checkpoints(created_at);
```

---

## 저장소 역할 분리

```
┌─────────────────────────────────────────────────────────────┐
│              Chat 저장소 아키텍처 (Cache-Aside)              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [L1 캐시 - Redis]                                          │
│  ├── 체크포인트 캐시 (Cache-Aside)  TTL: 24시간 🆕          │
│  │   └── chat:checkpoint:cache:{thread_id}                  │
│  ├── SSE 이벤트 (Streams)          TTL: 2시간               │
│  │   └── chat:events:{job_id}                               │
│  ├── 진행 상태 (State KV)           TTL: 1시간              │
│  │   └── chat:state:{job_id}                                │
│  └── 멱등성 마커                     TTL: 2시간             │
│      └── router:published:{job_id}:{seq}                    │
│                                                             │
│  [L2 영구 저장 - PostgreSQL]                                │
│  ├── 대화 히스토리 (checkpoints)  영구 저장                 │
│  │   └── thread_id = session_id                             │
│  ├── 사용자 세션 메타데이터        영구 저장                  │
│  └── 토큰 사용량 통계             영구 저장                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Hot vs Cold Session

| 세션 유형 | 저장소 | 응답 시간 | TTL |
|----------|--------|----------|-----|
| **Hot** (최근 대화) | Redis | ~1ms | 24시간 |
| **Cold** (오래된 대화) | PostgreSQL → Redis | ~5-10ms | 영구 |

---

## Scan vs Chat 전체 비교

| 항목 | Scan | Chat |
|------|------|------|
| **패턴** | Stateless Reducer (직접 구현) | **Cache-Aside Checkpointer** |
| **L1 캐시** | Redis (TTL 1시간) | Redis (TTL 24시간) |
| **L2 저장소** | - | **PostgreSQL (영구)** |
| **복구 단위** | Step 단위 | 노드 단위 |
| **세션 유지** | 단일 요청 | **멀티턴 대화** |
| **Hot session** | N/A | Redis ~1ms |
| **Cold session** | N/A | PostgreSQL ~5-10ms → 캐싱 |
| **비용 절감** | LLM 재호출 방지 | LLM 재호출 방지 + 히스토리 검색 |

---

## 멀티턴 대화 플로우

```
┌─────────────────────────────────────────────────────────────┐
│              멀티턴 대화 플로우                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Turn 1: "페트병 어떻게 버려?"                               │
│  ─────────────────────────────                              │
│      │                                                      │
│      │ thread_id = "session-123"                            │
│      ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ LangGraph       │  checkpoints 테이블:                   │
│  │ ainvoke()       │  thread_id | checkpoint                │
│  │                 │  session-123 | {state: {...}}          │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  "페트병은 투명 페트병 전용 수거함에..."                     │
│                                                             │
│                                                             │
│  Turn 2: "라벨은요?"                                         │
│  ─────────────────────────────                              │
│      │                                                      │
│      │ thread_id = "session-123" (동일)                     │
│      ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ LangGraph       │  이전 체크포인트 자동 로드:             │
│  │ ainvoke()       │  - 이전 질문: "페트병 어떻게 버려?"     │
│  │                 │  - 이전 답변: "페트병은..."             │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  "라벨은 떼어서 일반 쓰레기로..."                            │
│  (이전 컨텍스트 활용)                                        │
│                                                             │
│                                                             │
│  수개월 후...                                                │
│  ─────────────────────────────                              │
│      │                                                      │
│      │ thread_id = "session-123" (동일)                     │
│      ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ PostgreSQL      │  영구 저장된 히스토리 로드              │
│  │ checkpoints     │                                        │
│  └─────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## K8s ConfigMap 예시

```yaml
# workloads/domains/chat_worker/base/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: chat-worker-config
  namespace: chat
data:
  CHAT_WORKER_ENVIRONMENT: "production"
  CHAT_WORKER_REDIS_URL: "redis://dev-redis.redis.svc.cluster.local:6379/0"
  CHAT_WORKER_POSTGRES_URL: "postgresql://chat:password@dev-postgresql.postgres.svc.cluster.local:5432/eco2"
  CHAT_WORKER_DEFAULT_PROVIDER: "openai"
  CHAT_WORKER_LOG_LEVEL: "INFO"
```

---

## 결론

Chat 서비스는 **Cache-Aside 패턴**으로 멀티턴 대화를 구현합니다:

1. **Cache-Aside 패턴**: Hot session은 Redis에서 ~1ms 응답
2. **PostgreSQL 영구 저장**: Cursor처럼 장기 세션 유지
3. **자동 Warm-up**: Cold session 조회 시 Redis에 캐싱
4. **thread_id 연결**: session_id로 대화 컨텍스트 연결

Scan의 Stateless Reducer와 달리, Chat은 **멀티턴 대화**와 **장기 세션**이 핵심입니다:

| 특징 | 이점 |
|------|------|
| Redis L1 캐시 | Hot session ~1ms 응답 |
| PostgreSQL L2 | 영구 저장, 장기 보존 |
| Write-Through | 일관성 보장 |
| LangGraph 호환 | 에코시스템 통합 |

---

## 함께 보기

- [Agent #4: Event Relay & SSE](14-chat-event-relay-sse.md) - event_router 확장, SSE Gateway 구현

