# Celery + RabbitMQ 트러블슈팅 가이드

> 비동기 아키텍처 전환 과정에서 발생한 주요 이슈와 해결 방법을 정리한다.

---

## 1. Quorum Queue + Celery 호환성

### 증상

```
amqp.exceptions.AMQPNotImplementedError: Basic.consume: (540) NOT_IMPLEMENTED 
- queue 'scan.vision' in vhost 'eco2' does not support global qos
```

### 원인

- Quorum Queue는 `global_qos`를 지원하지 않음
- Celery는 기본적으로 `global_qos=True` 사용

### 해결

**방법 1: broker_transport_options 설정 (Quorum 유지)**

```python
# ❌ dict로 설정 시 nested 옵션이 무시됨
celery_app.config_from_object(settings.get_celery_config())

# ✅ conf.update() 사용
celery_app.conf.update(settings.get_celery_config())

# 설정 내용
"broker_transport_options": {"global_qos": False}
```

**방법 2: Classic Queue로 전환 (권장)**

단일 노드 RabbitMQ에서는 Quorum Queue의 HA 이점이 없으므로 Classic Queue가 적합하다.

```yaml
# workloads/rabbitmq/base/topology/queues.yaml
spec:
  type: classic  # quorum 대신 classic
```

---

## 2. Celery 설정과 Topology CR 불일치

### 증상

```
PRECONDITION_FAILED - inequivalent arg 'x-dead-letter-routing-key' 
for queue 'my.reward' in vhost 'eco2': 
received none but current is the value 'dlq.my.reward'
```

### 원인

RabbitMQ Messaging Topology Operator가 생성한 큐와 Celery Worker가 declare하는 큐의 arguments가 불일치.

### 해결

Celery `task_queues`와 Topology CR의 arguments를 **완전히 동일하게** 설정:

```python
# domains/_shared/celery/config.py
Queue(
    "my.reward",
    default_exchange,
    routing_key="my.reward",
    queue_arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "dlq.my.reward",
        "x-message-ttl": 86400000,
    },
),
```

```yaml
# workloads/rabbitmq/base/topology/queues.yaml
spec:
  name: my.reward
  type: classic
  arguments:
    x-dead-letter-exchange: dlx
    x-dead-letter-routing-key: dlq.my.reward
    x-message-ttl: 86400000
```

---

## 3. Worker 간 코드 의존성 (fastapi import)

### 증상

```
ModuleNotFoundError: No module named 'fastapi'
```

scan-worker에서 character 도메인 서비스를 직접 import 시 발생.

### 원인

```python
# scan.reward 내부 (scan-worker)
from domains.character.services.evaluators import evaluate_reward
```

이 import 체인이 fastapi를 필요로 하는 모듈까지 전파됨.

### 해결

`send_task()`로 도메인 간 통신. import 없이 메시지만 전달:

```python
# ❌ 직접 import
from domains.character.services.evaluators import evaluate_reward
result = evaluate_reward(...)

# ✅ send_task로 분리
async_result = celery_app.send_task(
    "character.match",
    kwargs={...},
    queue="character.match",
)
```

---

## 4. services/__init__.py re-export 문제

### 증상

```
ImportError: cannot import name 'CharacterService' from 'domains.character.services'
```

### 원인

`services/__init__.py`에서 re-export 시 Python이 패키지 전체를 초기화:

```python
# services/__init__.py
from .character import CharacterService  # fastapi import 발생
```

### 해결

`__init__.py`에서 re-export 제거. 필요 시 직접 import:

```python
# 사용처에서 직접 import
from domains.character.services.character import CharacterService
```

---

## 5. Task 내 동기 호출 차단

### 증상

```
RuntimeError: Never call result.get() within a task!
```

### 원인

Celery는 task 내에서 `result.get()` 호출을 기본적으로 차단 (데드락 방지).

### 해결

**별도 Worker에서 처리되는 경우** `disable_sync_subtasks=False` 명시:

```python
# scan-worker에서 character-match-worker의 task 호출
result = async_result.get(
    timeout=10,
    disable_sync_subtasks=False,  # 별도 Worker이므로 데드락 위험 없음
)
```

---

## 6. Fanout Exchange 메시지 브로드캐스트 실패

### 증상

Fanout Exchange에 메시지 발행 시 한 Consumer만 메시지 수신.

### 원인

모든 Consumer가 동일한 고정 큐를 바라봄:

```python
# ❌ 고정 큐 이름 → 경쟁적 소비
self.queue = Queue(name="character.cache.events", exchange=CACHE_EXCHANGE)
```

### 해결

각 Consumer가 **익명 큐(exclusive)** 생성:

```python
# ✅ 익명 큐 → 브로드캐스트
self.queue = Queue(
    name="",               # RabbitMQ가 자동 생성 (amq.gen-xxxx)
    exchange=CACHE_EXCHANGE,
    exclusive=True,        # 이 연결만 사용
    auto_delete=True,      # 연결 종료 시 삭제
)
```

---

## 7. Worker 시작 시 캐시 비어있음

### 증상

Worker Pod 재시작 후 캐시가 비어있어 매칭 실패.

### 해결

