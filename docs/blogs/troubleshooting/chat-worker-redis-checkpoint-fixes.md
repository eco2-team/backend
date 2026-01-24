# Chat Worker Redis & Checkpoint 직렬화 트러블슈팅

> 작성일: 2026-01-24
> PR: #517 ~ #523
> 상태: In Progress (PR #522, #523 배포 대기)

---

## 1. 개요

Chat Worker 배포 후 발생한 일련의 에러를 추적·수정한 기록.
Redis 연결 → 이벤트 발행 실패 → Checkpoint 직렬화 깨짐까지 연쇄적으로 발견.

### 타임라인

| 단계 | 에러 | 근본 원인 | PR |
|------|------|-----------|-----|
| 1 | Redis 연결 실패 | Pod DNS 사용 | #517 |
| 2 | Redis 인스턴스 혼선 | pubsub-redis 참조 | #518 |
| 3 | `stage_event_publish_failed` | `min_connections` 잘못된 kwarg | #519 |
| 4 | `'str' has no attribute 'type'` | `json.dumps(default=str)` 직렬화 | #520 |
| 5 | `'JsonPlusSerializer' has no attribute 'dumps'` | serde API 오용 | #521 |
| 6 | 2번째 메시지 여전히 `AttributeError` | legacy checkpoint str 잔존 | #522 |
| 7 | `UnicodeDecodeError` (미배포 시 발생 예정) | msgpack 바이너리 UTF-8 디코딩 | #523 |

---

## 2. Redis 연결 기반 수정 (PR #517, #518)

### 2.1 에러

```
ConnectionError: Error connecting to redis://rfr-cache-redis-0.rfr-cache-redis.redis.svc.cluster.local:6379/2
```

### 2.2 원인

- Pod DNS(`rfr-cache-redis-0.rfr-...`) 사용 → Sentinel failover 시 연결 불가
- chat-worker가 pubsub-redis를 참조 → 올바른 cache-redis 인스턴스가 아님

### 2.3 수정

```yaml
# PR #517: Service DNS 사용
CHAT_WORKER_REDIS_URL: redis://rfr-cache-redis.redis.svc.cluster.local:6379/2

# PR #518: streams-redis 분리
CHAT_WORKER_REDIS_STREAMS_URL: redis://rfr-streams-redis.redis.svc.cluster.local:6379/0
```

---

## 3. Redis Pool `min_connections` TypeError (PR #519)

### 3.1 에러 로그

```
stage_event_publish_failed
token_v2_publish_failed
```

에러 상세가 `extra` dict에 숨겨져 있어 로그 포맷에서 보이지 않았음.
실제 원인: `TypeError: Connection.__init__() got an unexpected keyword argument 'min_connections'`

### 3.2 근본 원인

`redis.asyncio.Redis`의 `ConnectionPool`은 알 수 없는 kwargs를 `Connection.__init__()`에 전달.
`min_connections`는 **redis-py 파라미터가 아님** — legacy aioredis v1.x의 `minsize`/`maxsize`에서 온 것.

```python
# redis-py 공식 파라미터
max_connections      # pool 최대 크기
socket_timeout       # 소켓 읽기/쓰기 타임아웃
socket_connect_timeout
health_check_interval
retry_on_timeout

# 존재하지 않는 파라미터 (aioredis v1.x 전용)
min_connections  # ← 이것
minsize / maxsize
```

### 3.3 수정

```python
# dependencies.py - get_redis_streams()
_redis_streams = Redis.from_url(
    streams_url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=20,
    health_check_interval=30,
    socket_timeout=5.0,        # 60→5 (Worker는 XADD만, blocking read 아님)
    socket_connect_timeout=5.0,
    retry_on_timeout=True,
)
```

추가: 에러 핸들러에서 exception 정보를 로그 메시지 본문으로 이동 (기존 `extra` dict → 포맷에 미노출).

```python
# Before (로그에서 안 보임)
logger.error("stage_event_publish_failed", extra={"error": str(e)})

# After (로그에서 보임)
logger.error("stage_event_publish_failed: %s: %s", type(e).__name__, e, extra={...})
```

---

## 4. Checkpoint 직렬화 — `json.dumps(default=str)` (PR #520)

### 4.1 에러 로그

```
Traceback (most recent call last):
  File ".../nodes/intent_node.py", line 102, in intent_node
    role = "user" if msg.type == "human" else "assistant"
                      ^^^^^^^^
AttributeError: 'str' object has no attribute 'type'
```

두 번째 메시지(멀티턴) 시점에서 발생. 첫 번째 메시지는 정상.

### 4.2 근본 원인

`PlainAsyncRedisSaver._serialize()`가 `json.dumps(obj, default=str)` 사용:

```python
# 저장 시
json.dumps(checkpoint, default=str)
# HumanMessage(content="hello") → '"human: hello"' (str() 호출 결과)

# 복원 시
json.loads(data)
# → "human: hello" (plain string, HumanMessage 아님)
```

`default=str`은 직렬화 불가 객체에 `str()`을 호출 → LangChain Message 타입 정보 소실.

### 4.3 수정 방향

`BaseCheckpointSaver.serde` (JsonPlusSerializer) 사용으로 전환.

---

## 5. serde API 오용 — `dumps`/`loads` (PR #521)

### 5.1 에러 로그

```
Traceback (most recent call last):
  File ".../sync/plain_redis_saver.py", line 311, in _serialize
    return self.serde.dumps(obj)
           ^^^^^^^^^^^^^^
AttributeError: 'JsonPlusSerializer' object has no attribute 'dumps'
```

### 5.2 원인

`JsonPlusSerializer`는 `dumps`/`loads`가 아닌 `dumps_typed`/`loads_typed` 인터페이스:

```python
# SerializerProtocol
dumps_typed(obj: Any) -> tuple[str, bytes]    # (type_tag, serialized_bytes)
loads_typed(data: tuple[str, bytes]) -> Any   # (type_tag, bytes) → object
```

### 5.3 수정 (PR #521에서 적용, 그러나 불완전)

```python
def _serialize(self, obj):
    _type, data = self.serde.dumps_typed(obj)
    return data.decode("utf-8")  # ← 여기서 새로운 문제 발생 (PR #523)

def _deserialize(self, data):
    return self.serde.loads_typed(("json", data.encode("utf-8")))  # ← type tag 하드코딩
```

---

## 6. Legacy Checkpoint str 메시지 잔존 (PR #522)

### 6.1 에러 로그

PR #521 배포 후에도 동일 에러 재발:

```
AttributeError: 'str' object has no attribute 'type'
```

### 6.2 원인

Redis TTL 24시간 내 `json.dumps(default=str)`로 저장된 legacy checkpoint 잔존.
`_deserialize`의 legacy 폴백(`json.loads`)이 이 데이터를 plain string으로 복원.

### 6.3 수정

`intent_node.py`에 방어 가드 추가:

```python
for msg in messages[-6:]:
    if isinstance(msg, str):
        continue  # legacy checkpoint (pre-serde)
    role = "user" if msg.type == "human" else "assistant"
    ...
```

다른 노드 검증 결과:

| 노드 | 방어 코드 | 상태 |
|------|-----------|------|
| `intent_node.py` | `isinstance(msg, str): continue` | PR #522에서 추가 |
| `answer_node.py` | `getattr(msg, "type", "user")` | 이미 안전 |
| `summarization.py` | `hasattr(msg, "content")` 필터 | 이미 안전 |

---

## 7. msgpack 바이너리 UTF-8 디코딩 불가 (PR #523)

### 7.1 발견 경위

LangGraph 공식 문서 확인 중 `JsonPlusSerializer`가 **msgpack** 포맷을 사용함을 확인:

```python
>>> from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
>>> serde = JsonPlusSerializer()
>>> serde.dumps_typed(HumanMessage(content='hello'))
('msgpack', b'\xc7\x8a\x05\x94\xbdlangchain_core...')
#  ^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#  type tag   msgpack binary (NOT utf-8 decodable)
```

### 7.2 PR #521의 치명적 결함

```python
def _serialize(self, obj):
    _type, data = self.serde.dumps_typed(obj)
    return data.decode("utf-8")  # UnicodeDecodeError! msgpack은 UTF-8이 아님

def _deserialize(self, data):
    return self.serde.loads_typed(("json", data.encode("utf-8")))
    #                              ^^^^^^ 하드코딩 — 실제는 "msgpack"
```

두 가지 문제:
1. `data.decode("utf-8")` → msgpack 바이너리는 UTF-8 디코딩 불가
2. `("json", ...)` 하드코딩 → 실제 type tag는 `"msgpack"`

### 7.3 수정

Redis는 `decode_responses=True`로 string만 저장 가능하므로 base64 인코딩 사용:

```python
import base64

def _serialize(self, obj: Any) -> str:
    type_tag, data = self.serde.dumps_typed(obj)
    encoded = base64.b64encode(data).decode("ascii")
    return f"{type_tag}:{encoded}"
    # 예: "msgpack:x5QFlL1sYW5nY2hhaW..."

def _deserialize(self, data: str) -> Any:
    if ":" in data:
        type_tag, encoded = data.split(":", 1)
        if type_tag in ("msgpack", "json"):
            raw = base64.b64decode(encoded)
            return self.serde.loads_typed((type_tag, raw))
    # Legacy 폴백
    return json.loads(data)
```

### 7.4 검증

```python
# Roundtrip 테스트
>>> _serialize(HumanMessage(content='안녕하세요'))
'msgpack:x5QFlL1sYW5nY2hhaW5fY29yZS...'

>>> _deserialize('msgpack:x5QFlL1sYW5nY2hhaW5fY29yZS...')
HumanMessage(content='안녕하세요')  # type + content 보존 ✓

# Legacy 호환
>>> _deserialize('{"id": "old-cp", "v": 1}')
{'id': 'old-cp', 'v': 1}  # json.loads 폴백 ✓
```

### 7.5 추가 수정: `aput()` 시그니처

```python
# Before (비표준)
async def aput(self, config, checkpoint, metadata, new_versions, stream_mode="values"):

# After (BaseCheckpointSaver 인터페이스 준수)
async def aput(self, config, checkpoint, metadata, new_versions):
```

---

## 8. 교훈

### 8.1 redis-py vs aioredis 혼동

| 항목 | redis-py (>=5.x) | aioredis (v1.x, deprecated) |
|------|-------------------|----------------------------|
| Pool 크기 | `max_connections` | `minsize` / `maxsize` |
| 비동기 | `redis.asyncio` | `aioredis.create_pool()` |
| `min_connections` | **존재하지 않음** | `minsize`로 구현 |

Unknown kwargs는 `ConnectionPool` → `Connection.__init__()`으로 전달되어 TypeError 발생.
에러가 `try/except`에 삼켜져 로그에서 보이지 않았음.

### 8.2 JsonPlusSerializer는 JSON이 아닌 msgpack

이름과 달리 `JsonPlusSerializer`는 msgpack 바이너리를 생성:
- `dumps_typed()` → `("msgpack", bytes)` — JSON string이 아님
- Redis string 저장 시 base64 인코딩 필수
- type tag 보존 필수 (deserialize 시 필요)

### 8.3 `default=str`의 위험성

`json.dumps(obj, default=str)`는 "직렬화 안 되는 건 str()로 변환"하는 편의 옵션이지만:
- `HumanMessage(content="hi")` → `"human: hi"` (타입 정보 소실)
- 역직렬화 시 원래 객체 복원 불가능
- checkpoint처럼 타입 정보가 중요한 곳에서는 절대 사용 금지

### 8.4 에러 로그 가시성

```python
# BAD: extra dict는 로그 포맷에 따라 미노출
logger.error("failed", extra={"error": str(e)})

# GOOD: 메시지 본문에 포함 → 항상 노출
logger.error("failed: %s: %s", type(e).__name__, e, extra={...})
```

---

## 9. 배포 순서

```
PR #523 (serde msgpack+base64) → merge → ArgoCD sync
PR #522 (intent_node guard)    → merge → ArgoCD sync
```

#523이 먼저 배포되어야 새 checkpoint가 올바르게 저장됨.
#522는 legacy checkpoint (TTL 24h 내 잔존) 방어용.