**ArgoCD PostSync Hook으로 배포 완료 후 캐시 워밍업**:

```yaml
# workloads/domains/character-match-worker/base/cache-warmup-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: cache-warmup
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
spec:
  template:
    spec:
      containers:
      - name: cache-warmup
        command: [python3, -c, ...]
        # DB 조회 → full_refresh 이벤트 발행
```

---

## 8. celery-batches 설치 누락

### 증상

```
ModuleNotFoundError: No module named 'celery_batches'
```

### 원인

Worker 이미지가 상속하는 base 이미지에 패키지 미포함.

### 해결

```dockerfile
# domains/_base/requirements.txt
celery-batches>=0.8.1
```

base 이미지 리빌드 → Worker 이미지 리빌드.

---

## 9. 도메인별 DB URL 혼동

### 증상

my-worker에서 테이블 없음 에러. character DB에 연결됨.

### 원인

```python
# ❌ 범용 환경변수
settings.database_url  # character DB URL
```

### 해결

도메인별 전용 환경변수 사용:

```python
# ✅ my 도메인 전용
my_db_url = os.getenv("MY_DATABASE_URL")
```

---

## 10. 배치 저장과 동기 매칭 큐 혼합

### 증상

character.match 응답이 지연되어 타임아웃.

### 원인

동일 큐에서 배치 저장(5초 대기)과 동기 매칭(10초 타임아웃) 혼합 시, 배치 저장이 큐를 점유하여 동기 매칭이 밀림.

### 해결

**큐/Worker 분리**:

| 큐 | 특성 | Worker |
|-----|------|--------|
| `character.match` | 동기 응답, ~10ms | character-match-worker (concurrency 4) |
| `character.reward` | Fire&Forget, ~5초 | character-worker (concurrency 2) |

---

## 11. prefork Pool에서 캐시 미공유

### 증상

```
[INFO/MainProcess] cache_event_full_refresh
[WARNING/ForkPoolWorker-2] Character cache empty, cannot perform match
```

MainProcess에서 캐시 이벤트를 수신했으나, ForkPoolWorker에서 캐시가 비어있음.

### 원인

Celery `prefork` pool은 fork 시스템 콜로 Worker 프로세스를 생성한다.

```
MainProcess (Cache Consumer) ← cache_event_full_refresh
     │
     └─ fork()
          │
          └─ ForkPoolWorker (별도 프로세스)
               └─ 캐시 공유 불가 (프로세스 격리)
```

- fork 시점의 메모리 스냅샷은 복사되나, 이후 변경은 공유되지 않음
- 싱글톤 패턴은 **동일 프로세스 내**에서만 유효
- MainProcess에서 갱신된 캐시는 ForkPoolWorker에 반영되지 않음

### 해결

**threads pool 사용**:

```yaml
# workloads/domains/character-match-worker/base/deployment.yaml
args:
- -P
- threads  # prefork 대신 threads
- -c
- '4'
```

```
MainProcess (Cache Consumer + Thread Workers)
     │
     ├─ CacheConsumerThread → CharacterLocalCache (공유)
     │
     ├─ ThreadPoolExecutor-0 → CharacterLocalCache (공유)
     ├─ ThreadPoolExecutor-1 → CharacterLocalCache (공유)
     ├─ ThreadPoolExecutor-2 → CharacterLocalCache (공유)
     └─ ThreadPoolExecutor-3 → CharacterLocalCache (공유)
```

threads pool은 MainProcess 내에서 스레드로 task를 실행하므로 캐시가 공유된다.

### 적용 기준

| Pool | 사용 케이스 | 캐시 공유 |
|------|-------------|-----------|
| `prefork` | CPU-bound, 프로세스 격리 필요 | ❌ |
| `threads` | I/O-bound, 메모리 공유 필요 | ✅ |
| `gevent` | 고동시성 I/O-bound | ✅ |
| `solo` | 단일 프로세스, 디버깅 | ✅ |

character-match는 캐시 조회(메모리 I/O)가 주 작업이므로 `threads` pool이 적합하다.

---

## 12. PostSync Hook Job DB 인증 실패

### 증상

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "sesacthon"
```

### 원인

- 인라인 Python 스크립트에서 환경변수 참조 시 shell 특수문자 이슈
- `envFrom` 순서가 기존 Deployment와 불일치

### 해결

**독립 모듈로 분리**:

```yaml
# cache-warmup-job.yaml
command: [python3, -m, domains.character.jobs.warmup_cache]
envFrom:
- configMapRef:
    name: character-config  # configMap 먼저
- secretRef:
    name: character-secret  # secret 나중 (덮어쓰기)
```

```python
# domains/character/jobs/warmup_cache.py
async def warmup_cache() -> None:
    db_url = os.getenv("CHARACTER_DATABASE_URL")
    # ...
```

---

## References

- [RabbitMQ Quorum vs Classic Queues](https://www.rabbitmq.com/blog/2020/04/20/quorum-queues-vs-classic-queues/)
- [Celery Task Execution](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [RabbitMQ Fanout Exchange](https://www.rabbitmq.com/tutorials/tutorial-three-python.html)
- [ArgoCD Resource Hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)

